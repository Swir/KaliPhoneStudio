from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from kaliphonestudio.fastboot_baseline import FastbootBaselineEvidence
from kaliphonestudio.physical_baseline_bundle import PhysicalBaselineBundleEvidence
from kaliphonestudio.physical_boot_identity_binding import PhysicalBootIdentityBindingEvidence
from kaliphonestudio.physical_recovery_readiness import (
    PhysicalRecoveryReadinessError,
    build_physical_recovery_readiness,
    verify_physical_recovery_readiness,
    write_physical_recovery_readiness,
)
from kaliphonestudio.profiles import DeviceProfile, get_profile


ROOT = Path(__file__).resolve().parents[1]
DEVICES_ROOT = ROOT / "devices"
SERIAL = "KPS-RECOVERY-001"


def _sha(label: str) -> str:
    return sha256(label.encode("utf-8")).hexdigest()


def _baseline(profile_id: str = "oneplus/avicii", *, active_slot: str | None = "a", slot_count: int | None = 2) -> FastbootBaselineEvidence:
    return FastbootBaselineEvidence(
        schema_version=1,
        profile_id=profile_id,
        transcript_sha256=_sha("transcript"),
        transcript_size=512,
        firmware_build="11.1.10.10.AC01BA",
        firmware_fingerprint="OnePlus/avicii_EEA/avicii:11/RKQ1.201022.002/210911:user/release-keys",
        product="avicii",
        serialno=SERIAL,
        current_slot=active_slot,
        slot_count=slot_count,
        unlocked=True,
        secure=True,
        bootloader_version="avicii-test-bootloader",
        baseband_version="avicii-test-baseband",
        variables={
            "product": "avicii",
            "serialno": SERIAL,
            "current-slot": active_slot or "",
            "slot-count": str(slot_count or ""),
            "unlocked": "yes",
            "secure": "yes",
        },
        beta_gate_credit=False,
    )


