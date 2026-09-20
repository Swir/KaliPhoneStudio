"""Fail-closed execution-time evidence gate for a later interactive rootfs writer.

This boundary is intentionally still non-writing. It binds the accepted offline
trial plan and exact local-rootfs preflight to the originally authorized fresh
storage revalidation, then requires a *second*, distinct fresh revalidation from
the same physical phone/firmware immediately before an interactive writer may be
considered.

Passing this gate proves only that the reviewed logical target identity, firmware,
filesystem/encryption/capacity, rootfs bytes and recovery-plan identity have not
drifted across the evidence chain. It does not resolve a raw block-device path,
mount storage, execute a trial, authorize a persistent write, contact the phone,
or grant storage/recovery/hardware/Beta credit. A later interactive writer must
still reacquire the raw target under the same live context and require explicit
operator confirmation of both device identity and write scope.
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
from .rootfs_handoff_trial_plan import (
    RootfsHandoffTrialPlan,
    RootfsHandoffTrialPlanError,
    load_rootfs_handoff_trial_plan,
    validate_rootfs_handoff_trial_plan,
)
from .rootfs_handoff_trial_preflight import (
    RootfsHandoffTrialPreflightError,
    RootfsHandoffTrialPreflightEvidence,
    load_rootfs_handoff_trial_preflight_evidence,
    validate_rootfs_handoff_trial_preflight_evidence,
)
from .stable_file import StableFileError, read_stable_regular_file

_POLICY = "rootfs-handoff-interactive-execution-gate-v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ROLE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
_SAFE_FS_RE = re.compile(r"^[a-z0-9][a-z0-9._+-]{0,31}$")
_ALLOWED_ENCRYPTION_STATES = frozenset({"unlocked", "unencrypted"})
_MAX_EVIDENCE_BYTES = 2 * 1024 * 1024

_REQUIRED_TRUE_FLAGS = (
    "exact_trial_plan_bound",
    "exact_preflight_bound",
    "authorized_revalidation_bound",
    "distinct_execution_capture_bound",
    "live_device_identity_revalidated",
    "live_firmware_revalidated",
    "live_target_identity_revalidated",
    "live_filesystem_encryption_capacity_revalidated",
    "local_rootfs_exact_bytes_verified",
    "recovery_plan_identity_revalidated",
    "execution_gate_passed",
    "explicit_operator_confirmation_required",
    "write_scope_confirmation_required",
    "raw_device_path_resolution_required",
    "interactive_writer_required",
    "physical_gate_still_incomplete",
)

_FORBIDDEN_FLAGS = (
    "physical_interaction_performed",
    "external_device_command_executed",
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


class RootfsHandoffTrialExecutionGateError(ValueError):
    """Raised when execution-time trial evidence is not exact and fail-closed."""


@dataclass(frozen=True)
class RootfsHandoffTrialExecutionGateEvidence:
    schema_version: int
    execution_gate_policy: str
    profile_id: str
    device_serial: str
    firmware_build: str
    firmware_fingerprint: str
    trial_plan_sha256: str
    trial_preflight_sha256: str
    trial_authorization_sha256: str
    target_binding_sha256: str
    authorized_fresh_revalidation_sha256: str
    execution_fresh_revalidation_sha256: str
    authorized_storage_discovery_sha256: str
    execution_storage_discovery_sha256: str
    execution_storage_report_sha256: str
    execution_storage_report_size: int
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
    exact_trial_plan_bound: bool
    exact_preflight_bound: bool
    authorized_revalidation_bound: bool
    distinct_execution_capture_bound: bool
    live_device_identity_revalidated: bool
    live_firmware_revalidated: bool
    live_target_identity_revalidated: bool
    live_filesystem_encryption_capacity_revalidated: bool
    local_rootfs_exact_bytes_verified: bool
    recovery_plan_identity_revalidated: bool
    execution_gate_passed: bool
    explicit_operator_confirmation_required: bool
    write_scope_confirmation_required: bool
    raw_device_path_resolution_required: bool
    interactive_writer_required: bool
    physical_gate_still_incomplete: bool
    physical_interaction_performed: bool
    external_device_command_executed: bool
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
        raise RootfsHandoffTrialExecutionGateError(f"{label} must be non-empty bounded text")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise RootfsHandoffTrialExecutionGateError(f"{label} contains control data")
    return value


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise RootfsHandoffTrialExecutionGateError(f"{label} must be a lowercase SHA-256")
    return value


def _positive(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise RootfsHandoffTrialExecutionGateError(f"{label} must be a positive integer")
    return value


def _safe_relative_subpath(value: object) -> str:
    text = _safe_text(value, "staging subpath", 512)
    if text.startswith(("/", "\\")) or ":" in text or "\\" in text:
        raise RootfsHandoffTrialExecutionGateError("staging subpath must be relative and path-independent")
    path = PurePosixPath(text)
    if not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise RootfsHandoffTrialExecutionGateError("staging subpath must be a safe relative POSIX path")
    return path.as_posix()


def _read_exact(path: Path) -> bytes:
    try:
        raw, _identity = read_stable_regular_file(
            Path(path),
            max_bytes=_MAX_EVIDENCE_BYTES,
            label="rootfs trial execution-gate evidence",
        )
    except StableFileError as exc:
        raise RootfsHandoffTrialExecutionGateError(str(exc)) from exc
    return raw


def _validate_sources(
    plan: RootfsHandoffTrialPlan,
    preflight: RootfsHandoffTrialPreflightEvidence,
    authorized: RootfsHandoffFreshRevalidationEvidence,
    execution: RootfsHandoffFreshRevalidationEvidence,
) -> None:
    try:
        validate_rootfs_handoff_trial_plan(plan)
        validate_rootfs_handoff_trial_preflight_evidence(preflight)
        validate_rootfs_handoff_fresh_revalidation_evidence(authorized)
        validate_rootfs_handoff_fresh_revalidation_evidence(execution)
    except (
        RootfsHandoffTrialPlanError,
        RootfsHandoffTrialPreflightError,
        RootfsHandoffFreshRevalidationError,
    ) as exc:
        raise RootfsHandoffTrialExecutionGateError(str(exc)) from exc

    plan_sha = plan.evidence_sha256()
    if preflight.trial_plan_sha256 != plan_sha:
        raise RootfsHandoffTrialExecutionGateError("trial preflight is detached from supplied trial plan")
    if plan.fresh_revalidation_sha256 != authorized.evidence_sha256():
        raise RootfsHandoffTrialExecutionGateError(
            "trial plan is detached from the fresh revalidation used for manual authorization"
        )
    if authorized.target_binding_sha256 != plan.target_binding_sha256:
        raise RootfsHandoffTrialExecutionGateError("authorized fresh revalidation target binding drifted")
    if execution.target_binding_sha256 != plan.target_binding_sha256:
        raise RootfsHandoffTrialExecutionGateError("execution-time fresh revalidation target binding drifted")
    if authorized.fresh_physical_storage_discovery_sha256 == execution.fresh_physical_storage_discovery_sha256:
        raise RootfsHandoffTrialExecutionGateError(
            "execution gate requires a second distinct storage capture after the authorization capture"
        )
    if authorized.fresh_physical_storage_discovery_report_sha256 == execution.fresh_physical_storage_discovery_report_sha256:
        raise RootfsHandoffTrialExecutionGateError(
            "execution gate requires a distinct fresh storage report, not reused authorization bytes"
        )
    if authorized.previous_physical_storage_discovery_sha256 != execution.previous_physical_storage_discovery_sha256:
        raise RootfsHandoffTrialExecutionGateError("execution revalidation resolves a different original storage chain")

    expected = (
        ("profile", preflight.profile_id, plan.profile_id),
        ("device serial", preflight.device_serial, plan.device_serial),
        ("firmware build", preflight.firmware_build, plan.firmware_build),
        ("firmware fingerprint", preflight.firmware_fingerprint, plan.firmware_fingerprint),
        ("partition role", preflight.candidate_partition_role, plan.candidate_partition_role),
        ("kernel name", preflight.observed_kernel_name, plan.observed_kernel_name),
        ("filesystem", preflight.observed_filesystem, plan.observed_filesystem),
        ("encryption state", preflight.observed_encryption_state, plan.observed_encryption_state),
        ("required free bytes", preflight.required_free_bytes, plan.required_free_bytes),
        ("staging subpath", preflight.staging_subpath, plan.staging_subpath),
        ("rootfs artifact", preflight.rootfs_artifact_sha256, plan.rootfs_artifact_sha256),
        ("rootfs artifact size", preflight.rootfs_artifact_size, plan.rootfs_artifact_size),
        ("recovery plan", preflight.recovery_plan_sha256, plan.recovery_plan_sha256),
    )
    for label, current, exact in expected:
        if current != exact:
            raise RootfsHandoffTrialExecutionGateError(f"{label} drifted between trial plan and preflight")

    for source_name, evidence in (("authorized", authorized), ("execution", execution)):
        pairs = (
            ("profile", evidence.profile_id, plan.profile_id),
            ("device serial", evidence.device_serial, plan.device_serial),
            ("firmware build", evidence.firmware_build, plan.firmware_build),
            ("firmware fingerprint", evidence.firmware_fingerprint, plan.firmware_fingerprint),
            ("partition role", evidence.candidate_partition_role, plan.candidate_partition_role),
            ("kernel name", evidence.observed_kernel_name, plan.observed_kernel_name),
            ("filesystem", evidence.observed_filesystem, plan.observed_filesystem),
            ("encryption state", evidence.observed_encryption_state, plan.observed_encryption_state),
            ("required free bytes", evidence.required_free_bytes, plan.required_free_bytes),
            ("staging subpath", evidence.staging_subpath, plan.staging_subpath),
            ("rootfs artifact", evidence.rootfs_artifact_sha256, plan.rootfs_artifact_sha256),
            ("rootfs artifact size", evidence.rootfs_artifact_size, plan.rootfs_artifact_size),
            ("recovery plan", evidence.recovery_plan_sha256, plan.recovery_plan_sha256),
        )
        for label, current, exact in pairs:
            if current != exact:
                raise RootfsHandoffTrialExecutionGateError(
                    f"{source_name} fresh revalidation {label} drifted from trial plan"
                )

    if execution.observed_free_bytes < plan.required_free_bytes:
        raise RootfsHandoffTrialExecutionGateError("execution-time free capacity is below the reviewed requirement")
    if execution.observed_encryption_state not in _ALLOWED_ENCRYPTION_STATES:
        raise RootfsHandoffTrialExecutionGateError("execution-time encryption state is not acceptable")
    if preflight.local_rootfs_exact_bytes_verified is not True:
        raise RootfsHandoffTrialExecutionGateError("local rootfs exact-byte preflight has not passed")


def build_rootfs_handoff_trial_execution_gate(
    trial_plan_path: Path,
    trial_preflight_path: Path,
    authorized_fresh_revalidation_path: Path,
    execution_fresh_revalidation_path: Path,
) -> RootfsHandoffTrialExecutionGateEvidence:
    try:
        plan = load_rootfs_handoff_trial_plan(Path(trial_plan_path))
        preflight = load_rootfs_handoff_trial_preflight_evidence(Path(trial_preflight_path))
        authorized = load_rootfs_handoff_fresh_revalidation_evidence(Path(authorized_fresh_revalidation_path))
        execution = load_rootfs_handoff_fresh_revalidation_evidence(Path(execution_fresh_revalidation_path))
    except (
        RootfsHandoffTrialPlanError,
        RootfsHandoffTrialPreflightError,
        RootfsHandoffFreshRevalidationError,
    ) as exc:
        raise RootfsHandoffTrialExecutionGateError(str(exc)) from exc

    _validate_sources(plan, preflight, authorized, execution)

    evidence = RootfsHandoffTrialExecutionGateEvidence(
        schema_version=1,
        execution_gate_policy=_POLICY,
        profile_id=plan.profile_id,
        device_serial=plan.device_serial,
        firmware_build=plan.firmware_build,
        firmware_fingerprint=plan.firmware_fingerprint,
        trial_plan_sha256=plan.evidence_sha256(),
        trial_preflight_sha256=preflight.evidence_sha256(),
        trial_authorization_sha256=plan.trial_authorization_sha256,
        target_binding_sha256=plan.target_binding_sha256,
        authorized_fresh_revalidation_sha256=authorized.evidence_sha256(),
        execution_fresh_revalidation_sha256=execution.evidence_sha256(),
        authorized_storage_discovery_sha256=authorized.fresh_physical_storage_discovery_sha256,
        execution_storage_discovery_sha256=execution.fresh_physical_storage_discovery_sha256,
        execution_storage_report_sha256=execution.fresh_physical_storage_discovery_report_sha256,
        execution_storage_report_size=execution.fresh_physical_storage_discovery_report_size,
        candidate_partition_role=plan.candidate_partition_role,
        observed_kernel_name=execution.observed_kernel_name,
        observed_filesystem=execution.observed_filesystem,
        observed_encryption_state=execution.observed_encryption_state,
        observed_free_bytes=execution.observed_free_bytes,
        required_free_bytes=plan.required_free_bytes,
        staging_subpath=plan.staging_subpath,
        rootfs_artifact_sha256=plan.rootfs_artifact_sha256,
        rootfs_artifact_size=plan.rootfs_artifact_size,
        recovery_plan_sha256=plan.recovery_plan_sha256,
        exact_trial_plan_bound=True,
        exact_preflight_bound=True,
        authorized_revalidation_bound=True,
        distinct_execution_capture_bound=True,
        live_device_identity_revalidated=True,
        live_firmware_revalidated=True,
        live_target_identity_revalidated=True,
        live_filesystem_encryption_capacity_revalidated=True,
        local_rootfs_exact_bytes_verified=True,
        recovery_plan_identity_revalidated=True,
        execution_gate_passed=True,
        explicit_operator_confirmation_required=True,
        write_scope_confirmation_required=True,
        raw_device_path_resolution_required=True,
        interactive_writer_required=True,
        physical_gate_still_incomplete=True,
        physical_interaction_performed=False,
        external_device_command_executed=False,
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
    validate_rootfs_handoff_trial_execution_gate_evidence(evidence)
    return evidence


def validate_rootfs_handoff_trial_execution_gate_evidence(
    evidence: RootfsHandoffTrialExecutionGateEvidence,
) -> None:
    if not isinstance(evidence, RootfsHandoffTrialExecutionGateEvidence) or evidence.schema_version != 1:
        raise RootfsHandoffTrialExecutionGateError("execution gate must be schema-v1 typed evidence")
    if evidence.execution_gate_policy != _POLICY:
        raise RootfsHandoffTrialExecutionGateError("execution gate policy is unsupported")
    if "/" not in _safe_text(evidence.profile_id, "profile id", 128):
        raise RootfsHandoffTrialExecutionGateError("profile id must use vendor/codename form")
    _safe_text(evidence.device_serial, "device serial", 256)
    _safe_text(evidence.firmware_build, "firmware build", 256)
    _safe_text(evidence.firmware_fingerprint, "firmware fingerprint", 1024)
    if not isinstance(evidence.candidate_partition_role, str) or not _SAFE_ROLE_RE.fullmatch(evidence.candidate_partition_role):
        raise RootfsHandoffTrialExecutionGateError("candidate partition role is invalid")
    if not isinstance(evidence.observed_kernel_name, str) or not _SAFE_NAME_RE.fullmatch(evidence.observed_kernel_name):
        raise RootfsHandoffTrialExecutionGateError("observed kernel name is invalid")
    if not isinstance(evidence.observed_filesystem, str) or not _SAFE_FS_RE.fullmatch(evidence.observed_filesystem):
        raise RootfsHandoffTrialExecutionGateError("observed filesystem is invalid")
    if evidence.observed_encryption_state not in _ALLOWED_ENCRYPTION_STATES:
        raise RootfsHandoffTrialExecutionGateError("observed encryption state is not acceptable")
    _safe_relative_subpath(evidence.staging_subpath)

    for value, label in (
        (evidence.trial_plan_sha256, "trial plan"),
        (evidence.trial_preflight_sha256, "trial preflight"),
        (evidence.trial_authorization_sha256, "trial authorization"),
        (evidence.target_binding_sha256, "target binding"),
        (evidence.authorized_fresh_revalidation_sha256, "authorized fresh revalidation"),
        (evidence.execution_fresh_revalidation_sha256, "execution fresh revalidation"),
        (evidence.authorized_storage_discovery_sha256, "authorized storage discovery"),
        (evidence.execution_storage_discovery_sha256, "execution storage discovery"),
        (evidence.execution_storage_report_sha256, "execution storage report"),
        (evidence.rootfs_artifact_sha256, "rootfs artifact"),
        (evidence.recovery_plan_sha256, "recovery plan"),
    ):
        _sha(value, label)

    if evidence.authorized_fresh_revalidation_sha256 == evidence.execution_fresh_revalidation_sha256:
        raise RootfsHandoffTrialExecutionGateError("execution fresh revalidation must differ from authorization evidence")
    if evidence.authorized_storage_discovery_sha256 == evidence.execution_storage_discovery_sha256:
        raise RootfsHandoffTrialExecutionGateError("execution storage discovery must be a distinct capture")

    _positive(evidence.execution_storage_report_size, "execution storage report size")
    observed = _positive(evidence.observed_free_bytes, "observed free bytes")
    required = _positive(evidence.required_free_bytes, "required free bytes")
    if observed < required:
        raise RootfsHandoffTrialExecutionGateError("execution gate free-space observation is below requirement")
    _positive(evidence.rootfs_artifact_size, "rootfs artifact size")

    for name in _REQUIRED_TRUE_FLAGS:
        if getattr(evidence, name) is not True:
            raise RootfsHandoffTrialExecutionGateError(f"execution gate requires {name}=true")
    for name in _FORBIDDEN_FLAGS:
        if getattr(evidence, name) is not False:
            raise RootfsHandoffTrialExecutionGateError(f"execution gate requires {name}=false")


def write_rootfs_handoff_trial_execution_gate_evidence(
    evidence: RootfsHandoffTrialExecutionGateEvidence,
    destination: Path,
) -> str:
    validate_rootfs_handoff_trial_execution_gate_evidence(evidence)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise RootfsHandoffTrialExecutionGateError(f"refusing to overwrite existing output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(evidence.canonical_json())
    return evidence.evidence_sha256()


def load_rootfs_handoff_trial_execution_gate_evidence(
    path: Path,
) -> RootfsHandoffTrialExecutionGateEvidence:
    raw = _read_exact(Path(path))
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RootfsHandoffTrialExecutionGateError("execution-gate evidence is not valid UTF-8 JSON") from exc
    expected = {field.name for field in fields(RootfsHandoffTrialExecutionGateEvidence)}
    if not isinstance(value, dict) or set(value) != expected:
        raise RootfsHandoffTrialExecutionGateError("execution-gate evidence fields do not match schema-v1")
    try:
        evidence = RootfsHandoffTrialExecutionGateEvidence(**value)
    except TypeError as exc:
        raise RootfsHandoffTrialExecutionGateError("execution-gate evidence fields are invalid") from exc
    validate_rootfs_handoff_trial_execution_gate_evidence(evidence)
    if raw != evidence.canonical_json().encode("utf-8"):
        raise RootfsHandoffTrialExecutionGateError("execution-gate evidence is not canonical JSON")
    return evidence
