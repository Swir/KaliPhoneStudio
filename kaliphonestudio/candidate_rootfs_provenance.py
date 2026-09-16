"""Bind a first-boot candidate to reviewed rootfs canonicalization provenance.

The first-boot candidate already binds the strict reproducible rootfs artifact.  The
rootfs pipeline may additionally canonicalize a small reviewed set of volatile build
state before strict A/B comparison.  This module closes the remaining candidate-level
provenance gap: a future release candidate can prove which two raw rootfs builds were
transformed, which reviewed policy was used, and that both transformations produced
exactly the rootfs bytes referenced by the first-boot manifest.

This is host-side evidence only.  It never grants physical-device or Beta credit and
it performs no phone I/O.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import re

from .candidate import FirstBootCandidateManifest
from .rootfs import RootfsError
from .rootfs_canonical import RootfsCanonicalizationEvidence
from .rootfs_canonical_binding import (
    RootfsCanonicalizationBindingEvidence,
    canonicalization_policy_sha256,
)


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class FirstBootRootfsProvenanceEvidence:
    schema_version: int
    profile_id: str
    first_boot_manifest_sha256: str
    rootfs_evidence_sha256: str
    rootfs_canonicalization_binding_sha256: str
    canonicalization_policy_sha256: str
    canonicalization_a_evidence_sha256: str
    canonicalization_b_evidence_sha256: str
    raw_a_sha256: str
    raw_a_size: int
    raw_b_sha256: str
    raw_b_size: int
    artifact_sha256: str
    artifact_size: int
    package_manifest_sha256: str
    package_count: int
    source_lock_sha256: str
    repository_snapshot_sha256: str
    strict_byte_identical: bool
    beta_gate_credit: bool = False
    hardware_verified: bool = False

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise RootfsError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _require_positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise RootfsError(f"{label} must be a positive integer")
    return value


def _verify_canonical_record(
    record: RootfsCanonicalizationEvidence,
    *,
    expected_evidence_sha256: str,
    expected_raw_sha256: str,
    expected_raw_size: int,
    expected_artifact_sha256: str,
    expected_artifact_size: int,
    label: str,
) -> None:
    if record.schema_version != 1:
        raise RootfsError(f"rootfs canonicalization {label} has unsupported schema")
    if record.beta_gate_credit is not False:
        raise RootfsError(f"rootfs canonicalization {label} cannot claim Beta credit")
    if record.evidence_sha256() != expected_evidence_sha256:
        raise RootfsError(f"rootfs canonicalization {label} evidence digest drifted")
    if record.input_sha256 != expected_raw_sha256 or record.input_size != expected_raw_size:
        raise RootfsError(f"rootfs canonicalization {label} raw input does not match binding")
    if record.output_sha256 != expected_artifact_sha256 or record.output_size != expected_artifact_size:
        raise RootfsError(f"rootfs canonicalization {label} output does not match accepted artifact")


def bind_first_boot_candidate_to_rootfs_provenance(
    manifest: FirstBootCandidateManifest,
    binding: RootfsCanonicalizationBindingEvidence,
    *,
    canonical_a: RootfsCanonicalizationEvidence,
    canonical_b: RootfsCanonicalizationEvidence,
) -> FirstBootRootfsProvenanceEvidence:
    """Bind schema-v8 first-boot evidence to exact A/B canonicalization provenance.

    The canonicalization binding itself is produced only after strict byte-identical
    rootfs verification.  Here we independently cross-check every candidate-visible
    rootfs field plus both transformation records, preventing a valid canonicalization
    record from being detached from the first-boot manifest that will consume it.
    """
    if not isinstance(manifest, FirstBootCandidateManifest):
        raise RootfsError("first-boot rootfs provenance requires a typed candidate manifest")
    if manifest.schema_version != 8:
        raise RootfsError("unsupported first-boot candidate schema for rootfs provenance binding")
    if not isinstance(manifest.profile_id, str) or not manifest.profile_id.strip():
        raise RootfsError("first-boot candidate has invalid profile id")

    if not isinstance(binding, RootfsCanonicalizationBindingEvidence):
        raise RootfsError("rootfs canonicalization binding has invalid type")
    if binding.schema_version != 1:
        raise RootfsError("unsupported rootfs canonicalization binding schema")
    if binding.beta_gate_credit is not False:
        raise RootfsError("rootfs canonicalization binding cannot claim Beta credit")
    if binding.strict_byte_identical is not True:
        raise RootfsError("rootfs canonicalization binding lacks strict byte-identical acceptance")

    current_policy = canonicalization_policy_sha256()
    if binding.canonicalization_policy_sha256 != current_policy:
        raise RootfsError("rootfs canonicalization binding uses an unknown policy")

    first_boot_digest = _require_sha256(manifest.manifest_sha256(), "first-boot manifest")
    binding_digest = _require_sha256(binding.evidence_sha256(), "rootfs canonicalization binding")

    candidate_pairs = (
        (manifest.rootfs_evidence_sha256, binding.rootfs_evidence_sha256, "rootfs evidence SHA-256"),
        (manifest.rootfs_artifact_sha256, binding.artifact_sha256, "rootfs artifact SHA-256"),
        (manifest.rootfs_package_manifest_sha256, binding.package_manifest_sha256, "rootfs package manifest SHA-256"),
        (manifest.rootfs_source_lock_sha256, binding.source_lock_sha256, "rootfs source lock SHA-256"),
        (manifest.repository_snapshot_sha256, binding.repository_snapshot_sha256, "repository snapshot SHA-256"),
    )
    for candidate_value, binding_value, label in candidate_pairs:
        _require_sha256(candidate_value, f"candidate {label}")
        _require_sha256(binding_value, f"binding {label}")
        if candidate_value != binding_value:
            raise RootfsError(f"first-boot candidate {label} does not match canonicalization binding")

    if manifest.rootfs_artifact_size != binding.artifact_size:
        raise RootfsError("first-boot candidate rootfs artifact size does not match canonicalization binding")
    if manifest.rootfs_package_count != binding.package_count:
        raise RootfsError("first-boot candidate rootfs package count does not match canonicalization binding")
    _require_positive_int(binding.artifact_size, "canonical rootfs artifact size")
    _require_positive_int(binding.package_count, "canonical rootfs package count")
    _require_positive_int(binding.raw_a_size, "raw rootfs A size")
    _require_positive_int(binding.raw_b_size, "raw rootfs B size")

    for value, label in (
        (binding.canonicalization_a_evidence_sha256, "canonicalization A evidence SHA-256"),
        (binding.canonicalization_b_evidence_sha256, "canonicalization B evidence SHA-256"),
        (binding.raw_a_sha256, "raw rootfs A SHA-256"),
        (binding.raw_b_sha256, "raw rootfs B SHA-256"),
    ):
        _require_sha256(value, label)

    _verify_canonical_record(
        canonical_a,
        expected_evidence_sha256=binding.canonicalization_a_evidence_sha256,
        expected_raw_sha256=binding.raw_a_sha256,
        expected_raw_size=binding.raw_a_size,
        expected_artifact_sha256=binding.artifact_sha256,
        expected_artifact_size=binding.artifact_size,
        label="A",
    )
    _verify_canonical_record(
        canonical_b,
        expected_evidence_sha256=binding.canonicalization_b_evidence_sha256,
        expected_raw_sha256=binding.raw_b_sha256,
        expected_raw_size=binding.raw_b_size,
        expected_artifact_sha256=binding.artifact_sha256,
        expected_artifact_size=binding.artifact_size,
        label="B",
    )

    return FirstBootRootfsProvenanceEvidence(
        schema_version=1,
        profile_id=manifest.profile_id,
        first_boot_manifest_sha256=first_boot_digest,
        rootfs_evidence_sha256=binding.rootfs_evidence_sha256,
        rootfs_canonicalization_binding_sha256=binding_digest,
        canonicalization_policy_sha256=current_policy,
        canonicalization_a_evidence_sha256=binding.canonicalization_a_evidence_sha256,
        canonicalization_b_evidence_sha256=binding.canonicalization_b_evidence_sha256,
        raw_a_sha256=binding.raw_a_sha256,
        raw_a_size=binding.raw_a_size,
        raw_b_sha256=binding.raw_b_sha256,
        raw_b_size=binding.raw_b_size,
        artifact_sha256=binding.artifact_sha256,
        artifact_size=binding.artifact_size,
        package_manifest_sha256=binding.package_manifest_sha256,
        package_count=binding.package_count,
        source_lock_sha256=binding.source_lock_sha256,
        repository_snapshot_sha256=binding.repository_snapshot_sha256,
        strict_byte_identical=True,
        beta_gate_credit=False,
        hardware_verified=False,
    )


def write_first_boot_rootfs_provenance_evidence(
    evidence: FirstBootRootfsProvenanceEvidence,
    destination,
) -> str:
    """Atomically write canonical non-release provenance evidence."""
    from pathlib import Path

    if not isinstance(evidence, FirstBootRootfsProvenanceEvidence):
        raise RootfsError("invalid first-boot rootfs provenance evidence type")
    if evidence.schema_version != 1 or evidence.beta_gate_credit is not False or evidence.hardware_verified is not False:
        raise RootfsError("invalid first-boot rootfs provenance evidence flags")
    if evidence.strict_byte_identical is not True:
        raise RootfsError("first-boot rootfs provenance cannot represent a non-strict artifact")
    path = Path(destination)
    if path.exists():
        raise RootfsError("refusing to overwrite first-boot rootfs provenance evidence")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists():
        raise RootfsError("refusing stale first-boot rootfs provenance temporary file")
    try:
        payload = evidence.canonical_json()
        temporary.write_text(payload, encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()
