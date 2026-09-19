"""Offline exact-byte rootfs preflight before any interactive trial executor.

This layer consumes one accepted non-executing rootfs trial plan and re-hashes the
local Kali rootfs artifact named by that plan. It deliberately does not connect
to a phone, resolve a raw block-device path, mount storage, execute a trial,
authorize a persistent write, or grant storage/recovery/hardware/Beta credit.

A successful preflight proves only that the local rootfs bytes still match the
reviewed plan. Live device/firmware/target/recovery checks and explicit operator
confirmation remain mandatory at the later interactive execution boundary.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any

from .rootfs_handoff_trial_plan import (
    RootfsHandoffTrialPlan,
    RootfsHandoffTrialPlanError,
    load_rootfs_handoff_trial_plan,
    validate_rootfs_handoff_trial_plan,
)
from .stable_file import StableFileError, hash_stable_regular_file

_POLICY = "rootfs-handoff-local-rootfs-preflight-v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ROLE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
_SAFE_FS_RE = re.compile(r"^[a-z0-9][a-z0-9._+-]{0,31}$")
_ALLOWED_ENCRYPTION_STATES = frozenset({"unlocked", "unencrypted"})
_MAX_EVIDENCE_BYTES = 2 * 1024 * 1024
_MAX_ROOTFS_ARTIFACT_BYTES = 64 * 1024 * 1024 * 1024

_REQUIRED_PLAN_FLAGS = (
    "exact_authorization_chain_bound",
    "rootfs_local_hash_recheck_required",
    "live_device_identity_recheck_required",
    "live_firmware_recheck_required",
    "live_target_identity_recheck_required",
    "live_filesystem_encryption_capacity_recheck_required",
    "recovery_readiness_recheck_required",
    "explicit_operator_confirmation_required",
    "write_scope_confirmation_required",
    "plan_ready_for_later_interactive_executor",
    "physical_gate_still_incomplete",
)

_FORBIDDEN_PLAN_FLAGS = (
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

_REQUIRED_PREFLIGHT_FLAGS = (
    "exact_trial_plan_bound",
    "local_rootfs_exact_bytes_verified",
    "live_device_identity_recheck_required",
    "live_firmware_recheck_required",
    "live_target_identity_recheck_required",
    "live_filesystem_encryption_capacity_recheck_required",
    "recovery_readiness_recheck_required",
    "explicit_operator_confirmation_required",
    "write_scope_confirmation_required",
    "interactive_executor_still_required",
    "physical_gate_still_incomplete",
)

_FORBIDDEN_PREFLIGHT_FLAGS = (
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


class RootfsHandoffTrialPreflightError(ValueError):
    """Raised when local rootfs preflight evidence cannot be proved exact/safe."""


@dataclass(frozen=True)
class RootfsHandoffTrialPreflightEvidence:
    schema_version: int
    preflight_policy: str
    profile_id: str
    device_serial: str
    firmware_build: str
    firmware_fingerprint: str
    trial_plan_sha256: str
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
    exact_trial_plan_bound: bool
    local_rootfs_exact_bytes_verified: bool
    live_device_identity_recheck_required: bool
    live_firmware_recheck_required: bool
    live_target_identity_recheck_required: bool
    live_filesystem_encryption_capacity_recheck_required: bool
    recovery_readiness_recheck_required: bool
    explicit_operator_confirmation_required: bool
    write_scope_confirmation_required: bool
    interactive_executor_still_required: bool
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
        raise RootfsHandoffTrialPreflightError(f"{label} must be non-empty bounded text")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise RootfsHandoffTrialPreflightError(f"{label} contains control data")
    return value


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise RootfsHandoffTrialPreflightError(f"{label} must be a lowercase SHA-256")
    return value


def _positive(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise RootfsHandoffTrialPreflightError(f"{label} must be a positive integer")
    return value


def _safe_relative_subpath(value: object) -> str:
    text = _safe_text(value, "staging subpath", 512)
    if text.startswith(("/", "\\")) or ":" in text or "\\" in text:
        raise RootfsHandoffTrialPreflightError("staging subpath must be relative and path-independent")
    path = PurePosixPath(text)
    if not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise RootfsHandoffTrialPreflightError("staging subpath must be a safe relative POSIX path")
    return path.as_posix()


def _read_exact(path: Path) -> bytes:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise RootfsHandoffTrialPreflightError("trial preflight evidence must be a regular non-symlink file")
    try:
        before = source.stat()
        if before.st_size <= 0 or before.st_size > _MAX_EVIDENCE_BYTES:
            raise RootfsHandoffTrialPreflightError("trial preflight evidence size is outside the safety limit")
        raw = source.read_bytes()
        after = source.stat()
    except OSError as exc:
        raise RootfsHandoffTrialPreflightError(f"cannot read trial preflight evidence: {exc}") from exc
    if len(raw) != before.st_size:
        raise RootfsHandoffTrialPreflightError("trial preflight evidence size changed while being read")
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or getattr(before, "st_ino", None) != getattr(after, "st_ino", None)
    ):
        raise RootfsHandoffTrialPreflightError("trial preflight evidence changed while being read")
    return raw


def _stable_rootfs_identity(path: Path, expected_size: int) -> tuple[str, int]:
    try:
        identity = hash_stable_regular_file(
            Path(path),
            max_bytes=_MAX_ROOTFS_ARTIFACT_BYTES,
            expected_size=expected_size,
            label="rootfs artifact",
        )
    except StableFileError as exc:
        raise RootfsHandoffTrialPreflightError(str(exc)) from exc
    return identity.sha256, identity.size


def _validate_plan_for_preflight(plan: RootfsHandoffTrialPlan) -> None:
    try:
        validate_rootfs_handoff_trial_plan(plan)
    except RootfsHandoffTrialPlanError as exc:
        raise RootfsHandoffTrialPreflightError(str(exc)) from exc
    for name in _REQUIRED_PLAN_FLAGS:
        if getattr(plan, name, None) is not True:
            raise RootfsHandoffTrialPreflightError(f"trial plan requires {name}=true")
    for name in _FORBIDDEN_PLAN_FLAGS:
        if getattr(plan, name, None) is not False:
            raise RootfsHandoffTrialPreflightError(f"trial plan requires {name}=false")


def build_rootfs_handoff_trial_preflight(
    trial_plan_path: Path,
    rootfs_artifact_path: Path,
) -> RootfsHandoffTrialPreflightEvidence:
    try:
        plan = load_rootfs_handoff_trial_plan(Path(trial_plan_path))
    except RootfsHandoffTrialPlanError as exc:
        raise RootfsHandoffTrialPreflightError(str(exc)) from exc
    _validate_plan_for_preflight(plan)

    local_sha, local_size = _stable_rootfs_identity(Path(rootfs_artifact_path), plan.rootfs_artifact_size)
    if local_sha != plan.rootfs_artifact_sha256:
        raise RootfsHandoffTrialPreflightError("local rootfs artifact SHA-256 differs from trial plan")

    evidence = RootfsHandoffTrialPreflightEvidence(
        schema_version=1,
        preflight_policy=_POLICY,
        profile_id=plan.profile_id,
        device_serial=plan.device_serial,
        firmware_build=plan.firmware_build,
        firmware_fingerprint=plan.firmware_fingerprint,
        trial_plan_sha256=plan.evidence_sha256(),
        trial_authorization_sha256=plan.trial_authorization_sha256,
        target_binding_sha256=plan.target_binding_sha256,
        fresh_revalidation_sha256=plan.fresh_revalidation_sha256,
        candidate_partition_role=plan.candidate_partition_role,
        observed_kernel_name=plan.observed_kernel_name,
        observed_filesystem=plan.observed_filesystem,
        observed_encryption_state=plan.observed_encryption_state,
        observed_free_bytes=plan.observed_free_bytes,
        required_free_bytes=plan.required_free_bytes,
        staging_subpath=plan.staging_subpath,
        rootfs_artifact_sha256=local_sha,
        rootfs_artifact_size=local_size,
        recovery_plan_sha256=plan.recovery_plan_sha256,
        exact_trial_plan_bound=True,
        local_rootfs_exact_bytes_verified=True,
        live_device_identity_recheck_required=True,
        live_firmware_recheck_required=True,
        live_target_identity_recheck_required=True,
        live_filesystem_encryption_capacity_recheck_required=True,
        recovery_readiness_recheck_required=True,
        explicit_operator_confirmation_required=True,
        write_scope_confirmation_required=True,
        interactive_executor_still_required=True,
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
    validate_rootfs_handoff_trial_preflight_evidence(evidence)
    return evidence


def validate_rootfs_handoff_trial_preflight_evidence(
    evidence: RootfsHandoffTrialPreflightEvidence,
) -> None:
    if not isinstance(evidence, RootfsHandoffTrialPreflightEvidence) or evidence.schema_version != 1:
        raise RootfsHandoffTrialPreflightError("trial preflight must be schema-v1 typed evidence")
    if evidence.preflight_policy != _POLICY:
        raise RootfsHandoffTrialPreflightError("trial preflight policy is unsupported")
    if "/" not in _safe_text(evidence.profile_id, "profile id", 128):
        raise RootfsHandoffTrialPreflightError("profile id must use vendor/codename form")
    _safe_text(evidence.device_serial, "device serial", 256)
    _safe_text(evidence.firmware_build, "firmware build", 256)
    _safe_text(evidence.firmware_fingerprint, "firmware fingerprint", 1024)
    role = evidence.candidate_partition_role
    if not isinstance(role, str) or not _SAFE_ROLE_RE.fullmatch(role):
        raise RootfsHandoffTrialPreflightError("candidate partition role is invalid")
    kernel = evidence.observed_kernel_name
    if not isinstance(kernel, str) or not _SAFE_NAME_RE.fullmatch(kernel):
        raise RootfsHandoffTrialPreflightError("observed kernel name is invalid")
    filesystem = evidence.observed_filesystem
    if not isinstance(filesystem, str) or not _SAFE_FS_RE.fullmatch(filesystem):
        raise RootfsHandoffTrialPreflightError("observed filesystem is invalid")
    if evidence.observed_encryption_state not in _ALLOWED_ENCRYPTION_STATES:
        raise RootfsHandoffTrialPreflightError("observed encryption state is not acceptable for trial preflight")
    _safe_relative_subpath(evidence.staging_subpath)
    for value, label in (
        (evidence.trial_plan_sha256, "trial plan"),
        (evidence.trial_authorization_sha256, "trial authorization"),
        (evidence.target_binding_sha256, "target binding"),
        (evidence.fresh_revalidation_sha256, "fresh revalidation"),
        (evidence.rootfs_artifact_sha256, "rootfs artifact"),
        (evidence.recovery_plan_sha256, "recovery plan"),
    ):
        _sha(value, label)
    observed = _positive(evidence.observed_free_bytes, "observed free bytes")
    required = _positive(evidence.required_free_bytes, "required free bytes")
    if observed < required:
        raise RootfsHandoffTrialPreflightError("trial preflight free-space observation is below requirement")
    artifact_size = _positive(evidence.rootfs_artifact_size, "rootfs artifact size")
    if artifact_size > _MAX_ROOTFS_ARTIFACT_BYTES:
        raise RootfsHandoffTrialPreflightError("rootfs artifact size exceeds the bounded preflight limit")
    for name in _REQUIRED_PREFLIGHT_FLAGS:
        if getattr(evidence, name) is not True:
            raise RootfsHandoffTrialPreflightError(f"trial preflight requires {name}=true")
    for name in _FORBIDDEN_PREFLIGHT_FLAGS:
        if getattr(evidence, name) is not False:
            raise RootfsHandoffTrialPreflightError(f"trial preflight requires {name}=false")


def write_rootfs_handoff_trial_preflight_evidence(
    evidence: RootfsHandoffTrialPreflightEvidence,
    destination: Path,
) -> str:
    validate_rootfs_handoff_trial_preflight_evidence(evidence)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise RootfsHandoffTrialPreflightError(f"refusing to overwrite existing output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(evidence.canonical_json())
    return evidence.evidence_sha256()


def load_rootfs_handoff_trial_preflight_evidence(path: Path) -> RootfsHandoffTrialPreflightEvidence:
    raw = _read_exact(Path(path))
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RootfsHandoffTrialPreflightError("trial preflight evidence is not valid UTF-8 JSON") from exc
    expected = {field.name for field in fields(RootfsHandoffTrialPreflightEvidence)}
    if not isinstance(value, dict) or set(value) != expected:
        raise RootfsHandoffTrialPreflightError("trial preflight evidence fields do not match schema-v1")
    try:
        evidence = RootfsHandoffTrialPreflightEvidence(**value)
    except TypeError as exc:
        raise RootfsHandoffTrialPreflightError("trial preflight evidence fields are invalid") from exc
    validate_rootfs_handoff_trial_preflight_evidence(evidence)
    if raw != evidence.canonical_json().encode("utf-8"):
        raise RootfsHandoffTrialPreflightError("trial preflight evidence is not canonical JSON")
    return evidence
