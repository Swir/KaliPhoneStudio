"""Device-independent deterministic rescue initramfs construction and evidence."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import gzip
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat


_MAX_ENTRIES = 4096
_MAX_FILE_BYTES = 64 * 1024 * 1024
_MAX_TOTAL_PAYLOAD_BYTES = 128 * 1024 * 1024


class InitramfsError(ValueError):
    """Raised when rescue initramfs inputs or evidence are unsafe/inconsistent."""


@dataclass(frozen=True)
class InitramfsEntryEvidence:
    path: str
    kind: str
    mode: int
    size: int
    sha256: str


@dataclass(frozen=True)
class InitramfsEvidence:
    schema_version: int
    archive_format: str
    compression: str
    artifact_sha256: str
    artifact_size: int
    entry_manifest_sha256: str
    entry_count: int
    init_sha256: str
    reproducible: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class _Entry:
    path: str
    kind: str
    mode: int
    payload: bytes

    def evidence(self) -> InitramfsEntryEvidence:
        return InitramfsEntryEvidence(
            path=self.path,
            kind=self.kind,
            mode=self.mode,
            size=len(self.payload),
            sha256=sha256(self.payload).hexdigest(),
        )


def _safe_archive_path(relative: Path) -> str:
    value = relative.as_posix()
    pure = PurePosixPath(value)
    if not value or value == "." or pure.is_absolute() or ".." in pure.parts or "\x00" in value:
        raise InitramfsError(f"unsafe initramfs path: {value!r}")
    return value


def _snapshot_staging(staging: Path) -> tuple[_Entry, ...]:
    try:
        root = staging.resolve(strict=True)
    except OSError as exc:
        raise InitramfsError(f"cannot resolve initramfs staging directory: {exc}") from exc
    if not root.is_dir() or staging.is_symlink():
        raise InitramfsError("initramfs staging path must be a real directory")

    paths = sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix())
    if not paths or len(paths) > _MAX_ENTRIES:
        raise InitramfsError("initramfs staging tree is empty or exceeds the entry safety limit")

    entries: list[_Entry] = []
    total_payload = 0
    for item in paths:
        relative = item.relative_to(root)
        archive_path = _safe_archive_path(relative)
        try:
            metadata = item.lstat()
        except OSError as exc:
            raise InitramfsError(f"cannot stat initramfs entry {archive_path}: {exc}") from exc
        permissions = stat.S_IMODE(metadata.st_mode)
        if permissions & (stat.S_ISUID | stat.S_ISGID):
            raise InitramfsError(f"setuid/setgid bits are forbidden in rescue initramfs: {archive_path}")

        if stat.S_ISDIR(metadata.st_mode):
            entry = _Entry(archive_path, "directory", permissions, b"")
        elif stat.S_ISREG(metadata.st_mode):
            if metadata.st_size < 0 or metadata.st_size > _MAX_FILE_BYTES:
                raise InitramfsError(f"initramfs file exceeds per-file safety limit: {archive_path}")
            try:
                payload = item.read_bytes()
            except OSError as exc:
                raise InitramfsError(f"cannot read initramfs file {archive_path}: {exc}") from exc
            if len(payload) != metadata.st_size:
                raise InitramfsError(f"initramfs file changed while being read: {archive_path}")
            entry = _Entry(archive_path, "file", permissions, payload)
        elif stat.S_ISLNK(metadata.st_mode):
            try:
                target = os.readlink(item)
            except OSError as exc:
                raise InitramfsError(f"cannot read initramfs symlink {archive_path}: {exc}") from exc
            if not target or "\x00" in target:
                raise InitramfsError(f"invalid initramfs symlink target: {archive_path}")
            entry = _Entry(archive_path, "symlink", permissions, target.encode("utf-8"))
        else:
            raise InitramfsError(
                f"special files are forbidden in reproducible rescue initramfs staging: {archive_path}"
            )
        total_payload += len(entry.payload)
        if total_payload > _MAX_TOTAL_PAYLOAD_BYTES:
            raise InitramfsError("initramfs staging tree exceeds total payload safety limit")
        entries.append(entry)

    init = next((entry for entry in entries if entry.path == "init"), None)
    if init is None or init.kind != "file" or not init.payload:
        raise InitramfsError("rescue initramfs requires a non-empty regular /init")
    if init.mode & 0o111 == 0:
        raise InitramfsError("rescue initramfs /init must be executable")
    return tuple(entries)


def _newc_mode(entry: _Entry) -> int:
    kind_bits = {
        "file": stat.S_IFREG,
        "directory": stat.S_IFDIR,
        "symlink": stat.S_IFLNK,
    }[entry.kind]
    return kind_bits | entry.mode


def _pad4(buffer: io.BytesIO) -> None:
    padding = (-buffer.tell()) % 4
    if padding:
        buffer.write(b"\x00" * padding)


def _write_newc_entry(buffer: io.BytesIO, *, inode: int, name: str, mode: int, payload: bytes) -> None:
    name_bytes = name.encode("utf-8") + b"\x00"
    fields = (
        inode,
        mode,
        0,  # uid is normalized for reproducibility and early-userspace safety
        0,  # gid is normalized for reproducibility and early-userspace safety
        1,  # nlink; hard-link reconstruction is intentionally not supported
        0,  # mtime is normalized to SOURCE_DATE_EPOCH=0 semantics
        len(payload),
        0,
        0,
        0,
        0,
        len(name_bytes),
        0,
    )
    if any(value < 0 or value > 0xFFFFFFFF for value in fields):
        raise InitramfsError(f"cpio newc field overflow for {name}")
    header = b"070701" + b"".join(f"{value:08x}".encode("ascii") for value in fields)
    if len(header) != 110:
        raise AssertionError("invalid internal newc header length")
    buffer.write(header)
    buffer.write(name_bytes)
    _pad4(buffer)
    buffer.write(payload)
    _pad4(buffer)


def _manifest_payload(entries: tuple[_Entry, ...]) -> bytes:
    items = [asdict(entry.evidence()) for entry in entries]
    return (json.dumps(items, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _build_archive(entries: tuple[_Entry, ...]) -> bytes:
    cpio = io.BytesIO()
    for inode, entry in enumerate(entries, start=1):
        _write_newc_entry(
            cpio,
            inode=inode,
            name=entry.path,
            mode=_newc_mode(entry),
            payload=entry.payload,
        )
    _write_newc_entry(cpio, inode=len(entries) + 1, name="TRAILER!!!", mode=0, payload=b"")

    compressed = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=compressed, compresslevel=9, mtime=0) as handle:
        handle.write(cpio.getvalue())
    return compressed.getvalue()


def build_reproducible_initramfs(staging: Path, destination: Path) -> InitramfsEvidence:
    """Build twice from staging and publish only a byte-identical gzip/newc archive."""
    first_entries = _snapshot_staging(staging)
    first_manifest = _manifest_payload(first_entries)
    first_archive = _build_archive(first_entries)

    second_entries = _snapshot_staging(staging)
    second_manifest = _manifest_payload(second_entries)
    second_archive = _build_archive(second_entries)
    if first_manifest != second_manifest or first_archive != second_archive:
        raise InitramfsError("rescue initramfs staging/build changed between reproducibility passes")

    init = next(entry for entry in first_entries if entry.path == "init")
    evidence = InitramfsEvidence(
        schema_version=1,
        archive_format="cpio-newc",
        compression="gzip-mtime0-level9",
        artifact_sha256=sha256(first_archive).hexdigest(),
        artifact_size=len(first_archive),
        entry_manifest_sha256=sha256(first_manifest).hexdigest(),
        entry_count=len(first_entries),
        init_sha256=sha256(init.payload).hexdigest(),
        reproducible=True,
    )
    if destination.exists():
        raise InitramfsError("refusing to overwrite an existing initramfs artifact")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    try:
        temporary.write_bytes(first_archive)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return evidence


def verify_initramfs_artifact(evidence: InitramfsEvidence, artifact: Path) -> None:
    if evidence.schema_version != 1 or not evidence.reproducible:
        raise InitramfsError("initramfs artifact lacks reproducibility evidence")
    if evidence.archive_format != "cpio-newc" or evidence.compression != "gzip-mtime0-level9":
        raise InitramfsError("unsupported initramfs artifact contract")
    if evidence.entry_count <= 0 or evidence.artifact_size <= 0:
        raise InitramfsError("invalid initramfs evidence size/count")
    if not artifact.is_file():
        raise InitramfsError("initramfs artifact is missing")
    payload = artifact.read_bytes()
    if len(payload) != evidence.artifact_size or sha256(payload).hexdigest() != evidence.artifact_sha256:
        raise InitramfsError("initramfs artifact changed after reproducibility verification")


def write_initramfs_evidence(evidence: InitramfsEvidence, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = evidence.canonical_json()
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8", newline="\n")
    temporary.replace(destination)
    return evidence.evidence_sha256()
