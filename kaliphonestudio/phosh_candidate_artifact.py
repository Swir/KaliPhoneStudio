"""Materialize one exact Phosh ARM64 rootfs payload after independent A/B equality.

This is a host-side packaging boundary. It turns the real build-A payload plus
the exact package manifest and A/B reproducibility-candidate evidence into one
portable candidate record for later first-boot assembly. It never creates a
reviewed reproducibility authority and never grants hardware or Beta credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from .phosh_reproducibility import (
    PhoshReproducibilityError,
    PhoshRootfsReproducibilityCandidate,
    load_phosh_rootfs_build_evidence,
)
from .stable_file import StableFileError, hash_stable_regular_file, read_stable_regular_file


_POLICY = "phosh-rootfs-candidate-artifact-v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_MAX_ROOTFS_BYTES = 8 * 1024 * 1024 * 1024
_MAX_MANIFEST_BYTES = 32 * 1024 * 1024
_MAX_EVIDENCE_BYTES = 256 * 1024


class PhoshCandidateArtifactError(ValueError):
    """Raised when a real Phosh rootfs payload is detached from its A/B proof."""


@dataclass(frozen=True)
class PhoshRootfsCandidateArtifactEvidence:
    schema_version: int
    candidate_policy: str
    selected_build_origin: str
    selected_build_evidence_sha256: str
    reproducibility_candidate_sha256: str
    upstream_commit: str
    source_lock_sha256: str
    build_contract_sha256: str
    build_plan_sha256: str
    rootfs_artifact_sha256: str
    rootfs_artifact_size: int
    package_manifest_sha256: str
    package_count: int
    rootfs_payload_verified: bool
    package_manifest_verified: bool
    independent_ab_match_verified: bool
    ready_for_first_boot_candidate_assembly: bool
    reproducibility_authority: bool
    physical_validation_required: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise PhoshCandidateArtifactError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _positive(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PhoshCandidateArtifactError(f"{label} must be a positive integer")
    return value


def _load_reproducibility_candidate(
    path: Path,
) -> tuple[PhoshRootfsReproducibilityCandidate, str]:
    try:
        payload, identity = read_stable_regular_file(
            Path(path),
            max_bytes=_MAX_EVIDENCE_BYTES,
            label="Phosh reproducibility candidate",
        )
    except StableFileError as exc:
        raise PhoshCandidateArtifactError(str(exc)) from exc
    try:
        raw: Any = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhoshCandidateArtifactError("Phosh reproducibility candidate is not valid UTF-8 JSON") from exc

    expected = {item.name for item in fields(PhoshRootfsReproducibilityCandidate)}
    if not isinstance(raw, dict) or set(raw) != expected:
        raise PhoshCandidateArtifactError("unexpected Phosh reproducibility-candidate fields")
    try:
        candidate = PhoshRootfsReproducibilityCandidate(**raw)
    except (TypeError, ValueError) as exc:
        raise PhoshCandidateArtifactError("invalid Phosh reproducibility-candidate field types") from exc

    for label, value in (
        ("source lock", candidate.source_lock_sha256),
        ("build contract", candidate.build_contract_sha256),
        ("build plan", candidate.build_plan_sha256),
        ("build A evidence", candidate.build_a_evidence_sha256),
        ("build B evidence", candidate.build_b_evidence_sha256),
        ("rootfs artifact", candidate.artifact_sha256),
        ("package manifest", candidate.package_manifest_sha256),
    ):
        _sha(value, label)
    if not _COMMIT_RE.fullmatch(candidate.upstream_commit):
        raise PhoshCandidateArtifactError("Phosh upstream commit must be a full lowercase 40-hex commit")
    _positive(candidate.artifact_size, "rootfs artifact size")
    _positive(candidate.package_count, "package count")
    if not candidate.build_a_origin or not candidate.build_b_origin or candidate.build_a_origin == candidate.build_b_origin:
        raise PhoshCandidateArtifactError("Phosh A/B build origins must be distinct and non-empty")
    if (
        candidate.strict_byte_identical is not True
        or candidate.package_manifest_identical is not True
        or candidate.review_required is not True
        or candidate.reproducibility_authority is not False
        or candidate.physical_validation_required is not True
        or candidate.hardware_verified is not False
        or candidate.beta_gate_credit is not False
    ):
        raise PhoshCandidateArtifactError("Phosh reproducibility candidate carries invalid safety state")
    if payload != candidate.canonical_json().encode("utf-8"):
        raise PhoshCandidateArtifactError("Phosh reproducibility candidate is not canonical JSON")
    return candidate, identity.sha256


def _validate_package_manifest(payload: bytes, expected_count: int) -> None:
    if not payload.endswith(b"\n"):
        raise PhoshCandidateArtifactError("Phosh package manifest must end with one newline")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PhoshCandidateArtifactError("Phosh package manifest is not valid UTF-8") from exc
    lines = text.splitlines()
    if len(lines) != expected_count or not lines:
        raise PhoshCandidateArtifactError("Phosh package manifest count differs from build evidence")
    if lines != sorted(lines) or len(lines) != len(set(lines)):
        raise PhoshCandidateArtifactError("Phosh package manifest must be sorted and unique")
    packages: set[str] = set()
    for line in lines:
        parts = line.split("\t")
        if len(parts) != 3 or not all(parts):
            raise PhoshCandidateArtifactError("Phosh package manifest contains a malformed entry")
        package, _version, architecture = parts
        if package in packages:
            raise PhoshCandidateArtifactError("Phosh package manifest contains duplicate package names")
        packages.add(package)
        if architecture not in {"arm64", "all"}:
            raise PhoshCandidateArtifactError("Phosh package manifest contains a non-ARM64 package entry")


def materialize_phosh_rootfs_candidate(
    *,
    rootfs_artifact_path: Path,
    package_manifest_path: Path,
    build_evidence_path: Path,
    reproducibility_candidate_path: Path,
    selected_build_origin: str,
) -> PhoshRootfsCandidateArtifactEvidence:
    """Verify exact candidate bytes against one selected A/B build and its equality proof."""
    try:
        build, build_evidence_sha = load_phosh_rootfs_build_evidence(Path(build_evidence_path))
    except PhoshReproducibilityError as exc:
        raise PhoshCandidateArtifactError(str(exc)) from exc
    candidate, candidate_sha = _load_reproducibility_candidate(Path(reproducibility_candidate_path))

    if selected_build_origin == candidate.build_a_origin:
        expected_build_evidence_sha = candidate.build_a_evidence_sha256
    elif selected_build_origin == candidate.build_b_origin:
        expected_build_evidence_sha = candidate.build_b_evidence_sha256
    else:
        raise PhoshCandidateArtifactError("selected build origin is not part of the A/B reproducibility candidate")
    if build_evidence_sha != expected_build_evidence_sha:
        raise PhoshCandidateArtifactError("selected build evidence digest does not match the A/B candidate")

    for field in (
        "upstream_commit",
        "source_lock_sha256",
        "build_contract_sha256",
        "build_plan_sha256",
        "artifact_sha256",
        "artifact_size",
        "package_manifest_sha256",
        "package_count",
    ):
        if build[field] != getattr(candidate, field):
            raise PhoshCandidateArtifactError(f"selected build drifted from A/B candidate: {field}")

    try:
        rootfs_identity = hash_stable_regular_file(
            Path(rootfs_artifact_path),
            max_bytes=_MAX_ROOTFS_BYTES,
            expected_size=candidate.artifact_size,
            label="Phosh rootfs candidate artifact",
        )
        manifest_payload, manifest_identity = read_stable_regular_file(
            Path(package_manifest_path),
            max_bytes=_MAX_MANIFEST_BYTES,
            label="Phosh package manifest",
        )
    except StableFileError as exc:
        raise PhoshCandidateArtifactError(str(exc)) from exc

    if rootfs_identity.sha256 != candidate.artifact_sha256:
        raise PhoshCandidateArtifactError("materialized Phosh rootfs bytes do not match A/B evidence")
    if manifest_identity.sha256 != candidate.package_manifest_sha256:
        raise PhoshCandidateArtifactError("materialized Phosh package manifest does not match A/B evidence")
    _validate_package_manifest(manifest_payload, candidate.package_count)

    evidence = PhoshRootfsCandidateArtifactEvidence(
        schema_version=1,
        candidate_policy=_POLICY,
        selected_build_origin=selected_build_origin,
        selected_build_evidence_sha256=build_evidence_sha,
        reproducibility_candidate_sha256=candidate_sha,
        upstream_commit=candidate.upstream_commit,
        source_lock_sha256=candidate.source_lock_sha256,
        build_contract_sha256=candidate.build_contract_sha256,
        build_plan_sha256=candidate.build_plan_sha256,
        rootfs_artifact_sha256=candidate.artifact_sha256,
        rootfs_artifact_size=candidate.artifact_size,
        package_manifest_sha256=candidate.package_manifest_sha256,
        package_count=candidate.package_count,
        rootfs_payload_verified=True,
        package_manifest_verified=True,
        independent_ab_match_verified=True,
        ready_for_first_boot_candidate_assembly=True,
        reproducibility_authority=False,
        physical_validation_required=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    validate_phosh_rootfs_candidate_artifact_evidence(evidence)
    return evidence


def validate_phosh_rootfs_candidate_artifact_evidence(
    evidence: PhoshRootfsCandidateArtifactEvidence,
) -> None:
    if not isinstance(evidence, PhoshRootfsCandidateArtifactEvidence) or evidence.schema_version != 1:
        raise PhoshCandidateArtifactError("Phosh candidate artifact evidence must be schema-v1 typed evidence")
    if evidence.candidate_policy != _POLICY:
        raise PhoshCandidateArtifactError("unsupported Phosh candidate artifact policy")
    if not evidence.selected_build_origin:
        raise PhoshCandidateArtifactError("selected Phosh build origin must be non-empty")
    for label, value in (
        ("selected build evidence", evidence.selected_build_evidence_sha256),
        ("reproducibility candidate", evidence.reproducibility_candidate_sha256),
        ("source lock", evidence.source_lock_sha256),
        ("build contract", evidence.build_contract_sha256),
        ("build plan", evidence.build_plan_sha256),
        ("rootfs artifact", evidence.rootfs_artifact_sha256),
        ("package manifest", evidence.package_manifest_sha256),
    ):
        _sha(value, label)
    if not _COMMIT_RE.fullmatch(evidence.upstream_commit):
        raise PhoshCandidateArtifactError("Phosh upstream commit must be a full lowercase 40-hex commit")
    _positive(evidence.rootfs_artifact_size, "rootfs artifact size")
    _positive(evidence.package_count, "package count")
    for name in (
        "rootfs_payload_verified",
        "package_manifest_verified",
        "independent_ab_match_verified",
        "ready_for_first_boot_candidate_assembly",
        "physical_validation_required",
    ):
        if getattr(evidence, name) is not True:
            raise PhoshCandidateArtifactError(f"Phosh candidate artifact evidence requires {name}=true")
    for name in ("reproducibility_authority", "hardware_verified", "beta_gate_credit"):
        if getattr(evidence, name) is not False:
            raise PhoshCandidateArtifactError(f"Phosh candidate artifact evidence cannot promote {name}")


def write_phosh_rootfs_candidate_artifact_evidence(
    evidence: PhoshRootfsCandidateArtifactEvidence,
    destination: Path,
) -> str:
    validate_phosh_rootfs_candidate_artifact_evidence(evidence)
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise PhoshCandidateArtifactError("refusing to overwrite Phosh candidate artifact evidence")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise PhoshCandidateArtifactError("refusing stale Phosh candidate artifact temporary file")
    try:
        temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
        temporary.replace(path)
    except OSError as exc:
        raise PhoshCandidateArtifactError(f"cannot write Phosh candidate artifact evidence: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()
