"""Execute a profile-driven, source-locked kernel build without touching a phone.

The runner deliberately separates *execution* from the existing evidence layers. It
accepts an already validated :class:`KernelBuildPlan`, exact kernel checkout and
materialized source-locked Clang tree, then runs a deterministic out-of-tree build
using argv-only subprocess calls. It emits per-build canonical evidence but never
claims hardware or Beta-gate success.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Any, Callable, Mapping

from .kernel_contract import (
    KernelBuildPlan,
    KernelContractError,
    verify_arm64_kernel_image,
    verify_generated_kernel_config,
    verify_kernel_checkout,
)
from .kernel_toolchain import (
    KernelToolchainLock,
    verify_materialized_toolchain,
)
from .kernel_toolchain_binding import bind_kernel_plan_to_toolchain


MAX_JOBS = 16
DEFAULT_STEP_TIMEOUT_SECONDS = 45 * 60
_POLICY_FRAGMENT_NAME = ".kaliphonestudio-required.config"
_CONFIG_NAME_RE = re.compile(r"^CONFIG_[A-Z0-9_]+$")
_CANONICAL_SOURCE_PREFIX = "/usr/src/kaliphonestudio-kernel"
_CANONICAL_OUTPUT_PREFIX = "/usr/src/kaliphonestudio-kernel-build"
_REPRO_ENV = {
    "KBUILD_BUILD_USER": "kaliphonestudio",
    "KBUILD_BUILD_HOST": "repro-builder",
    "KBUILD_BUILD_TIMESTAMP": "Thu Jan 1 00:00:00 UTC 1970",
    "KBUILD_BUILD_VERSION": "1",
    "SOURCE_DATE_EPOCH": "0",
    "TZ": "UTC",
    "LC_ALL": "C",
    "LANG": "C",
    # These values are evidence-bearing policy identifiers. Actual host paths are
    # translated to these canonical roots through compiler prefix-map flags below.
    "KPS_CANONICAL_SOURCE_PREFIX": _CANONICAL_SOURCE_PREFIX,
    "KPS_CANONICAL_OUTPUT_PREFIX": _CANONICAL_OUTPUT_PREFIX,
    "KPS_PATH_REMAP_POLICY": "clang-fdebug-prefix-map+fmacro-prefix-map-v1",
}


@dataclass(frozen=True)
class KernelBuildRecipe:
    schema_version: int
    profile_id: str
    kernel_plan_sha256: str
    toolchain_lock_sha256: str
    source_commit: str
    defconfig: str
    config_fragments: tuple[str, ...]
    make_flags: tuple[tuple[str, str], ...]
    image_target: str
    jobs: int
    reproducible_environment: tuple[tuple[str, str], ...]

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def recipe_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def environment_sha256(self) -> str:
        payload = json.dumps(
            dict(self.reproducible_environment), sort_keys=True, separators=(",", ":")
        ) + "\n"
        return sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class KernelBuildRunEvidence:
    schema_version: int
    profile_id: str
    kernel_plan_sha256: str
    source_commit: str
    toolchain_lock_sha256: str
    checkout_evidence_sha256: str
    toolchain_binding_evidence_sha256: str
    materialized_toolchain_evidence_sha256: str
    build_recipe_sha256: str
    reproducible_environment_sha256: str
    config_evidence_sha256: str
    config_sha256: str
    config_size: int
    image_evidence_sha256: str
    image_sha256: str
    image_size: int
    arm64_magic_verified: bool
    beta_gate_credit: bool = False

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _normalize_jobs(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1 or value > MAX_JOBS:
        raise KernelContractError(f"kernel build jobs must be an integer between 1 and {MAX_JOBS}")
    return value


def create_kernel_build_recipe(
    plan: KernelBuildPlan,
    lock: KernelToolchainLock,
    *,
    jobs: int = 2,
) -> KernelBuildRecipe:
    if plan.schema_version != 1:
        raise KernelContractError("unsupported kernel build plan schema")
    if lock.schema_version != 1:
        raise KernelContractError("unsupported kernel toolchain lock schema")
    flags = dict(plan.make_flags)
    if flags.get("ARCH") != plan.arch:
        raise KernelContractError("kernel make flags must bind ARCH to the plan architecture")
    if flags.get("LLVM") != "1":
        raise KernelContractError("kernel build runner requires profile make flag LLVM=1")
    return KernelBuildRecipe(
        schema_version=1,
        profile_id=plan.profile_id,
        kernel_plan_sha256=plan.plan_sha256(),
        toolchain_lock_sha256=lock.lock_sha256(),
        source_commit=plan.source_commit,
        defconfig=plan.defconfig,
        config_fragments=plan.config_fragments,
        make_flags=plan.make_flags,
        image_target=plan.image_name,
        jobs=_normalize_jobs(jobs),
        reproducible_environment=tuple(sorted(_REPRO_ENV.items())),
    )


def _real_dir(path: Path, label: str) -> Path:
    if not path.is_dir() or path.is_symlink():
        raise KernelContractError(f"{label} must be a real directory")
    try:
        return path.resolve(strict=True)
    except OSError as exc:
        raise KernelContractError(f"cannot resolve {label}") from exc


def _prepare_output_root(path: Path, checkout: Path, toolchain_root: Path) -> Path:
    if path.exists():
        if path.is_symlink() or not path.is_dir():
            raise KernelContractError("kernel build output root must be a real directory")
        if any(path.iterdir()):
            raise KernelContractError("kernel build output root must be empty")
    else:
        path.mkdir(parents=True, exist_ok=False)
    output = path.resolve(strict=True)
    for other, label in ((checkout, "kernel checkout"), (toolchain_root, "toolchain root")):
        if output == other or output in other.parents or other in output.parents:
            raise KernelContractError(f"kernel build output root must be independent of {label}")
    return output


def _fragment_path(checkout: Path, plan: KernelBuildPlan, fragment: str) -> Path:
    rel = PurePosixPath("arch") / plan.arch / "configs" / PurePosixPath(fragment)
    candidate = checkout.joinpath(*rel.parts)
    if candidate.is_symlink():
        raise KernelContractError(f"kernel config fragment must not be a symlink: {fragment}")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise KernelContractError(f"kernel config fragment is missing: {fragment}") from exc
    if checkout != resolved and checkout not in resolved.parents:
        raise KernelContractError(f"kernel config fragment escapes checkout: {fragment}")
    if not resolved.is_file():
        raise KernelContractError(f"kernel config fragment is not a regular file: {fragment}")
    return resolved


def _merge_script(checkout: Path) -> Path:
    candidate = checkout / "scripts" / "kconfig" / "merge_config.sh"
    if candidate.is_symlink():
        raise KernelContractError("kernel merge_config.sh must not be a symlink")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise KernelContractError("kernel merge_config.sh is missing") from exc
    if checkout != resolved and checkout not in resolved.parents:
        raise KernelContractError("kernel merge_config.sh escapes checkout")
    if not resolved.is_file():
        raise KernelContractError("kernel merge_config.sh must be a regular file")
    return resolved


def _required_config_fragment_payload(plan: KernelBuildPlan) -> str:
    """Render the plan's required CONFIG states as a deterministic Kconfig fragment."""
    lines: list[str] = []
    seen: set[str] = set()
    for name, state in plan.required_configs:
        if not isinstance(name, str) or not _CONFIG_NAME_RE.fullmatch(name):
            raise KernelContractError("kernel build plan contains invalid required CONFIG name")
        if name in seen:
            raise KernelContractError(f"kernel build plan contains duplicate required config {name}")
        seen.add(name)
        if state == "n":
            lines.append(f"# {name} is not set")
        elif state in {"y", "m"}:
            lines.append(f"{name}={state}")
        else:
            raise KernelContractError(f"kernel build plan contains unsupported required state for {name}")
    if not lines:
        raise KernelContractError("kernel build plan contains no required CONFIG policy")
    return "\n".join(lines) + "\n"


