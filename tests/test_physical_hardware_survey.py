from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from kaliphonestudio.physical_boot_observation import PhysicalBootObservationEvidence
from kaliphonestudio.physical_hardware_survey import (
    PhysicalHardwareSurveyError,
    load_physical_hardware_survey_evidence,
    record_physical_hardware_survey,
    validate_physical_hardware_survey_evidence,
    write_physical_hardware_survey_evidence,
)
from kaliphonestudio.physical_rescue_diagnostics import record_physical_rescue_diagnostics
from kaliphonestudio.profiles import DeviceProfile


def _digest(ch: str) -> str:
    return ch * 64


def _profile(tmp_path: Path, profile_id: str = "vendor/test") -> DeviceProfile:
    return DeviceProfile(path=tmp_path / "profile.json", data={"profile_id": profile_id})


def _transcript(
    path: Path,
    probe_id: str = _digest("a"),
    *,
    survey_outside: bytes = b"",
    empty_survey: bool = False,
) -> bytes:
    lines = [
        b"KPS_RESCUE_STAGE=init-reached-v1",
        b"KPS_RESCUE_PROBE_ID=" + probe_id.encode(),
        b"KPS_DIAG_BEGIN=readonly-sysfs-inventory-v1",
        b"KPS_DIAG_BLOCK=sda|122142720|0",
        b"KPS_DIAG_SCSI_HOST=host0|ufshcd",
        b"KPS_DIAG_POWER=battery|Battery|Charging|73|-|4012000|-325000|312",
        b"KPS_DIAG_INPUT=event2|goodix_ts",
        b"KPS_DIAG_GRAPHICS=fb0|msm_drm",
        b"KPS_DIAG_DRM=card0-DSI-1|connected",
        b"KPS_DIAG_END=readonly-sysfs-inventory-v1",
        b"KPS_SURVEY_BEGIN=readonly-hardware-presence-v1",
    ]
    if not empty_survey:
        lines.extend(
            [
                b"KPS_SURVEY_USB_UDC=a600000.dwc3",
                b"KPS_SURVEY_USB_DEVICE=1-1|18d1|4ee7|00",
                b"KPS_SURVEY_NET=lo|772|unknown",
                b"KPS_SURVEY_NET=wlan0|1|down",
                b"KPS_SURVEY_RFKILL=phy0|wlan|1|0|0",
                b"KPS_SURVEY_RFKILL=hci0|bluetooth|1|0|0",
                b"KPS_SURVEY_SOUND=card0|sm7250",
                b"KPS_SURVEY_THERMAL=thermal_zone0|cpu-0-0|34000",
                b"KPS_SURVEY_INPUT=event2|goodix_ts",
                b"KPS_SURVEY_GRAPHICS=fb0|msm_drm",
                b"KPS_SURVEY_DRM=card0-DSI-1|connected",
                b"KPS_SURVEY_POWER=battery|Battery|Charging|73",
            ]
        )
    lines.append(b"KPS_SURVEY_END=readonly-hardware-presence-v1")
    if survey_outside:
        lines.append(survey_outside)
    payload = b"\r\n".join(lines) + b"\r\n"
    path.write_bytes(payload)
    return payload


def _observation(
    raw: bytes,
    profile_id: str = "vendor/test",
    probe_id: str = _digest("a"),
) -> PhysicalBootObservationEvidence:
    return PhysicalBootObservationEvidence(
        schema_version=2,
        profile_id=profile_id,
        device_serial="SERIAL-001",
        execution_evidence_sha256=_digest("1"),
        offer_sha256=_digest("2"),
        rescue_candidate_evidence_sha256=_digest("3"),
        rescue_ramdisk_sha256=_digest("4"),
        rescue_probe_id=probe_id,
        transcript_sha256=sha256(raw).hexdigest(),
        transcript_size=len(raw),
        stage_marker_count=1,
        probe_marker_count=1,
        observation_policy="exact-rescue-probe+runtime-preexec-integrity-binding-v2",
        physical_observation_recorded=True,
        temporary_boot_command_succeeded=True,
        rescue_init_observed=True,
        kali_early_userspace_verified=False,
        storage_verified=False,
        display_touch_verified=False,
        charging_battery_verified=False,
        recovery_verified=False,
        manual_review_required=True,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
        runtime_probe_evidence_sha256=_digest("5"),
        authorization_sha256=_digest("6"),
        physical_baseline_bundle_sha256=_digest("7"),
        boot_identity_binding_sha256=_digest("8"),
        recovery_readiness_sha256=_digest("9"),
        recovery_stock_boot_sha256=_digest("b"),
        fresh_fastboot_transcript_sha256=_digest("c"),
        captured_active_slot="a",
        expected_inactive_slot="b",
        post_probe_material_revalidation_required=True,
    )


