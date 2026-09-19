"""Offline fail-closed plan for a later interactive rootfs trial executor.

The plan binds one accepted manual trial authorization back to the exact target
binding and fresh-device revalidation that produced it. It is deliberately
non-executing: no phone I/O, raw device path, mount target, copy/write action,
or hardware/Beta credit is possible here.

A future interactive executor must still reacquire live device state, match it
to this exact chain, verify local rootfs identity and recovery readiness, and
obtain explicit operator confirmation before any write-capable operation.
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
    load_rootfs_handoff_fresh_revalidation_evidence,
    validate_rootfs_handoff_fresh_revalidation_evidence,
)
from .rootfs_handoff_target_binding import (
    RootfsHandoffTargetBindingError,
    load_rootfs_handoff_target_binding_evidence,
    validate_rootfs_handoff_target_binding_evidence,
)
from .rootfs_handoff_trial_authorization import (
    RootfsHandoffTrialAuthorizationError,
    load_rootfs_handoff_trial_authorization_evidence,
    validate_rootfs_handoff_trial_authorization_evidence,
)
from .stable_file import StableFileError, read_stable_regular_file

_POLICY = "rootfs-handoff-interactive-trial-plan-v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ROLE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
_SAFE_FS_RE = re.compile(r"^[a-z0-9][a-z0-9._+-]{0,31}$")
_MAX_EVIDENCE_BYTES = 2 * 1024 * 1024

_REQUIRED_TRUE_FLAGS = (
    "manual_trial_authorization_accepted",
    "ready_for_interactive_trial_execution_boundary",
    "live_device_recheck_required_at_execution",
    "explicit_operator_confirmation_required_at_execution",
    "execution_boundary_required",
    "physical_gate_still_incomplete",
)

_FORBIDDEN_AUTH_FLAGS = (
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

_PLAN_REQUIRED_TRUE = (
    "exact_authorization_chain_bound",
    "live_device_identity_recheck_required",
    "live_firmware_recheck_required",
    "live_target_identity_recheck_required",
    "live_filesystem_encryption_capacity_recheck_required",
    "rootfs_local_hash_recheck_required",
    "recovery_readiness_recheck_required",
    "explicit_operator_confirmation_required",
    "write_scope_confirmation_required",
    "plan_ready_for_later_interactive_executor",
    "physical_gate_still_incomplete",
)

_PLAN_FORBIDDEN = (
    "raw_device_path_bound",
    "mount_target_bound",
    "trial_execution_allowed",
    "persistent_write_authorized",
    "persistent_write_performed",
    "phone_storage_written",
    "storage_verified",
    "recovery_verified",
    "hardware_verified",
    "beta_release_authorized",
    "beta_gate_credit",
)


class RootfsHandoffTrialPlanError(ValueError):
    """Raised when a trial execution plan cannot be proved safe and exact."""


@dataclass(frozen=True)
class RootfsHandoffTrialPlan:
    schema_version: int
    plan_policy: str
    profile_id: str
    device_serial: str
    firmware_build: str
    firmware_fingerprint: str
    trial_authorization_sha256: str
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
    exact_authorization_chain_bound: bool
    live_device_identity_recheck_required: bool
    live_firmware_recheck_required: bool
    live_target_identity_recheck_required: bool
    live_filesystem_encryption_capacity_recheck_required: bool
    rootfs_local_hash_recheck_required: bool
    recovery_readiness_recheck_required: bool
    explicit_operator_confirmation_required: bool
    write_scope_confirmation_required: bool
    plan_ready_for_later_interactive_executor: bool
    physical_gate_still_incomplete: bool
    raw_device_path_bound: bool
    mount_target_bound: bool
    trial_execution_allowed: bool
    persistent_write_authorized: bool
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


def _safe_text(value: object, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise RootfsHandoffTrialPlanError(f"{label} must be non-empty bounded text")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise RootfsHandoffTrialPlanError(f"{label} contains control data")
    return value


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise RootfsHandoffTrialPlanError(f"{label} must be a lowercase SHA-256")
    return value


def _positive(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise RootfsHandoffTrialPlanError(f"{label} must be a positive integer")
    return value


def _safe_relative_subpath(value: object) -> str:
    text = _safe_text(value, "staging subpath", 512)
    if text.startswith(("/", "\\")) or ":" in text or "\\" in text:
        raise RootfsHandoffTrialPlanError("staging subpath must be relative and path-independent")
    path = PurePosixPath(text)
    if not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise RootfsHandoffTrialPlanError("staging subpath must be a safe relative POSIX path")
    return path.as_posix()


def _read_exact(path: Path) -> bytes:
    try:
        raw, _identity = read_stable_regular_file(
            Path(path),
            max_bytes=_MAX_EVIDENCE_BYTES,
            label="trial plan",
        )
    except StableFileError as exc:
        raise RootfsHandoffTrialPlanError(str(exc)) from exc
    return raw


def _validate_source_chain(authorization: object, binding: object, revalidation: object) -> None:
    try:
        validate_rootfs_handoff_trial_authorization_evidence(authorization)
        validate_rootfs_handoff_target_binding_evidence(binding)
        validate_rootfs_handoff_fresh_revalidation_evidence(revalidation)
    except (
        RootfsHandoffTrialAuthorizationError,
        RootfsHandoffTargetBindingError,
        RootfsHandoffFreshRevalidationError,
    ) as exc:
        raise RootfsHandoffTrialPlanError(str(exc)) from exc

    for name in _REQUIRED_TRUE_FLAGS:
        if getattr(authorization, name, None) is not True:
            raise RootfsHandoffTrialPlanError(f"trial authorization requires {name}=true")
    for name in _FORBIDDEN_AUTH_FLAGS:
        if getattr(authorization, name, None) is not False:
            raise RootfsHandoffTrialPlanError(f"trial authorization requires {name}=false")

    binding_sha = binding.evidence_sha256()
    revalidation_sha = revalidation.evidence_sha256()
    if authorization.target_binding_sha256 != binding_sha:
        raise RootfsHandoffTrialPlanError("trial authorization is detached from supplied target binding")
    if authorization.fresh_revalidation_sha256 != revalidation_sha:
        raise RootfsHandoffTrialPlanError("trial authorization is detached from supplied fresh revalidation")
    if revalidation.target_binding_sha256 != binding_sha:
        raise RootfsHandoffTrialPlanError("fresh revalidation is detached from supplied target binding")

    expected = (
        ("profile", authorization.profile_id, binding.profile_id),
        ("device serial", authorization.device_serial, binding.device_serial),
        ("firmware build", authorization.firmware_build, binding.firmware_build),
        ("firmware fingerprint", authorization.firmware_fingerprint, binding.firmware_fingerprint),
        ("partition role", authorization.candidate_partition_role, binding.candidate_partition_role),
        ("kernel name", authorization.observed_kernel_name, binding.observed_kernel_name),
        ("filesystem", authorization.observed_filesystem, binding.observed_filesystem),
        ("encryption state", authorization.observed_encryption_state, revalidation.observed_encryption_state),
        ("observed free bytes", authorization.observed_free_bytes, revalidation.observed_free_bytes),
        ("required free bytes", authorization.required_free_bytes, binding.required_free_bytes),
        ("staging subpath", authorization.staging_subpath, binding.staging_subpath),
        ("rootfs artifact", authorization.rootfs_artifact_sha256, binding.rootfs_artifact_sha256),
        ("rootfs artifact size", authorization.rootfs_artifact_size, binding.rootfs_artifact_size),
        ("recovery plan", authorization.recovery_plan_sha256, binding.recovery_plan_sha256),
    )
    for label, current, exact in expected:
        if current != exact:
            raise RootfsHandoffTrialPlanError(f"{label} drifted from authorized evidence chain")

    if authorization.observed_free_bytes < authorization.required_free_bytes:
        raise RootfsHandoffTrialPlanError("authorized free-space observation is below requirement")


def build_rootfs_handoff_trial_plan(
    trial_authorization_path: Path,
    target_binding_path: Path,
    fresh_revalidation_path: Path,
) -> RootfsHandoffTrialPlan:
    try:
        authorization = load_rootfs_handoff_trial_authorization_evidence(Path(trial_authorization_path))
        binding = load_rootfs_handoff_target_binding_evidence(Path(target_binding_path))
        revalidation = load_rootfs_handoff_fresh_revalidation_evidence(Path(fresh_revalidation_path))
    except (
        RootfsHandoffTrialAuthorizationError,
        RootfsHandoffTargetBindingError,
        RootfsHandoffFreshRevalidationError,
    ) as exc:
        raise RootfsHandoffTrialPlanError(str(exc)) from exc

    _validate_source_chain(authorization, binding, revalidation)

    plan = RootfsHandoffTrialPlan(
        schema_version=1,
        plan_policy=_POLICY,
        profile_id=authorization.profile_id,
        device_serial=authorization.device_serial,
        firmware_build=authorization.firmware_build,
        firmware_fingerprint=authorization.firmware_fingerprint,
        trial_authorization_sha256=authorization.evidence_sha256(),
        target_binding_sha256=authorization.target_binding_sha256,
        fresh_revalidation_sha256=authorization.fresh_revalidation_sha256,
        candidate_partition_role=authorization.candidate_partition_role,
        observed_kernel_name=authorization.observed_kernel_name,
        observed_filesystem=authorization.observed_filesystem,
        observed_encryption_state=authorization.observed_encryption_state,
        observed_free_bytes=authorization.observed_free_bytes,
        required_free_bytes=authorization.required_free_bytes,
        staging_subpath=authorization.staging_subpath,
        rootfs_artifact_sha256=authorization.rootfs_artifact_sha256,
        rootfs_artifact_size=authorization.rootfs_artifact_size,
        recovery_plan_sha256=authorization.recovery_plan_sha256,
        exact_authorization_chain_bound=True,
        live_device_identity_recheck_required=True,
        live_firmware_recheck_required=True,
        live_target_identity_recheck_required=True,
        live_filesystem_encryption_capacity_recheck_required=True,
        rootfs_local_hash_recheck_required=True,
        recovery_readiness_recheck_required=True,
        explicit_operator_confirmation_required=True,
        write_scope_confirmation_required=True,
        plan_ready_for_later_interactive_executor=True,
        physical_gate_still_incomplete=True,
        raw_device_path_bound=False,
        mount_target_bound=False,
        trial_execution_allowed=False,
        persistent_write_authorized=False,
        persistent_write_performed=False,
        phone_storage_written=False,
        storage_verified=False,
        recovery_verified=False,
        hardware_verified=False,
        beta_release_authorized=False,
        beta_gate_credit=False,
    )
    validate_rootfs_handoff_trial_plan(plan)
    return plan


def validate_rootfs_handoff_trial_plan(plan: RootfsHandoffTrialPlan) -> None:
    if not isinstance(plan, RootfsHandoffTrialPlan) or plan.schema_version != 1:
        raise RootfsHandoffTrialPlanError("trial plan must be schema-v1 typed evidence")
    if plan.plan_policy != _POLICY:
        raise RootfsHandoffTrialPlanError("trial plan policy is unsupported")
    if "/" not in _safe_text(plan.profile_id, "profile id", 128):
        raise RootfsHandoffTrialPlanError("profile id must use vendor/codename form")
    _safe_text(plan.device_serial, "device serial", 256)
    _safe_text(plan.firmware_build, "firmware build", 256)
    _safe_text(plan.firmware_fingerprint, "firmware fingerprint", 1024)
    for value, label in (
        (plan.trial_authorization_sha256, "trial authorization"),
        (plan.target_binding_sha256, "target binding"),
        (plan.fresh_revalidation_sha256, "fresh revalidation"),
        (plan.rootfs_artifact_sha256, "rootfs artifact"),
        (plan.recovery_plan_sha256, "recovery plan"),
    ):
        _sha(value, label)
    role = plan.candidate_partition_role
    if not isinstance(role, str) or not _SAFE_ROLE_RE.fullmatch(role):
        raise RootfsHandoffTrialPlanError("candidate partition role is invalid")
    kernel = plan.observed_kernel_name
    if not isinstance(kernel, str) or not _SAFE_NAME_RE.fullmatch(kernel):
        raise RootfsHandoffTrialPlanError("observed kernel name is invalid")
    filesystem = plan.observed_filesystem
    if not isinstance(filesystem, str) or not _SAFE_FS_RE.fullmatch(filesystem):
        raise RootfsHandoffTrialPlanError("observed filesystem is invalid")
    _safe_text(plan.observed_encryption_state, "observed encryption state", 32)
    observed = _positive(plan.observed_free_bytes, "observed free bytes")
    required = _positive(plan.required_free_bytes, "required free bytes")
    if observed < required:
        raise RootfsHandoffTrialPlanError("trial plan free-space observation is below requirement")
    _safe_relative_subpath(plan.staging_subpath)
    _positive(plan.rootfs_artifact_size, "rootfs artifact size")

    for name in _PLAN_REQUIRED_TRUE:
        if getattr(plan, name) is not True:
            raise RootfsHandoffTrialPlanError(f"trial plan requires {name}=true")
    for name in _PLAN_FORBIDDEN:
        if getattr(plan, name) is not False:
            raise RootfsHandoffTrialPlanError(f"trial plan requires {name}=false")


def write_rootfs_handoff_trial_plan(plan: RootfsHandoffTrialPlan, destination: Path) -> str:
    validate_rootfs_handoff_trial_plan(plan)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise RootfsHandoffTrialPlanError(f"refusing to overwrite existing output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(plan.canonical_json())
    return plan.evidence_sha256()


def load_rootfs_handoff_trial_plan(path: Path) -> RootfsHandoffTrialPlan:
    raw = _read_exact(Path(path))
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RootfsHandoffTrialPlanError("trial plan is not valid UTF-8 JSON") from exc
    expected = {field.name for field in fields(RootfsHandoffTrialPlan)}
    if not isinstance(value, dict) or set(value) != expected:
        raise RootfsHandoffTrialPlanError("trial plan fields do not match schema-v1")
    try:
        plan = RootfsHandoffTrialPlan(**value)
    except TypeError as exc:
        raise RootfsHandoffTrialPlanError("trial plan fields are invalid") from exc
    validate_rootfs_handoff_trial_plan(plan)
    if raw != plan.canonical_json().encode("utf-8"):
        raise RootfsHandoffTrialPlanError("trial plan is not canonical JSON")
    return plan
