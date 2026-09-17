"""Aggregate reviewed physical functional-test evidence for one exact plan.

The summary is a status/audit artifact only. Even if every Beta-required test
has a reviewed pass, project hardware support and Beta release credit remain a
separate manual release-gate decision.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable

from .physical_hardware_test_plan import (
    PhysicalHardwareTestPlanError,
    PhysicalHardwareTestPlanEvidence,
    load_physical_hardware_test_plan,
    validate_physical_hardware_test_plan,
)
from .physical_hardware_test_review import (
    PhysicalHardwareTestReviewError,
    PhysicalHardwareTestReviewEvidence,
    load_physical_hardware_test_review_evidence,
    validate_physical_hardware_test_review_evidence,
)

_SUMMARY_POLICY = "physical-hardware-functional-test-summary-v1"
_MAX_EVIDENCE_BYTES = 8 * 1024 * 1024
_ALLOWED_STATUSES = frozenset({"pending", "reviewed_pass", "reviewed_fail", "reviewed_inconclusive", "rejected"})


class PhysicalHardwareTestSummaryError(ValueError):
    pass


@dataclass(frozen=True)
class PhysicalHardwareTestSummaryEvidence:
    schema_version: int
    summary_policy: str
    profile_id: str
    device_serial: str
    physical_hardware_test_plan_sha256: str
    functional_hardware_contract_sha256: str
    tests: tuple[dict[str, Any], ...]
    test_count: int
    reviewed_test_count: int
    reviewed_pass_count: int
    beta_required_test_count: int
    beta_required_reviewed_pass_count: int
    beta_required_remaining_count: int
    beta_required_tests_all_reviewed_pass: bool
    failed_or_inconclusive_present: bool
    manual_release_gate_review_required: bool
    project_support_claim_authorized: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise PhysicalHardwareTestSummaryError(f"{label} must be a lowercase SHA-256")
    return value


def build_physical_hardware_test_summary(
    plan: PhysicalHardwareTestPlanEvidence,
    reviews: Iterable[PhysicalHardwareTestReviewEvidence],
) -> PhysicalHardwareTestSummaryEvidence:
    try:
        validate_physical_hardware_test_plan(plan)
    except PhysicalHardwareTestPlanError as exc:
        raise PhysicalHardwareTestSummaryError(str(exc)) from exc

    review_by_test: dict[str, PhysicalHardwareTestReviewEvidence] = {}
    plan_sha = plan.evidence_sha256()
    for review in reviews:
        try:
            validate_physical_hardware_test_review_evidence(review)
        except PhysicalHardwareTestReviewError as exc:
            raise PhysicalHardwareTestSummaryError(str(exc)) from exc
        if review.profile_id != plan.profile_id or review.device_serial != plan.device_serial:
            raise PhysicalHardwareTestSummaryError("functional test review identity does not match exact plan")
        if review.physical_hardware_test_plan_sha256 != plan_sha:
            raise PhysicalHardwareTestSummaryError("functional test review is detached from exact plan")
        if review.functional_hardware_contract_sha256 != plan.functional_hardware_contract_sha256:
            raise PhysicalHardwareTestSummaryError("functional test review contract digest drifted")
        if review.test_id in review_by_test:
            raise PhysicalHardwareTestSummaryError("functional test summary contains duplicate review ids")
        if not any(row["id"] == review.test_id for row in plan.tests):
            raise PhysicalHardwareTestSummaryError("functional test review id is not present in exact plan")
        review_by_test[review.test_id] = review

    rows: list[dict[str, Any]] = []
    reviewed_count = 0
    pass_count = 0
    beta_total = 0
    beta_pass = 0
    failed_or_inconclusive = False
    for planned in plan.tests:
        test_id = planned["id"]
        required_for_beta = planned["required_for_beta"]
        if required_for_beta:
            beta_total += 1
        review = review_by_test.get(test_id)
        if review is None:
            status = "pending"
            review_sha: str | None = None
            reviewer: str | None = None
        else:
            reviewed_count += 1
            review_sha = review.evidence_sha256()
            reviewer = review.reviewer
            if review.accepted_for_functional_status:
                if review.reviewed_result == "pass":
                    status = "reviewed_pass"
                    pass_count += 1
                    if required_for_beta:
                        beta_pass += 1
                elif review.reviewed_result == "fail":
                    status = "reviewed_fail"
                    failed_or_inconclusive = True
                elif review.reviewed_result == "inconclusive":
                    status = "reviewed_inconclusive"
                    failed_or_inconclusive = True
                else:
                    raise PhysicalHardwareTestSummaryError("accepted functional test review has unsupported result")
            else:
                status = "rejected"
                failed_or_inconclusive = True
        rows.append(
            {
                "id": test_id,
                "required_for_beta": required_for_beta,
                "context_signals_satisfied": planned["context_signals_satisfied"],
                "status": status,
                "review_evidence_sha256": review_sha,
                "reviewer": reviewer,
            }
        )

    evidence = PhysicalHardwareTestSummaryEvidence(
        schema_version=1,
        summary_policy=_SUMMARY_POLICY,
        profile_id=plan.profile_id,
        device_serial=plan.device_serial,
        physical_hardware_test_plan_sha256=plan_sha,
        functional_hardware_contract_sha256=plan.functional_hardware_contract_sha256,
        tests=tuple(rows),
        test_count=len(rows),
        reviewed_test_count=reviewed_count,
        reviewed_pass_count=pass_count,
        beta_required_test_count=beta_total,
        beta_required_reviewed_pass_count=beta_pass,
        beta_required_remaining_count=beta_total - beta_pass,
        beta_required_tests_all_reviewed_pass=beta_total > 0 and beta_pass == beta_total,
        failed_or_inconclusive_present=failed_or_inconclusive,
        manual_release_gate_review_required=True,
        project_support_claim_authorized=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    validate_physical_hardware_test_summary_evidence(evidence)
    return evidence


def validate_physical_hardware_test_summary_evidence(evidence: PhysicalHardwareTestSummaryEvidence) -> None:
    if not isinstance(evidence, PhysicalHardwareTestSummaryEvidence) or evidence.schema_version != 1:
        raise PhysicalHardwareTestSummaryError("physical functional-test summary must be schema-v1 typed evidence")
    if evidence.summary_policy != _SUMMARY_POLICY:
        raise PhysicalHardwareTestSummaryError("physical functional-test summary policy is unsupported")
    if not isinstance(evidence.profile_id, str) or not evidence.profile_id or not isinstance(evidence.device_serial, str) or not evidence.device_serial:
        raise PhysicalHardwareTestSummaryError("physical functional-test summary identity is invalid")
    _sha(evidence.physical_hardware_test_plan_sha256, "physical hardware test plan")
    _sha(evidence.functional_hardware_contract_sha256, "functional hardware contract")
    if not isinstance(evidence.tests, tuple) or not evidence.tests:
        raise PhysicalHardwareTestSummaryError("physical functional-test summary must contain tests")

    expected_fields = {"id", "required_for_beta", "context_signals_satisfied", "status", "review_evidence_sha256", "reviewer"}
    ids: list[str] = []
    reviewed_count = 0
    pass_count = 0
    beta_total = 0
    beta_pass = 0
    failed_or_inconclusive = False
    for row in evidence.tests:
        if not isinstance(row, dict) or set(row) != expected_fields:
            raise PhysicalHardwareTestSummaryError("physical functional-test summary row fields drifted")
        test_id = row["id"]
        if not isinstance(test_id, str) or not test_id or len(test_id) > 64:
            raise PhysicalHardwareTestSummaryError("physical functional-test summary contains invalid test id")
        ids.append(test_id)
        if not isinstance(row["required_for_beta"], bool) or not isinstance(row["context_signals_satisfied"], bool):
            raise PhysicalHardwareTestSummaryError("physical functional-test summary row flags are invalid")
        status = row["status"]
        if status not in _ALLOWED_STATUSES:
            raise PhysicalHardwareTestSummaryError("physical functional-test summary row status is invalid")
        review_sha = row["review_evidence_sha256"]
        reviewer = row["reviewer"]
        if status == "pending":
            if review_sha is not None or reviewer is not None:
                raise PhysicalHardwareTestSummaryError("pending functional test summary row cannot carry review identity")
        else:
            _sha(review_sha, "functional test review evidence")
            if not isinstance(reviewer, str) or not reviewer:
                raise PhysicalHardwareTestSummaryError("reviewed functional test summary row requires reviewer")
            reviewed_count += 1
        if row["required_for_beta"]:
            beta_total += 1
        if status == "reviewed_pass":
            pass_count += 1
            if row["required_for_beta"]:
                beta_pass += 1
        if status in {"reviewed_fail", "reviewed_inconclusive", "rejected"}:
            failed_or_inconclusive = True

    if len(ids) != len(set(ids)):
        raise PhysicalHardwareTestSummaryError("physical functional-test summary contains duplicate test ids")
    expected_counts = (
        evidence.test_count == len(evidence.tests),
        evidence.reviewed_test_count == reviewed_count,
        evidence.reviewed_pass_count == pass_count,
        evidence.beta_required_test_count == beta_total,
        evidence.beta_required_reviewed_pass_count == beta_pass,
        evidence.beta_required_remaining_count == beta_total - beta_pass,
    )
    if not all(expected_counts):
        raise PhysicalHardwareTestSummaryError("physical functional-test summary counters drifted")
    if evidence.beta_required_tests_all_reviewed_pass is not (beta_total > 0 and beta_pass == beta_total):
        raise PhysicalHardwareTestSummaryError("physical functional-test Beta coverage flag drifted")
    if evidence.failed_or_inconclusive_present is not failed_or_inconclusive:
        raise PhysicalHardwareTestSummaryError("physical functional-test failure/inconclusive flag drifted")
    if evidence.manual_release_gate_review_required is not True:
        raise PhysicalHardwareTestSummaryError("physical functional-test summary must require manual release-gate review")
    if any(value is not False for value in (
        evidence.project_support_claim_authorized,
        evidence.hardware_verified,
        evidence.beta_gate_credit,
    )):
        raise PhysicalHardwareTestSummaryError("physical functional-test summary contains forbidden support/hardware/Beta promotion")


def load_physical_hardware_test_summary_evidence(path: Path) -> PhysicalHardwareTestSummaryEvidence:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalHardwareTestSummaryError("physical functional-test summary must be a regular non-symlink file")
    try:
        before = source.stat()
        raw = source.read_bytes()
        after = source.stat()
    except OSError as exc:
        raise PhysicalHardwareTestSummaryError(f"cannot read physical functional-test summary: {exc}") from exc
    if before.st_size <= 0 or before.st_size > _MAX_EVIDENCE_BYTES or len(raw) != before.st_size:
        raise PhysicalHardwareTestSummaryError("physical functional-test summary size is outside the safety limit")
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise PhysicalHardwareTestSummaryError("physical functional-test summary changed while being read")
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalHardwareTestSummaryError("physical functional-test summary is not valid UTF-8 JSON") from exc
    expected = {item.name for item in fields(PhysicalHardwareTestSummaryEvidence)}
    if not isinstance(value, dict) or set(value) != expected or not isinstance(value.get("tests"), list):
        raise PhysicalHardwareTestSummaryError("physical functional-test summary fields do not match schema-v1")
    value["tests"] = tuple(value["tests"])
    try:
        evidence = PhysicalHardwareTestSummaryEvidence(**value)
        validate_physical_hardware_test_summary_evidence(evidence)
    except (TypeError, PhysicalHardwareTestSummaryError) as exc:
        raise PhysicalHardwareTestSummaryError("physical functional-test summary evidence is invalid") from exc
    if raw != evidence.canonical_json().encode("utf-8"):
        raise PhysicalHardwareTestSummaryError("physical functional-test summary is not canonical JSON")
    return evidence


def write_physical_hardware_test_summary_evidence(
    evidence: PhysicalHardwareTestSummaryEvidence,
    destination: Path,
) -> str:
    validate_physical_hardware_test_summary_evidence(evidence)
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise PhysicalHardwareTestSummaryError("refusing to overwrite existing physical functional-test summary")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(evidence.canonical_json())
    except OSError as exc:
        raise PhysicalHardwareTestSummaryError(f"cannot write physical functional-test summary: {exc}") from exc
    return evidence.evidence_sha256()


def build_physical_hardware_test_summary_from_files(
    plan_path: Path,
    review_paths: Iterable[Path],
) -> PhysicalHardwareTestSummaryEvidence:
    try:
        plan = load_physical_hardware_test_plan(plan_path)
    except PhysicalHardwareTestPlanError as exc:
        raise PhysicalHardwareTestSummaryError(str(exc)) from exc
    reviews: list[PhysicalHardwareTestReviewEvidence] = []
    for path in review_paths:
        try:
            reviews.append(load_physical_hardware_test_review_evidence(path))
        except PhysicalHardwareTestReviewError as exc:
            raise PhysicalHardwareTestSummaryError(str(exc)) from exc
    return build_physical_hardware_test_summary(plan, reviews)
