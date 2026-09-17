"""Reviewed authority records for strictly reproducible host-built kernels.

A kernel authority record is an immutable review decision over an already
successful, source-locked A/B kernel reproducibility evidence chain.  It is not
hardware evidence: even an accepted record must keep ``hardware_verified`` and
``beta_gate_credit`` false until the physical device gate is satisfied.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from .kernel_build_binding import (
    KernelReproducibilityBindingEvidence,
    bind_kernel_reproducibility_to_build_runs,
    load_kernel_build_run_evidence,
    load_kernel_reproducibility_evidence,
)
from .kernel_build_runner import KernelBuildRunEvidence
from .kernel_contract import KernelBuildPlan, KernelContractError
from .kernel_repro import KernelReproducibilityEvidence
from .kernel_toolchain import KernelToolchainLock


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_AUTHORITY_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
_PROFILE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*$")


@dataclass(frozen=True)
class KernelAuthorityRecord:
    schema_version: int
    authority_name: str
    authority_run_id: int
    authority_commit: str
    authority_artifact_id: int
    profile_id: str
    source_commit: str
    kernel_plan_sha256: str
    toolchain_lock_sha256: str
    build_recipe_sha256: str
    reproducible_environment_sha256: str
    build_a_run_evidence_sha256: str
    build_b_run_evidence_sha256: str
    reproducibility_evidence_sha256: str
    reproducibility_binding_sha256: str
    config_sha256: str
    config_size: int
    image_sha256: str
    image_size: int
    strict_byte_identical: bool
    distinct_build_roots_verified: bool
    reviewed: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def authority_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


_REQUIRED_FIELDS = set(KernelAuthorityRecord.__dataclass_fields__)


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise KernelContractError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _positive_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise KernelContractError(f"{label} must be a positive integer")
    return value


def authority_from_dict(raw: Any) -> KernelAuthorityRecord:
    if not isinstance(raw, dict) or set(raw) != _REQUIRED_FIELDS:
        raise KernelContractError("invalid kernel authority record fields")
    if raw.get("schema_version") != 1:
        raise KernelContractError("unsupported kernel authority schema")

    name = raw.get("authority_name")
    if not isinstance(name, str) or not _AUTHORITY_NAME_RE.fullmatch(name):
        raise KernelContractError("invalid kernel authority name")
    authority_commit = raw.get("authority_commit")
    if not isinstance(authority_commit, str) or not _COMMIT_RE.fullmatch(authority_commit):
        raise KernelContractError("kernel authority commit must be a full 40-hex commit")
    source_commit = raw.get("source_commit")
    if not isinstance(source_commit, str) or not _COMMIT_RE.fullmatch(source_commit):
        raise KernelContractError("kernel source commit must be a full 40-hex commit")
    profile_id = raw.get("profile_id")
    if not isinstance(profile_id, str) or not _PROFILE_ID_RE.fullmatch(profile_id):
        raise KernelContractError("invalid kernel authority profile_id")

    if raw.get("strict_byte_identical") is not True:
        raise KernelContractError("kernel authority requires strict byte-identical A/B evidence")
    if raw.get("distinct_build_roots_verified") is not True:
        raise KernelContractError("kernel authority requires independently verified build roots")
    if raw.get("reviewed") is not True:
        raise KernelContractError("kernel authority must record an explicit completed review")
    if raw.get("hardware_verified") is not False:
        raise KernelContractError("host kernel authority cannot claim hardware verification")
    if raw.get("beta_gate_credit") is not False:
        raise KernelContractError("host kernel authority cannot claim Beta-gate credit")

    digest_fields = (
        "kernel_plan_sha256",
        "toolchain_lock_sha256",
        "build_recipe_sha256",
        "reproducible_environment_sha256",
        "build_a_run_evidence_sha256",
        "build_b_run_evidence_sha256",
        "reproducibility_evidence_sha256",
        "reproducibility_binding_sha256",
        "config_sha256",
        "image_sha256",
    )
    digests = {field: _sha256(raw.get(field), field) for field in digest_fields}

    return KernelAuthorityRecord(
        schema_version=1,
        authority_name=name,
        authority_run_id=_positive_int(raw.get("authority_run_id"), "kernel authority run id"),
        authority_commit=authority_commit,
        authority_artifact_id=_positive_int(raw.get("authority_artifact_id"), "kernel authority artifact id"),
        profile_id=profile_id,
        source_commit=source_commit,
        kernel_plan_sha256=digests["kernel_plan_sha256"],
        toolchain_lock_sha256=digests["toolchain_lock_sha256"],
        build_recipe_sha256=digests["build_recipe_sha256"],
        reproducible_environment_sha256=digests["reproducible_environment_sha256"],
        build_a_run_evidence_sha256=digests["build_a_run_evidence_sha256"],
        build_b_run_evidence_sha256=digests["build_b_run_evidence_sha256"],
        reproducibility_evidence_sha256=digests["reproducibility_evidence_sha256"],
        reproducibility_binding_sha256=digests["reproducibility_binding_sha256"],
        config_sha256=digests["config_sha256"],
        config_size=_positive_int(raw.get("config_size"), "kernel authority config size"),
        image_sha256=digests["image_sha256"],
        image_size=_positive_int(raw.get("image_size"), "kernel authority Image size"),
        strict_byte_identical=True,
        distinct_build_roots_verified=True,
        reviewed=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def load_kernel_authority(path: Path) -> KernelAuthorityRecord:
    if path.is_symlink() or not path.is_file():
        raise KernelContractError("kernel authority record must be a regular non-symlink JSON file")
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise KernelContractError("cannot read kernel authority record") from exc
    if len(raw_bytes) > 128 * 1024:
        raise KernelContractError("kernel authority record is unexpectedly large")
    try:
        raw = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KernelContractError("kernel authority record is not valid UTF-8 JSON") from exc
    return authority_from_dict(raw)


def verify_kernel_authority(
    authority: KernelAuthorityRecord,
    plan: KernelBuildPlan,
    lock: KernelToolchainLock,
    reproducibility: KernelReproducibilityEvidence,
    binding: KernelReproducibilityBindingEvidence,
    build_a: KernelBuildRunEvidence,
    build_b: KernelBuildRunEvidence,
) -> None:
    """Reconstruct the strict evidence chain and match the reviewed authority."""
    authority = authority_from_dict(asdict(authority))
    if plan.schema_version != 1 or lock.schema_version != 1:
        raise KernelContractError("unsupported kernel plan or toolchain lock schema")

    regenerated = bind_kernel_reproducibility_to_build_runs(
        plan,
        lock,
        reproducibility,
        build_a,
        build_b,
    )
    if binding.canonical_json() != regenerated.canonical_json():
        raise KernelContractError("kernel authority binding does not match reconstructed build chain")

    exact = {
        "profile_id": plan.profile_id,
        "source_commit": plan.source_commit,
        "kernel_plan_sha256": plan.plan_sha256(),
        "toolchain_lock_sha256": lock.lock_sha256(),
        "build_recipe_sha256": regenerated.build_recipe_sha256,
        "reproducible_environment_sha256": regenerated.reproducible_environment_sha256,
        "build_a_run_evidence_sha256": build_a.evidence_sha256(),
        "build_b_run_evidence_sha256": build_b.evidence_sha256(),
        "reproducibility_evidence_sha256": reproducibility.evidence_sha256(),
        "reproducibility_binding_sha256": regenerated.evidence_sha256(),
        "config_sha256": reproducibility.config_sha256,
        "config_size": reproducibility.config_size,
        "image_sha256": reproducibility.image_sha256,
        "image_size": reproducibility.image_size,
    }
    for field, expected in exact.items():
        if getattr(authority, field) != expected:
            raise KernelContractError(f"kernel authority evidence mismatch: {field}")

    if reproducibility.byte_identical is not True or regenerated.byte_identical is not True:
        raise KernelContractError("kernel authority evidence is not strict byte-identical")
    if (
        reproducibility.distinct_build_roots_verified is not True
        or regenerated.distinct_build_roots_verified is not True
    ):
        raise KernelContractError("kernel authority evidence lacks independent build-root proof")
    if reproducibility.beta_gate_credit is not False or regenerated.beta_gate_credit is not False:
        raise KernelContractError("kernel authority evidence cannot claim Beta-gate credit")


def build_reviewed_kernel_authority(
    *,
    authority_name: str,
    authority_run_id: int,
    authority_commit: str,
    authority_artifact_id: int,
    plan: KernelBuildPlan,
    lock: KernelToolchainLock,
    reproducibility: KernelReproducibilityEvidence,
    binding: KernelReproducibilityBindingEvidence,
    build_a: KernelBuildRunEvidence,
    build_b: KernelBuildRunEvidence,
    reviewed: bool,
) -> KernelAuthorityRecord:
    """Create a host authority only after an explicit completed evidence review."""
    if reviewed is not True:
        raise KernelContractError("kernel authority creation requires reviewed=True")
    regenerated = bind_kernel_reproducibility_to_build_runs(
        plan,
        lock,
        reproducibility,
        build_a,
        build_b,
    )
    if binding.canonical_json() != regenerated.canonical_json():
        raise KernelContractError("cannot authorize a detached kernel reproducibility binding")
    raw = {
        "schema_version": 1,
        "authority_name": authority_name,
        "authority_run_id": authority_run_id,
        "authority_commit": authority_commit,
        "authority_artifact_id": authority_artifact_id,
        "profile_id": plan.profile_id,
        "source_commit": plan.source_commit,
        "kernel_plan_sha256": plan.plan_sha256(),
        "toolchain_lock_sha256": lock.lock_sha256(),
        "build_recipe_sha256": regenerated.build_recipe_sha256,
        "reproducible_environment_sha256": regenerated.reproducible_environment_sha256,
        "build_a_run_evidence_sha256": build_a.evidence_sha256(),
        "build_b_run_evidence_sha256": build_b.evidence_sha256(),
        "reproducibility_evidence_sha256": reproducibility.evidence_sha256(),
        "reproducibility_binding_sha256": regenerated.evidence_sha256(),
        "config_sha256": reproducibility.config_sha256,
        "config_size": reproducibility.config_size,
        "image_sha256": reproducibility.image_sha256,
        "image_size": reproducibility.image_size,
        "strict_byte_identical": True,
        "distinct_build_roots_verified": True,
        "reviewed": True,
        "hardware_verified": False,
        "beta_gate_credit": False,
    }
    authority = authority_from_dict(raw)
    verify_kernel_authority(
        authority,
        plan,
        lock,
        reproducibility,
        binding,
        build_a,
        build_b,
    )
    return authority


def write_kernel_authority(authority: KernelAuthorityRecord, destination: Path) -> str:
    authority = authority_from_dict(asdict(authority))
    if destination.exists():
        raise KernelContractError(f"refusing to overwrite existing kernel authority: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists():
        raise KernelContractError("refusing stale kernel authority temporary file")
    try:
        temporary.write_text(authority.canonical_json(), encoding="utf-8", newline="\n")
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return authority.authority_sha256()


def load_and_verify_kernel_authority(
    authority_path: Path,
    plan: KernelBuildPlan,
    lock: KernelToolchainLock,
    reproducibility_path: Path,
    binding_path: Path,
    build_a_path: Path,
    build_b_path: Path,
) -> KernelAuthorityRecord:
    authority = load_kernel_authority(authority_path)
    reproducibility = load_kernel_reproducibility_evidence(reproducibility_path)
    build_a = load_kernel_build_run_evidence(build_a_path)
    build_b = load_kernel_build_run_evidence(build_b_path)
    if binding_path.is_symlink() or not binding_path.is_file():
        raise KernelContractError("kernel reproducibility binding must be a regular JSON file")
    try:
        raw = json.loads(binding_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KernelContractError("cannot read kernel reproducibility binding") from exc
    if not isinstance(raw, dict) or set(raw) != set(KernelReproducibilityBindingEvidence.__dataclass_fields__):
        raise KernelContractError("invalid kernel reproducibility binding fields")
    try:
        binding = KernelReproducibilityBindingEvidence(**raw)
    except (TypeError, ValueError) as exc:
        raise KernelContractError("kernel reproducibility binding does not match schema") from exc
    verify_kernel_authority(authority, plan, lock, reproducibility, binding, build_a, build_b)
    return authority