def _write_required_config_fragment(plan: KernelBuildPlan, output: Path) -> Path:
    destination = output / _POLICY_FRAGMENT_NAME
    if destination.exists() or destination.is_symlink():
        raise KernelContractError("refusing to overwrite kernel required-config policy fragment")
    destination.write_text(
        _required_config_fragment_payload(plan),
        encoding="utf-8",
        newline="\n",
    )
    return destination


def _path_remap_flags(checkout: Path, output: Path) -> str:
    """Map per-run absolute roots out of compiler debug and macro payloads.

    The first real A/B kernel build produced an identical final .config and equal
    Image sizes but different Image bytes. The selected defconfig enables
    CONFIG_DEBUG_INFO, and A/B intentionally use different absolute source/output
    roots. Clang's debug/macro prefix maps remove those host-local path identities
    while preserving source-relative paths and all executable semantics.
    """
    mappings = (
        (checkout, _CANONICAL_SOURCE_PREFIX),
        (output, _CANONICAL_OUTPUT_PREFIX),
    )
    flags: list[str] = []
    for source, canonical in mappings:
        raw = str(source)
        if not raw.startswith("/") or not canonical.startswith("/"):
            raise KernelContractError("kernel reproducibility path map requires absolute paths")
        flags.append(f"-fdebug-prefix-map={raw}={canonical}")
        flags.append(f"-fmacro-prefix-map={raw}={canonical}")
    return " ".join(flags)


def _make_argv(
    checkout: Path,
    output: Path,
    recipe: KernelBuildRecipe,
    target: str,
    *,
    parallel: bool,
) -> list[str]:
    argv = ["make", "-C", str(checkout), f"O={output}"]
    argv.extend(f"{key}={value}" for key, value in recipe.make_flags)
    path_flags = _path_remap_flags(checkout, output)
    argv.extend(
        [
            "KBUILD_ABS_SRCTREE=0",
            f"KCFLAGS={path_flags}",
            f"KAFLAGS={path_flags}",
        ]
    )
    if parallel:
        argv.append(f"-j{recipe.jobs}")
    argv.append(target)
    return argv


