from __future__ import annotations

from collections import Counter
import hashlib
import json
import lzma
import os
import tarfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO


class RootfsReproDiagnosticError(ValueError):
    """Raised when a rootfs archive cannot be diagnosed safely."""


_CHUNK_SIZE = 1024 * 1024
_METADATA_FIELDS = (
    "mode",
    "uid",
    "gid",
    "uname",
    "gname",
    "mtime",
    "size",
    "linkname",
    "pax_headers",
)
# When a report has to be truncated, preserve the differences that are most
# useful for fixing a failed reproducibility run. Thousands of build-time mtime
# changes must not hide a small number of changed payload files.
_DIFFERENCE_PRIORITY = {
    "type": 0,
    "content": 1,
    "added": 2,
    "removed": 3,
    "order": 4,
    "metadata": 5,
}
_DIFFERENCE_KINDS = tuple(_DIFFERENCE_PRIORITY)


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _sha256_stream(handle: BinaryIO) -> str:
    digest = hashlib.sha256()
    while True:
        chunk = handle.read(_CHUNK_SIZE)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


def _safe_parts(name: str) -> tuple[str, ...]:
    if not isinstance(name, str) or "\x00" in name:
        raise RootfsReproDiagnosticError("tar member name is invalid")
    if name.startswith("/"):
        raise RootfsReproDiagnosticError(
            f"absolute tar member path rejected: {name!r}"
        )
    parts: list[str] = []
    for part in PurePosixPath(name).parts:
        if part in ("", "."):
            continue
        if part == "..":
            raise RootfsReproDiagnosticError(
                f"tar traversal path rejected: {name!r}"
            )
        parts.append(part)
    return tuple(parts)


def _member_type(member: tarfile.TarInfo) -> str:
    if member.isreg():
        return "file"
    if member.isdir():
        return "dir"
    if member.issym():
        return "symlink"
    if member.islnk():
        return "hardlink"
    if member.ischr():
        return "char"
    if member.isblk():
        return "block"
    if member.isfifo():
        return "fifo"
    return "other"


def _json_scalar(value: Any) -> Any:
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return value
    return str(value)


@dataclass(frozen=True)
class _ArchiveScan:
    sha256: str
    size_bytes: int
    stripped_prefix: str | None
    order: tuple[str, ...]
    records: dict[str, dict[str, Any]]

    def summary(self) -> dict[str, Any]:
        return {
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "member_count": len(self.records),
            "stripped_prefix": self.stripped_prefix,
        }


def _scan_archive(path: Path) -> _ArchiveScan:
    path = Path(path)
    if not path.is_file():
        raise RootfsReproDiagnosticError(
            "rootfs archive is missing or is not a regular file"
        )
    archive_sha256, archive_size = _sha256_file(path)

    try:
        with tarfile.open(path, mode="r:xz") as archive:
            raw_members: list[tuple[tarfile.TarInfo, tuple[str, ...]]] = []
            raw_seen: set[tuple[str, ...]] = set()
            for member in archive:
                parts = _safe_parts(member.name)
                if not parts:
                    continue
                if parts in raw_seen:
                    raise RootfsReproDiagnosticError(
                        "duplicate normalized tar member rejected: "
                        f"{'/'.join(parts)!r}"
                    )
                raw_seen.add(parts)
                raw_members.append((member, parts))

            prefix: str | None = None
            if raw_members:
                first = raw_members[0][1][0]
                if all(
                    parts[0] == first for _, parts in raw_members
                ) and any(len(parts) > 1 for _, parts in raw_members):
                    prefix = first

            records: dict[str, dict[str, Any]] = {}
            order: list[str] = []
            for member, parts in raw_members:
                canonical_parts = parts
                if prefix is not None:
                    if parts == (prefix,):
                        continue
                    canonical_parts = parts[1:]
                if not canonical_parts:
                    continue
                canonical_path = "/".join(canonical_parts)
                if canonical_path in records:
                    raise RootfsReproDiagnosticError(
                        "duplicate canonical tar member rejected after prefix "
                        f"normalization: {canonical_path!r}"
                    )

                record: dict[str, Any] = {
                    "type": _member_type(member),
                    "mode": int(member.mode),
                    "uid": int(member.uid),
                    "gid": int(member.gid),
                    "uname": member.uname or "",
                    "gname": member.gname or "",
                    "mtime": _json_scalar(member.mtime),
                    "size": int(member.size),
                    "linkname": member.linkname or "",
                    "pax_headers": {
                        str(key): str(value)
                        for key, value in sorted(
                            (member.pax_headers or {}).items()
                        )
                    },
                }
                if member.isreg():
                    fileobj = archive.extractfile(member)
                    if fileobj is None:
                        raise RootfsReproDiagnosticError(
                            "unable to read regular tar member: "
                            f"{member.name!r}"
                        )
                    with fileobj:
                        record["content_sha256"] = _sha256_stream(fileobj)
                else:
                    record["content_sha256"] = None

                records[canonical_path] = record
                order.append(canonical_path)
    except (tarfile.TarError, lzma.LZMAError) as exc:
        raise RootfsReproDiagnosticError(
            f"invalid tar.xz rootfs archive: {exc}"
        ) from exc
    except OSError as exc:
        raise RootfsReproDiagnosticError(
            f"unable to read rootfs archive: {exc}"
        ) from exc

    return _ArchiveScan(
        sha256=archive_sha256,
        size_bytes=archive_size,
        stripped_prefix=prefix,
        order=tuple(order),
        records=records,
    )