def _evidence(tmp_path: Path, *, empty_survey: bool = False):
    transcript = tmp_path / "console.log"
    raw = _transcript(transcript, empty_survey=empty_survey)
    observation = _observation(raw)
    profile = _profile(tmp_path)
    diagnostics = record_physical_rescue_diagnostics(profile, observation, transcript)
    evidence = record_physical_hardware_survey(profile, observation, diagnostics, transcript)
    return transcript, observation, diagnostics, evidence


def test_hardware_presence_is_bound_without_functionality_credit(tmp_path: Path) -> None:
    _transcript_path, observation, diagnostics, evidence = _evidence(tmp_path)
    assert evidence.physical_boot_observation_sha256 == observation.evidence_sha256()
    assert evidence.physical_rescue_diagnostics_sha256 == diagnostics.evidence_sha256()
    assert evidence.survey_record_count == 12
    assert evidence.usb_udc_record_count == 1
    assert evidence.usb_device_record_count == 1
    assert evidence.net_record_count == 2
    assert evidence.rfkill_record_count == 2
    assert evidence.sound_record_count == 1
    assert evidence.thermal_record_count == 1
    assert evidence.input_record_count == 1
    assert evidence.graphics_record_count == 1
    assert evidence.drm_record_count == 1
    assert evidence.power_record_count == 1
    assert evidence.usb_signal_observed is True
    assert evidence.network_signal_observed is True
    assert evidence.wifi_signal_observed is True
    assert evidence.bluetooth_signal_observed is True
    assert evidence.audio_signal_observed is True
    assert evidence.thermal_signal_observed is True
    assert evidence.input_signal_observed is True
    assert evidence.display_signal_observed is True
    assert evidence.power_signal_observed is True
    assert evidence.hardware_survey_recorded is True
    assert evidence.manual_review_required is True
    assert evidence.display_verified is False
    assert evidence.touch_verified is False
    assert evidence.usb_verified is False
    assert evidence.wifi_verified is False
    assert evidence.bluetooth_verified is False
    assert evidence.audio_verified is False
    assert evidence.modem_verified is False
    assert evidence.power_charging_verified is False
    assert evidence.thermal_verified is False
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False


def test_empty_but_well_formed_survey_is_recorded_without_signals(tmp_path: Path) -> None:
    _path, _observation_value, _diagnostics, evidence = _evidence(tmp_path, empty_survey=True)
    assert evidence.survey_record_count == 0
    assert evidence.hardware_survey_recorded is True
    assert evidence.usb_signal_observed is False
    assert evidence.wifi_signal_observed is False
    assert evidence.display_signal_observed is False
    assert evidence.hardware_verified is False


def test_transcript_must_match_boot_observation(tmp_path: Path) -> None:
    transcript, observation, diagnostics, _evidence_value = _evidence(tmp_path)
    transcript.write_bytes(transcript.read_bytes() + b"extra\n")
    with pytest.raises(PhysicalHardwareSurveyError, match="not the transcript bound"):
        record_physical_hardware_survey(_profile(tmp_path), observation, diagnostics, transcript)


