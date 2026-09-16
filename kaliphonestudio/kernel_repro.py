"""Device-independent two-build kernel reproducibility evidence.

This module compares artifacts from two distinct build roots against the same
profile-driven :class:`KernelBuildPlan`.  It deliberately does not execute a
compiler and it never claims hardware success.  Its job is to fail closed if
an alleged reproducible kernel pair differs in final ``.config`` or ARM64
``Image`` bytes, or if either artifact does not satisfy the existing kernel
contract.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath

from .kernel_contract import (
    KernelBuildPlan,
    KernelContractError,
    verify_arm64_kernel_image,
    verify_generated_kernel_config,
)


@dataclass(frozen=True)
class KernelReproducibilityEvidence:
    schema_version: int
    profile_id: str
    kernel_plan_sha256: str
    source_commit: str
    kernel_version: str
    config_sha256: str
    config_size: int
    image_sha256: str
    image_size: int
    build_a_config_evidence_sha256: str
    build_b_config_evidence_sha256: str
    build_a_image_evidence_sha256: str
    build_b_image_evidence_sha256: str
    distinct_build_roots_verified: bool
    byte_identical: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _safe_relative_path(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KernelContractError(f"{label} must be a non-empty relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise KernelContractError(f"{label} must be a safe relative POSIX path")
    if any(not part or "\\" in part or any(ord(ch) < 0x20 for ch in part) for part in path.parts):
        raise KernelContractError(f"{label} contains unsafe path data")
    return path.as_posix()


def _resolve_build_root(path: Path, label: str) -> Path:
    if not path.is_dir() or path.is_symlink():
        raise KernelContractError(f"{label} must be a real build directory, not a symlink")
    try:
        return path.resolve(strict=True)
    except OSError as exc:
        raise KernelContractError(f"cannot resolve {label}") from exc


def _require_independent_roots(first: Path, second: Path) -> tuple[Path, Path]:
    first_resolved = _resolve_build_root(first, "build A root")
    second_resolved = _resolve_build_root(second, "build B root")
    if first_resolved == second_resolved:
        raise KernelContractError("kernel reproducibility requires two distinct build roots")
    if first_resolved in second_resolved.parents or second_resolved in first_resolved.parents:
        raise KernelContractError("kernel reproducibility build roots must not be nested")
    return first_resolved, second_resolved


def _artifact(root: Path, relative: str, label: str) -> Path:
    safe = _safe_relative_path(relative, label)
    candidate = root.joinpath(*PurePosixPath(safe).parts)
    if candidate.is_symlink():
        raise KernelContractError(f"{label} must not be a symlink")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise KernelContractError(f"{label} is missing") from exc
    if root != resolved and root not in resolved.parents:
        raise KernelContractError(f"{label} escapes its build root")
    if not resolved.is_file():
        raise KernelContractError(f"{label} must be a regular file")
    return resolved


def verify_kernel_reproducibility(
    plan: KernelBuildPlan,
    *,
    build_a: Path,
    build_b: Path,
    config_relative: str = ".config",
    image_relative: str | None = None,
) -> KernelReproducibilityEvidence:
    """Require byte-identical final config and kernel Image from distinct roots.

    The two build roots must be distinct siblings (or otherwise non-nested), and
    the final artifacts in each root are independently revalidated using the
    existing profile-driven config and ARM64 Image checks before equality is
    accepted.  Paths are never included in canonical evidence, keeping the
    evidence reproducible across hosts.
    """
    if plan.schema_version != 1:
        raise KernelContractError("unsupported kernel build plan schema")
    first_root, second_root = _require_independent_roots(build_a, build_b)
    image_relative = image_relative or f"arch/{plan.arch}/boot/{plan.image_name}"

    config_a_path = _artifact(first_root, config_relative, "build A final config")
    config_b_path = _artifact(second_root, config_relative, "build B final config")
    image_a_path = _artifact(first_root, image_relative, "build A kernel image")
    image_b_path = _artifact(second_root, image_relative, "build B kernel image")

    config_a = verify_generated_kernel_config(plan, config_a_path)
    config_b = verify_generated_kernel_config(plan, config_b_path)
    image_a = verify_arm64_kernel_image(plan, image_a_path)
    image_b = verify_arm64_kernel_image(plan, image_b_path)

    if config_a.config_sha256 != config_b.config_sha256 or config_a.config_size != config_b.config_size:
        raise KernelContractError("independent kernel builds produced different final .config bytes")
    if image_a.image_sha256 != image_b.image_sha256 or image_a.image_size != image_b.image_size:
        raise KernelContractError("independent kernel builds produced different Image bytes")

    return KernelReproducibilityEvidence(
        schema_version=1,
        profile_id=plan.profile_id,
        kernel_plan_sha256=plan.plan_sha256(),
        source_commit=plan.source_commit,
        kernel_version=plan.expected_kernel_version,
        config_sha256=config_a.config_sha256,
        config_size=config_a.config_size,
        image_sha256=image_a.image_sha256,
        image_size=image_a.image_size,
        build_a_config_evidence_sha256=config_a.evidence_sha256(),
        build_b_config_evidence_sha256=config_b.evidence_sha256(),
        build_a_image_evidence_sha256=image_a.evidence_sha256(),
        build_b_image_evidence_sha256=image_b.evidence_sha256(),
        distinct_build_roots_verified=True,
        byte_identical=True,
        beta_gate_credit=False,
    )


def write_kernel_reproducibility_evidence(
    evidence: KernelReproducibilityEvidence,
    destination: Path,
) -> str:
    if evidence.schema_version != 1:
        raise KernelContractError("unsupported kernel reproducibility evidence schema")
    if evidence.distinct_build_roots_verified is not True or evidence.byte_identical is not True:
        raise KernelContractError("refusing to persist incomplete kernel reproducibility evidence")
    if evidence.beta_gate_credit is not False:
        raise KernelContractError("host kernel reproducibility evidence cannot claim Beta hardware credit")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise KernelContractError(f"refusing to overwrite existing evidence: {destination}")
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists():
        raise KernelContractError("refusing to overwrite stale kernel reproducibility temporary file")
    try:
        temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return evidence.evidence_sha256()
