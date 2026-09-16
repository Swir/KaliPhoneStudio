"""Fail-closed authorization contract for temporary boot candidates."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path

from .boot_builder import BootAssemblyEvidence, BootBuildPlan, BootRoundTripEvidence
from .boot_image import BootImageError, boot_build_contract
from .profiles import DeviceProfile
from .provenance import StockBootProvenance
from .safety import VerifiedDevice, require_verified_device, validate_image


@dataclass(frozen=True)
class TemporaryBootAuthorization:
    schema_version: int
    profile_id: str
    device_serial: str
    plan_sha256: str
    stock_boot_sha256: str
    stock_ota_sha256: str
    image_sha256: str
    image_size: int
    reproducible: bool
    structurally_verified: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def authorization_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def authorize_temporary_boot(
    plan: BootBuildPlan,
    profile: DeviceProfile,
    provenance: StockBootProvenance,
    assembly: BootAssemblyEvidence,
    round_trip: BootRoundTripEvidence,
    device: VerifiedDevice,
    *,
    image: Path,
) -> TemporaryBootAuthorization:
    """Bind the complete verified host-side chain to one verified physical device.

    This does not execute fastboot. It only creates the evidence required before a
    caller may offer a temporary boot operation.
    """
    require_verified_device(profile, device)
    contract = boot_build_contract(profile)
    plan_digest = plan.plan_sha256()
    if plan.profile_id != profile.profile_id or provenance.profile_id != profile.profile_id:
        raise BootImageError("temporary boot profile/provenance mismatch")
    if plan.stock_boot_sha256 != provenance.boot_sha256 or plan.stock_ota_sha256 != provenance.ota_sha256:
        raise BootImageError("temporary boot stock provenance mismatch")
    if plan.header_version != contract.header_version or plan.page_size != contract.page_size:
        raise BootImageError("temporary boot plan no longer matches profile boot contract")
    if assembly.profile_id != profile.profile_id or assembly.plan_sha256 != plan_digest or not assembly.reproducible:
        raise BootImageError("temporary boot requires reproducible assembly evidence")
    if round_trip.profile_id != profile.profile_id or round_trip.plan_sha256 != plan_digest:
        raise BootImageError("temporary boot round-trip evidence does not match plan/profile")
    if not round_trip.structurally_verified:
        raise BootImageError("temporary boot requires structural round-trip verification")
    if round_trip.image_sha256 != assembly.image_sha256:
        raise BootImageError("temporary boot evidence refers to different images")
    digest = validate_image(profile, "boot", image)
    size = image.stat().st_size
    if digest != assembly.image_sha256 or size != assembly.image_size:
        raise BootImageError("temporary boot image changed after verification")
    return TemporaryBootAuthorization(
        1, profile.profile_id, device.serial, plan_digest,
        provenance.boot_sha256, provenance.ota_sha256,
        digest, size, True, True,
    )


def write_temporary_boot_authorization(auth: TemporaryBootAuthorization, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = auth.canonical_json()
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8", newline="\n")
    temporary.replace(destination)
    return auth.authorization_sha256()
