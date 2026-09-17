"""Independent manual review of one exact physical functional-hardware test plan.

This layer exists between deterministic plan generation and any physical test
execution. It forces a reviewer to inspect the original canonical plan bytes,
not merely a downstream digest. Acceptance only authorizes use of that exact
plan as an input to later manual, non-destructive tests; it never executes a
test, activates hardware, writes phone storage, or grants hardware/Beta credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from .physical_hardware_test_plan import (
    PhysicalHardwareTestPlanError,
    PhysicalHardwareTestPlanEvidence,
    load_physical_hardware_test_plan,
    validate_physical_hardware_test_plan,
)

_REVIEW_POLICY = "manual-physical-hardware-functional-test-plan-review-v1"
_ALLOWED_DECISIONS = frozenset({"accepted", "rejected"})
_MAX_PLAN_BYTES = 4 * 1024 * 1024
_MAX_RECORD_BYTES = 512 * 1024
_MAX_NOTES_BYTES = 2 * 1024 * 1024
_MAX_EVIDENCE_BYTES = 4 * 1024 * 1024
_SAFE_REVIEWER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+-]{0,127}$")

_REVIEW_CHECK_FIELDS = (
    "exact_plan_bytes_reviewed",
    "exact_plan_identity_reviewed",
    "functional_contract_reviewed",
    "beta_required_scope_reviewed",
    "context_readiness_reviewed",
    "no_write_policy_reviewed",
    "limitations_reviewed",
)


class PhysicalHardwareTestPlanReviewError(ValueError):
    pass


@dataclass(frozen=True)
class PhysicalHardwareTestPlanReviewRecord:
    schema_version: int
    review_policy: str
    profile_id: str
    device_serial: str
    reviewer: str
    decision: str
    exact_plan_bytes_reviewed: bool
    exact_plan_identity_reviewed: bool
    functional_contract_reviewed: bool
    beta_required_scope_reviewed: bool
    context_readiness_reviewed: bool
    no_write_policy_reviewed: bool
    limitations_reviewed: bool
    functional_tests_executed: bool
    phone_storage_written: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"


@dataclass(frozen=True)
class PhysicalHardwareTestPlanReviewEvidence:
    schema_version: int
    review_policy: str
    profile_id: str
    device_serial: str
    physical_hardware_test_plan_sha256: str
    physical_hardware_test_plan_file_sha256: str
    physical_hardware_test_plan_file_size: int
    physical_hardware_review_sha256: str
    physical_hardware_survey_sha256: str
    physical_boot_observation_sha256: str
    physical_rescue_diagnostics_sha256: str
    transcript_sha256: str
    rescue_probe_id: str
    functional_hardware_contract_sha256: str
    test_count: int
    beta_required_test_count: int
    plan_ready_for_physical_execution: bool
    review_record_sha256: str
    review_record_size: int
    review_notes_sha256: str
    review_notes_size: int
    reviewer: str
    decision: str
    exact_plan_bytes_reviewed: bool
    exact_plan_identity_reviewed: bool
    functional_contract_reviewed: bool
    beta_required_scope_reviewed: bool
    context_readiness_reviewed: bool
    no_write_policy_reviewed: bool
    limitations_reviewed: bool
    accepted_for_physical_execution: bool
    manual_test_execution_required: bool
    functional_tests_executed: bool
    functional_hardware_verified: bool
    phone_storage_written: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise PhysicalHardwareTestPlanReviewError(f"{label} must be a lowercase SHA-256")
    return value


def _positive(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PhysicalHardwareTestPlanReviewError(f"{label} must be a positive integer")
    return value


def _safe_text(value: object, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise PhysicalHardwareTestPlanReviewError(f"{label} must be non-empty bounded text")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise PhysicalHardwareTestPlanReviewError(f"{label} contains control data")
    return value


def _read_exact(path: Path, label: str, maximum: int) -> tuple[bytes, str, int]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalHardwareTestPlanReviewError(f"{label} must be a regular non-symlink file")
    try:
        before = source.stat()
        raw = source.read_bytes()
        after = source.stat()
    except OSError as exc:
        raise PhysicalHardwareTestPlanReviewError(f"cannot read {label}: {exc}") from exc
    if before.st_size <= 0 or before.st_size > maximum or len(raw) != before.st_size:
        raise PhysicalHardwareTestPlanReviewError(f"{label} size is outside the safety limit")
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise PhysicalHardwareTestPlanReviewError(f"{label} changed while being read")
    return raw, sha256(raw).hexdigest(), len(raw)


def _review_checks(record: PhysicalHardwareTestPlanReviewRecord) -> tuple[bool, ...]:
    return tuple(getattr(record, name) for name in _REVIEW_CHECK_FIELDS)


def parse_physical_hardware_test_plan_review_record(raw: object) -> PhysicalHardwareTestPlanReviewRecord:
    expected = {item.name for item in fields(PhysicalHardwareTestPlanReviewRecord)}
    if not isinstance(raw, dict) or set(raw) != expected:
        raise PhysicalHardwareTestPlanReviewError("physical test-plan review record fields do not match schema-v1")
    if raw["schema_version"] != 1 or raw["review_policy"] != _REVIEW_POLICY:
        raise PhysicalHardwareTestPlanReviewError("unsupported physical test-plan review record schema/policy")
    _safe_text(raw["profile_id"], "physical test-plan review profile id", 128)
    _safe_text(raw["device_serial"], "physical test-plan review device serial", 256)
    reviewer = raw["reviewer"]
    if not isinstance(reviewer, str) or not _SAFE_REVIEWER_RE.fullmatch(reviewer):
        raise PhysicalHardwareTestPlanReviewError("physical test-plan reviewer must be a safe bounded identifier")
    if raw["decision"] not in _ALLOWED_DECISIONS:
        raise PhysicalHardwareTestPlanReviewError("physical test-plan review decision is unsupported")
    bool_fields = (*_REVIEW_CHECK_FIELDS, "functional_tests_executed", "phone_storage_written", "hardware_verified", "beta_gate_credit")
    if any(not isinstance(raw[name], bool) for name in bool_fields):
        raise PhysicalHardwareTestPlanReviewError("physical test-plan review flags must be boolean")
    if raw["functional_tests_executed"] is not False or raw["phone_storage_written"] is not False:
        raise PhysicalHardwareTestPlanReviewError("physical test-plan review cannot execute tests or write phone storage")
    if raw["hardware_verified"] is not False or raw["beta_gate_credit"] is not False:
        raise PhysicalHardwareTestPlanReviewError("physical test-plan review cannot grant hardware/Beta credit")
    record = PhysicalHardwareTestPlanReviewRecord(**raw)
    if record.decision == "accepted" and not all(_review_checks(record)):
        raise PhysicalHardwareTestPlanReviewError("accepted physical test-plan review requires every review check")
    return record


def load_physical_hardware_test_plan_review_record(
    path: Path,
) -> tuple[PhysicalHardwareTestPlanReviewRecord, str, int]:
    raw, digest, size = _read_exact(path, "physical test-plan review record", _MAX_RECORD_BYTES)
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalHardwareTestPlanReviewError("physical test-plan review record is not valid UTF-8 JSON") from exc
    record = parse_physical_hardware_test_plan_review_record(value)
    if raw != record.canonical_json().encode("utf-8"):
        raise PhysicalHardwareTestPlanReviewError("physical test-plan review record is not canonical JSON")
    return record, digest, size


def read_physical_hardware_test_plan_review_notes(path: Path) -> tuple[str, int]:
    raw, digest, size = _read_exact(path, "physical test-plan review notes", _MAX_NOTES_BYTES)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PhysicalHardwareTestPlanReviewError("physical test-plan review notes must be UTF-8") from exc
    if not text.strip() or "\x00" in text:
        raise PhysicalHardwareTestPlanReviewError("physical test-plan review notes are empty or contain NUL data")
    return digest, size


def make_rejected_physical_hardware_test_plan_review_record(
    plan: PhysicalHardwareTestPlanEvidence,
    reviewer: str,
) -> PhysicalHardwareTestPlanReviewRecord:
    try:
        validate_physical_hardware_test_plan(plan)
    except PhysicalHardwareTestPlanError as exc:
        raise PhysicalHardwareTestPlanReviewError(str(exc)) from exc
    if not isinstance(reviewer, str) or not _SAFE_REVIEWER_RE.fullmatch(reviewer):
        raise PhysicalHardwareTestPlanReviewError("physical test-plan reviewer must be a safe bounded identifier")
    return PhysicalHardwareTestPlanReviewRecord(
        schema_version=1,
        review_policy=_REVIEW_POLICY,
        profile_id=plan.profile_id,
        device_serial=plan.device_serial,
        reviewer=reviewer,
        decision="rejected",
        exact_plan_bytes_reviewed=False,
        exact_plan_identity_reviewed=False,
        functional_contract_reviewed=False,
        beta_required_scope_reviewed=False,
        context_readiness_reviewed=False,
        no_write_policy_reviewed=False,
        limitations_reviewed=False,
        functional_tests_executed=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def bind_physical_hardware_test_plan_review(
    plan: PhysicalHardwareTestPlanEvidence,
    record: PhysicalHardwareTestPlanReviewRecord,
    *,
    plan_file_sha256: str,
    plan_file_size: int,
    review_record_sha256: str,
    review_record_size: int,
    review_notes_sha256: str,
    review_notes_size: int,
) -> PhysicalHardwareTestPlanReviewEvidence:
    try:
        validate_physical_hardware_test_plan(plan)
    except PhysicalHardwareTestPlanError as exc:
        raise PhysicalHardwareTestPlanReviewError(str(exc)) from exc
    parsed = parse_physical_hardware_test_plan_review_record(asdict(record))
    if parsed.profile_id != plan.profile_id or parsed.device_serial != plan.device_serial:
        raise PhysicalHardwareTestPlanReviewError("physical test-plan review identity does not match the exact plan")

    canonical_plan = plan.canonical_json().encode("utf-8")
    canonical_plan_digest = sha256(canonical_plan).hexdigest()
    supplied_file_digest = _sha(plan_file_sha256, "physical hardware test plan file")
    if supplied_file_digest != canonical_plan_digest:
        raise PhysicalHardwareTestPlanReviewError("physical test-plan file digest does not match the exact canonical plan")
    if _positive(plan_file_size, "physical hardware test plan file size") != len(canonical_plan):
        raise PhysicalHardwareTestPlanReviewError("physical test-plan file size does not match the exact canonical plan")

    checks_complete = all(_review_checks(parsed))
    accepted = parsed.decision == "accepted" and checks_complete and plan.plan_ready_for_physical_execution is True

    evidence = PhysicalHardwareTestPlanReviewEvidence(
        schema_version=1,
        review_policy=_REVIEW_POLICY,
        profile_id=plan.profile_id,
        device_serial=plan.device_serial,
        physical_hardware_test_plan_sha256=plan.evidence_sha256(),
        physical_hardware_test_plan_file_sha256=supplied_file_digest,
        physical_hardware_test_plan_file_size=len(canonical_plan),
        physical_hardware_review_sha256=plan.physical_hardware_review_sha256,
        physical_hardware_survey_sha256=plan.physical_hardware_survey_sha256,
        physical_boot_observation_sha256=plan.physical_boot_observation_sha256,
        physical_rescue_diagnostics_sha256=plan.physical_rescue_diagnostics_sha256,
        transcript_sha256=plan.transcript_sha256,
        rescue_probe_id=plan.rescue_probe_id,
        functional_hardware_contract_sha256=plan.functional_hardware_contract_sha256,
        test_count=plan.test_count,
        beta_required_test_count=plan.beta_required_test_count,
        plan_ready_for_physical_execution=plan.plan_ready_for_physical_execution,
        review_record_sha256=_sha(review_record_sha256, "physical test-plan review record"),
        review_record_size=_positive(review_record_size, "physical test-plan review record size"),
        review_notes_sha256=_sha(review_notes_sha256, "physical test-plan review notes"),
        review_notes_size=_positive(review_notes_size, "physical test-plan review notes size"),
        reviewer=parsed.reviewer,
        decision=parsed.decision,
        exact_plan_bytes_reviewed=parsed.exact_plan_bytes_reviewed,
        exact_plan_identity_reviewed=parsed.exact_plan_identity_reviewed,
        functional_contract_reviewed=parsed.functional_contract_reviewed,
        beta_required_scope_reviewed=parsed.beta_required_scope_reviewed,
        context_readiness_reviewed=parsed.context_readiness_reviewed,
        no_write_policy_reviewed=parsed.no_write_policy_reviewed,
        limitations_reviewed=parsed.limitations_reviewed,
        accepted_for_physical_execution=accepted,
        manual_test_execution_required=True,
        functional_tests_executed=False,
        functional_hardware_verified=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    validate_physical_hardware_test_plan_review_evidence(evidence)
    return evidence


def validate_physical_hardware_test_plan_review_evidence(
    evidence: PhysicalHardwareTestPlanReviewEvidence,
) -> None:
    if not isinstance(evidence, PhysicalHardwareTestPlanReviewEvidence) or evidence.schema_version != 1:
        raise PhysicalHardwareTestPlanReviewError("physical test-plan review must be schema-v1 typed evidence")
    if evidence.review_policy != _REVIEW_POLICY:
        raise PhysicalHardwareTestPlanReviewError("physical test-plan review policy is unsupported")
    _safe_text(evidence.profile_id, "physical test-plan review profile id", 128)
    _safe_text(evidence.device_serial, "physical test-plan review device serial", 256)
    if not _SAFE_REVIEWER_RE.fullmatch(evidence.reviewer):
        raise PhysicalHardwareTestPlanReviewError("physical test-plan reviewer identifier is invalid")
    if evidence.decision not in _ALLOWED_DECISIONS:
        raise PhysicalHardwareTestPlanReviewError("physical test-plan review decision is unsupported")
    for value, label in (
        (evidence.physical_hardware_test_plan_sha256, "physical hardware test plan"),
        (evidence.physical_hardware_test_plan_file_sha256, "physical hardware test plan file"),
        (evidence.physical_hardware_review_sha256, "physical hardware review"),
        (evidence.physical_hardware_survey_sha256, "physical hardware survey"),
        (evidence.physical_boot_observation_sha256, "physical boot observation"),
        (evidence.physical_rescue_diagnostics_sha256, "physical rescue diagnostics"),
        (evidence.transcript_sha256, "rescue transcript"),
        (evidence.rescue_probe_id, "rescue probe id"),
        (evidence.functional_hardware_contract_sha256, "functional hardware contract"),
        (evidence.review_record_sha256, "physical test-plan review record"),
        (evidence.review_notes_sha256, "physical test-plan review notes"),
    ):
        _sha(value, label)
    _positive(evidence.physical_hardware_test_plan_file_size, "physical hardware test plan file size")
    _positive(evidence.review_record_size, "physical test-plan review record size")
    _positive(evidence.review_notes_size, "physical test-plan review notes size")
    if not isinstance(evidence.test_count, int) or isinstance(evidence.test_count, bool) or evidence.test_count <= 0:
        raise PhysicalHardwareTestPlanReviewError("physical test-plan review test count is invalid")
    if (
        not isinstance(evidence.beta_required_test_count, int)
        or isinstance(evidence.beta_required_test_count, bool)
        or evidence.beta_required_test_count <= 0
        or evidence.beta_required_test_count > evidence.test_count
    ):
        raise PhysicalHardwareTestPlanReviewError("physical test-plan review Beta-required test count is invalid")

    bool_fields = (
        "plan_ready_for_physical_execution",
        *_REVIEW_CHECK_FIELDS,
        "accepted_for_physical_execution",
        "manual_test_execution_required",
        "functional_tests_executed",
        "functional_hardware_verified",
        "phone_storage_written",
        "hardware_verified",
        "beta_gate_credit",
    )
    if any(not isinstance(getattr(evidence, name), bool) for name in bool_fields):
        raise PhysicalHardwareTestPlanReviewError("physical test-plan review flags must be boolean")
    checks_complete = all(getattr(evidence, name) for name in _REVIEW_CHECK_FIELDS)
    expected_acceptance = (
        evidence.decision == "accepted"
        and checks_complete
        and evidence.plan_ready_for_physical_execution is True
    )
    if evidence.accepted_for_physical_execution is not expected_acceptance:
        raise PhysicalHardwareTestPlanReviewError("physical test-plan review acceptance does not match decision/readiness/checks")
    if evidence.decision == "accepted" and not checks_complete:
        raise PhysicalHardwareTestPlanReviewError("accepted physical test-plan review requires every review check")
    if evidence.manual_test_execution_required is not True:
        raise PhysicalHardwareTestPlanReviewError("accepted plan review must still require manual physical test execution")
    if any(
        value is not False
        for value in (
            evidence.functional_tests_executed,
            evidence.functional_hardware_verified,
            evidence.phone_storage_written,
            evidence.hardware_verified,
            evidence.beta_gate_credit,
        )
    ):
        raise PhysicalHardwareTestPlanReviewError("physical test-plan review contains forbidden execution/write/hardware/Beta promotion")


def load_physical_hardware_test_plan_review_evidence(path: Path) -> PhysicalHardwareTestPlanReviewEvidence:
    raw, _, _ = _read_exact(path, "physical test-plan review evidence", _MAX_EVIDENCE_BYTES)
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalHardwareTestPlanReviewError("physical test-plan review evidence is not valid UTF-8 JSON") from exc
    expected = {item.name for item in fields(PhysicalHardwareTestPlanReviewEvidence)}
    if not isinstance(value, dict) or set(value) != expected:
        raise PhysicalHardwareTestPlanReviewError("physical test-plan review evidence fields do not match schema-v1")
    try:
        evidence = PhysicalHardwareTestPlanReviewEvidence(**value)
        validate_physical_hardware_test_plan_review_evidence(evidence)
    except (TypeError, PhysicalHardwareTestPlanReviewError) as exc:
        raise PhysicalHardwareTestPlanReviewError("physical test-plan review evidence is invalid") from exc
    if raw != evidence.canonical_json().encode("utf-8"):
        raise PhysicalHardwareTestPlanReviewError("physical test-plan review evidence is not canonical JSON")
    return evidence


def write_physical_hardware_test_plan_review_evidence(
    evidence: PhysicalHardwareTestPlanReviewEvidence,
    destination: Path,
) -> str:
    validate_physical_hardware_test_plan_review_evidence(evidence)
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise PhysicalHardwareTestPlanReviewError("refusing to overwrite existing physical test-plan review evidence")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(evidence.canonical_json())
    except OSError as exc:
        raise PhysicalHardwareTestPlanReviewError(f"cannot write physical test-plan review evidence: {exc}") from exc
    return evidence.evidence_sha256()


def bind_physical_hardware_test_plan_review_from_files(
    plan_path: Path,
    review_record_path: Path,
    review_notes_path: Path,
) -> PhysicalHardwareTestPlanReviewEvidence:
    plan_raw, plan_file_sha, plan_file_size = _read_exact(
        plan_path,
        "physical hardware test plan",
        _MAX_PLAN_BYTES,
    )
    try:
        plan = load_physical_hardware_test_plan(plan_path)
    except PhysicalHardwareTestPlanError as exc:
        raise PhysicalHardwareTestPlanReviewError(str(exc)) from exc
    if plan_raw != plan.canonical_json().encode("utf-8"):
        raise PhysicalHardwareTestPlanReviewError("reviewed physical test-plan bytes do not match the exact canonical plan")
    record, record_sha, record_size = load_physical_hardware_test_plan_review_record(review_record_path)
    notes_sha, notes_size = read_physical_hardware_test_plan_review_notes(review_notes_path)
    return bind_physical_hardware_test_plan_review(
        plan,
        record,
        plan_file_sha256=plan_file_sha,
        plan_file_size=plan_file_size,
        review_record_sha256=record_sha,
        review_record_size=record_size,
        review_notes_sha256=notes_sha,
        review_notes_size=notes_size,
    )
