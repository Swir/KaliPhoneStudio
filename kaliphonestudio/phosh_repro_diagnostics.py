"""Fail-closed diagnostics for divergent Phosh A/B canonical rootfs builds.

A diagnostic report is deliberately non-promoting: it can explain why two independent
host builds differ, but it cannot create reproducibility authority or grant hardware/
Beta credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any

from .phosh_reproducibility import (
    PhoshReproducibilityError,
    load_phosh_rootfs_build_evidence,
)


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MANIFEST_FIELDS = {
    "schema_version",
    "artifact_sha256",
    "artifact_size",
    "member_count",
    "entries",
    "diagnostic_only",
    "reproducibility_authority",
    "hardware_verified",
    "beta_gate_credit",
}
_ENTRY_FIELDS = {
    "index",
    "path",
    "type_hex",
    "mode",
    "uid",
    "gid",
    "uname",
    "gname",
    "linkname",
    "size",
    "devmajor",
    "devminor",
    "pax_headers",
    "content_sha256",
}
_RECORD_COMPARE_FIELDS = tuple(sorted(_ENTRY_FIELDS - {"index"}))
# Consume the complete bounded output produced by rootfs_member_manifest. A diagnostic
# reader must not reject a manifest that the paired writer is explicitly allowed to emit.
_MAX_MANIFEST_BYTES = 192 * 1024 * 1024
_MAX_DIFFERENCES = 200


class PhoshReproDiagnosticError(PhoshReproducibilityError):
    """Raised when diagnostic input is malformed, detached or unsafe."""


def _safe_text(value: Any, label: str, *, allow_empty: bool = True) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise PhoshReproDiagnosticError(f"{label} must be text")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise PhoshReproDiagnosticError(f"{label} contains control characters")
    return value


def _safe_manifest_path(value: Any) -> str:
    """Validate the normalized member spelling emitted by rootfs_member_manifest."""
    name = _safe_text(value, "rootfs member path", allow_empty=False)
    parsed = PurePosixPath(name)
    if parsed.is_absolute() or ".." in parsed.parts:
        raise PhoshReproDiagnosticError("rootfs member manifest contains an unsafe path")
    parts = tuple(part for part in parsed.parts if part not in {"", "."})
    if not parts:
        if name != ".":
            raise PhoshReproDiagnosticError("rootfs member manifest contains an unsafe path")
        return name
    if name != "/".join(parts):
        raise PhoshReproDiagnosticError("rootfs member manifest contains an unsafe path")
    return name


def _nonnegative_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise PhoshReproDiagnosticError(f"{label} must be a non-negative integer")
    return value


@dataclass(frozen=True)
class PhoshRootfsDifference:
    path: str
    kind: str
    fields: tuple[str, ...]


@dataclass(frozen=True)
class PhoshRootfsReproducibilityDiagnostic:
    schema_version: int
    build_a_evidence_sha256: str
    build_b_evidence_sha256: str
    member_manifest_a_sha256: str
    member_manifest_b_sha256: str
    artifact_bytes_identical: bool
    package_manifest_identical: bool
    member_path_set_identical: bool
    member_order_identical: bool
    member_records_identical: bool
    ordering_only_difference: bool
    archive_encoding_only_difference: bool
    differing_member_count: int
    reported_difference_count: int
    differences_truncated: bool
    differences: tuple[PhoshRootfsDifference, ...]
    review_required: bool = True
    diagnostic_only: bool = True
    reproducibility_authority: bool = False
    physical_validation_required: bool = True
    hardware_verified: bool = False
    beta_gate_credit: bool = False

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _canonical_payload(raw: dict[str, Any]) -> bytes:
    return (json.dumps(raw, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _load_member_manifest(
    path: Path, *, expected_artifact_sha256: str, expected_artifact_size: int
) -> tuple[dict[str, Any], str]:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise PhoshReproDiagnosticError(
            "rootfs member manifest must be a regular non-symlink file"
        )
    try:
        payload = candidate.read_bytes()
    except OSError as exc:
        raise PhoshReproDiagnosticError(f"cannot read rootfs member manifest: {exc}") from exc
    if not payload or len(payload) > _MAX_MANIFEST_BYTES:
        raise PhoshReproDiagnosticError("rootfs member manifest has invalid size")
    try:
        raw = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhoshReproDiagnosticError(f"invalid rootfs member manifest JSON: {exc}") from exc
    if not isinstance(raw, dict) or set(raw) != _MANIFEST_FIELDS:
        raise PhoshReproDiagnosticError("unexpected rootfs member-manifest fields")
    if payload != _canonical_payload(raw):
        raise PhoshReproDiagnosticError("rootfs member manifest must use canonical JSON bytes")
    if raw.get("schema_version") != 1:
        raise PhoshReproDiagnosticError("unsupported rootfs member-manifest schema")
    if raw.get("diagnostic_only") is not True:
        raise PhoshReproDiagnosticError("rootfs member manifest must remain diagnostic-only")
    if (
        raw.get("reproducibility_authority") is not False
        or raw.get("hardware_verified") is not False
        or raw.get("beta_gate_credit") is not False
    ):
        raise PhoshReproDiagnosticError(
            "rootfs member manifest cannot grant authority/hardware/Beta credit"
        )
    artifact_sha256 = raw.get("artifact_sha256")
    if not isinstance(artifact_sha256, str) or not _SHA256_RE.fullmatch(artifact_sha256):
        raise PhoshReproDiagnosticError("rootfs member manifest artifact SHA-256 is invalid")
    if artifact_sha256 != expected_artifact_sha256:
        raise PhoshReproDiagnosticError("rootfs member manifest is detached from build artifact")
    if raw.get("artifact_size") != expected_artifact_size:
        raise PhoshReproDiagnosticError("rootfs member manifest artifact size is detached")
    entries = raw.get("entries")
    count = raw.get("member_count")
    if (
        not isinstance(entries, list)
        or not isinstance(count, int)
        or isinstance(count, bool)
        or count <= 0
        or count != len(entries)
    ):
        raise PhoshReproDiagnosticError("rootfs member manifest member count is invalid")
    seen: set[str] = set()
    for expected_index, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) != _ENTRY_FIELDS:
            raise PhoshReproDiagnosticError("unexpected rootfs member record fields")
        if entry.get("index") != expected_index:
            raise PhoshReproDiagnosticError("rootfs member manifest index sequence is invalid")
        name = _safe_manifest_path(entry.get("path"))
        if name in seen:
            raise PhoshReproDiagnosticError("rootfs member manifest contains duplicate path")
        seen.add(name)
        type_hex = _safe_text(entry.get("type_hex"), "rootfs member type", allow_empty=False)
        if len(type_hex) != 2 or any(char not in "0123456789abcdef" for char in type_hex):
            raise PhoshReproDiagnosticError("rootfs member type must be one lowercase byte in hex")
        for field in ("mode", "uid", "gid", "size", "devmajor", "devminor"):
            _nonnegative_int(entry.get(field), f"rootfs member {field}")
        for field in ("uname", "gname", "linkname"):
            _safe_text(entry.get(field), f"rootfs member {field}")
        digest = entry.get("content_sha256")
        if digest is not None and (
            not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest)
        ):
            raise PhoshReproDiagnosticError("rootfs member content SHA-256 is invalid")
        pax = entry.get("pax_headers")
        if not isinstance(pax, list):
            raise PhoshReproDiagnosticError("rootfs member PAX headers are invalid")
        for pair in pax:
            if not isinstance(pair, list) or len(pair) != 2:
                raise PhoshReproDiagnosticError("rootfs member PAX headers are invalid")
            _safe_text(pair[0], "rootfs member PAX key", allow_empty=False)
            value = _safe_text(pair[1], "rootfs member PAX value", allow_empty=False)
            if not value.startswith("hex:"):
                raise PhoshReproDiagnosticError(
                    "rootfs member PAX value must use the exact hex encoding"
                )
            encoded = value[4:]
            if len(encoded) % 2 or any(char not in "0123456789abcdef" for char in encoded):
                raise PhoshReproDiagnosticError(
                    "rootfs member PAX value has invalid hex encoding"
                )
    return raw, sha256(payload).hexdigest()


def _records_by_path(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {entry["path"]: entry for entry in entries}


def diagnose_phosh_rootfs_builds(
    build_a_path: Path,
    build_b_path: Path,
    member_manifest_a_path: Path,
    member_manifest_b_path: Path,
) -> PhoshRootfsReproducibilityDiagnostic:
    build_a, build_a_digest = load_phosh_rootfs_build_evidence(build_a_path)
    build_b, build_b_digest = load_phosh_rootfs_build_evidence(build_b_path)

    for field in (
        "upstream_commit",
        "source_lock_sha256",
        "build_contract_sha256",
        "build_plan_sha256",
    ):
        if build_a[field] != build_b[field]:
            raise PhoshReproDiagnosticError(f"Phosh A/B build identity mismatch: {field}")

    manifest_a, manifest_a_digest = _load_member_manifest(
        member_manifest_a_path,
        expected_artifact_sha256=build_a["artifact_sha256"],
        expected_artifact_size=build_a["artifact_size"],
    )
    manifest_b, manifest_b_digest = _load_member_manifest(
        member_manifest_b_path,
        expected_artifact_sha256=build_b["artifact_sha256"],
        expected_artifact_size=build_b["artifact_size"],
    )

    entries_a = manifest_a["entries"]
    entries_b = manifest_b["entries"]
    paths_a = [entry["path"] for entry in entries_a]
    paths_b = [entry["path"] for entry in entries_b]
    map_a = _records_by_path(entries_a)
    map_b = _records_by_path(entries_b)
    set_a = set(map_a)
    set_b = set(map_b)

    path_set_identical = set_a == set_b
    order_identical = paths_a == paths_b

    differences: list[PhoshRootfsDifference] = []
    differing_member_count = 0
    for path in sorted(set_a | set_b):
        if path not in map_a:
            differing_member_count += 1
            if len(differences) < _MAX_DIFFERENCES:
                differences.append(
                    PhoshRootfsDifference(path=path, kind="only_in_build_b", fields=("path",))
                )
            continue
        if path not in map_b:
            differing_member_count += 1
            if len(differences) < _MAX_DIFFERENCES:
                differences.append(
                    PhoshRootfsDifference(path=path, kind="only_in_build_a", fields=("path",))
                )
            continue
        changed_fields = tuple(
            field
            for field in _RECORD_COMPARE_FIELDS
            if map_a[path].get(field) != map_b[path].get(field)
        )
        if changed_fields:
            differing_member_count += 1
            if len(differences) < _MAX_DIFFERENCES:
                differences.append(
                    PhoshRootfsDifference(
                        path=path, kind="record_mismatch", fields=changed_fields
                    )
                )

    member_records_identical = path_set_identical and differing_member_count == 0
    artifact_bytes_identical = (
        build_a["artifact_sha256"] == build_b["artifact_sha256"]
        and build_a["artifact_size"] == build_b["artifact_size"]
    )
    package_manifest_identical = (
        build_a["package_manifest_sha256"] == build_b["package_manifest_sha256"]
        and build_a["package_count"] == build_b["package_count"]
    )
    ordering_only_difference = (
        not artifact_bytes_identical
        and member_records_identical
        and not order_identical
    )
    archive_encoding_only_difference = (
        not artifact_bytes_identical
        and member_records_identical
        and order_identical
    )

    return PhoshRootfsReproducibilityDiagnostic(
        schema_version=1,
        build_a_evidence_sha256=build_a_digest,
        build_b_evidence_sha256=build_b_digest,
        member_manifest_a_sha256=manifest_a_digest,
        member_manifest_b_sha256=manifest_b_digest,
        artifact_bytes_identical=artifact_bytes_identical,
        package_manifest_identical=package_manifest_identical,
        member_path_set_identical=path_set_identical,
        member_order_identical=order_identical,
        member_records_identical=member_records_identical,
        ordering_only_difference=ordering_only_difference,
        archive_encoding_only_difference=archive_encoding_only_difference,
        differing_member_count=differing_member_count,
        reported_difference_count=len(differences),
        differences_truncated=differing_member_count > len(differences),
        differences=tuple(differences),
    )


def write_phosh_rootfs_reproducibility_diagnostic(
    diagnostic: PhoshRootfsReproducibilityDiagnostic, destination: Path
) -> str:
    if not isinstance(diagnostic, PhoshRootfsReproducibilityDiagnostic):
        raise PhoshReproDiagnosticError("invalid Phosh reproducibility diagnostic type")
    if (
        diagnostic.schema_version != 1
        or diagnostic.review_required is not True
        or diagnostic.diagnostic_only is not True
        or diagnostic.reproducibility_authority is not False
        or diagnostic.physical_validation_required is not True
        or diagnostic.hardware_verified is not False
        or diagnostic.beta_gate_credit is not False
    ):
        raise PhoshReproDiagnosticError(
            "Phosh reproducibility diagnostic cannot promote authority/hardware/Beta state"
        )
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise PhoshReproDiagnosticError("refusing to overwrite Phosh reproducibility diagnostic")
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = diagnostic.canonical_json().encode("utf-8")
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise PhoshReproDiagnosticError("refusing stale Phosh reproducibility diagnostic temporary file")
    try:
        temporary.write_bytes(payload)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return sha256(payload).hexdigest()
