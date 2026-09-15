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
    p = PurePosixPath(name)
    return not p.is_absolute() and ".." not in p.parts


def _parse_metadata(raw: bytes) -> dict[str, str]:
    text = raw.decode("utf-8", errors="replace")
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def inspect_ota_zip(path: Path) -> OTAPackageReport:
    if not path.is_file():
        raise OTAImportError(f"OTA package does not exist: {path}")
    if path.stat().st_size <= 0:
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
            metadata_candidates = [
                "META-INF/com/android/metadata",
                "metadata",
            ]
            metadata_member = next((n for n in metadata_candidates if n in zf.namelist()), None)
            metadata = _parse_metadata(zf.read(metadata_member)) if metadata_member else {}
    except BadZipFile as exc:
        raise OTAImportError("file is not a valid ZIP archive") from exc
    return OTAPackageReport(
        path=path,
        size=path.stat().st_size,
        sha256=_digest(path),
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
