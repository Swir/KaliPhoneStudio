"""Manual-review evidence for physical storage discovery.

This module records a human review of one exact PhysicalStorageDiscoveryEvidence
record. It deliberately cannot select a block-device path, choose a staging
location, authorize writes, or grant hardware/Beta credit. A successful review
only means the exact discovery evidence is accepted as input for a later,
separately reviewed strategy-design milestone.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from .physical_storage_discovery import (
    PhysicalStorageDiscoveryError,
    PhysicalStorageDiscoveryEvidence,
    load_physical_storage_discovery_evidence,
    validate_physical_storage_discovery_evidence,
)

_REVIEW_POLICY = "manual-physical-storage-review-v1"
_ALLOWED_DECISIONS = frozenset({"accepted_for_strategy_design", "rejected"})
_MAX_REVIEW_RECORD_BYTES = 512 * 1024
_MAX_REVIEW_NOTES_BYTES = 2 * 1024 * 1024
_SAFE_REVIEWER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+-]{0,127}$")


class PhysicalStorageReviewError(ValueError):
    pass


@dataclass(frozen=True)
class PhysicalStorageReviewRecord:
    schema_version: int
    profile_id: str
    device_serial: str
    review_policy: str
    reviewer: str
    decision: str
    physical_context_reviewed: bool
    topology_reviewed: bool
    filesystem_reviewed: bool
    encryption_reviewed: bool
    free_space_reviewed: bool
    recovery_plan_reviewed: bool
    evidence_chain_reviewed: bool
    target_selected: bool
    storage_path_bound: bool
    write_authorized: bool

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
    review_record_sha256: str
    review_record_size: int
    review_notes_sha256: str
    review_notes_size: int
    reviewer: str
    decision: str
    source_discovery_ready_for_manual_review: bool
    physical_context_reviewed: bool
    topology_reviewed: bool
    filesystem_reviewed: bool
    encryption_reviewed: bool
    free_space_reviewed: bool
    recovery_plan_reviewed: bool
    evidence_chain_reviewed: bool
    review_checks_complete: bool
    review_recorded: bool
    accepted_for_strategy_design: bool
    target_selected: bool
    storage_path_bound: bool
    write_authorized: bool
    handoff_ready: bool
    storage_verified: bool
    recovery_verified: bool
    phone_storage_written: bool
    further_strategy_review_required: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _safe_text(value: object, label: str, max_len: int) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len:
        raise PhysicalStorageReviewError(f"{label} must be non-empty bounded text")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise PhysicalStorageReviewError(f"{label} contains control data")
    return value


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise PhysicalStorageReviewError(f"{label} must be a lowercase SHA-256")
    return value


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PhysicalStorageReviewError(f"{label} must be a positive integer")
    return value


def _exact_keys(raw: object, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != expected:
        raise PhysicalStorageReviewError(f"{label} fields do not match schema-v1")
    return raw


def parse_physical_storage_review_record(raw: object) -> PhysicalStorageReviewRecord:
    item = _exact_keys(
        raw,
        {
            "schema_version",
            "profile_id",
            "device_serial",
            "review_policy",
            "reviewer",
            "decision",
            "physical_context_reviewed",
            "topology_reviewed",
            "filesystem_reviewed",
            "encryption_reviewed",
            "free_space_reviewed",
            "recovery_plan_reviewed",
            "evidence_chain_reviewed",
            "target_selected",
            "storage_path_bound",
            "write_authorized",
        },
        "physical storage review record",
    )
    if item["schema_version"] != 1:
        raise PhysicalStorageReviewError("unsupported physical storage review record schema")
    if item["review_policy"] != _REVIEW_POLICY:
        raise PhysicalStorageReviewError("unsupported physical storage review policy")
    reviewer = item["reviewer"]
    if not isinstance(reviewer, str) or not _SAFE_REVIEWER_RE.fullmatch(reviewer):
        raise PhysicalStorageReviewError("reviewer must be a safe bounded identifier")
    decision = item["decision"]
    if decision not in _ALLOWED_DECISIONS:
        raise PhysicalStorageReviewError("physical storage review decision is unsupported")
    review_flags = (
        "physical_context_reviewed",
        "topology_reviewed",
        "filesystem_reviewed",
        "encryption_reviewed",
        "free_space_reviewed",
        "recovery_plan_reviewed",
        "evidence_chain_reviewed",
    )
    for name in review_flags:
        if not isinstance(item[name], bool):
            raise PhysicalStorageReviewError(f"{name} must be boolean")
    for name in ("target_selected", "storage_path_bound", "write_authorized"):
        if item[name] is not False:
            raise PhysicalStorageReviewError(f"manual storage review requires {name}=false")
    return PhysicalStorageReviewRecord(
        schema_version=1,
        profile_id=_safe_text(item["profile_id"], "review profile id", 128),
        device_serial=_safe_text(item["device_serial"], "review device serial", 256),
        review_policy=_REVIEW_POLICY,
        reviewer=reviewer,
        decision=decision,
        physical_context_reviewed=item["physical_context_reviewed"],
        topology_reviewed=item["topology_reviewed"],
        filesystem_reviewed=item["filesystem_reviewed"],
        encryption_reviewed=item["encryption_reviewed"],
        free_space_reviewed=item["free_space_reviewed"],
        recovery_plan_reviewed=item["recovery_plan_reviewed"],
        evidence_chain_reviewed=item["evidence_chain_reviewed"],
        target_selected=False,
        storage_path_bound=False,
        write_authorized=False,
    )


def _read_exact_file(path: Path, label: str, max_bytes: int) -> tuple[bytes, str, int]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalStorageReviewError(f"{label} must be a regular non-symlink file")
    before = source.stat()
    raw = source.read_bytes()
    after = source.stat()
    if before.st_size <= 0 or before.st_size > max_bytes or len(raw) != before.st_size:
        raise PhysicalStorageReviewError(f"{label} size is outside the safety limit")
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise PhysicalStorageReviewError(f"{label} changed while being read")
    return raw, sha256(raw).hexdigest(), len(raw)


def load_physical_storage_review_record(path: Path) -> tuple[PhysicalStorageReviewRecord, str, int]:
    raw, digest, size = _read_exact_file(path, "physical storage review record", _MAX_REVIEW_RECORD_BYTES)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalStorageReviewError("physical storage review record is not valid UTF-8 JSON") from exc
    return parse_physical_storage_review_record(value), digest, size


def _read_review_notes(path: Path) -> tuple[str, int]:
    raw, digest, size = _read_exact_file(path, "physical storage review notes", _MAX_REVIEW_NOTES_BYTES)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PhysicalStorageReviewError("physical storage review notes must be UTF-8") from exc
    if not text.strip() or "\x00" in text:
        raise PhysicalStorageReviewError("physical storage review notes are empty or contain NUL data")
    return digest, size


def bind_physical_storage_review(
    discovery: PhysicalStorageDiscoveryEvidence,
    review: PhysicalStorageReviewRecord,
    *,
    review_record_sha256: str,
    review_record_size: int,
    review_notes_sha256: str,
    review_notes_size: int,
) -> PhysicalStorageReviewEvidence:
    try:
        validate_physical_storage_discovery_evidence(discovery)
    except PhysicalStorageDiscoveryError as exc:
        raise PhysicalStorageReviewError(str(exc)) from exc
    if review.profile_id != discovery.profile_id:
        raise PhysicalStorageReviewError("physical storage review profile mismatch")
    if review.device_serial != discovery.device_serial:
        raise PhysicalStorageReviewError("physical storage review serial mismatch")
    record_sha = _digest(review_record_sha256, "review record SHA-256")
    record_size = _positive_int(review_record_size, "review record size")
    notes_sha = _digest(review_notes_sha256, "review notes SHA-256")
    notes_size = _positive_int(review_notes_size, "review notes size")

    checks = (
        review.physical_context_reviewed,
        review.topology_reviewed,
        review.filesystem_reviewed,
        review.encryption_reviewed,
        review.free_space_reviewed,
        review.recovery_plan_reviewed,
        review.evidence_chain_reviewed,
    )
    checks_complete = all(checks)
    accepted = (
        review.decision == "accepted_for_strategy_design"
        and discovery.discovery_ready_for_manual_review
        and checks_complete
    )
    if review.decision == "accepted_for_strategy_design" and not accepted:
        raise PhysicalStorageReviewError(
            "cannot accept discovery for strategy design until source evidence is review-ready and every review check is complete"
        )

    evidence = PhysicalStorageReviewEvidence(
        schema_version=1,
        profile_id=discovery.profile_id,
        device_serial=discovery.device_serial,
        firmware_build=discovery.firmware_build,
        firmware_fingerprint=discovery.firmware_fingerprint,
        physical_storage_discovery_sha256=discovery.evidence_sha256(),
        rootfs_handoff_assessment_sha256=discovery.rootfs_handoff_assessment_sha256,
        rootfs_handoff_contract_sha256=discovery.rootfs_handoff_contract_sha256,
        physical_candidate_gate_sha256=discovery.physical_candidate_gate_sha256,
        rootfs_authority_sha256=discovery.rootfs_authority_sha256,
        rootfs_artifact_sha256=discovery.rootfs_artifact_sha256,
        rootfs_artifact_size=discovery.rootfs_artifact_size,
        rescue_diagnostics_sha256=discovery.rescue_diagnostics_sha256,
        rescue_functional_probe_sha256=discovery.rescue_functional_probe_sha256,
        transcript_sha256=discovery.transcript_sha256,
        rescue_probe_id=discovery.rescue_probe_id,
        discovery_report_sha256=discovery.discovery_report_sha256,
        discovery_report_size=discovery.discovery_report_size,
        recovery_plan_sha256=discovery.recovery_plan_sha256,
        recovery_plan_size=discovery.recovery_plan_size,
        review_record_sha256=record_sha,
        review_record_size=record_size,
        review_notes_sha256=notes_sha,
        review_notes_size=notes_size,
        reviewer=review.reviewer,
        decision=review.decision,
        source_discovery_ready_for_manual_review=discovery.discovery_ready_for_manual_review,
        physical_context_reviewed=review.physical_context_reviewed,
        topology_reviewed=review.topology_reviewed,
        filesystem_reviewed=review.filesystem_reviewed,
        encryption_reviewed=review.encryption_reviewed,
        free_space_reviewed=review.free_space_reviewed,
        recovery_plan_reviewed=review.recovery_plan_reviewed,
        evidence_chain_reviewed=review.evidence_chain_reviewed,
        review_checks_complete=checks_complete,
        review_recorded=True,
        accepted_for_strategy_design=accepted,
        target_selected=False,
        storage_path_bound=False,
        write_authorized=False,
        handoff_ready=False,
        storage_verified=False,
        recovery_verified=False,
        phone_storage_written=False,
        further_strategy_review_required=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    validate_physical_storage_review_evidence(evidence)
    return evidence


def validate_physical_storage_review_evidence(evidence: PhysicalStorageReviewEvidence) -> None:
    if not isinstance(evidence, PhysicalStorageReviewEvidence) or evidence.schema_version != 1:
        raise PhysicalStorageReviewError("physical storage review must be schema-v1 typed evidence")
    _safe_text(evidence.profile_id, "storage review profile id", 128)
    _safe_text(evidence.device_serial, "storage review serial", 256)
    _safe_text(evidence.firmware_build, "storage review firmware build", 512)
    _safe_text(evidence.firmware_fingerprint, "storage review firmware fingerprint", 1024)
    if not _SAFE_REVIEWER_RE.fullmatch(evidence.reviewer):
        raise PhysicalStorageReviewError("storage review reviewer identifier is invalid")
    if evidence.decision not in _ALLOWED_DECISIONS:
        raise PhysicalStorageReviewError("storage review decision is unsupported")
    for value, label in (
        (evidence.physical_storage_discovery_sha256, "physical storage discovery"),
        (evidence.rootfs_handoff_assessment_sha256, "rootfs handoff assessment"),
        (evidence.rootfs_handoff_contract_sha256, "rootfs handoff contract"),
        (evidence.physical_candidate_gate_sha256, "physical candidate gate"),
        (evidence.rootfs_authority_sha256, "rootfs authority"),
        (evidence.rootfs_artifact_sha256, "rootfs artifact"),
        (evidence.rescue_diagnostics_sha256, "rescue diagnostics"),
        (evidence.rescue_functional_probe_sha256, "rescue functional probe"),
        (evidence.transcript_sha256, "rescue transcript"),
        (evidence.rescue_probe_id, "rescue probe id"),
        (evidence.discovery_report_sha256, "discovery report"),
        (evidence.recovery_plan_sha256, "recovery plan"),
        (evidence.review_record_sha256, "review record"),
        (evidence.review_notes_sha256, "review notes"),
    ):
        _digest(value, label)
    for value, label in (
        (evidence.rootfs_artifact_size, "rootfs artifact size"),
        (evidence.discovery_report_size, "discovery report size"),
        (evidence.recovery_plan_size, "recovery plan size"),
        (evidence.review_record_size, "review record size"),
        (evidence.review_notes_size, "review notes size"),
    ):
        _positive_int(value, label)
    boolean_fields = (
        evidence.source_discovery_ready_for_manual_review,
        evidence.physical_context_reviewed,
        evidence.topology_reviewed,
        evidence.filesystem_reviewed,
        evidence.encryption_reviewed,
        evidence.free_space_reviewed,
        evidence.recovery_plan_reviewed,
        evidence.evidence_chain_reviewed,
        evidence.review_checks_complete,
        evidence.review_recorded,
        evidence.accepted_for_strategy_design,
    )
    if any(not isinstance(value, bool) for value in boolean_fields):
        raise PhysicalStorageReviewError("physical storage review state fields must be boolean")
    expected_checks = all(
        (
            evidence.physical_context_reviewed,
            evidence.topology_reviewed,
            evidence.filesystem_reviewed,
            evidence.encryption_reviewed,
            evidence.free_space_reviewed,
            evidence.recovery_plan_reviewed,
            evidence.evidence_chain_reviewed,
        )
    )
    if evidence.review_checks_complete is not expected_checks:
        raise PhysicalStorageReviewError("physical storage review check summary drifted")
    expected_acceptance = (
        evidence.decision == "accepted_for_strategy_design"
        and evidence.source_discovery_ready_for_manual_review
        and expected_checks
    )
    if evidence.accepted_for_strategy_design is not expected_acceptance:
        raise PhysicalStorageReviewError("physical storage review acceptance summary drifted")
    if evidence.review_recorded is not True or evidence.further_strategy_review_required is not True:
        raise PhysicalStorageReviewError("physical storage review lifecycle state is invalid")
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
    review_notes_path: Path,
) -> PhysicalStorageReviewEvidence:
    review, record_sha, record_size = load_physical_storage_review_record(review_record_path)
    notes_sha, notes_size = _read_review_notes(review_notes_path)
    return bind_physical_storage_review(
        discovery,
        review,
        review_record_sha256=record_sha,
        review_record_size=record_size,
        review_notes_sha256=notes_sha,
        review_notes_size=notes_size,
    )


def _read_json(path: Path, label: str, max_bytes: int = 4 * 1024 * 1024) -> dict[str, Any]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalStorageReviewError(f"{label} must be a regular non-symlink file")
    before = source.stat()
    raw = source.read_bytes()
    after = source.stat()
    if not raw or len(raw) > max_bytes:
        raise PhysicalStorageReviewError(f"{label} size is outside the safety limit")
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise PhysicalStorageReviewError(f"{label} changed while being read")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalStorageReviewError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise PhysicalStorageReviewError(f"{label} must be a JSON object")
    return value


def load_physical_storage_review_evidence(path: Path) -> PhysicalStorageReviewEvidence:
    raw = _read_json(path, "physical storage review evidence")
    expected = {item.name for item in fields(PhysicalStorageReviewEvidence)}
    if set(raw) != expected:
        raise PhysicalStorageReviewError("physical storage review evidence fields do not match schema-v1")
    try:
        evidence = PhysicalStorageReviewEvidence(**raw)
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
