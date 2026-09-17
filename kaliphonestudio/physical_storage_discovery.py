"""Fail-closed physical storage discovery evidence for rootfs handoff review.

This module records read-only observations only.  It deliberately does not
select a block-device path, mount target, staging target, or authorize any write.
The resulting evidence is bound to one exact discovery-only handoff assessment
and the exact rescue diagnostics/functional-probe chain from the same physical
transcript.  It remains manual-review-only and grants no hardware/Beta credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from .physical_rescue_diagnostics import (
    PhysicalRescueDiagnosticsEvidence,
    PhysicalRescueDiagnosticsError,
    validate_physical_rescue_diagnostics_evidence,
)
from .physical_rescue_functional_probes import (
    PhysicalRescueFunctionalProbeEvidence,
    PhysicalRescueFunctionalProbeError,
    validate_physical_rescue_functional_probe_evidence,
)
from .profiles import DeviceProfile
from .rootfs_handoff import (
    RootfsHandoffAssessmentEvidence,
    RootfsHandoffError,
    rootfs_handoff_contract,
)

_POLICY = "operator-read-only-storage-discovery-v1"
_MAX_REPORT_BYTES = 2 * 1024 * 1024
_MAX_RECOVERY_PLAN_BYTES = 2 * 1024 * 1024
_MAX_RECORDS = 128
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
_SAFE_ROLE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_SAFE_FS_RE = re.compile(r"^[a-z0-9][a-z0-9._+-]{0,31}$")
_SAFE_FEATURE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._=:+-]{0,127}$")
_ALLOWED_ENCRYPTION_STATES = frozenset({"encrypted", "unencrypted", "locked", "unlocked", "unknown"})


class PhysicalStorageDiscoveryError(ValueError):
    pass


@dataclass(frozen=True)
class StorageBlockObservation:
    kernel_name: str
    size_sectors: int
    removable: bool


@dataclass(frozen=True)
class StorageFilesystemObservation:
    partition_role: str
    kernel_name: str
    filesystem: str
    observed: bool


@dataclass(frozen=True)
class StorageEncryptionObservation:
    partition_role: str
    state: str
    features: tuple[str, ...]
    observed: bool


@dataclass(frozen=True)
class StorageFreeSpaceObservation:
    partition_role: str
    total_bytes: int | None
    free_bytes: int | None
    observed: bool


@dataclass(frozen=True)
class PhysicalStorageDiscoveryReport:
    schema_version: int
    profile_id: str
    device_serial: str
    collection_policy: str
    block_devices: tuple[StorageBlockObservation, ...]
    filesystems: tuple[StorageFilesystemObservation, ...]
    encryption: tuple[StorageEncryptionObservation, ...]
    free_space: tuple[StorageFreeSpaceObservation, ...]
    phone_storage_written: bool
    target_selected: bool
    storage_path_bound: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def report_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PhysicalStorageDiscoveryEvidence:
    schema_version: int
    profile_id: str
    device_serial: str
    firmware_build: str
    firmware_fingerprint: str
    rootfs_handoff_assessment_sha256: str
    rootfs_handoff_contract_sha256: str
    physical_candidate_gate_sha256: str
    rootfs_authority_sha256: str
    rootfs_artifact_sha256: str
    rootfs_artifact_size: int
    rescue_diagnostics_sha256: str
    rescue_functional_probe_sha256: str
    transcript_sha256: str
    rescue_probe_id: str
    discovery_report_sha256: str
    discovery_report_size: int
    recovery_plan_sha256: str
    recovery_plan_size: int
    storage_bus: str
    partition_hint: str
    expected_filesystems: tuple[str, ...]
    expected_encryption_features: tuple[str, ...]
    forbidden_partitions: tuple[str, ...]
    block_device_count: int
    filesystem_observation_count: int
    encryption_observation_count: int
    free_space_observation_count: int
    topology_bound_to_rescue_diagnostics: bool
    storage_bus_signal_observed: bool
    filesystem_identity_observed: bool
    expected_filesystem_observed: bool
    encryption_state_observed: bool
    expected_encryption_features_observed: bool
    free_space_observed: bool
    recovery_plan_bound: bool
    all_required_categories_recorded: bool
    discovery_ready_for_manual_review: bool
    target_selected: bool
    storage_path_bound: bool
    write_authorized: bool
    handoff_ready: bool
    storage_verified: bool
    recovery_verified: bool
    phone_storage_written: bool
    manual_review_required: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _safe_text(value: object, label: str, max_len: int = 512) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len:
        raise PhysicalStorageDiscoveryError(f"{label} must be non-empty bounded text")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise PhysicalStorageDiscoveryError(f"{label} contains control data")
    return value


def _safe_name(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_NAME_RE.fullmatch(value):
        raise PhysicalStorageDiscoveryError(f"{label} must be a safe kernel/name token")
    return value


def _safe_role(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_ROLE_RE.fullmatch(value):
        raise PhysicalStorageDiscoveryError(f"{label} must be a safe lowercase role token")
    return value


def _safe_fs(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_FS_RE.fullmatch(value):
        raise PhysicalStorageDiscoveryError(f"{label} must be a safe filesystem token")
    return value


def _safe_feature(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_FEATURE_RE.fullmatch(value):
        raise PhysicalStorageDiscoveryError(f"{label} contains an unsafe feature token")
    return value


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise PhysicalStorageDiscoveryError(f"{label} must be a lowercase SHA-256")
    return value


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PhysicalStorageDiscoveryError(f"{label} must be a positive integer")
    return value


def _nonnegative_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise PhysicalStorageDiscoveryError(f"{label} must be a non-negative integer")
    return value


def _exact_keys(raw: object, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != expected:
        raise PhysicalStorageDiscoveryError(f"{label} fields do not match schema-v1")
    return raw


def _parse_block(raw: object) -> StorageBlockObservation:
    item = _exact_keys(raw, {"kernel_name", "size_sectors", "removable"}, "block observation")
    name = _safe_name(item["kernel_name"], "block kernel name")
    size = _positive_int(item["size_sectors"], "block size sectors")
    removable = item["removable"]
    if not isinstance(removable, bool):
        raise PhysicalStorageDiscoveryError("block removable must be boolean")
    return StorageBlockObservation(name, size, removable)


def _parse_filesystem(raw: object) -> StorageFilesystemObservation:
    item = _exact_keys(raw, {"partition_role", "kernel_name", "filesystem", "observed"}, "filesystem observation")
    observed = item["observed"]
    if not isinstance(observed, bool):
        raise PhysicalStorageDiscoveryError("filesystem observed must be boolean")
    filesystem = _safe_fs(item["filesystem"], "filesystem")
    if not observed and filesystem != "unknown":
        raise PhysicalStorageDiscoveryError("unobserved filesystem must use filesystem=unknown")
    return StorageFilesystemObservation(
        _safe_role(item["partition_role"], "filesystem partition role"),
        _safe_name(item["kernel_name"], "filesystem kernel name"),
        filesystem,
        observed,
    )


def _parse_encryption(raw: object) -> StorageEncryptionObservation:
    item = _exact_keys(raw, {"partition_role", "state", "features", "observed"}, "encryption observation")
    observed = item["observed"]
    if not isinstance(observed, bool):
        raise PhysicalStorageDiscoveryError("encryption observed must be boolean")
    state = item["state"]
    if state not in _ALLOWED_ENCRYPTION_STATES:
        raise PhysicalStorageDiscoveryError("encryption state is unsupported")
    features_raw = item["features"]
    if not isinstance(features_raw, list) or len(features_raw) > 32:
        raise PhysicalStorageDiscoveryError("encryption features must be a bounded list")
    features = tuple(_safe_feature(value, "encryption feature") for value in features_raw)
    if len(features) != len(set(features)):
        raise PhysicalStorageDiscoveryError("encryption features must not contain duplicates")
    if not observed and (state != "unknown" or features):
        raise PhysicalStorageDiscoveryError("unobserved encryption must use state=unknown with no features")
    return StorageEncryptionObservation(
        _safe_role(item["partition_role"], "encryption partition role"),
        state,
        features,
        observed,
    )


def _parse_free_space(raw: object) -> StorageFreeSpaceObservation:
    item = _exact_keys(raw, {"partition_role", "total_bytes", "free_bytes", "observed"}, "free-space observation")
    observed = item["observed"]
    if not isinstance(observed, bool):
        raise PhysicalStorageDiscoveryError("free-space observed must be boolean")
    total, free = item["total_bytes"], item["free_bytes"]
    if observed:
        total = _positive_int(total, "free-space total bytes")
        free = _nonnegative_int(free, "free-space free bytes")
        if free > total:
            raise PhysicalStorageDiscoveryError("free-space free bytes cannot exceed total bytes")
    elif total is not None or free is not None:
        raise PhysicalStorageDiscoveryError("unobserved free-space must use null byte values")
    return StorageFreeSpaceObservation(
        _safe_role(item["partition_role"], "free-space partition role"),
        total,
        free,
        observed,
    )


def parse_physical_storage_discovery_report(raw: object) -> PhysicalStorageDiscoveryReport:
    item = _exact_keys(
        raw,
        {
            "schema_version", "profile_id", "device_serial", "collection_policy",
            "block_devices", "filesystems", "encryption", "free_space",
            "phone_storage_written", "target_selected", "storage_path_bound",
        },
        "physical storage discovery report",
    )
    if item["schema_version"] != 1:
        raise PhysicalStorageDiscoveryError("unsupported physical storage discovery report schema")
    if item["collection_policy"] != _POLICY:
        raise PhysicalStorageDiscoveryError("physical storage discovery report policy is unsupported")
    for flag in ("phone_storage_written", "target_selected", "storage_path_bound"):
        if item[flag] is not False:
            raise PhysicalStorageDiscoveryError(f"physical storage discovery report requires {flag}=false")
    collections = []
    for name, parser in (
        ("block_devices", _parse_block),
        ("filesystems", _parse_filesystem),
        ("encryption", _parse_encryption),
        ("free_space", _parse_free_space),
    ):
        values = item[name]
        if not isinstance(values, list) or len(values) > _MAX_RECORDS:
            raise PhysicalStorageDiscoveryError(f"{name} must be a bounded list")
        collections.append(tuple(parser(value) for value in values))
    blocks, filesystems, encryption, free_space = collections
    if len({x.kernel_name for x in blocks}) != len(blocks):
        raise PhysicalStorageDiscoveryError("block observations must have unique kernel names")
    for values, label, key in (
        (filesystems, "filesystem", lambda x: x.partition_role),
        (encryption, "encryption", lambda x: x.partition_role),
        (free_space, "free-space", lambda x: x.partition_role),
    ):
        keys = [key(value) for value in values]
        if len(keys) != len(set(keys)):
            raise PhysicalStorageDiscoveryError(f"{label} observations must have unique partition roles")
    return PhysicalStorageDiscoveryReport(
        schema_version=1,
        profile_id=_safe_text(item["profile_id"], "report profile id", 128),
        device_serial=_safe_text(item["device_serial"], "report device serial", 256),
        collection_policy=_POLICY,
        block_devices=blocks,
        filesystems=filesystems,
        encryption=encryption,
        free_space=free_space,
        phone_storage_written=False,
        target_selected=False,
        storage_path_bound=False,
    )


def load_physical_storage_discovery_report(path: Path) -> tuple[PhysicalStorageDiscoveryReport, str, int]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalStorageDiscoveryError("physical storage discovery report must be a regular non-symlink file")
    before = source.stat()
    raw = source.read_bytes()
    after = source.stat()
    if before.st_size <= 0 or before.st_size > _MAX_REPORT_BYTES or len(raw) != before.st_size:
        raise PhysicalStorageDiscoveryError("physical storage discovery report size is outside the safety limit")
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise PhysicalStorageDiscoveryError("physical storage discovery report changed while being read")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalStorageDiscoveryError("physical storage discovery report is not valid UTF-8 JSON") from exc
    report = parse_physical_storage_discovery_report(value)
    return report, sha256(raw).hexdigest(), len(raw)


def _read_recovery_plan(path: Path) -> tuple[str, int]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalStorageDiscoveryError("recovery plan must be a regular non-symlink file")
    before = source.stat()
    raw = source.read_bytes()
    after = source.stat()
    if before.st_size <= 0 or before.st_size > _MAX_RECOVERY_PLAN_BYTES or len(raw) != before.st_size:
        raise PhysicalStorageDiscoveryError("recovery plan size is outside the safety limit")
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise PhysicalStorageDiscoveryError("recovery plan changed while being read")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PhysicalStorageDiscoveryError("recovery plan must be UTF-8 text") from exc
    if not text.strip() or "\x00" in text:
        raise PhysicalStorageDiscoveryError("recovery plan is empty or contains NUL data")
    return sha256(raw).hexdigest(), len(raw)


def _validate_assessment(profile: DeviceProfile, assessment: RootfsHandoffAssessmentEvidence) -> None:
    if not isinstance(profile, DeviceProfile):
        raise PhysicalStorageDiscoveryError("profile must be typed DeviceProfile evidence")
    if not isinstance(assessment, RootfsHandoffAssessmentEvidence) or assessment.schema_version != 1:
        raise PhysicalStorageDiscoveryError("rootfs handoff assessment must be schema-v1 typed evidence")
    contract = rootfs_handoff_contract(profile)
    if assessment.profile_id != profile.profile_id:
        raise PhysicalStorageDiscoveryError("rootfs handoff assessment profile mismatch")
    if assessment.rootfs_handoff_contract_sha256 != contract.contract_sha256():
        raise PhysicalStorageDiscoveryError("rootfs handoff assessment is detached from current profile contract")
    if assessment.target_selected or assessment.storage_path_bound or assessment.write_authorized or assessment.handoff_ready:
        raise PhysicalStorageDiscoveryError("rootfs handoff assessment must remain discovery-only")
    if assessment.manual_review_required is not True or assessment.hardware_verified or assessment.beta_gate_credit:
        raise PhysicalStorageDiscoveryError("rootfs handoff assessment contains unsupported review/hardware claims")


def _topology_matches_diagnostics(report: PhysicalStorageDiscoveryReport, diagnostics: PhysicalRescueDiagnosticsEvidence) -> bool:
    diag: set[tuple[str, int, bool]] = set()
    for record in diagnostics.records:
        if record.kind != "BLOCK":
            continue
        name, sectors, removable = record.values
        if not sectors.isdigit() or removable not in {"0", "1"}:
            continue
        diag.add((name, int(sectors), removable == "1"))
    return bool(report.block_devices) and all(
        (item.kernel_name, item.size_sectors, item.removable) in diag for item in report.block_devices
    )


def _role_item(items: tuple[Any, ...], role: str) -> Any | None:
    return next((item for item in items if item.partition_role == role), None)


def bind_physical_storage_discovery(
    profile: DeviceProfile,
    assessment: RootfsHandoffAssessmentEvidence,
    diagnostics: PhysicalRescueDiagnosticsEvidence,
    functional_probe: PhysicalRescueFunctionalProbeEvidence,
    report: PhysicalStorageDiscoveryReport,
    *,
    discovery_report_sha256: str,
    discovery_report_size: int,
    recovery_plan_sha256: str,
    recovery_plan_size: int,
) -> PhysicalStorageDiscoveryEvidence:
    """Bind raw physical storage observations without selecting or modifying a target."""
    try:
        _validate_assessment(profile, assessment)
    except RootfsHandoffError as exc:
        raise PhysicalStorageDiscoveryError(str(exc)) from exc
    try:
        validate_physical_rescue_diagnostics_evidence(diagnostics)
    except PhysicalRescueDiagnosticsError as exc:
        raise PhysicalStorageDiscoveryError(str(exc)) from exc
    try:
        validate_physical_rescue_functional_probe_evidence(functional_probe)
    except PhysicalRescueFunctionalProbeError as exc:
        raise PhysicalStorageDiscoveryError(str(exc)) from exc
    if report.profile_id != profile.profile_id or report.profile_id != assessment.profile_id:
        raise PhysicalStorageDiscoveryError("storage discovery report profile mismatch")
    if report.device_serial != assessment.device_serial:
        raise PhysicalStorageDiscoveryError("storage discovery report serial mismatch")
    if diagnostics.profile_id != assessment.profile_id or diagnostics.device_serial != assessment.device_serial:
        raise PhysicalStorageDiscoveryError("rescue diagnostics do not match rootfs handoff assessment")
    if functional_probe.profile_id != assessment.profile_id or functional_probe.device_serial != assessment.device_serial:
        raise PhysicalStorageDiscoveryError("functional probe does not match rootfs handoff assessment")
    if functional_probe.rescue_diagnostics_sha256 != diagnostics.evidence_sha256():
        raise PhysicalStorageDiscoveryError("functional probe is detached from supplied rescue diagnostics")
    if functional_probe.transcript_sha256 != diagnostics.transcript_sha256 or functional_probe.rescue_probe_id != diagnostics.rescue_probe_id:
        raise PhysicalStorageDiscoveryError("physical storage evidence chain transcript/probe identity drifted")
    if diagnostics.phone_storage_written or functional_probe.phone_storage_written:
        raise PhysicalStorageDiscoveryError("physical storage discovery requires a no-write rescue evidence chain")

    report_sha = _digest(discovery_report_sha256, "discovery report SHA-256")
    report_size = _positive_int(discovery_report_size, "discovery report size")
    recovery_sha = _digest(recovery_plan_sha256, "recovery plan SHA-256")
    recovery_size = _positive_int(recovery_plan_size, "recovery plan size")

    contract = rootfs_handoff_contract(profile)
    topology_bound = _topology_matches_diagnostics(report, diagnostics)
    bus_signal = diagnostics.ufs_signal_observed if contract.storage_bus == "ufs" else False
    fs = _role_item(report.filesystems, contract.partition_hint)
    filesystem_observed = bool(fs is not None and fs.observed)
    expected_fs = bool(filesystem_observed and fs.filesystem in contract.expected_filesystems)
    enc = _role_item(report.encryption, contract.partition_hint)
    encryption_observed = bool(enc is not None and enc.observed and enc.state != "unknown")
    expected_enc = bool(
        encryption_observed and set(contract.encryption_features).issubset(set(enc.features))
    )
    free = _role_item(report.free_space, contract.partition_hint)
    free_observed = bool(free is not None and free.observed and free.total_bytes and free.free_bytes is not None)
    recovery_bound = recovery_size > 0
    all_required = topology_bound and filesystem_observed and encryption_observed and free_observed and recovery_bound
    review_ready = all_required and bus_signal and expected_fs and expected_enc

    evidence = PhysicalStorageDiscoveryEvidence(
        schema_version=1,
        profile_id=assessment.profile_id,
        device_serial=assessment.device_serial,
        firmware_build=assessment.firmware_build,
        firmware_fingerprint=assessment.firmware_fingerprint,
        rootfs_handoff_assessment_sha256=assessment.evidence_sha256(),
        rootfs_handoff_contract_sha256=assessment.rootfs_handoff_contract_sha256,
        physical_candidate_gate_sha256=assessment.physical_candidate_gate_sha256,
        rootfs_authority_sha256=assessment.rootfs_authority_sha256,
        rootfs_artifact_sha256=assessment.rootfs_artifact_sha256,
        rootfs_artifact_size=assessment.rootfs_artifact_size,
        rescue_diagnostics_sha256=diagnostics.evidence_sha256(),
        rescue_functional_probe_sha256=functional_probe.evidence_sha256(),
        transcript_sha256=diagnostics.transcript_sha256,
        rescue_probe_id=diagnostics.rescue_probe_id,
        discovery_report_sha256=report_sha,
        discovery_report_size=report_size,
        recovery_plan_sha256=recovery_sha,
        recovery_plan_size=recovery_size,
        storage_bus=contract.storage_bus,
        partition_hint=contract.partition_hint,
        expected_filesystems=contract.expected_filesystems,
        expected_encryption_features=contract.encryption_features,
        forbidden_partitions=contract.forbidden_partitions,
        block_device_count=len(report.block_devices),
        filesystem_observation_count=len(report.filesystems),
        encryption_observation_count=len(report.encryption),
        free_space_observation_count=len(report.free_space),
        topology_bound_to_rescue_diagnostics=topology_bound,
        storage_bus_signal_observed=bus_signal,
        filesystem_identity_observed=filesystem_observed,
        expected_filesystem_observed=expected_fs,
        encryption_state_observed=encryption_observed,
        expected_encryption_features_observed=expected_enc,
        free_space_observed=free_observed,
        recovery_plan_bound=recovery_bound,
        all_required_categories_recorded=all_required,
        discovery_ready_for_manual_review=review_ready,
        target_selected=False,
        storage_path_bound=False,
        write_authorized=False,
        handoff_ready=False,
        storage_verified=False,
        recovery_verified=False,
        phone_storage_written=False,
        manual_review_required=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    validate_physical_storage_discovery_evidence(evidence)
    return evidence


def validate_physical_storage_discovery_evidence(evidence: PhysicalStorageDiscoveryEvidence) -> None:
    if not isinstance(evidence, PhysicalStorageDiscoveryEvidence) or evidence.schema_version != 1:
        raise PhysicalStorageDiscoveryError("physical storage discovery must be schema-v1 typed evidence")
    _safe_text(evidence.profile_id, "storage discovery profile id", 128)
    _safe_text(evidence.device_serial, "storage discovery device serial", 256)
    _safe_text(evidence.firmware_build, "storage discovery firmware build", 512)
    _safe_text(evidence.firmware_fingerprint, "storage discovery firmware fingerprint", 1024)
    for value, label in (
        (evidence.rootfs_handoff_assessment_sha256, "rootfs handoff assessment"),
        (evidence.rootfs_handoff_contract_sha256, "rootfs handoff contract"),
        (evidence.physical_candidate_gate_sha256, "physical candidate gate"),
        (evidence.rootfs_authority_sha256, "rootfs authority"),
        (evidence.rootfs_artifact_sha256, "rootfs artifact"),
        (evidence.rescue_diagnostics_sha256, "rescue diagnostics"),
        (evidence.rescue_functional_probe_sha256, "rescue functional probe"),
        (evidence.transcript_sha256, "transcript"),
        (evidence.rescue_probe_id, "rescue probe id"),
        (evidence.discovery_report_sha256, "discovery report"),
        (evidence.recovery_plan_sha256, "recovery plan"),
    ):
        _digest(value, label)
    for value, label in (
        (evidence.rootfs_artifact_size, "rootfs artifact size"),
        (evidence.discovery_report_size, "discovery report size"),
        (evidence.recovery_plan_size, "recovery plan size"),
    ):
        _positive_int(value, label)
    for value, label in (
        (evidence.block_device_count, "block device count"),
        (evidence.filesystem_observation_count, "filesystem observation count"),
        (evidence.encryption_observation_count, "encryption observation count"),
        (evidence.free_space_observation_count, "free-space observation count"),
    ):
        if _nonnegative_int(value, label) > _MAX_RECORDS:
            raise PhysicalStorageDiscoveryError(f"{label} exceeds safety limit")
    _safe_role(evidence.storage_bus, "storage bus")
    _safe_role(evidence.partition_hint, "partition hint")
    if not isinstance(evidence.expected_filesystems, tuple) or not evidence.expected_filesystems:
        raise PhysicalStorageDiscoveryError("expected filesystems are invalid")
    for value in evidence.expected_filesystems:
        _safe_fs(value, "expected filesystem")
    if not isinstance(evidence.expected_encryption_features, tuple):
        raise PhysicalStorageDiscoveryError("expected encryption features are invalid")
    for value in evidence.expected_encryption_features:
        _safe_feature(value, "expected encryption feature")
    if not isinstance(evidence.forbidden_partitions, tuple) or not evidence.forbidden_partitions:
        raise PhysicalStorageDiscoveryError("forbidden partitions are invalid")
    for value in evidence.forbidden_partitions:
        _safe_role(value, "forbidden partition")
    boolean_fields = (
        evidence.topology_bound_to_rescue_diagnostics,
        evidence.storage_bus_signal_observed,
        evidence.filesystem_identity_observed,
        evidence.expected_filesystem_observed,
        evidence.encryption_state_observed,
        evidence.expected_encryption_features_observed,
        evidence.free_space_observed,
        evidence.recovery_plan_bound,
        evidence.all_required_categories_recorded,
        evidence.discovery_ready_for_manual_review,
    )
    if any(not isinstance(value, bool) for value in boolean_fields):
        raise PhysicalStorageDiscoveryError("physical storage discovery observation flags must be boolean")
    expected_all = (
        evidence.topology_bound_to_rescue_diagnostics
        and evidence.filesystem_identity_observed
        and evidence.encryption_state_observed
        and evidence.free_space_observed
        and evidence.recovery_plan_bound
    )
    if evidence.all_required_categories_recorded is not expected_all:
        raise PhysicalStorageDiscoveryError("required physical storage category summary drifted")
    expected_review = (
        expected_all
        and evidence.storage_bus_signal_observed
        and evidence.expected_filesystem_observed
        and evidence.expected_encryption_features_observed
    )
    if evidence.discovery_ready_for_manual_review is not expected_review:
        raise PhysicalStorageDiscoveryError("physical storage discovery review-readiness summary drifted")
    if (
        evidence.target_selected is not False
        or evidence.storage_path_bound is not False
        or evidence.write_authorized is not False
        or evidence.handoff_ready is not False
        or evidence.storage_verified is not False
        or evidence.recovery_verified is not False
        or evidence.phone_storage_written is not False
        or evidence.manual_review_required is not True
        or evidence.hardware_verified is not False
        or evidence.beta_gate_credit is not False
    ):
        raise PhysicalStorageDiscoveryError("physical storage discovery contains an unsupported target/write/hardware claim")


def record_physical_storage_discovery(
    profile: DeviceProfile,
    assessment: RootfsHandoffAssessmentEvidence,
    diagnostics: PhysicalRescueDiagnosticsEvidence,
    functional_probe: PhysicalRescueFunctionalProbeEvidence,
    discovery_report_path: Path,
    recovery_plan_path: Path,
) -> PhysicalStorageDiscoveryEvidence:
    report, report_sha, report_size = load_physical_storage_discovery_report(discovery_report_path)
    recovery_sha, recovery_size = _read_recovery_plan(recovery_plan_path)
    return bind_physical_storage_discovery(
        profile,
        assessment,
        diagnostics,
        functional_probe,
        report,
        discovery_report_sha256=report_sha,
        discovery_report_size=report_size,
        recovery_plan_sha256=recovery_sha,
        recovery_plan_size=recovery_size,
    )


def _read_json(path: Path, label: str, max_bytes: int = 4 * 1024 * 1024) -> dict[str, Any]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalStorageDiscoveryError(f"{label} must be a regular non-symlink file")
    raw = source.read_bytes()
    if not raw or len(raw) > max_bytes:
        raise PhysicalStorageDiscoveryError(f"{label} size is outside the safety limit")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalStorageDiscoveryError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise PhysicalStorageDiscoveryError(f"{label} must be a JSON object")
    return value


def load_rootfs_handoff_assessment(path: Path) -> RootfsHandoffAssessmentEvidence:
    raw = _read_json(path, "rootfs handoff assessment")
    expected = {item.name for item in fields(RootfsHandoffAssessmentEvidence)}
    if set(raw) != expected:
        raise PhysicalStorageDiscoveryError("rootfs handoff assessment fields do not match schema-v1")
    for key in ("expected_filesystems", "encryption_features", "required_physical_evidence", "forbidden_partitions"):
        if not isinstance(raw.get(key), list):
            raise PhysicalStorageDiscoveryError(f"rootfs handoff assessment {key} must be a list")
        raw[key] = tuple(raw[key])
    try:
        value = RootfsHandoffAssessmentEvidence(**raw)
    except TypeError as exc:
        raise PhysicalStorageDiscoveryError("rootfs handoff assessment types are invalid") from exc
    return value


def load_physical_storage_discovery_evidence(path: Path) -> PhysicalStorageDiscoveryEvidence:
    raw = _read_json(path, "physical storage discovery evidence")
    expected = {item.name for item in fields(PhysicalStorageDiscoveryEvidence)}
    if set(raw) != expected:
        raise PhysicalStorageDiscoveryError("physical storage discovery evidence fields do not match schema-v1")
    for key in ("expected_filesystems", "expected_encryption_features", "forbidden_partitions"):
        if not isinstance(raw.get(key), list):
            raise PhysicalStorageDiscoveryError(f"physical storage discovery {key} must be a list")
        raw[key] = tuple(raw[key])
    try:
        value = PhysicalStorageDiscoveryEvidence(**raw)
    except TypeError as exc:
        raise PhysicalStorageDiscoveryError("physical storage discovery evidence types are invalid") from exc
    validate_physical_storage_discovery_evidence(value)
    return value


def write_physical_storage_discovery_evidence(evidence: PhysicalStorageDiscoveryEvidence, destination: Path) -> str:
    validate_physical_storage_discovery_evidence(evidence)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise PhysicalStorageDiscoveryError("refusing to overwrite physical storage discovery evidence")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise PhysicalStorageDiscoveryError("refusing stale physical storage discovery temporary path")
    try:
        temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()
