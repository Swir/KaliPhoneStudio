"""Immutable provenance records for stock boot images extracted from exact OTAs.

Host-side only. A provenance record binds profile identity, complete OTA bytes,
payload evidence, firmware metadata and extracted boot.img bytes. It does not
claim that the image has booted on physical hardware.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re

from .boot_image import BootImageReport
from .ota_import import OTAPackageReport
from .payload import PayloadHeaderReport

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ProvenanceError(ValueError):
    pass


@dataclass(frozen=True)
class StockBootProvenance:
    schema_version: int
    profile_id: str
    ota_sha256: str
    ota_size: int
    payload_sha256: str
    payload_metadata_sha256: str
    payload_size: int
    boot_sha256: str
    boot_size: int
    boot_header_version: int
    firmware_metadata: dict[str, str]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True) + "\n"


def _require_sha(name: str, value: str) -> None:
    if not _SHA256_RE.fullmatch(value):
        raise ProvenanceError(f"{name} must be a lowercase SHA-256")


def build_stock_boot_provenance(
    profile_id: str,
    ota: OTAPackageReport,
    payload: PayloadHeaderReport,
    boot: BootImageReport,
) -> StockBootProvenance:
    """Bind an extracted stock boot image to exact OTA/payload evidence."""
    if not profile_id or "/" not in profile_id:
        raise ProvenanceError("profile_id must be an explicit vendor/codename identifier")
    _require_sha("OTA hash", ota.sha256)
    _require_sha("payload hash", payload.payload_sha256)
    _require_sha("payload metadata hash", payload.metadata_sha256)
    _require_sha("boot hash", boot.sha256)
    if ota.payload_size != payload.file_size:
        raise ProvenanceError("OTA payload size does not match inspected payload bytes")
    if boot.header_version is None:
        raise ProvenanceError("boot image has no validated header version")
    metadata = {str(k): str(v) for k, v in sorted(ota.metadata.items()) if str(k).strip()}
    if not metadata:
        raise ProvenanceError("exact OTA firmware metadata is required for stock provenance")
    return StockBootProvenance(
        schema_version=1,
        profile_id=profile_id,
        ota_sha256=ota.sha256,
        ota_size=ota.size,
        payload_sha256=payload.payload_sha256,
        payload_metadata_sha256=payload.metadata_sha256,
        payload_size=payload.file_size,
        boot_sha256=boot.sha256,
        boot_size=boot.size,
        boot_header_version=boot.header_version,
        firmware_metadata=metadata,
    )


def write_immutable_provenance(record: StockBootProvenance, path: Path) -> None:
    """Create evidence once; refuse to overwrite different provenance."""
    content = record.to_json()
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise ProvenanceError("provenance record already exists with different evidence")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
