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

from .lz4_legacy import Lz4LegacyError, compress_legacy, decompress_legacy


_MAX_ENTRIES = 4096
_MAX_FILE_BYTES = 64 * 1024 * 1024
_MAX_TOTAL_PAYLOAD_BYTES = 128 * 1024 * 1024
_MAX_CPIO_BYTES = 192 * 1024 * 1024
_MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
_COMPRESSION_CONTRACTS = {
    "gzip": "gzip-mtime0-level9",
    "lz4": "lz4-legacy-literal-v1",
}


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
class InitramfsInspection:
    compression: str
    uncompressed_size: int
    entry_manifest_sha256: str
    entry_count: int
    init_sha256: str


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


def _safe_archive_path(relative: Path | PurePosixPath) -> str:
    value = relative.as_posix()
    pure = PurePosixPath(value)
    if not value or value == "." or pure.is_absolute() or ".." in pure.parts or "\x00" in value:
        raise InitramfsError(f"unsafe initramfs path: {value!r}")
    return value


def _validate_entry_permissions(path: str, kind: str, permissions: int) -> None:
    if permissions & (stat.S_ISUID | stat.S_ISGID):
        raise InitramfsError(f"setuid/setgid bits are forbidden in rescue initramfs: {path}")
    if kind == "file" and permissions & 0o002:
        raise InitramfsError(f"world-writable regular files are forbidden in rescue initramfs: {path}")


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
        _validate_entry_permissions(entry.path, entry.kind, entry.mode)
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


def _build_cpio(entries: tuple[_Entry, ...]) -> bytes:
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
    payload = cpio.getvalue()
    if len(payload) > _MAX_CPIO_BYTES:
        raise InitramfsError("cpio payload exceeds the initramfs safety limit")
    return payload


def _build_archive(entries: tuple[_Entry, ...], compression: str) -> bytes:
    raw = _build_cpio(entries)
    if compression == "gzip":
        compressed = io.BytesIO()
        with gzip.GzipFile(filename="", mode="wb", fileobj=compressed, compresslevel=9, mtime=0) as handle:
            handle.write(raw)
        result = compressed.getvalue()
    elif compression == "lz4":
        try:
            result = compress_legacy(raw)
        except Lz4LegacyError as exc:
            raise InitramfsError(f"cannot encode LZ4 legacy initramfs: {exc}") from exc
    else:
        raise InitramfsError(f"unsupported initramfs compression policy: {compression}")
    if len(result) > _MAX_ARCHIVE_BYTES:
        raise InitramfsError("compressed initramfs exceeds the artifact safety limit")
    return result


def _decompress_archive(compression: str, payload: bytes) -> bytes:
    if len(payload) > _MAX_ARCHIVE_BYTES:
        raise InitramfsError("compressed initramfs exceeds the artifact safety limit")
    if compression == "gzip-mtime0-level9":
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(payload), mode="rb") as handle:
                raw = handle.read(_MAX_CPIO_BYTES + 1)
        except (OSError, EOFError) as exc:
            raise InitramfsError(f"invalid gzip initramfs artifact: {exc}") from exc
    elif compression == "lz4-legacy-literal-v1":
        try:
            raw, _ = decompress_legacy(payload, max_output_bytes=_MAX_CPIO_BYTES + 1)
        except Lz4LegacyError as exc:
            raise InitramfsError(f"invalid LZ4 legacy initramfs artifact: {exc}") from exc
    else:
        raise InitramfsError("unsupported initramfs artifact contract")
    if len(raw) > _MAX_CPIO_BYTES:
        raise InitramfsError("decompressed cpio exceeds the initramfs safety limit")
    return raw


def _parse_newc(payload: bytes) -> tuple[_Entry, ...]:
    cursor = 0
    entries: list[_Entry] = []
    expected_inode = 1
    previous_path = ""
    while True:
        if cursor + 110 > len(payload):
            raise InitramfsError("truncated cpio newc header")
        header = payload[cursor : cursor + 110]
        if header[:6] != b"070701":
            raise InitramfsError("unsupported or corrupt cpio header magic")
        try:
            fields = [int(header[6 + index * 8 : 14 + index * 8], 16) for index in range(13)]
        except ValueError as exc:
            raise InitramfsError("invalid hexadecimal cpio header field") from exc
        (
            inode,
            mode,
            uid,
            gid,
            nlink,
            mtime,
            filesize,
            devmajor,
            devminor,
            rdevmajor,
            rdevminor,
            namesize,
            check,
        ) = fields
        if inode != expected_inode:
            raise InitramfsError("cpio inode sequence is not canonical")
        if uid != 0 or gid != 0 or nlink != 1 or mtime != 0:
            raise InitramfsError("cpio metadata is not normalized")
        if any(value != 0 for value in (devmajor, devminor, rdevmajor, rdevminor, check)):
            raise InitramfsError("cpio device/check metadata is not canonical")
        if namesize <= 0 or namesize > 4096:
            raise InitramfsError("invalid cpio entry name size")

        name_start = cursor + 110
        name_end = name_start + namesize
        if name_end > len(payload) or payload[name_end - 1] != 0:
            raise InitramfsError("truncated or unterminated cpio entry name")
        try:
            name = payload[name_start : name_end - 1].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise InitramfsError("cpio entry name is not valid UTF-8") from exc
        data_start = (name_end + 3) & ~3
        data_end = data_start + filesize
        if data_end > len(payload):
            raise InitramfsError("truncated cpio entry payload")
        data = payload[data_start:data_end]
        cursor = (data_end + 3) & ~3

        if name == "TRAILER!!!":
            if filesize != 0 or mode != 0 or expected_inode != len(entries) + 1:
                raise InitramfsError("invalid cpio trailer")
            if any(payload[cursor:]):
                raise InitramfsError("non-zero bytes follow the cpio trailer")
            break

        archive_path = _safe_archive_path(PurePosixPath(name))
        if archive_path <= previous_path:
            raise InitramfsError("cpio entries are not in canonical lexical order")
        previous_path = archive_path
        kind_bits = stat.S_IFMT(mode)
        kind = {
            stat.S_IFREG: "file",
            stat.S_IFDIR: "directory",
            stat.S_IFLNK: "symlink",
        }.get(kind_bits)
        if kind is None:
            raise InitramfsError(f"special file type found in cpio: {archive_path}")
        permissions = stat.S_IMODE(mode)
        _validate_entry_permissions(archive_path, kind, permissions)
        if kind == "directory" and data:
            raise InitramfsError(f"directory carries unexpected payload: {archive_path}")
        entries.append(_Entry(archive_path, kind, permissions, data))
        if len(entries) > _MAX_ENTRIES:
            raise InitramfsError("cpio entry count exceeds the safety limit")
        expected_inode += 1

    return tuple(entries)


