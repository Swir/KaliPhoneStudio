from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from kaliphonestudio.physical_hardware_test_plan import (
    PhysicalHardwareTestPlanEvidence,
    write_physical_hardware_test_plan,
)
from kaliphonestudio.physical_hardware_test_plan_review import (
    PhysicalHardwareTestPlanReviewError,
    bind_physical_hardware_test_plan_review_from_files,
    load_physical_hardware_test_plan_review_evidence,
    make_rejected_physical_hardware_test_plan_review_record,
    write_physical_hardware_test_plan_review_evidence,
)


def _plan(*, context_ready: bool = True) -> PhysicalHardwareTestPlanEvidence:
    return PhysicalHardwareTestPlanEvidence(
        schema_version=1,
        plan_policy="physical-hardware-functional-test-plan-v1",
        profile_id="oneplus/avicii",
        device_serial="SERIAL-TEST-001",
        physical_hardware_review_sha256="1" * 64,
        physical_hardware_survey_sha256="2" * 64,
        physical_boot_observation_sha256="3" * 64,
        physical_rescue_diagnostics_sha256="4" * 64,
        transcript_sha256="5" * 64,
        rescue_probe_id="6" * 64,
        functional_hardware_contract_sha256="7" * 64,
        tests=(
            {
                "id": "display",
                "required_for_beta": True,
                "manual_review_required": True,
                "destructive": False,
                "persistent_write_allowed": False,
                "required_context_signals": ["input_display_context_reviewed"],
                "context_signals_satisfied": context_ready,
                "required_observations": ["framebuffer_or_drm_output_visible"],
                "status": "pending",
            },
        ),
        test_count=1,
        beta_required_test_count=1,
        plan_ready_for_physical_execution=context_ready,
        functional_tests_executed=False,
        functional_hardware_verified=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def _accepted_record(plan: PhysicalHardwareTestPlanEvidence):
    base = make_rejected_physical_hardware_test_plan_review_record(plan, "reviewer-1")
    return replace(
        base,
        decision="accepted",
        exact_plan_bytes_reviewed=True,
        exact_plan_identity_reviewed=True,
        functional_contract_reviewed=True,
        beta_required_scope_reviewed=True,
        context_readiness_reviewed=True,
        no_write_policy_reviewed=True,
        limitations_reviewed=True,
    )


def _write_inputs(tmp_path: Path, *, context_ready: bool = True):
    plan = _plan(context_ready=context_ready)
    plan_path = tmp_path / "plan.json"
    write_physical_hardware_test_plan(plan, plan_path)
    record = _accepted_record(plan)
    record_path = tmp_path / "review-record.json"
    record_path.write_text(record.canonical_json(), encoding="utf-8", newline="\n")
    notes_path = tmp_path / "review-notes.txt"
    notes_path.write_text("Reviewed exact plan bytes and safety limitations.\n", encoding="utf-8")
    return plan, plan_path, record_path, notes_path


def test_exact_ready_plan_can_be_accepted_without_promoting_hardware_or_beta(tmp_path: Path):
    plan, plan_path, record_path, notes_path = _write_inputs(tmp_path)
    evidence = bind_physical_hardware_test_plan_review_from_files(plan_path, record_path, notes_path)

    assert evidence.physical_hardware_test_plan_sha256 == plan.evidence_sha256()
    assert evidence.physical_hardware_test_plan_file_sha256 == plan.evidence_sha256()
    assert evidence.accepted_for_physical_execution is True
    assert evidence.manual_test_execution_required is True
    assert evidence.functional_tests_executed is False
    assert evidence.functional_hardware_verified is False
    assert evidence.phone_storage_written is False
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False


def test_rejected_template_is_fail_closed():
    plan = _plan()
    record = make_rejected_physical_hardware_test_plan_review_record(plan, "reviewer-1")
    assert record.decision == "rejected"
    assert record.exact_plan_bytes_reviewed is False
    assert record.context_readiness_reviewed is False
    assert record.functional_tests_executed is False
    assert record.phone_storage_written is False
    assert record.hardware_verified is False
    assert record.beta_gate_credit is False


def test_accepted_record_requires_every_review_check(tmp_path: Path):
    plan, plan_path, _, notes_path = _write_inputs(tmp_path)
    record = replace(_accepted_record(plan), no_write_policy_reviewed=False)
    record_path = tmp_path / "incomplete-record.json"
    record_path.write_text(record.canonical_json(), encoding="utf-8", newline="\n")

    with pytest.raises(PhysicalHardwareTestPlanReviewError):
        bind_physical_hardware_test_plan_review_from_files(plan_path, record_path, notes_path)


def test_not_ready_plan_cannot_be_accepted_for_execution(tmp_path: Path):
    plan, plan_path, record_path, notes_path = _write_inputs(tmp_path, context_ready=False)
    evidence = bind_physical_hardware_test_plan_review_from_files(plan_path, record_path, notes_path)

    assert plan.plan_ready_for_physical_execution is False
    assert evidence.decision == "accepted"
    assert evidence.accepted_for_physical_execution is False
    assert evidence.beta_gate_credit is False


def test_review_identity_must_match_exact_plan(tmp_path: Path):
    plan, plan_path, _, notes_path = _write_inputs(tmp_path)
    record = replace(_accepted_record(plan), device_serial="OTHER-SERIAL")
    record_path = tmp_path / "wrong-device-record.json"
    record_path.write_text(record.canonical_json(), encoding="utf-8", newline="\n")

    with pytest.raises(PhysicalHardwareTestPlanReviewError, match="identity"):
        bind_physical_hardware_test_plan_review_from_files(plan_path, record_path, notes_path)


def test_noncanonical_plan_bytes_are_rejected(tmp_path: Path):
    plan = _plan()
    plan_path = tmp_path / "pretty-plan.json"
    plan_path.write_text(json.dumps(json.loads(plan.canonical_json()), indent=2) + "\n", encoding="utf-8")
    record = _accepted_record(plan)
    record_path = tmp_path / "review-record.json"
    record_path.write_text(record.canonical_json(), encoding="utf-8", newline="\n")
    notes_path = tmp_path / "notes.txt"
    notes_path.write_text("Reviewed.\n", encoding="utf-8")

    with pytest.raises(PhysicalHardwareTestPlanReviewError):
        bind_physical_hardware_test_plan_review_from_files(plan_path, record_path, notes_path)


def test_noncanonical_review_record_is_rejected(tmp_path: Path):
    plan, plan_path, _, notes_path = _write_inputs(tmp_path)
    record = _accepted_record(plan)
    record_path = tmp_path / "pretty-record.json"
    record_path.write_text(json.dumps(json.loads(record.canonical_json()), indent=2) + "\n", encoding="utf-8")

    with pytest.raises(PhysicalHardwareTestPlanReviewError, match="canonical"):
        bind_physical_hardware_test_plan_review_from_files(plan_path, record_path, notes_path)


@pytest.mark.parametrize("notes", ["", "   \n", "bad\x00notes\n"])
def test_review_notes_must_be_nonempty_utf8_without_nul(tmp_path: Path, notes: str):
    _, plan_path, record_path, notes_path = _write_inputs(tmp_path)
    notes_path.write_text(notes, encoding="utf-8")

    with pytest.raises(PhysicalHardwareTestPlanReviewError):
        bind_physical_hardware_test_plan_review_from_files(plan_path, record_path, notes_path)


def test_review_evidence_round_trip_and_immutable_write(tmp_path: Path):
    _, plan_path, record_path, notes_path = _write_inputs(tmp_path)
    evidence = bind_physical_hardware_test_plan_review_from_files(plan_path, record_path, notes_path)
    out = tmp_path / "review-evidence.json"
    digest = write_physical_hardware_test_plan_review_evidence(evidence, out)

    loaded = load_physical_hardware_test_plan_review_evidence(out)
    assert loaded == evidence
    assert digest == evidence.evidence_sha256()

    with pytest.raises(PhysicalHardwareTestPlanReviewError, match="overwrite"):
        write_physical_hardware_test_plan_review_evidence(evidence, out)


def test_review_evidence_rejects_forbidden_promotion(tmp_path: Path):
    _, plan_path, record_path, notes_path = _write_inputs(tmp_path)
    evidence = bind_physical_hardware_test_plan_review_from_files(plan_path, record_path, notes_path)
    unsafe = replace(evidence, beta_gate_credit=True)
    out = tmp_path / "unsafe.json"
    out.write_text(unsafe.canonical_json(), encoding="utf-8", newline="\n")

    with pytest.raises(PhysicalHardwareTestPlanReviewError):
        load_physical_hardware_test_plan_review_evidence(out)
