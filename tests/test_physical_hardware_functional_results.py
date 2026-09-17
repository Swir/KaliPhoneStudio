from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from kaliphonestudio.physical_hardware_test_observation import (
    PhysicalHardwareTestObservationError,
    PhysicalHardwareTestObservationRecord,
    bind_physical_hardware_test_observation,
    load_physical_hardware_test_observation_evidence,
    make_inconclusive_physical_hardware_test_observation_record,
    validate_physical_hardware_test_observation_evidence,
    write_physical_hardware_test_observation_evidence,
)
from kaliphonestudio.physical_hardware_test_plan import PhysicalHardwareTestPlanEvidence
from kaliphonestudio.physical_hardware_test_plan_review import (
    PhysicalHardwareTestPlanReviewRecord,
    bind_physical_hardware_test_plan_review,
)
from kaliphonestudio.physical_hardware_test_review import (
    PhysicalHardwareTestReviewError,
    PhysicalHardwareTestReviewRecord,
    bind_physical_hardware_test_review,
    load_physical_hardware_test_review_evidence,
    make_rejected_physical_hardware_test_review_record,
    validate_physical_hardware_test_review_evidence,
    write_physical_hardware_test_review_evidence,
)
from kaliphonestudio.physical_hardware_test_summary import (
    PhysicalHardwareTestSummaryError,
    build_physical_hardware_test_summary,
    load_physical_hardware_test_summary_evidence,
    validate_physical_hardware_test_summary_evidence,
    write_physical_hardware_test_summary_evidence,
)


