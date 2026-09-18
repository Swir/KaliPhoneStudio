from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from kaliphonestudio.physical_hardware_review import (
    PhysicalHardwareReviewError,
    PhysicalHardwareReviewRecord,
    load_physical_hardware_review_evidence,
    load_physical_hardware_review_record,
    make_rejected_hardware_review_record,
    read_physical_hardware_review_notes,
    review_physical_hardware_survey,
    review_physical_hardware_survey_files,
    validate_physical_hardware_review_evidence,
    write_physical_hardware_review_evidence,
)
from kaliphonestudio.physical_hardware_survey import (
    PhysicalHardwareSurveyEvidence,
    write_physical_hardware_survey_evidence,
)


def _survey(tmp_path: Path | None = None) -> PhysicalHardwareSurveyEvidence:
    del tmp_path
    return PhysicalHardwareSurveyEvidence(
        schema_version=1,
        profile_id="oneplus/avicii",
        device_serial="SERIAL-HW",
        candidate_id="candidate-physical-hw",
        boot_observation_sha256="1" * 64,
        rescue_diagnostics_sha256="2" * 64,
        rescue_probe_id="probe-hw",
        console_transcript_sha256="3" * 64,
        hardware_survey_marker_id="kaliphonestudio-hardware-survey-v1",
        survey_record_count=8,
        usb_records=("usb_device=1d6b:0002",),
        netdev_records=("netdev=wlan0",),
        rfkill_records=("rfkill=wlan0|wlan|unblocked|unblocked",),
        sound_records=("sound_card=card0|some-codec",),
        input_records=("input_name=touchscreen",),
        display_records=("drm_status=card0-DSI-1|connected|1080x2400",),
        thermal_records=("thermal_zone=thermal_zone0|soc|42000",),
        power_records=("power_supply=battery|Battery|Discharging|77|3890000|250",),
        hardware_survey_recorded=True,
        survey_only=True,
        functional_tests_executed=False,
        display_verified=False,
        touch_verified=False,
        usb_verified=False,
        wifi_verified=False,
        bluetooth_verified=False,
        audio_verified=False,
        modem_verified=False,
        charging_verified=False,
        power_verified=False,
        thermal_verified=False,
        hardware_verified=False,
        beta_gate_credit=False,
        manual_review_required=True,
    )


def _record(survey: PhysicalHardwareSurveyEvidence, **overrides: object) -> PhysicalHardwareReviewRecord:
    data: dict[str, object] = {
        "schema_version": 1,
        "profile_id": survey.profile_id,
        "device_serial": survey.device_serial,
        "candidate_id": survey.candidate_id,
        "hardware_survey_sha256": survey.evidence_sha256(),
        "hardware_survey_marker_id": survey.hardware_survey_marker_id,
        "boot_observation_sha256": survey.boot_observation_sha256,
        "rescue_diagnostics_sha256": survey.rescue_diagnostics_sha256,
        "rescue_probe_id": survey.rescue_probe_id,
        "console_transcript_sha256": survey.console_transcript_sha256,
        "review_policy": "manual-physical-hardware-survey-review-v1",
        "reviewer": "reviewer-1",
        "decision": "accepted",
        "physical_context_reviewed": True,
        "survey_integrity_reviewed": True,
        "usb_context_reviewed": True,
        "network_radio_context_reviewed": True,
        "audio_context_reviewed": True,
        "input_display_context_reviewed": True,
        "thermal_power_context_reviewed": True,
        "limitations_acknowledged": True,
        "accepted_as_context": True,
        "functional_tests_executed": False,
        "display_verified": False,
        "touch_verified": False,
        "usb_verified": False,
        "wifi_verified": False,
        "bluetooth_verified": False,
        "audio_verified": False,
        "modem_verified": False,
        "charging_verified": False,
        "power_verified": False,
        "thermal_verified": False,
        "hardware_verified": False,
        "beta_gate_credit": False,
    }
    data.update(overrides)
    return PhysicalHardwareReviewRecord(**data)


def _bind(
    survey: PhysicalHardwareSurveyEvidence,
    record: PhysicalHardwareReviewRecord,
    *,
    notes: bytes = b"Reviewed as presence-only context. Functional tests remain pending.\n",
):
    return review_physical_hardware_survey(survey, record, notes, review_notes_name="notes.txt")


