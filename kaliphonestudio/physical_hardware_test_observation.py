"""Exact evidence for one manually executed physical functional-hardware test.

This module never activates hardware and performs no phone I/O. It binds an
operator-authored observation record and notes to one exact pending test from a
``PhysicalHardwareTestPlanEvidence`` only after the original canonical plan has
an independently accepted exact-plan review. A recorded observation is only a
candidate for later manual review: it never grants hardware or Beta credit by
itself.
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
from .physical_hardware_test_plan_review import (
    PhysicalHardwareTestPlanReviewError,
    PhysicalHardwareTestPlanReviewEvidence,
    load_physical_hardware_test_plan_review_evidence,
    validate_physical_hardware_test_plan_review_evidence,
)

_OBSERVATION_POLICY = "manual-physical-hardware-functional-observation-v2"
_ALLOWED_OUTCOMES = frozenset({"pass_candidate", "failed", "inconclusive"})
_MAX_RECORD_BYTES = 512 * 1024
_MAX_NOTES_BYTES = 2 * 1024 * 1024
_MAX_EVIDENCE_BYTES = 4 * 1024 * 1024
_SAFE_OPERATOR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+-]{0,127}$")


class PhysicalHardwareTestObservationError(ValueError):
    pass


@dataclass(frozen=True)
class PhysicalHardwareTestObservationRecord:
    schema_version: int
    observation_policy: str
    profile_id: str
    device_serial: str
    test_id: str
    operator: str
    outcome: str
    physical_test_executed: bool
    exact_candidate_identity_confirmed: bool
    physical_device_observed: bool
    required_observation_checks: tuple[dict[str, Any], ...]
    limitations_recorded: bool
    persistent_write_performed: bool
    phone_storage_written: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"


@dataclass(frozen=True)
class PhysicalHardwareTestObservationEvidence:
    schema_version: int
    observation_policy: str
    profile_id: str
    device_serial: str
    physical_hardware_test_plan_sha256: str
    physical_hardware_test_plan_review_sha256: str
    physical_hardware_test_plan_file_sha256: str
    physical_hardware_test_plan_review_record_sha256: str
    physical_hardware_test_plan_review_notes_sha256: str
    plan_review_reviewer: str
    plan_review_accepted_for_physical_execution: bool
    physical_hardware_review_sha256: str
    physical_hardware_survey_sha256: str
    physical_boot_observation_sha256: str
    physical_rescue_diagnostics_sha256: str
    transcript_sha256: str
    rescue_probe_id: str
    functional_hardware_contract_sha256: str
    test_id: str
    required_for_beta: bool
    required_context_signals: tuple[str, ...]
    context_signals_satisfied: bool
    required_observations: tuple[str, ...]
    observation_record_sha256: str
    observation_record_size: int
    observation_notes_sha256: str
    observation_notes_size: int
    operator: str
    outcome: str
    physical_test_executed: bool
    exact_candidate_identity_confirmed: bool
    physical_device_observed: bool
    required_observation_checks: tuple[dict[str, Any], ...]
    limitations_recorded: bool
    observation_ready_for_manual_review: bool
    manual_review_required: bool
    functional_test_verified: bool
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
        raise PhysicalHardwareTestObservationError(f"{label} must be a lowercase SHA-256")
    return value


def _positive(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PhysicalHardwareTestObservationError(f"{label} must be a positive integer")
    return value


def _safe_text(value: object, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise PhysicalHardwareTestObservationError(f"{label} must be non-empty bounded text")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise PhysicalHardwareTestObservationError(f"{label} contains control data")
    return value


def _read_exact(path: Path, label: str, maximum: int) -> tuple[bytes, str, int]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalHardwareTestObservationError(f"{label} must be a regular non-symlink file")
    try:
        before = source.stat()
        raw = source.read_bytes()
        after = source.stat()
    except OSError as exc:
        raise PhysicalHardwareTestObservationError(f"cannot read {label}: {exc}") from exc
    if before.st_size <= 0 or before.st_size > maximum or len(raw) != before.st_size:
        raise PhysicalHardwareTestObservationError(f"{label} size is outside the safety limit")
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise PhysicalHardwareTestObservationError(f"{label} changed while being read")
    return raw, sha256(raw).hexdigest(), len(raw)


def _normalize_checks(value: object, required: tuple[str, ...]) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, (list, tuple)) or len(value) != len(required):
        raise PhysicalHardwareTestObservationError("functional observation checks must match every required observation exactly")
    rows: list[dict[str, Any]] = []
    for index, (row, expected) in enumerate(zip(value, required, strict=True)):
        if not isinstance(row, dict) or set(row) != {"observation", "satisfied"}:
            raise PhysicalHardwareTestObservationError(f"functional observation check {index} fields are invalid")
        if row["observation"] != expected or not isinstance(row["satisfied"], bool):
            raise PhysicalHardwareTestObservationError("functional observation checks drifted from the exact test plan")
        rows.append({"observation": expected, "satisfied": row["satisfied"]})
    return tuple(rows)


def _plan_test(plan: PhysicalHardwareTestPlanEvidence, test_id: str) -> dict[str, Any]:
    matches = [row for row in plan.tests if row["id"] == test_id]
    if len(matches) != 1:
        raise PhysicalHardwareTestObservationError("functional test id is not uniquely present in the exact test plan")
    return matches[0]


def _validate_exact_plan_review(
    plan: PhysicalHardwareTestPlanEvidence,
    review: PhysicalHardwareTestPlanReviewEvidence,
) -> None:
    try:
        validate_physical_hardware_test_plan(plan)
        validate_physical_hardware_test_plan_review_evidence(review)
    except (PhysicalHardwareTestPlanError, PhysicalHardwareTestPlanReviewError) as exc:
        raise PhysicalHardwareTestObservationError(str(exc)) from exc

    if review.accepted_for_physical_execution is not True or review.decision != "accepted":
        raise PhysicalHardwareTestObservationError(
            "functional observation requires an accepted exact test-plan review"
        )
    if review.plan_ready_for_physical_execution is not True or review.manual_test_execution_required is not True:
        raise PhysicalHardwareTestObservationError(
            "accepted exact test-plan review is not ready for manual physical execution"
        )
    if review.profile_id != plan.profile_id or review.device_serial != plan.device_serial:
        raise PhysicalHardwareTestObservationError(
            "accepted test-plan review identity does not match exact test plan"
        )

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
            raise PhysicalHardwareTestObservationError(
                f"accepted test-plan review drifted from exact plan: {name}"
            )
    if review.physical_hardware_test_plan_file_size != len(canonical):
        raise PhysicalHardwareTestObservationError(
            "accepted test-plan review file size drifted from exact plan"
        )
    if review.test_count != plan.test_count or review.beta_required_test_count != plan.beta_required_test_count:
        raise PhysicalHardwareTestObservationError(
            "accepted test-plan review test counts drifted from exact plan"
        )


def parse_physical_hardware_test_observation_record(
    raw: object,
    *,
    required_observations: tuple[str, ...],
) -> PhysicalHardwareTestObservationRecord:
    expected = {item.name for item in fields(PhysicalHardwareTestObservationRecord)}
    if not isinstance(raw, dict) or set(raw) != expected:
        raise PhysicalHardwareTestObservationError(
            "functional observation record fields do not match schema-v2"
        )
    if raw["schema_version"] != 2 or raw["observation_policy"] != _OBSERVATION_POLICY:
        raise PhysicalHardwareTestObservationError(
            "unsupported functional observation record schema/policy"
        )
    _safe_text(raw["profile_id"], "functional observation profile id", 128)
    _safe_text(raw["device_serial"], "functional observation device serial", 256)
    _safe_text(raw["test_id"], "functional observation test id", 64)
    operator = raw["operator"]
    if not isinstance(operator, str) or not _SAFE_OPERATOR_RE.fullmatch(operator):
        raise PhysicalHardwareTestObservationError(
            "functional observation operator must be a safe bounded identifier"
        )
    if raw["outcome"] not in _ALLOWED_OUTCOMES:
        raise PhysicalHardwareTestObservationError("functional observation outcome is unsupported")
    bool_fields = (
        "physical_test_executed",
        "exact_candidate_identity_confirmed",
        "physical_device_observed",
        "limitations_recorded",
        "persistent_write_performed",
        "phone_storage_written",
        "hardware_verified",
        "beta_gate_credit",
    )
    if any(not isinstance(raw[name], bool) for name in bool_fields):
        raise PhysicalHardwareTestObservationError("functional observation flags must be boolean")
    if raw["persistent_write_performed"] is not False or raw["phone_storage_written"] is not False:
        raise PhysicalHardwareTestObservationError("functional observation contract forbids persistent writes")
    if raw["hardware_verified"] is not False or raw["beta_gate_credit"] is not False:
        raise PhysicalHardwareTestObservationError("raw functional observations cannot grant hardware/Beta credit")
    checks = _normalize_checks(raw["required_observation_checks"], required_observations)
    if raw["physical_test_executed"] is not True:
        raise PhysicalHardwareTestObservationError("functional observation record requires an actually executed physical test")
    if raw["exact_candidate_identity_confirmed"] is not True or raw["physical_device_observed"] is not True:
        raise PhysicalHardwareTestObservationError("functional observation must be tied to the exact observed physical candidate")
    if raw["limitations_recorded"] is not True:
        raise PhysicalHardwareTestObservationError("functional observation limitations must be recorded")
    if raw["outcome"] == "pass_candidate" and not all(row["satisfied"] for row in checks):
        raise PhysicalHardwareTestObservationError("pass_candidate requires every exact required observation to be satisfied")
    normalized = dict(raw)
    normalized["required_observation_checks"] = checks
    return PhysicalHardwareTestObservationRecord(**normalized)


def load_physical_hardware_test_observation_record(
    path: Path,
    *,
    required_observations: tuple[str, ...],
) -> tuple[PhysicalHardwareTestObservationRecord, str, int]:
    raw, digest, size = _read_exact(path, "functional observation record", _MAX_RECORD_BYTES)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalHardwareTestObservationError("functional observation record is not valid UTF-8 JSON") from exc
    record = parse_physical_hardware_test_observation_record(value, required_observations=required_observations)
    if raw != record.canonical_json().encode("utf-8"):
        raise PhysicalHardwareTestObservationError("functional observation record is not canonical JSON")
    return record, digest, size


def read_physical_hardware_test_observation_notes(path: Path) -> tuple[str, int]:
    raw, digest, size = _read_exact(path, "functional observation notes", _MAX_NOTES_BYTES)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PhysicalHardwareTestObservationError("functional observation notes must be UTF-8") from exc
    if not text.strip() or "\x00" in text:
        raise PhysicalHardwareTestObservationError("functional observation notes are empty or contain NUL data")
    return digest, size


def make_inconclusive_physical_hardware_test_observation_record(
    plan: PhysicalHardwareTestPlanEvidence,
    plan_review: PhysicalHardwareTestPlanReviewEvidence,
    test_id: str,
    operator: str,
) -> PhysicalHardwareTestObservationRecord:
    _validate_exact_plan_review(plan, plan_review)
    row = _plan_test(plan, test_id)
    if not isinstance(operator, str) or not _SAFE_OPERATOR_RE.fullmatch(operator):
        raise PhysicalHardwareTestObservationError(
            "functional observation operator must be a safe bounded identifier"
        )
    return PhysicalHardwareTestObservationRecord(
        schema_version=2,
        observation_policy=_OBSERVATION_POLICY,
        profile_id=plan.profile_id,
        device_serial=plan.device_serial,
        test_id=test_id,
        operator=operator,
        outcome="inconclusive",
        physical_test_executed=False,
        exact_candidate_identity_confirmed=False,
        physical_device_observed=False,
        required_observation_checks=tuple(
            {"observation": item, "satisfied": False} for item in row["required_observations"]
        ),
        limitations_recorded=False,
        persistent_write_performed=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def bind_physical_hardware_test_observation(
    plan: PhysicalHardwareTestPlanEvidence,
    plan_review: PhysicalHardwareTestPlanReviewEvidence,
    record: PhysicalHardwareTestObservationRecord,
    *,
    observation_record_sha256: str,
    observation_record_size: int,
    observation_notes_sha256: str,
    observation_notes_size: int,
) -> PhysicalHardwareTestObservationEvidence:
    _validate_exact_plan_review(plan, plan_review)
    if record.profile_id != plan.profile_id or record.device_serial != plan.device_serial:
        raise PhysicalHardwareTestObservationError(
            "functional observation identity does not match exact test plan"
        )
    row = _plan_test(plan, record.test_id)
    required_observations = tuple(row["required_observations"])
    parsed = parse_physical_hardware_test_observation_record(
        asdict(record),
        required_observations=required_observations,
    )
    if row["status"] != "pending":
        raise PhysicalHardwareTestObservationError(
            "functional observation requires an exact pending test"
        )
    if row["context_signals_satisfied"] is not True:
        raise PhysicalHardwareTestObservationError(
            "functional observation cannot be bound while required context signals are missing"
        )

    evidence = PhysicalHardwareTestObservationEvidence(
        schema_version=2,
        observation_policy=_OBSERVATION_POLICY,
        profile_id=plan.profile_id,
        device_serial=plan.device_serial,
        physical_hardware_test_plan_sha256=plan.evidence_sha256(),
        physical_hardware_test_plan_review_sha256=plan_review.evidence_sha256(),
        physical_hardware_test_plan_file_sha256=plan_review.physical_hardware_test_plan_file_sha256,
        physical_hardware_test_plan_review_record_sha256=plan_review.review_record_sha256,
        physical_hardware_test_plan_review_notes_sha256=plan_review.review_notes_sha256,
        plan_review_reviewer=plan_review.reviewer,
        plan_review_accepted_for_physical_execution=True,
        physical_hardware_review_sha256=plan.physical_hardware_review_sha256,
        physical_hardware_survey_sha256=plan.physical_hardware_survey_sha256,
        physical_boot_observation_sha256=plan.physical_boot_observation_sha256,
        physical_rescue_diagnostics_sha256=plan.physical_rescue_diagnostics_sha256,
        transcript_sha256=plan.transcript_sha256,
        rescue_probe_id=plan.rescue_probe_id,
        functional_hardware_contract_sha256=plan.functional_hardware_contract_sha256,
        test_id=record.test_id,
        required_for_beta=row["required_for_beta"],
        required_context_signals=tuple(row["required_context_signals"]),
        context_signals_satisfied=True,
        required_observations=required_observations,
        observation_record_sha256=_sha(
            observation_record_sha256, "functional observation record"
        ),
        observation_record_size=_positive(
            observation_record_size, "functional observation record size"
        ),
        observation_notes_sha256=_sha(
            observation_notes_sha256, "functional observation notes"
        ),
        observation_notes_size=_positive(
            observation_notes_size, "functional observation notes size"
        ),
        operator=parsed.operator,
        outcome=parsed.outcome,
        physical_test_executed=True,
        exact_candidate_identity_confirmed=True,
        physical_device_observed=True,
        required_observation_checks=parsed.required_observation_checks,
        limitations_recorded=True,
        observation_ready_for_manual_review=True,
        manual_review_required=True,
        functional_test_verified=False,
        persistent_write_performed=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    validate_physical_hardware_test_observation_evidence(evidence)
    return evidence


def validate_physical_hardware_test_observation_evidence(
    evidence: PhysicalHardwareTestObservationEvidence,
) -> None:
    if not isinstance(evidence, PhysicalHardwareTestObservationEvidence) or evidence.schema_version != 2:
        raise PhysicalHardwareTestObservationError(
            "physical functional observation must be schema-v2 typed evidence"
        )
    if evidence.observation_policy != _OBSERVATION_POLICY:
        raise PhysicalHardwareTestObservationError(
            "physical functional observation policy is unsupported"
        )
    _safe_text(evidence.profile_id, "functional observation profile id", 128)
    _safe_text(evidence.device_serial, "functional observation device serial", 256)
    _safe_text(evidence.test_id, "functional observation test id", 64)
    if not _SAFE_OPERATOR_RE.fullmatch(evidence.operator):
        raise PhysicalHardwareTestObservationError("functional observation operator identifier is invalid")
    if not _SAFE_OPERATOR_RE.fullmatch(evidence.plan_review_reviewer):
        raise PhysicalHardwareTestObservationError("functional observation plan reviewer identifier is invalid")
    if evidence.outcome not in _ALLOWED_OUTCOMES:
        raise PhysicalHardwareTestObservationError("functional observation outcome is unsupported")
    for value, label in (
        (evidence.physical_hardware_test_plan_sha256, "physical hardware test plan"),
        (evidence.physical_hardware_test_plan_review_sha256, "physical hardware test plan review"),
        (evidence.physical_hardware_test_plan_file_sha256, "physical hardware test plan file"),
        (evidence.physical_hardware_test_plan_review_record_sha256, "physical hardware test plan review record"),
        (evidence.physical_hardware_test_plan_review_notes_sha256, "physical hardware test plan review notes"),
        (evidence.physical_hardware_review_sha256, "physical hardware review"),
        (evidence.physical_hardware_survey_sha256, "physical hardware survey"),
        (evidence.physical_boot_observation_sha256, "physical boot observation"),
        (evidence.physical_rescue_diagnostics_sha256, "physical rescue diagnostics"),
        (evidence.transcript_sha256, "rescue transcript"),
        (evidence.rescue_probe_id, "rescue probe id"),
        (evidence.functional_hardware_contract_sha256, "functional hardware contract"),
        (evidence.observation_record_sha256, "functional observation record"),
        (evidence.observation_notes_sha256, "functional observation notes"),
    ):
        _sha(value, label)
    _positive(evidence.observation_record_size, "functional observation record size")
    _positive(evidence.observation_notes_size, "functional observation notes size")
    if evidence.plan_review_accepted_for_physical_execution is not True:
        raise PhysicalHardwareTestObservationError(
            "functional observation lacks accepted exact test-plan review authorization"
        )
    if not isinstance(evidence.required_for_beta, bool) or evidence.context_signals_satisfied is not True:
        raise PhysicalHardwareTestObservationError("functional observation test metadata is invalid")
    if not isinstance(evidence.required_context_signals, tuple) or any(
        not isinstance(item, str) or not item for item in evidence.required_context_signals
    ):
        raise PhysicalHardwareTestObservationError("functional observation context signals are invalid")
    if not isinstance(evidence.required_observations, tuple) or not evidence.required_observations or any(
        not isinstance(item, str) or not item for item in evidence.required_observations
    ):
        raise PhysicalHardwareTestObservationError("functional observation requirements are invalid")
    checks = _normalize_checks(evidence.required_observation_checks, evidence.required_observations)
    if evidence.outcome == "pass_candidate" and not all(row["satisfied"] for row in checks):
        raise PhysicalHardwareTestObservationError("pass_candidate evidence requires every required observation")
    required_true = (
        evidence.physical_test_executed,
        evidence.exact_candidate_identity_confirmed,
        evidence.physical_device_observed,
        evidence.limitations_recorded,
        evidence.observation_ready_for_manual_review,
        evidence.manual_review_required,
    )
    if any(value is not True for value in required_true):
        raise PhysicalHardwareTestObservationError("functional observation is missing required physical/manual-review state")
    forbidden = (
        evidence.functional_test_verified,
        evidence.persistent_write_performed,
        evidence.phone_storage_written,
        evidence.hardware_verified,
        evidence.beta_gate_credit,
    )
    if any(value is not False for value in forbidden):
        raise PhysicalHardwareTestObservationError("functional observation contains forbidden write/hardware/Beta promotion")


def load_physical_hardware_test_observation_evidence(path: Path) -> PhysicalHardwareTestObservationEvidence:
    raw, _, _ = _read_exact(path, "functional observation evidence", _MAX_EVIDENCE_BYTES)
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalHardwareTestObservationError("functional observation evidence is not valid UTF-8 JSON") from exc
    expected = {item.name for item in fields(PhysicalHardwareTestObservationEvidence)}
    if not isinstance(value, dict) or set(value) != expected:
        raise PhysicalHardwareTestObservationError("functional observation evidence fields do not match schema-v2")
    for name in ("required_context_signals", "required_observations", "required_observation_checks"):
        if not isinstance(value.get(name), list):
            raise PhysicalHardwareTestObservationError("functional observation evidence list fields are invalid")
        value[name] = tuple(value[name])
    try:
        evidence = PhysicalHardwareTestObservationEvidence(**value)
        validate_physical_hardware_test_observation_evidence(evidence)
    except (TypeError, PhysicalHardwareTestObservationError) as exc:
        raise PhysicalHardwareTestObservationError("functional observation evidence is invalid") from exc
    if raw != evidence.canonical_json().encode("utf-8"):
        raise PhysicalHardwareTestObservationError("functional observation evidence is not canonical JSON")
    return evidence


def write_physical_hardware_test_observation_evidence(
    evidence: PhysicalHardwareTestObservationEvidence,
    destination: Path,
) -> str:
    validate_physical_hardware_test_observation_evidence(evidence)
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise PhysicalHardwareTestObservationError("refusing to overwrite existing functional observation evidence")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(evidence.canonical_json())
    except OSError as exc:
        raise PhysicalHardwareTestObservationError(f"cannot write functional observation evidence: {exc}") from exc
    return evidence.evidence_sha256()


def bind_physical_hardware_test_observation_from_files(
    plan_path: Path,
    plan_review_path: Path,
    test_id: str,
    record_path: Path,
    notes_path: Path,
) -> PhysicalHardwareTestObservationEvidence:
    try:
        plan = load_physical_hardware_test_plan(plan_path)
        plan_review = load_physical_hardware_test_plan_review_evidence(plan_review_path)
    except (PhysicalHardwareTestPlanError, PhysicalHardwareTestPlanReviewError) as exc:
        raise PhysicalHardwareTestObservationError(str(exc)) from exc
    _validate_exact_plan_review(plan, plan_review)
    row = _plan_test(plan, test_id)
    required = tuple(row["required_observations"])
    record, record_sha, record_size = load_physical_hardware_test_observation_record(
        record_path,
        required_observations=required,
    )
    if record.test_id != test_id:
        raise PhysicalHardwareTestObservationError(
            "functional observation record test id does not match requested test"
        )
    notes_sha, notes_size = read_physical_hardware_test_observation_notes(notes_path)
    return bind_physical_hardware_test_observation(
        plan,
        plan_review,
        record,
        observation_record_sha256=record_sha,
        observation_record_size=record_size,
        observation_notes_sha256=notes_sha,
        observation_notes_size=notes_size,
    )
