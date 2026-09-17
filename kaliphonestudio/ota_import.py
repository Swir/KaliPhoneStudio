"""Safe, device-independent OTA package inspection.

This module never flashes a device. It inventories a local Android OTA ZIP,
locates payload.bin and captures immutable evidence needed before a profile-
specific extractor is allowed to produce stock partition images.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

MAX_METADATA_BYTES = 1024 * 1024
MAX_METADATA_ENTRIES = 512
MAX_METADATA_KEY_LENGTH = 256
MAX_METADATA_VALUE_LENGTH = 8192


class OTAImportError(ValueError):
    pass


@dataclass(frozen=True)
class OTAPackageReport:
    path: Path
    size: int
    sha256: str
    payload_member: str
    payload_size: int
    metadata_member: str | None
    metadata: dict[str, str]


def _digest(path: Path) -> str:
    h = sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def _safe_member(name: str) -> bool:
    if not isinstance(name, str) or not name or "\\" in name:
        return False
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in name):
        return False
    p = PurePosixPath(name)
    return not p.is_absolute() and ".." not in p.parts and all(part not in {"", "."} for part in p.parts)


def _parse_metadata(raw: bytes) -> dict[str, str]:
    if not raw or len(raw) > MAX_METADATA_BYTES:
        raise OTAImportError("OTA metadata is empty or exceeds the safety size limit")
    if b"\x00" in raw:
        raise OTAImportError("OTA metadata contains NUL bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OTAImportError("OTA metadata must be valid UTF-8") from exc
    for ch in text:
        if ord(ch) < 0x20 and ch not in "\r\n\t":
            raise OTAImportError("OTA metadata contains unsafe control characters")

    out: dict[str, str] = {}
    for original in text.splitlines():
        line = original.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise OTAImportError("OTA metadata contains a malformed non-comment line")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or len(key) > MAX_METADATA_KEY_LENGTH:
            raise OTAImportError("OTA metadata key is empty or exceeds the safety limit")
        if len(value) > MAX_METADATA_VALUE_LENGTH:
            raise OTAImportError(f"OTA metadata value exceeds the safety limit for {key!r}")
        if any(ord(ch) < 0x21 or ord(ch) > 0x7E for ch in key):
            raise OTAImportError(f"OTA metadata key contains unsafe characters: {key!r}")
        if key in out:
            raise OTAImportError(f"OTA metadata contains duplicate key: {key}")
        out[key] = value
        if len(out) > MAX_METADATA_ENTRIES:
            raise OTAImportError("OTA metadata contains too many entries")
    if not out:
        raise OTAImportError("OTA metadata contains no usable entries")
    return out


def inspect_ota_zip(path: Path) -> OTAPackageReport:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise OTAImportError(f"OTA package must be a regular non-symlink file: {path}")
    before = path.stat()
    if before.st_size <= 0:
        raise OTAImportError("OTA package is empty")
    try:
        with ZipFile(path) as zf:
            infos = zf.infolist()
            unsafe = [i.filename for i in infos if not _safe_member(i.filename)]
            if unsafe:
                raise OTAImportError("OTA ZIP contains unsafe member paths")
            payloads = [i for i in infos if PurePosixPath(i.filename).name == "payload.bin" and not i.is_dir()]
            if len(payloads) != 1:
                raise OTAImportError(f"OTA ZIP must contain exactly one payload.bin; got {len(payloads)}")
            payload = payloads[0]
            if payload.file_size <= 0:
                raise OTAImportError("payload.bin is empty")

            metadata_names = {"META-INF/com/android/metadata", "metadata"}
            metadata_infos = [i for i in infos if i.filename in metadata_names and not i.is_dir()]
            if len(metadata_infos) > 1:
                raise OTAImportError("OTA ZIP contains ambiguous or duplicate firmware metadata members")
            if metadata_infos:
                metadata_info = metadata_infos[0]
                if metadata_info.file_size <= 0 or metadata_info.file_size > MAX_METADATA_BYTES:
                    raise OTAImportError("OTA metadata size is outside the safety bound")
                metadata_member = metadata_info.filename
                metadata = _parse_metadata(zf.read(metadata_info))
            else:
                metadata_member = None
                metadata = {}
    except BadZipFile as exc:
        raise OTAImportError("file is not a valid ZIP archive") from exc

    digest = _digest(path)
    after = path.stat()
    if after.st_size != before.st_size or after.st_mtime_ns != before.st_mtime_ns:
        raise OTAImportError("OTA package changed while being inspected")
    return OTAPackageReport(
        path=path,
        size=after.st_size,
        sha256=digest,
        payload_member=payload.filename,
        payload_size=payload.file_size,
        metadata_member=metadata_member,
        metadata=metadata,
    )


def require_firmware_hint(report: OTAPackageReport, expected_fragments: list[str]) -> None:
    """Fail closed when profile-provided firmware hints cannot be found.

    Hints are deliberately profile data, not hard-coded device names. Matching
    is case-insensitive against OTA metadata values. Empty hints are rejected.
    """
    hints = [x.strip().lower() for x in expected_fragments if x and x.strip()]
    if not hints:
        raise OTAImportError("profile provides no firmware identity hints")
    haystack = "\n".join(report.metadata.values()).lower()
    if not haystack:
        raise OTAImportError("OTA has no readable firmware metadata; manual verification required")
    if not all(h in haystack for h in hints):
        raise OTAImportError("OTA metadata does not satisfy profile firmware hints")
