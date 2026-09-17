"""Manual review for one exact physical bring-up dossier.

This is an offline audit layer. It can accept an already verified dossier only as
input for a later, separately reviewed reversible rootfs strategy. It cannot
select a storage path, authorize writes, prove hardware, or grant Beta credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from .physical_bringup_dossier import (
    PhysicalBringupDossierEvidence,
    PhysicalBringupDossierError,
    validate_physical_bringup_dossier_evidence,
)
from .physical_bringup_dossier_verify import (
    PhysicalBringupDossierVerificationEvidence,
    validate_physical_bringup_dossier_verification_evidence,
)

_REVIEW_POLICY = "manual-physical-bringup-dossier-review-v1"
_ALLOWED_DECISIONS = frozenset({"accepted_for_strategy_review", "rejected"})
_MAX_RECORD_BYTES = 512 * 1024
_MAX_NOTES_BYTES = 2 * 1024 * 1024
_SAFE_REVIEWER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+-]{0,127}$")


class PhysicalBringupDossierReviewError(ValueError):
    pass


@dataclass(frozen=True)
class PhysicalBringupDossierReviewRecord:
    schema_version: int
    review_policy: str
    profile_id: str
    device_serial: str
    reviewer: str
    decision: str
    physical_identity_reviewed: bool
    firmware_stock_boot_reviewed: bool
    candidate_authority_chain_reviewed: bool
    rescue_evidence_chain_reviewed: bool
    storage_review_chain_reviewed: bool
    exact_file_set_reviewed: bool
    recovery_plan_reviewed: bool
    target_selected: bool
    storage_path_bound: bool
    write_authorized: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"


@dataclass(frozen=True)
class PhysicalBringupDossierReviewEvidence:
    schema_version: int
    review_policy: str
    profile_id: str
    device_serial: str
    firmware_build: str
    firmware_fingerprint: str
    physical_bringup_dossier_sha256: str
    dossier_verification_sha256: str
    review_record_sha256: str
    review_record_size: int
    review_notes_sha256: str
    review_notes_size: int
    reviewer: str
    decision: str
    physical_identity_reviewed: bool
    firmware_stock_boot_reviewed: bool
    candidate_authority_chain_reviewed: bool
    rescue_evidence_chain_reviewed: bool
    storage_review_chain_reviewed: bool
    exact_file_set_reviewed: bool
    recovery_plan_reviewed: bool
    review_checks_complete: bool
    dossier_review_completed: bool
    accepted_for_strategy_review: bool
    separate_strategy_review_required: bool
    target_selected: bool
    storage_path_bound: bool
    write_authorized: bool
    handoff_ready: bool
    storage_verified: bool
    recovery_verified: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _safe_text(value: object, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise PhysicalBringupDossierReviewError(f"{label} must be non-empty bounded text")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise PhysicalBringupDossierReviewError(f"{label} contains control data")
    return value


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise PhysicalBringupDossierReviewError(f"{label} must be a lowercase SHA-256")
    return value


def _positive(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PhysicalBringupDossierReviewError(f"{label} must be a positive integer")
    return value


def _read_exact(path: Path, label: str, maximum: int) -> tuple[bytes, str, int]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalBringupDossierReviewError(f"{label} must be a regular non-symlink file")
    before = source.stat()
    raw = source.read_bytes()
    after = source.stat()
    if before.st_size <= 0 or before.st_size > maximum or len(raw) != before.st_size:
        raise PhysicalBringupDossierReviewError(f"{label} size is outside the safety limit")
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise PhysicalBringupDossierReviewError(f"{label} changed while being read")
    return raw, sha256(raw).hexdigest(), len(raw)


def parse_physical_bringup_dossier_review_record(raw: object) -> PhysicalBringupDossierReviewRecord:
    expected = {item.name for item in fields(PhysicalBringupDossierReviewRecord)}
    if not isinstance(raw, dict) or set(raw) != expected:
        raise PhysicalBringupDossierReviewError("dossier review record fields do not match schema-v1")
    if raw["schema_version"] != 1 or raw["review_policy"] != _REVIEW_POLICY:
        raise PhysicalBringupDossierReviewError("unsupported dossier review record schema/policy")
    reviewer = raw["reviewer"]
    if not isinstance(reviewer, str) or not _SAFE_REVIEWER_RE.fullmatch(reviewer):
        raise PhysicalBringupDossierReviewError("dossier reviewer must be a safe bounded identifier")
    if raw["decision"] not in _ALLOWED_DECISIONS:
        raise PhysicalBringupDossierReviewError("dossier review decision is unsupported")
    checks = (
        "physical_identity_reviewed",
        "firmware_stock_boot_reviewed",
        "candidate_authority_chain_reviewed",
        "rescue_evidence_chain_reviewed",
        "storage_review_chain_reviewed",
        "exact_file_set_reviewed",
        "recovery_plan_reviewed",
    )
    for name in checks:
        if not isinstance(raw[name], bool):
            raise PhysicalBringupDossierReviewError(f"{name} must be boolean")
    for name in ("target_selected", "storage_path_bound", "write_authorized"):
        if raw[name] is not False:
            raise PhysicalBringupDossierReviewError(f"dossier review requires {name}=false")
    return PhysicalBringupDossierReviewRecord(**raw)


def load_physical_bringup_dossier_review_record(path: Path) -> tuple[PhysicalBringupDossierReviewRecord, str, int]:
    raw, digest, size = _read_exact(path, "dossier review record", _MAX_RECORD_BYTES)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalBringupDossierReviewError("dossier review record is not valid UTF-8 JSON") from exc
    record = parse_physical_bringup_dossier_review_record(value)
    if raw != record.canonical_json().encode("utf-8"):
        raise PhysicalBringupDossierReviewError("dossier review record is not canonical JSON")
    return record, digest, size


def read_physical_bringup_dossier_review_notes(path: Path) -> tuple[str, int]:
    raw, digest, size = _read_exact(path, "dossier review notes", _MAX_NOTES_BYTES)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PhysicalBringupDossierReviewError("dossier review notes must be UTF-8") from exc
    if not text.strip() or "\x00" in text:
        raise PhysicalBringupDossierReviewError("dossier review notes are empty or contain NUL data")
    return digest, size


def bind_physical_bringup_dossier_review(
    dossier: PhysicalBringupDossierEvidence,
    verification: PhysicalBringupDossierVerificationEvidence,
    review: PhysicalBringupDossierReviewRecord,
    *,
    review_record_sha256: str,
    review_record_size: int,
    review_notes_sha256: str,
    review_notes_size: int,
) -> PhysicalBringupDossierReviewEvidence:
    try:
        validate_physical_bringup_dossier_evidence(dossier)
        validate_physical_bringup_dossier_verification_evidence(verification)
    except PhysicalBringupDossierError as exc:
        raise PhysicalBringupDossierReviewError(str(exc)) from exc
    if verification.physical_bringup_dossier_sha256 != dossier.evidence_sha256():
        raise PhysicalBringupDossierReviewError("dossier verification is detached from dossier")
    if verification.profile_id != dossier.profile_id or verification.device_serial != dossier.device_serial:
        raise PhysicalBringupDossierReviewError("dossier verification identity drifted")
    if verification.rootfs_artifact_file_verified is not dossier.rootfs_artifact_file_verified:
        raise PhysicalBringupDossierReviewError("dossier rootfs file verification flag drifted")
    if review.profile_id != dossier.profile_id or review.device_serial != dossier.device_serial:
        raise PhysicalBringupDossierReviewError("dossier review identity does not match dossier")

    checks = (
        review.physical_identity_reviewed,
        review.firmware_stock_boot_reviewed,
        review.candidate_authority_chain_reviewed,
        review.rescue_evidence_chain_reviewed,
        review.storage_review_chain_reviewed,
        review.exact_file_set_reviewed,
        review.recovery_plan_reviewed,
    )
    checks_complete = all(checks)
    accepted = (
        review.decision == "accepted_for_strategy_review"
        and dossier.storage_review_accepted_for_strategy_design
        and dossier.exact_file_set_verified
        and verification.exact_file_set_verified
        and checks_complete
    )
    if review.decision == "accepted_for_strategy_review" and not accepted:
        raise PhysicalBringupDossierReviewError(
            "cannot accept dossier for strategy review until storage review, exact-file verification and every dossier review check are complete"
        )

    evidence = PhysicalBringupDossierReviewEvidence(
        schema_version=1,
        review_policy=_REVIEW_POLICY,
        profile_id=dossier.profile_id,
        device_serial=dossier.device_serial,
        firmware_build=dossier.firmware_build,
        firmware_fingerprint=dossier.firmware_fingerprint,
        physical_bringup_dossier_sha256=dossier.evidence_sha256(),
        dossier_verification_sha256=verification.evidence_sha256(),
        review_record_sha256=_sha(review_record_sha256, "dossier review record"),
        review_record_size=_positive(review_record_size, "dossier review record size"),
        review_notes_sha256=_sha(review_notes_sha256, "dossier review notes"),
        review_notes_size=_positive(review_notes_size, "dossier review notes size"),
        reviewer=review.reviewer,
        decision=review.decision,
        physical_identity_reviewed=review.physical_identity_reviewed,
        firmware_stock_boot_reviewed=review.firmware_stock_boot_reviewed,
        candidate_authority_chain_reviewed=review.candidate_authority_chain_reviewed,
        rescue_evidence_chain_reviewed=review.rescue_evidence_chain_reviewed,
        storage_review_chain_reviewed=review.storage_review_chain_reviewed,
        exact_file_set_reviewed=review.exact_file_set_reviewed,
        recovery_plan_reviewed=review.recovery_plan_reviewed,
        review_checks_complete=checks_complete,
        dossier_review_completed=True,
        accepted_for_strategy_review=accepted,
        separate_strategy_review_required=True,
        target_selected=False,
        storage_path_bound=False,
        write_authorized=False,
        handoff_ready=False,
        storage_verified=False,
        recovery_verified=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    validate_physical_bringup_dossier_review_evidence(evidence)
    return evidence


def validate_physical_bringup_dossier_review_evidence(evidence: PhysicalBringupDossierReviewEvidence) -> None:
    if not isinstance(evidence, PhysicalBringupDossierReviewEvidence) or evidence.schema_version != 1:
        raise PhysicalBringupDossierReviewError("dossier review must be schema-v1 typed evidence")
    if evidence.review_policy != _REVIEW_POLICY:
        raise PhysicalBringupDossierReviewError("dossier review policy is unsupported")
    _safe_text(evidence.profile_id, "dossier review profile id", 128)
    _safe_text(evidence.device_serial, "dossier review serial", 256)
    _safe_text(evidence.firmware_build, "dossier review firmware build", 512)
    _safe_text(evidence.firmware_fingerprint, "dossier review firmware fingerprint", 1024)
    if not _SAFE_REVIEWER_RE.fullmatch(evidence.reviewer):
        raise PhysicalBringupDossierReviewError("dossier review reviewer identifier is invalid")
    if evidence.decision not in _ALLOWED_DECISIONS:
        raise PhysicalBringupDossierReviewError("dossier review decision is unsupported")
    for value, label in (
        (evidence.physical_bringup_dossier_sha256, "physical bring-up dossier"),
        (evidence.dossier_verification_sha256, "dossier verification"),
        (evidence.review_record_sha256, "dossier review record"),
        (evidence.review_notes_sha256, "dossier review notes"),
    ):
        _sha(value, label)
    _positive(evidence.review_record_size, "dossier review record size")
    _positive(evidence.review_notes_size, "dossier review notes size")
    checks = (
        evidence.physical_identity_reviewed,
        evidence.firmware_stock_boot_reviewed,
        evidence.candidate_authority_chain_reviewed,
        evidence.rescue_evidence_chain_reviewed,
        evidence.storage_review_chain_reviewed,
        evidence.exact_file_set_reviewed,
        evidence.recovery_plan_reviewed,
    )
    if any(not isinstance(value, bool) for value in checks):
        raise PhysicalBringupDossierReviewError("dossier review checks must be boolean")
    if evidence.review_checks_complete is not all(checks):
        raise PhysicalBringupDossierReviewError("dossier review completeness flag drifted")
    if evidence.dossier_review_completed is not True or evidence.separate_strategy_review_required is not True:
        raise PhysicalBringupDossierReviewError("dossier review is missing required audit flags")
    if evidence.accepted_for_strategy_review is not (evidence.decision == "accepted_for_strategy_review" and evidence.review_checks_complete):
        raise PhysicalBringupDossierReviewError("dossier strategy-review acceptance flag drifted")
    if any(value is not False for value in (
        evidence.target_selected,
        evidence.storage_path_bound,
        evidence.write_authorized,
        evidence.handoff_ready,
        evidence.storage_verified,
        evidence.recovery_verified,
        evidence.hardware_verified,
        evidence.beta_gate_credit,
    )):
        raise PhysicalBringupDossierReviewError("dossier review contains an unsupported target/write/hardware/Beta claim")


def load_physical_bringup_dossier_verification_for_review(path: Path) -> PhysicalBringupDossierVerificationEvidence:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalBringupDossierReviewError("dossier verification must be a regular non-symlink file")
    raw = source.read_bytes()
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalBringupDossierReviewError("dossier verification is not valid UTF-8 JSON") from exc
    expected = {item.name for item in fields(PhysicalBringupDossierVerificationEvidence)}
    if not isinstance(value, dict) or set(value) != expected:
        raise PhysicalBringupDossierReviewError("dossier verification fields do not match schema-v1")
    try:
        evidence = PhysicalBringupDossierVerificationEvidence(**value)
        validate_physical_bringup_dossier_verification_evidence(evidence)
    except (TypeError, PhysicalBringupDossierError) as exc:
        raise PhysicalBringupDossierReviewError("dossier verification evidence is invalid") from exc
    if raw != evidence.canonical_json().encode("utf-8"):
        raise PhysicalBringupDossierReviewError("dossier verification is not canonical JSON")
    return evidence


def load_physical_bringup_dossier_review_evidence(path: Path) -> PhysicalBringupDossierReviewEvidence:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalBringupDossierReviewError("dossier review evidence must be a regular non-symlink file")
    raw = source.read_bytes()
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalBringupDossierReviewError("dossier review evidence is not valid UTF-8 JSON") from exc
    expected = {item.name for item in fields(PhysicalBringupDossierReviewEvidence)}
    if not isinstance(value, dict) or set(value) != expected:
        raise PhysicalBringupDossierReviewError("dossier review evidence fields do not match schema-v1")
    try:
        evidence = PhysicalBringupDossierReviewEvidence(**value)
        validate_physical_bringup_dossier_review_evidence(evidence)
    except (TypeError, PhysicalBringupDossierReviewError) as exc:
        raise PhysicalBringupDossierReviewError("dossier review evidence is invalid") from exc
    if raw != evidence.canonical_json().encode("utf-8"):
        raise PhysicalBringupDossierReviewError("dossier review evidence is not canonical JSON")
    return evidence


def write_physical_bringup_dossier_review_evidence(evidence: PhysicalBringupDossierReviewEvidence, destination: Path) -> str:
    validate_physical_bringup_dossier_review_evidence(evidence)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise PhysicalBringupDossierReviewError("refusing to overwrite dossier review evidence")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise PhysicalBringupDossierReviewError("refusing stale dossier review temporary path")
    temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
    temporary.replace(destination)
    return evidence.evidence_sha256()
