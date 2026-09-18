"""Fail-closed manual authorization review before any rootfs trial executor.

This module is deliberately offline and non-executing. It consumes one accepted
logical target-binding review and one distinct-capture fresh-device revalidation,
then lets an independent reviewer decide whether that exact evidence chain is
ready to be handed to a later *interactive* trial-execution boundary.

Even an accepted authorization does not carry a raw block-device path or mount
target, does not contact a phone, does not mount/copy/write storage, does not
execute the trial, and does not grant storage/recovery/hardware/Beta credit.
The later executor must bind the same evidence again, re-check live device state
and require explicit operator interaction before any write-capable action.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any

from .rootfs_handoff_fresh_revalidation import (
    RootfsHandoffFreshRevalidationError,
    RootfsHandoffFreshRevalidationEvidence,
    load_rootfs_handoff_fresh_revalidation_evidence,
    validate_rootfs_handoff_fresh_revalidation_evidence,
)
from .rootfs_handoff_target_binding import (
    RootfsHandoffTargetBindingError,
    RootfsHandoffTargetBindingEvidence,
    load_rootfs_handoff_target_binding_evidence,
    validate_rootfs_handoff_target_binding_evidence,
)

_POLICY = "rootfs-handoff-manual-trial-authorization-v1"
_ALLOWED_DECISIONS = frozenset({"accepted_for_interactive_execution_boundary", "rejected"})
_ALLOWED_ENCRYPTION_STATES = frozenset({"unlocked", "unencrypted"})
_SAFE_REVIEWER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+-]{0,127}$")
_SAFE_ROLE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
_SAFE_FS_RE = re.compile(r"^[a-z0-9][a-z0-9._+-]{0,31}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_RECORD_BYTES = 512 * 1024
_MAX_NOTES_BYTES = 2 * 1024 * 1024
_MAX_EVIDENCE_BYTES = 2 * 1024 * 1024

_REVIEW_FLAGS = (
    "exact_target_binding_reviewed",
    "exact_fresh_revalidation_reviewed",
    "logical_identity_reviewed",
    "filesystem_encryption_capacity_reviewed",
    "rootfs_identity_reviewed",
    "recovery_plan_reviewed",
    "staging_subpath_reviewed",
    "rollback_limitations_reviewed",
    "explicit_operator_interaction_reviewed",
    "no_automatic_execution_reviewed",
    "no_raw_path_in_evidence_reviewed",
    "no_persistent_write_authorization_reviewed",
)

_FORBIDDEN_RECORD_FLAGS = (
    "raw_device_path_bound",
    "mount_target_bound",
    "trial_execution_allowed",
    "persistent_write_authorized",
    "phone_storage_written",
)

_FORBIDDEN_EVIDENCE_FLAGS = (
    "raw_device_path_bound",
    "mount_target_bound",
    "trial_execution_allowed",
    "persistent_write_authorized",
    "handoff_ready",
    "persistent_write_performed",
    "phone_storage_written",
    "storage_verified",
    "recovery_verified",
    "hardware_verified",
    "beta_release_authorized",
    "beta_gate_credit",
)


class RootfsHandoffTrialAuthorizationError(ValueError):
    """Raised when manual trial authorization evidence fails closed."""


@dataclass(frozen=True)
class RootfsHandoffTrialAuthorizationReviewRecord:
    schema_version: int
    review_policy: str
    profile_id: str
    device_serial: str
    reviewer: str
    decision: str
    target_binding_sha256: str
    fresh_revalidation_sha256: str
    candidate_partition_role: str
    observed_kernel_name: str
    observed_filesystem: str
    observed_encryption_state: str
    observed_free_bytes: int
    required_free_bytes: int
    staging_subpath: str
    rootfs_artifact_sha256: str
    rootfs_artifact_size: int
    recovery_plan_sha256: str
    exact_target_binding_reviewed: bool
    exact_fresh_revalidation_reviewed: bool
    logical_identity_reviewed: bool
    filesystem_encryption_capacity_reviewed: bool
    rootfs_identity_reviewed: bool
    recovery_plan_reviewed: bool
    staging_subpath_reviewed: bool
    rollback_limitations_reviewed: bool
    explicit_operator_interaction_reviewed: bool
    no_automatic_execution_reviewed: bool
    no_raw_path_in_evidence_reviewed: bool
    no_persistent_write_authorization_reviewed: bool
    raw_device_path_bound: bool
    mount_target_bound: bool
    trial_execution_allowed: bool
    persistent_write_authorized: bool
    phone_storage_written: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"


@dataclass(frozen=True)
class RootfsHandoffTrialAuthorizationEvidence:
    schema_version: int
    authorization_policy: str
    profile_id: str
    device_serial: str
    firmware_build: str
    firmware_fingerprint: str
    target_binding_sha256: str
    fresh_revalidation_sha256: str
    candidate_partition_role: str
    observed_kernel_name: str
    observed_filesystem: str
    observed_encryption_state: str
    observed_free_bytes: int
    required_free_bytes: int
    staging_subpath: str
    rootfs_artifact_sha256: str
    rootfs_artifact_size: int
    recovery_plan_sha256: str
    review_record_sha256: str
    review_record_size: int
    review_notes_sha256: str
    review_notes_size: int
    reviewer: str
    decision: str
    exact_target_binding_reviewed: bool
    exact_fresh_revalidation_reviewed: bool
    logical_identity_reviewed: bool
    filesystem_encryption_capacity_reviewed: bool
    rootfs_identity_reviewed: bool
    recovery_plan_reviewed: bool
    staging_subpath_reviewed: bool
    rollback_limitations_reviewed: bool
    explicit_operator_interaction_reviewed: bool
    no_automatic_execution_reviewed: bool
    no_raw_path_in_evidence_reviewed: bool
    no_persistent_write_authorization_reviewed: bool
    review_checks_complete: bool
    manual_trial_authorization_accepted: bool
    ready_for_interactive_trial_execution_boundary: bool
    live_device_recheck_required_at_execution: bool
    explicit_operator_confirmation_required_at_execution: bool
    execution_boundary_required: bool
    physical_gate_still_incomplete: bool
    raw_device_path_bound: bool
    mount_target_bound: bool
    trial_execution_allowed: bool
    persistent_write_authorized: bool
    handoff_ready: bool
    persistent_write_performed: bool
    phone_storage_written: bool
    storage_verified: bool
    recovery_verified: bool
    hardware_verified: bool
    beta_release_authorized: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise RootfsHandoffTrialAuthorizationError(f"{label} must be a lowercase SHA-256")
    return value


def _safe_text(value: object, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise RootfsHandoffTrialAuthorizationError(f"{label} must be non-empty bounded text")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise RootfsHandoffTrialAuthorizationError(f"{label} contains control data")
    return value


def _positive(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise RootfsHandoffTrialAuthorizationError(f"{label} must be a positive integer")
    return value


def _safe_relative_subpath(value: object) -> str:
    text = _safe_text(value, "staging subpath", 512)
    if text.startswith(("/", "\\")) or ":" in text or "\\" in text:
        raise RootfsHandoffTrialAuthorizationError("staging subpath must be relative and path-independent")
    path = PurePosixPath(text)
    if not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise RootfsHandoffTrialAuthorizationError("staging subpath must be a safe relative POSIX path")
    return path.as_posix()


def _read_exact(path: Path, label: str, maximum: int) -> tuple[bytes, str, int]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise RootfsHandoffTrialAuthorizationError(f"{label} must be a regular non-symlink file")
    try:
        before = source.stat()
        if before.st_size <= 0 or before.st_size > maximum:
            raise RootfsHandoffTrialAuthorizationError(f"{label} size is outside the safety limit")
        raw = source.read_bytes()
        after = source.stat()
    except OSError as exc:
        raise RootfsHandoffTrialAuthorizationError(f"cannot read {label}: {exc}") from exc
    if len(raw) != before.st_size:
        raise RootfsHandoffTrialAuthorizationError(f"{label} size changed while being read")
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or getattr(before, "st_ino", None) != getattr(after, "st_ino", None)
    ):
        raise RootfsHandoffTrialAuthorizationError(f"{label} changed while being read")
    return raw, sha256(raw).hexdigest(), len(raw)


def _exact_keys(raw: object, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != expected:
        raise RootfsHandoffTrialAuthorizationError(f"{label} fields do not match schema-v1")
    return raw


def _validate_chain(
    binding: RootfsHandoffTargetBindingEvidence,
    revalidation: RootfsHandoffFreshRevalidationEvidence,
) -> None:
    try:
        validate_rootfs_handoff_target_binding_evidence(binding)
        validate_rootfs_handoff_fresh_revalidation_evidence(revalidation)
    except (RootfsHandoffTargetBindingError, RootfsHandoffFreshRevalidationError) as exc:
        raise RootfsHandoffTrialAuthorizationError(str(exc)) from exc

    if binding.decision != "accepted_for_manual_trial":
        raise RootfsHandoffTrialAuthorizationError("trial authorization requires an accepted target binding")
    if binding.logical_target_identity_bound is not True:
        raise RootfsHandoffTrialAuthorizationError("target binding is not logically bound")
    if revalidation.fresh_device_revalidated is not True:
        raise RootfsHandoffTrialAuthorizationError("trial authorization requires successful fresh-device revalidation")
    if revalidation.ready_for_separate_manual_trial_authorization is not True:
        raise RootfsHandoffTrialAuthorizationError("fresh revalidation is not eligible for manual trial authorization")
    if revalidation.target_binding_sha256 != binding.evidence_sha256():
        raise RootfsHandoffTrialAuthorizationError("fresh revalidation is detached from supplied target binding")

    pairs = (
        ("profile", revalidation.profile_id, binding.profile_id),
        ("device serial", revalidation.device_serial, binding.device_serial),
        ("firmware build", revalidation.firmware_build, binding.firmware_build),
        ("firmware fingerprint", revalidation.firmware_fingerprint, binding.firmware_fingerprint),
        ("partition role", revalidation.candidate_partition_role, binding.candidate_partition_role),
        ("kernel name", revalidation.observed_kernel_name, binding.observed_kernel_name),
        ("filesystem", revalidation.observed_filesystem, binding.observed_filesystem),
        ("encryption state", revalidation.observed_encryption_state, binding.observed_encryption_state),
        ("required free bytes", revalidation.required_free_bytes, binding.required_free_bytes),
        ("staging subpath", revalidation.staging_subpath, binding.staging_subpath),
        ("rootfs artifact", revalidation.rootfs_artifact_sha256, binding.rootfs_artifact_sha256),
        ("rootfs artifact size", revalidation.rootfs_artifact_size, binding.rootfs_artifact_size),
        ("recovery plan", revalidation.recovery_plan_sha256, binding.recovery_plan_sha256),
    )
    for label, current, expected in pairs:
        if current != expected:
            raise RootfsHandoffTrialAuthorizationError(f"{label} drifted between target binding and fresh revalidation")

    if revalidation.observed_free_bytes < binding.required_free_bytes:
        raise RootfsHandoffTrialAuthorizationError("fresh revalidation capacity is below the accepted requirement")
    if revalidation.observed_encryption_state not in _ALLOWED_ENCRYPTION_STATES:
        raise RootfsHandoffTrialAuthorizationError("fresh revalidation encryption state is not acceptable")

    for name in _FORBIDDEN_EVIDENCE_FLAGS:
        if hasattr(revalidation, name) and getattr(revalidation, name) is not False:
            raise RootfsHandoffTrialAuthorizationError(f"fresh revalidation requires {name}=false")


def prepare_rootfs_handoff_trial_authorization_review_record(
    target_binding_path: Path,
    fresh_revalidation_path: Path,
    reviewer: str,
) -> RootfsHandoffTrialAuthorizationReviewRecord:
    if not isinstance(reviewer, str) or not _SAFE_REVIEWER_RE.fullmatch(reviewer):
        raise RootfsHandoffTrialAuthorizationError("reviewer must be a safe bounded identifier")
    try:
        binding = load_rootfs_handoff_target_binding_evidence(Path(target_binding_path))
        revalidation = load_rootfs_handoff_fresh_revalidation_evidence(Path(fresh_revalidation_path))
    except (RootfsHandoffTargetBindingError, RootfsHandoffFreshRevalidationError) as exc:
        raise RootfsHandoffTrialAuthorizationError(str(exc)) from exc
    _validate_chain(binding, revalidation)

    record = RootfsHandoffTrialAuthorizationReviewRecord(
        schema_version=1,
        review_policy=_POLICY,
        profile_id=binding.profile_id,
        device_serial=binding.device_serial,
        reviewer=reviewer,
        decision="rejected",
        target_binding_sha256=binding.evidence_sha256(),
        fresh_revalidation_sha256=revalidation.evidence_sha256(),
        candidate_partition_role=binding.candidate_partition_role,
        observed_kernel_name=binding.observed_kernel_name,
        observed_filesystem=binding.observed_filesystem,
        observed_encryption_state=revalidation.observed_encryption_state,
        observed_free_bytes=revalidation.observed_free_bytes,
        required_free_bytes=binding.required_free_bytes,
        staging_subpath=binding.staging_subpath,
        rootfs_artifact_sha256=binding.rootfs_artifact_sha256,
        rootfs_artifact_size=binding.rootfs_artifact_size,
        recovery_plan_sha256=binding.recovery_plan_sha256,
        exact_target_binding_reviewed=False,
        exact_fresh_revalidation_reviewed=False,
        logical_identity_reviewed=False,
        filesystem_encryption_capacity_reviewed=False,
        rootfs_identity_reviewed=False,
        recovery_plan_reviewed=False,
        staging_subpath_reviewed=False,
        rollback_limitations_reviewed=False,
        explicit_operator_interaction_reviewed=False,
        no_automatic_execution_reviewed=False,
        no_raw_path_in_evidence_reviewed=False,
        no_persistent_write_authorization_reviewed=False,
        raw_device_path_bound=False,
        mount_target_bound=False,
        trial_execution_allowed=False,
        persistent_write_authorized=False,
        phone_storage_written=False,
    )
    return parse_rootfs_handoff_trial_authorization_review_record(json.loads(record.canonical_json()))


def parse_rootfs_handoff_trial_authorization_review_record(
    raw: object,
) -> RootfsHandoffTrialAuthorizationReviewRecord:
    item = _exact_keys(
        raw,
        {field.name for field in fields(RootfsHandoffTrialAuthorizationReviewRecord)},
        "rootfs handoff trial authorization review record",
    )
    if item["schema_version"] != 1 or item["review_policy"] != _POLICY:
        raise RootfsHandoffTrialAuthorizationError("unsupported trial authorization review schema/policy")
    reviewer = item["reviewer"]
    if not isinstance(reviewer, str) or not _SAFE_REVIEWER_RE.fullmatch(reviewer):
        raise RootfsHandoffTrialAuthorizationError("reviewer must be a safe bounded identifier")
    if item["decision"] not in _ALLOWED_DECISIONS:
        raise RootfsHandoffTrialAuthorizationError("unsupported trial authorization decision")
    profile_id = _safe_text(item["profile_id"], "profile id", 128)
    device_serial = _safe_text(item["device_serial"], "device serial", 256)
    if "/" not in profile_id:
        raise RootfsHandoffTrialAuthorizationError("profile id must use vendor/codename form")
    role = item["candidate_partition_role"]
    if not isinstance(role, str) or not _SAFE_ROLE_RE.fullmatch(role):
        raise RootfsHandoffTrialAuthorizationError("candidate partition role is invalid")
    kernel = item["observed_kernel_name"]
    if not isinstance(kernel, str) or not _SAFE_NAME_RE.fullmatch(kernel):
        raise RootfsHandoffTrialAuthorizationError("observed kernel name is invalid")
    filesystem = item["observed_filesystem"]
    if not isinstance(filesystem, str) or not _SAFE_FS_RE.fullmatch(filesystem):
        raise RootfsHandoffTrialAuthorizationError("observed filesystem is invalid")
    encryption = _safe_text(item["observed_encryption_state"], "observed encryption state", 32)
    if encryption not in _ALLOWED_ENCRYPTION_STATES:
        raise RootfsHandoffTrialAuthorizationError("observed encryption state is not eligible for a trial")
    observed_free = _positive(item["observed_free_bytes"], "observed free bytes")
    required_free = _positive(item["required_free_bytes"], "required free bytes")
    if observed_free < required_free:
        raise RootfsHandoffTrialAuthorizationError("observed free bytes are below required free bytes")
    staging = _safe_relative_subpath(item["staging_subpath"])
    rootfs_size = _positive(item["rootfs_artifact_size"], "rootfs artifact size")
    target_sha = _sha(item["target_binding_sha256"], "target binding")
    fresh_sha = _sha(item["fresh_revalidation_sha256"], "fresh revalidation")
    rootfs_sha = _sha(item["rootfs_artifact_sha256"], "rootfs artifact")
    recovery_sha = _sha(item["recovery_plan_sha256"], "recovery plan")
    for name in _REVIEW_FLAGS:
        if not isinstance(item[name], bool):
            raise RootfsHandoffTrialAuthorizationError(f"{name} must be boolean")
    for name in _FORBIDDEN_RECORD_FLAGS:
        if item[name] is not False:
            raise RootfsHandoffTrialAuthorizationError(f"trial authorization review requires {name}=false")

    return RootfsHandoffTrialAuthorizationReviewRecord(
        schema_version=1,
        review_policy=_POLICY,
        profile_id=profile_id,
        device_serial=device_serial,
        reviewer=reviewer,
        decision=item["decision"],
        target_binding_sha256=target_sha,
        fresh_revalidation_sha256=fresh_sha,
        candidate_partition_role=role,
        observed_kernel_name=kernel,
        observed_filesystem=filesystem,
        observed_encryption_state=encryption,
        observed_free_bytes=observed_free,
        required_free_bytes=required_free,
        staging_subpath=staging,
        rootfs_artifact_sha256=rootfs_sha,
        rootfs_artifact_size=rootfs_size,
        recovery_plan_sha256=recovery_sha,
        **{name: item[name] for name in _REVIEW_FLAGS},
        raw_device_path_bound=False,
        mount_target_bound=False,
        trial_execution_allowed=False,
        persistent_write_authorized=False,
        phone_storage_written=False,
    )


def load_rootfs_handoff_trial_authorization_review_record(
    path: Path,
) -> tuple[RootfsHandoffTrialAuthorizationReviewRecord, str, int]:
    raw, digest, size = _read_exact(path, "trial authorization review record", _MAX_RECORD_BYTES)
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RootfsHandoffTrialAuthorizationError("trial authorization review record is not valid UTF-8 JSON") from exc
    record = parse_rootfs_handoff_trial_authorization_review_record(value)
    if raw != record.canonical_json().encode("utf-8"):
        raise RootfsHandoffTrialAuthorizationError("trial authorization review record is not canonical JSON")
    return record, digest, size


def read_rootfs_handoff_trial_authorization_review_notes(path: Path) -> tuple[str, int]:
    raw, digest, size = _read_exact(path, "trial authorization review notes", _MAX_NOTES_BYTES)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RootfsHandoffTrialAuthorizationError("trial authorization review notes must be UTF-8") from exc
    if not text.strip() or "\x00" in text:
        raise RootfsHandoffTrialAuthorizationError("trial authorization review notes are empty or contain NUL data")
    return digest, size


def bind_rootfs_handoff_trial_authorization_review(
    target_binding_path: Path,
    fresh_revalidation_path: Path,
    review_record_path: Path,
    review_notes_path: Path,
) -> RootfsHandoffTrialAuthorizationEvidence:
    try:
        binding = load_rootfs_handoff_target_binding_evidence(Path(target_binding_path))
        revalidation = load_rootfs_handoff_fresh_revalidation_evidence(Path(fresh_revalidation_path))
    except (RootfsHandoffTargetBindingError, RootfsHandoffFreshRevalidationError) as exc:
        raise RootfsHandoffTrialAuthorizationError(str(exc)) from exc
    _validate_chain(binding, revalidation)
    record, record_sha, record_size = load_rootfs_handoff_trial_authorization_review_record(
        Path(review_record_path)
    )
    notes_sha, notes_size = read_rootfs_handoff_trial_authorization_review_notes(Path(review_notes_path))

    expected = {
        "profile_id": binding.profile_id,
        "device_serial": binding.device_serial,
        "target_binding_sha256": binding.evidence_sha256(),
        "fresh_revalidation_sha256": revalidation.evidence_sha256(),
        "candidate_partition_role": binding.candidate_partition_role,
        "observed_kernel_name": binding.observed_kernel_name,
        "observed_filesystem": binding.observed_filesystem,
        "observed_encryption_state": revalidation.observed_encryption_state,
        "observed_free_bytes": revalidation.observed_free_bytes,
        "required_free_bytes": binding.required_free_bytes,
        "staging_subpath": binding.staging_subpath,
        "rootfs_artifact_sha256": binding.rootfs_artifact_sha256,
        "rootfs_artifact_size": binding.rootfs_artifact_size,
        "recovery_plan_sha256": binding.recovery_plan_sha256,
    }
    for name, value in expected.items():
        if getattr(record, name) != value:
            raise RootfsHandoffTrialAuthorizationError(f"review record {name} drifted from exact evidence chain")

    checks_complete = all(getattr(record, name) is True for name in _REVIEW_FLAGS)
    accepted = record.decision == "accepted_for_interactive_execution_boundary"
    if accepted and not checks_complete:
        raise RootfsHandoffTrialAuthorizationError(
            "accepted trial authorization requires every review check to be true"
        )

    evidence = RootfsHandoffTrialAuthorizationEvidence(
        schema_version=1,
        authorization_policy=_POLICY,
        profile_id=binding.profile_id,
        device_serial=binding.device_serial,
        firmware_build=binding.firmware_build,
        firmware_fingerprint=binding.firmware_fingerprint,
        target_binding_sha256=binding.evidence_sha256(),
        fresh_revalidation_sha256=revalidation.evidence_sha256(),
        candidate_partition_role=binding.candidate_partition_role,
        observed_kernel_name=binding.observed_kernel_name,
        observed_filesystem=binding.observed_filesystem,
        observed_encryption_state=revalidation.observed_encryption_state,
        observed_free_bytes=revalidation.observed_free_bytes,
        required_free_bytes=binding.required_free_bytes,
        staging_subpath=binding.staging_subpath,
        rootfs_artifact_sha256=binding.rootfs_artifact_sha256,
        rootfs_artifact_size=binding.rootfs_artifact_size,
        recovery_plan_sha256=binding.recovery_plan_sha256,
        review_record_sha256=record_sha,
        review_record_size=record_size,
        review_notes_sha256=notes_sha,
        review_notes_size=notes_size,
        reviewer=record.reviewer,
        decision=record.decision,
        **{name: getattr(record, name) for name in _REVIEW_FLAGS},
        review_checks_complete=checks_complete,
        manual_trial_authorization_accepted=accepted and checks_complete,
        ready_for_interactive_trial_execution_boundary=accepted and checks_complete,
        live_device_recheck_required_at_execution=True,
        explicit_operator_confirmation_required_at_execution=True,
        execution_boundary_required=True,
        physical_gate_still_incomplete=True,
        raw_device_path_bound=False,
        mount_target_bound=False,
        trial_execution_allowed=False,
        persistent_write_authorized=False,
        handoff_ready=False,
        persistent_write_performed=False,
        phone_storage_written=False,
        storage_verified=False,
        recovery_verified=False,
        hardware_verified=False,
        beta_release_authorized=False,
        beta_gate_credit=False,
    )
    validate_rootfs_handoff_trial_authorization_evidence(evidence)
    return evidence


def validate_rootfs_handoff_trial_authorization_evidence(
    evidence: RootfsHandoffTrialAuthorizationEvidence,
) -> None:
    if not isinstance(evidence, RootfsHandoffTrialAuthorizationEvidence) or evidence.schema_version != 1:
        raise RootfsHandoffTrialAuthorizationError("trial authorization must be schema-v1 typed evidence")
    if evidence.authorization_policy != _POLICY:
        raise RootfsHandoffTrialAuthorizationError("trial authorization policy is unsupported")
    if "/" not in _safe_text(evidence.profile_id, "profile id", 128):
        raise RootfsHandoffTrialAuthorizationError("profile id must use vendor/codename form")
    _safe_text(evidence.device_serial, "device serial", 256)
    _safe_text(evidence.firmware_build, "firmware build", 256)
    _safe_text(evidence.firmware_fingerprint, "firmware fingerprint", 1024)
    for value, label in (
        (evidence.target_binding_sha256, "target binding"),
        (evidence.fresh_revalidation_sha256, "fresh revalidation"),
        (evidence.rootfs_artifact_sha256, "rootfs artifact"),
        (evidence.recovery_plan_sha256, "recovery plan"),
        (evidence.review_record_sha256, "review record"),
        (evidence.review_notes_sha256, "review notes"),
    ):
        _sha(value, label)
    _positive(evidence.review_record_size, "review record size")
    _positive(evidence.review_notes_size, "review notes size")
    _positive(evidence.observed_free_bytes, "observed free bytes")
    _positive(evidence.required_free_bytes, "required free bytes")
    _positive(evidence.rootfs_artifact_size, "rootfs artifact size")
    if evidence.observed_free_bytes < evidence.required_free_bytes:
        raise RootfsHandoffTrialAuthorizationError("authorized evidence capacity is below requirement")
    _safe_relative_subpath(evidence.staging_subpath)
    if evidence.observed_encryption_state not in _ALLOWED_ENCRYPTION_STATES:
        raise RootfsHandoffTrialAuthorizationError("authorized evidence encryption state is invalid")
    if evidence.decision not in _ALLOWED_DECISIONS:
        raise RootfsHandoffTrialAuthorizationError("trial authorization decision is unsupported")
    if not isinstance(evidence.reviewer, str) or not _SAFE_REVIEWER_RE.fullmatch(evidence.reviewer):
        raise RootfsHandoffTrialAuthorizationError("reviewer must be a safe bounded identifier")
    for name in _REVIEW_FLAGS:
        if not isinstance(getattr(evidence, name), bool):
            raise RootfsHandoffTrialAuthorizationError(f"{name} must be boolean")
    if evidence.review_checks_complete is not all(getattr(evidence, name) for name in _REVIEW_FLAGS):
        raise RootfsHandoffTrialAuthorizationError("review_checks_complete is inconsistent with review flags")
    accepted = evidence.decision == "accepted_for_interactive_execution_boundary"
    if evidence.manual_trial_authorization_accepted is not (accepted and evidence.review_checks_complete):
        raise RootfsHandoffTrialAuthorizationError("manual_trial_authorization_accepted is inconsistent")
    if evidence.ready_for_interactive_trial_execution_boundary is not evidence.manual_trial_authorization_accepted:
        raise RootfsHandoffTrialAuthorizationError("execution-boundary readiness is inconsistent")
    for name in (
        "live_device_recheck_required_at_execution",
        "explicit_operator_confirmation_required_at_execution",
        "execution_boundary_required",
        "physical_gate_still_incomplete",
    ):
        if getattr(evidence, name) is not True:
            raise RootfsHandoffTrialAuthorizationError(f"trial authorization requires {name}=true")
    for name in _FORBIDDEN_EVIDENCE_FLAGS:
        if getattr(evidence, name) is not False:
            raise RootfsHandoffTrialAuthorizationError(f"trial authorization requires {name}=false")


def write_rootfs_handoff_trial_authorization_evidence(
    evidence: RootfsHandoffTrialAuthorizationEvidence,
    destination: Path,
) -> str:
    validate_rootfs_handoff_trial_authorization_evidence(evidence)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise RootfsHandoffTrialAuthorizationError(f"refusing to overwrite existing output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = evidence.canonical_json()
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
    return evidence.evidence_sha256()


def load_rootfs_handoff_trial_authorization_evidence(
    path: Path,
) -> RootfsHandoffTrialAuthorizationEvidence:
    raw, _digest, _size = _read_exact(path, "trial authorization evidence", _MAX_EVIDENCE_BYTES)
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RootfsHandoffTrialAuthorizationError("trial authorization evidence is not valid UTF-8 JSON") from exc
    item = _exact_keys(
        value,
        {field.name for field in fields(RootfsHandoffTrialAuthorizationEvidence)},
        "trial authorization evidence",
    )
    try:
        evidence = RootfsHandoffTrialAuthorizationEvidence(**item)
    except TypeError as exc:
        raise RootfsHandoffTrialAuthorizationError("trial authorization evidence fields are invalid") from exc
    validate_rootfs_handoff_trial_authorization_evidence(evidence)
    if raw != evidence.canonical_json().encode("utf-8"):
        raise RootfsHandoffTrialAuthorizationError("trial authorization evidence is not canonical JSON")
    return evidence
