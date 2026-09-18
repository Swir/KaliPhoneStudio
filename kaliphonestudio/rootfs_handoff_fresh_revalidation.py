"""Fail-closed fresh-device revalidation before any rootfs trial authorization.

This module is deliberately non-executing. It consumes an already accepted
logical target-binding review plus a *new* read-only physical-storage discovery
chain from the same phone/firmware. It verifies that the reviewed logical target
identity still resolves to the same non-removable role/kernel/filesystem and an
acceptable encryption state with enough free capacity.

A successful revalidation is only evidence that a separate manual trial-
authorization stage may be considered. It never carries a raw block-device path
or mount target, never mounts or writes storage, never talks to a phone, never
executes a rootfs trial and never grants hardware or Beta credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .physical_storage_discovery import (
    PhysicalStorageDiscoveryError,
    PhysicalStorageDiscoveryEvidence,
    PhysicalStorageDiscoveryReport,
    load_physical_storage_discovery_evidence,
    load_physical_storage_discovery_report,
)
from .rootfs_handoff_target_binding import (
    RootfsHandoffTargetBindingError,
    RootfsHandoffTargetBindingEvidence,
    load_rootfs_handoff_target_binding_evidence,
    validate_rootfs_handoff_target_binding_evidence,
)

_POLICY = "reversible-rootfs-handoff-fresh-target-revalidation-v1"
_ALLOWED_ENCRYPTION_STATES = frozenset({"unlocked", "unencrypted"})
_MAX_EVIDENCE_BYTES = 2 * 1024 * 1024


class RootfsHandoffFreshRevalidationError(ValueError):
    """Raised when fresh target revalidation fails closed."""


@dataclass(frozen=True)
class RootfsHandoffFreshRevalidationEvidence:
    schema_version: int
    revalidation_policy: str
    profile_id: str
    device_serial: str
    firmware_build: str
    firmware_fingerprint: str
    target_binding_sha256: str
    previous_physical_storage_discovery_sha256: str
    fresh_physical_storage_discovery_sha256: str
    fresh_physical_storage_discovery_report_sha256: str
    fresh_physical_storage_discovery_report_size: int
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
    fresh_capture_chain_distinct: bool
    exact_logical_identity_matches: bool
    fresh_filesystem_identity_matches: bool
    fresh_encryption_state_acceptable: bool
    fresh_capacity_sufficient: bool
    recovery_plan_matches: bool
    fresh_device_revalidated: bool
    ready_for_separate_manual_trial_authorization: bool
    manual_trial_authorization_required: bool
    physical_gate_still_incomplete: bool
    raw_device_path_bound: bool
    mount_target_bound: bool
    trial_execution_allowed: bool
    write_authorized: bool
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


def _exact_role_observations(
    binding: RootfsHandoffTargetBindingEvidence,
    discovery: PhysicalStorageDiscoveryEvidence,
    report: PhysicalStorageDiscoveryReport,
) -> tuple[str, str, str, int]:
    role = binding.candidate_partition_role
    if discovery.partition_hint != role:
        raise RootfsHandoffFreshRevalidationError("fresh discovery partition role drifted from accepted target binding")
    if role in set(discovery.forbidden_partitions):
        raise RootfsHandoffFreshRevalidationError("fresh discovery marks the accepted target role as forbidden")

    fs_matches = [item for item in report.filesystems if item.partition_role == role]
    enc_matches = [item for item in report.encryption if item.partition_role == role]
    free_matches = [item for item in report.free_space if item.partition_role == role]
    if len(fs_matches) != 1 or len(enc_matches) != 1 or len(free_matches) != 1:
        raise RootfsHandoffFreshRevalidationError(
            "fresh target role requires one exact filesystem/encryption/free-space observation"
        )

    filesystem = fs_matches[0]
    encryption = enc_matches[0]
    free = free_matches[0]
    if filesystem.observed is not True or encryption.observed is not True or free.observed is not True:
        raise RootfsHandoffFreshRevalidationError("fresh logical target observations must all be physically observed")
    if filesystem.kernel_name != binding.observed_kernel_name:
        raise RootfsHandoffFreshRevalidationError("fresh logical target kernel identity drifted from accepted binding")
    if filesystem.filesystem != binding.observed_filesystem:
        raise RootfsHandoffFreshRevalidationError("fresh filesystem identity drifted from accepted binding")
    if encryption.state != binding.observed_encryption_state:
        raise RootfsHandoffFreshRevalidationError("fresh encryption state drifted from accepted binding")
    if encryption.state not in _ALLOWED_ENCRYPTION_STATES:
        raise RootfsHandoffFreshRevalidationError("fresh target is not unlocked or unencrypted")
    if free.free_bytes is None or free.free_bytes < binding.required_free_bytes:
        raise RootfsHandoffFreshRevalidationError("fresh free capacity is below the accepted trial requirement")

    block_matches = [item for item in report.block_devices if item.kernel_name == filesystem.kernel_name]
    if len(block_matches) != 1:
        raise RootfsHandoffFreshRevalidationError("fresh logical target must resolve to one exact block observation")
    if block_matches[0].removable is not False:
        raise RootfsHandoffFreshRevalidationError("fresh logical target must not resolve to removable storage")

    return filesystem.kernel_name, filesystem.filesystem, encryption.state, free.free_bytes


def _validate_input_binding(binding: RootfsHandoffTargetBindingEvidence) -> None:
    try:
        validate_rootfs_handoff_target_binding_evidence(binding)
    except RootfsHandoffTargetBindingError as exc:
        raise RootfsHandoffFreshRevalidationError(str(exc)) from exc
    if binding.decision != "accepted_for_manual_trial":
        raise RootfsHandoffFreshRevalidationError("fresh revalidation requires an accepted target-binding review")
    if binding.review_checks_complete is not True or binding.logical_target_identity_bound is not True:
        raise RootfsHandoffFreshRevalidationError("target binding is not fully reviewed and logically bound")
    if binding.fresh_device_revalidation_required is not True or binding.manual_trial_execution_required is not True:
        raise RootfsHandoffFreshRevalidationError("target binding does not require the mandatory later revalidation/trial gate")
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
        if getattr(binding, name) is not False:
            raise RootfsHandoffFreshRevalidationError(f"accepted target binding requires {name}=false")


def build_rootfs_handoff_fresh_revalidation(
    target_binding_path: Path,
    fresh_storage_discovery_path: Path,
    fresh_storage_report_path: Path,
) -> RootfsHandoffFreshRevalidationEvidence:
    try:
        binding = load_rootfs_handoff_target_binding_evidence(Path(target_binding_path))
        discovery = load_physical_storage_discovery_evidence(Path(fresh_storage_discovery_path))
        report, report_sha, report_size = load_physical_storage_discovery_report(Path(fresh_storage_report_path))
    except (RootfsHandoffTargetBindingError, PhysicalStorageDiscoveryError) as exc:
        raise RootfsHandoffFreshRevalidationError(str(exc)) from exc

    _validate_input_binding(binding)

    fresh_discovery_sha = discovery.evidence_sha256()
    if fresh_discovery_sha == binding.physical_storage_discovery_sha256:
        raise RootfsHandoffFreshRevalidationError(
            "fresh revalidation requires a distinct physical storage discovery chain, not the original reviewed discovery"
        )
    if discovery.discovery_report_sha256 != report_sha or discovery.discovery_report_size != report_size:
        raise RootfsHandoffFreshRevalidationError("fresh storage discovery is detached from supplied report bytes")
    if report.profile_id != discovery.profile_id or report.device_serial != discovery.device_serial:
        raise RootfsHandoffFreshRevalidationError("fresh storage report identity differs from fresh discovery evidence")

    for label, current, expected in (
        ("profile", discovery.profile_id, binding.profile_id),
        ("device serial", discovery.device_serial, binding.device_serial),
        ("firmware build", discovery.firmware_build, binding.firmware_build),
        ("firmware fingerprint", discovery.firmware_fingerprint, binding.firmware_fingerprint),
        ("rootfs artifact", discovery.rootfs_artifact_sha256, binding.rootfs_artifact_sha256),
        ("rootfs size", discovery.rootfs_artifact_size, binding.rootfs_artifact_size),
        ("recovery plan", discovery.recovery_plan_sha256, binding.recovery_plan_sha256),
    ):
        if current != expected:
            raise RootfsHandoffFreshRevalidationError(f"fresh {label} drifted from accepted target binding")

    if discovery.discovery_ready_for_manual_review is not True:
        raise RootfsHandoffFreshRevalidationError("fresh storage discovery is not complete enough for manual review")
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
            raise RootfsHandoffFreshRevalidationError(f"fresh storage discovery requires {name}=false")

    kernel_name, filesystem, encryption_state, free_bytes = _exact_role_observations(binding, discovery, report)

    evidence = RootfsHandoffFreshRevalidationEvidence(
        schema_version=1,
        revalidation_policy=_POLICY,
        profile_id=binding.profile_id,
        device_serial=binding.device_serial,
        firmware_build=binding.firmware_build,
        firmware_fingerprint=binding.firmware_fingerprint,
        target_binding_sha256=binding.evidence_sha256(),
        previous_physical_storage_discovery_sha256=binding.physical_storage_discovery_sha256,
        fresh_physical_storage_discovery_sha256=fresh_discovery_sha,
        fresh_physical_storage_discovery_report_sha256=report_sha,
        fresh_physical_storage_discovery_report_size=report_size,
        candidate_partition_role=binding.candidate_partition_role,
        observed_kernel_name=kernel_name,
        observed_filesystem=filesystem,
        observed_encryption_state=encryption_state,
        observed_free_bytes=free_bytes,
        required_free_bytes=binding.required_free_bytes,
        staging_subpath=binding.staging_subpath,
        rootfs_artifact_sha256=binding.rootfs_artifact_sha256,
        rootfs_artifact_size=binding.rootfs_artifact_size,
        recovery_plan_sha256=binding.recovery_plan_sha256,
        fresh_capture_chain_distinct=True,
        exact_logical_identity_matches=True,
        fresh_filesystem_identity_matches=True,
        fresh_encryption_state_acceptable=True,
        fresh_capacity_sufficient=True,
        recovery_plan_matches=True,
        fresh_device_revalidated=True,
        ready_for_separate_manual_trial_authorization=True,
        manual_trial_authorization_required=True,
        physical_gate_still_incomplete=True,
        raw_device_path_bound=False,
        mount_target_bound=False,
        trial_execution_allowed=False,
        write_authorized=False,
        handoff_ready=False,
        persistent_write_performed=False,
        phone_storage_written=False,
        storage_verified=False,
        recovery_verified=False,
        hardware_verified=False,
        beta_release_authorized=False,
        beta_gate_credit=False,
    )
    validate_rootfs_handoff_fresh_revalidation_evidence(evidence)
    return evidence


def validate_rootfs_handoff_fresh_revalidation_evidence(
    evidence: RootfsHandoffFreshRevalidationEvidence,
) -> None:
    if not isinstance(evidence, RootfsHandoffFreshRevalidationEvidence) or evidence.schema_version != 1:
        raise RootfsHandoffFreshRevalidationError("fresh target revalidation must be schema-v1 typed evidence")
    if evidence.revalidation_policy != _POLICY:
        raise RootfsHandoffFreshRevalidationError("fresh target revalidation policy is unsupported")
    if not evidence.profile_id or "/" not in evidence.profile_id or not evidence.device_serial:
        raise RootfsHandoffFreshRevalidationError("fresh target revalidation device identity is invalid")
    for value, label in (
        (evidence.target_binding_sha256, "target binding"),
        (evidence.previous_physical_storage_discovery_sha256, "previous storage discovery"),
        (evidence.fresh_physical_storage_discovery_sha256, "fresh storage discovery"),
        (evidence.fresh_physical_storage_discovery_report_sha256, "fresh storage report"),
        (evidence.rootfs_artifact_sha256, "rootfs artifact"),
        (evidence.recovery_plan_sha256, "recovery plan"),
    ):
        if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
            raise RootfsHandoffFreshRevalidationError(f"{label} digest is invalid")
    if evidence.previous_physical_storage_discovery_sha256 == evidence.fresh_physical_storage_discovery_sha256:
        raise RootfsHandoffFreshRevalidationError("fresh storage discovery must differ from the original bound discovery")
    if (
        not isinstance(evidence.fresh_physical_storage_discovery_report_size, int)
        or isinstance(evidence.fresh_physical_storage_discovery_report_size, bool)
        or evidence.fresh_physical_storage_discovery_report_size <= 0
    ):
        raise RootfsHandoffFreshRevalidationError("fresh storage report size is invalid")
    if (
        not isinstance(evidence.observed_free_bytes, int)
        or isinstance(evidence.observed_free_bytes, bool)
        or not isinstance(evidence.required_free_bytes, int)
        or isinstance(evidence.required_free_bytes, bool)
        or evidence.required_free_bytes <= 0
        or evidence.observed_free_bytes < evidence.required_free_bytes
    ):
        raise RootfsHandoffFreshRevalidationError("fresh target capacity evidence is invalid")
    if evidence.observed_encryption_state not in _ALLOWED_ENCRYPTION_STATES:
        raise RootfsHandoffFreshRevalidationError("fresh target encryption state is not acceptable")
    for name in (
        "fresh_capture_chain_distinct",
        "exact_logical_identity_matches",
        "fresh_filesystem_identity_matches",
        "fresh_encryption_state_acceptable",
        "fresh_capacity_sufficient",
        "recovery_plan_matches",
        "fresh_device_revalidated",
        "ready_for_separate_manual_trial_authorization",
        "manual_trial_authorization_required",
        "physical_gate_still_incomplete",
    ):
        if getattr(evidence, name) is not True:
            raise RootfsHandoffFreshRevalidationError(f"accepted fresh revalidation requires {name}=true")
    for name in (
        "raw_device_path_bound",
        "mount_target_bound",
        "trial_execution_allowed",
        "write_authorized",
        "handoff_ready",
        "persistent_write_performed",
        "phone_storage_written",
        "storage_verified",
        "recovery_verified",
        "hardware_verified",
        "beta_release_authorized",
        "beta_gate_credit",
    ):
        if getattr(evidence, name) is not False:
            raise RootfsHandoffFreshRevalidationError(f"fresh target revalidation requires {name}=false")


def write_rootfs_handoff_fresh_revalidation_evidence(
    evidence: RootfsHandoffFreshRevalidationEvidence,
    destination: Path,
) -> str:
    validate_rootfs_handoff_fresh_revalidation_evidence(evidence)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise RootfsHandoffFreshRevalidationError(f"refusing to overwrite existing output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = evidence.canonical_json()
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
    return evidence.evidence_sha256()


def load_rootfs_handoff_fresh_revalidation_evidence(
    path: Path,
) -> RootfsHandoffFreshRevalidationEvidence:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise RootfsHandoffFreshRevalidationError("fresh target revalidation evidence must be a regular non-symlink file")
    try:
        before = source.stat()
        raw = source.read_bytes()
        after = source.stat()
    except OSError as exc:
        raise RootfsHandoffFreshRevalidationError(f"cannot read fresh target revalidation evidence: {exc}") from exc
    if not raw or len(raw) > _MAX_EVIDENCE_BYTES:
        raise RootfsHandoffFreshRevalidationError("fresh target revalidation evidence size is outside the safety limit")
    if (
        before.st_size != len(raw)
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or getattr(before, "st_ino", None) != getattr(after, "st_ino", None)
    ):
        raise RootfsHandoffFreshRevalidationError("fresh target revalidation evidence changed while being read")
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RootfsHandoffFreshRevalidationError("fresh target revalidation evidence is not valid UTF-8 JSON") from exc
    expected = {field.name for field in fields(RootfsHandoffFreshRevalidationEvidence)}
    if not isinstance(value, dict) or set(value) != expected:
        raise RootfsHandoffFreshRevalidationError("fresh target revalidation fields do not match schema-v1")
    try:
        evidence = RootfsHandoffFreshRevalidationEvidence(**value)
    except TypeError as exc:
        raise RootfsHandoffFreshRevalidationError("fresh target revalidation types are invalid") from exc
    validate_rootfs_handoff_fresh_revalidation_evidence(evidence)
    if raw != evidence.canonical_json().encode("utf-8"):
        raise RootfsHandoffFreshRevalidationError("fresh target revalidation evidence is not canonical JSON")
    return evidence
