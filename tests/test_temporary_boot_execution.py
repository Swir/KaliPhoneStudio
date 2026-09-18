from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import subprocess

import pytest

from kaliphonestudio.fastboot_baseline import FastbootBaselineEvidence
from kaliphonestudio.fastboot_capture_bundle import FastbootCaptureBundleEvidence
from kaliphonestudio.fastboot_tool import FastbootToolEvidence
from kaliphonestudio.physical_baseline_bundle import PhysicalBaselineBundleEvidence
from kaliphonestudio.physical_boot_identity_binding import PhysicalBootIdentityBindingEvidence
from kaliphonestudio.physical_candidate_gate import PhysicalCandidateGateEvidence
from kaliphonestudio.physical_recovery_readiness import (
    PhysicalRecoveryReadinessEvidence,
    build_physical_recovery_readiness,
)
from kaliphonestudio.profiles import DeviceProfile
from kaliphonestudio.temporary_boot_execution import (
    TemporaryBootExecutionError,
    execute_temporary_boot_once,
    probe_temporary_boot_runtime,
    write_temporary_boot_execution,
    write_temporary_boot_runtime_probe,
)
from kaliphonestudio.temporary_boot_offer import (
    authorize_temporary_boot_offer,
    prepare_temporary_boot_offer,
)