def _physical(baseline: FastbootBaselineEvidence, stock_sha: str, stock_size: int) -> PhysicalBaselineBundleEvidence:
    return PhysicalBaselineBundleEvidence(
        schema_version=1,
        profile_id=baseline.profile_id,
        device_serial=baseline.serialno,
        product=baseline.product,
        firmware_build=baseline.firmware_build,
        firmware_fingerprint=baseline.firmware_fingerprint,
        fastboot_capture_bundle_sha256=_sha("capture-bundle"),
        fastboot_baseline_evidence_sha256=baseline.evidence_sha256(),
        fastboot_transcript_sha256=baseline.transcript_sha256,
        stock_provenance_sha256=_sha("stock-provenance"),
        stock_ota_sha256=_sha("stock-ota"),
        stock_ota_size=4096,
        stock_payload_sha256=_sha("payload"),
        stock_payload_metadata_sha256=_sha("payload-metadata"),
        stock_payload_size=2048,
        stock_boot_sha256=stock_sha,
        stock_boot_size=stock_size,
        stock_boot_header_version=2,
        firmware_metadata_sha256=_sha("firmware-metadata"),
        baseline_matches_exact_stock_ota=True,
        ready_for_candidate_instantiation=True,
        temporary_boot_authorized=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def _binding(physical: PhysicalBaselineBundleEvidence, stock_sha: str, stock_size: int) -> PhysicalBootIdentityBindingEvidence:
    return PhysicalBootIdentityBindingEvidence(
        schema_version=1,
        profile_id=physical.profile_id,
        device_serial=physical.device_serial,
        physical_baseline_bundle_sha256=physical.evidence_sha256(),
        physical_candidate_gate_sha256=_sha("candidate-gate"),
        stock_provenance_sha256=physical.stock_provenance_sha256,
        boot_plan_sha256=_sha("boot-plan"),
        stock_boot_sha256=stock_sha,
        stock_boot_size=stock_size,
        stock_boot_header_version=2,
        stock_kernel_sha256=_sha("stock-kernel"),
        stock_kernel_size=1024,
        stock_ramdisk_sha256=_sha("stock-ramdisk"),
        stock_ramdisk_size=512,
        stock_second_sha256=None,
        stock_second_size=0,
        stock_recovery_dtbo_sha256=None,
        stock_recovery_dtbo_size=0,
        stock_dtb_sha256=_sha("stock-dtb"),
        stock_dtb_size=256,
        stock_avb_footer_present=False,
        stock_avb_footer_version_major=None,
        stock_avb_footer_version_minor=None,
        stock_avb_original_image_size=None,
        stock_avb_vbmeta_offset=None,
        stock_avb_vbmeta_size=None,
        stock_avb_vbmeta_sha256=None,
        candidate_boot_sha256=_sha("candidate-boot"),
        candidate_boot_size=8192,
        candidate_boot_header_version=2,
        candidate_kernel_sha256=_sha("candidate-kernel"),
        candidate_kernel_size=2048,
        candidate_ramdisk_sha256=_sha("candidate-ramdisk"),
        candidate_ramdisk_size=1024,
        candidate_second_sha256=None,
        candidate_second_size=0,
        candidate_recovery_dtbo_sha256=None,
        candidate_recovery_dtbo_size=0,
        candidate_dtb_sha256=_sha("candidate-dtb"),
        candidate_dtb_size=512,
        candidate_external_dtbo_sha256=_sha("candidate-dtbo"),
        candidate_external_dtbo_size=512,
        candidate_avb_footer_present=False,
        candidate_avb_footer_version_major=None,
        candidate_avb_footer_version_minor=None,
        candidate_avb_original_image_size=None,
        candidate_avb_vbmeta_offset=None,
        candidate_avb_vbmeta_size=None,
        candidate_avb_vbmeta_sha256=None,
        stock_exact_bytes_verified=True,
        candidate_exact_bytes_verified=True,
        component_identity_bound=True,
        avb_layout_bound=True,
        temporary_boot_executed=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def _fixture(tmp_path: Path):
    profile = get_profile(DEVICES_ROOT, "oneplus/avicii")
    stock_boot = tmp_path / "stock-boot.img"
    stock_boot.write_bytes(b"KPS exact stock boot recovery material\n")
    stock_sha = sha256(stock_boot.read_bytes()).hexdigest()
    baseline = _baseline()
    physical = _physical(baseline, stock_sha, stock_boot.stat().st_size)
    binding = _binding(physical, stock_sha, stock_boot.stat().st_size)
    return profile, baseline, physical, binding, stock_boot


def test_recovery_readiness_binds_exact_stock_material_and_ab_slot_context(tmp_path: Path) -> None:
    profile, baseline, physical, binding, stock_boot = _fixture(tmp_path)
    evidence = build_physical_recovery_readiness(
        profile,
        baseline,
        physical,
        binding,
        stock_boot=stock_boot,
    )

    assert evidence.profile_id == "oneplus/avicii"
    assert evidence.device_serial == SERIAL
    assert evidence.captured_active_slot == "a"
    assert evidence.expected_inactive_slot == "b"
    assert evidence.slot_count == 2
    assert evidence.ab_device is True
    assert evidence.stock_boot_sha256 == sha256(stock_boot.read_bytes()).hexdigest()
    assert evidence.stock_boot_material_present is True
    assert evidence.exact_stock_identity_bound is True
    assert evidence.slot_context_bound is True
    assert evidence.ready_for_temporary_boot_safety_review is True
    assert evidence.slot_switch_authorized is False
    assert evidence.inactive_slot_write_authorized is False
    assert evidence.persistent_write_authorized is False
    assert evidence.rollback_exercised is False
    assert evidence.recovery_verified is False
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False

    verify_physical_recovery_readiness(
        evidence,
        profile,
        baseline,
        physical,
        binding,
        stock_boot=stock_boot,
    )


def test_recovery_readiness_rejects_local_stock_boot_drift(tmp_path: Path) -> None:
    profile, baseline, physical, binding, stock_boot = _fixture(tmp_path)
    stock_boot.write_bytes(stock_boot.read_bytes() + b"drift")

    with pytest.raises(PhysicalRecoveryReadinessError, match="differs from exact physical provenance"):
        build_physical_recovery_readiness(profile, baseline, physical, binding, stock_boot=stock_boot)


def test_recovery_readiness_rejects_detached_boot_identity_binding(tmp_path: Path) -> None:
    profile, baseline, physical, binding, stock_boot = _fixture(tmp_path)
    detached = replace(binding, physical_baseline_bundle_sha256=_sha("other-physical-baseline"))

    with pytest.raises(PhysicalRecoveryReadinessError, match="detached from the physical baseline bundle"):
        build_physical_recovery_readiness(profile, baseline, physical, detached, stock_boot=stock_boot)


def test_recovery_readiness_rejects_ambiguous_ab_slot_context(tmp_path: Path) -> None:
    profile, baseline, _, _, stock_boot = _fixture(tmp_path)
    bad_baseline = replace(baseline, current_slot="c")
    physical = _physical(bad_baseline, sha256(stock_boot.read_bytes()).hexdigest(), stock_boot.stat().st_size)
    binding = _binding(physical, physical.stock_boot_sha256, physical.stock_boot_size)

    with pytest.raises(PhysicalRecoveryReadinessError, match="active slot a or b"):
        build_physical_recovery_readiness(profile, bad_baseline, physical, binding, stock_boot=stock_boot)


def test_recovery_readiness_rejects_precredited_or_written_binding(tmp_path: Path) -> None:
    profile, baseline, physical, binding, stock_boot = _fixture(tmp_path)
    unsafe = replace(binding, phone_storage_written=True)

    with pytest.raises(PhysicalRecoveryReadinessError, match="invalid execution/write/hardware claim"):
        build_physical_recovery_readiness(profile, baseline, physical, unsafe, stock_boot=stock_boot)


def test_recovery_readiness_supports_generic_single_slot_profile_without_inventing_slot(tmp_path: Path) -> None:
    base_profile = get_profile(DEVICES_ROOT, "oneplus/avicii")
    data = dict(base_profile.data)
    data["profile_id"] = "example/single-slot"
    data["confirmation_text"] = "SINGLE-SLOT"
    data["ab_device"] = False
    data["ab_partitions"] = []
    profile = DeviceProfile(path=Path("devices/example/single-slot/profile.json"), data=data)

    stock_boot = tmp_path / "stock-single.img"
    stock_boot.write_bytes(b"single slot stock boot\n")
    stock_sha = sha256(stock_boot.read_bytes()).hexdigest()
    baseline = _baseline(profile.profile_id, active_slot=None, slot_count=None)
    physical = _physical(baseline, stock_sha, stock_boot.stat().st_size)
    binding = _binding(physical, stock_sha, stock_boot.stat().st_size)

    evidence = build_physical_recovery_readiness(profile, baseline, physical, binding, stock_boot=stock_boot)
    assert evidence.ab_device is False
    assert evidence.captured_active_slot is None
    assert evidence.expected_inactive_slot is None
    assert evidence.slot_count is None
    assert evidence.slot_switch_authorized is False


def test_recovery_readiness_evidence_write_is_create_only(tmp_path: Path) -> None:
    profile, baseline, physical, binding, stock_boot = _fixture(tmp_path)
    evidence = build_physical_recovery_readiness(profile, baseline, physical, binding, stock_boot=stock_boot)
    destination = tmp_path / "recovery-readiness.json"

    digest = write_physical_recovery_readiness(evidence, destination)
    assert digest == evidence.evidence_sha256()
    assert destination.read_text(encoding="utf-8") == evidence.canonical_json()

    with pytest.raises(PhysicalRecoveryReadinessError, match="refusing to overwrite"):
        write_physical_recovery_readiness(evidence, destination)