def _plan(*, context=True, test_id="display", required_for_beta=True):
    tests = (
        {
            "id": test_id,
            "required_for_beta": required_for_beta,
            "manual_review_required": True,
            "destructive": False,
            "persistent_write_allowed": False,
            "required_context_signals": ["display_signal_observed"] if test_id == "display" else [],
            "context_signals_satisfied": context,
            "required_observations": ["usable physical output is observed on the exact candidate"],
            "status": "pending",
        },
    )
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
        tests=tests,
        test_count=1,
        beta_required_test_count=1 if required_for_beta else 0,
        plan_ready_for_physical_execution=context if required_for_beta else False,
        functional_tests_executed=False,
        functional_hardware_verified=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def _plan_review(plan, *, accepted=True):
    data = plan.canonical_json().encode("utf-8")
    record = PhysicalHardwareTestPlanReviewRecord(
        schema_version=1,
        review_policy="manual-physical-hardware-functional-test-plan-review-v1",
        profile_id=plan.profile_id,
        device_serial=plan.device_serial,
        reviewer="plan-reviewer-1",
        decision="accepted" if accepted else "rejected",
        exact_plan_bytes_reviewed=accepted,
        exact_plan_identity_reviewed=accepted,
        functional_contract_reviewed=accepted,
        beta_required_scope_reviewed=accepted,
        context_readiness_reviewed=accepted,
        no_write_policy_reviewed=accepted,
        limitations_reviewed=accepted,
        functional_tests_executed=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    return bind_physical_hardware_test_plan_review(
        plan,
        record,
        plan_file_sha256=sha256(data).hexdigest(),
        plan_file_size=len(data),
        review_record_sha256="c" * 64,
        review_record_size=384,
        review_notes_sha256="d" * 64,
        review_notes_size=192,
    )


def _observation_record(plan, *, outcome="pass_candidate", satisfied=True, **overrides):
    data = dict(
        schema_version=2,
        observation_policy="manual-physical-hardware-functional-observation-v2",
        profile_id=plan.profile_id,
        device_serial=plan.device_serial,
        test_id=plan.tests[0]["id"],
        operator="operator-1",
        outcome=outcome,
        physical_test_executed=True,
        exact_candidate_identity_confirmed=True,
        physical_device_observed=True,
        required_observation_checks=(
            {"observation": plan.tests[0]["required_observations"][0], "satisfied": satisfied},
        ),
        limitations_recorded=True,
        persistent_write_performed=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    data.update(overrides)
    return PhysicalHardwareTestObservationRecord(**data)


def _observation(plan=None, *, outcome="pass_candidate", satisfied=True, plan_review=None):
    plan = plan or _plan()
    plan_review = plan_review or _plan_review(plan)
    record = _observation_record(plan, outcome=outcome, satisfied=satisfied)
    return bind_physical_hardware_test_observation(
        plan,
        plan_review,
        record,
        observation_record_sha256="8" * 64,
        observation_record_size=512,
        observation_notes_sha256="9" * 64,
        observation_notes_size=256,
    )


def _review_record(observation, *, decision=None, **overrides):
    if decision is None:
        decision = {
            "pass_candidate": "accepted_pass",
            "failed": "accepted_fail",
            "inconclusive": "accepted_inconclusive",
        }[observation.outcome]
    data = dict(
        schema_version=1,
        review_policy="manual-physical-hardware-functional-test-review-v1",
        profile_id=observation.profile_id,
        device_serial=observation.device_serial,
        test_id=observation.test_id,
        reviewer="reviewer-1",
        decision=decision,
        exact_test_plan_reviewed=True,
        exact_observation_evidence_reviewed=True,
        physical_context_reviewed=True,
        required_observations_reviewed=True,
        notes_and_limitations_reviewed=True,
        no_persistent_write_confirmed=True,
        project_support_claim_authorized=False,
        beta_gate_credit=False,
    )
    data.update(overrides)
    return PhysicalHardwareTestReviewRecord(**data)


def _review(observation=None, *, decision=None):
    observation = observation or _observation()
    record = _review_record(observation, decision=decision)
    return bind_physical_hardware_test_review(
        observation,
        record,
        review_record_sha256="a" * 64,
        review_record_size=384,
        review_notes_sha256="b" * 64,
        review_notes_size=192,
    )


def test_observation_binds_exact_accepted_plan_review_and_never_promotes_credit(tmp_path):
    plan = _plan()
    plan_review = _plan_review(plan)
    evidence = _observation(plan, plan_review=plan_review)
    assert evidence.physical_hardware_test_plan_sha256 == plan.evidence_sha256()
    assert evidence.physical_hardware_test_plan_review_sha256 == plan_review.evidence_sha256()
    assert evidence.physical_hardware_test_plan_file_sha256 == plan_review.physical_hardware_test_plan_file_sha256
    assert evidence.physical_hardware_test_plan_review_record_sha256 == plan_review.review_record_sha256
    assert evidence.physical_hardware_test_plan_review_notes_sha256 == plan_review.review_notes_sha256
    assert evidence.plan_review_reviewer == plan_review.reviewer
    assert evidence.plan_review_accepted_for_physical_execution is True
    assert evidence.test_id == "display"
    assert evidence.outcome == "pass_candidate"
    assert evidence.observation_ready_for_manual_review is True
    assert evidence.manual_review_required is True
    assert evidence.functional_test_verified is False
    assert evidence.persistent_write_performed is False
    assert evidence.phone_storage_written is False
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False

    path = tmp_path / "observation.json"
    digest = write_physical_hardware_test_observation_evidence(evidence, path)
    assert digest == evidence.evidence_sha256()
    assert load_physical_hardware_test_observation_evidence(path) == evidence
    with pytest.raises(PhysicalHardwareTestObservationError, match="overwrite"):
        write_physical_hardware_test_observation_evidence(evidence, path)


def test_observation_requires_accepted_exact_plan_review_and_rejects_detached_review():
    plan = _plan()
    rejected = _plan_review(plan, accepted=False)
    with pytest.raises(PhysicalHardwareTestObservationError, match="accepted exact test-plan review"):
        bind_physical_hardware_test_observation(
            plan,
            rejected,
            _observation_record(plan),
            observation_record_sha256="8" * 64,
            observation_record_size=100,
            observation_notes_sha256="9" * 64,
            observation_notes_size=100,
        )

    accepted = _plan_review(plan)
    detached = replace(accepted, physical_hardware_test_plan_sha256="f" * 64)
    with pytest.raises(PhysicalHardwareTestObservationError, match="drifted"):
        bind_physical_hardware_test_observation(
            plan,
            detached,
            _observation_record(plan),
            observation_record_sha256="8" * 64,
            observation_record_size=100,
            observation_notes_sha256="9" * 64,
            observation_notes_size=100,
        )


def test_pass_candidate_requires_every_exact_required_observation():
    plan = _plan()
    plan_review = _plan_review(plan)
    with pytest.raises(PhysicalHardwareTestObservationError, match="pass_candidate"):
        bind_physical_hardware_test_observation(
            plan,
            plan_review,
            _observation_record(plan, satisfied=False),
            observation_record_sha256="8" * 64,
            observation_record_size=100,
            observation_notes_sha256="9" * 64,
            observation_notes_size=100,
        )


def test_observation_rejects_missing_context_identity_drift_and_write_claims():
    blocked = _plan(context=False)
    # A blocked plan cannot obtain accepted-for-physical-execution review evidence.
    blocked_review = _plan_review(blocked, accepted=False)
    with pytest.raises(PhysicalHardwareTestObservationError, match="accepted exact test-plan review"):
        bind_physical_hardware_test_observation(
            blocked,
            blocked_review,
            _observation_record(blocked),
            observation_record_sha256="8" * 64,
            observation_record_size=100,
            observation_notes_sha256="9" * 64,
            observation_notes_size=100,
        )

    plan = _plan()
    plan_review = _plan_review(plan)
    with pytest.raises(PhysicalHardwareTestObservationError, match="identity"):
        bind_physical_hardware_test_observation(
            plan,
            plan_review,
            _observation_record(plan, device_serial="OTHER"),
            observation_record_sha256="8" * 64,
            observation_record_size=100,
            observation_notes_sha256="9" * 64,
            observation_notes_size=100,
        )
    with pytest.raises(PhysicalHardwareTestObservationError, match="persistent writes"):
        bind_physical_hardware_test_observation(
            plan,
            plan_review,
            _observation_record(plan, persistent_write_performed=True),
            observation_record_sha256="8" * 64,
            observation_record_size=100,
            observation_notes_sha256="9" * 64,
            observation_notes_size=100,
        )


def test_observation_validation_rejects_plan_review_or_hardware_or_beta_promotion():
    evidence = _observation()
    with pytest.raises(PhysicalHardwareTestObservationError, match="accepted exact test-plan review"):
        validate_physical_hardware_test_observation_evidence(
            replace(evidence, plan_review_accepted_for_physical_execution=False)
        )
    with pytest.raises(PhysicalHardwareTestObservationError, match="forbidden"):
        validate_physical_hardware_test_observation_evidence(replace(evidence, hardware_verified=True))
    with pytest.raises(PhysicalHardwareTestObservationError, match="forbidden"):
        validate_physical_hardware_test_observation_evidence(replace(evidence, beta_gate_credit=True))


def test_observation_template_requires_accepted_review_and_is_not_bindable_until_edited():
    plan = _plan()
    plan_review = _plan_review(plan)
    record = make_inconclusive_physical_hardware_test_observation_record(
        plan, plan_review, "display", "operator-1"
    )
    assert record.outcome == "inconclusive"
    assert record.physical_test_executed is False
    assert record.exact_candidate_identity_confirmed is False
    assert record.physical_device_observed is False
    assert all(row["satisfied"] is False for row in record.required_observation_checks)
    assert record.hardware_verified is False
    assert record.beta_gate_credit is False
    with pytest.raises(PhysicalHardwareTestObservationError, match="actually executed"):
        bind_physical_hardware_test_observation(
            plan,
            plan_review,
            record,
            observation_record_sha256="8" * 64,
            observation_record_size=100,
            observation_notes_sha256="9" * 64,
            observation_notes_size=100,
        )


def test_manual_review_accepts_exact_pass_as_status_input_but_not_project_support(tmp_path):
    observation = _observation()
    evidence = _review(observation)
    assert evidence.physical_hardware_test_observation_sha256 == observation.evidence_sha256()
    assert evidence.accepted_for_functional_status is True
    assert evidence.reviewed_result == "pass"
    assert evidence.test_passed_review is True
    assert evidence.manual_release_gate_review_required is True
    assert evidence.project_support_claim_authorized is False
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False

    path = tmp_path / "review.json"
    digest = write_physical_hardware_test_review_evidence(evidence, path)
    assert digest == evidence.evidence_sha256()
    assert load_physical_hardware_test_review_evidence(path) == evidence


def test_manual_review_preserves_fail_and_inconclusive_without_promotion():
    failed = _review(_observation(outcome="failed", satisfied=False))
    assert failed.reviewed_result == "fail"
    assert failed.test_passed_review is False
    assert failed.beta_gate_credit is False

    inconclusive = _review(_observation(outcome="inconclusive", satisfied=False))
    assert inconclusive.reviewed_result == "inconclusive"
    assert inconclusive.test_passed_review is False
    assert inconclusive.hardware_verified is False


def test_manual_review_rejects_decision_mismatch_incomplete_checks_and_support_claim():
    observation = _observation()
    with pytest.raises(PhysicalHardwareTestReviewError, match="does not match"):
        bind_physical_hardware_test_review(
            observation,
            _review_record(observation, decision="accepted_fail"),
            review_record_sha256="a" * 64,
            review_record_size=100,
            review_notes_sha256="b" * 64,
            review_notes_size=100,
        )
    with pytest.raises(PhysicalHardwareTestReviewError, match="every exact review check"):
        bind_physical_hardware_test_review(
            observation,
            _review_record(observation, exact_test_plan_reviewed=False),
            review_record_sha256="a" * 64,
            review_record_size=100,
            review_notes_sha256="b" * 64,
            review_notes_size=100,
        )
    with pytest.raises(PhysicalHardwareTestReviewError, match="cannot authorize"):
        bind_physical_hardware_test_review(
            observation,
            _review_record(observation, project_support_claim_authorized=True),
            review_record_sha256="a" * 64,
            review_record_size=100,
            review_notes_sha256="b" * 64,
            review_notes_size=100,
        )


def test_rejected_review_template_defaults_every_check_false():
    observation = _observation()
    record = make_rejected_physical_hardware_test_review_record(observation, "reviewer-1")
    assert record.decision == "rejected"
    assert record.exact_test_plan_reviewed is False
    assert record.exact_observation_evidence_reviewed is False
    assert record.physical_context_reviewed is False
    assert record.required_observations_reviewed is False
    assert record.notes_and_limitations_reviewed is False
    assert record.no_persistent_write_confirmed is False
    assert record.project_support_claim_authorized is False
    assert record.beta_gate_credit is False


def test_review_validation_rejects_project_or_beta_promotion():
    evidence = _review()
    with pytest.raises(PhysicalHardwareTestReviewError, match="forbidden"):
        validate_physical_hardware_test_review_evidence(replace(evidence, project_support_claim_authorized=True))
    with pytest.raises(PhysicalHardwareTestReviewError, match="forbidden"):
        validate_physical_hardware_test_review_evidence(replace(evidence, beta_gate_credit=True))


def test_summary_reports_reviewed_coverage_but_never_promotes_release_credit(tmp_path):
    plan = _plan()
    review = _review(_observation(plan))
    summary = build_physical_hardware_test_summary(plan, [review])
    assert summary.reviewed_test_count == 1
    assert summary.reviewed_pass_count == 1
    assert summary.beta_required_reviewed_pass_count == 1
    assert summary.beta_required_remaining_count == 0
    assert summary.beta_required_tests_all_reviewed_pass is True
    assert summary.tests[0]["status"] == "reviewed_pass"
    assert summary.manual_release_gate_review_required is True
    assert summary.project_support_claim_authorized is False
    assert summary.hardware_verified is False
    assert summary.beta_gate_credit is False

    path = tmp_path / "summary.json"
    digest = write_physical_hardware_test_summary_evidence(summary, path)
    assert digest == summary.evidence_sha256()
    assert load_physical_hardware_test_summary_evidence(path) == summary


def test_summary_keeps_pending_tests_pending_and_rejects_detached_or_duplicate_reviews():
    plan = _plan()
    pending = build_physical_hardware_test_summary(plan, [])
    assert pending.tests[0]["status"] == "pending"
    assert pending.reviewed_test_count == 0
    assert pending.beta_required_remaining_count == 1
    assert pending.beta_required_tests_all_reviewed_pass is False

    review = _review(_observation(plan))
    detached = replace(review, physical_hardware_test_plan_sha256="f" * 64)
    with pytest.raises(PhysicalHardwareTestSummaryError, match="detached"):
        build_physical_hardware_test_summary(plan, [detached])
    with pytest.raises(PhysicalHardwareTestSummaryError, match="duplicate"):
        build_physical_hardware_test_summary(plan, [review, review])


def test_summary_validation_rejects_hardware_or_beta_promotion():
    summary = build_physical_hardware_test_summary(_plan(), [])
    with pytest.raises(PhysicalHardwareTestSummaryError, match="forbidden"):
        validate_physical_hardware_test_summary_evidence(replace(summary, hardware_verified=True))
    with pytest.raises(PhysicalHardwareTestSummaryError, match="forbidden"):
        validate_physical_hardware_test_summary_evidence(replace(summary, beta_gate_credit=True))