def test_rejected_template_is_fail_closed_and_profile_bound() -> None:
    survey = _survey()
    record = make_rejected_hardware_review_record(survey, "reviewer-1")
    assert record.profile_id == survey.profile_id
    assert record.device_serial == survey.device_serial
    assert record.candidate_id == survey.candidate_id
    assert record.hardware_survey_sha256 == survey.evidence_sha256()
    assert record.decision == "rejected"
    assert record.accepted_as_context is False
    assert record.functional_tests_executed is False
    assert record.hardware_verified is False
    assert record.beta_gate_credit is False
    assert all(
        value is False
        for value in (
            record.physical_context_reviewed,
            record.survey_integrity_reviewed,
            record.usb_context_reviewed,
            record.network_radio_context_reviewed,
            record.audio_context_reviewed,
            record.input_display_context_reviewed,
            record.thermal_power_context_reviewed,
            record.limitations_acknowledged,
        )
    )


def test_accepted_review_requires_every_context_check() -> None:
    survey = _survey()
    record = _record(survey, thermal_power_context_reviewed=False)
    with pytest.raises(PhysicalHardwareReviewError, match="all context checks"):
        _bind(survey, record)


def test_acceptance_cannot_claim_functional_or_beta_credit() -> None:
    survey = _survey()
    with pytest.raises(PhysicalHardwareReviewError, match="cannot grant functional/Beta credit"):
        _bind(survey, _record(survey, wifi_verified=True))
    with pytest.raises(PhysicalHardwareReviewError, match="cannot grant functional/Beta credit"):
        _bind(survey, _record(survey, hardware_verified=True))
    with pytest.raises(PhysicalHardwareReviewError, match="cannot grant functional/Beta credit"):
        _bind(survey, _record(survey, beta_gate_credit=True))


def test_rejected_review_cannot_be_context_ready() -> None:
    survey = _survey()
    record = _record(survey, decision="rejected", accepted_as_context=True)
    with pytest.raises(PhysicalHardwareReviewError, match="rejected reviews cannot be accepted as context"):
        _bind(survey, record)


def test_review_must_match_exact_survey_identity() -> None:
    survey = _survey()
    with pytest.raises(PhysicalHardwareReviewError, match="survey digest"):
        _bind(survey, _record(survey, hardware_survey_sha256="9" * 64))
    with pytest.raises(PhysicalHardwareReviewError, match="profile/device identity"):
        _bind(survey, _record(survey, device_serial="OTHER"))
    with pytest.raises(PhysicalHardwareReviewError, match="candidate identity"):
        _bind(survey, _record(survey, candidate_id="other-candidate"))


def test_review_record_parser_rejects_unknown_fields(tmp_path: Path) -> None:
    survey = _survey(tmp_path)
    path = tmp_path / "review.json"
    raw = json.loads(_record(survey).canonical_json())
    raw["unexpected"] = True
    path.write_text(json.dumps(raw, sort_keys=True, separators=(",", ":")) + "\n")
    with pytest.raises(PhysicalHardwareReviewError, match="unexpected fields"):
        load_physical_hardware_review_record(path)


def test_review_record_parser_rejects_wrong_boolean_types(tmp_path: Path) -> None:
    survey = _survey(tmp_path)
    path = tmp_path / "review.json"
    raw = json.loads(_record(survey).canonical_json())
    raw["wifi_verified"] = 0
    path.write_text(json.dumps(raw, sort_keys=True, separators=(",", ":")) + "\n")
    with pytest.raises(PhysicalHardwareReviewError, match="wifi_verified must be a boolean"):
        load_physical_hardware_review_record(path)


def test_review_record_parser_rejects_functional_claims_before_binding(tmp_path: Path) -> None:
    survey = _survey(tmp_path)
    path = tmp_path / "review.json"
    raw = json.loads(_record(survey).canonical_json())
    raw["wifi_verified"] = True
    path.write_text(json.dumps(raw, sort_keys=True, separators=(",", ":")) + "\n")
    with pytest.raises(PhysicalHardwareReviewError, match="cannot grant functional/Beta credit"):
        load_physical_hardware_review_record(path)


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
