"""Exact-file audit bundle for one physical functional-hardware test campaign.

The bundle closes the host-side audit chain around the exact canonical test plan,
its independently accepted plan review, schema-v2 physical observations,
independent result reviews and the deterministic aggregate summary. It performs
no phone I/O, authorizes no storage write and never grants hardware or Beta
release credit. A complete bundle is only an input to a later manual release-
gate review.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable

from .physical_boot_observation import PhysicalBootObservationEvidence
from .physical_campaign_admission import (
    PhysicalCampaignAdmissionError,
    require_current_physical_campaign_observation,
)
from .physical_hardware_test_observation import (
    PhysicalHardwareTestObservationError,
    PhysicalHardwareTestObservationEvidence,
    load_physical_hardware_test_observation_evidence,
    validate_physical_hardware_test_observation_evidence,
)
from .physical_hardware_test_plan import (
    PhysicalHardwareTestPlanError,
    PhysicalHardwareTestPlanEvidence,
    load_physical_hardware_test_plan,
    validate_physical_hardware_test_plan,
)
from .physical_hardware_test_plan_review import (
    PhysicalHardwareTestPlanReviewError,
    PhysicalHardwareTestPlanReviewEvidence,
    load_physical_hardware_test_plan_review_evidence,
    validate_physical_hardware_test_plan_review_evidence,
)
from .physical_hardware_test_review import (
    PhysicalHardwareTestReviewError,
    PhysicalHardwareTestReviewEvidence,
    load_physical_hardware_test_review_evidence,
    validate_physical_hardware_test_review_evidence,
)
from .physical_hardware_test_summary import (
    PhysicalHardwareTestSummaryError,
    PhysicalHardwareTestSummaryEvidence,
    build_physical_hardware_test_summary,
    load_physical_hardware_test_summary_evidence,
    validate_physical_hardware_test_summary_evidence,
)

_BUNDLE_POLICY = "physical-hardware-functional-result-bundle-v1"
_MAX_FILE_BYTES = 8 * 1024 * 1024
_MAX_BUNDLE_BYTES = 16 * 1024 * 1024
_ALLOWED_SUMMARY_STATUSES = frozenset(
    {"pending", "reviewed_pass", "reviewed_fail", "reviewed_inconclusive", "rejected"}
)


class PhysicalHardwareResultBundleError(ValueError):
    pass


@dataclass(frozen=True)
class PhysicalHardwareResultBundleEvidence:
    schema_version: int
    bundle_policy: str
    profile_id: str
    device_serial: str
    physical_hardware_test_plan_sha256: str
    physical_hardware_test_plan_file_sha256: str
    physical_hardware_test_plan_file_size: int
    physical_hardware_test_plan_review_sha256: str
    physical_hardware_test_plan_review_file_sha256: str
    physical_hardware_test_plan_review_file_size: int
    plan_review_reviewer: str
    plan_review_accepted_for_physical_execution: bool
    functional_hardware_contract_sha256: str
    tests: tuple[dict[str, Any], ...]
    test_count: int
    observation_count: int
    result_review_count: int
    reviewed_test_count: int
    reviewed_pass_count: int
    beta_required_test_count: int
    beta_required_reviewed_pass_count: int
    beta_required_remaining_count: int
    beta_required_tests_all_reviewed_pass: bool
    physical_hardware_test_summary_sha256: str
    physical_hardware_test_summary_file_sha256: str
    physical_hardware_test_summary_file_size: int
    exact_files_verified: bool
    manual_release_gate_review_required: bool
    project_support_claim_authorized: bool
    persistent_write_performed: bool
    phone_storage_written: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise PhysicalHardwareResultBundleError(f"{label} must be a lowercase SHA-256")
    return value


def _nonnegative(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise PhysicalHardwareResultBundleError(f"{label} must be a non-negative integer")
    return value


def _positive(value: object, label: str) -> int:
    value = _nonnegative(value, label)
    if value == 0:
        raise PhysicalHardwareResultBundleError(f"{label} must be a positive integer")
    return value


def _safe_identity(value: object, label: str, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise PhysicalHardwareResultBundleError(f"{label} must be non-empty bounded text")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise PhysicalHardwareResultBundleError(f"{label} contains control data")
    return value


def _read_exact(path: Path, label: str, maximum: int = _MAX_FILE_BYTES) -> tuple[bytes, str, int]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalHardwareResultBundleError(f"{label} must be a regular non-symlink file")
    try:
        before = source.stat()
        raw = source.read_bytes()
        after = source.stat()
    except OSError as exc:
        raise PhysicalHardwareResultBundleError(f"cannot read {label}: {exc}") from exc
    if before.st_size <= 0 or before.st_size > maximum or len(raw) != before.st_size:
        raise PhysicalHardwareResultBundleError(f"{label} size is outside the safety limit")
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise PhysicalHardwareResultBundleError(f"{label} changed while being read")
    return raw, sha256(raw).hexdigest(), len(raw)


def _require_canonical_file(raw: bytes, canonical_json: str, digest: str, label: str) -> None:
    canonical = canonical_json.encode("utf-8")
    if raw != canonical:
        raise PhysicalHardwareResultBundleError(f"{label} is not the exact canonical evidence bytes")
    if digest != sha256(canonical).hexdigest():
        raise PhysicalHardwareResultBundleError(f"{label} digest drifted while being verified")


def _validate_exact_plan_review(
    plan: PhysicalHardwareTestPlanEvidence,
    review: PhysicalHardwareTestPlanReviewEvidence,
) -> None:
    try:
        validate_physical_hardware_test_plan(plan)
        validate_physical_hardware_test_plan_review_evidence(review)
    except (PhysicalHardwareTestPlanError, PhysicalHardwareTestPlanReviewError) as exc:
        raise PhysicalHardwareResultBundleError(str(exc)) from exc
    if review.accepted_for_physical_execution is not True or review.decision != "accepted":
        raise PhysicalHardwareResultBundleError("result bundle requires an accepted exact test-plan review")
    if review.plan_ready_for_physical_execution is not True or review.manual_test_execution_required is not True:
        raise PhysicalHardwareResultBundleError("accepted exact test-plan review is not ready for manual execution")
    if review.profile_id != plan.profile_id or review.device_serial != plan.device_serial:
        raise PhysicalHardwareResultBundleError("exact test-plan review identity does not match the plan")

    canonical = plan.canonical_json().encode("utf-8")
    expected = {
        "physical_hardware_test_plan_sha256": plan.evidence_sha256(),
        "physical_hardware_test_plan_file_sha256": sha256(canonical).hexdigest(),
        "physical_hardware_review_sha256": plan.physical_hardware_review_sha256,
        "physical_hardware_survey_sha256": plan.physical_hardware_survey_sha256,
        "physical_boot_observation_sha256": plan.physical_boot_observation_sha256,
        "physical_rescue_diagnostics_sha256": plan.physical_rescue_diagnostics_sha256,
        "transcript_sha256": plan.transcript_sha256,
        "rescue_probe_id": plan.rescue_probe_id,
        "functional_hardware_contract_sha256": plan.functional_hardware_contract_sha256,
    }
    for name, value in expected.items():
        if getattr(review, name) != value:
            raise PhysicalHardwareResultBundleError(f"accepted exact test-plan review drifted: {name}")
    if review.physical_hardware_test_plan_file_size != len(canonical):
        raise PhysicalHardwareResultBundleError("accepted exact test-plan review file size drifted")
    if review.test_count != plan.test_count or review.beta_required_test_count != plan.beta_required_test_count:
        raise PhysicalHardwareResultBundleError("accepted exact test-plan review counters drifted")


def _validate_observation_against_plan_review(
    plan: PhysicalHardwareTestPlanEvidence,
    plan_review: PhysicalHardwareTestPlanReviewEvidence,
    observation: PhysicalHardwareTestObservationEvidence,
) -> None:
    try:
        validate_physical_hardware_test_observation_evidence(observation)
    except PhysicalHardwareTestObservationError as exc:
        raise PhysicalHardwareResultBundleError(str(exc)) from exc
    if observation.profile_id != plan.profile_id or observation.device_serial != plan.device_serial:
        raise PhysicalHardwareResultBundleError("functional observation identity does not match exact plan")
    if observation.physical_hardware_test_plan_sha256 != plan.evidence_sha256():
        raise PhysicalHardwareResultBundleError("functional observation is detached from exact plan")
    expected = {
        "physical_hardware_test_plan_review_sha256": plan_review.evidence_sha256(),
        "physical_hardware_test_plan_file_sha256": plan_review.physical_hardware_test_plan_file_sha256,
        "physical_hardware_test_plan_review_record_sha256": plan_review.review_record_sha256,
        "physical_hardware_test_plan_review_notes_sha256": plan_review.review_notes_sha256,
        "plan_review_reviewer": plan_review.reviewer,
        "functional_hardware_contract_sha256": plan.functional_hardware_contract_sha256,
        "physical_hardware_review_sha256": plan.physical_hardware_review_sha256,
        "physical_hardware_survey_sha256": plan.physical_hardware_survey_sha256,
        "physical_boot_observation_sha256": plan.physical_boot_observation_sha256,
        "physical_rescue_diagnostics_sha256": plan.physical_rescue_diagnostics_sha256,
        "transcript_sha256": plan.transcript_sha256,
        "rescue_probe_id": plan.rescue_probe_id,
    }
    for name, value in expected.items():
        if getattr(observation, name) != value:
            raise PhysicalHardwareResultBundleError(f"functional observation drifted from accepted plan review: {name}")
    if observation.plan_review_accepted_for_physical_execution is not True:
        raise PhysicalHardwareResultBundleError("functional observation lacks accepted exact-plan review state")


def _validate_result_review_against_observation(
    plan: PhysicalHardwareTestPlanEvidence,
    observation: PhysicalHardwareTestObservationEvidence,
    review: PhysicalHardwareTestReviewEvidence,
) -> None:
    try:
        validate_physical_hardware_test_review_evidence(review)
    except PhysicalHardwareTestReviewError as exc:
        raise PhysicalHardwareResultBundleError(str(exc)) from exc
    if review.profile_id != plan.profile_id or review.device_serial != plan.device_serial:
        raise PhysicalHardwareResultBundleError("functional result review identity does not match exact plan")
    if review.test_id != observation.test_id:
        raise PhysicalHardwareResultBundleError("functional result review test id does not match observation")
    expected = {
        "physical_hardware_test_plan_sha256": plan.evidence_sha256(),
        "physical_hardware_test_observation_sha256": observation.evidence_sha256(),
        "physical_hardware_review_sha256": observation.physical_hardware_review_sha256,
        "physical_hardware_survey_sha256": observation.physical_hardware_survey_sha256,
        "physical_boot_observation_sha256": observation.physical_boot_observation_sha256,
        "physical_rescue_diagnostics_sha256": observation.physical_rescue_diagnostics_sha256,
        "transcript_sha256": observation.transcript_sha256,
        "rescue_probe_id": observation.rescue_probe_id,
        "functional_hardware_contract_sha256": observation.functional_hardware_contract_sha256,
        "required_for_beta": observation.required_for_beta,
        "observation_outcome": observation.outcome,
    }
    for name, value in expected.items():
        if getattr(review, name) != value:
            raise PhysicalHardwareResultBundleError(f"functional result review drifted from exact observation: {name}")


def build_physical_hardware_result_bundle_from_files(
    plan_path: Path,
    plan_review_path: Path,
    observation_paths: Iterable[Path],
    result_review_paths: Iterable[Path],
    summary_path: Path,
) -> PhysicalHardwareResultBundleEvidence:
    try:
        plan_raw, plan_file_sha, plan_file_size = _read_exact(Path(plan_path), "physical hardware test plan")
        plan = load_physical_hardware_test_plan(Path(plan_path))
        plan_review_raw, plan_review_file_sha, plan_review_file_size = _read_exact(
            Path(plan_review_path), "physical hardware test-plan review evidence"
        )
        plan_review = load_physical_hardware_test_plan_review_evidence(Path(plan_review_path))
    except (PhysicalHardwareTestPlanError, PhysicalHardwareTestPlanReviewError) as exc:
        raise PhysicalHardwareResultBundleError(str(exc)) from exc
    _require_canonical_file(plan_raw, plan.canonical_json(), plan_file_sha, "physical hardware test plan")
    _require_canonical_file(
        plan_review_raw,
        plan_review.canonical_json(),
        plan_review_file_sha,
        "physical hardware test-plan review evidence",
    )
    _validate_exact_plan_review(plan, plan_review)
    if plan_file_sha != plan_review.physical_hardware_test_plan_file_sha256:
        raise PhysicalHardwareResultBundleError("exact plan file does not match accepted plan-review file identity")

    observation_by_test: dict[str, tuple[PhysicalHardwareTestObservationEvidence, str, int]] = {}
    for path in observation_paths:
        try:
            raw, file_sha, file_size = _read_exact(Path(path), "functional observation evidence")
            observation = load_physical_hardware_test_observation_evidence(Path(path))
        except PhysicalHardwareTestObservationError as exc:
            raise PhysicalHardwareResultBundleError(str(exc)) from exc
        _require_canonical_file(raw, observation.canonical_json(), file_sha, "functional observation evidence")
        _validate_observation_against_plan_review(plan, plan_review, observation)
        if observation.test_id in observation_by_test:
            raise PhysicalHardwareResultBundleError("result bundle contains duplicate functional observation test ids")
        if not any(row["id"] == observation.test_id for row in plan.tests):
            raise PhysicalHardwareResultBundleError("functional observation test id is not in exact plan")
        observation_by_test[observation.test_id] = (observation, file_sha, file_size)

    review_by_test: dict[str, tuple[PhysicalHardwareTestReviewEvidence, str, int]] = {}
    for path in result_review_paths:
        try:
            raw, file_sha, file_size = _read_exact(Path(path), "functional result-review evidence")
            review = load_physical_hardware_test_review_evidence(Path(path))
        except PhysicalHardwareTestReviewError as exc:
            raise PhysicalHardwareResultBundleError(str(exc)) from exc
        _require_canonical_file(raw, review.canonical_json(), file_sha, "functional result-review evidence")
        if review.test_id in review_by_test:
            raise PhysicalHardwareResultBundleError("result bundle contains duplicate functional result-review test ids")
        observation_entry = observation_by_test.get(review.test_id)
        if observation_entry is None:
            raise PhysicalHardwareResultBundleError("functional result review has no exact bundled observation")
        _validate_result_review_against_observation(plan, observation_entry[0], review)
        review_by_test[review.test_id] = (review, file_sha, file_size)

    try:
        summary_raw, summary_file_sha, summary_file_size = _read_exact(
            Path(summary_path), "physical functional-test summary evidence"
        )
        summary = load_physical_hardware_test_summary_evidence(Path(summary_path))
    except PhysicalHardwareTestSummaryError as exc:
        raise PhysicalHardwareResultBundleError(str(exc)) from exc
    _require_canonical_file(
        summary_raw,
        summary.canonical_json(),
        summary_file_sha,
        "physical functional-test summary evidence",
    )
    try:
        recomputed_summary = build_physical_hardware_test_summary(
            plan, [entry[0] for entry in review_by_test.values()]
        )
        validate_physical_hardware_test_summary_evidence(summary)
    except PhysicalHardwareTestSummaryError as exc:
        raise PhysicalHardwareResultBundleError(str(exc)) from exc
    if summary != recomputed_summary:
        raise PhysicalHardwareResultBundleError("supplied functional-test summary does not match exact bundled reviews")

    summary_rows = {row["id"]: row for row in summary.tests}
    rows: list[dict[str, Any]] = []
    for planned in plan.tests:
        test_id = planned["id"]
        summary_row = summary_rows.get(test_id)
        if summary_row is None:
            raise PhysicalHardwareResultBundleError("functional-test summary is missing a planned test id")
        status = summary_row["status"]
        if status not in _ALLOWED_SUMMARY_STATUSES:
            raise PhysicalHardwareResultBundleError("functional-test summary contains unsupported status")
        observation_entry = observation_by_test.get(test_id)
        review_entry = review_by_test.get(test_id)
        rows.append(
            {
                "id": test_id,
                "required_for_beta": planned["required_for_beta"],
                "summary_status": status,
                "observation_present": observation_entry is not None,
                "observation_evidence_sha256": observation_entry[0].evidence_sha256() if observation_entry else None,
                "observation_file_sha256": observation_entry[1] if observation_entry else None,
                "observation_file_size": observation_entry[2] if observation_entry else None,
                "result_review_present": review_entry is not None,
                "result_review_evidence_sha256": review_entry[0].evidence_sha256() if review_entry else None,
                "result_review_file_sha256": review_entry[1] if review_entry else None,
                "result_review_file_size": review_entry[2] if review_entry else None,
                "result_reviewer": review_entry[0].reviewer if review_entry else None,
            }
        )

    evidence = PhysicalHardwareResultBundleEvidence(
        schema_version=1,
        bundle_policy=_BUNDLE_POLICY,
        profile_id=plan.profile_id,
        device_serial=plan.device_serial,
        physical_hardware_test_plan_sha256=plan.evidence_sha256(),
        physical_hardware_test_plan_file_sha256=plan_file_sha,
        physical_hardware_test_plan_file_size=plan_file_size,
        physical_hardware_test_plan_review_sha256=plan_review.evidence_sha256(),
        physical_hardware_test_plan_review_file_sha256=plan_review_file_sha,
        physical_hardware_test_plan_review_file_size=plan_review_file_size,
        plan_review_reviewer=plan_review.reviewer,
        plan_review_accepted_for_physical_execution=True,
        functional_hardware_contract_sha256=plan.functional_hardware_contract_sha256,
        tests=tuple(rows),
        test_count=summary.test_count,
        observation_count=len(observation_by_test),
        result_review_count=len(review_by_test),
        reviewed_test_count=summary.reviewed_test_count,
        reviewed_pass_count=summary.reviewed_pass_count,
        beta_required_test_count=summary.beta_required_test_count,
        beta_required_reviewed_pass_count=summary.beta_required_reviewed_pass_count,
        beta_required_remaining_count=summary.beta_required_remaining_count,
        beta_required_tests_all_reviewed_pass=summary.beta_required_tests_all_reviewed_pass,
        physical_hardware_test_summary_sha256=summary.evidence_sha256(),
        physical_hardware_test_summary_file_sha256=summary_file_sha,
        physical_hardware_test_summary_file_size=summary_file_size,
        exact_files_verified=True,
        manual_release_gate_review_required=True,
        project_support_claim_authorized=False,
        persistent_write_performed=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    validate_physical_hardware_result_bundle_evidence(evidence)
    return evidence


def validate_physical_hardware_result_bundle_evidence(
    evidence: PhysicalHardwareResultBundleEvidence,
) -> None:
    if not isinstance(evidence, PhysicalHardwareResultBundleEvidence) or evidence.schema_version != 1:
        raise PhysicalHardwareResultBundleError("physical functional result bundle must be schema-v1 typed evidence")
    if evidence.bundle_policy != _BUNDLE_POLICY:
        raise PhysicalHardwareResultBundleError("physical functional result bundle policy is unsupported")
    _safe_identity(evidence.profile_id, "functional result bundle profile id", 128)
    _safe_identity(evidence.device_serial, "functional result bundle device serial")
    _safe_identity(evidence.plan_review_reviewer, "functional result bundle plan reviewer", 128)
    for value, label in (
        (evidence.physical_hardware_test_plan_sha256, "physical hardware test plan"),
        (evidence.physical_hardware_test_plan_file_sha256, "physical hardware test plan file"),
        (evidence.physical_hardware_test_plan_review_sha256, "physical hardware test-plan review"),
        (evidence.physical_hardware_test_plan_review_file_sha256, "physical hardware test-plan review file"),
        (evidence.functional_hardware_contract_sha256, "functional hardware contract"),
        (evidence.physical_hardware_test_summary_sha256, "physical functional-test summary"),
        (evidence.physical_hardware_test_summary_file_sha256, "physical functional-test summary file"),
    ):
        _sha(value, label)
    _positive(evidence.physical_hardware_test_plan_file_size, "physical hardware test plan file size")
    _positive(evidence.physical_hardware_test_plan_review_file_size, "physical hardware test-plan review file size")
    _positive(evidence.physical_hardware_test_summary_file_size, "physical functional-test summary file size")
    if evidence.plan_review_accepted_for_physical_execution is not True or evidence.exact_files_verified is not True:
        raise PhysicalHardwareResultBundleError("physical functional result bundle lacks accepted plan review/exact-file state")
    if not isinstance(evidence.tests, tuple) or not evidence.tests:
        raise PhysicalHardwareResultBundleError("physical functional result bundle must contain planned tests")

    expected_fields = {
        "id",
        "required_for_beta",
        "summary_status",
        "observation_present",
        "observation_evidence_sha256",
        "observation_file_sha256",
        "observation_file_size",
        "result_review_present",
        "result_review_evidence_sha256",
        "result_review_file_sha256",
        "result_review_file_size",
        "result_reviewer",
    }
    ids: list[str] = []
    observation_count = 0
    result_review_count = 0
    for row in evidence.tests:
        if not isinstance(row, dict) or set(row) != expected_fields:
            raise PhysicalHardwareResultBundleError("physical functional result bundle row fields drifted")
        test_id = _safe_identity(row["id"], "physical functional result bundle test id", 64)
        ids.append(test_id)
        if not isinstance(row["required_for_beta"], bool):
            raise PhysicalHardwareResultBundleError("physical functional result bundle required-for-Beta flag is invalid")
        if row["summary_status"] not in _ALLOWED_SUMMARY_STATUSES:
            raise PhysicalHardwareResultBundleError("physical functional result bundle summary status is invalid")
        if not isinstance(row["observation_present"], bool) or not isinstance(row["result_review_present"], bool):
            raise PhysicalHardwareResultBundleError("physical functional result bundle presence flags are invalid")
        if row["result_review_present"] and not row["observation_present"]:
            raise PhysicalHardwareResultBundleError("physical functional result bundle review cannot exist without observation")
        if row["observation_present"]:
            observation_count += 1
            _sha(row["observation_evidence_sha256"], "functional observation evidence")
            _sha(row["observation_file_sha256"], "functional observation file")
            _positive(row["observation_file_size"], "functional observation file size")
        elif any(row[name] is not None for name in (
            "observation_evidence_sha256", "observation_file_sha256", "observation_file_size"
        )):
            raise PhysicalHardwareResultBundleError("absent functional observation cannot carry file identity")
        if row["result_review_present"]:
            result_review_count += 1
            _sha(row["result_review_evidence_sha256"], "functional result-review evidence")
            _sha(row["result_review_file_sha256"], "functional result-review file")
            _positive(row["result_review_file_size"], "functional result-review file size")
            _safe_identity(row["result_reviewer"], "functional result reviewer", 128)
        elif any(row[name] is not None for name in (
            "result_review_evidence_sha256", "result_review_file_sha256", "result_review_file_size", "result_reviewer"
        )):
            raise PhysicalHardwareResultBundleError("absent functional result review cannot carry file identity")
        if row["summary_status"] != "pending" and not row["result_review_present"]:
            raise PhysicalHardwareResultBundleError("reviewed functional summary status requires bundled result review")

    if len(ids) != len(set(ids)):
        raise PhysicalHardwareResultBundleError("physical functional result bundle contains duplicate test ids")
    if evidence.test_count != len(evidence.tests):
        raise PhysicalHardwareResultBundleError("physical functional result bundle test count drifted")
    if evidence.observation_count != observation_count or evidence.result_review_count != result_review_count:
        raise PhysicalHardwareResultBundleError("physical functional result bundle file counters drifted")
    for value, label in (
        (evidence.reviewed_test_count, "reviewed test count"),
        (evidence.reviewed_pass_count, "reviewed pass count"),
        (evidence.beta_required_test_count, "Beta-required test count"),
        (evidence.beta_required_reviewed_pass_count, "Beta-required reviewed-pass count"),
        (evidence.beta_required_remaining_count, "Beta-required remaining count"),
    ):
        _nonnegative(value, label)
    if evidence.reviewed_test_count != result_review_count:
        raise PhysicalHardwareResultBundleError("physical functional result bundle reviewed count drifted")
    if evidence.reviewed_pass_count > evidence.reviewed_test_count:
        raise PhysicalHardwareResultBundleError("physical functional result bundle reviewed-pass count is impossible")
    if evidence.beta_required_reviewed_pass_count > evidence.beta_required_test_count:
        raise PhysicalHardwareResultBundleError("physical functional result bundle Beta pass count is impossible")
    if evidence.beta_required_remaining_count != (
        evidence.beta_required_test_count - evidence.beta_required_reviewed_pass_count
    ):
        raise PhysicalHardwareResultBundleError("physical functional result bundle Beta remaining count drifted")
    if evidence.beta_required_tests_all_reviewed_pass is not (
        evidence.beta_required_test_count > 0
        and evidence.beta_required_reviewed_pass_count == evidence.beta_required_test_count
    ):
        raise PhysicalHardwareResultBundleError("physical functional result bundle Beta coverage flag drifted")
    if evidence.manual_release_gate_review_required is not True:
        raise PhysicalHardwareResultBundleError("physical functional result bundle must require manual release-gate review")
    forbidden = (
        evidence.project_support_claim_authorized,
        evidence.persistent_write_performed,
        evidence.phone_storage_written,
        evidence.hardware_verified,
        evidence.beta_gate_credit,
    )
    if any(value is not False for value in forbidden):
        raise PhysicalHardwareResultBundleError("physical functional result bundle contains forbidden support/write/hardware/Beta promotion")


def load_physical_hardware_result_bundle_evidence(path: Path) -> PhysicalHardwareResultBundleEvidence:
    raw, _, _ = _read_exact(Path(path), "physical functional result bundle", _MAX_BUNDLE_BYTES)
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalHardwareResultBundleError("physical functional result bundle is not valid UTF-8 JSON") from exc
    expected = {item.name for item in fields(PhysicalHardwareResultBundleEvidence)}
    if not isinstance(value, dict) or set(value) != expected or not isinstance(value.get("tests"), list):
        raise PhysicalHardwareResultBundleError("physical functional result bundle fields do not match schema-v1")
    value["tests"] = tuple(value["tests"])
    try:
        evidence = PhysicalHardwareResultBundleEvidence(**value)
        validate_physical_hardware_result_bundle_evidence(evidence)
    except (TypeError, PhysicalHardwareResultBundleError) as exc:
        raise PhysicalHardwareResultBundleError("physical functional result bundle evidence is invalid") from exc
    if raw != evidence.canonical_json().encode("utf-8"):
        raise PhysicalHardwareResultBundleError("physical functional result bundle is not canonical JSON")
    return evidence


def write_physical_hardware_result_bundle_evidence(
    evidence: PhysicalHardwareResultBundleEvidence,
    destination: Path,
) -> str:
    validate_physical_hardware_result_bundle_evidence(evidence)
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise PhysicalHardwareResultBundleError("refusing to overwrite existing physical functional result bundle")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(evidence.canonical_json())
    except OSError as exc:
        raise PhysicalHardwareResultBundleError(f"cannot write physical functional result bundle: {exc}") from exc
    return evidence.evidence_sha256()

def build_current_physical_hardware_result_bundle_from_files(
    boot_observation: PhysicalBootObservationEvidence,
    plan_path: Path,
    plan_review_path: Path,
    observation_paths: Iterable[Path],
    result_review_paths: Iterable[Path],
    summary_path: Path,
) -> PhysicalHardwareResultBundleEvidence:
    """Freeze a new functional campaign only when its exact plan is current-provenance rooted."""
    try:
        require_current_physical_campaign_observation(boot_observation)
    except PhysicalCampaignAdmissionError as exc:
        raise PhysicalHardwareResultBundleError(str(exc)) from exc
    try:
        plan = load_physical_hardware_test_plan(Path(plan_path))
    except PhysicalHardwareTestPlanError as exc:
        raise PhysicalHardwareResultBundleError(str(exc)) from exc
    try:
        require_current_physical_campaign_observation(
            boot_observation,
            expected_profile_id=plan.profile_id,
            expected_device_serial=plan.device_serial,
            expected_observation_sha256=plan.physical_boot_observation_sha256,
            expected_transcript_sha256=plan.transcript_sha256,
            expected_rescue_probe_id=plan.rescue_probe_id,
        )
    except PhysicalCampaignAdmissionError as exc:
        raise PhysicalHardwareResultBundleError(str(exc)) from exc
    return build_physical_hardware_result_bundle_from_files(
        plan_path,
        plan_review_path,
        observation_paths,
        result_review_paths,
        summary_path,
    )

