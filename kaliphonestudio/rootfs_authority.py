"""Reviewed authority records for reproducible Kali ARM64 rootfs artifacts.

A rootfs authority record is an immutable review decision over already-produced
host-side reproducibility evidence. It does not make the artifact a device build
and it never grants physical-device or Beta credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .rootfs import RepositorySnapshotEvidence, RootfsArtifactEvidence, RootfsError

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_AUTHORITY_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")


@dataclass(frozen=True)
class RootfsAuthorityRecord:
    schema_version: int
    authority_name: str
    authority_run_id: int
    authority_commit: str
    authority_artifact_id: int
    release_tag: str
    architecture: str
    variant: str
    source_lock_sha256: str
    repository_snapshot_sha256: str
    inrelease_sha256: str
    rootfs_evidence_sha256: str
    canonicalization_binding_sha256: str
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
    strict_byte_identical: bool
    reviewed: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def authority_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


_REQUIRED_FIELDS = set(RootfsAuthorityRecord.__dataclass_fields__)
_BINDING_FIELDS = {
    "schema_version",
    "rootfs_evidence_sha256",
    "source_lock_sha256",
    "repository_snapshot_sha256",
    "canonicalization_policy_sha256",
    "canonicalization_a_evidence_sha256",
    "canonicalization_b_evidence_sha256",
    "raw_a_sha256",
    "raw_a_size",
    "raw_b_sha256",
    "raw_b_size",
    "artifact_sha256",
    "artifact_size",
    "package_manifest_sha256",
    "package_count",
    "strict_byte_identical",
    "beta_gate_credit",
}


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise RootfsError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _positive_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise RootfsError(f"{label} must be a positive integer")
    return value


def _canonical_mapping_sha256(raw: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(raw), sort_keys=True, separators=(",", ":")) + "\n"
    return sha256(payload.encode("utf-8")).hexdigest()


def authority_from_dict(raw: Any) -> RootfsAuthorityRecord:
    if not isinstance(raw, dict) or set(raw) != _REQUIRED_FIELDS:
        raise RootfsError("invalid rootfs authority record fields")
    if raw.get("schema_version") != 1:
        raise RootfsError("unsupported rootfs authority schema")

    name = raw.get("authority_name")
    if not isinstance(name, str) or not _AUTHORITY_NAME_RE.fullmatch(name):
        raise RootfsError("invalid rootfs authority name")
    commit = raw.get("authority_commit")
    if not isinstance(commit, str) or not _COMMIT_RE.fullmatch(commit):
        raise RootfsError("rootfs authority commit must be a full 40-hex commit")
    release_tag = raw.get("release_tag")
    if not isinstance(release_tag, str) or not release_tag.strip():
        raise RootfsError("rootfs authority release tag must be non-empty")
    if raw.get("architecture") != "arm64":
        raise RootfsError("rootfs authority must target arm64")
    if raw.get("variant") not in {"minimal", "full"}:
        raise RootfsError("rootfs authority has unsupported variant")
    if raw.get("strict_byte_identical") is not True:
        raise RootfsError("rootfs authority requires strict byte-identical A/B evidence")
    if raw.get("reviewed") is not True:
        raise RootfsError("rootfs authority must record an explicit completed review")
    if raw.get("hardware_verified") is not False:
        raise RootfsError("host rootfs authority cannot claim hardware verification")
    if raw.get("beta_gate_credit") is not False:
        raise RootfsError("host rootfs authority cannot claim Beta-gate credit")

    digest_fields = (
        "source_lock_sha256",
        "repository_snapshot_sha256",
        "inrelease_sha256",
        "rootfs_evidence_sha256",
        "canonicalization_binding_sha256",
        "canonicalization_policy_sha256",
        "canonicalization_a_evidence_sha256",
        "canonicalization_b_evidence_sha256",
        "raw_a_sha256",
        "raw_b_sha256",
        "artifact_sha256",
        "package_manifest_sha256",
    )
    validated = {field: _require_sha256(raw.get(field), field) for field in digest_fields}

    return RootfsAuthorityRecord(
        schema_version=1,
        authority_name=name,
        authority_run_id=_positive_int(raw.get("authority_run_id"), "rootfs authority run id"),
        authority_commit=commit,
        authority_artifact_id=_positive_int(raw.get("authority_artifact_id"), "rootfs authority artifact id"),
        release_tag=release_tag,
        architecture="arm64",
        variant=raw["variant"],
        source_lock_sha256=validated["source_lock_sha256"],
        repository_snapshot_sha256=validated["repository_snapshot_sha256"],
        inrelease_sha256=validated["inrelease_sha256"],
        rootfs_evidence_sha256=validated["rootfs_evidence_sha256"],
        canonicalization_binding_sha256=validated["canonicalization_binding_sha256"],
        canonicalization_policy_sha256=validated["canonicalization_policy_sha256"],
        canonicalization_a_evidence_sha256=validated["canonicalization_a_evidence_sha256"],
        canonicalization_b_evidence_sha256=validated["canonicalization_b_evidence_sha256"],
        raw_a_sha256=validated["raw_a_sha256"],
        raw_a_size=_positive_int(raw.get("raw_a_size"), "raw rootfs A size"),
        raw_b_sha256=validated["raw_b_sha256"],
        raw_b_size=_positive_int(raw.get("raw_b_size"), "raw rootfs B size"),
        artifact_sha256=validated["artifact_sha256"],
        artifact_size=_positive_int(raw.get("artifact_size"), "accepted rootfs artifact size"),
        package_manifest_sha256=validated["package_manifest_sha256"],
        package_count=_positive_int(raw.get("package_count"), "accepted rootfs package count"),
        strict_byte_identical=True,
        reviewed=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def load_rootfs_authority(path: Path) -> RootfsAuthorityRecord:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RootfsError(f"cannot read rootfs authority record: {exc}") from exc
    return authority_from_dict(raw)


def verify_rootfs_authority(
    authority: RootfsAuthorityRecord,
    rootfs_evidence: RootfsArtifactEvidence,
    canonicalization_binding: Mapping[str, Any],
    repository_snapshot: RepositorySnapshotEvidence,
) -> None:
    """Verify a reviewed authority record against its complete typed evidence chain."""
    # Re-parse the dataclass to make this function fail closed even when callers
    # construct it directly instead of using load_rootfs_authority().
    authority = authority_from_dict(asdict(authority))

    if rootfs_evidence.schema_version != 2 or rootfs_evidence.reproducible is not True:
        raise RootfsError("authority rootfs evidence is not a reproducible schema-v2 artifact")
    if rootfs_evidence.architecture != authority.architecture or rootfs_evidence.variant != authority.variant:
        raise RootfsError("authority rootfs target does not match reproducibility evidence")
    if rootfs_evidence.source_lock_sha256 != authority.source_lock_sha256:
        raise RootfsError("authority source-lock digest does not match rootfs evidence")
    if rootfs_evidence.repository_snapshot_sha256 != authority.repository_snapshot_sha256:
        raise RootfsError("authority repository snapshot digest does not match rootfs evidence")
    if rootfs_evidence.evidence_sha256() != authority.rootfs_evidence_sha256:
        raise RootfsError("authority rootfs-evidence digest does not match reviewed evidence")
    if (
        rootfs_evidence.artifact_sha256 != authority.artifact_sha256
        or rootfs_evidence.artifact_size != authority.artifact_size
        or rootfs_evidence.package_manifest_sha256 != authority.package_manifest_sha256
        or rootfs_evidence.package_count != authority.package_count
    ):
        raise RootfsError("authority accepted artifact/package identity does not match rootfs evidence")

    if repository_snapshot.schema_version != 2:
        raise RootfsError("authority repository snapshot must use schema v2")
    if repository_snapshot.architecture != authority.architecture:
        raise RootfsError("authority repository snapshot architecture mismatch")
    if repository_snapshot.inrelease_sha256 != authority.inrelease_sha256:
        raise RootfsError("authority InRelease digest does not match repository snapshot")
    if repository_snapshot.evidence_sha256() != authority.repository_snapshot_sha256:
        raise RootfsError("authority repository snapshot digest does not match reviewed snapshot")

    binding = dict(canonicalization_binding)
    if set(binding) != _BINDING_FIELDS or binding.get("schema_version") != 1:
        raise RootfsError("invalid authority canonicalization-binding schema")
    if binding.get("strict_byte_identical") is not True:
        raise RootfsError("authority canonicalization binding is not strict byte-identical")
    if binding.get("beta_gate_credit") is not False:
        raise RootfsError("authority canonicalization binding cannot claim Beta credit")
    if _canonical_mapping_sha256(binding) != authority.canonicalization_binding_sha256:
        raise RootfsError("authority canonicalization-binding digest mismatch")

    exact_fields = {
        "rootfs_evidence_sha256": authority.rootfs_evidence_sha256,
        "source_lock_sha256": authority.source_lock_sha256,
        "repository_snapshot_sha256": authority.repository_snapshot_sha256,
        "canonicalization_policy_sha256": authority.canonicalization_policy_sha256,
        "canonicalization_a_evidence_sha256": authority.canonicalization_a_evidence_sha256,
        "canonicalization_b_evidence_sha256": authority.canonicalization_b_evidence_sha256,
        "raw_a_sha256": authority.raw_a_sha256,
        "raw_a_size": authority.raw_a_size,
        "raw_b_sha256": authority.raw_b_sha256,
        "raw_b_size": authority.raw_b_size,
        "artifact_sha256": authority.artifact_sha256,
        "artifact_size": authority.artifact_size,
        "package_manifest_sha256": authority.package_manifest_sha256,
        "package_count": authority.package_count,
    }
    for field, expected in exact_fields.items():
        if binding.get(field) != expected:
            raise RootfsError(f"authority canonicalization binding mismatch: {field}")


def load_and_verify_rootfs_authority(
    authority_path: Path,
    rootfs_evidence_path: Path,
    canonicalization_binding_path: Path,
    repository_snapshot_path: Path,
) -> RootfsAuthorityRecord:
    from .rootfs import load_repository_snapshot
    from .rootfs_canonical_binding import load_rootfs_artifact_evidence

    authority = load_rootfs_authority(authority_path)
    rootfs_evidence = load_rootfs_artifact_evidence(rootfs_evidence_path)
    repository_snapshot = load_repository_snapshot(repository_snapshot_path)
    try:
        binding = json.loads(canonicalization_binding_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RootfsError(f"cannot read rootfs canonicalization binding: {exc}") from exc
    if not isinstance(binding, dict):
        raise RootfsError("rootfs canonicalization binding must be a JSON object")
    verify_rootfs_authority(authority, rootfs_evidence, binding, repository_snapshot)
    return authority
