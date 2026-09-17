from dataclasses import replace
from hashlib import sha256

import pytest

from kaliphonestudio.physical_hardware_result_bundle import (
    PhysicalHardwareResultBundleError,
    build_physical_hardware_result_bundle_from_files,
    load_physical_hardware_result_bundle_evidence,
    validate_physical_hardware_result_bundle_evidence,
    write_physical_hardware_result_bundle_evidence,
)
from kaliphonestudio.physical_hardware_test_observation import (
    PhysicalHardwareTestObservationRecord,
    bind_physical_hardware_test_observation,
    write_physical_hardware_test_observation_evidence,
)
from kaliphonestudio.physical_hardware_test_plan import (
    PhysicalHardwareTestPlanEvidence,
    write_physical_hardware_test_plan,
)
from kaliphonestudio.physical_hardware_test_plan_review import (
    PhysicalHardwareTestPlanReviewRecord,
    bind_physical_hardware_test_plan_review,
    write_physical_hardware_test_plan_review_evidence,
)
from kaliphonestudio.physical_hardware_test_review import (
    PhysicalHardwareTestReviewRecord,
    bind_physical_hardware_test_review,
    write_physical_hardware_test_review_evidence,
)
from kaliphonestudio.physical_hardware_test_summary import (
    build_physical_hardware_test_summary,
    write_physical_hardware_test_summary_evidence,
)


