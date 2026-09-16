"""Deterministic, device-independent rescue initramfs (newc CPIO) builder."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
from typing import Iterable


class RescueInitramfsError(ValueError):
    """Raised when a rescue initramfs tree or artifact violates the safety contract."""


_MAX_ENTRIES = 4096
_MAX_FILE_SIZE = 32 * 1024 * 1024
_MAX_TOTAL_FILE_BYTES = 128 * 1024 * 1024
_MAX_PATH_BYTES = 4096
_MAX_SYMLINK_BYTES = 4096


@dataclass(frozen=True)
class _Entry:
    path: str
    kind: str
    mode: int
    data: bytes


@dataclass(frozen=True)
class RescueInitramfsEvidence:
    schema_version: int
    archive_format: str
    compression: str
    source_date_epoch: int
    source_tree_sha256: str
    artifact_sha256: str
    artifact_size: int
    entry_count: int
    init_sha256: str
    reproducible: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _require_safe_archive_path(path: str) -> bytes:
    if not path or "\x00" in path or path.startswith("/"):
        raise RescueInitramfsError("initramfs entry path must be non-empty and relative")
    posix = PurePosixPath(path)
    if any(part in {"", ".", ".."} for part in posix.parts):
        raise RescueInitramfsError(f"unsafe initramfs entry path: {path}")
    try:
        encoded = path.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise RescueInitramfsError(f"initramfs path is not UTF-8 encodable: {path!r}") from exc
    if len(encoded) > _MAX_PATH_BYTES:
        raise RescueInitramfsError(f"initramfs entry path is too long: {path}")
    return encoded


def _normalize_symlink_target(entry_path: str, target: str) -> bytes:
    if not target or "\x00" in target:
        raise RescueInitramfsError(f"empty or invalid symlink target for {entry_path}")
    target_path = PurePosixPath(target)
    if target_path.is_absolute():
        raise RescueInitramfsError(f"absolute symlink target is not allowed: {entry_path} -> {target}")
    parts: list[str] = []
    for part in (*PurePosixPath(entry_path).parent.parts, *target_path.parts):
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                raise RescueInitramfsError(f"symlink escapes rescue root: {entry_path} -> {target}")
            parts.pop()
        else:
            parts.append(part)
    if not parts:
        raise RescueInitramfsError(f"symlink resolves to rescue root: {entry_path} -> {target}")
    try:
        encoded = target.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise RescueInitramfsError(f"symlink target is not UTF-8 encodable: {entry_path}") from exc
    if len(encoded) > _MAX_SYMLINK_BYTES:
        raise RescueInitramfsError(f"symlink target is too long: {entry_path}")
    return encoded


def _read_stable_file(path: Path) -> tuple[bytes, os.stat_result]:
    before = path.stat(follow_symlinks=False)
    if before.st_size < 0 or before.st_size > _MAX_FILE_SIZE:
        raise RescueInitramfsError(f"rescue file exceeds size limit: {path}")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise RescueInitramfsError(f"cannot read rescue file {path}: {exc}") from exc
    after = path.stat(follow_symlinks=False)
    stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_mode")
    if any(getattr(before, field) != getattr(after, field) for field in stable_fields):
        raise RescueInitramfsError(f"rescue file changed while it was being read: {path}")
    if len(data) != before.st_size:
        raise RescueInitramfsError(f"rescue file size changed while it was being read: {path}")
    return data, before


def _safe_mode(kind: str, raw_mode: int) -> int:
    perms = stat.S_IMODE(raw_mode)
    if perms & 0o6000:
        raise RescueInitramfsError("setuid/setgid bits are forbidden in rescue initramfs")
    if kind != "dir" and perms & stat.S_ISVTX:
        raise RescueInitramfsError("sticky bit is only allowed on rescue directories")
    if kind == "file" and perms & 0o002:
        raise RescueInitramfsError("world-writable regular files are forbidden in rescue initramfs")
    if kind == "dir":
        return stat.S_IFDIR | perms
    if kind == "file":
        return stat.S_IFREG | perms
    if kind == "symlink":
        return stat.S_IFLNK | 0o777
    raise RescueInitramfsError(f"unsupported rescue entry kind: {kind}")


def _scan_tree(source: Path) -> tuple[tuple[_Entry, ...], str, str]:
    source = source.resolve()
    if not source.is_dir():
        raise RescueInitramfsError("rescue source tree does not exist or is not a directory")

    entries: list[_Entry] = []
    total_file_bytes = 0
    init_sha256 = ""

    for dirpath, dirnames, filenames in os.walk(source, topdown=True, followlinks=False):
        current = Path(dirpath)
        real_dirs: list[str] = []
        symlink_dirs: list[str] = []
        for name in sorted(dirnames):
            child = current / name
            if child.is_symlink():
                symlink_dirs.append(name)
            else:
                real_dirs.append(name)
        dirnames[:] = real_dirs

        for name in real_dirs:
            child = current / name
            rel = child.relative_to(source).as_posix()
            _require_safe_archive_path(rel)
            st = child.stat(follow_symlinks=False)
            if not stat.S_ISDIR(st.st_mode):
                raise RescueInitramfsError(f"unexpected non-directory during rescue scan: {rel}")
            entries.append(_Entry(rel, "dir", _safe_mode("dir", st.st_mode), b""))

        for name in symlink_dirs:
            child = current / name
            rel = child.relative_to(source).as_posix()
            _require_safe_archive_path(rel)
            target = os.readlink(child)
            data = _normalize_symlink_target(rel, target)
            st = child.lstat()
            entries.append(_Entry(rel, "symlink", _safe_mode("symlink", st.st_mode), data))

        for name in sorted(filenames):
            child = current / name
            rel = child.relative_to(source).as_posix()
            _require_safe_archive_path(rel)
            st = child.lstat()
            if stat.S_ISLNK(st.st_mode):
                data = _normalize_symlink_target(rel, os.readlink(child))
                entries.append(_Entry(rel, "symlink", _safe_mode("symlink", st.st_mode), data))
                continue
            if not stat.S_ISREG(st.st_mode):
                raise RescueInitramfsError(f"special files are forbidden in rescue source tree: {rel}")
            data, stable = _read_stable_file(child)
            total_file_bytes += len(data)
            if total_file_bytes > _MAX_TOTAL_FILE_BYTES:
                raise RescueInitramfsError("rescue source tree exceeds total file-size limit")
            mode = _safe_mode("file", stable.st_mode)
            entries.append(_Entry(rel, "file", mode, data))
            if rel == "init":
                if not (mode & 0o111):
                    raise RescueInitramfsError("/init must be executable")
                init_sha256 = sha256(data).hexdigest()

        if len(entries) > _MAX_ENTRIES:
            raise RescueInitramfsError("rescue source tree contains too many entries")

    if not init_sha256:
        raise RescueInitramfsError("rescue source tree must contain an executable regular /init")

    entries.sort(key=lambda item: item.path)
    if len({item.path for item in entries}) != len(entries):
        raise RescueInitramfsError("duplicate rescue entry path")

    canonical = [
        {
            "path": item.path,
            "kind": item.kind,
            "mode": item.mode,
            "size": len(item.data),
            "sha256": sha256(item.data).hexdigest(),
        }
        for item in entries
    ]
    tree_json = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return tuple(entries), sha256(tree_json).hexdigest(), init_sha256


def _pad4(buffer: bytearray) -> None:
    while len(buffer) % 4:
        buffer.append(0)


def _append_newc_entry(
    buffer: bytearray,
    *,
    ino: int,
    name: str,
    mode: int,
    data: bytes,
    mtime: int,
) -> None:
    name_bytes = name.encode("utf-8") + b"\x00"
    fields = (
        ino,
        mode,
        0,
        0,
        1,
        mtime,
        len(data),
        0,
        0,
        0,
        0,
        len(name_bytes),
        0,
    )
    if any(value < 0 or value > 0xFFFFFFFF for value in fields):
        raise RescueInitramfsError("newc field exceeds 32-bit range")
    header = b"070701" + b"".join(f"{value:08x}".encode("ascii") for value in fields)
    if len(header) != 110:
        raise AssertionError("invalid newc header length")
    buffer.extend(header)
    buffer.extend(name_bytes)
    _pad4(buffer)
    buffer.extend(data)
    _pad4(buffer)


def _serialize_newc(entries: Iterable[_Entry], source_date_epoch: int) -> bytes:
    if not isinstance(source_date_epoch, int) or isinstance(source_date_epoch, bool):
        raise RescueInitramfsError("SOURCE_DATE_EPOCH must be an integer")
    if source_date_epoch < 0 or source_date_epoch > 0xFFFFFFFF:
        raise RescueInitramfsError("SOURCE_DATE_EPOCH is outside newc range")
    output = bytearray()
    for ino, entry in enumerate(entries, start=1):
        _append_newc_entry(
            output,
            ino=ino,
            name=entry.path,
            mode=entry.mode,
            data=entry.data,
            mtime=source_date_epoch,
        )
    _append_newc_entry(
        output,
        ino=0,
        name="TRAILER!!!",
        mode=0,
        data=b"",
        mtime=source_date_epoch,
    )
    while len(output) % 512:
        output.append(0)
    return bytes(output)


def build_reproducible_rescue_initramfs(
    source: Path,
    output: Path,
    evidence_path: Path,
    *,
    source_date_epoch: int = 0,
) -> RescueInitramfsEvidence:
    """Read the source tree twice, build independently, require byte equality, and publish atomically."""
    output = output.resolve()
    evidence_path = evidence_path.resolve()
    if output == evidence_path:
        raise RescueInitramfsError("artifact and evidence paths must be different")
    if output.exists() or evidence_path.exists():
        raise RescueInitramfsError("refusing to overwrite rescue artifact or evidence")
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)

    first_entries, first_tree_sha, first_init_sha = _scan_tree(source)
    first_bytes = _serialize_newc(first_entries, source_date_epoch)

    second_entries, second_tree_sha, second_init_sha = _scan_tree(source)
    second_bytes = _serialize_newc(second_entries, source_date_epoch)

    if first_tree_sha != second_tree_sha or first_init_sha != second_init_sha:
        raise RescueInitramfsError("rescue source tree changed between independent builds")
    if first_bytes != second_bytes:
        raise RescueInitramfsError("rescue initramfs builds are not byte-identical")

    evidence = RescueInitramfsEvidence(
        schema_version=1,
        archive_format="newc",
        compression="none",
        source_date_epoch=source_date_epoch,
        source_tree_sha256=first_tree_sha,
        artifact_sha256=sha256(first_bytes).hexdigest(),
        artifact_size=len(first_bytes),
        entry_count=len(first_entries),
        init_sha256=first_init_sha,
        reproducible=True,
    )

    with tempfile.TemporaryDirectory(prefix=".kps-rescue-", dir=output.parent) as temp_dir:
        temp = Path(temp_dir)
        artifact_tmp = temp / "rescue-initramfs.cpio"
        evidence_tmp = temp / "rescue-initramfs.json"
        artifact_tmp.write_bytes(first_bytes)
        evidence_tmp.write_text(evidence.canonical_json(), encoding="utf-8")
        os.replace(artifact_tmp, output)
        try:
            os.replace(evidence_tmp, evidence_path)
        except OSError:
            output.unlink(missing_ok=True)
            raise
    return evidence
