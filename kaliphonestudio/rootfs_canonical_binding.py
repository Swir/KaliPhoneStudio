"""Bind reviewed rootfs canonicalization records to strict reproducibility evidence.

The rootfs canonicalizer intentionally transforms a tiny, reviewed set of volatile
builder state before A/B byte comparison. This module closes the provenance gap
between those per-build audit records and the exact canonical rootfs accepted by the
strict reproducibility contract.

This is host-side evidence only. It never grants physical-device or Beta credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from .rootfs import (
    RepositorySnapshotEvidence,
    RootfsArtifactEvidence,
    RootfsError,
    RootfsSourceLock,
    verify_rootfs_artifact,
)
from .rootfs_canonical import RootfsCanonicalizationEvidence


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

# Explicit versioned description of the transformation implemented by
# rootfs_canonical.py. The digest is carried by binding evidence so a future policy
# change cannot silently inherit an older release candidate's provenance.
_CANONICALIZATION_POLICY_V1 = {
    "schema_version": 1,
    "archive_output": "tar-pax+xz",
    "member_mtime": 0,
    "pax_remove": ["atime", "ctime"],
    "pax_mtime": "0",
    "zero_content_paths": [
        "etc/fake-hwclock.data",
        "etc/machine-id",
        "var/lib/dbus/machine-id",
    ],
    "drop_paths": ["var/cache/ldconfig/aux-cache"],
    "shadow_policy": "preserve-star;lock-other-password-fields-with-bang;last-change-zero",
    "all_other_regular_file_payloads": "preserve",
    "archive_layout": "root-or-one-top-level-prefix;single-var/lib/dpkg/status",
}


@dataclass(frozen=True)
class RootfsCanonicalizationBindingEvidence:
    schema_version: int
    rootfs_evidence_sha256: str
    source_lock_sha256: str
    repository_snapshot_sha256: str
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
    beta_gate_credit: bool = False

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def canonicalization_policy_sha256() -> str:
    payload = json.dumps(
        _CANONICALIZATION_POLICY_V1, sort_keys=True, separators=(",", ":")
    ) + "\n"
    return sha256(payload.encode("utf-8")).hexdigest()


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise RootfsError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _require_positive_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise RootfsError(f"{label} must be a positive integer")
    return value


def _require_nonnegative_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise RootfsError(f"{label} must be a non-negative integer")
    return value


def rootfs_artifact_evidence_from_dict(raw: Any) -> RootfsArtifactEvidence:
    required = {
        "schema_version",
        "source_lock_sha256",
        "repository_snapshot_sha256",
        "architecture",
        "variant",
        "artifact_sha256",
        "artifact_size",
        "package_manifest_sha256",
        "package_count",
        "reproducible",
    }
    if not isinstance(raw, dict) or set(raw) != required or raw.get("schema_version") != 2:
        raise RootfsError("invalid rootfs artifact evidence schema")
    if raw.get("reproducible") is not True:
        raise RootfsError("rootfs artifact evidence is not reproducible")
    architecture = raw.get("architecture")
    variant = raw.get("variant")
    if not isinstance(architecture, str) or not architecture:
        raise RootfsError("rootfs artifact evidence has invalid architecture")
    if not isinstance(variant, str) or not variant:
        raise RootfsError("rootfs artifact evidence has invalid variant")
    return RootfsArtifactEvidence(
        schema_version=2,
        source_lock_sha256=_require_sha256(raw.get("source_lock_sha256"), "rootfs source lock"),
        repository_snapshot_sha256=_require_sha256(
            raw.get("repository_snapshot_sha256"), "rootfs repository snapshot"
        ),
        architecture=architecture,
        variant=variant,
        artifact_sha256=_require_sha256(raw.get("artifact_sha256"), "rootfs artifact"),
        artifact_size=_require_positive_int(raw.get("artifact_size"), "rootfs artifact size"),
        package_manifest_sha256=_require_sha256(
            raw.get("package_manifest_sha256"), "rootfs package manifest"
        ),
        package_count=_require_positive_int(raw.get("package_count"), "rootfs package count"),
        reproducible=True,
    )


def load_rootfs_artifact_evidence(path: Path) -> RootfsArtifactEvidence:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RootfsError(f"cannot read rootfs artifact evidence: {exc}") from exc
    return rootfs_artifact_evidence_from_dict(raw)


def canonicalization_evidence_from_dict(raw: Any) -> RootfsCanonicalizationEvidence:
    required = {
        "schema_version",
        "input_sha256",
        "input_size",
        "output_sha256",
        "output_size",
        "member_count_input",
        "member_count_output",
        "normalized_mtime_count",
        "zeroed_volatile_files",
        "locked_password_entries",
        "dropped_cache_entries",
        "archive_prefix",
        "beta_gate_credit",
    }
    if not isinstance(raw, dict) or set(raw) != required or raw.get("schema_version") != 1:
        raise RootfsError("invalid rootfs canonicalization evidence schema")
    if raw.get("beta_gate_credit") is not False:
        raise RootfsError("rootfs canonicalization evidence cannot claim Beta credit")
    prefix = raw.get("archive_prefix")
    if not isinstance(prefix, str) or "/" in prefix or prefix in {".", ".."}:
        raise RootfsError("rootfs canonicalization evidence has invalid archive prefix")
    result = RootfsCanonicalizationEvidence(
        schema_version=1,
        input_sha256=_require_sha256(raw.get("input_sha256"), "raw rootfs input"),
        input_size=_require_positive_int(raw.get("input_size"), "raw rootfs input size"),
        output_sha256=_require_sha256(raw.get("output_sha256"), "canonical rootfs output"),
        output_size=_require_positive_int(raw.get("output_size"), "canonical rootfs output size"),
        member_count_input=_require_positive_int(raw.get("member_count_input"), "rootfs input member count"),
        member_count_output=_require_positive_int(raw.get("member_count_output"), "rootfs output member count"),
        normalized_mtime_count=_require_nonnegative_int(
            raw.get("normalized_mtime_count"), "normalized rootfs mtime count"
        ),
        zeroed_volatile_files=_require_nonnegative_int(
            raw.get("zeroed_volatile_files"), "zeroed rootfs volatile-file count"
        ),
        locked_password_entries=_require_nonnegative_int(
            raw.get("locked_password_entries"), "locked rootfs password-entry count"
        ),
        dropped_cache_entries=_require_nonnegative_int(
            raw.get("dropped_cache_entries"), "dropped rootfs cache-entry count"
        ),
        archive_prefix=prefix,
        beta_gate_credit=False,
    )
    if result.member_count_output > result.member_count_input:
        raise RootfsError("canonical rootfs cannot contain more members than its input")
    if result.member_count_input - result.member_count_output != result.dropped_cache_entries:
        raise RootfsError("rootfs canonicalization member accounting mismatch")
    return result


def load_canonicalization_evidence(path: Path) -> RootfsCanonicalizationEvidence:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RootfsError(f"cannot read rootfs canonicalization evidence: {exc}") from exc
    return canonicalization_evidence_from_dict(raw)


def _verify_pair_shape(
    first: RootfsCanonicalizationEvidence,
    second: RootfsCanonicalizationEvidence,
) -> None:
    if first.schema_version != 1 or second.schema_version != 1:
        raise RootfsError("unsupported rootfs canonicalization evidence schema")
    if first.beta_gate_credit is not False or second.beta_gate_credit is not False:
        raise RootfsError("canonicalization audit evidence cannot claim hardware/Beta credit")
    if first.archive_prefix != second.archive_prefix:
        raise RootfsError("independent rootfs canonicalization records disagree on archive prefix")
    for field in (
        "member_count_input",
        "member_count_output",
        "zeroed_volatile_files",
        "locked_password_entries",
        "dropped_cache_entries",
    ):
        if getattr(first, field) != getattr(second, field):
            raise RootfsError(f"independent rootfs canonicalization records disagree on {field}")


def create_rootfs_canonicalization_binding(
    lock: RootfsSourceLock,
    snapshot: RepositorySnapshotEvidence,
    rootfs_evidence: RootfsArtifactEvidence,
    *,
    artifact: Path,
    canonical_a: RootfsCanonicalizationEvidence,
    canonical_b: RootfsCanonicalizationEvidence,
) -> RootfsCanonicalizationBindingEvidence:
    """Bind both raw-build transformation records to the accepted strict artifact."""
    verify_rootfs_artifact(lock, snapshot, rootfs_evidence, artifact=artifact)
    _verify_pair_shape(canonical_a, canonical_b)

    for item, label in ((canonical_a, "A"), (canonical_b, "B")):
        if item.output_sha256 != rootfs_evidence.artifact_sha256:
            raise RootfsError(f"canonical rootfs {label} output hash is not the accepted artifact")
        if item.output_size != rootfs_evidence.artifact_size:
            raise RootfsError(f"canonical rootfs {label} output size is not the accepted artifact")
        _require_sha256(item.evidence_sha256(), f"canonical rootfs {label} evidence")

    return RootfsCanonicalizationBindingEvidence(
        schema_version=1,
        rootfs_evidence_sha256=rootfs_evidence.evidence_sha256(),
        source_lock_sha256=rootfs_evidence.source_lock_sha256,
        repository_snapshot_sha256=rootfs_evidence.repository_snapshot_sha256,
        canonicalization_policy_sha256=canonicalization_policy_sha256(),
        canonicalization_a_evidence_sha256=canonical_a.evidence_sha256(),
        canonicalization_b_evidence_sha256=canonical_b.evidence_sha256(),
        raw_a_sha256=canonical_a.input_sha256,
        raw_a_size=canonical_a.input_size,
        raw_b_sha256=canonical_b.input_sha256,
        raw_b_size=canonical_b.input_size,
        artifact_sha256=rootfs_evidence.artifact_sha256,
        artifact_size=rootfs_evidence.artifact_size,
        package_manifest_sha256=rootfs_evidence.package_manifest_sha256,
        package_count=rootfs_evidence.package_count,
        strict_byte_identical=True,
        beta_gate_credit=False,
    )


def verify_rootfs_canonicalization_binding(
    binding: RootfsCanonicalizationBindingEvidence,
    lock: RootfsSourceLock,
    snapshot: RepositorySnapshotEvidence,
    rootfs_evidence: RootfsArtifactEvidence,
    *,
    artifact: Path,
    canonical_a: RootfsCanonicalizationEvidence,
    canonical_b: RootfsCanonicalizationEvidence,
) -> None:
    if binding.schema_version != 1:
        raise RootfsError("unsupported rootfs canonicalization binding schema")
    if binding.beta_gate_credit is not False:
        raise RootfsError("rootfs canonicalization binding cannot claim Beta credit")
    expected = create_rootfs_canonicalization_binding(
        lock,
        snapshot,
        rootfs_evidence,
        artifact=artifact,
        canonical_a=canonical_a,
        canonical_b=canonical_b,
    )
    if binding != expected:
        raise RootfsError("rootfs canonicalization binding does not match current evidence/policy")


def write_rootfs_canonicalization_binding(
    evidence: RootfsCanonicalizationBindingEvidence,
    destination: Path,
) -> str:
    if evidence.schema_version != 1 or evidence.beta_gate_credit is not False:
        raise RootfsError("invalid rootfs canonicalization binding evidence")
    if evidence.canonicalization_policy_sha256 != canonicalization_policy_sha256():
        raise RootfsError("rootfs canonicalization binding uses an unknown policy")
    if destination.exists():
        raise RootfsError("refusing to overwrite rootfs canonicalization binding evidence")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists():
        raise RootfsError("refusing stale rootfs canonicalization binding temporary file")
    try:
        temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()