def _plan(*, serial="SERIAL-BUNDLE-001"):
    tests = (
        {
            "id": "display",
            "required_for_beta": True,
            "manual_review_required": True,
            "destructive": False,
            "persistent_write_allowed": False,
            "required_context_signals": ["display_signal_observed"],
            "context_signals_satisfied": True,
            "required_observations": ["usable physical output is observed on the exact candidate"],
            "status": "pending",
        },
    )
    return PhysicalHardwareTestPlanEvidence(
        schema_version=1,
        plan_policy="physical-hardware-functional-test-plan-v1",
        profile_id="oneplus/avicii",
        device_serial=serial,
        physical_hardware_review_sha256="1" * 64,
        physical_hardware_survey_sha256="2" * 64,
        physical_boot_observation_sha256="3" * 64,
        physical_rescue_diagnostics_sha256="4" * 64,
        transcript_sha256="5" * 64,
        rescue_probe_id="6" * 64,
        functional_hardware_contract_sha256="7" * 64,
        tests=tests,
        test_count=1,
        beta_required_test_count=1,
        plan_ready_for_physical_execution=True,
        functional_tests_executed=False,
        functional_hardware_verified=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def _plan_review(plan):
    canonical = plan.canonical_json().encode("utf-8")
    record = PhysicalHardwareTestPlanReviewRecord(
        schema_version=1,
        review_policy="manual-physical-hardware-functional-test-plan-review-v1",
        profile_id=plan.profile_id,
        device_serial=plan.device_serial,
        reviewer="plan-reviewer-1",
        decision="accepted",
        exact_plan_bytes_reviewed=True,
        exact_plan_identity_reviewed=True,
        functional_contract_reviewed=True,
        beta_required_scope_reviewed=True,
        context_readiness_reviewed=True,
        no_write_policy_reviewed=True,
        limitations_reviewed=True,
        functional_tests_executed=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    return bind_physical_hardware_test_plan_review(
        plan,
        record,
        plan_file_sha256=sha256(canonical).hexdigest(),
        plan_file_size=len(canonical),
        review_record_sha256="a" * 64,
        review_record_size=384,
        review_notes_sha256="b" * 64,
        review_notes_size=192,
    )


def _observation(plan, plan_review):
    record = PhysicalHardwareTestObservationRecord(
        schema_version=2,
        observation_policy="manual-physical-hardware-functional-observation-v2",
        profile_id=plan.profile_id,
        device_serial=plan.device_serial,
        test_id="display",
        operator="operator-1",
        outcome="pass_candidate",
        physical_test_executed=True,
        exact_candidate_identity_confirmed=True,
        physical_device_observed=True,
        required_observation_checks=(
            {
                "observation": plan.tests[0]["required_observations"][0],
                "satisfied": True,
            },
        ),
        limitations_recorded=True,
        persistent_write_performed=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    return bind_physical_hardware_test_observation(
        plan,
        plan_review,
        record,
        observation_record_sha256="8" * 64,
        observation_record_size=512,
        observation_notes_sha256="9" * 64,
        observation_notes_size=256,
    )


def _result_review(observation):
    record = PhysicalHardwareTestReviewRecord(
        schema_version=1,
        review_policy="manual-physical-hardware-functional-test-review-v1",
        profile_id=observation.profile_id,
        device_serial=observation.device_serial,
        test_id=observation.test_id,
        reviewer="result-reviewer-1",
        decision="accepted_pass",
        exact_test_plan_reviewed=True,
        exact_observation_evidence_reviewed=True,
        physical_context_reviewed=True,
        required_observations_reviewed=True,
        notes_and_limitations_reviewed=True,
        no_persistent_write_confirmed=True,
        project_support_claim_authorized=False,
        beta_gate_credit=False,
    )
    return bind_physical_hardware_test_review(
        observation,
        record,
        review_record_sha256="c" * 64,
        review_record_size=384,
        review_notes_sha256="d" * 64,
        review_notes_size=192,
    )


def _write_exact_set(tmp_path, *, with_observation=True, with_review=True, summary_with_review=True):
    plan = _plan()
    plan_review = _plan_review(plan)
    observation = _observation(plan, plan_review)
    result_review = _result_review(observation)

    plan_path = tmp_path / "plan.json"
    plan_review_path = tmp_path / "plan-review.json"
    observation_path = tmp_path / "observation.json"
    result_review_path = tmp_path / "result-review.json"
    summary_path = tmp_path / "summary.json"

    write_physical_hardware_test_plan(plan, plan_path)
    write_physical_hardware_test_plan_review_evidence(plan_review, plan_review_path)
    if with_observation:
        write_physical_hardware_test_observation_evidence(observation, observation_path)
    if with_review:
        write_physical_hardware_test_review_evidence(result_review, result_review_path)
    summary_reviews = [result_review] if summary_with_review else []
    summary = build_physical_hardware_test_summary(plan, summary_reviews)
    write_physical_hardware_test_summary_evidence(summary, summary_path)
    return {
        "plan": plan,
        "plan_review": plan_review,
        "observation": observation,
        "result_review": result_review,
        "plan_path": plan_path,
        "plan_review_path": plan_review_path,
        "observation_path": observation_path,
        "result_review_path": result_review_path,
        "summary_path": summary_path,
    }


def test_exact_bundle_cross_binds_plan_review_observation_review_and_summary_without_promotion(tmp_path):
    files = _write_exact_set(tmp_path)
    bundle = build_physical_hardware_result_bundle_from_files(
        files["plan_path"],
        files["plan_review_path"],
        [files["observation_path"]],
        [files["result_review_path"]],
        files["summary_path"],
    )
    assert bundle.physical_hardware_test_plan_sha256 == files["plan"].evidence_sha256()
    assert bundle.physical_hardware_test_plan_review_sha256 == files["plan_review"].evidence_sha256()
    assert bundle.observation_count == 1
    assert bundle.result_review_count == 1
    assert bundle.reviewed_pass_count == 1
    assert bundle.beta_required_reviewed_pass_count == 1
    assert bundle.beta_required_remaining_count == 0
    assert bundle.beta_required_tests_all_reviewed_pass is True
    assert bundle.tests[0]["summary_status"] == "reviewed_pass"
    assert bundle.tests[0]["observation_evidence_sha256"] == files["observation"].evidence_sha256()
    assert bundle.tests[0]["result_review_evidence_sha256"] == files["result_review"].evidence_sha256()
    assert bundle.exact_files_verified is True
    assert bundle.manual_release_gate_review_required is True
    assert bundle.project_support_claim_authorized is False
    assert bundle.persistent_write_performed is False
    assert bundle.phone_storage_written is False
    assert bundle.hardware_verified is False
    assert bundle.beta_gate_credit is False

    path = tmp_path / "bundle.json"
    digest = write_physical_hardware_result_bundle_evidence(bundle, path)
    assert digest == bundle.evidence_sha256()
    assert load_physical_hardware_result_bundle_evidence(path) == bundle
    with pytest.raises(PhysicalHardwareResultBundleError, match="overwrite"):
        write_physical_hardware_result_bundle_evidence(bundle, path)


def test_bundle_allows_executed_observation_pending_independent_result_review(tmp_path):
    files = _write_exact_set(tmp_path, with_review=False, summary_with_review=False)
    bundle = build_physical_hardware_result_bundle_from_files(
        files["plan_path"],
        files["plan_review_path"],
        [files["observation_path"]],
        [],
        files["summary_path"],
    )
    assert bundle.observation_count == 1
    assert bundle.result_review_count == 0
    assert bundle.tests[0]["observation_present"] is True
    assert bundle.tests[0]["result_review_present"] is False
    assert bundle.tests[0]["summary_status"] == "pending"
    assert bundle.beta_required_tests_all_reviewed_pass is False
    assert bundle.beta_gate_credit is False


def test_bundle_rejects_accepted_plan_review_from_different_exact_device(tmp_path):
    files = _write_exact_set(tmp_path, with_observation=False, with_review=False, summary_with_review=False)
    other_plan = _plan(serial="OTHER-SERIAL")
    other_review = _plan_review(other_plan)
    other_review_path = tmp_path / "other-plan-review.json"
    write_physical_hardware_test_plan_review_evidence(other_review, other_review_path)
    with pytest.raises(PhysicalHardwareResultBundleError, match="identity"):
        build_physical_hardware_result_bundle_from_files(
            files["plan_path"], other_review_path, [], [], files["summary_path"]
        )


def test_bundle_rejects_duplicate_observation_or_review_ids(tmp_path):
    files = _write_exact_set(tmp_path)
    with pytest.raises(PhysicalHardwareResultBundleError, match="duplicate functional observation"):
        build_physical_hardware_result_bundle_from_files(
            files["plan_path"],
            files["plan_review_path"],
            [files["observation_path"], files["observation_path"]],
            [files["result_review_path"]],
            files["summary_path"],
        )
    with pytest.raises(PhysicalHardwareResultBundleError, match="duplicate functional result-review"):
        build_physical_hardware_result_bundle_from_files(
            files["plan_path"],
            files["plan_review_path"],
            [files["observation_path"]],
            [files["result_review_path"], files["result_review_path"]],
            files["summary_path"],
        )


def test_bundle_rejects_result_review_without_exact_bundled_observation(tmp_path):
    files = _write_exact_set(tmp_path)
    with pytest.raises(PhysicalHardwareResultBundleError, match="no exact bundled observation"):
        build_physical_hardware_result_bundle_from_files(
            files["plan_path"],
            files["plan_review_path"],
            [],
            [files["result_review_path"]],
            files["summary_path"],
        )


def test_bundle_rejects_summary_not_recomputed_from_exact_bundled_reviews(tmp_path):
    files = _write_exact_set(tmp_path, summary_with_review=False)
    with pytest.raises(PhysicalHardwareResultBundleError, match="does not match exact bundled reviews"):
        build_physical_hardware_result_bundle_from_files(
            files["plan_path"],
            files["plan_review_path"],
            [files["observation_path"]],
            [files["result_review_path"]],
            files["summary_path"],
        )


def test_bundle_validation_rejects_hardware_beta_or_write_promotion(tmp_path):
    files = _write_exact_set(tmp_path)
    bundle = build_physical_hardware_result_bundle_from_files(
        files["plan_path"],
        files["plan_review_path"],
        [files["observation_path"]],
        [files["result_review_path"]],
        files["summary_path"],
    )
    for changed in (
        replace(bundle, hardware_verified=True),
        replace(bundle, beta_gate_credit=True),
        replace(bundle, project_support_claim_authorized=True),
        replace(bundle, persistent_write_performed=True),
        replace(bundle, phone_storage_written=True),
    ):
        with pytest.raises(PhysicalHardwareResultBundleError, match="forbidden"):
            validate_physical_hardware_result_bundle_evidence(changed)
