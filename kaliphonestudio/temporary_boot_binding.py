"""Validate the exact boot-identity record before a temporary-boot offer exists.

This module is intentionally host-only.  It does not re-run Fastboot or mutate phone
state; it verifies that the already immutable exact-byte binding produced immediately
before physical testing is the same profile/device/candidate chain that the offer is
about to expose.
"""
from __future__ import annotations

from hashlib import sha256
import re

from .physical_boot_identity_binding import PhysicalBootIdentityBindingEvidence
from .physical_candidate_gate import PhysicalCandidateGateEvidence
from .profiles import DeviceProfile

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class TemporaryBootBindingError(ValueError):
    pass


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise TemporaryBootBindingError(f"{label} must be a lowercase SHA-256")
    return value


def require_temporary_boot_identity_binding(
    profile: DeviceProfile,
    gate: PhysicalCandidateGateEvidence,
    binding: PhysicalBootIdentityBindingEvidence,
) -> str:
    """Return the canonical binding digest only when the exact candidate chain agrees."""
    profile_id = getattr(profile, "profile_id", None)
    if not isinstance(profile_id, str) or not profile_id:
        raise TemporaryBootBindingError("selected profile has invalid profile_id")
    if not isinstance(gate, PhysicalCandidateGateEvidence) or gate.schema_version != 1:
        raise TemporaryBootBindingError("physical candidate gate must be schema-v1 typed evidence")
    if not isinstance(binding, PhysicalBootIdentityBindingEvidence) or binding.schema_version != 1:
        raise TemporaryBootBindingError("physical boot identity binding must be schema-v1 typed evidence")

    if binding.profile_id != profile_id or gate.profile_id != profile_id:
        raise TemporaryBootBindingError("boot identity binding profile mismatch")
    if binding.device_serial != gate.device_serial:
        raise TemporaryBootBindingError("boot identity binding serial mismatch")
    if binding.physical_candidate_gate_sha256 != gate.evidence_sha256():
        raise TemporaryBootBindingError("boot identity binding is detached from the physical candidate gate")
    if binding.physical_baseline_bundle_sha256 != gate.physical_baseline_bundle_sha256:
        raise TemporaryBootBindingError("boot identity binding physical baseline mismatch")
    if binding.stock_provenance_sha256 != gate.stock_provenance_sha256:
        raise TemporaryBootBindingError("boot identity binding stock provenance mismatch")
    if binding.boot_plan_sha256 != gate.boot_plan_sha256:
        raise TemporaryBootBindingError("boot identity binding boot-plan mismatch")
    if binding.stock_boot_sha256 != gate.stock_boot_sha256:
        raise TemporaryBootBindingError("boot identity binding stock boot mismatch")
    if (
        binding.candidate_boot_sha256 != gate.boot_image_sha256
        or binding.candidate_boot_size != gate.boot_image_size
    ):
        raise TemporaryBootBindingError("boot identity binding candidate boot mismatch")
    if binding.candidate_kernel_sha256 != gate.kernel_image_sha256:
        raise TemporaryBootBindingError("boot identity binding candidate kernel mismatch")
    if binding.candidate_dtb_sha256 != gate.dtb_sha256:
        raise TemporaryBootBindingError("boot identity binding candidate DTB mismatch")
    if binding.candidate_external_dtbo_sha256 != gate.dtbo_image_sha256:
        raise TemporaryBootBindingError("boot identity binding candidate DTBO mismatch")

    for value, label in (
        (binding.stock_boot_sha256, "stock boot SHA-256"),
        (binding.stock_kernel_sha256, "stock kernel SHA-256"),
        (binding.stock_ramdisk_sha256, "stock ramdisk SHA-256"),
        (binding.candidate_boot_sha256, "candidate boot SHA-256"),
        (binding.candidate_kernel_sha256, "candidate kernel SHA-256"),
        (binding.candidate_ramdisk_sha256, "candidate ramdisk SHA-256"),
        (binding.physical_candidate_gate_sha256, "physical candidate gate SHA-256"),
        (binding.physical_baseline_bundle_sha256, "physical baseline bundle SHA-256"),
        (binding.stock_provenance_sha256, "stock provenance SHA-256"),
        (binding.boot_plan_sha256, "boot plan SHA-256"),
    ):
        _sha(value, label)

    if gate.dtb_sha256 is not None:
        _sha(binding.candidate_dtb_sha256, "candidate DTB SHA-256")
    if gate.dtbo_image_sha256 is not None:
        _sha(binding.candidate_external_dtbo_sha256, "candidate external DTBO SHA-256")

    if (
        binding.stock_exact_bytes_verified is not True
        or binding.candidate_exact_bytes_verified is not True
        or binding.component_identity_bound is not True
        or binding.avb_layout_bound is not True
    ):
        raise TemporaryBootBindingError("boot identity binding is incomplete")
    if (
        binding.temporary_boot_executed is not False
        or binding.phone_storage_written is not False
        or binding.hardware_verified is not False
        or binding.beta_gate_credit is not False
    ):
        raise TemporaryBootBindingError("boot identity binding contains an invalid pre-boot claim")

    digest = binding.evidence_sha256()
    _sha(digest, "physical boot identity binding SHA-256")
    # Keep a tiny independent canonicalization sanity check here so a future custom
    # evidence_sha256 implementation cannot silently stop being SHA-256(canonical_json).
    if digest != sha256(binding.canonical_json().encode("utf-8")).hexdigest():
        raise TemporaryBootBindingError("boot identity binding canonical digest mismatch")
    return digest