def _inspect_payload(evidence: InitramfsEvidence, payload: bytes) -> InitramfsInspection:
    if evidence.schema_version != 1 or not evidence.reproducible:
        raise InitramfsError("initramfs artifact lacks reproducibility evidence")
    if evidence.archive_format != "cpio-newc" or evidence.compression not in set(_COMPRESSION_CONTRACTS.values()):
        raise InitramfsError("unsupported initramfs artifact contract")
    if evidence.entry_count <= 0 or evidence.artifact_size <= 0:
        raise InitramfsError("invalid initramfs evidence size/count")
    if evidence.artifact_size > _MAX_ARCHIVE_BYTES:
        raise InitramfsError("initramfs evidence exceeds the artifact safety limit")
    if len(payload) != evidence.artifact_size or sha256(payload).hexdigest() != evidence.artifact_sha256:
        raise InitramfsError("initramfs artifact changed after reproducibility verification")

    raw = _decompress_archive(evidence.compression, payload)
    entries = _parse_newc(raw)
    manifest_sha = sha256(_manifest_payload(entries)).hexdigest()
    init = next((entry for entry in entries if entry.path == "init"), None)
    if init is None or init.kind != "file" or not init.payload or init.mode & 0o111 == 0:
        raise InitramfsError("verified cpio does not contain an executable regular /init")
    init_sha = sha256(init.payload).hexdigest()
    if len(entries) != evidence.entry_count:
        raise InitramfsError("initramfs entry count does not match evidence")
    if manifest_sha != evidence.entry_manifest_sha256:
        raise InitramfsError("initramfs entry manifest does not match evidence")
    if init_sha != evidence.init_sha256:
        raise InitramfsError("initramfs /init does not match evidence")
    return InitramfsInspection(
        compression=evidence.compression,
        uncompressed_size=len(raw),
        entry_manifest_sha256=manifest_sha,
        entry_count=len(entries),
        init_sha256=init_sha,
    )


def build_reproducible_initramfs(
    staging: Path,
    destination: Path,
    *,
    compression: str = "gzip",
) -> InitramfsEvidence:
    """Build twice and publish only a structurally verified byte-identical archive."""
    if compression not in _COMPRESSION_CONTRACTS:
        raise InitramfsError(f"unsupported initramfs compression policy: {compression}")
    first_entries = _snapshot_staging(staging)
    first_manifest = _manifest_payload(first_entries)
    first_archive = _build_archive(first_entries, compression)

    second_entries = _snapshot_staging(staging)
    second_manifest = _manifest_payload(second_entries)
    second_archive = _build_archive(second_entries, compression)
    if first_manifest != second_manifest or first_archive != second_archive:
        raise InitramfsError("rescue initramfs staging/build changed between reproducibility passes")

    init = next(entry for entry in first_entries if entry.path == "init")
    evidence = InitramfsEvidence(
        schema_version=1,
        archive_format="cpio-newc",
        compression=_COMPRESSION_CONTRACTS[compression],
        artifact_sha256=sha256(first_archive).hexdigest(),
        artifact_size=len(first_archive),
        entry_manifest_sha256=sha256(first_manifest).hexdigest(),
        entry_count=len(first_entries),
        init_sha256=sha256(init.payload).hexdigest(),
        reproducible=True,
    )
    _inspect_payload(evidence, first_archive)
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


def inspect_initramfs_artifact(evidence: InitramfsEvidence, artifact: Path) -> InitramfsInspection:
    if not artifact.is_file():
        raise InitramfsError("initramfs artifact is missing")
    try:
        artifact_size = artifact.stat().st_size
    except OSError as exc:
        raise InitramfsError(f"cannot stat initramfs artifact: {exc}") from exc
    if artifact_size > _MAX_ARCHIVE_BYTES:
        raise InitramfsError("compressed initramfs exceeds the artifact safety limit")
    return _inspect_payload(evidence, artifact.read_bytes())


def verify_initramfs_artifact(evidence: InitramfsEvidence, artifact: Path) -> None:
    inspect_initramfs_artifact(evidence, artifact)


def write_initramfs_evidence(evidence: InitramfsEvidence, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = evidence.canonical_json()
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8", newline="\n")
    temporary.replace(destination)
    return evidence.evidence_sha256()
