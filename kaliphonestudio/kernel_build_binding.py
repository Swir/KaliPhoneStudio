"""Bind strict kernel reproducibility evidence to exact executed build runs.

The existing reproducibility verifier proves that two output trees contain
byte-identical, profile-valid ``.config`` and ARM64 ``Image`` files. This module
closes the provenance gap between those output bytes and the executor: both
per-build run records must point at the same kernel plan, source commit,
toolchain lock, deterministic recipe/environment and final artifacts.
Host-side evidence from this module can never grant hardware/Beta credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping, TypeVar

from .kernel_build_runner import KernelBuildRunEvidence
from .kernel_contract import KernelBuildPlan, KernelContractError
from .kernel_repro import KernelReproducibilityEvidence
from .kernel_toolchain import KernelToolchainLock


T = TypeVar("T")
_HEX64 = set("0123456789abcdef")


@dataclass(frozen=True)
class KernelReproducibilityBindingEvidence:
    schema_version: int
    profile_id: str
    kernel_plan_sha256: str
    source_commit: str
    toolchain_lock_sha256: str
    build_recipe_sha256: str
    reproducible_environment_sha256: str
    build_a_run_evidence_sha256: str
    build_b_run_evidence_sha256: str
    reproducibility_evidence_sha256: str
    config_sha256: str
    config_size: int
    image_sha256: str
    image_size: int
    byte_identical: bool
    distinct_build_roots_verified: bool
    beta_gate_credit: bool = False

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _require_sha256(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in _HEX64 for ch in value):
        raise KernelContractError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _load_dataclass(path: Path, cls: type[T], label: str) -> T:
    if not path.is_file() or path.is_symlink():
        raise KernelContractError(f"{label} must be a real regular JSON file")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise KernelContractError(f"cannot read {label}") from exc
    if len(raw) > 128 * 1024:
        raise KernelContractError(f"{label} is unexpectedly large")
    try:
        data: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KernelContractError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(data, Mapping):
        raise KernelContractError(f"{label} must contain a JSON object")
    expected = {item.name for item in fields(cls)}
    actual = set(data)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise KernelContractError(f"{label} fields mismatch; missing={missing}, extra={extra}")
    try:
        return cls(**data)
    except (TypeError, ValueError) as exc:
        raise KernelContractError(f"{label} does not match its evidence schema") from exc


def load_kernel_build_run_evidence(path: Path) -> KernelBuildRunEvidence:
    evidence = _load_dataclass(path, KernelBuildRunEvidence, "kernel build-run evidence")
    _validate_build_run_shape(evidence, "kernel build-run evidence")
    return evidence


def load_kernel_reproducibility_evidence(path: Path) -> KernelReproducibilityEvidence:
    evidence = _load_dataclass(path, KernelReproducibilityEvidence, "kernel reproducibility evidence")
    _validate_repro_shape(evidence)
    return evidence


def _validate_build_run_shape(evidence: KernelBuildRunEvidence, label: str) -> None:
    if evidence.schema_version != 1:
        raise KernelContractError(f"{label} has unsupported schema")
    for name in (
        "kernel_plan_sha256",
        "toolchain_lock_sha256",
        "checkout_evidence_sha256",
        "toolchain_binding_evidence_sha256",
        "materialized_toolchain_evidence_sha256",
        "build_recipe_sha256",
        "reproducible_environment_sha256",
        "config_evidence_sha256",
        "config_sha256",
        "image_evidence_sha256",
        "image_sha256",
    ):
        _require_sha256(getattr(evidence, name), f"{label} {name}")
    if evidence.config_size <= 0 or evidence.image_size <= 0:
        raise KernelContractError(f"{label} contains invalid artifact sizes")
    if evidence.arm64_magic_verified is not True:
        raise KernelContractError(f"{label} does not prove ARM64 Image magic")
    if evidence.beta_gate_credit is not False:
        raise KernelContractError(f"{label} cannot claim hardware/Beta credit")


def _validate_repro_shape(evidence: KernelReproducibilityEvidence) -> None:
    if evidence.schema_version != 1:
        raise KernelContractError("kernel reproducibility evidence has unsupported schema")
    for name in (
        "kernel_plan_sha256",
        "config_sha256",
        "image_sha256",
        "build_a_config_evidence_sha256",
        "build_b_config_evidence_sha256",
        "build_a_image_evidence_sha256",
        "build_b_image_evidence_sha256",
    ):
        _require_sha256(getattr(evidence, name), f"kernel reproducibility {name}")
    if evidence.config_size <= 0 or evidence.image_size <= 0:
        raise KernelContractError("kernel reproducibility evidence has invalid artifact sizes")
    if evidence.distinct_build_roots_verified is not True or evidence.byte_identical is not True:
        raise KernelContractError("kernel reproducibility evidence is incomplete")
    if evidence.beta_gate_credit is not False:
        raise KernelContractError("kernel reproducibility evidence cannot claim hardware/Beta credit")


def bind_kernel_reproducibility_to_build_runs(
    plan: KernelBuildPlan,
    lock: KernelToolchainLock,
    reproducibility: KernelReproducibilityEvidence,
    build_a: KernelBuildRunEvidence,
    build_b: KernelBuildRunEvidence,
) -> KernelReproducibilityBindingEvidence:
    """Require the strict A/B result to come from one locked build recipe."""
    if plan.schema_version != 1 or lock.schema_version != 1:
        raise KernelContractError("unsupported kernel plan or toolchain lock schema")
    _validate_repro_shape(reproducibility)
    _validate_build_run_shape(build_a, "build A run evidence")
    _validate_build_run_shape(build_b, "build B run evidence")

    plan_digest = plan.plan_sha256()
    lock_digest = lock.lock_sha256()
    for label, run in (("build A", build_a), ("build B", build_b)):
        if run.profile_id != plan.profile_id:
            raise KernelContractError(f"{label} profile does not match kernel plan")
        if run.kernel_plan_sha256 != plan_digest:
            raise KernelContractError(f"{label} is not bound to the exact kernel plan")
        if run.source_commit != plan.source_commit:
            raise KernelContractError(f"{label} source commit does not match kernel plan")
        if run.toolchain_lock_sha256 != lock_digest:
            raise KernelContractError(f"{label} toolchain lock does not match the approved lock")

    if reproducibility.profile_id != plan.profile_id:
        raise KernelContractError("reproducibility profile does not match kernel plan")
    if reproducibility.kernel_plan_sha256 != plan_digest:
        raise KernelContractError("reproducibility evidence is not bound to the exact kernel plan")
    if reproducibility.source_commit != plan.source_commit:
        raise KernelContractError("reproducibility source commit does not match kernel plan")
    if reproducibility.kernel_version != plan.expected_kernel_version:
        raise KernelContractError("reproducibility kernel version does not match kernel plan")

    if build_a.build_recipe_sha256 != build_b.build_recipe_sha256:
        raise KernelContractError("independent builds used different canonical build recipes")
    if build_a.reproducible_environment_sha256 != build_b.reproducible_environment_sha256:
        raise KernelContractError("independent builds used different reproducibility environments")

    for label, run in (("build A", build_a), ("build B", build_b)):
        if run.config_sha256 != reproducibility.config_sha256 or run.config_size != reproducibility.config_size:
            raise KernelContractError(f"{label} final config does not match reproducibility evidence")
        if run.image_sha256 != reproducibility.image_sha256 or run.image_size != reproducibility.image_size:
            raise KernelContractError(f"{label} Image does not match reproducibility evidence")

    return KernelReproducibilityBindingEvidence(
        schema_version=1,
        profile_id=plan.profile_id,
        kernel_plan_sha256=plan_digest,
        source_commit=plan.source_commit,
        toolchain_lock_sha256=lock_digest,
        build_recipe_sha256=build_a.build_recipe_sha256,
        reproducible_environment_sha256=build_a.reproducible_environment_sha256,
        build_a_run_evidence_sha256=build_a.evidence_sha256(),
        build_b_run_evidence_sha256=build_b.evidence_sha256(),
        reproducibility_evidence_sha256=reproducibility.evidence_sha256(),
        config_sha256=reproducibility.config_sha256,
        config_size=reproducibility.config_size,
        image_sha256=reproducibility.image_sha256,
        image_size=reproducibility.image_size,
        byte_identical=True,
        distinct_build_roots_verified=True,
        beta_gate_credit=False,
    )


def write_kernel_reproducibility_binding_evidence(
    evidence: KernelReproducibilityBindingEvidence,
    destination: Path,
) -> str:
    if evidence.schema_version != 1:
        raise KernelContractError("unsupported kernel reproducibility binding schema")
    if evidence.byte_identical is not True or evidence.distinct_build_roots_verified is not True:
        raise KernelContractError("refusing incomplete kernel reproducibility binding evidence")
    if evidence.beta_gate_credit is not False:
        raise KernelContractError("host kernel binding evidence cannot claim hardware/Beta credit")
    if destination.exists():
        raise KernelContractError(f"refusing to overwrite existing evidence: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists():
        raise KernelContractError("refusing stale kernel binding evidence temporary file")
    try:
        temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return evidence.evidence_sha256()