def _compare_scans(
    left: _ArchiveScan,
    right: _ArchiveScan,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    differences: list[dict[str, Any]] = []
    left_paths = set(left.records)
    right_paths = set(right.records)

    added_paths = sorted(right_paths - left_paths)
    removed_paths = sorted(left_paths - right_paths)
    for path in added_paths:
        differences.append({"kind": "added", "path": path})
    for path in removed_paths:
        differences.append({"kind": "removed", "path": path})

    type_changed = 0
    metadata_changed = 0
    metadata_mtime_only = 0
    metadata_field_changes: Counter[str] = Counter()
    content_changed = 0

    for path in sorted(left_paths & right_paths):
        first = left.records[path]
        second = right.records[path]
        if first["type"] != second["type"]:
            type_changed += 1
            differences.append(
                {
                    "kind": "type",
                    "path": path,
                    "left": first["type"],
                    "right": second["type"],
                }
            )

        changed_fields: dict[str, dict[str, Any]] = {}
        for field in _METADATA_FIELDS:
            if first[field] != second[field]:
                metadata_field_changes[field] += 1
                changed_fields[field] = {
                    "left": first[field],
                    "right": second[field],
                }
        if changed_fields:
            metadata_changed += 1
            if set(changed_fields) == {"mtime"}:
                metadata_mtime_only += 1
            differences.append(
                {
                    "kind": "metadata",
                    "path": path,
                    "fields": changed_fields,
                }
            )

        if first.get("content_sha256") != second.get("content_sha256"):
            content_changed += 1
            differences.append(
                {
                    "kind": "content",
                    "path": path,
                    "left_sha256": first.get("content_sha256"),
                    "right_sha256": second.get("content_sha256"),
                }
            )

    order_changed = left.order != right.order
    if order_changed:
        differences.append(
            {
                "kind": "order",
                "left_member_count": len(left.order),
                "right_member_count": len(right.order),
            }
        )

    # Actionable differences come first. In particular, a small number of
    # content changes must remain visible even when thousands of timestamps
    # differ and the JSON report has a strict output limit.
    differences.sort(
        key=lambda item: (
            _DIFFERENCE_PRIORITY.get(str(item.get("kind", "")), 99),
            str(item.get("path", "")),
            str(item.get("kind", "")),
        )
    )
    summary = {
        "added": len(added_paths),
        "removed": len(removed_paths),
        "type_changed": type_changed,
        "metadata_changed": metadata_changed,
        "metadata_mtime_only": metadata_mtime_only,
        "metadata_field_changes": {
            field: metadata_field_changes.get(field, 0)
            for field in _METADATA_FIELDS
            if metadata_field_changes.get(field, 0)
        },
        "content_changed": content_changed,
        "order_changed": order_changed,
        "difference_count_total": len(differences),
    }
    return summary, differences


def _reporting_summary(
    all_differences: list[dict[str, Any]],
    reported: list[dict[str, Any]],
) -> dict[str, Any]:
    total = Counter(str(item.get("kind", "unknown")) for item in all_differences)
    emitted = Counter(str(item.get("kind", "unknown")) for item in reported)
    kinds = list(_DIFFERENCE_KINDS)
    for kind in sorted(set(total) - set(kinds)):
        kinds.append(kind)
    return {
        "priority": list(_DIFFERENCE_KINDS),
        "reported_by_kind": {
            kind: emitted.get(kind, 0) for kind in kinds if total.get(kind, 0)
        },
        "omitted_by_kind": {
            kind: total.get(kind, 0) - emitted.get(kind, 0)
            for kind in kinds
            if total.get(kind, 0) - emitted.get(kind, 0)
        },
    }


def build_rootfs_repro_diagnostics(
    archive_a: Path,
    archive_b: Path,
    *,
    max_differences: int = 200,
) -> dict[str, Any]:
    """Build a bounded canonical diagnostic report for two rootfs archives.

    The report is deliberately non-authoritative: it never grants Beta or
    release credit and it does not relax the project's strict byte-for-byte
    reproducibility requirement.
    """

    if (
        isinstance(max_differences, bool)
        or not isinstance(max_differences, int)
        or max_differences < 1
    ):
        raise RootfsReproDiagnosticError(
            "max_differences must be an integer >= 1"
        )

    left = _scan_archive(Path(archive_a))
    right = _scan_archive(Path(archive_b))
    summary, all_differences = _compare_scans(left, right)
    reported = all_differences[:max_differences]

    strict_reproducible = left.sha256 == right.sha256
    semantic_equal = summary["difference_count_total"] == 0
    return {
        "schema_version": 2,
        "kind": "kps.rootfs-repro-diagnostic",
        "beta_gate_credit": False,
        "strict_reproducible": strict_reproducible,
        "semantic_equal": semantic_equal,
        "container_only_difference": (
            not strict_reproducible and semantic_equal
        ),
        "left": left.summary(),
        "right": right.summary(),
        "summary": summary,
        "reporting": _reporting_summary(all_differences, reported),
        "differences": reported,
        "differences_truncated": len(all_differences) > max_differences,
        "max_differences": max_differences,
    }


def write_rootfs_repro_diagnostics(
    archive_a: Path,
    archive_b: Path,
    out_path: Path,
    *,
    max_differences: int = 200,
) -> dict[str, Any]:
    report = build_rootfs_repro_diagnostics(
        archive_a,
        archive_b,
        max_differences=max_differences,
    )
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(out_path.name + ".tmp")
    tmp.write_text(
        json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, out_path)
    return report
