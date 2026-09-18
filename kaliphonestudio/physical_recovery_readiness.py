"""Fail-closed offline recovery-readiness binding for a physical device baseline.

The record produced here is intentionally *not* a rollback result.  It binds the
captured A/B slot context and the exact locally available stock ``boot.img``
material to the same physical baseline and exact stock/candidate boot identity
chain that will be used for temporary bring-up.

No Fastboot/ADB command is executed, no slot is changed, no partition is selected
for writing, and no recovery/Beta/hardware claim is granted.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re

from .fastboot_baseline import FastbootBaselineEvidence
from .physical_baseline_bundle import PhysicalBaselineBundleEvidence
from .physical_boot_identity_binding import PhysicalBootIdentityBindingEvidence
from .profiles import DeviceProfile


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_STOCK_BOOT_BYTES = 512 * 1024 * 1024


class PhysicalRecoveryReadinessError(ValueError):
    pass


@dataclass(frozen=True)
class PhysicalRecoveryReadinessEvidence:
    schema_version: int
    profile_id: str
    device_serial: str
    firmware_build: str
    firmware_fingerprint: str
    fastboot_baseline_evidence_sha256: str
    physical_baseline_bundle_sha256: str
    physical_boot_identity_binding_sha256: str
    physical_candidate_gate_sha256: str
    boot_plan_sha256: str
    captured_active_slot: str | None
    expected_inactive_slot: str | None
    slot_count: int | None
    ab_device: bool
    ab_partitions_sha256: str
    stock_boot_sha256: str
    stock_boot_size: int
    stock_kernel_sha256: str
    stock_ramdisk_sha256: str
    stock_dtb_sha256: str | None
    stock_avb_footer_present: bool
    stock_avb_vbmeta_sha256: str | None
    candidate_boot_sha256: str
    candidate_boot_size: int
    recovery_notes_sha256: str
    confirmation_text_sha256: str
    stock_boot_material_present: bool
    exact_stock_identity_bound: bool
    slot_context_bound: bool
    ready_for_temporary_boot_safety_review: bool
    slot_switch_authorized: bool
    inactive_slot_write_authorized: bool
    persistent_write_authorized: bool
    rollback_exercised: bool
    recovery_verified: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise PhysicalRecoveryReadinessError(f"{label} must be a lowercase SHA-256")
    return value


def _positive(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PhysicalRecoveryReadinessError(f"{label} must be a positive integer")
    return value


def _canonical_list_sha(values: object, label: str, *, allow_empty: bool) -> str:
    if not isinstance(values, list) or (not allow_empty and not values):
        raise PhysicalRecoveryReadinessError(f"{label} must be a {'possibly empty ' if allow_empty else 'non-empty '}list")
    cleaned: list[str] = []
    for item in values:
        if not isinstance(item, str) or not item.strip():
            raise PhysicalRecoveryReadinessError(f"{label} contains an invalid entry")
        text = item.strip()
        if text in cleaned:
            raise PhysicalRecoveryReadinessError(f"{label} contains duplicate entries")
        cleaned.append(text)
    payload = json.dumps(cleaned, separators=(",", ":")) + "\n"
    return sha256(payload.encode("utf-8")).hexdigest()


def _text_sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PhysicalRecoveryReadinessError(f"{label} must be non-empty text")
    return sha256(value.strip().encode("utf-8")).hexdigest()


def _stable_file_identity(path: Path, label: str) -> tuple[str, int]:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise PhysicalRecoveryReadinessError(f"{label} must be a regular non-symlink file: {candidate}")
    before = candidate.stat()
    if before.st_size <= 0 or before.st_size > MAX_STOCK_BOOT_BYTES:
        raise PhysicalRecoveryReadinessError(f"{label} size is outside the bounded recovery-material limit")
    digest = sha256()
    with candidate.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    after = candidate.stat()
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or before.st_ino != after.st_ino
    ):
        raise PhysicalRecoveryReadinessError(f"{label} changed while being hashed")
    return digest.hexdigest(), after.st_size


def _slot_context(profile: DeviceProfile, baseline: FastbootBaselineEvidence) -> tuple[str | None, str | None, int | None, str]:
    ab_device = profile.data.get("ab_device")
    if not isinstance(ab_device, bool):
        raise PhysicalRecoveryReadinessError("profile ab_device contract must be boolean")
    partitions = profile.data.get("ab_partitions", [])
    partitions_sha = _canonical_list_sha(partitions, "profile ab_partitions", allow_empty=not ab_device)

    if not ab_device:
        if baseline.current_slot is not None or baseline.slot_count is not None:
            raise PhysicalRecoveryReadinessError("single-slot profile cannot carry A/B slot evidence")
        return None, None, None, partitions_sha

    if "boot" not in partitions:
        raise PhysicalRecoveryReadinessError("A/B recovery contract must declare boot in ab_partitions")
    if baseline.current_slot not in {"a", "b"}:
        raise PhysicalRecoveryReadinessError("A/B baseline must have captured active slot a or b")
    if baseline.slot_count != 2:
        raise PhysicalRecoveryReadinessError("A/B recovery readiness currently requires exactly two captured slots")
    inactive = "b" if baseline.current_slot == "a" else "a"
    return baseline.current_slot, inactive, baseline.slot_count, partitions_sha


def build_physical_recovery_readiness(
    profile: DeviceProfile,
    baseline: FastbootBaselineEvidence,
    physical: PhysicalBaselineBundleEvidence,
    binding: PhysicalBootIdentityBindingEvidence,
    *,
    stock_boot: Path,
) -> PhysicalRecoveryReadinessEvidence:
    """Bind exact stock recovery material and captured slot context without device I/O."""
    profile_id = getattr(profile, "profile_id", None)
    if not isinstance(profile_id, str) or not profile_id.strip():
        raise PhysicalRecoveryReadinessError("selected profile has an invalid profile_id")

    if not isinstance(baseline, FastbootBaselineEvidence) or baseline.schema_version != 1:
        raise PhysicalRecoveryReadinessError("Fastboot baseline must be schema-v1 typed evidence")
    if baseline.profile_id != profile_id:
        raise PhysicalRecoveryReadinessError("Fastboot baseline profile mismatch")
    if baseline.beta_gate_credit is not False:
        raise PhysicalRecoveryReadinessError("Fastboot baseline cannot claim Beta credit")
    if baseline.unlocked is not True:
        raise PhysicalRecoveryReadinessError("temporary-boot recovery readiness requires an unlocked captured baseline")

    if not isinstance(physical, PhysicalBaselineBundleEvidence) or physical.schema_version != 1:
        raise PhysicalRecoveryReadinessError("physical baseline bundle must be schema-v1 typed evidence")
    if physical.profile_id != profile_id or physical.device_serial != baseline.serialno:
        raise PhysicalRecoveryReadinessError("physical baseline bundle identity mismatch")
    if physical.fastboot_baseline_evidence_sha256 != baseline.evidence_sha256():
        raise PhysicalRecoveryReadinessError("physical baseline bundle is detached from Fastboot baseline evidence")
    if physical.fastboot_transcript_sha256 != baseline.transcript_sha256:
        raise PhysicalRecoveryReadinessError("physical baseline transcript identity drifted")
    if physical.firmware_build != baseline.firmware_build or physical.firmware_fingerprint != baseline.firmware_fingerprint:
        raise PhysicalRecoveryReadinessError("physical baseline firmware identity drifted")
    if physical.baseline_matches_exact_stock_ota is not True or physical.ready_for_candidate_instantiation is not True:
        raise PhysicalRecoveryReadinessError("physical baseline is not exact-stock/candidate ready")
    if physical.temporary_boot_authorized is not False or physical.hardware_verified is not False or physical.beta_gate_credit is not False:
        raise PhysicalRecoveryReadinessError("physical baseline contains an invalid authorization/hardware claim")

    if not isinstance(binding, PhysicalBootIdentityBindingEvidence) or binding.schema_version != 1:
        raise PhysicalRecoveryReadinessError("boot identity binding must be schema-v1 typed evidence")
    if binding.profile_id != profile_id or binding.device_serial != baseline.serialno:
        raise PhysicalRecoveryReadinessError("boot identity binding identity mismatch")
    if binding.physical_baseline_bundle_sha256 != physical.evidence_sha256():
        raise PhysicalRecoveryReadinessError("boot identity binding is detached from the physical baseline bundle")
    if binding.stock_boot_sha256 != physical.stock_boot_sha256 or binding.stock_boot_size != physical.stock_boot_size:
        raise PhysicalRecoveryReadinessError("stock boot identity drifted between physical baseline and boot binding")
    if (
        binding.stock_exact_bytes_verified is not True
        or binding.candidate_exact_bytes_verified is not True
        or binding.component_identity_bound is not True
        or binding.avb_layout_bound is not True
    ):
        raise PhysicalRecoveryReadinessError("boot identity binding is not exact-byte/component/AVB complete")
    if (
        binding.temporary_boot_executed is not False
        or binding.phone_storage_written is not False
        or binding.hardware_verified is not False
        or binding.beta_gate_credit is not False
    ):
        raise PhysicalRecoveryReadinessError("boot identity binding contains an invalid execution/write/hardware claim")

    stock_sha, stock_size = _stable_file_identity(stock_boot, "stock boot recovery material")
    if stock_sha != physical.stock_boot_sha256 or stock_size != physical.stock_boot_size:
        raise PhysicalRecoveryReadinessError("local stock boot recovery material differs from exact physical provenance")
    if stock_sha != binding.stock_boot_sha256 or stock_size != binding.stock_boot_size:
        raise PhysicalRecoveryReadinessError("local stock boot recovery material differs from exact boot identity binding")

    limits = profile.data.get("partition_limits")
    if not isinstance(limits, dict):
        raise PhysicalRecoveryReadinessError("profile has no partition_limits contract")
    boot_limit = _positive(limits.get("boot"), "profile boot partition limit")
    if stock_size > boot_limit:
        raise PhysicalRecoveryReadinessError("stock boot recovery material exceeds the profile boot partition limit")

    stock_kernel_sha = _sha(binding.stock_kernel_sha256, "stock kernel SHA-256")
    stock_ramdisk_sha = _sha(binding.stock_ramdisk_sha256, "stock ramdisk SHA-256")
    stock_dtb_sha = binding.stock_dtb_sha256
    if profile.data.get("boot", {}).get("include_dtb") is True:
        stock_dtb_sha = _sha(stock_dtb_sha, "stock DTB SHA-256")
    elif stock_dtb_sha is not None:
        stock_dtb_sha = _sha(stock_dtb_sha, "stock DTB SHA-256")

    stock_vbmeta_sha = binding.stock_avb_vbmeta_sha256
    if binding.stock_avb_footer_present:
        stock_vbmeta_sha = _sha(stock_vbmeta_sha, "stock AVB vbmeta SHA-256")
    elif stock_vbmeta_sha is not None:
        raise PhysicalRecoveryReadinessError("stock AVB vbmeta identity exists while footer is absent")

    candidate_boot_sha = _sha(binding.candidate_boot_sha256, "candidate boot SHA-256")
    candidate_boot_size = _positive(binding.candidate_boot_size, "candidate boot size")
    _sha(binding.physical_candidate_gate_sha256, "physical candidate gate SHA-256")
    _sha(binding.boot_plan_sha256, "boot plan SHA-256")

    active_slot, inactive_slot, slot_count, ab_partitions_sha = _slot_context(profile, baseline)
    recovery_notes_sha = _canonical_list_sha(profile.data.get("recovery_notes"), "profile recovery_notes", allow_empty=False)
    confirmation_sha = _text_sha(getattr(profile, "confirmation_text", None), "profile confirmation text")

    return PhysicalRecoveryReadinessEvidence(
        schema_version=1,
        profile_id=profile_id,
        device_serial=baseline.serialno,
        firmware_build=baseline.firmware_build,
        firmware_fingerprint=baseline.firmware_fingerprint,
        fastboot_baseline_evidence_sha256=baseline.evidence_sha256(),
        physical_baseline_bundle_sha256=physical.evidence_sha256(),
        physical_boot_identity_binding_sha256=binding.evidence_sha256(),
        physical_candidate_gate_sha256=binding.physical_candidate_gate_sha256,
        boot_plan_sha256=binding.boot_plan_sha256,
        captured_active_slot=active_slot,
        expected_inactive_slot=inactive_slot,
        slot_count=slot_count,
        ab_device=bool(profile.data.get("ab_device")),
        ab_partitions_sha256=ab_partitions_sha,
        stock_boot_sha256=stock_sha,
        stock_boot_size=stock_size,
        stock_kernel_sha256=stock_kernel_sha,
        stock_ramdisk_sha256=stock_ramdisk_sha,
        stock_dtb_sha256=stock_dtb_sha,
        stock_avb_footer_present=binding.stock_avb_footer_present,
        stock_avb_vbmeta_sha256=stock_vbmeta_sha,
        candidate_boot_sha256=candidate_boot_sha,
        candidate_boot_size=candidate_boot_size,
        recovery_notes_sha256=recovery_notes_sha,
        confirmation_text_sha256=confirmation_sha,
        stock_boot_material_present=True,
        exact_stock_identity_bound=True,
        slot_context_bound=True,
        ready_for_temporary_boot_safety_review=True,
        slot_switch_authorized=False,
        inactive_slot_write_authorized=False,
        persistent_write_authorized=False,
        rollback_exercised=False,
        recovery_verified=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def verify_physical_recovery_readiness(
    evidence: PhysicalRecoveryReadinessEvidence,
    profile: DeviceProfile,
    baseline: FastbootBaselineEvidence,
    physical: PhysicalBaselineBundleEvidence,
    binding: PhysicalBootIdentityBindingEvidence,
    *,
    stock_boot: Path,
) -> None:
    expected = build_physical_recovery_readiness(
        profile,
        baseline,
        physical,
        binding,
        stock_boot=stock_boot,
    )
    if evidence != expected:
        raise PhysicalRecoveryReadinessError("physical recovery readiness does not match exact inputs")


def write_physical_recovery_readiness(evidence: PhysicalRecoveryReadinessEvidence, destination: Path) -> str:
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise PhysicalRecoveryReadinessError(f"refusing to overwrite recovery readiness evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise PhysicalRecoveryReadinessError("refusing stale recovery readiness temporary path")
    try:
        temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()
