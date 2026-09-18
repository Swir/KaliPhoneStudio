from __future__ import annotations

from dataclasses import fields, replace
from hashlib import sha256
from pathlib import Path

import pytest

from kaliphonestudio.fastboot_capture_bundle import FastbootCaptureBundleEvidence
from kaliphonestudio.fastboot_tool import FastbootToolEvidence
from kaliphonestudio.physical_boot_identity_binding import PhysicalBootIdentityBindingEvidence
from kaliphonestudio.physical_candidate_gate import PhysicalCandidateGateEvidence
from kaliphonestudio.profiles import DeviceProfile
from kaliphonestudio.temporary_boot_offer import (
    TemporaryBootOfferError,
    authorize_temporary_boot_offer,
    prepare_temporary_boot_offer,
    verify_temporary_boot_offer,
    write_temporary_boot_offer,
)


def _h(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _binding(profile: DeviceProfile, gate: PhysicalCandidateGateEvidence) -> PhysicalBootIdentityBindingEvidence:
    values = {field.name: None for field in fields(PhysicalBootIdentityBindingEvidence)}
    values.update(
        schema_version=1,
        profile_id=profile.profile_id,
        device_serial=gate.device_serial,
        physical_baseline_bundle_sha256=gate.physical_baseline_bundle_sha256,
        physical_candidate_gate_sha256=gate.evidence_sha256(),
        stock_provenance_sha256=gate.stock_provenance_sha256,
        boot_plan_sha256=gate.boot_plan_sha256,
        stock_boot_sha256=gate.stock_boot_sha256,
        stock_boot_size=4096,
        stock_boot_header_version=2,
        stock_kernel_sha256=_h("stock-kernel"),
        stock_kernel_size=1024,
        stock_ramdisk_sha256=_h("stock-ramdisk"),
        stock_ramdisk_size=1024,
        stock_second_sha256=None,
        stock_second_size=0,
        stock_recovery_dtbo_sha256=None,
        stock_recovery_dtbo_size=0,
        stock_dtb_sha256=_h("stock-dtb") if gate.dtb_sha256 is not None else None,
        stock_dtb_size=512 if gate.dtb_sha256 is not None else None,
        stock_avb_footer_present=False,
        stock_avb_footer_version_major=None,
        stock_avb_footer_version_minor=None,
        stock_avb_original_image_size=None,
        stock_avb_vbmeta_offset=None,
        stock_avb_vbmeta_size=None,
        stock_avb_vbmeta_sha256=None,
        candidate_boot_sha256=gate.boot_image_sha256,
        candidate_boot_size=gate.boot_image_size,
        candidate_boot_header_version=2,
        candidate_kernel_sha256=gate.kernel_image_sha256,
        candidate_kernel_size=1024,
        candidate_ramdisk_sha256=_h("candidate-ramdisk"),
        candidate_ramdisk_size=1024,
        candidate_second_sha256=None,
        candidate_second_size=0,
        candidate_recovery_dtbo_sha256=None,
        candidate_recovery_dtbo_size=0,
        candidate_dtb_sha256=gate.dtb_sha256,
        candidate_dtb_size=512 if gate.dtb_sha256 is not None else None,
        candidate_external_dtbo_sha256=gate.dtbo_image_sha256,
        candidate_external_dtbo_size=512 if gate.dtbo_image_sha256 is not None else None,
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
    return PhysicalBootIdentityBindingEvidence(**values)


def _fixture(tmp_path: Path, *, boot_limit: int = 1024 * 1024):
    fastboot = tmp_path / "fastboot.exe"
    fastboot.write_bytes(b"reviewed-fastboot-binary")
    image = tmp_path / "candidate-boot.img"
    image.write_bytes(b"candidate-boot-image" * 100)
    fastboot_sha = sha256(fastboot.read_bytes()).hexdigest()
    image_sha = sha256(image.read_bytes()).hexdigest()

    profile = DeviceProfile(
        path=Path("devices/acme/demo/profile.json"),
        data={
            "profile_id": "acme/demo",
            "confirmation_text": "DEMO-PHONE",
            "partition_limits": {"boot": boot_limit},
        },
    )
    tool = FastbootToolEvidence(
        schema_version=1,
        tool="fastboot",
        policy_sha256=_h("policy"),
        required_platform_tools_version="37.0.1",
        observed_platform_tools_version="37.0.1",
        executable_filename="fastboot.exe",
        executable_sha256=fastboot_sha,
        executable_size=fastboot.stat().st_size,
        version_line="fastboot version 37.0.1",
        version_output_sha256=_h("version-output"),
        hardware_verified=False,
        beta_gate_credit=False,
    )
    capture = FastbootCaptureBundleEvidence(
        schema_version=1,
        profile_id=profile.profile_id,
        device_serial="SERIAL123",
        product="demo",
        firmware_build="FW.1",
        firmware_fingerprint="acme/demo/demo:1/test:user/release-keys",
        transcript_sha256=_h("transcript"),
        transcript_size=4096,
        baseline_evidence_sha256=_h("baseline"),
        fastboot_tool_evidence_sha256=tool.evidence_sha256(),
        fastboot_tool_policy_sha256=tool.policy_sha256,
        fastboot_executable_sha256=tool.executable_sha256,
        fastboot_executable_size=tool.executable_size,
        platform_tools_version=tool.observed_platform_tools_version,
        capture_policy="fastboot-version+devices+serial-getvar-all-v1",
        read_only=True,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    gate = PhysicalCandidateGateEvidence(
        schema_version=1,
        profile_id=profile.profile_id,
        device_serial=capture.device_serial,
        firmware_build=capture.firmware_build,
        firmware_fingerprint=capture.firmware_fingerprint,
        physical_baseline_bundle_sha256=_h("physical"),
        fastboot_capture_bundle_sha256=capture.evidence_sha256(),
        fastboot_baseline_evidence_sha256=capture.baseline_evidence_sha256,
        fastboot_transcript_sha256=capture.transcript_sha256,
        stock_provenance_sha256=_h("stock-provenance"),
        stock_ota_sha256=_h("ota"),
        stock_boot_sha256=_h("stock-boot"),
        first_boot_manifest_sha256=_h("manifest"),
        first_boot_authority_bundle_sha256=_h("authorities"),
        boot_authorization_sha256=_h("boot-authorization"),
        boot_plan_sha256=_h("boot-plan"),
        boot_image_sha256=image_sha,
        boot_image_size=image.stat().st_size,
        kernel_image_sha256=_h("kernel"),
        rootfs_artifact_sha256=_h("rootfs"),
        dtb_sha256=_h("dtb"),
        dtbo_image_sha256=_h("dtbo"),
        reviewed_authorities_bound=True,
        exact_physical_baseline_bound=True,
        ready_for_temporary_boot_offer=True,
        temporary_boot_executed=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    return profile, gate, capture, tool, fastboot, image


def _prepare(profile, gate, capture, tool, fastboot, image):
    return prepare_temporary_boot_offer(
        profile,
        gate,
        capture,
        tool,
        boot_identity_binding=_binding(profile, gate),
        fastboot_executable=fastboot,
        boot_image=image,
    )


def test_prepare_offer_is_exact_argv_only_and_nonexecuting(tmp_path: Path) -> None:
    profile, gate, capture, tool, fastboot, image = _fixture(tmp_path)
    binding = _binding(profile, gate)
    offer = prepare_temporary_boot_offer(
        profile,
        gate,
        capture,
        tool,
        boot_identity_binding=binding,
        fastboot_executable=fastboot,
        boot_image=image,
    )
    assert offer.argv == (
        str(fastboot.resolve()), "-s", "SERIAL123", "boot", str(image.resolve())
    )
    assert offer.evidence.schema_version == 2
    assert offer.evidence.command_policy == "fastboot-serial-temporary-boot-only-v2-exact-boot-identity"
    assert offer.evidence.physical_boot_identity_binding_sha256 == binding.evidence_sha256()
    assert offer.evidence.persistent_write is False
    assert offer.evidence.phone_storage_written is False
    assert offer.evidence.temporary_boot_executed is False
    assert offer.evidence.hardware_verified is False
    assert offer.evidence.beta_gate_credit is False
    verify_temporary_boot_offer(offer, profile, gate, capture, tool)


def test_rejects_detached_exact_boot_identity_binding(tmp_path: Path) -> None:
    profile, gate, capture, tool, fastboot, image = _fixture(tmp_path)
    binding = replace(_binding(profile, gate), boot_plan_sha256=_h("other-plan"))
    with pytest.raises(TemporaryBootOfferError, match="boot-plan mismatch"):
        prepare_temporary_boot_offer(
            profile,
            gate,
            capture,
            tool,
            boot_identity_binding=binding,
            fastboot_executable=fastboot,
            boot_image=image,
        )


def test_rejects_candidate_binding_byte_drift(tmp_path: Path) -> None:
    profile, gate, capture, tool, fastboot, image = _fixture(tmp_path)
    binding = replace(_binding(profile, gate), candidate_boot_sha256=_h("other-image"))
    with pytest.raises(TemporaryBootOfferError, match="candidate boot mismatch"):
        prepare_temporary_boot_offer(
            profile,
            gate,
            capture,
            tool,
            boot_identity_binding=binding,
            fastboot_executable=fastboot,
            boot_image=image,
        )


def test_rejects_detached_capture_bundle(tmp_path: Path) -> None:
    profile, gate, capture, tool, fastboot, image = _fixture(tmp_path)
    capture = replace(capture, transcript_sha256=_h("other-transcript"))
    with pytest.raises(TemporaryBootOfferError, match="detached"):
        _prepare(profile, gate, capture, tool, fastboot, image)


def test_rejects_fastboot_byte_drift(tmp_path: Path) -> None:
    profile, gate, capture, tool, fastboot, image = _fixture(tmp_path)
    fastboot.write_bytes(b"different-fastboot")
    with pytest.raises(TemporaryBootOfferError, match="executable bytes"):
        _prepare(profile, gate, capture, tool, fastboot, image)


def test_rejects_candidate_image_byte_drift(tmp_path: Path) -> None:
    profile, gate, capture, tool, fastboot, image = _fixture(tmp_path)
    image.write_bytes(b"different-image")
    with pytest.raises(TemporaryBootOfferError, match="boot image bytes"):
        _prepare(profile, gate, capture, tool, fastboot, image)


def test_rejects_boot_image_above_profile_limit(tmp_path: Path) -> None:
    profile, gate, capture, tool, fastboot, image = _fixture(tmp_path, boot_limit=64)
    with pytest.raises(TemporaryBootOfferError, match="partition limit"):
        _prepare(profile, gate, capture, tool, fastboot, image)


def test_user_authorization_requires_exact_profile_confirmation(tmp_path: Path) -> None:
    profile, gate, capture, tool, fastboot, image = _fixture(tmp_path)
    offer = _prepare(profile, gate, capture, tool, fastboot, image)
    with pytest.raises(TemporaryBootOfferError, match="confirmation token"):
        authorize_temporary_boot_offer(offer, profile, "WRONG")
    authorization = authorize_temporary_boot_offer(offer, profile, "DEMO-PHONE")
    assert authorization.confirmation_verified is True
    assert authorization.execution_permitted is True
    assert authorization.temporary_boot_executed is False
    assert authorization.persistent_write is False
    assert authorization.phone_storage_written is False
    assert authorization.hardware_verified is False
    assert authorization.beta_gate_credit is False


def test_rejects_profile_or_gate_host_claim_drift(tmp_path: Path) -> None:
    profile, gate, capture, tool, fastboot, image = _fixture(tmp_path)
    changed_profile = replace(profile, data={**profile.data, "profile_id": "acme/other"})
    with pytest.raises(TemporaryBootOfferError, match="profile mismatch"):
        prepare_temporary_boot_offer(
            changed_profile,
            gate,
            capture,
            tool,
            boot_identity_binding=_binding(profile, gate),
            fastboot_executable=fastboot,
            boot_image=image,
        )
    with pytest.raises(TemporaryBootOfferError, match="host-only claim"):
        prepare_temporary_boot_offer(
            profile,
            replace(gate, temporary_boot_executed=True),
            capture,
            tool,
            boot_identity_binding=_binding(profile, gate),
            fastboot_executable=fastboot,
            boot_image=image,
        )


def test_writer_is_immutable_and_rejects_execution_claim(tmp_path: Path) -> None:
    profile, gate, capture, tool, fastboot, image = _fixture(tmp_path)
    offer = _prepare(profile, gate, capture, tool, fastboot, image)
    destination = tmp_path / "offer.json"
    digest = write_temporary_boot_offer(offer.evidence, destination)
    assert digest == offer.evidence.evidence_sha256()
    assert destination.read_text(encoding="utf-8") == offer.evidence.canonical_json()
    with pytest.raises(TemporaryBootOfferError, match="overwrite"):
        write_temporary_boot_offer(offer.evidence, destination)
    with pytest.raises(TemporaryBootOfferError, match="execution/write claim"):
        write_temporary_boot_offer(
            replace(offer.evidence, temporary_boot_executed=True),
            tmp_path / "bad.json",
        )
