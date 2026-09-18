"""Fail-closed review boundary for a reversible rootfs handoff strategy design.

This module consumes already captured and independently reviewed physical evidence.
It may accept a *design* for later target binding, but deliberately cannot bind a
block-device path, execute a trial, authorize a persistent write, claim hardware
support, or grant Beta-gate credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any

from .physical_bringup_dossier import (
    PhysicalBringupDossierEvidence,
    PhysicalBringupDossierError,
    validate_physical_bringup_dossier_evidence,
)
from .physical_bringup_dossier_review import (
    PhysicalBringupDossierReviewEvidence,
    PhysicalBringupDossierReviewError,
    validate_physical_bringup_dossier_review_evidence,
)
from .physical_release_gate_audit import (
    PhysicalReleaseGateAuditEvidence,
    PhysicalReleaseGateAuditError,
    validate_physical_release_gate_audit_evidence,
)
from .physical_storage_discovery import (
    PhysicalStorageDiscoveryEvidence,
    PhysicalStorageDiscoveryError,
    validate_physical_storage_discovery_evidence,
)
from .physical_storage_review import (
    PhysicalStorageReviewEvidence,
    PhysicalStorageReviewError,
    validate_physical_storage_review_evidence,
)

_POLICY = "reversible-rootfs-handoff-strategy-review-v1"
_ALLOWED_DECISIONS = frozenset({"accepted_for_trial_design", "rejected"})
_SAFE_REVIEWER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+-]{0,127}$")
_SAFE_ROLE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_MAX_RECORD_BYTES = 512 * 1024
_MAX_NOTES_BYTES = 2 * 1024 * 1024
_MAX_EVIDENCE_BYTES = 2 * 1024 * 1024


class RootfsHandoffStrategyReviewError(ValueError):
    pass


@dataclass(frozen=True)
class RootfsHandoffStrategyReviewRecord:
    schema_version: int
    review_policy: str
    profile_id: str
    device_serial: str
    reviewer: str
    decision: str
    candidate_partition_role: str
    staging_subpath: str
    required_free_bytes: int
    rootfs_artifact_sha256: str
    recovery_plan_sha256: str
    exact_physical_chain_reviewed: bool
    capacity_evidence_reviewed: bool
    filesystem_encryption_reviewed: bool
    rollback_plan_reviewed: bool
    forbidden_partition_policy_reviewed: bool
    no_raw_device_path_reviewed: bool
    no_write_authorization_reviewed: bool
    target_selected: bool
    storage_path_bound: bool
    trial_execution_allowed: bool
    write_authorized: bool
    phone_storage_written: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"


@dataclass(frozen=True)
class RootfsHandoffStrategyReviewEvidence:
    schema_version: int
    review_policy: str
    profile_id: str
    device_serial: str
    firmware_build: str
    firmware_fingerprint: str
    physical_storage_discovery_sha256: str
    physical_storage_review_sha256: str
    physical_bringup_dossier_sha256: str
    physical_bringup_dossier_review_sha256: str
    physical_release_gate_audit_sha256: str
    rootfs_artifact_sha256: str
    rootfs_artifact_size: int
    recovery_plan_sha256: str
    candidate_partition_role: str
    staging_subpath: str
    required_free_bytes: int
    review_record_sha256: str
    review_record_size: int
    review_notes_sha256: str
    review_notes_size: int
    reviewer: str
    decision: str
    exact_physical_chain_reviewed: bool
    capacity_evidence_reviewed: bool
    filesystem_encryption_reviewed: bool
    rollback_plan_reviewed: bool
    forbidden_partition_policy_reviewed: bool
    no_raw_device_path_reviewed: bool
    no_write_authorization_reviewed: bool
    review_checks_complete: bool
    strategy_design_accepted: bool
    manual_target_binding_required: bool
    physical_gate_still_incomplete: bool
    target_selected: bool
    storage_path_bound: bool
    trial_execution_allowed: bool
    write_authorized: bool
    handoff_ready: bool
    persistent_write_performed: bool
    phone_storage_written: bool
    hardware_verified: bool
    beta_release_authorized: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _safe_text(value: object, label: str, maximum: int = 1024) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise RootfsHandoffStrategyReviewError(f"{label} must be non-empty bounded text")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise RootfsHandoffStrategyReviewError(f"{label} contains control data")
    return value


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise RootfsHandoffStrategyReviewError(f"{label} must be a lowercase SHA-256")
    return value


def _positive(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise RootfsHandoffStrategyReviewError(f"{label} must be a positive integer")
    return value


def _safe_role(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_ROLE_RE.fullmatch(value):
        raise RootfsHandoffStrategyReviewError(f"{label} must be a safe logical partition role")
    return value


def _safe_relative_subpath(value: object) -> str:
    text = _safe_text(value, "staging subpath", 512)
    if text.startswith(("/", "\\")) or ":" in text or "\\" in text:
        raise RootfsHandoffStrategyReviewError("staging subpath must not be an absolute/raw device path")
    path = PurePosixPath(text)
    if not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise RootfsHandoffStrategyReviewError("staging subpath must be a safe relative POSIX path")
    return path.as_posix()


def _exact_keys(raw: object, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != expected:
        raise RootfsHandoffStrategyReviewError(f"{label} fields do not match schema-v1")
    return raw


def parse_rootfs_handoff_strategy_review_record(raw: object) -> RootfsHandoffStrategyReviewRecord:
    expected = {item.name for item in fields(RootfsHandoffStrategyReviewRecord)}
    item = _exact_keys(raw, expected, "rootfs handoff strategy review record")
    if item["schema_version"] != 1:
        raise RootfsHandoffStrategyReviewError("unsupported rootfs handoff strategy review record schema")
    if item["review_policy"] != _POLICY:
        raise RootfsHandoffStrategyReviewError("unsupported rootfs handoff strategy review policy")
    reviewer = item["reviewer"]
    if not isinstance(reviewer, str) or not _SAFE_REVIEWER_RE.fullmatch(reviewer):
        raise RootfsHandoffStrategyReviewError("reviewer must be a safe bounded identifier")
    if item["decision"] not in _ALLOWED_DECISIONS:
        raise RootfsHandoffStrategyReviewError("unsupported rootfs handoff strategy decision")
    review_flags = (
        "exact_physical_chain_reviewed",
        "capacity_evidence_reviewed",
        "filesystem_encryption_reviewed",
        "rollback_plan_reviewed",
        "forbidden_partition_policy_reviewed",
        "no_raw_device_path_reviewed",
        "no_write_authorization_reviewed",
    )
    for name in review_flags:
        if not isinstance(item[name], bool):
            raise RootfsHandoffStrategyReviewError(f"{name} must be boolean")
    for name in (
        "target_selected",
        "storage_path_bound",
        "trial_execution_allowed",
        "write_authorized",
        "phone_storage_written",
    ):
        if item[name] is not False:
            raise RootfsHandoffStrategyReviewError(f"strategy design review requires {name}=false")
    return RootfsHandoffStrategyReviewRecord(
        schema_version=1,
        review_policy=_POLICY,
        profile_id=_safe_text(item["profile_id"], "profile id", 128),
        device_serial=_safe_text(item["device_serial"], "device serial", 256),
        reviewer=reviewer,
        decision=item["decision"],
        candidate_partition_role=_safe_role(item["candidate_partition_role"], "candidate partition role"),
        staging_subpath=_safe_relative_subpath(item["staging_subpath"]),
        required_free_bytes=_positive(item["required_free_bytes"], "required free bytes"),
        rootfs_artifact_sha256=_sha(item["rootfs_artifact_sha256"], "rootfs artifact SHA-256"),
        recovery_plan_sha256=_sha(item["recovery_plan_sha256"], "recovery plan SHA-256"),
        exact_physical_chain_reviewed=item["exact_physical_chain_reviewed"],
        capacity_evidence_reviewed=item["capacity_evidence_reviewed"],
        filesystem_encryption_reviewed=item["filesystem_encryption_reviewed"],
        rollback_plan_reviewed=item["rollback_plan_reviewed"],
        forbidden_partition_policy_reviewed=item["forbidden_partition_policy_reviewed"],
        no_raw_device_path_reviewed=item["no_raw_device_path_reviewed"],
        no_write_authorization_reviewed=item["no_write_authorization_reviewed"],
        target_selected=False,
        storage_path_bound=False,
        trial_execution_allowed=False,
        write_authorized=False,
        phone_storage_written=False,
    )


def _read_exact(path: Path, label: str, maximum: int) -> tuple[bytes, str, int]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise RootfsHandoffStrategyReviewError(f"{label} must be a regular non-symlink file")
    before = source.stat()
    raw = source.read_bytes()
    after = source.stat()
    if before.st_size <= 0 or before.st_size > maximum or len(raw) != before.st_size:
        raise RootfsHandoffStrategyReviewError(f"{label} size is outside the safety limit")
    if (before.st_size, before.st_mtime_ns, getattr(before, "st_ino", None)) != (
        after.st_size,
        after.st_mtime_ns,
        getattr(after, "st_ino", None),
    ):
        raise RootfsHandoffStrategyReviewError(f"{label} changed while being read")
    return raw, sha256(raw).hexdigest(), len(raw)


def load_rootfs_handoff_strategy_review_record(path: Path) -> tuple[RootfsHandoffStrategyReviewRecord, str, int]:
    raw, digest, size = _read_exact(path, "rootfs handoff strategy review record", _MAX_RECORD_BYTES)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RootfsHandoffStrategyReviewError("rootfs handoff strategy review record is not valid UTF-8 JSON") from exc
    record = parse_rootfs_handoff_strategy_review_record(value)
    if raw != record.canonical_json().encode("utf-8"):
        raise RootfsHandoffStrategyReviewError("rootfs handoff strategy review record must use canonical JSON bytes")
    return record, digest, size


def read_rootfs_handoff_strategy_review_notes(path: Path) -> tuple[str, int]:
    raw, digest, size = _read_exact(path, "rootfs handoff strategy review notes", _MAX_NOTES_BYTES)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RootfsHandoffStrategyReviewError("rootfs handoff strategy review notes must be UTF-8") from exc
    if not text.strip() or "\x00" in text:
        raise RootfsHandoffStrategyReviewError("rootfs handoff strategy review notes are empty or contain NUL data")
    return digest, size


def _dossier_role_sha(dossier: PhysicalBringupDossierEvidence, role: str) -> str:
    matches = [item.sha256 for item in dossier.files if item.role == role]
    if len(matches) != 1:
        raise RootfsHandoffStrategyReviewError(f"dossier must contain exactly one {role} role")
    return _sha(matches[0], f"dossier {role} SHA-256")


def _validate_upstream(
    discovery: PhysicalStorageDiscoveryEvidence,
    storage_review: PhysicalStorageReviewEvidence,
    dossier: PhysicalBringupDossierEvidence,
    dossier_review: PhysicalBringupDossierReviewEvidence,
    audit: PhysicalReleaseGateAuditEvidence,
) -> None:
    try:
        validate_physical_storage_discovery_evidence(discovery)
        validate_physical_storage_review_evidence(storage_review)
        validate_physical_bringup_dossier_evidence(dossier)
        validate_physical_bringup_dossier_review_evidence(dossier_review)
        validate_physical_release_gate_audit_evidence(audit)
    except (
        PhysicalStorageDiscoveryError,
        PhysicalStorageReviewError,
        PhysicalBringupDossierError,
        PhysicalBringupDossierReviewError,
        PhysicalReleaseGateAuditError,
        ValueError,
    ) as exc:
        raise RootfsHandoffStrategyReviewError(str(exc)) from exc


def bind_rootfs_handoff_strategy_review(
    discovery: PhysicalStorageDiscoveryEvidence,
    storage_review: PhysicalStorageReviewEvidence,
    dossier: PhysicalBringupDossierEvidence,
    dossier_review: PhysicalBringupDossierReviewEvidence,
    audit: PhysicalReleaseGateAuditEvidence,
    review: RootfsHandoffStrategyReviewRecord,
    *,
    review_record_sha256: str,
    review_record_size: int,
    review_notes_sha256: str,
    review_notes_size: int,
) -> RootfsHandoffStrategyReviewEvidence:
    """Bind one reviewed, logical strategy design to one exact physical evidence chain."""
    _validate_upstream(discovery, storage_review, dossier, dossier_review, audit)

    identity = (discovery.profile_id, discovery.device_serial, discovery.firmware_build, discovery.firmware_fingerprint)
    for label, value in (
        ("storage review", (storage_review.profile_id, storage_review.device_serial, storage_review.firmware_build, storage_review.firmware_fingerprint)),
        ("dossier", (dossier.profile_id, dossier.device_serial, dossier.firmware_build, dossier.firmware_fingerprint)),
        ("dossier review", (dossier_review.profile_id, dossier_review.device_serial, dossier_review.firmware_build, dossier_review.firmware_fingerprint)),
        ("release-gate audit", (audit.profile_id, audit.device_serial, audit.firmware_build, audit.firmware_fingerprint)),
    ):
        if value != identity:
            raise RootfsHandoffStrategyReviewError(f"{label} physical identity/firmware drifted from storage discovery")
    if (review.profile_id, review.device_serial) != identity[:2]:
        raise RootfsHandoffStrategyReviewError("strategy review record profile/serial mismatch")

    discovery_sha = discovery.evidence_sha256()
    storage_review_sha = storage_review.evidence_sha256()
    dossier_sha = dossier.evidence_sha256()
    dossier_review_sha = dossier_review.evidence_sha256()
    audit_sha = audit.evidence_sha256()
    for value, label in (
        (discovery_sha, "physical storage discovery"),
        (storage_review_sha, "physical storage review"),
        (dossier_sha, "physical bring-up dossier"),
        (dossier_review_sha, "physical bring-up dossier review"),
        (audit_sha, "physical release-gate audit"),
    ):
        _sha(value, f"{label} SHA-256")

    if storage_review.physical_storage_discovery_sha256 != discovery_sha:
        raise RootfsHandoffStrategyReviewError("storage review is detached from the exact storage discovery")
    if storage_review.accepted_for_strategy_design is not True or storage_review.further_strategy_review_required is not True:
        raise RootfsHandoffStrategyReviewError("strategy review requires an accepted physical storage review")
    if _dossier_role_sha(dossier, "physical_storage_discovery") != discovery_sha:
        raise RootfsHandoffStrategyReviewError("dossier is detached from the exact storage discovery")
    if _dossier_role_sha(dossier, "physical_storage_review") != storage_review_sha:
        raise RootfsHandoffStrategyReviewError("dossier is detached from the exact storage review")
    if dossier.storage_review_accepted_for_strategy_design is not True or dossier.exact_file_set_verified is not True:
        raise RootfsHandoffStrategyReviewError("strategy review requires an exact dossier with accepted storage review")
    if dossier_review.physical_bringup_dossier_sha256 != dossier_sha:
        raise RootfsHandoffStrategyReviewError("dossier review is detached from the exact dossier")
    if dossier_review.accepted_for_strategy_review is not True or dossier_review.separate_strategy_review_required is not True:
        raise RootfsHandoffStrategyReviewError("strategy review requires an accepted independent dossier review")
    if audit.physical_bringup_dossier_sha256 != dossier_sha or audit.dossier_review_sha256 != dossier_review_sha:
        raise RootfsHandoffStrategyReviewError("release-gate audit is detached from the exact dossier/review")
    if not (audit.cross_campaign_context_verified and audit.exact_files_verified and audit.dossier_review_accepted_for_strategy_review):
        raise RootfsHandoffStrategyReviewError("release-gate audit has not verified the exact cross-campaign context")

    forbidden_true = (
        audit.target_selected,
        audit.storage_path_bound,
        audit.write_authorized,
        audit.project_support_claim_authorized,
        audit.persistent_write_performed,
        audit.phone_storage_written,
        audit.hardware_verified,
        audit.beta_release_authorized,
        audit.beta_gate_credit,
    )
    if any(forbidden_true) or audit.physical_gate_still_incomplete is not True:
        raise RootfsHandoffStrategyReviewError("strategy review requires the non-authorizing, still-incomplete physical gate state")

    if review.rootfs_artifact_sha256 != storage_review.rootfs_artifact_sha256:
        raise RootfsHandoffStrategyReviewError("strategy record rootfs artifact does not match the accepted physical chain")
    if review.rootfs_artifact_sha256 != dossier.rootfs_artifact_sha256:
        raise RootfsHandoffStrategyReviewError("strategy record rootfs artifact is detached from the exact dossier")
    if review.recovery_plan_sha256 != storage_review.recovery_plan_sha256:
        raise RootfsHandoffStrategyReviewError("strategy record recovery plan does not match the accepted physical chain")
    if review.required_free_bytes < storage_review.rootfs_artifact_size:
        raise RootfsHandoffStrategyReviewError("required free bytes cannot be smaller than the reviewed rootfs artifact")
    if review.candidate_partition_role != discovery.partition_hint:
        raise RootfsHandoffStrategyReviewError("candidate partition role must match the reviewed profile-driven discovery hint")
    if review.candidate_partition_role in set(discovery.forbidden_partitions):
        raise RootfsHandoffStrategyReviewError("candidate partition role is forbidden by the reviewed discovery contract")

    checks = (
        review.exact_physical_chain_reviewed,
        review.capacity_evidence_reviewed,
        review.filesystem_encryption_reviewed,
        review.rollback_plan_reviewed,
        review.forbidden_partition_policy_reviewed,
        review.no_raw_device_path_reviewed,
        review.no_write_authorization_reviewed,
    )
    checks_complete = all(checks)
    accepted = review.decision == "accepted_for_trial_design" and checks_complete
    if review.decision == "accepted_for_trial_design" and not accepted:
        raise RootfsHandoffStrategyReviewError("cannot accept strategy design until every mandatory review check is complete")

    evidence = RootfsHandoffStrategyReviewEvidence(
        schema_version=1,
        review_policy=_POLICY,
        profile_id=identity[0],
        device_serial=identity[1],
        firmware_build=identity[2],
        firmware_fingerprint=identity[3],
        physical_storage_discovery_sha256=discovery_sha,
        physical_storage_review_sha256=storage_review_sha,
        physical_bringup_dossier_sha256=dossier_sha,
        physical_bringup_dossier_review_sha256=dossier_review_sha,
        physical_release_gate_audit_sha256=audit_sha,
        rootfs_artifact_sha256=storage_review.rootfs_artifact_sha256,
        rootfs_artifact_size=storage_review.rootfs_artifact_size,
        recovery_plan_sha256=storage_review.recovery_plan_sha256,
        candidate_partition_role=review.candidate_partition_role,
        staging_subpath=review.staging_subpath,
        required_free_bytes=review.required_free_bytes,
        review_record_sha256=_sha(review_record_sha256, "strategy review record SHA-256"),
        review_record_size=_positive(review_record_size, "strategy review record size"),
        review_notes_sha256=_sha(review_notes_sha256, "strategy review notes SHA-256"),
        review_notes_size=_positive(review_notes_size, "strategy review notes size"),
        reviewer=review.reviewer,
        decision=review.decision,
        exact_physical_chain_reviewed=review.exact_physical_chain_reviewed,
        capacity_evidence_reviewed=review.capacity_evidence_reviewed,
        filesystem_encryption_reviewed=review.filesystem_encryption_reviewed,
        rollback_plan_reviewed=review.rollback_plan_reviewed,
        forbidden_partition_policy_reviewed=review.forbidden_partition_policy_reviewed,
        no_raw_device_path_reviewed=review.no_raw_device_path_reviewed,
        no_write_authorization_reviewed=review.no_write_authorization_reviewed,
        review_checks_complete=checks_complete,
        strategy_design_accepted=accepted,
        manual_target_binding_required=True,
        physical_gate_still_incomplete=True,
        target_selected=False,
        storage_path_bound=False,
        trial_execution_allowed=False,
        write_authorized=False,
        handoff_ready=False,
        persistent_write_performed=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_release_authorized=False,
        beta_gate_credit=False,
    )
    validate_rootfs_handoff_strategy_review_evidence(evidence)
    return evidence


def validate_rootfs_handoff_strategy_review_evidence(evidence: RootfsHandoffStrategyReviewEvidence) -> None:
    if not isinstance(evidence, RootfsHandoffStrategyReviewEvidence) or evidence.schema_version != 1:
        raise RootfsHandoffStrategyReviewError("rootfs handoff strategy review must be schema-v1 typed evidence")
    if evidence.review_policy != _POLICY:
        raise RootfsHandoffStrategyReviewError("rootfs handoff strategy review policy mismatch")
    _safe_text(evidence.profile_id, "profile id", 128)
    _safe_text(evidence.device_serial, "device serial", 256)
    _safe_text(evidence.firmware_build, "firmware build", 512)
    _safe_text(evidence.firmware_fingerprint, "firmware fingerprint", 1024)
    if not _SAFE_REVIEWER_RE.fullmatch(evidence.reviewer):
        raise RootfsHandoffStrategyReviewError("reviewer identifier is invalid")
    if evidence.decision not in _ALLOWED_DECISIONS:
        raise RootfsHandoffStrategyReviewError("strategy review decision is unsupported")
    for value, label in (
        (evidence.physical_storage_discovery_sha256, "storage discovery"),
        (evidence.physical_storage_review_sha256, "storage review"),
        (evidence.physical_bringup_dossier_sha256, "bring-up dossier"),
        (evidence.physical_bringup_dossier_review_sha256, "dossier review"),
        (evidence.physical_release_gate_audit_sha256, "release-gate audit"),
        (evidence.rootfs_artifact_sha256, "rootfs artifact"),
        (evidence.recovery_plan_sha256, "recovery plan"),
        (evidence.review_record_sha256, "review record"),
        (evidence.review_notes_sha256, "review notes"),
    ):
        _sha(value, f"{label} SHA-256")
    _positive(evidence.rootfs_artifact_size, "rootfs artifact size")
    _positive(evidence.required_free_bytes, "required free bytes")
    _positive(evidence.review_record_size, "review record size")
    _positive(evidence.review_notes_size, "review notes size")
    _safe_role(evidence.candidate_partition_role, "candidate partition role")
    if evidence.staging_subpath != _safe_relative_subpath(evidence.staging_subpath):
        raise RootfsHandoffStrategyReviewError("staging subpath is not canonical")
    for name in (
        "exact_physical_chain_reviewed",
        "capacity_evidence_reviewed",
        "filesystem_encryption_reviewed",
        "rollback_plan_reviewed",
        "forbidden_partition_policy_reviewed",
        "no_raw_device_path_reviewed",
        "no_write_authorization_reviewed",
        "review_checks_complete",
        "strategy_design_accepted",
        "manual_target_binding_required",
        "physical_gate_still_incomplete",
        "target_selected",
        "storage_path_bound",
        "trial_execution_allowed",
        "write_authorized",
        "handoff_ready",
        "persistent_write_performed",
        "phone_storage_written",
        "hardware_verified",
        "beta_release_authorized",
        "beta_gate_credit",
    ):
        if not isinstance(getattr(evidence, name), bool):
            raise RootfsHandoffStrategyReviewError(f"{name} must be boolean")
    if evidence.review_checks_complete != all((
        evidence.exact_physical_chain_reviewed,
        evidence.capacity_evidence_reviewed,
        evidence.filesystem_encryption_reviewed,
        evidence.rollback_plan_reviewed,
        evidence.forbidden_partition_policy_reviewed,
        evidence.no_raw_device_path_reviewed,
        evidence.no_write_authorization_reviewed,
    )):
        raise RootfsHandoffStrategyReviewError("strategy review completion flag does not match review checks")
    expected_accepted = evidence.decision == "accepted_for_trial_design" and evidence.review_checks_complete
    if evidence.strategy_design_accepted != expected_accepted:
        raise RootfsHandoffStrategyReviewError("strategy design acceptance does not match decision/checks")
    if evidence.manual_target_binding_required is not True or evidence.physical_gate_still_incomplete is not True:
        raise RootfsHandoffStrategyReviewError("strategy design must remain manually target-bound with incomplete physical gate")
    for name in (
        "target_selected",
        "storage_path_bound",
        "trial_execution_allowed",
        "write_authorized",
        "handoff_ready",
        "persistent_write_performed",
        "phone_storage_written",
        "hardware_verified",
        "beta_release_authorized",
        "beta_gate_credit",
    ):
        if getattr(evidence, name) is not False:
            raise RootfsHandoffStrategyReviewError(f"strategy design review cannot promote {name}")


def write_rootfs_handoff_strategy_review_evidence(
    evidence: RootfsHandoffStrategyReviewEvidence,
    destination: Path,
) -> str:
    validate_rootfs_handoff_strategy_review_evidence(evidence)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise RootfsHandoffStrategyReviewError("refusing to overwrite existing strategy review evidence")
    destination.parent.mkdir(parents=True, exist_ok=True)
    text = evidence.canonical_json()
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return sha256(text.encode("utf-8")).hexdigest()


def load_rootfs_handoff_strategy_review_evidence(path: Path) -> RootfsHandoffStrategyReviewEvidence:
    raw, digest, _ = _read_exact(path, "rootfs handoff strategy review evidence", _MAX_EVIDENCE_BYTES)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RootfsHandoffStrategyReviewError("rootfs handoff strategy review evidence is not valid UTF-8 JSON") from exc
    expected = {item.name for item in fields(RootfsHandoffStrategyReviewEvidence)}
    item = _exact_keys(value, expected, "rootfs handoff strategy review evidence")
    try:
        evidence = RootfsHandoffStrategyReviewEvidence(**item)
    except TypeError as exc:
        raise RootfsHandoffStrategyReviewError("rootfs handoff strategy review evidence types are invalid") from exc
    validate_rootfs_handoff_strategy_review_evidence(evidence)
    canonical = evidence.canonical_json().encode("utf-8")
    if raw != canonical or digest != sha256(canonical).hexdigest():
        raise RootfsHandoffStrategyReviewError("rootfs handoff strategy review evidence is not canonical")
    return evidence
