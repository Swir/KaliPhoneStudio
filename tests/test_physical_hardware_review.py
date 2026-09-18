from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import pytest

from kaliphonestudio.physical_boot_observation import PhysicalBootObservationEvidence
from kaliphonestudio.physical_hardware_review import (
    PhysicalHardwareReviewError,
    PhysicalHardwareReviewRecord,
    bind_physical_hardware_review,
    load_physical_hardware_review_evidence,
    load_physical_hardware_review_record,
    make_rejected_hardware_review_record,
    read_physical_hardware_review_notes,
    review_physical_hardware_survey_files,
    validate_physical_hardware_review_evidence,
    write_physical_hardware_review_evidence,
)
from kaliphonestudio.physical_hardware_survey import (
    record_physical_hardware_survey,
    write_physical_hardware_survey_evidence,
)
from kaliphonestudio.physical_rescue_diagnostics import record_physical_rescue_diagnostics
from kaliphonestudio.profiles import DeviceProfile


def _digest(ch: str) -> str:
    return ch * 64


def _profile(tmp_path: Path) -> DeviceProfile:
    return DeviceProfile(path=tmp_path / "profile.json", data={"profile_id": "vendor/test"})


def _transcript(path: Path, *, empty_survey: bool = False) -> bytes:
    probe = _digest("a")
    lines = [
        b"KPS_RESCUE_STAGE=init-reached-v1",
        b"KPS_RESCUE_PROBE_ID=" + probe.encode(),
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
    raw = b"\r\n".join(lines) + b"\r\n"
    path.write_bytes(raw)
    return raw


def _observation(raw: bytes) -> PhysicalBootObservationEvidence:
    return PhysicalBootObservationEvidence(
        schema_version=2,
        profile_id="vendor/test",
        device_serial="SERIAL-001",
        execution_evidence_sha256=_digest("1"),
        offer_sha256=_digest("2"),
        rescue_candidate_evidence_sha256=_digest("3"),
        rescue_ramdisk_sha256=_digest("4"),
        rescue_probe_id=_digest("a"),
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


def _survey(tmp_path: Path, *, empty: bool = False):
    transcript = tmp_path / "console.log"
    raw = _transcript(transcript, empty_survey=empty)
    observation = _observation(raw)
    profile = _profile(tmp_path)
    diagnostics = record_physical_rescue_diagnostics(profile, observation, transcript)
    return record_physical_hardware_survey(profile, observation, diagnostics, transcript)


def _record(survey, **overrides) -> PhysicalHardwareReviewRecord:
    values = dict(
        schema_version=1,
        review_policy="manual-physical-hardware-survey-review-v1",
        profile_id=survey.profile_id,
        device_serial=survey.device_serial,
        reviewer="operator-1",
        decision="accepted_as_context",
        physical_context_reviewed=True,
        survey_integrity_reviewed=True,
        usb_presence_reviewed=True,
        network_radio_presence_reviewed=True,
        audio_presence_reviewed=True,
        input_display_presence_reviewed=True,
        thermal_power_presence_reviewed=True,
        limitations_understood=True,
        functional_hardware_verified=False,
        beta_gate_credit=False,
    )
    values.update(overrides)
    return PhysicalHardwareReviewRecord(**values)


def _bind(survey, record):
    return bind_physical_hardware_review(
        survey,
        record,
        review_record_sha256=_digest("b"),
        review_record_size=200,
        review_notes_sha256=_digest("c"),
        review_notes_size=100,
    )


def test_complete_review_accepts_context_but_never_functionality(tmp_path: Path) -> None:
    survey = _survey(tmp_path)
    evidence = _bind(survey, _record(survey))
    assert evidence.accepted_as_context is True
    assert evidence.review_checks_complete is True
    assert evidence.functional_testing_required is True
    assert evidence.wifi_signal_observed is True
    assert evidence.bluetooth_signal_observed is True
    assert evidence.display_signal_observed is True
    assert evidence.usb_verified is False
    assert evidence.wifi_verified is False
    assert evidence.bluetooth_verified is False
    assert evidence.display_verified is False
    assert evidence.power_charging_verified is False
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False


def test_accepted_review_requires_every_manual_check(tmp_path: Path) -> None:
    survey = _survey(tmp_path)
    with pytest.raises(PhysicalHardwareReviewError, match="every review check"):
        _bind(survey, _record(survey, limitations_understood=False))


def test_empty_survey_cannot_be_accepted_as_context(tmp_path: Path) -> None:
    survey = _survey(tmp_path, empty=True)
    with pytest.raises(PhysicalHardwareReviewError, match="non-empty exact survey"):
        _bind(survey, _record(survey))


def test_rejected_template_is_safe_by_default(tmp_path: Path) -> None:
    survey = _survey(tmp_path)
    record = make_rejected_hardware_review_record(survey, "operator-1")
    assert record.decision == "rejected"
    assert record.physical_context_reviewed is False
    assert record.limitations_understood is False
    assert record.functional_hardware_verified is False
    assert record.beta_gate_credit is False


def test_review_identity_mismatch_fails_closed(tmp_path: Path) -> None:
    survey = _survey(tmp_path)
    with pytest.raises(PhysicalHardwareReviewError, match="identity does not match"):
        _bind(survey, _record(survey, device_serial="OTHER"))


def test_review_record_cannot_claim_functional_credit(tmp_path: Path) -> None:
    survey = _survey(tmp_path)
    raw = json.loads(_record(survey).canonical_json())
    raw["functional_hardware_verified"] = True
    record_path = tmp_path / "review.json"
    record_path.write_text(json.dumps(raw, sort_keys=True, separators=(",", ":")) + "\n")
    with pytest.raises(PhysicalHardwareReviewError, match="cannot grant functional/Beta credit"):
        load_physical_hardware_review_record(record_path)


def test_review_record_must_be_canonical_json(tmp_path: Path) -> None:
    survey = _survey(tmp_path)
    path = tmp_path / "review.json"
    path.write_text(json.dumps(json.loads(_record(survey).canonical_json()), indent=2) + "\n")
    with pytest.raises(PhysicalHardwareReviewError, match="not canonical JSON"):
        load_physical_hardware_review_record(path)


def test_review_notes_must_be_nonempty_utf8(tmp_path: Path) -> None:
    notes = tmp_path / "notes.txt"
    notes.write_text("   \n")
    with pytest.raises(PhysicalHardwareReviewError, match="empty"):
        read_physical_hardware_review_notes(notes)


def test_exact_file_binding_round_trip_and_write_once(tmp_path: Path) -> None:
    survey = _survey(tmp_path)
    survey_path = tmp_path / "survey.json"
    write_physical_hardware_survey_evidence(survey, survey_path)
    record_path = tmp_path / "review.json"
    record_path.write_bytes(_record(survey).canonical_json().encode("utf-8"))
    notes_path = tmp_path / "notes.txt"
    notes_path.write_text("Reviewed as presence-only context. Functional tests remain pending.\n")
    evidence = review_physical_hardware_survey_files(survey_path, record_path, notes_path)
    out = tmp_path / "hardware-review.json"
    digest = write_physical_hardware_review_evidence(evidence, out)
    assert digest == evidence.evidence_sha256()
    assert load_physical_hardware_review_evidence(out) == evidence
    with pytest.raises(PhysicalHardwareReviewError, match="overwrite"):
        write_physical_hardware_review_evidence(evidence, out)


def test_evidence_tampering_cannot_promote_hardware(tmp_path: Path) -> None:
    survey = _survey(tmp_path)
    evidence = _bind(survey, _record(survey))
    with pytest.raises(PhysicalHardwareReviewError, match="unsupported functional/write/hardware/Beta claim"):
        validate_physical_hardware_review_evidence(replace(evidence, wifi_verified=True))
