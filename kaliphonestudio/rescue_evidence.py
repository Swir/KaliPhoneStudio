"""Strict loading and independent artifact revalidation for rescue initramfs evidence."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any

from .rescue_initramfs import RescueInitramfsError, RescueInitramfsEvidence


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_EVIDENCE_FIELDS = {
    "schema_version",
    "archive_format",
    "compression",
    "source_date_epoch",
    "source_tree_sha256",
    "artifact_sha256",
    "artifact_size",
    "entry_count",
    "init_sha256",
    "reproducible",
}
_MAX_ARTIFACT_SIZE = 160 * 1024 * 1024
_MAX_PATH_BYTES = 4096
_MAX_ENTRY_DATA = 32 * 1024 * 1024
_NEWC_HEADER_SIZE = 110
_NEWC_MAGIC = b"070701"
_TRAILER = "TRAILER!!!"


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise RescueInitramfsError(f"{label} must be a lowercase SHA-256 digest")
    return value


def evidence_from_dict(raw: dict[str, Any]) -> RescueInitramfsEvidence:
    if not isinstance(raw, dict) or set(raw) != _EVIDENCE_FIELDS:
        raise RescueInitramfsError("invalid rescue initramfs evidence fields")
    if raw["schema_version"] != 1:
        raise RescueInitramfsError("unsupported rescue initramfs evidence schema")
    if raw["archive_format"] != "newc" or raw["compression"] != "none":
        raise RescueInitramfsError("unsupported rescue initramfs artifact format")
    epoch = raw["source_date_epoch"]
    if not isinstance(epoch, int) or isinstance(epoch, bool) or not 0 <= epoch <= 0xFFFFFFFF:
        raise RescueInitramfsError("invalid rescue initramfs SOURCE_DATE_EPOCH")
    artifact_size = raw["artifact_size"]
    if (
        not isinstance(artifact_size, int)
        or isinstance(artifact_size, bool)
        or artifact_size < 512
        or artifact_size > _MAX_ARTIFACT_SIZE
        or artifact_size % 512 != 0
    ):
        raise RescueInitramfsError("invalid rescue initramfs artifact size")
    entry_count = raw["entry_count"]
    if not isinstance(entry_count, int) or isinstance(entry_count, bool) or entry_count <= 0 or entry_count > 4096:
        raise RescueInitramfsError("invalid rescue initramfs entry count")
    if raw["reproducible"] is not True:
        raise RescueInitramfsError("rescue initramfs evidence must prove reproducibility")
    return RescueInitramfsEvidence(
        schema_version=1,
        archive_format="newc",
        compression="none",
        source_date_epoch=epoch,
        source_tree_sha256=_require_sha256(raw["source_tree_sha256"], "source tree"),
        artifact_sha256=_require_sha256(raw["artifact_sha256"], "artifact"),
        artifact_size=artifact_size,
        entry_count=entry_count,
        init_sha256=_require_sha256(raw["init_sha256"], "init"),
        reproducible=True,
    )


def load_rescue_initramfs_evidence(path: Path) -> RescueInitramfsEvidence:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RescueInitramfsError(f"cannot read rescue initramfs evidence: {exc}") from exc
    return evidence_from_dict(raw)


def _align4(offset: int) -> int:
    return (offset + 3) & ~3


def _parse_hex_field(header: bytes, index: int) -> int:
    start = 6 + index * 8
    raw = header[start : start + 8]
    try:
        return int(raw, 16)
    except ValueError as exc:
        raise RescueInitramfsError("rescue initramfs contains a non-hex newc header field") from exc


def _safe_archive_name(raw: bytes) -> str:
    if not raw or raw[-1:] != b"\x00" or b"\x00" in raw[:-1]:
        raise RescueInitramfsError("rescue initramfs contains an invalid CPIO name")
    if len(raw) - 1 > _MAX_PATH_BYTES:
        raise RescueInitramfsError("rescue initramfs contains an oversized CPIO name")
    try:
        name = raw[:-1].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RescueInitramfsError("rescue initramfs contains a non-UTF-8 CPIO name") from exc
    if name == _TRAILER:
        return name
    path = PurePosixPath(name)
    if not name or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise RescueInitramfsError(f"unsafe rescue CPIO entry path: {name!r}")
    return name


def _validate_relative_symlink(entry_name: str, raw_target: bytes) -> None:
    if not raw_target or b"\x00" in raw_target or len(raw_target) > _MAX_PATH_BYTES:
        raise RescueInitramfsError(f"invalid rescue symlink target: {entry_name}")
    try:
        target = raw_target.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RescueInitramfsError(f"non-UTF-8 rescue symlink target: {entry_name}") from exc
    target_path = PurePosixPath(target)
    if target_path.is_absolute():
        raise RescueInitramfsError(f"absolute rescue symlink target: {entry_name}")
    parts: list[str] = []
    for part in (*PurePosixPath(entry_name).parent.parts, *target_path.parts):
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                raise RescueInitramfsError(f"rescue symlink escapes root: {entry_name}")
            parts.pop()
        else:
            parts.append(part)
    if not parts:
        raise RescueInitramfsError(f"rescue symlink resolves to archive root: {entry_name}")


def _validate_newc_structure(data: bytes, evidence: RescueInitramfsEvidence) -> None:
    offset = 0
    entry_count = 0
    expected_ino = 1
    paths: set[str] = set()
    init_digest: str | None = None
    trailer_seen = False

    while offset < len(data):
        if len(data) - offset < _NEWC_HEADER_SIZE:
            raise RescueInitramfsError("truncated rescue newc header")
        header = data[offset : offset + _NEWC_HEADER_SIZE]
        if header[:6] != _NEWC_MAGIC:
            raise RescueInitramfsError("rescue initramfs is not a canonical newc CPIO archive")
        fields = [_parse_hex_field(header, index) for index in range(13)]
        ino, mode, uid, gid, nlink, mtime, filesize, devmaj, devmin, rdevmaj, rdevmin, namesize, check = fields
        offset += _NEWC_HEADER_SIZE

        if namesize <= 0 or namesize > _MAX_PATH_BYTES + 1 or offset + namesize > len(data):
            raise RescueInitramfsError("invalid rescue newc name size")
        name = _safe_archive_name(data[offset : offset + namesize])
        offset = _align4(offset + namesize)
        if offset > len(data) or filesize > _MAX_ENTRY_DATA or offset + filesize > len(data):
            raise RescueInitramfsError("invalid rescue newc entry size")
        payload = data[offset : offset + filesize]
        offset = _align4(offset + filesize)
        if offset > len(data):
            raise RescueInitramfsError("truncated rescue newc entry padding")

        if check != 0 or uid != 0 or gid != 0 or devmaj or devmin or rdevmaj or rdevmin:
            raise RescueInitramfsError("rescue newc metadata is not canonical")
        if mtime != evidence.source_date_epoch:
            raise RescueInitramfsError("rescue newc timestamp does not match evidence")

        if name == _TRAILER:
            if ino != 0 or mode != 0 or filesize != 0:
                raise RescueInitramfsError("invalid rescue newc trailer")
            trailer_seen = True
            break

        if ino != expected_ino:
            raise RescueInitramfsError("rescue newc inode sequence is not deterministic")
        expected_ino += 1
        entry_count += 1
        if entry_count > 4096:
            raise RescueInitramfsError("rescue newc contains too many entries")
        if name in paths:
            raise RescueInitramfsError("duplicate rescue newc entry path")
        paths.add(name)
        if nlink != 1:
            raise RescueInitramfsError("rescue newc nlink is not canonical")

        file_type = stat.S_IFMT(mode)
        perms = stat.S_IMODE(mode)
        if perms & 0o6000:
            raise RescueInitramfsError("setuid/setgid rescue entry found during verification")
        if file_type == stat.S_IFDIR:
            if filesize != 0:
                raise RescueInitramfsError("rescue directory contains unexpected payload bytes")
        elif file_type == stat.S_IFREG:
            if perms & 0o002:
                raise RescueInitramfsError("world-writable rescue regular file found during verification")
            if name == "init":
                if not perms & 0o111:
                    raise RescueInitramfsError("verified rescue /init is not executable")
                init_digest = sha256(payload).hexdigest()
        elif file_type == stat.S_IFLNK:
            _validate_relative_symlink(name, payload)
        else:
            raise RescueInitramfsError("special file found in verified rescue CPIO")

    if not trailer_seen:
        raise RescueInitramfsError("rescue newc trailer is missing")
    if entry_count != evidence.entry_count:
        raise RescueInitramfsError("rescue newc entry count does not match evidence")
    if init_digest != evidence.init_sha256:
        raise RescueInitramfsError("rescue /init SHA-256 does not match evidence")
    if any(data[offset:]):
        raise RescueInitramfsError("non-zero data follows rescue newc trailer")


def verify_rescue_initramfs_artifact(
    artifact: Path,
    evidence: RescueInitramfsEvidence,
) -> None:
    """Fail closed unless bytes, stable file identity and CPIO structure match evidence."""
    evidence = evidence_from_dict(json.loads(evidence.canonical_json()))
    if not artifact.is_file():
        raise RescueInitramfsError("rescue initramfs artifact does not exist")
    try:
        before = artifact.stat(follow_symlinks=False)
        if before.st_size != evidence.artifact_size or before.st_size > _MAX_ARTIFACT_SIZE:
            raise RescueInitramfsError("rescue initramfs size does not match evidence")
        data = artifact.read_bytes()
        after = artifact.stat(follow_symlinks=False)
    except OSError as exc:
        raise RescueInitramfsError(f"cannot verify rescue initramfs artifact: {exc}") from exc
    stable = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_mode")
    if any(getattr(before, field) != getattr(after, field) for field in stable):
        raise RescueInitramfsError("rescue initramfs changed while it was being verified")
    if len(data) != evidence.artifact_size:
        raise RescueInitramfsError("rescue initramfs size changed while it was being verified")
    if sha256(data).hexdigest() != evidence.artifact_sha256:
        raise RescueInitramfsError("rescue initramfs SHA-256 does not match evidence")
    _validate_newc_structure(data, evidence)
