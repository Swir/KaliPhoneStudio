"""Bind an accepted physical hardware-survey review to profile-driven tests.

The resulting plan is deliberately pending-only. It performs no phone I/O,
executes no subsystem activation, authorizes no write, and grants no physical
hardware or Beta credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .functional_hardware_contract import (
    FunctionalHardwareContractError,
    functional_hardware_contract_sha256,
    validate_functional_hardware_contract,
)
from .physical_hardware_review import (
    PhysicalHardwareReviewError,
    PhysicalHardwareReviewEvidence,
    load_physical_hardware_review_evidence,
    validate_physical_hardware_review_evidence,
)
from .profiles import DeviceProfile

_PLAN_POLICY = "physical-hardware-functional-test-plan-v1"
_MAX_PLAN_BYTES = 4 * 1024 * 1024


class PhysicalHardwareTestPlanError(ValueError):
    pass


@dataclass(frozen=True)
class PhysicalHardwareTestPlanEvidence:
    schema_version: int
    plan_policy: str
    profile_id: str
    device_serial: str
    physical_hardware_review_sha256: str
    physical_hardware_survey_sha256: str
    physical_boot_observation_sha256: str
    physical_rescue_diagnostics_sha256: str
    transcript_sha256: str
    rescue_probe_id: str
    functional_hardware_contract_sha256: str
    tests: tuple[dict[str, Any], ...]
    test_count: int
    beta_required_test_count: int
    plan_ready_for_physical_execution: bool
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
        raise PhysicalHardwareTestPlanError(f"{label} must be a lowercase SHA-256")
    return value


def build_physical_hardware_test_plan(
    profile: DeviceProfile,
    review: PhysicalHardwareReviewEvidence,
) -> PhysicalHardwareTestPlanEvidence:
    try:
        validate_physical_hardware_review_evidence(review)
    except PhysicalHardwareReviewError as exc:
        raise PhysicalHardwareTestPlanError(str(exc)) from exc
    if profile.profile_id != review.profile_id:
        raise PhysicalHardwareTestPlanError("hardware review profile does not match selected device profile")
    if review.review_recorded is not True or review.accepted_as_context is not True or review.functional_testing_required is not True:
        raise PhysicalHardwareTestPlanError("an accepted exact hardware-survey review is required before planning functional tests")

    try:
        raw_contract = profile.data["test_contract"]["functional_hardware"]
        contract = validate_functional_hardware_contract(raw_contract)
        contract_sha = functional_hardware_contract_sha256(raw_contract)
    except (KeyError, TypeError, FunctionalHardwareContractError) as exc:
        raise PhysicalHardwareTestPlanError(f"profile functional hardware contract is invalid: {exc}") from exc

    tests = tuple(
        {
            "id": item["id"],
            "required_for_beta": item["required_for_beta"],
            "manual_review_required": True,
            "destructive": False,
            "persistent_write_allowed": False,
            "required_context_signals": list(item["required_context_signals"]),
            "required_observations": list(item["required_observations"]),
            "status": "pending",
        }
        for item in contract["tests"]
    )
    evidence = PhysicalHardwareTestPlanEvidence(
        schema_version=1,
        plan_policy=_PLAN_POLICY,
        profile_id=profile.profile_id,
        device_serial=review.device_serial,
        physical_hardware_review_sha256=review.evidence_sha256(),
        physical_hardware_survey_sha256=review.physical_hardware_survey_sha256,
        physical_boot_observation_sha256=review.physical_boot_observation_sha256,
        physical_rescue_diagnostics_sha256=review.physical_rescue_diagnostics_sha256,
        transcript_sha256=review.transcript_sha256,
        rescue_probe_id=review.rescue_probe_id,
        functional_hardware_contract_sha256=contract_sha,
        tests=tests,
        test_count=len(tests),
        beta_required_test_count=sum(1 for item in tests if item["required_for_beta"]),
        plan_ready_for_physical_execution=True,
        functional_tests_executed=False,
        functional_hardware_verified=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    validate_physical_hardware_test_plan(evidence)
    return evidence


def validate_physical_hardware_test_plan(evidence: PhysicalHardwareTestPlanEvidence) -> None:
    if not isinstance(evidence, PhysicalHardwareTestPlanEvidence) or evidence.schema_version != 1:
        raise PhysicalHardwareTestPlanError("physical hardware test plan must be schema-v1 typed evidence")
    if evidence.plan_policy != _PLAN_POLICY:
        raise PhysicalHardwareTestPlanError("physical hardware test plan policy is unsupported")
    if not isinstance(evidence.profile_id, str) or not evidence.profile_id or not isinstance(evidence.device_serial, str) or not evidence.device_serial:
        raise PhysicalHardwareTestPlanError("physical hardware test plan identity is invalid")
    for value, label in (
        (evidence.physical_hardware_review_sha256, "physical hardware review"),
        (evidence.physical_hardware_survey_sha256, "physical hardware survey"),
        (evidence.physical_boot_observation_sha256, "physical boot observation"),
        (evidence.physical_rescue_diagnostics_sha256, "physical rescue diagnostics"),
        (evidence.transcript_sha256, "rescue transcript"),
        (evidence.rescue_probe_id, "rescue probe id"),
        (evidence.functional_hardware_contract_sha256, "functional hardware contract"),
    ):
        _sha(value, label)
    if not isinstance(evidence.tests, tuple) or not evidence.tests:
        raise PhysicalHardwareTestPlanError("physical hardware test plan must contain tests")
    ids: list[str] = []
    beta_count = 0
    expected_fields = {
        "id", "required_for_beta", "manual_review_required", "destructive",
        "persistent_write_allowed", "required_context_signals", "required_observations", "status",
    }
    for item in evidence.tests:
        if not isinstance(item, dict) or set(item) != expected_fields:
            raise PhysicalHardwareTestPlanError("physical hardware test plan test fields drifted")
        ids.append(item["id"])
        if item["status"] != "pending":
            raise PhysicalHardwareTestPlanError("new physical hardware test plans must remain pending-only")
        if item["manual_review_required"] is not True or item["destructive"] is not False or item["persistent_write_allowed"] is not False:
            raise PhysicalHardwareTestPlanError("physical hardware test plan contains unsafe permissions")
        if not isinstance(item["required_for_beta"], bool):
            raise PhysicalHardwareTestPlanError("physical hardware test Beta requirement must be boolean")
        beta_count += int(item["required_for_beta"])
    if len(ids) != len(set(ids)):
        raise PhysicalHardwareTestPlanError("physical hardware test plan contains duplicate test ids")
    if evidence.test_count != len(evidence.tests) or evidence.beta_required_test_count != beta_count or beta_count <= 0:
        raise PhysicalHardwareTestPlanError("physical hardware test plan counters drifted")
    if evidence.plan_ready_for_physical_execution is not True:
        raise PhysicalHardwareTestPlanError("physical hardware test plan readiness flag drifted")
    if any(value is not False for value in (
        evidence.functional_tests_executed,
        evidence.functional_hardware_verified,
        evidence.phone_storage_written,
        evidence.hardware_verified,
        evidence.beta_gate_credit,
    )):
        raise PhysicalHardwareTestPlanError("physical hardware test plan contains unsupported execution/write/hardware/Beta claim")


def load_physical_hardware_test_plan(path: Path) -> PhysicalHardwareTestPlanEvidence:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalHardwareTestPlanError("physical hardware test plan must be a regular non-symlink file")
    try:
        before = source.stat()
        raw = source.read_bytes()
        after = source.stat()
    except OSError as exc:
        raise PhysicalHardwareTestPlanError(f"cannot read physical hardware test plan: {exc}") from exc
    if before.st_size <= 0 or before.st_size > _MAX_PLAN_BYTES or len(raw) != before.st_size:
        raise PhysicalHardwareTestPlanError("physical hardware test plan size is outside the safety limit")
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise PhysicalHardwareTestPlanError("physical hardware test plan changed while being read")
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalHardwareTestPlanError("physical hardware test plan is not valid UTF-8 JSON") from exc
    expected = {item.name for item in fields(PhysicalHardwareTestPlanEvidence)}
    if not isinstance(value, dict) or set(value) != expected or not isinstance(value.get("tests"), list):
        raise PhysicalHardwareTestPlanError("physical hardware test plan fields do not match schema-v1")
    value["tests"] = tuple(value["tests"])
    try:
        evidence = PhysicalHardwareTestPlanEvidence(**value)
        validate_physical_hardware_test_plan(evidence)
    except (TypeError, PhysicalHardwareTestPlanError) as exc:
        raise PhysicalHardwareTestPlanError("physical hardware test plan is invalid") from exc
    if raw != evidence.canonical_json().encode("utf-8"):
        raise PhysicalHardwareTestPlanError("physical hardware test plan is not canonical JSON")
    return evidence


def write_physical_hardware_test_plan(evidence: PhysicalHardwareTestPlanEvidence, destination: Path) -> str:
    validate_physical_hardware_test_plan(evidence)
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise PhysicalHardwareTestPlanError("refusing to overwrite existing physical hardware test plan")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(evidence.canonical_json())
    except OSError as exc:
        raise PhysicalHardwareTestPlanError(f"cannot write physical hardware test plan: {exc}") from exc
    return evidence.evidence_sha256()


def build_physical_hardware_test_plan_from_file(profile: DeviceProfile, review_path: Path) -> PhysicalHardwareTestPlanEvidence:
    try:
        review = load_physical_hardware_review_evidence(review_path)
    except PhysicalHardwareReviewError as exc:
        raise PhysicalHardwareTestPlanError(str(exc)) from exc
    return build_physical_hardware_test_plan(profile, review)
