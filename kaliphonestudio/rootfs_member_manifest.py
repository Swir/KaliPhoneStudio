"""Deterministic member-level manifest for canonical Kali rootfs archives.

This module is diagnostic-only. It records path/order, tar metadata and regular-file
content hashes from an already canonicalized rootfs so independent builds can identify
the exact source of byte drift without extracting the archive to the host filesystem.

The manifest never grants reproducibility authority, hardware verification or Beta
credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import tarfile
from typing import Any

from .rootfs import RootfsError


# A graphical Kali/Phosh rootfs can legitimately exceed the old 250k diagnostic-entry
# ceiling. The manifest remains hard-bounded by both member count and serialized bytes.
_MAX_MEMBERS = 400_000
_MAX_MANIFEST_BYTES = 192 * 1024 * 1024
_PAX_VALUE_PREFIX = "hex:"


@dataclass(frozen=True)
class RootfsMemberRecord:
    index: int
    path: str
    type_hex: str
    mode: int
    uid: int
    gid: int
    uname: str
    gname: str
    linkname: str
    size: int
    devmajor: int
    devminor: int
    pax_headers: tuple[tuple[str, str], ...]
    content_sha256: str | None


@dataclass(frozen=True)
class RootfsMemberManifest:
    schema_version: int
    artifact_sha256: str
    artifact_size: int
    member_count: int
    entries: tuple[RootfsMemberRecord, ...]
    diagnostic_only: bool = True
    reproducibility_authority: bool = False
    hardware_verified: bool = False
    beta_gate_credit: bool = False

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def manifest_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


class RootfsMemberManifestError(RootfsError):
    """Raised when a canonical rootfs cannot produce a safe diagnostic manifest."""


def _archive_sha256_and_size(path: Path) -> tuple[str, int]:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise RootfsMemberManifestError("canonical rootfs must be a regular non-symlink file")
    size = candidate.stat().st_size
    if size <= 0:
        raise RootfsMemberManifestError("canonical rootfs is empty")
    digest = sha256()
    with candidate.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest(), size


def _contains_control_text(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def _safe_member_name(name: Any) -> str:
    if (
        not isinstance(name, str)
        or not name
        or _contains_control_text(name)
    ):
        raise RootfsMemberManifestError("rootfs archive contains an invalid member name")
    path = PurePosixPath(name)
    if path.is_absolute():
        raise RootfsMemberManifestError("rootfs archive contains an absolute member path")
    parts = tuple(part for part in path.parts if part not in {"", "."})
    if ".." in parts:
        raise RootfsMemberManifestError("rootfs archive contains path traversal")
    # GNU/Python tar writers commonly preserve one explicit root-directory marker
    # named `.` or `./`. It is a safe canonical member, not a traversal. Keep one
    # stable spelling in the diagnostic manifest so real rootfs A/B artifacts can be
    # inspected without weakening rejection of absolute paths or `..` components.
    if not parts:
        return "."
    return "/".join(parts)


def _stable_text(value: Any, label: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or _contains_control_text(value):
        raise RootfsMemberManifestError(f"{label} must be safe text")
    return value


def _encoded_pax_value(value: Any) -> str:
    """Return one lossless, JSON/log-safe representation of a PAX value.

    Linux rootfs archives legitimately carry binary extended-attribute values such as
    ``SCHILY.xattr.security.capability``. ``tarfile`` exposes PAX records as ``str``
    and can preserve undecodable bytes through surrogate escapes, so rejecting control
    characters makes real package payloads impossible to diagnose. Encode the exact
    UTF-8/surrogateescaped byte sequence as lowercase hexadecimal instead. This is
    diagnostic representation only; the original archive bytes are never modified.
    """
    if not isinstance(value, str):
        raise RootfsMemberManifestError("PAX header value must be text")
    try:
        payload = value.encode("utf-8", errors="surrogateescape")
    except UnicodeEncodeError as exc:
        raise RootfsMemberManifestError("PAX header value cannot be represented safely") from exc
    return _PAX_VALUE_PREFIX + payload.hex()


def _pax_headers(raw: dict[str, str]) -> tuple[tuple[str, str], ...]:
    result: list[tuple[str, str]] = []
    for key, value in sorted(raw.items()):
        result.append((_stable_text(key, "PAX header key"), _encoded_pax_value(value)))
    return tuple(result)


def _regular_file_digest(archive: tarfile.TarFile, member: tarfile.TarInfo) -> str:
    handle = archive.extractfile(member)
    if handle is None:
        raise RootfsMemberManifestError(f"cannot read regular rootfs member: {member.name}")
    digest = sha256()
    total = 0
    while chunk := handle.read(1024 * 1024):
        total += len(chunk)
        digest.update(chunk)
    if total != member.size:
        raise RootfsMemberManifestError(
            f"rootfs member size changed while reading: {member.name}"
        )
    return digest.hexdigest()


def build_rootfs_member_manifest(path: Path) -> RootfsMemberManifest:
    """Create a member-level identity manifest from an already canonical rootfs archive."""
    candidate = Path(path)
    artifact_sha256, artifact_size = _archive_sha256_and_size(candidate)
    records: list[RootfsMemberRecord] = []
    seen: set[str] = set()
    try:
        # Stream the compressed archive exactly once. This avoids retaining every TarInfo
        # and avoids seek/re-decompression churn when hashing a large graphical rootfs.
        with tarfile.open(candidate, mode="r|xz") as archive:
            for index, member in enumerate(archive):
                if index >= _MAX_MEMBERS:
                    raise RootfsMemberManifestError("canonical rootfs archive has too many members")
                name = _safe_member_name(member.name)
                if name in seen:
                    raise RootfsMemberManifestError(
                        f"canonical rootfs archive contains duplicate path: {name}"
                    )
                seen.add(name)
                # The input is expected to be the canonical comparison artifact.
                if member.mtime != 0:
                    raise RootfsMemberManifestError(
                        f"canonical rootfs member has nonzero mtime: {name}"
                    )
                content_sha256 = (
                    _regular_file_digest(archive, member) if member.isfile() else None
                )
                records.append(
                    RootfsMemberRecord(
                        index=index,
                        path=name,
                        type_hex=bytes(member.type).hex(),
                        mode=int(member.mode),
                        uid=int(member.uid),
                        gid=int(member.gid),
                        uname=_stable_text(member.uname, "tar uname"),
                        gname=_stable_text(member.gname, "tar gname"),
                        linkname=_stable_text(member.linkname, "tar linkname"),
                        size=int(member.size),
                        devmajor=int(member.devmajor),
                        devminor=int(member.devminor),
                        pax_headers=_pax_headers(member.pax_headers),
                        content_sha256=content_sha256,
                    )
                )
    except (RootfsMemberManifestError, tarfile.TarError, OSError) as exc:
        if isinstance(exc, RootfsMemberManifestError):
            raise
        raise RootfsMemberManifestError(f"cannot inspect canonical rootfs archive: {exc}") from exc

    if not records:
        raise RootfsMemberManifestError("canonical rootfs archive has no members")
    return RootfsMemberManifest(
        schema_version=1,
        artifact_sha256=artifact_sha256,
        artifact_size=artifact_size,
        member_count=len(records),
        entries=tuple(records),
    )


def write_rootfs_member_manifest(
    manifest: RootfsMemberManifest, destination: Path
) -> str:
    if not isinstance(manifest, RootfsMemberManifest):
        raise RootfsMemberManifestError("invalid rootfs member manifest type")
    if (
        manifest.schema_version != 1
        or manifest.diagnostic_only is not True
        or manifest.reproducibility_authority is not False
        or manifest.hardware_verified is not False
        or manifest.beta_gate_credit is not False
        or manifest.member_count != len(manifest.entries)
    ):
        raise RootfsMemberManifestError("invalid rootfs member manifest policy")
    payload = manifest.canonical_json().encode("utf-8")
    if len(payload) > _MAX_MANIFEST_BYTES:
        raise RootfsMemberManifestError(
            f"rootfs member manifest is unexpectedly large: {len(payload)} bytes"
        )
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise RootfsMemberManifestError("refusing to overwrite rootfs member manifest")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise RootfsMemberManifestError("refusing stale rootfs member-manifest temporary file")
    try:
        temporary.write_bytes(payload)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return sha256(payload).hexdigest()
