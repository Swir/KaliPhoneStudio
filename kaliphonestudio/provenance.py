"""Immutable provenance records for stock boot images extracted from exact OTAs.

Host-side only. A provenance record binds profile identity, complete OTA bytes,
payload evidence, firmware metadata and extracted boot.img bytes. It does not
claim that the image has booted on physical hardware.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
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

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def to_json(self) -> str:
        """Human-readable representation retained for existing evidence files."""
        return json.dumps(asdict(self), indent=2, sort_keys=True) + "\n"


def _require_sha(name: str, value: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ProvenanceError(f"{name} must be a lowercase SHA-256")


def _require_positive_int(name: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ProvenanceError(f"{name} must be a positive integer")


def build_stock_boot_provenance(
    profile_id: str,
    ota: OTAPackageReport,
    payload: PayloadHeaderReport,
    boot: BootImageReport,
) -> StockBootProvenance:
    """Bind an extracted stock boot image to exact OTA/payload evidence.

    The OTA report carries the SHA-256 of its exact embedded payload.bin. The
    external payload inspected by ``inspect_payload`` must match that digest,
    not merely the uncompressed size. This prevents a same-size payload from a
    different OTA from being bound into stock provenance.
    """
    if not profile_id or "/" not in profile_id:
        raise ProvenanceError("profile_id must be an explicit vendor/codename identifier")
    _require_sha("OTA hash", ota.sha256)
    _require_sha("OTA embedded payload hash", ota.payload_sha256)
    _require_sha("payload hash", payload.payload_sha256)
    _require_sha("payload metadata hash", payload.metadata_sha256)
    _require_sha("boot hash", boot.sha256)
    _require_positive_int("OTA size", ota.size)
    _require_positive_int("payload size", payload.file_size)
    _require_positive_int("boot size", boot.size)
    if ota.payload_size != payload.file_size:
        raise ProvenanceError("payload size does not match exact OTA member")
    if ota.payload_sha256 != payload.payload_sha256:
        raise ProvenanceError("payload SHA-256 does not match exact OTA payload.bin")
    if not isinstance(boot.header_version, int) or isinstance(boot.header_version, bool) or boot.header_version < 0:
        raise ProvenanceError("boot image has no validated header version")
    metadata: dict[str, str] = {}
    for key, value in sorted(ota.metadata.items()):
        if not isinstance(key, str) or not key.strip() or not isinstance(value, str) or not value.strip():
            raise ProvenanceError("exact OTA firmware metadata contains invalid entries")
        metadata[key] = value
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
    """Create evidence once; refuse symlinks or different existing provenance."""
    path = Path(path)
    content = record.to_json()
    if path.is_symlink():
        raise ProvenanceError("refusing symlink provenance path")
    if path.exists():
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            raise ProvenanceError("provenance record already exists with different evidence")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
