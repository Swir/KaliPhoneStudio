from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from kaliphonestudio.fastboot_capture_bundle import FastbootCaptureBundleEvidence
from kaliphonestudio.fastboot_tool import FastbootToolEvidence
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


def test_prepare_offer_is_exact_argv_only_and_nonexecuting(tmp_path: Path) -> None:
    profile, gate, capture, tool, fastboot, image = _fixture(tmp_path)
    offer = prepare_temporary_boot_offer(
        profile, gate, capture, tool, fastboot_executable=fastboot, boot_image=image
    )
    assert offer.argv == (
        str(fastboot.resolve()), "-s", "SERIAL123", "boot", str(image.resolve())
    )
    assert offer.evidence.command_policy == "fastboot-serial-temporary-boot-only-v1"
    assert offer.evidence.persistent_write is False
    assert offer.evidence.phone_storage_written is False
    assert offer.evidence.temporary_boot_executed is False
    assert offer.evidence.hardware_verified is False
    assert offer.evidence.beta_gate_credit is False
    verify_temporary_boot_offer(offer, profile, gate, capture, tool)


def test_rejects_detached_capture_bundle(tmp_path: Path) -> None:
    profile, gate, capture, tool, fastboot, image = _fixture(tmp_path)
    capture = replace(capture, transcript_sha256=_h("other-transcript"))
    with pytest.raises(TemporaryBootOfferError, match="detached"):
        prepare_temporary_boot_offer(
            profile, gate, capture, tool, fastboot_executable=fastboot, boot_image=image
        )


def test_rejects_fastboot_byte_drift(tmp_path: Path) -> None:
    profile, gate, capture, tool, fastboot, image = _fixture(tmp_path)
    fastboot.write_bytes(b"different-fastboot")
    with pytest.raises(TemporaryBootOfferError, match="executable bytes"):
        prepare_temporary_boot_offer(
            profile, gate, capture, tool, fastboot_executable=fastboot, boot_image=image
        )


def test_rejects_candidate_image_byte_drift(tmp_path: Path) -> None:
    profile, gate, capture, tool, fastboot, image = _fixture(tmp_path)
    image.write_bytes(b"different-image")
    with pytest.raises(TemporaryBootOfferError, match="boot image bytes"):
        prepare_temporary_boot_offer(
            profile, gate, capture, tool, fastboot_executable=fastboot, boot_image=image
        )


def test_rejects_boot_image_above_profile_limit(tmp_path: Path) -> None:
    profile, gate, capture, tool, fastboot, image = _fixture(tmp_path, boot_limit=64)
    with pytest.raises(TemporaryBootOfferError, match="partition limit"):
        prepare_temporary_boot_offer(
            profile, gate, capture, tool, fastboot_executable=fastboot, boot_image=image
        )


def test_user_authorization_requires_exact_profile_confirmation(tmp_path: Path) -> None:
    profile, gate, capture, tool, fastboot, image = _fixture(tmp_path)
    offer = prepare_temporary_boot_offer(
        profile, gate, capture, tool, fastboot_executable=fastboot, boot_image=image
    )
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
            changed_profile, gate, capture, tool, fastboot_executable=fastboot, boot_image=image
        )
    with pytest.raises(TemporaryBootOfferError, match="host-only claim"):
        prepare_temporary_boot_offer(
            profile,
            replace(gate, temporary_boot_executed=True),
            capture,
            tool,
            fastboot_executable=fastboot,
            boot_image=image,
        )


def test_writer_is_immutable_and_rejects_execution_claim(tmp_path: Path) -> None:
    profile, gate, capture, tool, fastboot, image = _fixture(tmp_path)
    offer = prepare_temporary_boot_offer(
        profile, gate, capture, tool, fastboot_executable=fastboot, boot_image=image
    )
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
