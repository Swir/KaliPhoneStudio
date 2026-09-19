"""Fail-closed A/B reproducibility candidate evidence for Phosh ARM64 rootfs builds.

This module compares two independently produced host-side Phosh build-evidence files.
It can prove that their canonical rootfs and package-manifest identities are identical,
but it deliberately does not create a reviewed reproducibility authority and never
grants hardware or Beta credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_ORIGIN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:@+-]{0,191}$")

_BUILD_FIELDS = {
    "schema_version",
    "upstream_commit",
    "source_lock_sha256",
    "build_contract_sha256",
    "build_plan_sha256",
    "artifact_sha256",
    "artifact_size",
    "package_manifest_sha256",
    "package_count",
    "phosh_package_contract_satisfied",
    "reproducibility_authority",
    "physical_validation_required",
    "hardware_verified",
    "beta_gate_credit",
}


class PhoshReproducibilityError(ValueError):
    """Raised when Phosh A/B evidence is malformed, detached or non-reproducible."""


@dataclass(frozen=True)
class PhoshRootfsReproducibilityCandidate:
    schema_version: int
    upstream_commit: str
    source_lock_sha256: str
    build_contract_sha256: str
    build_plan_sha256: str
    build_a_origin: str
    build_b_origin: str
    build_a_evidence_sha256: str
    build_b_evidence_sha256: str
    artifact_sha256: str
    artifact_size: int
    package_manifest_sha256: str
    package_count: int
    strict_byte_identical: bool
    package_manifest_identical: bool
    review_required: bool
    reproducibility_authority: bool
    physical_validation_required: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise PhoshReproducibilityError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _positive_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PhoshReproducibilityError(f"{label} must be a positive integer")
    return value


def _origin(value: str, label: str) -> str:
    if not isinstance(value, str) or not _ORIGIN_RE.fullmatch(value):
        raise PhoshReproducibilityError(f"{label} must be a bounded build-origin identifier")
    return value


def _canonical_build_payload(raw: dict[str, Any]) -> bytes:
    return (json.dumps(raw, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def load_phosh_rootfs_build_evidence(path: Path) -> tuple[dict[str, Any], str]:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise PhoshReproducibilityError("Phosh build evidence must be a regular non-symlink file")
    try:
        payload = candidate.read_bytes()
    except OSError as exc:
        raise PhoshReproducibilityError(f"cannot read Phosh build evidence: {exc}") from exc
    if not payload or len(payload) > 64 * 1024:
        raise PhoshReproducibilityError("Phosh build evidence has invalid size")
    try:
        raw = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhoshReproducibilityError(f"invalid Phosh build evidence JSON: {exc}") from exc
    if not isinstance(raw, dict) or set(raw) != _BUILD_FIELDS:
        raise PhoshReproducibilityError("unexpected Phosh build-evidence fields")
    if payload != _canonical_build_payload(raw):
        raise PhoshReproducibilityError("Phosh build evidence must use canonical JSON bytes")
    if raw.get("schema_version") != 1:
        raise PhoshReproducibilityError("unsupported Phosh build-evidence schema")
    if not isinstance(raw.get("upstream_commit"), str) or not _COMMIT_RE.fullmatch(raw["upstream_commit"]):
        raise PhoshReproducibilityError("Phosh build upstream commit must be a full 40-hex commit")
    for field in (
        "source_lock_sha256",
        "build_contract_sha256",
        "build_plan_sha256",
        "artifact_sha256",
        "package_manifest_sha256",
    ):
        _sha256(raw.get(field), field)
    _positive_int(raw.get("artifact_size"), "artifact size")
    _positive_int(raw.get("package_count"), "package count")
    if raw.get("phosh_package_contract_satisfied") is not True:
        raise PhoshReproducibilityError("Phosh build evidence did not satisfy the package contract")
    if raw.get("reproducibility_authority") is not False:
        raise PhoshReproducibilityError("single-build Phosh evidence cannot already be authoritative")
    if raw.get("physical_validation_required") is not True:
        raise PhoshReproducibilityError("Phosh build evidence must retain physical validation requirement")
    if raw.get("hardware_verified") is not False or raw.get("beta_gate_credit") is not False:
        raise PhoshReproducibilityError("host Phosh build evidence cannot grant hardware/Beta credit")
    return raw, sha256(payload).hexdigest()


def compare_phosh_rootfs_builds(
    build_a_path: Path,
    build_b_path: Path,
    *,
    build_a_origin: str,
    build_b_origin: str,
) -> PhoshRootfsReproducibilityCandidate:
    origin_a = _origin(build_a_origin, "build A origin")
    origin_b = _origin(build_b_origin, "build B origin")
    if origin_a == origin_b:
        raise PhoshReproducibilityError("Phosh A/B comparison requires distinct build origins")

    build_a, digest_a = load_phosh_rootfs_build_evidence(build_a_path)
    build_b, digest_b = load_phosh_rootfs_build_evidence(build_b_path)

    for field in (
        "upstream_commit",
        "source_lock_sha256",
        "build_contract_sha256",
        "build_plan_sha256",
    ):
        if build_a[field] != build_b[field]:
            raise PhoshReproducibilityError(f"Phosh A/B build identity mismatch: {field}")

    if (
        build_a["artifact_sha256"] != build_b["artifact_sha256"]
        or build_a["artifact_size"] != build_b["artifact_size"]
    ):
        raise PhoshReproducibilityError("Phosh A/B canonical rootfs artifacts are not byte-identical")

    if (
        build_a["package_manifest_sha256"] != build_b["package_manifest_sha256"]
        or build_a["package_count"] != build_b["package_count"]
    ):
        raise PhoshReproducibilityError("Phosh A/B package manifests are not identical")

    return PhoshRootfsReproducibilityCandidate(
        schema_version=1,
        upstream_commit=build_a["upstream_commit"],
        source_lock_sha256=build_a["source_lock_sha256"],
        build_contract_sha256=build_a["build_contract_sha256"],
        build_plan_sha256=build_a["build_plan_sha256"],
        build_a_origin=origin_a,
        build_b_origin=origin_b,
        build_a_evidence_sha256=digest_a,
        build_b_evidence_sha256=digest_b,
        artifact_sha256=build_a["artifact_sha256"],
        artifact_size=build_a["artifact_size"],
        package_manifest_sha256=build_a["package_manifest_sha256"],
        package_count=build_a["package_count"],
        strict_byte_identical=True,
        package_manifest_identical=True,
        review_required=True,
        reproducibility_authority=False,
        physical_validation_required=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def write_phosh_rootfs_reproducibility_candidate(
    evidence: PhoshRootfsReproducibilityCandidate,
    destination: Path,
) -> str:
    if not isinstance(evidence, PhoshRootfsReproducibilityCandidate):
        raise PhoshReproducibilityError("invalid Phosh reproducibility-candidate evidence type")
    if (
        evidence.schema_version != 1
        or evidence.strict_byte_identical is not True
        or evidence.package_manifest_identical is not True
        or evidence.review_required is not True
    ):
        raise PhoshReproducibilityError("Phosh reproducibility candidate is incomplete")
    if (
        evidence.reproducibility_authority is not False
        or evidence.physical_validation_required is not True
        or evidence.hardware_verified is not False
        or evidence.beta_gate_credit is not False
    ):
        raise PhoshReproducibilityError("Phosh reproducibility candidate cannot grant authority/hardware/Beta credit")

    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise PhoshReproducibilityError("refusing to overwrite Phosh reproducibility-candidate evidence")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise PhoshReproducibilityError("refusing stale Phosh reproducibility temporary file")
    try:
        temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()
