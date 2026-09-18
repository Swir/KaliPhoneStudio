"""Fail-closed logical target binding review for a reversible rootfs handoff.

This offline layer is deliberately positioned *after* an accepted rootfs handoff
strategy review and *before* any real target mount/copy/trial.  It binds one exact
reviewed physical-storage report to one logical partition identity and exact
staging subpath.  It never carries a raw block-device path, never mounts or
writes storage, never talks to a phone and never grants hardware or Beta credit.

A successful review only means that the exact logical target identity may be
used as input to a later, separately gated manual trial-execution stage.  That
later stage must freshly revalidate the phone and require explicit operator
interaction before any write-capable action.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any

from .physical_storage_discovery import (
    PhysicalStorageDiscoveryError,
    PhysicalStorageDiscoveryEvidence,
    PhysicalStorageDiscoveryReport,
    load_physical_storage_discovery_evidence,
    load_physical_storage_discovery_report,
)
from .rootfs_handoff_strategy_review import (
    RootfsHandoffStrategyReviewError,
    RootfsHandoffStrategyReviewEvidence,
    load_rootfs_handoff_strategy_review_evidence,
)

_POLICY = "reversible-rootfs-handoff-target-binding-review-v1"
_ALLOWED_DECISIONS = frozenset({"accepted_for_manual_trial", "rejected"})
_ALLOWED_BINDING_ENCRYPTION_STATES = frozenset({"unlocked", "unencrypted"})
_SAFE_REVIEWER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+-]{0,127}$")
_SAFE_ROLE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
_SAFE_FS_RE = re.compile(r"^[a-z0-9][a-z0-9._+-]{0,31}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_RECORD_BYTES = 512 * 1024
_MAX_NOTES_BYTES = 2 * 1024 * 1024
_MAX_EVIDENCE_BYTES = 2 * 1024 * 1024


class RootfsHandoffTargetBindingError(ValueError):
    """Raised when the target-binding review chain fails closed."""


@dataclass(frozen=True)
class RootfsHandoffTargetBindingReviewRecord:
    schema_version: int
    review_policy: str
    profile_id: str
    device_serial: str
    reviewer: str
    decision: str
    candidate_partition_role: str
    observed_kernel_name: str
    observed_filesystem: str
    observed_encryption_state: str
    observed_free_bytes: int
    required_free_bytes: int
    staging_subpath: str
    rootfs_artifact_sha256: str
    recovery_plan_sha256: str
    exact_physical_chain_reviewed: bool
    exact_discovery_report_reviewed: bool
    logical_partition_identity_reviewed: bool
    filesystem_identity_reviewed: bool
    encryption_unlock_state_reviewed: bool
    capacity_reviewed: bool
    recovery_plan_reviewed: bool
    staging_subpath_reviewed: bool
    no_raw_device_path_reviewed: bool
    no_write_authorization_reviewed: bool
    raw_device_path_bound: bool
    mount_target_bound: bool
    trial_execution_allowed: bool
    write_authorized: bool
    phone_storage_written: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"


@dataclass(frozen=True)
class RootfsHandoffTargetBindingEvidence:
    schema_version: int
    review_policy: str
    profile_id: str
    device_serial: str
    firmware_build: str
    firmware_fingerprint: str
    physical_storage_discovery_sha256: str
    physical_storage_discovery_report_sha256: str
    physical_storage_discovery_report_size: int
    rootfs_handoff_strategy_review_sha256: str
    physical_release_gate_audit_sha256: str
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
    exact_physical_chain_reviewed: bool
    exact_discovery_report_reviewed: bool
    logical_partition_identity_reviewed: bool
    filesystem_identity_reviewed: bool
    encryption_unlock_state_reviewed: bool
    capacity_reviewed: bool
    recovery_plan_reviewed: bool
    staging_subpath_reviewed: bool
    no_raw_device_path_reviewed: bool
    no_write_authorization_reviewed: bool
    review_checks_complete: bool
    logical_target_identity_bound: bool
    fresh_device_revalidation_required: bool
    manual_trial_execution_required: bool
    physical_gate_still_incomplete: bool
    raw_device_path_bound: bool
    mount_target_bound: bool
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


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise RootfsHandoffTargetBindingError(f"{label} must be a lowercase SHA-256")
    return value


def _safe_text(value: object, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise RootfsHandoffTargetBindingError(f"{label} must be non-empty bounded text")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise RootfsHandoffTargetBindingError(f"{label} contains control data")
    return value


def _safe_role(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_ROLE_RE.fullmatch(value):
        raise RootfsHandoffTargetBindingError(f"{label} must be a safe logical partition role")
    return value


def _safe_name(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_NAME_RE.fullmatch(value):
        raise RootfsHandoffTargetBindingError(f"{label} must be a safe kernel/name token")
    return value


def _safe_filesystem(value: object) -> str:
    if not isinstance(value, str) or not _SAFE_FS_RE.fullmatch(value):
        raise RootfsHandoffTargetBindingError("observed filesystem must be a safe filesystem token")
    return value


def _safe_relative_subpath(value: object) -> str:
    text = _safe_text(value, "staging subpath", 512)
    if text.startswith(("/", "\\")) or ":" in text or "\\" in text:
        raise RootfsHandoffTargetBindingError("staging subpath must not be an absolute/raw device path")
    path = PurePosixPath(text)
    if not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise RootfsHandoffTargetBindingError("staging subpath must be a safe relative POSIX path")
    return path.as_posix()


def _positive(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise RootfsHandoffTargetBindingError(f"{label} must be a positive integer")
    return value


def _read_exact(path: Path, label: str, maximum: int) -> tuple[bytes, str, int]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise RootfsHandoffTargetBindingError(f"{label} must be a regular non-symlink file")
    try:
        before = source.stat()
        if before.st_size <= 0 or before.st_size > maximum:
            raise RootfsHandoffTargetBindingError(f"{label} size is outside the safety limit")
        raw = source.read_bytes()
        after = source.stat()
    except OSError as exc:
        raise RootfsHandoffTargetBindingError(f"cannot read {label}: {exc}") from exc
    if len(raw) != before.st_size:
        raise RootfsHandoffTargetBindingError(f"{label} size changed while being read")
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or getattr(before, "st_ino", None) != getattr(after, "st_ino", None)
    ):
        raise RootfsHandoffTargetBindingError(f"{label} changed while being read")
    return raw, sha256(raw).hexdigest(), len(raw)


def _exact_keys(raw: object, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != expected:
        raise RootfsHandoffTargetBindingError(f"{label} fields do not match schema-v1")
    return raw


def parse_rootfs_handoff_target_binding_review_record(
    raw: object,
) -> RootfsHandoffTargetBindingReviewRecord:
    item = _exact_keys(
        raw,
        {field.name for field in fields(RootfsHandoffTargetBindingReviewRecord)},
        "rootfs handoff target-binding review record",
    )
    if item["schema_version"] != 1 or item["review_policy"] != _POLICY:
        raise RootfsHandoffTargetBindingError("unsupported target-binding review record schema/policy")
    reviewer = item["reviewer"]
    if not isinstance(reviewer, str) or not _SAFE_REVIEWER_RE.fullmatch(reviewer):
        raise RootfsHandoffTargetBindingError("reviewer must be a safe bounded identifier")
    if item["decision"] not in _ALLOWED_DECISIONS:
        raise RootfsHandoffTargetBindingError("unsupported target-binding review decision")
    role = _safe_role(item["candidate_partition_role"], "candidate partition role")
    kernel_name = _safe_name(item["observed_kernel_name"], "observed kernel name")
    filesystem = _safe_filesystem(item["observed_filesystem"])
    encryption_state = _safe_text(item["observed_encryption_state"], "observed encryption state", 32)
    if encryption_state not in {"encrypted", "unencrypted", "locked", "unlocked", "unknown"}:
        raise RootfsHandoffTargetBindingError("observed encryption state is unsupported")
    observed_free = _positive(item["observed_free_bytes"], "observed free bytes")
    required_free = _positive(item["required_free_bytes"], "required free bytes")
    staging = _safe_relative_subpath(item["staging_subpath"])
    rootfs_sha = _sha(item["rootfs_artifact_sha256"], "rootfs artifact")
    recovery_sha = _sha(item["recovery_plan_sha256"], "recovery plan")

    review_flags = (
        "exact_physical_chain_reviewed",
        "exact_discovery_report_reviewed",
        "logical_partition_identity_reviewed",
        "filesystem_identity_reviewed",
        "encryption_unlock_state_reviewed",
        "capacity_reviewed",
        "recovery_plan_reviewed",
        "staging_subpath_reviewed",
        "no_raw_device_path_reviewed",
        "no_write_authorization_reviewed",
    )
    for name in review_flags:
        if not isinstance(item[name], bool):
            raise RootfsHandoffTargetBindingError(f"{name} must be boolean")
    for name in (
        "raw_device_path_bound",
        "mount_target_bound",
        "trial_execution_allowed",
        "write_authorized",
        "phone_storage_written",
    ):
        if item[name] is not False:
            raise RootfsHandoffTargetBindingError(f"target-binding review requires {name}=false")

    return RootfsHandoffTargetBindingReviewRecord(
        schema_version=1,
        review_policy=_POLICY,
        profile_id=_safe_text(item["profile_id"], "profile id", 128),
        device_serial=_safe_text(item["device_serial"], "device serial", 256),
        reviewer=reviewer,
        decision=item["decision"],
        candidate_partition_role=role,
        observed_kernel_name=kernel_name,
        observed_filesystem=filesystem,
        observed_encryption_state=encryption_state,
        observed_free_bytes=observed_free,
        required_free_bytes=required_free,
        staging_subpath=staging,
        rootfs_artifact_sha256=rootfs_sha,
        recovery_plan_sha256=recovery_sha,
        exact_physical_chain_reviewed=item["exact_physical_chain_reviewed"],
        exact_discovery_report_reviewed=item["exact_discovery_report_reviewed"],
        logical_partition_identity_reviewed=item["logical_partition_identity_reviewed"],
        filesystem_identity_reviewed=item["filesystem_identity_reviewed"],
        encryption_unlock_state_reviewed=item["encryption_unlock_state_reviewed"],
        capacity_reviewed=item["capacity_reviewed"],
        recovery_plan_reviewed=item["recovery_plan_reviewed"],
        staging_subpath_reviewed=item["staging_subpath_reviewed"],
        no_raw_device_path_reviewed=item["no_raw_device_path_reviewed"],
        no_write_authorization_reviewed=item["no_write_authorization_reviewed"],
        raw_device_path_bound=False,
        mount_target_bound=False,
        trial_execution_allowed=False,
        write_authorized=False,
        phone_storage_written=False,
    )


def load_rootfs_handoff_target_binding_review_record(
    path: Path,
) -> tuple[RootfsHandoffTargetBindingReviewRecord, str, int]:
    raw, digest, size = _read_exact(path, "target-binding review record", _MAX_RECORD_BYTES)
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RootfsHandoffTargetBindingError("target-binding review record is not valid UTF-8 JSON") from exc
    record = parse_rootfs_handoff_target_binding_review_record(value)
    if raw != record.canonical_json().encode("utf-8"):
        raise RootfsHandoffTargetBindingError("target-binding review record is not canonical JSON")
    return record, digest, size


def read_rootfs_handoff_target_binding_review_notes(path: Path) -> tuple[str, int]:
    raw, digest, size = _read_exact(path, "target-binding review notes", _MAX_NOTES_BYTES)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RootfsHandoffTargetBindingError("target-binding review notes must be UTF-8") from exc
    if not text.strip() or "\x00" in text:
        raise RootfsHandoffTargetBindingError("target-binding review notes are empty or contain NUL data")
    return digest, size


def _target_observations(
    discovery: PhysicalStorageDiscoveryEvidence,
    report: PhysicalStorageDiscoveryReport,
    strategy: RootfsHandoffStrategyReviewEvidence,
) -> tuple[str, str, str, int]:
    role = strategy.candidate_partition_role
    if role != discovery.partition_hint:
        raise RootfsHandoffTargetBindingError("strategy partition role drifted from physical discovery hint")
    if role in set(discovery.forbidden_partitions):
        raise RootfsHandoffTargetBindingError("strategy partition role is forbidden by physical discovery")

    fs_matches = [item for item in report.filesystems if item.partition_role == role]
    enc_matches = [item for item in report.encryption if item.partition_role == role]
    free_matches = [item for item in report.free_space if item.partition_role == role]
    if len(fs_matches) != 1 or len(enc_matches) != 1 or len(free_matches) != 1:
        raise RootfsHandoffTargetBindingError("target role requires one exact filesystem/encryption/free-space observation")
    filesystem = fs_matches[0]
    encryption = enc_matches[0]
    free = free_matches[0]
    if not filesystem.observed or filesystem.filesystem not in set(discovery.expected_filesystems):
        raise RootfsHandoffTargetBindingError("target filesystem is not an observed expected filesystem")
    if not encryption.observed or encryption.state not in _ALLOWED_BINDING_ENCRYPTION_STATES:
        raise RootfsHandoffTargetBindingError("target encryption state must be physically observed as unlocked or unencrypted")
    if not free.observed or free.free_bytes is None or free.total_bytes is None:
        raise RootfsHandoffTargetBindingError("target free-space observation is incomplete")
    if free.free_bytes < strategy.required_free_bytes:
        raise RootfsHandoffTargetBindingError("target free space is below the reviewed strategy requirement")

    block_matches = [item for item in report.block_devices if item.kernel_name == filesystem.kernel_name]
    if len(block_matches) != 1:
        raise RootfsHandoffTargetBindingError("target filesystem kernel identity is not uniquely present in block observations")
    if block_matches[0].removable:
        raise RootfsHandoffTargetBindingError("rootfs staging target must not resolve to removable storage")
    return filesystem.kernel_name, filesystem.filesystem, encryption.state, free.free_bytes


def prepare_rootfs_handoff_target_binding_review_record(
    discovery_path: Path,
    discovery_report_path: Path,
    strategy_review_path: Path,
    reviewer: str,
) -> RootfsHandoffTargetBindingReviewRecord:
    if not isinstance(reviewer, str) or not _SAFE_REVIEWER_RE.fullmatch(reviewer):
        raise RootfsHandoffTargetBindingError("reviewer must be a safe bounded identifier")
    try:
        discovery = load_physical_storage_discovery_evidence(Path(discovery_path))
        report, report_sha, report_size = load_physical_storage_discovery_report(Path(discovery_report_path))
        strategy = load_rootfs_handoff_strategy_review_evidence(Path(strategy_review_path))
    except (PhysicalStorageDiscoveryError, RootfsHandoffStrategyReviewError) as exc:
        raise RootfsHandoffTargetBindingError(str(exc)) from exc
    _validate_upstream(discovery, report, report_sha, report_size, strategy)
    kernel_name, filesystem, encryption_state, free_bytes = _target_observations(discovery, report, strategy)
    record = RootfsHandoffTargetBindingReviewRecord(
        schema_version=1,
        review_policy=_POLICY,
        profile_id=discovery.profile_id,
        device_serial=discovery.device_serial,
        reviewer=reviewer,
        decision="rejected",
        candidate_partition_role=strategy.candidate_partition_role,
        observed_kernel_name=kernel_name,
        observed_filesystem=filesystem,
        observed_encryption_state=encryption_state,
        observed_free_bytes=free_bytes,
        required_free_bytes=strategy.required_free_bytes,
        staging_subpath=strategy.staging_subpath,
        rootfs_artifact_sha256=strategy.rootfs_artifact_sha256,
        recovery_plan_sha256=strategy.recovery_plan_sha256,
        exact_physical_chain_reviewed=False,
        exact_discovery_report_reviewed=False,
        logical_partition_identity_reviewed=False,
        filesystem_identity_reviewed=False,
        encryption_unlock_state_reviewed=False,
        capacity_reviewed=False,
        recovery_plan_reviewed=False,
        staging_subpath_reviewed=False,
        no_raw_device_path_reviewed=False,
        no_write_authorization_reviewed=False,
        raw_device_path_bound=False,
        mount_target_bound=False,
        trial_execution_allowed=False,
        write_authorized=False,
        phone_storage_written=False,
    )
    return parse_rootfs_handoff_target_binding_review_record(json.loads(record.canonical_json()))


def _validate_upstream(
    discovery: PhysicalStorageDiscoveryEvidence,
    report: PhysicalStorageDiscoveryReport,
    report_sha: str,
    report_size: int,
    strategy: RootfsHandoffStrategyReviewEvidence,
) -> None:
    if strategy.strategy_design_accepted is not True or strategy.review_checks_complete is not True:
        raise RootfsHandoffTargetBindingError("target binding requires an accepted exact strategy review")
    if strategy.manual_target_binding_required is not True or strategy.physical_gate_still_incomplete is not True:
        raise RootfsHandoffTargetBindingError("strategy review does not require the expected manual target-binding stage")
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
        if getattr(strategy, name) is not False:
            raise RootfsHandoffTargetBindingError(f"strategy review contains forbidden promotion: {name}")
    if strategy.physical_storage_discovery_sha256 != discovery.evidence_sha256():
        raise RootfsHandoffTargetBindingError("strategy review is detached from exact physical storage discovery")
    if (
        strategy.profile_id != discovery.profile_id
        or strategy.device_serial != discovery.device_serial
        or strategy.firmware_build != discovery.firmware_build
        or strategy.firmware_fingerprint != discovery.firmware_fingerprint
    ):
        raise RootfsHandoffTargetBindingError("target-binding physical identity drifted across evidence")
    if report.profile_id != discovery.profile_id or report.device_serial != discovery.device_serial:
        raise RootfsHandoffTargetBindingError("physical storage discovery report identity drifted")
    if report_sha != discovery.discovery_report_sha256 or report_size != discovery.discovery_report_size:
        raise RootfsHandoffTargetBindingError("physical storage discovery report bytes differ from exact bound discovery")
    if strategy.rootfs_artifact_sha256 != discovery.rootfs_artifact_sha256:
        raise RootfsHandoffTargetBindingError("strategy rootfs artifact drifted from physical discovery")
    if strategy.rootfs_artifact_size != discovery.rootfs_artifact_size:
        raise RootfsHandoffTargetBindingError("strategy rootfs artifact size drifted from physical discovery")
    if strategy.recovery_plan_sha256 != discovery.recovery_plan_sha256:
        raise RootfsHandoffTargetBindingError("strategy recovery plan drifted from physical discovery")
    for name in (
        "target_selected",
        "storage_path_bound",
        "write_authorized",
        "handoff_ready",
        "storage_verified",
        "recovery_verified",
        "phone_storage_written",
        "hardware_verified",
        "beta_gate_credit",
    ):
        if getattr(discovery, name) is not False:
            raise RootfsHandoffTargetBindingError(f"physical storage discovery contains forbidden promotion: {name}")


def bind_rootfs_handoff_target_binding_review(
    discovery_path: Path,
    discovery_report_path: Path,
    strategy_review_path: Path,
    review_record_path: Path,
    review_notes_path: Path,
) -> RootfsHandoffTargetBindingEvidence:
    try:
        discovery = load_physical_storage_discovery_evidence(Path(discovery_path))
        report, report_sha, report_size = load_physical_storage_discovery_report(Path(discovery_report_path))
        strategy = load_rootfs_handoff_strategy_review_evidence(Path(strategy_review_path))
    except (PhysicalStorageDiscoveryError, RootfsHandoffStrategyReviewError) as exc:
        raise RootfsHandoffTargetBindingError(str(exc)) from exc
    _validate_upstream(discovery, report, report_sha, report_size, strategy)
    kernel_name, filesystem, encryption_state, free_bytes = _target_observations(discovery, report, strategy)
    record, record_sha, record_size = load_rootfs_handoff_target_binding_review_record(Path(review_record_path))
    notes_sha, notes_size = read_rootfs_handoff_target_binding_review_notes(Path(review_notes_path))

    exact_values = {
        "profile_id": discovery.profile_id,
        "device_serial": discovery.device_serial,
        "candidate_partition_role": strategy.candidate_partition_role,
        "observed_kernel_name": kernel_name,
        "observed_filesystem": filesystem,
        "observed_encryption_state": encryption_state,
        "observed_free_bytes": free_bytes,
        "required_free_bytes": strategy.required_free_bytes,
        "staging_subpath": strategy.staging_subpath,
        "rootfs_artifact_sha256": strategy.rootfs_artifact_sha256,
        "recovery_plan_sha256": strategy.recovery_plan_sha256,
    }
    for name, expected in exact_values.items():
        if getattr(record, name) != expected:
            raise RootfsHandoffTargetBindingError(f"target-binding review record drifted from exact evidence: {name}")

    review_flag_names = (
        "exact_physical_chain_reviewed",
        "exact_discovery_report_reviewed",
        "logical_partition_identity_reviewed",
        "filesystem_identity_reviewed",
        "encryption_unlock_state_reviewed",
        "capacity_reviewed",
        "recovery_plan_reviewed",
        "staging_subpath_reviewed",
        "no_raw_device_path_reviewed",
        "no_write_authorization_reviewed",
    )
    checks_complete = all(getattr(record, name) is True for name in review_flag_names)
    accepted = record.decision == "accepted_for_manual_trial"
    if accepted and not checks_complete:
        raise RootfsHandoffTargetBindingError("accepted target binding requires every explicit review check")
    if accepted and encryption_state not in _ALLOWED_BINDING_ENCRYPTION_STATES:
        raise RootfsHandoffTargetBindingError("accepted target binding requires unlocked or unencrypted target evidence")
    if accepted and free_bytes < strategy.required_free_bytes:
        raise RootfsHandoffTargetBindingError("accepted target binding has insufficient reviewed free space")

    evidence = RootfsHandoffTargetBindingEvidence(
        schema_version=1,
        review_policy=_POLICY,
        profile_id=discovery.profile_id,
        device_serial=discovery.device_serial,
        firmware_build=discovery.firmware_build,
        firmware_fingerprint=discovery.firmware_fingerprint,
        physical_storage_discovery_sha256=discovery.evidence_sha256(),
        physical_storage_discovery_report_sha256=report_sha,
        physical_storage_discovery_report_size=report_size,
        rootfs_handoff_strategy_review_sha256=strategy.evidence_sha256(),
        physical_release_gate_audit_sha256=strategy.physical_release_gate_audit_sha256,
        candidate_partition_role=strategy.candidate_partition_role,
        observed_kernel_name=kernel_name,
        observed_filesystem=filesystem,
        observed_encryption_state=encryption_state,
        observed_free_bytes=free_bytes,
        required_free_bytes=strategy.required_free_bytes,
        staging_subpath=strategy.staging_subpath,
        rootfs_artifact_sha256=strategy.rootfs_artifact_sha256,
        rootfs_artifact_size=strategy.rootfs_artifact_size,
        recovery_plan_sha256=strategy.recovery_plan_sha256,
        review_record_sha256=record_sha,
        review_record_size=record_size,
        review_notes_sha256=notes_sha,
        review_notes_size=notes_size,
        reviewer=record.reviewer,
        decision=record.decision,
        exact_physical_chain_reviewed=record.exact_physical_chain_reviewed,
        exact_discovery_report_reviewed=record.exact_discovery_report_reviewed,
        logical_partition_identity_reviewed=record.logical_partition_identity_reviewed,
        filesystem_identity_reviewed=record.filesystem_identity_reviewed,
        encryption_unlock_state_reviewed=record.encryption_unlock_state_reviewed,
        capacity_reviewed=record.capacity_reviewed,
        recovery_plan_reviewed=record.recovery_plan_reviewed,
        staging_subpath_reviewed=record.staging_subpath_reviewed,
        no_raw_device_path_reviewed=record.no_raw_device_path_reviewed,
        no_write_authorization_reviewed=record.no_write_authorization_reviewed,
        review_checks_complete=checks_complete,
        logical_target_identity_bound=accepted and checks_complete,
        fresh_device_revalidation_required=True,
        manual_trial_execution_required=True,
        physical_gate_still_incomplete=True,
        raw_device_path_bound=False,
        mount_target_bound=False,
        trial_execution_allowed=False,
        write_authorized=False,
        handoff_ready=False,
        persistent_write_performed=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_release_authorized=False,
        beta_gate_credit=False,
    )
    validate_rootfs_handoff_target_binding_evidence(evidence)
    return evidence


def validate_rootfs_handoff_target_binding_evidence(
    evidence: RootfsHandoffTargetBindingEvidence,
) -> None:
    if not isinstance(evidence, RootfsHandoffTargetBindingEvidence) or evidence.schema_version != 1:
        raise RootfsHandoffTargetBindingError("rootfs target binding must be schema-v1 typed evidence")
    if evidence.review_policy != _POLICY:
        raise RootfsHandoffTargetBindingError("rootfs target binding policy is unsupported")
    _safe_text(evidence.profile_id, "profile id", 128)
    _safe_text(evidence.device_serial, "device serial", 256)
    _safe_text(evidence.firmware_build, "firmware build", 512)
    _safe_text(evidence.firmware_fingerprint, "firmware fingerprint", 1024)
    for value, label in (
        (evidence.physical_storage_discovery_sha256, "physical storage discovery"),
        (evidence.physical_storage_discovery_report_sha256, "physical storage discovery report"),
        (evidence.rootfs_handoff_strategy_review_sha256, "rootfs handoff strategy review"),
        (evidence.physical_release_gate_audit_sha256, "physical release-gate audit"),
        (evidence.rootfs_artifact_sha256, "rootfs artifact"),
        (evidence.recovery_plan_sha256, "recovery plan"),
        (evidence.review_record_sha256, "review record"),
        (evidence.review_notes_sha256, "review notes"),
    ):
        _sha(value, label)
    for value, label in (
        (evidence.physical_storage_discovery_report_size, "physical storage discovery report size"),
        (evidence.observed_free_bytes, "observed free bytes"),
        (evidence.required_free_bytes, "required free bytes"),
        (evidence.rootfs_artifact_size, "rootfs artifact size"),
        (evidence.review_record_size, "review record size"),
        (evidence.review_notes_size, "review notes size"),
    ):
        _positive(value, label)
    _safe_role(evidence.candidate_partition_role, "candidate partition role")
    _safe_name(evidence.observed_kernel_name, "observed kernel name")
    _safe_filesystem(evidence.observed_filesystem)
    if evidence.observed_encryption_state not in _ALLOWED_BINDING_ENCRYPTION_STATES:
        if evidence.logical_target_identity_bound:
            raise RootfsHandoffTargetBindingError("bound target requires unlocked or unencrypted evidence")
    _safe_relative_subpath(evidence.staging_subpath)
    if not _SAFE_REVIEWER_RE.fullmatch(evidence.reviewer):
        raise RootfsHandoffTargetBindingError("reviewer is invalid")
    if evidence.decision not in _ALLOWED_DECISIONS:
        raise RootfsHandoffTargetBindingError("target-binding decision is invalid")

    review_flags = (
        evidence.exact_physical_chain_reviewed,
        evidence.exact_discovery_report_reviewed,
        evidence.logical_partition_identity_reviewed,
        evidence.filesystem_identity_reviewed,
        evidence.encryption_unlock_state_reviewed,
        evidence.capacity_reviewed,
        evidence.recovery_plan_reviewed,
        evidence.staging_subpath_reviewed,
        evidence.no_raw_device_path_reviewed,
        evidence.no_write_authorization_reviewed,
    )
    if not all(isinstance(value, bool) for value in review_flags):
        raise RootfsHandoffTargetBindingError("target-binding review checks must be booleans")
    expected_complete = all(review_flags)
    if evidence.review_checks_complete is not expected_complete:
        raise RootfsHandoffTargetBindingError("target-binding review completion flag drifted")
    expected_bound = evidence.decision == "accepted_for_manual_trial" and expected_complete
    if evidence.logical_target_identity_bound is not expected_bound:
        raise RootfsHandoffTargetBindingError("logical target binding flag drifted")
    if expected_bound and evidence.observed_free_bytes < evidence.required_free_bytes:
        raise RootfsHandoffTargetBindingError("bound target does not satisfy required free space")
    if evidence.fresh_device_revalidation_required is not True or evidence.manual_trial_execution_required is not True:
        raise RootfsHandoffTargetBindingError("target binding must require fresh device revalidation and manual trial execution")
    if evidence.physical_gate_still_incomplete is not True:
        raise RootfsHandoffTargetBindingError("target binding must keep the physical release gate incomplete")
    for name in (
        "raw_device_path_bound",
        "mount_target_bound",
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
            raise RootfsHandoffTargetBindingError(f"target binding cannot promote {name}")


def write_rootfs_handoff_target_binding_evidence(
    evidence: RootfsHandoffTargetBindingEvidence,
    destination: Path,
) -> str:
    validate_rootfs_handoff_target_binding_evidence(evidence)
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise RootfsHandoffTargetBindingError("refusing to overwrite rootfs target-binding evidence")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise RootfsHandoffTargetBindingError("refusing stale target-binding temporary output")
    try:
        temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
        temporary.replace(path)
    except OSError as exc:
        raise RootfsHandoffTargetBindingError(f"cannot write target-binding evidence: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()


def load_rootfs_handoff_target_binding_evidence(path: Path) -> RootfsHandoffTargetBindingEvidence:
    raw, _, _ = _read_exact(path, "rootfs target-binding evidence", _MAX_EVIDENCE_BYTES)
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RootfsHandoffTargetBindingError("rootfs target-binding evidence is not valid UTF-8 JSON") from exc
    item = _exact_keys(
        value,
        {field.name for field in fields(RootfsHandoffTargetBindingEvidence)},
        "rootfs target-binding evidence",
    )
    try:
        evidence = RootfsHandoffTargetBindingEvidence(**item)
    except TypeError as exc:
        raise RootfsHandoffTargetBindingError("rootfs target-binding evidence field types are invalid") from exc
    validate_rootfs_handoff_target_binding_evidence(evidence)
    if raw != evidence.canonical_json().encode("utf-8"):
        raise RootfsHandoffTargetBindingError("rootfs target-binding evidence is not canonical JSON")
    return evidence
