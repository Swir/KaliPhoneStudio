"""Rehydrate a reviewed kernel build root without rebuilding the kernel Image.

GitHub Actions historically omitted hidden ``.config`` files from the accepted kernel
artifact while preserving both byte-identical ARM64 Images and the full reviewed
reproducibility evidence chain. Device-tree builds need the exact final config but do
not need another expensive kernel Image build.

This module deterministically recreates only the final config from the exact pinned
source/profile/toolchain policy, verifies it against the immutable reviewed kernel
authority, and also verifies that the already-present Image bytes still match that
authority. It performs no device I/O and grants no hardware/Beta credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from typing import Any, Callable, Mapping

from .kernel_authority import KernelAuthorityRecord
from .kernel_build_runner import (
    DEFAULT_STEP_TIMEOUT_SECONDS,
    _execution_env,
    _fragment_path,
    _make_argv,
    _merge_script,
    _real_dir,
    _run_checked,
    _write_required_config_fragment,
    create_kernel_build_recipe,
)
from .kernel_contract import (
    KernelBuildPlan,
    KernelContractError,
    verify_arm64_kernel_image,
    verify_generated_kernel_config,
    verify_kernel_checkout,
)
from .kernel_toolchain import KernelToolchainLock, verify_materialized_toolchain
from .kernel_toolchain_binding import bind_kernel_plan_to_toolchain


@dataclass(frozen=True)
class ReviewedKernelBuildRootEvidence:
    schema_version: int
    profile_id: str
    kernel_plan_sha256: str
    kernel_authority_sha256: str
    source_commit: str
    toolchain_lock_sha256: str
    checkout_evidence_sha256: str
    toolchain_binding_evidence_sha256: str
    materialized_toolchain_evidence_sha256: str
    build_recipe_sha256: str
    reproducible_environment_sha256: str
    config_sha256: str
    config_size: int
    image_sha256: str
    image_size: int
    config_rehydrated: bool
    hardware_verified: bool = False
    beta_gate_credit: bool = False

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def materialize_reviewed_kernel_build_root(
    plan: KernelBuildPlan,
    lock: KernelToolchainLock,
    authority: KernelAuthorityRecord,
    *,
    checkout: Path,
    toolchain_root: Path,
    output_root: Path,
    jobs: int = 1,
    runner: Callable[..., Any] = subprocess.run,
    base_env: Mapping[str, str] | None = None,
    step_timeout_seconds: int = DEFAULT_STEP_TIMEOUT_SECONDS,
) -> ReviewedKernelBuildRootEvidence:
    """Ensure an output root has the authority-exact config and Image.

    If a future artifact already contains ``.config``, it is only verified. If it is
    absent, the exact deterministic defconfig/fragment/required-policy/olddefconfig
    sequence is replayed. The kernel Image itself is never rebuilt here.
    """
    if authority.schema_version != 1 or authority.reviewed is not True:
        raise KernelContractError("reviewed kernel build-root materialization requires a reviewed authority")
    if authority.strict_byte_identical is not True or authority.distinct_build_roots_verified is not True:
        raise KernelContractError("kernel authority is not strict/independent")
    if authority.hardware_verified is not False or authority.beta_gate_credit is not False:
        raise KernelContractError("host kernel authority cannot claim hardware/Beta credit")
    if authority.profile_id != plan.profile_id or authority.source_commit != plan.source_commit:
        raise KernelContractError("kernel authority identity/source does not match build plan")
    if authority.kernel_plan_sha256 != plan.plan_sha256():
        raise KernelContractError("kernel authority does not match build plan digest")
    if authority.toolchain_lock_sha256 != lock.lock_sha256():
        raise KernelContractError("kernel authority does not match toolchain lock")
    if not isinstance(step_timeout_seconds, int) or isinstance(step_timeout_seconds, bool) or step_timeout_seconds < 60:
        raise KernelContractError("kernel config materialization timeout must be an integer >= 60 seconds")

    source = _real_dir(Path(checkout), "kernel checkout")
    toolchain = _real_dir(Path(toolchain_root), "toolchain root")
    output = _real_dir(Path(output_root), "kernel build output")
    checkout_evidence = verify_kernel_checkout(plan, source)
    binding_evidence = bind_kernel_plan_to_toolchain(plan, lock, source)
    materialized_evidence = verify_materialized_toolchain(lock, toolchain)
    recipe = create_kernel_build_recipe(plan, lock, jobs=jobs)
    if recipe.recipe_sha256() != authority.build_recipe_sha256:
        raise KernelContractError("kernel authority build recipe does not match config materialization recipe")
    if recipe.environment_sha256() != authority.reproducible_environment_sha256:
        raise KernelContractError("kernel authority environment does not match config materialization environment")

    config_path = output / ".config"
    rehydrated = not config_path.exists()
    if rehydrated:
        env = _execution_env(toolchain, recipe, base_env)
        _run_checked(
            runner,
            _make_argv(source, output, recipe, recipe.defconfig, parallel=False),
            env=env,
            timeout=step_timeout_seconds,
        )
        merge = _merge_script(source)
        fragments = [_fragment_path(source, plan, item) for item in recipe.config_fragments]
        policy_fragment = _write_required_config_fragment(plan, output)
        _run_checked(
            runner,
            [
                "bash",
                str(merge),
                "-m",
                "-O",
                str(output),
                str(config_path),
                *[str(path) for path in fragments],
                str(policy_fragment),
            ],
            env=env,
            timeout=step_timeout_seconds,
        )
        _run_checked(
            runner,
            _make_argv(source, output, recipe, "olddefconfig", parallel=False),
            env=env,
            timeout=step_timeout_seconds,
        )

    config = verify_generated_kernel_config(plan, config_path)
    if config.config_sha256 != authority.config_sha256 or config.config_size != authority.config_size:
        raise KernelContractError("materialized config does not match reviewed kernel authority")

    image_path = output / "arch" / plan.arch / "boot" / plan.image_name
    image = verify_arm64_kernel_image(plan, image_path)
    if image.image_sha256 != authority.image_sha256 or image.image_size != authority.image_size:
        raise KernelContractError("materialized build-root Image does not match reviewed kernel authority")

    return ReviewedKernelBuildRootEvidence(
        schema_version=1,
        profile_id=plan.profile_id,
        kernel_plan_sha256=plan.plan_sha256(),
        kernel_authority_sha256=authority.authority_sha256(),
        source_commit=plan.source_commit,
        toolchain_lock_sha256=lock.lock_sha256(),
        checkout_evidence_sha256=checkout_evidence.evidence_sha256(),
        toolchain_binding_evidence_sha256=binding_evidence.evidence_sha256(),
        materialized_toolchain_evidence_sha256=materialized_evidence.evidence_sha256(),
        build_recipe_sha256=recipe.recipe_sha256(),
        reproducible_environment_sha256=recipe.environment_sha256(),
        config_sha256=config.config_sha256,
        config_size=config.config_size,
        image_sha256=image.image_sha256,
        image_size=image.image_size,
        config_rehydrated=rehydrated,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def write_reviewed_kernel_build_root_evidence(
    evidence: ReviewedKernelBuildRootEvidence,
    destination: Path,
) -> str:
    if not isinstance(evidence, ReviewedKernelBuildRootEvidence) or evidence.schema_version != 1:
        raise KernelContractError("invalid reviewed kernel build-root evidence")
    if evidence.hardware_verified is not False or evidence.beta_gate_credit is not False:
        raise KernelContractError("reviewed kernel build-root evidence cannot claim hardware/Beta credit")
    path = Path(destination)
    if path.exists():
        raise KernelContractError("refusing to overwrite reviewed kernel build-root evidence")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists():
        raise KernelContractError("refusing stale reviewed kernel build-root evidence temporary file")
    try:
        temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()
