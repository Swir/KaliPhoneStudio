from dataclasses import replace
from pathlib import Path

import pytest

from kaliphonestudio.physical_hardware_review import PhysicalHardwareReviewEvidence
from kaliphonestudio.physical_hardware_test_plan import (
    PhysicalHardwareTestPlanError,
    build_physical_hardware_test_plan,
    load_physical_hardware_test_plan,
    write_physical_hardware_test_plan,
)
from kaliphonestudio.profiles import load_profile

ROOT = Path(__file__).resolve().parents[1]
PROFILE = load_profile(ROOT / "devices" / "oneplus" / "avicii" / "profile.json")


def _review(**overrides):
    data = dict(
        schema_version=1,
        review_policy="manual-physical-hardware-survey-review-v1",
        profile_id="oneplus/avicii",
        device_serial="SERIAL-TEST-001",
        physical_hardware_survey_sha256="1" * 64,
        physical_boot_observation_sha256="2" * 64,
        physical_rescue_diagnostics_sha256="3" * 64,
        transcript_sha256="4" * 64,
        rescue_probe_id="5" * 64,
        normalized_survey_sha256="6" * 64,
        survey_record_count=9,
        review_record_sha256="7" * 64,
        review_record_size=512,
        review_notes_sha256="8" * 64,
        review_notes_size=128,
        reviewer="test-reviewer",
        decision="accepted_as_context",
        physical_context_reviewed=True,
        survey_integrity_reviewed=True,
        usb_presence_reviewed=True,
        network_radio_presence_reviewed=True,
        audio_presence_reviewed=True,
        input_display_presence_reviewed=True,
        thermal_power_presence_reviewed=True,
        limitations_understood=True,
        review_checks_complete=True,
        review_recorded=True,
        accepted_as_context=True,
        functional_testing_required=True,
        usb_signal_observed=True,
        network_signal_observed=True,
        wifi_signal_observed=True,
        bluetooth_signal_observed=True,
        audio_signal_observed=True,
        thermal_signal_observed=True,
        input_signal_observed=True,
        display_signal_observed=True,
        power_signal_observed=True,
        display_verified=False,
        touch_verified=False,
        usb_verified=False,
        wifi_verified=False,
        bluetooth_verified=False,
        audio_verified=False,
        modem_verified=False,
        power_charging_verified=False,
        thermal_verified=False,
        storage_verified=False,
        recovery_verified=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    data.update(overrides)
    return PhysicalHardwareReviewEvidence(**data)


def test_plan_binds_exact_review_and_keeps_every_test_pending_without_credit(tmp_path):
    review = _review()
    plan = build_physical_hardware_test_plan(PROFILE, review)
    assert plan.profile_id == "oneplus/avicii"
    assert plan.device_serial == review.device_serial
    assert plan.physical_hardware_review_sha256 == review.evidence_sha256()
    assert plan.test_count == len(plan.tests)
    assert plan.beta_required_test_count > 0
    assert all(item["status"] == "pending" for item in plan.tests)
    assert all(item["manual_review_required"] is True for item in plan.tests)
    assert all(item["destructive"] is False and item["persistent_write_allowed"] is False for item in plan.tests)
    assert plan.functional_tests_executed is False
    assert plan.functional_hardware_verified is False
    assert plan.phone_storage_written is False
    assert plan.hardware_verified is False
    assert plan.beta_gate_credit is False

    path = tmp_path / "plan.json"
    digest = write_physical_hardware_test_plan(plan, path)
    loaded = load_physical_hardware_test_plan(path)
    assert loaded == plan
    assert digest == plan.evidence_sha256()
    with pytest.raises(PhysicalHardwareTestPlanError, match="overwrite"):
        write_physical_hardware_test_plan(plan, path)


def test_plan_rejects_unaccepted_review_and_profile_drift():
    review = _review(decision="rejected", accepted_as_context=False)
    with pytest.raises(PhysicalHardwareTestPlanError, match="accepted exact"):
        build_physical_hardware_test_plan(PROFILE, review)

    review = _review(profile_id="other/device")
    with pytest.raises(PhysicalHardwareTestPlanError, match="profile does not match"):
        build_physical_hardware_test_plan(PROFILE, review)


def test_plan_validation_rejects_execution_or_beta_promotion():
    plan = build_physical_hardware_test_plan(PROFILE, _review())
    with pytest.raises(PhysicalHardwareTestPlanError, match="unsupported execution"):
        from kaliphonestudio.physical_hardware_test_plan import validate_physical_hardware_test_plan
        validate_physical_hardware_test_plan(replace(plan, functional_tests_executed=True))
    with pytest.raises(PhysicalHardwareTestPlanError, match="unsupported execution"):
        validate_physical_hardware_test_plan(replace(plan, beta_gate_credit=True))
