"""Fail-closed human review gate for physical storage discovery evidence.

This module deliberately stops before target selection.  It binds one exact
operator review record to one exact ``PhysicalStorageDiscoveryEvidence`` object
and can only permit *offline strategy design*.  It never creates a block-device
path, mount target, staging target, write authorization, hardware claim or Beta
credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from .physical_storage_discovery import (
    PhysicalStorageDiscoveryEvidence,
    PhysicalStorageDiscoveryError,
    load_physical_storage_discovery_evidence,
    validate_physical_storage_discovery_evidence,
)

_REVIEW_POLICY = "human-storage-discovery-review-v1"
_REVIEW_SCOPE = "discovery-evidence-only-no-target-v1"
_ATTESTATION = (
    "I reviewed the exact physical storage discovery evidence and recovery plan; "
    "this decision does not select a storage target or authorize a write."
)
_ALLOWED_DECISIONS = frozenset({"approve_for_strategy_design", "reject"})
_MAX_RECORD_BYTES = 2 * 1024 * 1024
_SAFE_REVIEWER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+-]{0,127}$")


class PhysicalStorageReviewError(ValueError):
    pass


@dataclass(frozen=True)
class PhysicalStorageReviewRecord:
    schema_version: int
    profile_id: str
    device_serial: str
    review_policy: str
    review_scope: str
    reviewer_id: str
    decision: str
    physical_storage_discovery_sha256: str
    discovery_report_sha256: str
    recovery_plan_sha256: str
    target_selected: bool
    storage_path_bound: bool
    write_authorized: bool
    phone_storage_written: bool
    attestation: str

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def record_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PhysicalStorageReviewEvidence:
    schema_version: int
    profile_id: str
    device_serial: str
    firmware_build: str
    firmware_fingerprint: str
    physical_storage_discovery_sha256: str
    discovery_report_sha256: str
    recovery_plan_sha256: str
    rootfs_handoff_assessment_sha256: str
    physical_candidate_gate_sha256: str
    rootfs_authority_sha256: str
    rootfs_artifact_sha256: str
    rootfs_artifact_size: int
    transcript_sha256: str
    rescue_probe_id: str
    review_record_sha256: str
    review_record_size: int
    reviewer_id: str
    decision: str
    discovery_ready_for_manual_review: bool
    manual_review_completed: bool
    strategy_design_allowed: bool
    target_selected: bool
    storage_path_bound: bool
    write_authorized: bool
    handoff_ready: bool
    storage_verified: bool
    recovery_verified: bool
    phone_storage_written: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise PhysicalStorageReviewError(f"{label} must be a lowercase SHA-256")
    return value


def _safe_text(value: object, label: str, max_len: int) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len:
        raise PhysicalStorageReviewError(f"{label} must be non-empty bounded text")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise PhysicalStorageReviewError(f"{label} contains control data")
    return value


def _safe_reviewer(value: object) -> str:
    if not isinstance(value, str) or not _SAFE_REVIEWER_RE.fullmatch(value):
        raise PhysicalStorageReviewError("reviewer_id must be a safe bounded identifier")
    return value


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PhysicalStorageReviewError(f"{label} must be a positive integer")
    return value


def parse_physical_storage_review_record(raw: object) -> PhysicalStorageReviewRecord:
    expected = {item.name for item in fields(PhysicalStorageReviewRecord)}
    if not isinstance(raw, dict) or set(raw) != expected:
        raise PhysicalStorageReviewError("physical storage review record fields do not match schema-v1")
    if raw["schema_version"] != 1:
        raise PhysicalStorageReviewError("unsupported physical storage review record schema")
    if raw["review_policy"] != _REVIEW_POLICY or raw["review_scope"] != _REVIEW_SCOPE:
        raise PhysicalStorageReviewError("physical storage review policy/scope is unsupported")
    if raw["decision"] not in _ALLOWED_DECISIONS:
        raise PhysicalStorageReviewError("physical storage review decision is unsupported")
    for flag in ("target_selected", "storage_path_bound", "write_authorized", "phone_storage_written"):
        if raw[flag] is not False:
            raise PhysicalStorageReviewError(f"physical storage review requires {flag}=false")
    if raw["attestation"] != _ATTESTATION:
        raise PhysicalStorageReviewError("physical storage review attestation does not match the required text")
    return PhysicalStorageReviewRecord(
        schema_version=1,
        profile_id=_safe_text(raw["profile_id"], "review profile id", 128),
        device_serial=_safe_text(raw["device_serial"], "review device serial", 256),
        review_policy=_REVIEW_POLICY,
        review_scope=_REVIEW_SCOPE,
        reviewer_id=_safe_reviewer(raw["reviewer_id"]),
        decision=raw["decision"],
        physical_storage_discovery_sha256=_digest(
            raw["physical_storage_discovery_sha256"], "physical storage discovery"
        ),
        discovery_report_sha256=_digest(raw["discovery_report_sha256"], "discovery report"),
        recovery_plan_sha256=_digest(raw["recovery_plan_sha256"], "recovery plan"),
        target_selected=False,
        storage_path_bound=False,
        write_authorized=False,
        phone_storage_written=False,
        attestation=_ATTESTATION,
    )


def load_physical_storage_review_record(path: Path) -> tuple[PhysicalStorageReviewRecord, str, int]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalStorageReviewError("physical storage review record must be a regular non-symlink file")
    before = source.stat()
    raw = source.read_bytes()
    after = source.stat()
    if before.st_size <= 0 or before.st_size > _MAX_RECORD_BYTES or len(raw) != before.st_size:
        raise PhysicalStorageReviewError("physical storage review record size is outside the safety limit")
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise PhysicalStorageReviewError("physical storage review record changed while being read")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalStorageReviewError("physical storage review record is not valid UTF-8 JSON") from exc
    record = parse_physical_storage_review_record(value)
    return record, sha256(raw).hexdigest(), len(raw)


def bind_physical_storage_review(
    discovery: PhysicalStorageDiscoveryEvidence,
    record: PhysicalStorageReviewRecord,
    *,
    review_record_sha256: str,
    review_record_size: int,
) -> PhysicalStorageReviewEvidence:
    """Bind an explicit human review decision without selecting any storage target."""
    try:
        validate_physical_storage_discovery_evidence(discovery)
    except PhysicalStorageDiscoveryError as exc:
        raise PhysicalStorageReviewError(str(exc)) from exc
    if not isinstance(record, PhysicalStorageReviewRecord) or record.schema_version != 1:
        raise PhysicalStorageReviewError("physical storage review record must be schema-v1 typed evidence")
    parse_physical_storage_review_record(asdict(record))
    if record.profile_id != discovery.profile_id:
        raise PhysicalStorageReviewError("physical storage review profile mismatch")
    if record.device_serial != discovery.device_serial:
        raise PhysicalStorageReviewError("physical storage review serial mismatch")
    if record.physical_storage_discovery_sha256 != discovery.evidence_sha256():
        raise PhysicalStorageReviewError("physical storage review is detached from supplied discovery evidence")
    if record.discovery_report_sha256 != discovery.discovery_report_sha256:
        raise PhysicalStorageReviewError("physical storage review discovery-report digest mismatch")
    if record.recovery_plan_sha256 != discovery.recovery_plan_sha256:
        raise PhysicalStorageReviewError("physical storage review recovery-plan digest mismatch")
    if record.decision == "approve_for_strategy_design" and not discovery.discovery_ready_for_manual_review:
        raise PhysicalStorageReviewError("cannot approve strategy design from discovery evidence that is not review-ready")
    if discovery.phone_storage_written or discovery.target_selected or discovery.storage_path_bound or discovery.write_authorized:
        raise PhysicalStorageReviewError("review input must remain discovery-only and no-write")

    evidence = PhysicalStorageReviewEvidence(
        schema_version=1,
        profile_id=discovery.profile_id,
        device_serial=discovery.device_serial,
        firmware_build=discovery.firmware_build,
        firmware_fingerprint=discovery.firmware_fingerprint,
        physical_storage_discovery_sha256=discovery.evidence_sha256(),
        discovery_report_sha256=discovery.discovery_report_sha256,
        recovery_plan_sha256=discovery.recovery_plan_sha256,
        rootfs_handoff_assessment_sha256=discovery.rootfs_handoff_assessment_sha256,
        physical_candidate_gate_sha256=discovery.physical_candidate_gate_sha256,
        rootfs_authority_sha256=discovery.rootfs_authority_sha256,
        rootfs_artifact_sha256=discovery.rootfs_artifact_sha256,
        rootfs_artifact_size=discovery.rootfs_artifact_size,
        transcript_sha256=discovery.transcript_sha256,
        rescue_probe_id=discovery.rescue_probe_id,
        review_record_sha256=_digest(review_record_sha256, "review record"),
        review_record_size=_positive_int(review_record_size, "review record size"),
        reviewer_id=record.reviewer_id,
        decision=record.decision,
        discovery_ready_for_manual_review=discovery.discovery_ready_for_manual_review,
        manual_review_completed=True,
        strategy_design_allowed=record.decision == "approve_for_strategy_design",
        target_selected=False,
        storage_path_bound=False,
        write_authorized=False,
        handoff_ready=False,
        storage_verified=False,
        recovery_verified=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    validate_physical_storage_review_evidence(evidence)
    return evidence


def validate_physical_storage_review_evidence(evidence: PhysicalStorageReviewEvidence) -> None:
    if not isinstance(evidence, PhysicalStorageReviewEvidence) or evidence.schema_version != 1:
        raise PhysicalStorageReviewError("physical storage review must be schema-v1 typed evidence")
    _safe_text(evidence.profile_id, "review evidence profile id", 128)
    _safe_text(evidence.device_serial, "review evidence device serial", 256)
    _safe_text(evidence.firmware_build, "review evidence firmware build", 512)
    _safe_text(evidence.firmware_fingerprint, "review evidence firmware fingerprint", 1024)
    _safe_reviewer(evidence.reviewer_id)
    if evidence.decision not in _ALLOWED_DECISIONS:
        raise PhysicalStorageReviewError("physical storage review evidence decision is unsupported")
    for value, label in (
        (evidence.physical_storage_discovery_sha256, "physical storage discovery"),
        (evidence.discovery_report_sha256, "discovery report"),
        (evidence.recovery_plan_sha256, "recovery plan"),
        (evidence.rootfs_handoff_assessment_sha256, "rootfs handoff assessment"),
        (evidence.physical_candidate_gate_sha256, "physical candidate gate"),
        (evidence.rootfs_authority_sha256, "rootfs authority"),
        (evidence.rootfs_artifact_sha256, "rootfs artifact"),
        (evidence.transcript_sha256, "transcript"),
        (evidence.rescue_probe_id, "rescue probe id"),
        (evidence.review_record_sha256, "review record"),
    ):
        _digest(value, label)
    _positive_int(evidence.rootfs_artifact_size, "rootfs artifact size")
    _positive_int(evidence.review_record_size, "review record size")
    if not isinstance(evidence.discovery_ready_for_manual_review, bool):
        raise PhysicalStorageReviewError("discovery review-readiness flag must be boolean")
    if evidence.manual_review_completed is not True:
        raise PhysicalStorageReviewError("physical storage review must record manual_review_completed=true")
    expected_strategy_design = evidence.decision == "approve_for_strategy_design"
    if evidence.strategy_design_allowed is not expected_strategy_design:
        raise PhysicalStorageReviewError("strategy-design summary drifted from review decision")
    if evidence.strategy_design_allowed and not evidence.discovery_ready_for_manual_review:
        raise PhysicalStorageReviewError("strategy design cannot be allowed from non-review-ready discovery")
    if (
        evidence.target_selected is not False
        or evidence.storage_path_bound is not False
        or evidence.write_authorized is not False
        or evidence.handoff_ready is not False
        or evidence.storage_verified is not False
        or evidence.recovery_verified is not False
        or evidence.phone_storage_written is not False
        or evidence.hardware_verified is not False
        or evidence.beta_gate_credit is not False
    ):
        raise PhysicalStorageReviewError("physical storage review contains an unsupported target/write/hardware claim")


def record_physical_storage_review(
    discovery: PhysicalStorageDiscoveryEvidence,
    review_record_path: Path,
) -> PhysicalStorageReviewEvidence:
    record, digest, size = load_physical_storage_review_record(review_record_path)
    return bind_physical_storage_review(
        discovery,
        record,
        review_record_sha256=digest,
        review_record_size=size,
    )


def load_physical_storage_review_evidence(path: Path) -> PhysicalStorageReviewEvidence:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalStorageReviewError("physical storage review evidence must be a regular non-symlink file")
    raw = source.read_bytes()
    if not raw or len(raw) > 4 * 1024 * 1024:
        raise PhysicalStorageReviewError("physical storage review evidence size is outside the safety limit")
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalStorageReviewError("physical storage review evidence is not valid UTF-8 JSON") from exc
    expected = {item.name for item in fields(PhysicalStorageReviewEvidence)}
    if not isinstance(value, dict) or set(value) != expected:
        raise PhysicalStorageReviewError("physical storage review evidence fields do not match schema-v1")
    try:
        evidence = PhysicalStorageReviewEvidence(**value)
    except TypeError as exc:
        raise PhysicalStorageReviewError("physical storage review evidence types are invalid") from exc
    validate_physical_storage_review_evidence(evidence)
    return evidence


def write_physical_storage_review_evidence(evidence: PhysicalStorageReviewEvidence, destination: Path) -> str:
    validate_physical_storage_review_evidence(evidence)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise PhysicalStorageReviewError("refusing to overwrite physical storage review evidence")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise PhysicalStorageReviewError("refusing stale physical storage review temporary path")
    try:
        temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()


def load_discovery_for_review(path: Path) -> PhysicalStorageDiscoveryEvidence:
    try:
        return load_physical_storage_discovery_evidence(path)
    except PhysicalStorageDiscoveryError as exc:
        raise PhysicalStorageReviewError(str(exc)) from exc