def _execution_env(
    toolchain_root: Path,
    recipe: KernelBuildRecipe,
    base_env: Mapping[str, str] | None,
) -> dict[str, str]:
    env = dict(os.environ if base_env is None else base_env)
    tool_bin = toolchain_root / "bin"
    if not tool_bin.is_dir() or tool_bin.is_symlink():
        raise KernelContractError("locked toolchain bin directory is missing or unsafe")
    prior = env.get("PATH", "")
    env["PATH"] = str(tool_bin) if not prior else f"{tool_bin}{os.pathsep}{prior}"
    env.update(dict(recipe.reproducible_environment))
    return env


def _run_checked(
    runner: Callable[..., Any],
    argv: list[str],
    *,
    env: Mapping[str, str],
    timeout: int,
) -> None:
    try:
        runner(
            argv,
            check=True,
            shell=False,
            env=dict(env),
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise KernelContractError(f"kernel build command failed: {argv[0]} ...") from exc


def execute_kernel_build(
    plan: KernelBuildPlan,
    lock: KernelToolchainLock,
    *,
    checkout: Path,
    toolchain_root: Path,
    output_root: Path,
    jobs: int = 2,
    build_config_relative: str = "build.config.common",
    runner: Callable[..., Any] = subprocess.run,
    base_env: Mapping[str, str] | None = None,
    step_timeout_seconds: int = DEFAULT_STEP_TIMEOUT_SECONDS,
) -> KernelBuildRunEvidence:
    """Run one exact-source, out-of-tree kernel build and emit canonical evidence.

    The function never invokes ADB/Fastboot and never writes phone storage. The
    output directory must be empty and independent from both the source checkout
    and toolchain root. Commands are passed as argv arrays with ``shell=False``.

    After upstream defconfig/fragments are loaded, the runner applies a generated,
    deterministic fragment containing the profile's exact ``required_configs``.
    The source checkout is never mutated. Compiler macro/debug paths are remapped
    from independent A/B host directories to fixed virtual roots before building.
    """
    if not isinstance(step_timeout_seconds, int) or isinstance(step_timeout_seconds, bool) or step_timeout_seconds < 60:
        raise KernelContractError("kernel build step timeout must be an integer >= 60 seconds")

    source = _real_dir(checkout, "kernel checkout")
    toolchain = _real_dir(toolchain_root, "toolchain root")
    recipe = create_kernel_build_recipe(plan, lock, jobs=jobs)

    checkout_evidence = verify_kernel_checkout(plan, source)
    binding_evidence = bind_kernel_plan_to_toolchain(
        plan,
        lock,
        source,
        build_config_relative=build_config_relative,
    )
    materialized_evidence = verify_materialized_toolchain(lock, toolchain)

    output = _prepare_output_root(output_root, source, toolchain)
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
            str(output / ".config"),
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
    config_evidence = verify_generated_kernel_config(plan, output / ".config")

    _run_checked(
        runner,
        _make_argv(source, output, recipe, recipe.image_target, parallel=True),
        env=env,
        timeout=step_timeout_seconds,
    )
    image_path = output / "arch" / plan.arch / "boot" / plan.image_name
    image_evidence = verify_arm64_kernel_image(plan, image_path)

    return KernelBuildRunEvidence(
        schema_version=1,
        profile_id=plan.profile_id,
        kernel_plan_sha256=plan.plan_sha256(),
        source_commit=plan.source_commit,
        toolchain_lock_sha256=lock.lock_sha256(),
        checkout_evidence_sha256=checkout_evidence.evidence_sha256(),
        toolchain_binding_evidence_sha256=binding_evidence.evidence_sha256(),
        materialized_toolchain_evidence_sha256=materialized_evidence.evidence_sha256(),
        build_recipe_sha256=recipe.recipe_sha256(),
        reproducible_environment_sha256=recipe.environment_sha256(),
        config_evidence_sha256=config_evidence.evidence_sha256(),
        config_sha256=config_evidence.config_sha256,
        config_size=config_evidence.config_size,
        image_evidence_sha256=image_evidence.evidence_sha256(),
        image_sha256=image_evidence.image_sha256,
        image_size=image_evidence.image_size,
        arm64_magic_verified=image_evidence.arm64_magic_verified,
        beta_gate_credit=False,
    )


def write_kernel_build_run_evidence(evidence: KernelBuildRunEvidence, destination: Path) -> str:
    if evidence.schema_version != 1:
        raise KernelContractError("unsupported kernel build-run evidence schema")
    if evidence.arm64_magic_verified is not True:
        raise KernelContractError("refusing to persist kernel build evidence without ARM64 Image verification")
    if evidence.beta_gate_credit is not False:
        raise KernelContractError("host kernel build evidence cannot claim Beta hardware credit")
    if destination.exists():
        raise KernelContractError(f"refusing to overwrite existing evidence: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists():
        raise KernelContractError("refusing to overwrite stale kernel build evidence temporary file")
    try:
        temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return evidence.evidence_sha256()
