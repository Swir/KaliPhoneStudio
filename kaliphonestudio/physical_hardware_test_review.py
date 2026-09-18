"""Manual review of one exact physical functional-hardware observation.

A review may accept the observation as a reviewed pass/fail/inconclusive result
for later aggregate status work, but this module never updates public support,
never authorizes a phone write, and never grants hardware or Beta release
credit. Project/Beta claims remain a separate release-gate decision.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

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

_REVIEW_POLICY = "manual-physical-hardware-functional-test-review-v1"
_ALLOWED_DECISIONS = frozenset({"accepted_pass", "accepted_fail", "accepted_inconclusive", "rejected"})
_DECISION_BY_OUTCOME = {
    "pass_candidate": "accepted_pass",
    "failed": "accepted_fail",
    "inconclusive": "accepted_inconclusive",
}
_RESULT_BY_DECISION = {
    "accepted_pass": "pass",
    "accepted_fail": "fail",
    "accepted_inconclusive": "inconclusive",
    "rejected": "rejected",
}
_MAX_REVIEW_RECORD_BYTES = 512 * 1024
_MAX_REVIEW_NOTES_BYTES = 2 * 1024 * 1024
_MAX_EVIDENCE_BYTES = 4 * 1024 * 1024
_SAFE_REVIEWER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+-]{0,127}$")


class PhysicalHardwareTestReviewError(ValueError):
    pass


@dataclass(frozen=True)
class PhysicalHardwareTestReviewRecord:
    schema_version: int
    review_policy: str
    profile_id: str
    device_serial: str
    test_id: str
    reviewer: str
    decision: str
    exact_test_plan_reviewed: bool
    exact_observation_evidence_reviewed: bool
    physical_context_reviewed: bool
    required_observations_reviewed: bool
    notes_and_limitations_reviewed: bool
    no_persistent_write_confirmed: bool
    project_support_claim_authorized: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"


@dataclass(frozen=True)
class PhysicalHardwareTestReviewEvidence:
    schema_version: int
    review_policy: str
    profile_id: str
    device_serial: str
    physical_hardware_test_plan_sha256: str
    physical_hardware_test_observation_sha256: str
    physical_hardware_review_sha256: str
    physical_hardware_survey_sha256: str
    physical_boot_observation_sha256: str
    physical_rescue_diagnostics_sha256: str
    transcript_sha256: str
    rescue_probe_id: str
    functional_hardware_contract_sha256: str
    test_id: str
    required_for_beta: bool
    observation_outcome: str
    review_record_sha256: str
    review_record_size: int
    review_notes_sha256: str
    review_notes_size: int
    reviewer: str
    decision: str
    exact_test_plan_reviewed: bool
    exact_observation_evidence_reviewed: bool
    physical_context_reviewed: bool
    required_observations_reviewed: bool
    notes_and_limitations_reviewed: bool
    no_persistent_write_confirmed: bool
    review_checks_complete: bool
    review_recorded: bool
    accepted_for_functional_status: bool
    reviewed_result: str
    test_passed_review: bool
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
        raise PhysicalHardwareTestReviewError(f"{label} must be a lowercase SHA-256")
    return value


def _positive(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PhysicalHardwareTestReviewError(f"{label} must be a positive integer")
    return value


def _safe_text(value: object, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise PhysicalHardwareTestReviewError(f"{label} must be non-empty bounded text")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise PhysicalHardwareTestReviewError(f"{label} contains control data")
    return value


def _read_exact(path: Path, label: str, maximum: int) -> tuple[bytes, str, int]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalHardwareTestReviewError(f"{label} must be a regular non-symlink file")
    try:
        before = source.stat()
        raw = source.read_bytes()
        after = source.stat()
    except OSError as exc:
        raise PhysicalHardwareTestReviewError(f"cannot read {label}: {exc}") from exc
    if before.st_size <= 0 or before.st_size > maximum or len(raw) != before.st_size:
        raise PhysicalHardwareTestReviewError(f"{label} size is outside the safety limit")
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise PhysicalHardwareTestReviewError(f"{label} changed while being read")
    return raw, sha256(raw).hexdigest(), len(raw)


def parse_physical_hardware_test_review_record(raw: object) -> PhysicalHardwareTestReviewRecord:
    expected = {item.name for item in fields(PhysicalHardwareTestReviewRecord)}
    if not isinstance(raw, dict) or set(raw) != expected:
        raise PhysicalHardwareTestReviewError("functional test review record fields do not match schema-v1")
    if raw["schema_version"] != 1 or raw["review_policy"] != _REVIEW_POLICY:
        raise PhysicalHardwareTestReviewError("unsupported functional test review schema/policy")
    _safe_text(raw["profile_id"], "functional test review profile id", 128)
    _safe_text(raw["device_serial"], "functional test review device serial", 256)
    _safe_text(raw["test_id"], "functional test review test id", 64)
    reviewer = raw["reviewer"]
    if not isinstance(reviewer, str) or not _SAFE_REVIEWER_RE.fullmatch(reviewer):
        raise PhysicalHardwareTestReviewError("functional test reviewer must be a safe bounded identifier")
    if raw["decision"] not in _ALLOWED_DECISIONS:
        raise PhysicalHardwareTestReviewError("functional test review decision is unsupported")
    bool_fields = (
        "exact_test_plan_reviewed",
        "exact_observation_evidence_reviewed",
        "physical_context_reviewed",
        "required_observations_reviewed",
        "notes_and_limitations_reviewed",
        "no_persistent_write_confirmed",
        "project_support_claim_authorized",
        "beta_gate_credit",
    )
    if any(not isinstance(raw[name], bool) for name in bool_fields):
        raise PhysicalHardwareTestReviewError("functional test review flags must be boolean")
    if raw["project_support_claim_authorized"] is not False or raw["beta_gate_credit"] is not False:
        raise PhysicalHardwareTestReviewError("functional test review record cannot authorize project support/Beta credit")
    return PhysicalHardwareTestReviewRecord(**raw)


def load_physical_hardware_test_review_record(path: Path) -> tuple[PhysicalHardwareTestReviewRecord, str, int]:
    raw, digest, size = _read_exact(path, "functional test review record", _MAX_REVIEW_RECORD_BYTES)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalHardwareTestReviewError("functional test review record is not valid UTF-8 JSON") from exc
    record = parse_physical_hardware_test_review_record(value)
    if raw != record.canonical_json().encode("utf-8"):
        raise PhysicalHardwareTestReviewError("functional test review record is not canonical JSON")
    return record, digest, size


def read_physical_hardware_test_review_notes(path: Path) -> tuple[str, int]:
    raw, digest, size = _read_exact(path, "functional test review notes", _MAX_REVIEW_NOTES_BYTES)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PhysicalHardwareTestReviewError("functional test review notes must be UTF-8") from exc
    if not text.strip() or "\x00" in text:
        raise PhysicalHardwareTestReviewError("functional test review notes are empty or contain NUL data")
    return digest, size


def make_rejected_physical_hardware_test_review_record(
    observation: PhysicalHardwareTestObservationEvidence,
    reviewer: str,
) -> PhysicalHardwareTestReviewRecord:
    try:
        validate_physical_hardware_test_observation_evidence(observation)
    except PhysicalHardwareTestObservationError as exc:
        raise PhysicalHardwareTestReviewError(str(exc)) from exc
    if not isinstance(reviewer, str) or not _SAFE_REVIEWER_RE.fullmatch(reviewer):
        raise PhysicalHardwareTestReviewError("functional test reviewer must be a safe bounded identifier")
    return PhysicalHardwareTestReviewRecord(
        schema_version=1,
        review_policy=_REVIEW_POLICY,
        profile_id=observation.profile_id,
        device_serial=observation.device_serial,
        test_id=observation.test_id,
        reviewer=reviewer,
        decision="rejected",
        exact_test_plan_reviewed=False,
        exact_observation_evidence_reviewed=False,
        physical_context_reviewed=False,
        required_observations_reviewed=False,
        notes_and_limitations_reviewed=False,
        no_persistent_write_confirmed=False,
        project_support_claim_authorized=False,
        beta_gate_credit=False,
    )


def bind_physical_hardware_test_review(
    observation: PhysicalHardwareTestObservationEvidence,
    review: PhysicalHardwareTestReviewRecord,
    *,
    review_record_sha256: str,
    review_record_size: int,
    review_notes_sha256: str,
    review_notes_size: int,
) -> PhysicalHardwareTestReviewEvidence:
    try:
        validate_physical_hardware_test_observation_evidence(observation)
    except PhysicalHardwareTestObservationError as exc:
        raise PhysicalHardwareTestReviewError(str(exc)) from exc
    parsed = parse_physical_hardware_test_review_record(asdict(review))
    if parsed.profile_id != observation.profile_id or parsed.device_serial != observation.device_serial:
        raise PhysicalHardwareTestReviewError("functional test review identity does not match observation")
    if parsed.test_id != observation.test_id:
        raise PhysicalHardwareTestReviewError("functional test review id does not match observation")

    checks = (
        parsed.exact_test_plan_reviewed,
        parsed.exact_observation_evidence_reviewed,
        parsed.physical_context_reviewed,
        parsed.required_observations_reviewed,
        parsed.notes_and_limitations_reviewed,
        parsed.no_persistent_write_confirmed,
    )
    complete = all(checks)
    accepted = parsed.decision != "rejected"
    if accepted:
        expected_decision = _DECISION_BY_OUTCOME[observation.outcome]
        if parsed.decision != expected_decision:
            raise PhysicalHardwareTestReviewError("accepted review decision does not match exact observation outcome")
        if observation.observation_ready_for_manual_review is not True or not complete:
            raise PhysicalHardwareTestReviewError("cannot accept functional test result until every exact review check is complete")

    reviewed_result = _RESULT_BY_DECISION[parsed.decision]
    evidence = PhysicalHardwareTestReviewEvidence(
        schema_version=1,
        review_policy=_REVIEW_POLICY,
        profile_id=observation.profile_id,
        device_serial=observation.device_serial,
        physical_hardware_test_plan_sha256=observation.physical_hardware_test_plan_sha256,
        physical_hardware_test_observation_sha256=observation.evidence_sha256(),
        physical_hardware_review_sha256=observation.physical_hardware_review_sha256,
        physical_hardware_survey_sha256=observation.physical_hardware_survey_sha256,
        physical_boot_observation_sha256=observation.physical_boot_observation_sha256,
        physical_rescue_diagnostics_sha256=observation.physical_rescue_diagnostics_sha256,
        transcript_sha256=observation.transcript_sha256,
        rescue_probe_id=observation.rescue_probe_id,
        functional_hardware_contract_sha256=observation.functional_hardware_contract_sha256,
        test_id=observation.test_id,
        required_for_beta=observation.required_for_beta,
        observation_outcome=observation.outcome,
        review_record_sha256=_sha(review_record_sha256, "functional test review record"),
        review_record_size=_positive(review_record_size, "functional test review record size"),
        review_notes_sha256=_sha(review_notes_sha256, "functional test review notes"),
        review_notes_size=_positive(review_notes_size, "functional test review notes size"),
        reviewer=parsed.reviewer,
        decision=parsed.decision,
        exact_test_plan_reviewed=parsed.exact_test_plan_reviewed,
        exact_observation_evidence_reviewed=parsed.exact_observation_evidence_reviewed,
        physical_context_reviewed=parsed.physical_context_reviewed,
        required_observations_reviewed=parsed.required_observations_reviewed,
        notes_and_limitations_reviewed=parsed.notes_and_limitations_reviewed,
        no_persistent_write_confirmed=parsed.no_persistent_write_confirmed,
        review_checks_complete=complete,
        review_recorded=True,
        accepted_for_functional_status=accepted,
        reviewed_result=reviewed_result,
        test_passed_review=parsed.decision == "accepted_pass",
        manual_release_gate_review_required=True,
        project_support_claim_authorized=False,
        persistent_write_performed=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    validate_physical_hardware_test_review_evidence(evidence)
    return evidence


def validate_physical_hardware_test_review_evidence(evidence: PhysicalHardwareTestReviewEvidence) -> None:
    if not isinstance(evidence, PhysicalHardwareTestReviewEvidence) or evidence.schema_version != 1:
        raise PhysicalHardwareTestReviewError("physical functional test review must be schema-v1 typed evidence")
    if evidence.review_policy != _REVIEW_POLICY:
        raise PhysicalHardwareTestReviewError("physical functional test review policy is unsupported")
    _safe_text(evidence.profile_id, "functional test review profile id", 128)
    _safe_text(evidence.device_serial, "functional test review device serial", 256)
    _safe_text(evidence.test_id, "functional test review test id", 64)
    if not _SAFE_REVIEWER_RE.fullmatch(evidence.reviewer):
        raise PhysicalHardwareTestReviewError("functional test reviewer identifier is invalid")
    if evidence.decision not in _ALLOWED_DECISIONS or evidence.reviewed_result != _RESULT_BY_DECISION[evidence.decision]:
        raise PhysicalHardwareTestReviewError("functional test review decision/result is invalid")
    if evidence.observation_outcome not in _DECISION_BY_OUTCOME:
        raise PhysicalHardwareTestReviewError("functional test review observation outcome is invalid")
    for value, label in (
        (evidence.physical_hardware_test_plan_sha256, "physical hardware test plan"),
        (evidence.physical_hardware_test_observation_sha256, "physical hardware test observation"),
        (evidence.physical_hardware_review_sha256, "physical hardware review"),
        (evidence.physical_hardware_survey_sha256, "physical hardware survey"),
        (evidence.physical_boot_observation_sha256, "physical boot observation"),
        (evidence.physical_rescue_diagnostics_sha256, "physical rescue diagnostics"),
        (evidence.transcript_sha256, "rescue transcript"),
        (evidence.rescue_probe_id, "rescue probe id"),
        (evidence.functional_hardware_contract_sha256, "functional hardware contract"),
        (evidence.review_record_sha256, "functional test review record"),
        (evidence.review_notes_sha256, "functional test review notes"),
    ):
        _sha(value, label)
    _positive(evidence.review_record_size, "functional test review record size")
    _positive(evidence.review_notes_size, "functional test review notes size")
    if not isinstance(evidence.required_for_beta, bool):
        raise PhysicalHardwareTestReviewError("functional test review Beta requirement must be boolean")
    checks = (
        evidence.exact_test_plan_reviewed,
        evidence.exact_observation_evidence_reviewed,
        evidence.physical_context_reviewed,
        evidence.required_observations_reviewed,
        evidence.notes_and_limitations_reviewed,
        evidence.no_persistent_write_confirmed,
    )
    if any(not isinstance(value, bool) for value in checks):
        raise PhysicalHardwareTestReviewError("functional test review checks must be boolean")
    if evidence.review_checks_complete is not all(checks):
        raise PhysicalHardwareTestReviewError("functional test review completeness flag drifted")
    accepted = evidence.decision != "rejected"
    if evidence.accepted_for_functional_status is not accepted:
        raise PhysicalHardwareTestReviewError("functional test review acceptance flag drifted")
    if accepted:
        if evidence.decision != _DECISION_BY_OUTCOME[evidence.observation_outcome]:
            raise PhysicalHardwareTestReviewError("functional test review decision does not match observation outcome")
        if evidence.review_checks_complete is not True:
            raise PhysicalHardwareTestReviewError("accepted functional test review must have every check complete")
    if evidence.test_passed_review is not (evidence.decision == "accepted_pass"):
        raise PhysicalHardwareTestReviewError("functional test reviewed-pass flag drifted")
    required_true = (evidence.review_recorded, evidence.manual_release_gate_review_required)
    if any(value is not True for value in required_true):
        raise PhysicalHardwareTestReviewError("functional test review is missing mandatory review state")
    forbidden = (
        evidence.project_support_claim_authorized,
        evidence.persistent_write_performed,
        evidence.phone_storage_written,
        evidence.hardware_verified,
        evidence.beta_gate_credit,
    )
    if any(value is not False for value in forbidden):
        raise PhysicalHardwareTestReviewError("functional test review contains forbidden support/write/hardware/Beta promotion")


def load_physical_hardware_test_review_evidence(path: Path) -> PhysicalHardwareTestReviewEvidence:
    raw, _, _ = _read_exact(path, "functional test review evidence", _MAX_EVIDENCE_BYTES)
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalHardwareTestReviewError("functional test review evidence is not valid UTF-8 JSON") from exc
    expected = {item.name for item in fields(PhysicalHardwareTestReviewEvidence)}
    if not isinstance(value, dict) or set(value) != expected:
        raise PhysicalHardwareTestReviewError("functional test review evidence fields do not match schema-v1")
    try:
        evidence = PhysicalHardwareTestReviewEvidence(**value)
        validate_physical_hardware_test_review_evidence(evidence)
    except (TypeError, PhysicalHardwareTestReviewError) as exc:
        raise PhysicalHardwareTestReviewError("functional test review evidence is invalid") from exc
    if raw != evidence.canonical_json().encode("utf-8"):
        raise PhysicalHardwareTestReviewError("functional test review evidence is not canonical JSON")
    return evidence


def write_physical_hardware_test_review_evidence(
    evidence: PhysicalHardwareTestReviewEvidence,
    destination: Path,
) -> str:
    validate_physical_hardware_test_review_evidence(evidence)
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise PhysicalHardwareTestReviewError("refusing to overwrite existing functional test review evidence")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(evidence.canonical_json())
    except OSError as exc:
        raise PhysicalHardwareTestReviewError(f"cannot write functional test review evidence: {exc}") from exc
    return evidence.evidence_sha256()


def bind_physical_hardware_test_review_from_files(
    observation_path: Path,
    review_record_path: Path,
    review_notes_path: Path,
) -> PhysicalHardwareTestReviewEvidence:
    try:
        observation = load_physical_hardware_test_observation_evidence(observation_path)
    except PhysicalHardwareTestObservationError as exc:
        raise PhysicalHardwareTestReviewError(str(exc)) from exc
    review, review_sha, review_size = load_physical_hardware_test_review_record(review_record_path)
    notes_sha, notes_size = read_physical_hardware_test_review_notes(review_notes_path)
    return bind_physical_hardware_test_review(
        observation,
        review,
        review_record_sha256=review_sha,
        review_record_size=review_size,
        review_notes_sha256=notes_sha,
        review_notes_size=notes_size,
    )

def make_current_rejected_physical_hardware_test_review_record(
    boot_observation: PhysicalBootObservationEvidence,
    observation: PhysicalHardwareTestObservationEvidence,
    reviewer: str,
) -> PhysicalHardwareTestReviewRecord:
    """Prepare result review only for an observation rooted in the current campaign."""
    try:
        # Reject stale/legacy provenance before dereferencing downstream evidence.
        require_current_physical_campaign_observation(boot_observation)
        require_current_physical_campaign_observation(
            boot_observation,
            expected_profile_id=observation.profile_id,
            expected_device_serial=observation.device_serial,
            expected_observation_sha256=observation.physical_boot_observation_sha256,
            expected_transcript_sha256=observation.transcript_sha256,
            expected_rescue_probe_id=observation.rescue_probe_id,
        )
    except PhysicalCampaignAdmissionError as exc:
        raise PhysicalHardwareTestReviewError(str(exc)) from exc
    return make_rejected_physical_hardware_test_review_record(observation, reviewer)


def bind_current_physical_hardware_test_review_from_files(
    boot_observation: PhysicalBootObservationEvidence,
    observation_path: Path,
    review_record_path: Path,
    review_notes_path: Path,
) -> PhysicalHardwareTestReviewEvidence:
    """Bind result review only when the exact observation belongs to the current campaign."""
    try:
        require_current_physical_campaign_observation(boot_observation)
    except PhysicalCampaignAdmissionError as exc:
        raise PhysicalHardwareTestReviewError(str(exc)) from exc
    try:
        observation = load_physical_hardware_test_observation_evidence(observation_path)
    except PhysicalHardwareTestObservationError as exc:
        raise PhysicalHardwareTestReviewError(str(exc)) from exc
    try:
        require_current_physical_campaign_observation(
            boot_observation,
            expected_profile_id=observation.profile_id,
            expected_device_serial=observation.device_serial,
            expected_observation_sha256=observation.physical_boot_observation_sha256,
            expected_transcript_sha256=observation.transcript_sha256,
            expected_rescue_probe_id=observation.rescue_probe_id,
        )
    except PhysicalCampaignAdmissionError as exc:
        raise PhysicalHardwareTestReviewError(str(exc)) from exc
    return bind_physical_hardware_test_review_from_files(
        observation_path,
        review_record_path,
        review_notes_path,
    )

