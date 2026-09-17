"""Bind one physical Fastboot capture to matching exact OTA/stock-boot provenance.

The bundle is the host-side ingress record required before a physical-firmware
first-boot candidate can be instantiated. It proves evidence consistency only;
it does not authorize Fastboot boot and never grants hardware/Beta credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re

from .fastboot_baseline import FastbootBaselineEvidence, FastbootBaselineError, require_baseline_matches_stock_provenance
from .fastboot_capture_bundle import FastbootCaptureBundleEvidence
from .profiles import DeviceProfile
from .provenance import StockBootProvenance

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PhysicalBaselineBundleError(ValueError):
    pass


@dataclass(frozen=True)
class PhysicalBaselineBundleEvidence:
    schema_version: int
    profile_id: str
    device_serial: str
    product: str
    firmware_build: str
    firmware_fingerprint: str
    fastboot_capture_bundle_sha256: str
    fastboot_baseline_evidence_sha256: str
    fastboot_transcript_sha256: str
    stock_provenance_sha256: str
    stock_ota_sha256: str
    stock_ota_size: int
    stock_payload_sha256: str
    stock_payload_metadata_sha256: str
    stock_payload_size: int
    stock_boot_sha256: str
    stock_boot_size: int
    stock_boot_header_version: int
    firmware_metadata_sha256: str
    baseline_matches_exact_stock_ota: bool
    ready_for_candidate_instantiation: bool
    temporary_boot_authorized: bool
    hardware_verified: bool = False
    beta_gate_credit: bool = False

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _metadata_sha(metadata: dict[str, str]) -> str:
    if not isinstance(metadata, dict) or not metadata:
        raise PhysicalBaselineBundleError("stock provenance firmware metadata is empty")
    normalized: dict[str, str] = {}
    for key, value in metadata.items():
        if not isinstance(key, str) or not key.strip() or not isinstance(value, str) or not value.strip():
            raise PhysicalBaselineBundleError("stock provenance firmware metadata is malformed")
        normalized[key] = value
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":")) + "\n"
    return sha256(payload.encode("utf-8")).hexdigest()


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise PhysicalBaselineBundleError(f"{label} must be a lowercase SHA-256")
    return value


def _size(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PhysicalBaselineBundleError(f"{label} must be a positive integer")
    return value


def bind_physical_baseline_to_stock(
    profile: DeviceProfile,
    baseline: FastbootBaselineEvidence,
    capture: FastbootCaptureBundleEvidence,
    provenance: StockBootProvenance,
) -> PhysicalBaselineBundleEvidence:
    if capture.schema_version != 1 or capture.profile_id != profile.profile_id:
        raise PhysicalBaselineBundleError("Fastboot capture bundle profile/schema mismatch")
    if capture.hardware_verified is not False or capture.beta_gate_credit is not False:
        raise PhysicalBaselineBundleError("Fastboot capture bundle cannot claim hardware/Beta credit")
    if capture.read_only is not True or capture.phone_storage_written is not False:
        raise PhysicalBaselineBundleError("Fastboot capture bundle is not read-only")
    if baseline.schema_version != 1 or baseline.profile_id != profile.profile_id:
        raise PhysicalBaselineBundleError("Fastboot baseline profile/schema mismatch")
    if capture.baseline_evidence_sha256 != baseline.evidence_sha256():
        raise PhysicalBaselineBundleError("Fastboot capture bundle is detached from baseline evidence")
    if capture.device_serial != baseline.serialno or capture.transcript_sha256 != baseline.transcript_sha256:
        raise PhysicalBaselineBundleError("Fastboot capture identity/transcript drifted")
    if capture.firmware_build != baseline.firmware_build or capture.firmware_fingerprint != baseline.firmware_fingerprint:
        raise PhysicalBaselineBundleError("Fastboot capture firmware identity drifted")

    if provenance.schema_version != 1 or provenance.profile_id != profile.profile_id:
        raise PhysicalBaselineBundleError("stock boot provenance profile/schema mismatch")
    try:
        require_baseline_matches_stock_provenance(profile, baseline, provenance)
    except FastbootBaselineError as exc:
        raise PhysicalBaselineBundleError(str(exc)) from exc

    for value, label in (
        (capture.evidence_sha256(), "Fastboot capture bundle SHA-256"),
        (baseline.evidence_sha256(), "Fastboot baseline evidence SHA-256"),
        (baseline.transcript_sha256, "Fastboot transcript SHA-256"),
        (provenance.evidence_sha256(), "stock provenance SHA-256"),
        (provenance.ota_sha256, "stock OTA SHA-256"),
        (provenance.payload_sha256, "payload SHA-256"),
        (provenance.payload_metadata_sha256, "payload metadata SHA-256"),
        (provenance.boot_sha256, "stock boot SHA-256"),
    ):
        _sha(value, label)
    for value, label in (
        (provenance.ota_size, "stock OTA size"),
        (provenance.payload_size, "payload size"),
        (provenance.boot_size, "stock boot size"),
        (provenance.boot_header_version, "stock boot header version"),
    ):
        _size(value, label)

    return PhysicalBaselineBundleEvidence(
        schema_version=1,
        profile_id=profile.profile_id,
        device_serial=baseline.serialno,
        product=baseline.product,
        firmware_build=baseline.firmware_build,
        firmware_fingerprint=baseline.firmware_fingerprint,
        fastboot_capture_bundle_sha256=capture.evidence_sha256(),
        fastboot_baseline_evidence_sha256=baseline.evidence_sha256(),
        fastboot_transcript_sha256=baseline.transcript_sha256,
        stock_provenance_sha256=provenance.evidence_sha256(),
        stock_ota_sha256=provenance.ota_sha256,
        stock_ota_size=provenance.ota_size,
        stock_payload_sha256=provenance.payload_sha256,
        stock_payload_metadata_sha256=provenance.payload_metadata_sha256,
        stock_payload_size=provenance.payload_size,
        stock_boot_sha256=provenance.boot_sha256,
        stock_boot_size=provenance.boot_size,
        stock_boot_header_version=provenance.boot_header_version,
        firmware_metadata_sha256=_metadata_sha(provenance.firmware_metadata),
        baseline_matches_exact_stock_ota=True,
        ready_for_candidate_instantiation=True,
        temporary_boot_authorized=False,
    )


def verify_physical_baseline_bundle(
    evidence: PhysicalBaselineBundleEvidence,
    profile: DeviceProfile,
    baseline: FastbootBaselineEvidence,
    capture: FastbootCaptureBundleEvidence,
    provenance: StockBootProvenance,
) -> None:
    expected = bind_physical_baseline_to_stock(profile, baseline, capture, provenance)
    if evidence != expected:
        raise PhysicalBaselineBundleError("physical baseline bundle does not match exact inputs")


def write_physical_baseline_bundle(evidence: PhysicalBaselineBundleEvidence, destination: Path) -> str:
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise PhysicalBaselineBundleError(f"refusing to overwrite physical baseline bundle: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = evidence.canonical_json()
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise PhysicalBaselineBundleError("refusing stale physical baseline bundle temporary path")
    try:
        temporary.write_text(payload, encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()
