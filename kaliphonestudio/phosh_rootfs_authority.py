"""Explicit review boundary for real A/B Phosh ARM64 rootfs candidates.

The real-build workflow can produce a byte-identical Phosh-capable rootfs and a
portable candidate artifact. This module converts that exact evidence chain into
a review packet and, only after an explicit human ``reviewed=True`` decision,
into a host-side Phosh reproducibility authority. It never performs device I/O
and never grants hardware or Beta credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, TypeVar

from .phosh_candidate_artifact import (
    PhoshCandidateArtifactError,
    PhoshRootfsCandidateArtifactEvidence,
    validate_phosh_rootfs_candidate_artifact_evidence,
)
from .phosh_reproducibility import (
    PhoshReproducibilityError,
    PhoshRootfsReproducibilityCandidate,
    load_phosh_rootfs_build_evidence,
)
from .stable_file import StableFileError, read_stable_regular_file


_PACKET_POLICY = "phosh-rootfs-review-packet-v1"
_AUTHORITY_POLICY = "phosh-rootfs-reviewed-authority-v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+:/ -]{0,127}$")
_MAX_EVIDENCE_BYTES = 512 * 1024
T = TypeVar("T")


class PhoshRootfsAuthorityError(ValueError):
    """Raised when Phosh review/authority evidence is malformed or detached."""


@dataclass(frozen=True)
class PhoshRootfsReviewPacketEvidence:
    schema_version: int
    review_policy: str
    repository: str
    source_run_id: int
    source_run_attempt: int
    source_commit: str
    candidate_artifact_evidence_sha256: str
    reproducibility_candidate_sha256: str
    selected_build_evidence_sha256: str
    upstream_commit: str
    source_lock_sha256: str
    build_contract_sha256: str
    build_plan_sha256: str
    rootfs_artifact_sha256: str
    rootfs_artifact_size: int
    package_manifest_sha256: str
    package_count: int
    strict_byte_identical: bool
    package_manifest_identical: bool
    rootfs_payload_verified: bool
    package_manifest_verified: bool
    independent_ab_match_verified: bool
    ready_for_authority_review: bool
    reviewed: bool
    reproducibility_authority: bool
    physical_validation_required: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PhoshRootfsAuthorityRecord:
    schema_version: int
    authority_policy: str
    authority_name: str
    authority_run_id: int
    authority_commit: str
    authority_artifact_id: int
    review_packet_sha256: str
    repository: str
    source_run_id: int
    source_run_attempt: int
    source_commit: str
    candidate_artifact_evidence_sha256: str
    reproducibility_candidate_sha256: str
    selected_build_evidence_sha256: str
    upstream_commit: str
    source_lock_sha256: str
    build_contract_sha256: str
    build_plan_sha256: str
    rootfs_artifact_sha256: str
    rootfs_artifact_size: int
    package_manifest_sha256: str
    package_count: int
    strict_byte_identical: bool
    package_manifest_identical: bool
    reviewed: bool
    reproducibility_authority: bool
    ready_for_first_boot_binding: bool
    physical_validation_required: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def authority_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise PhoshRootfsAuthorityError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _commit(value: object, label: str) -> str:
    if not isinstance(value, str) or not _COMMIT_RE.fullmatch(value):
        raise PhoshRootfsAuthorityError(f"{label} must be a full lowercase 40-hex commit")
    return value


def _positive(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PhoshRootfsAuthorityError(f"{label} must be a positive integer")
    return value


def _load_canonical_dataclass(path: Path, cls: type[T], label: str) -> tuple[T, str]:
    try:
        payload, identity = read_stable_regular_file(
            Path(path), max_bytes=_MAX_EVIDENCE_BYTES, label=label
        )
    except StableFileError as exc:
        raise PhoshRootfsAuthorityError(str(exc)) from exc
    try:
        raw: Any = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhoshRootfsAuthorityError(f"{label} is not valid UTF-8 JSON") from exc
    expected = {item.name for item in fields(cls)}
    if not isinstance(raw, dict) or set(raw) != expected:
        raise PhoshRootfsAuthorityError(f"{label} fields do not match schema")
    try:
        value = cls(**raw)
    except (TypeError, ValueError) as exc:
        raise PhoshRootfsAuthorityError(f"{label} field types are invalid") from exc
    canonical = value.canonical_json().encode("utf-8")
    if payload != canonical:
        raise PhoshRootfsAuthorityError(f"{label} is not canonical JSON")
    return value, identity.sha256


def _validate_reproducibility_candidate(
    evidence: PhoshRootfsReproducibilityCandidate,
) -> None:
    if evidence.schema_version != 1:
        raise PhoshRootfsAuthorityError("unsupported Phosh reproducibility-candidate schema")
    _commit(evidence.upstream_commit, "Phosh upstream commit")
    for label, value in (
        ("source lock", evidence.source_lock_sha256),
        ("build contract", evidence.build_contract_sha256),
        ("build plan", evidence.build_plan_sha256),
        ("build A evidence", evidence.build_a_evidence_sha256),
        ("build B evidence", evidence.build_b_evidence_sha256),
        ("rootfs artifact", evidence.artifact_sha256),
        ("package manifest", evidence.package_manifest_sha256),
    ):
        _sha(value, label)
    _positive(evidence.artifact_size, "rootfs artifact size")
    _positive(evidence.package_count, "package count")
    if not evidence.build_a_origin or not evidence.build_b_origin:
        raise PhoshRootfsAuthorityError("Phosh A/B origins must be non-empty")
    if evidence.build_a_origin == evidence.build_b_origin:
        raise PhoshRootfsAuthorityError("Phosh A/B origins must be distinct")
    if (
        evidence.strict_byte_identical is not True
        or evidence.package_manifest_identical is not True
        or evidence.review_required is not True
        or evidence.reproducibility_authority is not False
        or evidence.physical_validation_required is not True
        or evidence.hardware_verified is not False
        or evidence.beta_gate_credit is not False
    ):
        raise PhoshRootfsAuthorityError("Phosh reproducibility candidate has invalid safety state")


def build_phosh_rootfs_review_packet(
    *,
    candidate_artifact_path: Path,
    reproducibility_candidate_path: Path,
    selected_build_evidence_path: Path,
    repository: str,
    source_run_id: int,
    source_run_attempt: int,
    source_commit: str,
) -> PhoshRootfsReviewPacketEvidence:
    """Cross-check the exact materialized rootfs candidate into a review packet."""
    if not isinstance(repository, str) or not _REPOSITORY_RE.fullmatch(repository):
        raise PhoshRootfsAuthorityError("repository must be OWNER/REPO")
    _positive(source_run_id, "source run id")
    _positive(source_run_attempt, "source run attempt")
    _commit(source_commit, "source commit")

    candidate, candidate_sha = _load_canonical_dataclass(
        Path(candidate_artifact_path),
        PhoshRootfsCandidateArtifactEvidence,
        "Phosh rootfs candidate artifact evidence",
    )
    try:
        validate_phosh_rootfs_candidate_artifact_evidence(candidate)
    except PhoshCandidateArtifactError as exc:
        raise PhoshRootfsAuthorityError(str(exc)) from exc

    repro, repro_sha = _load_canonical_dataclass(
        Path(reproducibility_candidate_path),
        PhoshRootfsReproducibilityCandidate,
        "Phosh rootfs reproducibility candidate",
    )
    _validate_reproducibility_candidate(repro)

    try:
        build, build_sha = load_phosh_rootfs_build_evidence(Path(selected_build_evidence_path))
    except PhoshReproducibilityError as exc:
        raise PhoshRootfsAuthorityError(str(exc)) from exc

    if candidate.reproducibility_candidate_sha256 != repro_sha:
        raise PhoshRootfsAuthorityError("candidate artifact is detached from reproducibility evidence")
    if candidate.selected_build_evidence_sha256 != build_sha:
        raise PhoshRootfsAuthorityError("candidate artifact is detached from selected build evidence")

    if candidate.selected_build_origin == repro.build_a_origin:
        expected_build_sha = repro.build_a_evidence_sha256
    elif candidate.selected_build_origin == repro.build_b_origin:
        expected_build_sha = repro.build_b_evidence_sha256
    else:
        raise PhoshRootfsAuthorityError("selected build origin is absent from A/B evidence")
    if build_sha != expected_build_sha:
        raise PhoshRootfsAuthorityError("selected build digest does not match its A/B origin")

    identity_pairs = (
        ("upstream_commit", candidate.upstream_commit, repro.upstream_commit, build["upstream_commit"]),
        ("source_lock_sha256", candidate.source_lock_sha256, repro.source_lock_sha256, build["source_lock_sha256"]),
        ("build_contract_sha256", candidate.build_contract_sha256, repro.build_contract_sha256, build["build_contract_sha256"]),
        ("build_plan_sha256", candidate.build_plan_sha256, repro.build_plan_sha256, build["build_plan_sha256"]),
        ("rootfs_artifact_sha256", candidate.rootfs_artifact_sha256, repro.artifact_sha256, build["artifact_sha256"]),
        ("rootfs_artifact_size", candidate.rootfs_artifact_size, repro.artifact_size, build["artifact_size"]),
        ("package_manifest_sha256", candidate.package_manifest_sha256, repro.package_manifest_sha256, build["package_manifest_sha256"]),
        ("package_count", candidate.package_count, repro.package_count, build["package_count"]),
    )
    for label, a, b, c in identity_pairs:
        if a != b or a != c:
            raise PhoshRootfsAuthorityError(f"Phosh review identity mismatch: {label}")

    evidence = PhoshRootfsReviewPacketEvidence(
        schema_version=1,
        review_policy=_PACKET_POLICY,
        repository=repository,
        source_run_id=source_run_id,
        source_run_attempt=source_run_attempt,
        source_commit=source_commit,
        candidate_artifact_evidence_sha256=candidate_sha,
        reproducibility_candidate_sha256=repro_sha,
        selected_build_evidence_sha256=build_sha,
        upstream_commit=candidate.upstream_commit,
        source_lock_sha256=candidate.source_lock_sha256,
        build_contract_sha256=candidate.build_contract_sha256,
        build_plan_sha256=candidate.build_plan_sha256,
        rootfs_artifact_sha256=candidate.rootfs_artifact_sha256,
        rootfs_artifact_size=candidate.rootfs_artifact_size,
        package_manifest_sha256=candidate.package_manifest_sha256,
        package_count=candidate.package_count,
        strict_byte_identical=True,
        package_manifest_identical=True,
        rootfs_payload_verified=True,
        package_manifest_verified=True,
        independent_ab_match_verified=True,
        ready_for_authority_review=True,
        reviewed=False,
        reproducibility_authority=False,
        physical_validation_required=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    validate_phosh_rootfs_review_packet(evidence)
    return evidence


def validate_phosh_rootfs_review_packet(evidence: PhoshRootfsReviewPacketEvidence) -> None:
    if not isinstance(evidence, PhoshRootfsReviewPacketEvidence) or evidence.schema_version != 1:
        raise PhoshRootfsAuthorityError("Phosh rootfs review packet must be schema-v1 typed evidence")
    if evidence.review_policy != _PACKET_POLICY:
        raise PhoshRootfsAuthorityError("unsupported Phosh rootfs review policy")
    if not _REPOSITORY_RE.fullmatch(evidence.repository):
        raise PhoshRootfsAuthorityError("review packet repository must be OWNER/REPO")
    _positive(evidence.source_run_id, "source run id")
    _positive(evidence.source_run_attempt, "source run attempt")
    _commit(evidence.source_commit, "source commit")
    _commit(evidence.upstream_commit, "Phosh upstream commit")
    for label, value in (
        ("candidate artifact evidence", evidence.candidate_artifact_evidence_sha256),
        ("reproducibility candidate", evidence.reproducibility_candidate_sha256),
        ("selected build evidence", evidence.selected_build_evidence_sha256),
        ("source lock", evidence.source_lock_sha256),
        ("build contract", evidence.build_contract_sha256),
        ("build plan", evidence.build_plan_sha256),
        ("rootfs artifact", evidence.rootfs_artifact_sha256),
        ("package manifest", evidence.package_manifest_sha256),
    ):
        _sha(value, label)
    _positive(evidence.rootfs_artifact_size, "rootfs artifact size")
    _positive(evidence.package_count, "package count")
    for name in (
        "strict_byte_identical",
        "package_manifest_identical",
        "rootfs_payload_verified",
        "package_manifest_verified",
        "independent_ab_match_verified",
        "ready_for_authority_review",
        "physical_validation_required",
    ):
        if getattr(evidence, name) is not True:
            raise PhoshRootfsAuthorityError(f"review packet requires {name}=true")
    for name in ("reviewed", "reproducibility_authority", "hardware_verified", "beta_gate_credit"):
        if getattr(evidence, name) is not False:
            raise PhoshRootfsAuthorityError(f"review packet cannot promote {name}")


def write_phosh_rootfs_review_packet(
    evidence: PhoshRootfsReviewPacketEvidence, destination: Path
) -> str:
    validate_phosh_rootfs_review_packet(evidence)
    return _write_new_canonical(evidence.canonical_json(), Path(destination), "Phosh review packet")


def load_phosh_rootfs_review_packet(path: Path) -> PhoshRootfsReviewPacketEvidence:
    evidence, _digest = _load_canonical_dataclass(
        Path(path), PhoshRootfsReviewPacketEvidence, "Phosh rootfs review packet"
    )
    validate_phosh_rootfs_review_packet(evidence)
    return evidence


def build_reviewed_phosh_rootfs_authority(
    *,
    review_packet: PhoshRootfsReviewPacketEvidence,
    authority_name: str,
    authority_run_id: int,
    authority_commit: str,
    authority_artifact_id: int,
    reviewed: bool,
) -> PhoshRootfsAuthorityRecord:
    """Promote one exact packet only after an explicit completed review."""
    validate_phosh_rootfs_review_packet(review_packet)
    if reviewed is not True:
        raise PhoshRootfsAuthorityError("explicit reviewed=true is required for authority creation")
    if not isinstance(authority_name, str) or not _NAME_RE.fullmatch(authority_name):
        raise PhoshRootfsAuthorityError("authority name is invalid")
    _positive(authority_run_id, "authority run id")
    _positive(authority_artifact_id, "authority artifact id")
    _commit(authority_commit, "authority commit")
    if authority_run_id != review_packet.source_run_id:
        raise PhoshRootfsAuthorityError("authority run id must match the reviewed source run")
    if authority_commit != review_packet.source_commit:
        raise PhoshRootfsAuthorityError("authority commit must match the reviewed source commit")

    authority = PhoshRootfsAuthorityRecord(
        schema_version=1,
        authority_policy=_AUTHORITY_POLICY,
        authority_name=authority_name,
        authority_run_id=authority_run_id,
        authority_commit=authority_commit,
        authority_artifact_id=authority_artifact_id,
        review_packet_sha256=review_packet.evidence_sha256(),
        repository=review_packet.repository,
        source_run_id=review_packet.source_run_id,
        source_run_attempt=review_packet.source_run_attempt,
        source_commit=review_packet.source_commit,
        candidate_artifact_evidence_sha256=review_packet.candidate_artifact_evidence_sha256,
        reproducibility_candidate_sha256=review_packet.reproducibility_candidate_sha256,
        selected_build_evidence_sha256=review_packet.selected_build_evidence_sha256,
        upstream_commit=review_packet.upstream_commit,
        source_lock_sha256=review_packet.source_lock_sha256,
        build_contract_sha256=review_packet.build_contract_sha256,
        build_plan_sha256=review_packet.build_plan_sha256,
        rootfs_artifact_sha256=review_packet.rootfs_artifact_sha256,
        rootfs_artifact_size=review_packet.rootfs_artifact_size,
        package_manifest_sha256=review_packet.package_manifest_sha256,
        package_count=review_packet.package_count,
        strict_byte_identical=True,
        package_manifest_identical=True,
        reviewed=True,
        reproducibility_authority=True,
        ready_for_first_boot_binding=True,
        physical_validation_required=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    validate_phosh_rootfs_authority(authority, review_packet)
    return authority


def validate_phosh_rootfs_authority(
    authority: PhoshRootfsAuthorityRecord,
    review_packet: PhoshRootfsReviewPacketEvidence,
) -> None:
    validate_phosh_rootfs_review_packet(review_packet)
    if not isinstance(authority, PhoshRootfsAuthorityRecord) or authority.schema_version != 1:
        raise PhoshRootfsAuthorityError("Phosh rootfs authority must be schema-v1 typed evidence")
    if authority.authority_policy != _AUTHORITY_POLICY:
        raise PhoshRootfsAuthorityError("unsupported Phosh rootfs authority policy")
    if not _NAME_RE.fullmatch(authority.authority_name):
        raise PhoshRootfsAuthorityError("authority name is invalid")
    _positive(authority.authority_run_id, "authority run id")
    _positive(authority.authority_artifact_id, "authority artifact id")
    _commit(authority.authority_commit, "authority commit")
    _sha(authority.review_packet_sha256, "review packet")
    if authority.review_packet_sha256 != review_packet.evidence_sha256():
        raise PhoshRootfsAuthorityError("authority is detached from the reviewed packet")
    expected = {
        "repository": review_packet.repository,
        "source_run_id": review_packet.source_run_id,
        "source_run_attempt": review_packet.source_run_attempt,
        "source_commit": review_packet.source_commit,
        "candidate_artifact_evidence_sha256": review_packet.candidate_artifact_evidence_sha256,
        "reproducibility_candidate_sha256": review_packet.reproducibility_candidate_sha256,
        "selected_build_evidence_sha256": review_packet.selected_build_evidence_sha256,
        "upstream_commit": review_packet.upstream_commit,
        "source_lock_sha256": review_packet.source_lock_sha256,
        "build_contract_sha256": review_packet.build_contract_sha256,
        "build_plan_sha256": review_packet.build_plan_sha256,
        "rootfs_artifact_sha256": review_packet.rootfs_artifact_sha256,
        "rootfs_artifact_size": review_packet.rootfs_artifact_size,
        "package_manifest_sha256": review_packet.package_manifest_sha256,
        "package_count": review_packet.package_count,
    }
    for name, value in expected.items():
        if getattr(authority, name) != value:
            raise PhoshRootfsAuthorityError(f"authority drifted from review packet: {name}")
    if authority.authority_run_id != review_packet.source_run_id:
        raise PhoshRootfsAuthorityError("authority run id differs from reviewed run")
    if authority.authority_commit != review_packet.source_commit:
        raise PhoshRootfsAuthorityError("authority commit differs from reviewed source commit")
    for name in (
        "strict_byte_identical",
        "package_manifest_identical",
        "reviewed",
        "reproducibility_authority",
        "ready_for_first_boot_binding",
        "physical_validation_required",
    ):
        if getattr(authority, name) is not True:
            raise PhoshRootfsAuthorityError(f"authority requires {name}=true")
    if authority.hardware_verified is not False or authority.beta_gate_credit is not False:
        raise PhoshRootfsAuthorityError("host Phosh rootfs authority cannot grant hardware/Beta credit")


def write_phosh_rootfs_authority(authority: PhoshRootfsAuthorityRecord, destination: Path) -> str:
    path = Path(destination)
    if authority.hardware_verified is not False or authority.beta_gate_credit is not False:
        raise PhoshRootfsAuthorityError("refusing unsafe Phosh rootfs authority state")
    return _write_new_canonical(authority.canonical_json(), path, "Phosh rootfs authority")


def load_and_verify_phosh_rootfs_authority(
    authority_path: Path, review_packet_path: Path
) -> PhoshRootfsAuthorityRecord:
    packet = load_phosh_rootfs_review_packet(Path(review_packet_path))
    authority, _digest = _load_canonical_dataclass(
        Path(authority_path), PhoshRootfsAuthorityRecord, "Phosh rootfs authority"
    )
    validate_phosh_rootfs_authority(authority, packet)
    return authority


def _write_new_canonical(payload: str, path: Path, label: str) -> str:
    if path.exists() or path.is_symlink():
        raise PhoshRootfsAuthorityError(f"refusing to overwrite {label}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise PhoshRootfsAuthorityError(f"refusing stale {label} temporary path")
    data = payload.encode("utf-8")
    try:
        temporary.write_bytes(data)
        temporary.replace(path)
    except OSError as exc:
        raise PhoshRootfsAuthorityError(f"cannot write {label}: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return sha256(data).hexdigest()