def _h(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


class _Result:
    def __init__(self, returncode: int, stdout: bytes):
        self.returncode = returncode
        self.stdout = stdout


def _transcript(*, serial: str = "SERIAL123", unlocked: str = "yes", slot: str = "a") -> bytes:
    values = {
        "product": "demo",
        "serialno": serial,
        "current-slot": slot,
        "slot-count": "2",
        "unlocked": unlocked,
        "secure": "yes",
        "version-bootloader": "BL1",
        "version-baseband": "BB1",
    }
    return "".join(f"(bootloader) {key}: {value}\n" for key, value in values.items()).encode("utf-8")


def _physical(
    baseline: FastbootBaselineEvidence,
    capture: FastbootCaptureBundleEvidence,
    stock_sha: str,
    stock_size: int,
) -> PhysicalBaselineBundleEvidence:
    return PhysicalBaselineBundleEvidence(
        schema_version=1,
        profile_id=baseline.profile_id,
        device_serial=baseline.serialno,
        product=baseline.product,
        firmware_build=baseline.firmware_build,
        firmware_fingerprint=baseline.firmware_fingerprint,
        fastboot_capture_bundle_sha256=capture.evidence_sha256(),
        fastboot_baseline_evidence_sha256=baseline.evidence_sha256(),
        fastboot_transcript_sha256=baseline.transcript_sha256,
        stock_provenance_sha256=_h("stock-provenance"),
        stock_ota_sha256=_h("ota"),
        stock_ota_size=4096,
        stock_payload_sha256=_h("payload"),
        stock_payload_metadata_sha256=_h("payload-metadata"),
        stock_payload_size=2048,
        stock_boot_sha256=stock_sha,
        stock_boot_size=stock_size,
        stock_boot_header_version=2,
        firmware_metadata_sha256=_h("firmware-metadata"),
        baseline_matches_exact_stock_ota=True,
        ready_for_candidate_instantiation=True,
        temporary_boot_authorized=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def _binding(
    gate: PhysicalCandidateGateEvidence,
    physical: PhysicalBaselineBundleEvidence,
) -> PhysicalBootIdentityBindingEvidence:
    return PhysicalBootIdentityBindingEvidence(
        schema_version=1,
        profile_id=gate.profile_id,
        device_serial=gate.device_serial,
        physical_baseline_bundle_sha256=physical.evidence_sha256(),
        physical_candidate_gate_sha256=gate.evidence_sha256(),
        stock_provenance_sha256=gate.stock_provenance_sha256,
        boot_plan_sha256=gate.boot_plan_sha256,
        stock_boot_sha256=gate.stock_boot_sha256,
        stock_boot_size=physical.stock_boot_size,
        stock_boot_header_version=2,
        stock_kernel_sha256=_h("stock-kernel"),
        stock_kernel_size=64,
        stock_ramdisk_sha256=_h("stock-ramdisk"),
        stock_ramdisk_size=64,
        stock_second_sha256=None,
        stock_second_size=0,
        stock_recovery_dtbo_sha256=None,
        stock_recovery_dtbo_size=0,
        stock_dtb_sha256=_h("stock-dtb"),
        stock_dtb_size=64,
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
        candidate_kernel_size=64,
        candidate_ramdisk_sha256=_h("candidate-ramdisk"),
        candidate_ramdisk_size=64,
        candidate_second_sha256=None,
        candidate_second_size=0,
        candidate_recovery_dtbo_sha256=None,
        candidate_recovery_dtbo_size=0,
        candidate_dtb_sha256=gate.dtb_sha256,
        candidate_dtb_size=64,
        candidate_external_dtbo_sha256=gate.dtbo_image_sha256,
        candidate_external_dtbo_size=64,
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
    fastboot = tmp_path / "fastboot.exe"
    fastboot.write_bytes(b"reviewed-fastboot-binary")
    image = tmp_path / "candidate-boot.img"
    image.write_bytes(b"candidate-boot-image" * 100)
    stock_boot = tmp_path / "stock-boot.img"
    stock_boot.write_bytes(b"exact-stock-boot-recovery-material" * 100)
    fastboot_sha = sha256(fastboot.read_bytes()).hexdigest()
    image_sha = sha256(image.read_bytes()).hexdigest()
    stock_sha = sha256(stock_boot.read_bytes()).hexdigest()
    profile = DeviceProfile(
        path=Path("devices/acme/demo/profile.json"),
        data={
            "profile_id": "acme/demo",
            "vendor": "Acme",
            "display_name": "Demo",
            "codename": "demo",
            "model": "DEMO",
            "aliases": ["demo"],
            "confirmation_text": "DEMO-PHONE",
            "partition_limits": {"boot": 1024 * 1024},
            "ab_device": True,
            "ab_partitions": ["boot", "dtbo"],
            "recovery_notes": ["Use exact captured stock boot material for recovery review."],
            "boot": {"include_dtb": True},
            "fastboot_probe": {
                "required_vars": [
                    "product", "serialno", "current-slot", "slot-count", "unlocked", "secure",
                    "version-bootloader", "version-baseband",
                ],
                "identity_var": "product",
                "serial_var": "serialno",
                "current_slot_var": "current-slot",
                "slot_count_var": "slot-count",
                "unlocked_var": "unlocked",
                "secure_var": "secure",
                "bootloader_version_var": "version-bootloader",
                "baseband_version_var": "version-baseband",
                "expected_slot_count": 2,
            },
        },
    )
    baseline = FastbootBaselineEvidence(
        schema_version=1,
        profile_id=profile.profile_id,
        transcript_sha256=_h("original transcript"),
        transcript_size=4096,
        firmware_build="FW.1",
        firmware_fingerprint="acme/demo/demo:1/test:user/release-keys",
        product="demo",
        serialno="SERIAL123",
        current_slot="a",
        slot_count=2,
        unlocked=True,
        secure=True,
        bootloader_version="BL1",
        baseband_version="BB1",
        variables={
            "product": "demo",
            "serialno": "SERIAL123",
            "current-slot": "a",
            "slot-count": "2",
            "unlocked": "yes",
            "secure": "yes",
            "version-bootloader": "BL1",
            "version-baseband": "BB1",
        },
        beta_gate_credit=False,
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
        device_serial=baseline.serialno,
        product=baseline.product,
        firmware_build=baseline.firmware_build,
        firmware_fingerprint=baseline.firmware_fingerprint,
        transcript_sha256=baseline.transcript_sha256,
        transcript_size=baseline.transcript_size,
        baseline_evidence_sha256=baseline.evidence_sha256(),
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
    physical = _physical(baseline, capture, stock_sha, stock_boot.stat().st_size)
    gate = PhysicalCandidateGateEvidence(
        schema_version=1,
        profile_id=profile.profile_id,
        device_serial=capture.device_serial,
        firmware_build=capture.firmware_build,
        firmware_fingerprint=capture.firmware_fingerprint,
        physical_baseline_bundle_sha256=physical.evidence_sha256(),
        fastboot_capture_bundle_sha256=capture.evidence_sha256(),
        fastboot_baseline_evidence_sha256=capture.baseline_evidence_sha256,
        fastboot_transcript_sha256=capture.transcript_sha256,
        stock_provenance_sha256=physical.stock_provenance_sha256,
        stock_ota_sha256=physical.stock_ota_sha256,
        stock_boot_sha256=physical.stock_boot_sha256,
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
    binding = _binding(gate, physical)
    recovery = build_physical_recovery_readiness(
        profile,
        baseline,
        physical,
        binding,
        stock_boot=stock_boot,
    )
    offer = prepare_temporary_boot_offer(
        profile, gate, capture, tool, fastboot_executable=fastboot, boot_image=image
    )
    authorization = authorize_temporary_boot_offer(offer, profile, "DEMO-PHONE")
    return (
        profile,
        baseline,
        capture,
        tool,
        physical,
        gate,
        binding,
        recovery,
        offer,
        authorization,
        fastboot,
        image,
        stock_boot,
    )


def _runner(*, transcript: bytes | None = None, devices: bytes | None = None, boot_rc: int = 0):
    calls: list[tuple[str, ...]] = []
    transcript = _transcript() if transcript is None else transcript
    devices = b"SERIAL123\tfastboot\n" if devices is None else devices

    def run(argv, **kwargs):
        assert kwargs["shell"] is False
        assert kwargs["check"] is False
        assert kwargs["stdin"] is subprocess.DEVNULL
        assert kwargs["stdout"] is subprocess.PIPE
        assert kwargs["stderr"] is subprocess.STDOUT
        calls.append(tuple(str(item) for item in argv))
        if argv[-1] == "devices":
            return _Result(0, devices)
        if argv[-2:] == ["getvar", "all"]:
            return _Result(0, transcript)
        if len(argv) >= 5 and argv[-2] == "boot":
            return _Result(boot_rc, b"OKAY temporary boot\n" if boot_rc == 0 else b"FAILED temporary boot\n")
        raise AssertionError(f"unexpected argv: {argv!r}")

    return run, calls


def _probe_args(fixture):
    profile, baseline, capture, tool, physical, gate, binding, recovery, offer, auth, _, _, stock_boot = fixture
    return profile, offer, auth, gate, binding, capture, tool, baseline, physical, recovery, stock_boot


def test_probe_revalidates_recovery_material_then_exact_device_read_only(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    profile, offer, auth, gate, binding, capture, tool, baseline, physical, recovery, stock_boot = _probe_args(fixture)
    runner, calls = _runner()
    probe = probe_temporary_boot_runtime(
        profile,
        offer,
        auth,
        gate,
        binding,
        capture,
        tool,
        baseline,
        physical,
        recovery,
        stock_boot=stock_boot,
        runner=runner,
    )
    assert probe.schema_version == 3
    assert probe.physical_baseline_bundle_sha256 == physical.evidence_sha256()
    assert probe.boot_identity_binding_sha256 == binding.evidence_sha256()
    assert probe.recovery_readiness_sha256 == recovery.evidence_sha256()
    assert probe.recovery_stock_boot_sha256 == recovery.stock_boot_sha256
    assert probe.device_serial == "SERIAL123"
    assert probe.current_slot == "a"
    assert probe.captured_active_slot == "a"
    assert probe.expected_inactive_slot == "b"
    assert probe.slot_count == 2
    assert probe.read_only is True
    assert probe.phone_storage_written is False
    assert probe.hardware_verified is False
    assert probe.beta_gate_credit is False
    assert [call[-1] for call in calls] == ["devices", "all"]
    assert all("boot" not in call for call in calls)


def test_execute_invokes_only_serial_bound_boot_after_recovery_and_probe(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    profile, offer, auth, gate, binding, capture, tool, baseline, physical, recovery, stock_boot = _probe_args(fixture)
    fastboot, image = fixture[10], fixture[11]
    runner, calls = _runner()
    probe, execution = execute_temporary_boot_once(
        profile,
        offer,
        auth,
        gate,
        binding,
        capture,
        tool,
        baseline,
        physical,
        recovery,
        stock_boot=stock_boot,
        runner=runner,
    )
    assert calls[-1] == (str(fastboot.resolve()), "-s", "SERIAL123", "boot", str(image.resolve()))
    assert len(calls) == 3
    assert execution.runtime_probe_sha256 == probe.evidence_sha256()
    assert execution.command_invoked is True
    assert execution.temporary_boot_executed is True
    assert execution.temporary_boot_command_succeeded is True
    assert execution.persistent_write is False
    assert execution.phone_storage_written is False
    assert execution.kali_userspace_verified is False
    assert execution.hardware_verified is False
    assert execution.beta_gate_credit is False
    assert all(not any(verb in call for verb in ("flash", "erase", "set_active", "reboot")) for call in calls)


def test_detached_boot_identity_binding_fails_before_fastboot(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    profile, offer, auth, gate, binding, capture, tool, baseline, physical, recovery, stock_boot = _probe_args(fixture)
    detached = replace(binding, physical_candidate_gate_sha256=_h("other-gate"))
    runner, calls = _runner()
    with pytest.raises(TemporaryBootExecutionError, match="detached"):
        execute_temporary_boot_once(
            profile, offer, auth, gate, detached, capture, tool, baseline, physical, recovery,
            stock_boot=stock_boot, runner=runner,
        )
    assert calls == []


def test_detached_recovery_readiness_fails_before_fastboot(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    profile, offer, auth, gate, binding, capture, tool, baseline, physical, recovery, stock_boot = _probe_args(fixture)
    detached = replace(recovery, physical_candidate_gate_sha256=_h("other-gate"))
    runner, calls = _runner()
    with pytest.raises(TemporaryBootExecutionError, match="recovery readiness"):
        execute_temporary_boot_once(
            profile, offer, auth, gate, binding, capture, tool, baseline, physical, detached,
            stock_boot=stock_boot, runner=runner,
        )
    assert calls == []


def test_local_stock_recovery_material_drift_fails_before_fastboot(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    profile, offer, auth, gate, binding, capture, tool, baseline, physical, recovery, stock_boot = _probe_args(fixture)
    stock_boot.write_bytes(stock_boot.read_bytes() + b"drift")
    runner, calls = _runner()
    with pytest.raises(TemporaryBootExecutionError, match="recovery readiness"):
        execute_temporary_boot_once(
            profile, offer, auth, gate, binding, capture, tool, baseline, physical, recovery,
            stock_boot=stock_boot, runner=runner,
        )
    assert calls == []


def test_recovery_precredit_or_write_authorization_fails_before_fastboot(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    profile, offer, auth, gate, binding, capture, tool, baseline, physical, recovery, stock_boot = _probe_args(fixture)
    unsafe = replace(recovery, persistent_write_authorized=True)
    runner, calls = _runner()
    with pytest.raises(TemporaryBootExecutionError, match="recovery readiness"):
        execute_temporary_boot_once(
            profile, offer, auth, gate, binding, capture, tool, baseline, physical, unsafe,
            stock_boot=stock_boot, runner=runner,
        )
    assert calls == []


def test_device_swap_fails_before_boot(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    profile, offer, auth, gate, binding, capture, tool, baseline, physical, recovery, stock_boot = _probe_args(fixture)
    runner, calls = _runner(devices=b"OTHER\tfastboot\n")
    with pytest.raises(TemporaryBootExecutionError, match="requested fastboot serial"):
        execute_temporary_boot_once(
            profile, offer, auth, gate, binding, capture, tool, baseline, physical, recovery,
            stock_boot=stock_boot, runner=runner,
        )
    assert all("boot" not in call for call in calls)


def test_unlock_or_slot_drift_fails_before_boot(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    profile, offer, auth, gate, binding, capture, tool, baseline, physical, recovery, stock_boot = _probe_args(fixture)
    for transcript in (_transcript(unlocked="no"), _transcript(slot="b")):
        runner, calls = _runner(transcript=transcript)
        with pytest.raises(TemporaryBootExecutionError, match="drifted|unlocked"):
            execute_temporary_boot_once(
                profile, offer, auth, gate, binding, capture, tool, baseline, physical, recovery,
                stock_boot=stock_boot, runner=runner,
            )
        assert all("boot" not in call for call in calls)


def test_detached_authorization_fails_before_fastboot(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    profile, offer, auth, gate, binding, capture, tool, baseline, physical, recovery, stock_boot = _probe_args(fixture)
    bad = replace(auth, offer_sha256=_h("other-offer"))
    runner, calls = _runner()
    with pytest.raises(TemporaryBootExecutionError, match="detached"):
        execute_temporary_boot_once(
            profile, offer, bad, gate, binding, capture, tool, baseline, physical, recovery,
            stock_boot=stock_boot, runner=runner,
        )
    assert calls == []


def test_local_candidate_image_drift_fails_before_fastboot(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    profile, offer, auth, gate, binding, capture, tool, baseline, physical, recovery, stock_boot = _probe_args(fixture)
    image = fixture[11]
    image.write_bytes(b"changed-after-authorization")
    runner, calls = _runner()
    with pytest.raises(TemporaryBootExecutionError, match="boot image bytes"):
        execute_temporary_boot_once(
            profile, offer, auth, gate, binding, capture, tool, baseline, physical, recovery,
            stock_boot=stock_boot, runner=runner,
        )
    assert calls == []


def test_normal_fastboot_failure_is_recorded_without_hardware_credit(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    profile, offer, auth, gate, binding, capture, tool, baseline, physical, recovery, stock_boot = _probe_args(fixture)
    runner, _ = _runner(boot_rc=1)
    probe, execution = execute_temporary_boot_once(
        profile, offer, auth, gate, binding, capture, tool, baseline, physical, recovery,
        stock_boot=stock_boot, runner=runner,
    )
    assert execution.returncode == 1
    assert execution.temporary_boot_executed is True
    assert execution.temporary_boot_command_succeeded is False
    assert execution.runtime_probe_sha256 == probe.evidence_sha256()
    assert execution.hardware_verified is False
    assert execution.beta_gate_credit is False


def test_evidence_writers_are_immutable(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    profile, offer, auth, gate, binding, capture, tool, baseline, physical, recovery, stock_boot = _probe_args(fixture)
    runner, _ = _runner()
    probe, execution = execute_temporary_boot_once(
        profile, offer, auth, gate, binding, capture, tool, baseline, physical, recovery,
        stock_boot=stock_boot, runner=runner,
    )
    probe_path = tmp_path / "probe.json"
    execution_path = tmp_path / "execution.json"
    assert write_temporary_boot_runtime_probe(probe, probe_path) == probe.evidence_sha256()
    assert write_temporary_boot_execution(execution, execution_path) == execution.evidence_sha256()
    with pytest.raises(TemporaryBootExecutionError, match="overwrite"):
        write_temporary_boot_runtime_probe(probe, probe_path)
    with pytest.raises(TemporaryBootExecutionError, match="overwrite"):
        write_temporary_boot_execution(execution, execution_path)