def test_duplicate_survey_block_is_rejected(tmp_path: Path) -> None:
    transcript = tmp_path / "console.log"
    raw = _transcript(transcript)
    duplicate = raw + (
        b"KPS_SURVEY_BEGIN=readonly-hardware-presence-v1\n"
        b"KPS_SURVEY_NET=lo|772|unknown\n"
        b"KPS_SURVEY_END=readonly-hardware-presence-v1\n"
    )
    transcript.write_bytes(duplicate)
    observation = _observation(duplicate)
    profile = _profile(tmp_path)
    diagnostics = record_physical_rescue_diagnostics(profile, observation, transcript)
    with pytest.raises(PhysicalHardwareSurveyError, match="exactly one survey block"):
        record_physical_hardware_survey(profile, observation, diagnostics, transcript)


def test_survey_marker_outside_block_is_rejected(tmp_path: Path) -> None:
    transcript = tmp_path / "console.log"
    raw = _transcript(transcript, survey_outside=b"KPS_SURVEY_NET=rmnet0|1|down")
    observation = _observation(raw)
    profile = _profile(tmp_path)
    diagnostics = record_physical_rescue_diagnostics(profile, observation, transcript)
    with pytest.raises(PhysicalHardwareSurveyError, match="outside the locked survey block"):
        record_physical_hardware_survey(profile, observation, diagnostics, transcript)


def test_malformed_rfkill_record_is_rejected(tmp_path: Path) -> None:
    transcript = tmp_path / "console.log"
    raw = _transcript(transcript).replace(
        b"KPS_SURVEY_RFKILL=phy0|wlan|1|0|0",
        b"KPS_SURVEY_RFKILL=phy0|wlan",
    )
    transcript.write_bytes(raw)
    observation = _observation(raw)
    profile = _profile(tmp_path)
    diagnostics = record_physical_rescue_diagnostics(profile, observation, transcript)
    with pytest.raises(PhysicalHardwareSurveyError, match="field count drifted"):
        record_physical_hardware_survey(profile, observation, diagnostics, transcript)


def test_diagnostics_must_be_bound_to_same_boot(tmp_path: Path) -> None:
    transcript, observation, diagnostics, _evidence_value = _evidence(tmp_path)
    detached = replace(diagnostics, physical_boot_observation_sha256=_digest("f"))
    with pytest.raises(PhysicalHardwareSurveyError):
        record_physical_hardware_survey(_profile(tmp_path), observation, detached, transcript)


def test_profile_mismatch_is_rejected(tmp_path: Path) -> None:
    transcript, observation, diagnostics, _evidence_value = _evidence(tmp_path)
    with pytest.raises(PhysicalHardwareSurveyError, match="profile does not match"):
        record_physical_hardware_survey(
            _profile(tmp_path, "vendor/other"), observation, diagnostics, transcript
        )


def test_claim_tampering_is_rejected(tmp_path: Path) -> None:
    _path, _observation_value, _diagnostics, evidence = _evidence(tmp_path)
    with pytest.raises(PhysicalHardwareSurveyError, match="unsupported hardware/Beta claim"):
        validate_physical_hardware_survey_evidence(replace(evidence, wifi_verified=True))


def test_evidence_round_trip_and_write_once(tmp_path: Path) -> None:
    _path, _observation_value, _diagnostics, evidence = _evidence(tmp_path)
    out = tmp_path / "hardware-survey.json"
    digest = write_physical_hardware_survey_evidence(evidence, out)
    assert digest == evidence.evidence_sha256()
    assert load_physical_hardware_survey_evidence(out) == evidence
    with pytest.raises(PhysicalHardwareSurveyError, match="overwrite"):
        write_physical_hardware_survey_evidence(evidence, out)


def test_unrelated_non_ascii_console_noise_is_ignored(tmp_path: Path) -> None:
    transcript = tmp_path / "console.log"
    raw = _transcript(transcript) + b"kernel-noise:\xff\xfe\n"
    transcript.write_bytes(raw)
    observation = _observation(raw)
    profile = _profile(tmp_path)
    diagnostics = record_physical_rescue_diagnostics(profile, observation, transcript)
    evidence = record_physical_hardware_survey(profile, observation, diagnostics, transcript)
    assert evidence.survey_record_count == 12
