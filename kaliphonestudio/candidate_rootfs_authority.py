"""Bind a first-boot candidate to a reviewed reproducible rootfs authority.

The rootfs canonicalization/provenance layer proves which raw A/B builds and reviewed
normalization policy produced the strict rootfs bytes referenced by a candidate.  A
separate reviewed authority record is created only after the expensive real A/B run
has completed and its evidence has been accepted.  This module joins those two chains
without pretending that host-side review proves anything about a physical phone.

No phone I/O is performed here.  The output always has hardware_verified=false and
beta_gate_credit=false.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import re
from pathlib import Path

from .candidate import FirstBootCandidateManifest
from .candidate_rootfs_provenance import FirstBootRootfsProvenanceEvidence
from .rootfs import RootfsError
from .rootfs_authority import RootfsAuthorityRecord, authority_from_dict

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class FirstBootRootfsAuthorityEvidence:
    schema_version: int
    profile_id: str
    first_boot_manifest_sha256: str
    first_boot_rootfs_provenance_sha256: str
    rootfs_authority_sha256: str
    authority_name: str
    authority_run_id: int
    authority_commit: str
    authority_artifact_id: int
    release_tag: str
    architecture: str
    variant: str
    rootfs_evidence_sha256: str
    rootfs_canonicalization_binding_sha256: str
    canonicalization_policy_sha256: str
    artifact_sha256: str
    artifact_size: int
    package_manifest_sha256: str
    package_count: int
    source_lock_sha256: str
    repository_snapshot_sha256: str
    inrelease_sha256: str
    strict_byte_identical: bool
    reviewed: bool
    hardware_verified: bool = False
    beta_gate_credit: bool = False

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


def bind_first_boot_candidate_to_rootfs_authority(
    manifest: FirstBootCandidateManifest,
    provenance: FirstBootRootfsProvenanceEvidence,
    authority: RootfsAuthorityRecord,
) -> FirstBootRootfsAuthorityEvidence:
    """Bind an exact first-boot manifest/provenance chain to reviewed rootfs authority.

    This function deliberately does not create or infer an authority.  It accepts only
    a typed record that passes the authority schema's fail-closed invariants, and then
    requires every candidate-visible rootfs identity to agree with the accepted record.
    """
    if not isinstance(manifest, FirstBootCandidateManifest):
        raise RootfsError("rootfs authority binding requires a typed first-boot candidate manifest")
    if manifest.schema_version != 8:
        raise RootfsError("unsupported first-boot candidate schema for rootfs authority binding")
    if not isinstance(manifest.profile_id, str) or not manifest.profile_id.strip():
        raise RootfsError("first-boot candidate has invalid profile id")

    if not isinstance(provenance, FirstBootRootfsProvenanceEvidence):
        raise RootfsError("rootfs authority binding requires typed candidate rootfs provenance")
    if provenance.schema_version != 1:
        raise RootfsError("unsupported first-boot rootfs provenance schema")
    if provenance.strict_byte_identical is not True:
        raise RootfsError("candidate rootfs provenance lacks strict byte-identical acceptance")
    if provenance.hardware_verified is not False or provenance.beta_gate_credit is not False:
        raise RootfsError("candidate rootfs provenance cannot claim hardware/Beta credit")
    if provenance.profile_id != manifest.profile_id:
        raise RootfsError("candidate rootfs provenance profile does not match first-boot manifest")

    manifest_digest = _require_sha256(manifest.manifest_sha256(), "first-boot manifest")
    if provenance.first_boot_manifest_sha256 != manifest_digest:
        raise RootfsError("candidate rootfs provenance is detached from first-boot manifest")
    provenance_digest = _require_sha256(
        provenance.evidence_sha256(), "first-boot rootfs provenance"
    )

    if not isinstance(authority, RootfsAuthorityRecord):
        raise RootfsError("rootfs authority binding requires a typed authority record")
    # Reparse the dataclass so callers cannot bypass the authority's exact schema and
    # safety flags by constructing a malformed object directly.
    authority = authority_from_dict(asdict(authority))
    authority_digest = _require_sha256(authority.authority_sha256(), "rootfs authority")

    if authority.architecture != "arm64":
        raise RootfsError("reviewed rootfs authority is not ARM64")
    if authority.strict_byte_identical is not True or authority.reviewed is not True:
        raise RootfsError("reviewed rootfs authority lacks strict reviewed acceptance")
    if authority.hardware_verified is not False or authority.beta_gate_credit is not False:
        raise RootfsError("reviewed rootfs authority cannot claim hardware/Beta credit")
    _require_positive_int(authority.authority_run_id, "rootfs authority run id")
    _require_positive_int(authority.authority_artifact_id, "rootfs authority artifact id")
    if not _COMMIT_RE.fullmatch(authority.authority_commit):
        raise RootfsError("rootfs authority commit must be a full 40-hex commit")

    digest_pairs = (
        (manifest.rootfs_evidence_sha256, provenance.rootfs_evidence_sha256, "candidate/rootfs-provenance evidence"),
        (manifest.rootfs_artifact_sha256, provenance.artifact_sha256, "candidate/rootfs-provenance artifact"),
        (manifest.rootfs_package_manifest_sha256, provenance.package_manifest_sha256, "candidate/rootfs-provenance package manifest"),
        (manifest.rootfs_source_lock_sha256, provenance.source_lock_sha256, "candidate/rootfs-provenance source lock"),
        (manifest.repository_snapshot_sha256, provenance.repository_snapshot_sha256, "candidate/rootfs-provenance repository snapshot"),
        (provenance.rootfs_evidence_sha256, authority.rootfs_evidence_sha256, "provenance/authority rootfs evidence"),
        (provenance.rootfs_canonicalization_binding_sha256, authority.canonicalization_binding_sha256, "provenance/authority canonicalization binding"),
        (provenance.canonicalization_policy_sha256, authority.canonicalization_policy_sha256, "provenance/authority canonicalization policy"),
        (provenance.artifact_sha256, authority.artifact_sha256, "provenance/authority artifact"),
        (provenance.package_manifest_sha256, authority.package_manifest_sha256, "provenance/authority package manifest"),
        (provenance.source_lock_sha256, authority.source_lock_sha256, "provenance/authority source lock"),
        (provenance.repository_snapshot_sha256, authority.repository_snapshot_sha256, "provenance/authority repository snapshot"),
    )
    for left, right, label in digest_pairs:
        _require_sha256(left, f"{label} left SHA-256")
        _require_sha256(right, f"{label} right SHA-256")
        if left != right:
            raise RootfsError(f"rootfs authority binding mismatch: {label}")

    size_pairs = (
        (manifest.rootfs_artifact_size, provenance.artifact_size, "candidate/rootfs-provenance artifact size"),
        (manifest.rootfs_package_count, provenance.package_count, "candidate/rootfs-provenance package count"),
        (provenance.artifact_size, authority.artifact_size, "provenance/authority artifact size"),
        (provenance.package_count, authority.package_count, "provenance/authority package count"),
    )
    for left, right, label in size_pairs:
        _require_positive_int(left, f"{label} left")
        _require_positive_int(right, f"{label} right")
        if left != right:
            raise RootfsError(f"rootfs authority binding mismatch: {label}")

    for value, label in (
        (authority.inrelease_sha256, "authority InRelease SHA-256"),
        (authority.canonicalization_a_evidence_sha256, "authority canonicalization A evidence SHA-256"),
        (authority.canonicalization_b_evidence_sha256, "authority canonicalization B evidence SHA-256"),
        (authority.raw_a_sha256, "authority raw rootfs A SHA-256"),
        (authority.raw_b_sha256, "authority raw rootfs B SHA-256"),
    ):
        _require_sha256(value, label)

    if provenance.canonicalization_a_evidence_sha256 != authority.canonicalization_a_evidence_sha256:
        raise RootfsError("rootfs authority binding mismatch: canonicalization A evidence")
    if provenance.canonicalization_b_evidence_sha256 != authority.canonicalization_b_evidence_sha256:
        raise RootfsError("rootfs authority binding mismatch: canonicalization B evidence")
    if provenance.raw_a_sha256 != authority.raw_a_sha256 or provenance.raw_a_size != authority.raw_a_size:
        raise RootfsError("rootfs authority binding mismatch: raw rootfs A")
    if provenance.raw_b_sha256 != authority.raw_b_sha256 or provenance.raw_b_size != authority.raw_b_size:
        raise RootfsError("rootfs authority binding mismatch: raw rootfs B")

    return FirstBootRootfsAuthorityEvidence(
        schema_version=1,
        profile_id=manifest.profile_id,
        first_boot_manifest_sha256=manifest_digest,
        first_boot_rootfs_provenance_sha256=provenance_digest,
        rootfs_authority_sha256=authority_digest,
        authority_name=authority.authority_name,
        authority_run_id=authority.authority_run_id,
        authority_commit=authority.authority_commit,
        authority_artifact_id=authority.authority_artifact_id,
        release_tag=authority.release_tag,
        architecture=authority.architecture,
        variant=authority.variant,
        rootfs_evidence_sha256=authority.rootfs_evidence_sha256,
        rootfs_canonicalization_binding_sha256=authority.canonicalization_binding_sha256,
        canonicalization_policy_sha256=authority.canonicalization_policy_sha256,
        artifact_sha256=authority.artifact_sha256,
        artifact_size=authority.artifact_size,
        package_manifest_sha256=authority.package_manifest_sha256,
        package_count=authority.package_count,
        source_lock_sha256=authority.source_lock_sha256,
        repository_snapshot_sha256=authority.repository_snapshot_sha256,
        inrelease_sha256=authority.inrelease_sha256,
        strict_byte_identical=True,
        reviewed=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def write_first_boot_rootfs_authority_evidence(
    evidence: FirstBootRootfsAuthorityEvidence,
    destination: Path,
) -> str:
    """Atomically write canonical non-release candidate/authority binding evidence."""
    if not isinstance(evidence, FirstBootRootfsAuthorityEvidence):
        raise RootfsError("invalid first-boot rootfs authority evidence type")
    if evidence.schema_version != 1:
        raise RootfsError("unsupported first-boot rootfs authority evidence schema")
    if evidence.strict_byte_identical is not True or evidence.reviewed is not True:
        raise RootfsError("first-boot rootfs authority evidence is not strict/reviewed")
    if evidence.hardware_verified is not False or evidence.beta_gate_credit is not False:
        raise RootfsError("first-boot rootfs authority evidence cannot claim hardware/Beta credit")
    path = Path(destination)
    if path.exists():
        raise RootfsError("refusing to overwrite first-boot rootfs authority evidence")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists():
        raise RootfsError("refusing stale first-boot rootfs authority temporary file")
    try:
        temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()
