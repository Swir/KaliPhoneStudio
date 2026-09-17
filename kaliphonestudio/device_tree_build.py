"""Profile-driven host build and strict reproducibility contracts for DTB/DTBO artifacts.

The module deliberately reuses the exact reviewed kernel source/config/toolchain build
roots. It never talks to a phone and all evidence explicitly grants no hardware or
Beta credit. Device-specific output paths live in the device profile, not this core.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import struct
import subprocess
from typing import Any, Callable, Mapping

from .device_tree import (
    DeviceTreeError,
    inspect_dtb_artifact,
    inspect_dtbo_artifact,
    load_device_tree_format_locks,
)
from .kernel_authority import KernelAuthorityRecord
from .kernel_build_runner import (
    DEFAULT_STEP_TIMEOUT_SECONDS,
    _execution_env,
    _make_argv,
    _real_dir,
    _run_checked,
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
from .profiles import DeviceProfile


_SAFE_TARGET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
_MAX_OVERLAYS = 64
_MAX_RAW_FDT_BYTES = 128 * 1024 * 1024
_DT_TABLE_MAGIC = 0xD7B7AB1E
_DT_TABLE_HEADER_SIZE = 32
_DT_TABLE_ENTRY_SIZE = 32


@dataclass(frozen=True)
class DeviceTreeBuildPlan:
    schema_version: int
    profile_id: str
    kernel_plan_sha256: str
    kernel_authority_sha256: str
    source_commit: str
    build_target: str
    dtb_output: str
    dtbo_outputs: tuple[str, ...]
    dtbo_page_size: int
    dtbo_table_version: int
    format_lock_sha256: str

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def plan_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RawOverlayEvidence:
    relative_path: str
    artifact_sha256: str
    artifact_size: int
    fdt_tree_count: int
    fdt_evidence_sha256: str


@dataclass(frozen=True)
class DeviceTreeBuildRunEvidence:
    schema_version: int
    profile_id: str
    device_tree_plan_sha256: str
    kernel_authority_sha256: str
    kernel_config_sha256: str
    kernel_image_sha256: str
    dtb_relative_path: str
    dtb_sha256: str
    dtb_size: int
    dtb_tree_count: int
    dtb_evidence_sha256: str
    raw_dtbo: tuple[RawOverlayEvidence, ...]
    dtbo_image_sha256: str
    dtbo_image_size: int
    dtbo_entry_count: int
    dtbo_evidence_sha256: str
    hardware_verified: bool = False
    beta_gate_credit: bool = False

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DeviceTreeReproducibilityEvidence:
    schema_version: int
    profile_id: str
    device_tree_plan_sha256: str
    kernel_authority_sha256: str
    build_a_evidence_sha256: str
    build_b_evidence_sha256: str
    dtb_sha256: str
    dtb_size: int
    raw_dtbo: tuple[tuple[str, str, int], ...]
    dtbo_image_sha256: str
    dtbo_image_size: int
    dtbo_entry_count: int
    byte_identical: bool
    distinct_build_roots_verified: bool
    hardware_verified: bool = False
    beta_gate_credit: bool = False

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _safe_relative(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise DeviceTreeError(f"{label} must be a non-empty relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise DeviceTreeError(f"{label} must be a safe relative POSIX path")
    if any("\\" in part or any(ord(ch) < 0x20 for ch in part) for part in path.parts):
        raise DeviceTreeError(f"{label} contains unsafe path data")
    return path.as_posix()


def _plain_int(value: Any, label: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise DeviceTreeError(f"{label} must be an integer >= {minimum}")
    return value


def _align(value: int, page_size: int) -> int:
    return (value + page_size - 1) // page_size * page_size


def create_device_tree_build_plan(
    profile: DeviceProfile,
    kernel_plan: KernelBuildPlan,
    kernel_authority: KernelAuthorityRecord,
    *,
    format_lock: Path,
) -> DeviceTreeBuildPlan:
    """Create a deterministic DT build plan tied to one reviewed kernel authority."""
    contract = profile.data.get("device_tree")
    if not isinstance(contract, dict):
        raise DeviceTreeError("profile has no device_tree build contract")
    if kernel_plan.profile_id != profile.profile_id or kernel_authority.profile_id != profile.profile_id:
        raise DeviceTreeError("device-tree profile/kernel authority identity mismatch")
    if kernel_authority.source_commit != kernel_plan.source_commit:
        raise DeviceTreeError("device-tree kernel source does not match reviewed kernel authority")
    if kernel_authority.kernel_plan_sha256 != kernel_plan.plan_sha256():
        raise DeviceTreeError("device-tree kernel plan does not match reviewed kernel authority")
    if kernel_authority.reviewed is not True or kernel_authority.strict_byte_identical is not True:
        raise DeviceTreeError("device-tree build requires a reviewed strict kernel authority")
    if kernel_authority.hardware_verified is not False or kernel_authority.beta_gate_credit is not False:
        raise DeviceTreeError("host kernel authority must grant no hardware/Beta credit")

    source_name = contract.get("source_name")
    if source_name != kernel_plan.source_name:
        raise DeviceTreeError("device_tree.source_name must match the reviewed kernel source")
    target = contract.get("build_target")
    if not isinstance(target, str) or not _SAFE_TARGET_RE.fullmatch(target):
        raise DeviceTreeError("device_tree.build_target is unsafe")
    dtb_output = _safe_relative(contract.get("dtb_output"), "device_tree.dtb_output")
    raw_outputs = contract.get("dtbo_outputs")
    if not isinstance(raw_outputs, list) or not raw_outputs or len(raw_outputs) > _MAX_OVERLAYS:
        raise DeviceTreeError("device_tree.dtbo_outputs must contain 1..64 paths")
    dtbo_outputs = tuple(_safe_relative(item, "device_tree.dtbo_outputs") for item in raw_outputs)
    if len(dtbo_outputs) != len(set(dtbo_outputs)):
        raise DeviceTreeError("device_tree.dtbo_outputs must not contain duplicates")
    page_size = _plain_int(contract.get("dtbo_page_size"), "device_tree.dtbo_page_size", minimum=512)
    if page_size & (page_size - 1):
        raise DeviceTreeError("device_tree.dtbo_page_size must be a power of two")
    if page_size != profile.data["boot"]["page_size"]:
        raise DeviceTreeError("device_tree.dtbo_page_size must match boot.page_size")
    table_version = _plain_int(contract.get("dtbo_table_version"), "device_tree.dtbo_table_version")
    if table_version != 0:
        raise DeviceTreeError("only Android DT table version 0 is accepted for this profile contract")
    if profile.data["boot"].get("include_dtb") is not True:
        raise DeviceTreeError("device_tree contract requires boot.include_dtb=true")
    if profile.data["boot"].get("separate_dtbo") is not True:
        raise DeviceTreeError("device_tree contract requires boot.separate_dtbo=true")
    _locks, lock_sha = load_device_tree_format_locks(format_lock)
    return DeviceTreeBuildPlan(
        schema_version=1,
        profile_id=profile.profile_id,
        kernel_plan_sha256=kernel_plan.plan_sha256(),
        kernel_authority_sha256=kernel_authority.authority_sha256(),
        source_commit=kernel_plan.source_commit,
        build_target=target,
        dtb_output=dtb_output,
        dtbo_outputs=dtbo_outputs,
        dtbo_page_size=page_size,
        dtbo_table_version=table_version,
        format_lock_sha256=lock_sha,
    )


def _build_file(root: Path, relative: str, label: str) -> Path:
    root = root.resolve(strict=True)
    candidate = root.joinpath(*PurePosixPath(relative).parts)
    if candidate.is_symlink():
        raise DeviceTreeError(f"{label} must not be a symlink: {relative}")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise DeviceTreeError(f"missing {label}: {relative}") from exc
    if root != resolved and root not in resolved.parents:
        raise DeviceTreeError(f"{label} escapes build root: {relative}")
    if not resolved.is_file():
        raise DeviceTreeError(f"{label} is not a regular file: {relative}")
    size = resolved.stat().st_size
    if size <= 0 or size > _MAX_RAW_FDT_BYTES:
        raise DeviceTreeError(f"{label} size is outside safety bounds")
    return resolved


def pack_android_dtbo_image(
    overlays: tuple[Path, ...],
    destination: Path,
    *,
    page_size: int,
    table_version: int = 0,
) -> None:
    """Create a deterministic Android DT table image from raw overlay FDTs.

    The layout follows the version-0 table contract pinned in
    ``tools/device-tree-format-locks.json``. Entry identifiers/revisions/custom
    fields are zero because no device-specific matching metadata has been
    demonstrated for this profile yet; physical bootloader acceptance remains a
    separate hardware gate.
    """
    if table_version != 0:
        raise DeviceTreeError("only DT table version 0 is supported")
    if page_size < 512 or page_size & (page_size - 1):
        raise DeviceTreeError("DTBO page_size must be a power of two >= 512")
    if not overlays or len(overlays) > _MAX_OVERLAYS:
        raise DeviceTreeError("DTBO image requires 1..64 overlays")
    payloads: list[bytes] = []
    for index, path in enumerate(overlays):
        evidence = inspect_dtb_artifact(path)
        if evidence.tree_count != 1:
            raise DeviceTreeError(f"raw DTBO overlay {index} must contain exactly one FDT")
        payloads.append(path.read_bytes())

    entries_end = _DT_TABLE_HEADER_SIZE + _DT_TABLE_ENTRY_SIZE * len(payloads)
    cursor = _align(entries_end, page_size)
    entry_rows: list[bytes] = []
    placed: list[tuple[int, bytes]] = []
    for payload in payloads:
        entry_rows.append(struct.pack(">8I", len(payload), cursor, 0, 0, 0, 0, 0, 0))
        placed.append((cursor, payload))
        cursor = _align(cursor + len(payload), page_size)
    total_size = cursor
    header = struct.pack(
        ">8I",
        _DT_TABLE_MAGIC,
        total_size,
        _DT_TABLE_HEADER_SIZE,
        _DT_TABLE_ENTRY_SIZE,
        len(payloads),
        _DT_TABLE_HEADER_SIZE,
        page_size,
        table_version,
    )
    image = bytearray(total_size)
    image[:_DT_TABLE_HEADER_SIZE] = header
    for index, row in enumerate(entry_rows):
        start = _DT_TABLE_HEADER_SIZE + index * _DT_TABLE_ENTRY_SIZE
        image[start : start + _DT_TABLE_ENTRY_SIZE] = row
    for offset, payload in placed:
        image[offset : offset + len(payload)] = payload

    if destination.exists():
        raise DeviceTreeError("refusing to overwrite DTBO image destination")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists():
        raise DeviceTreeError("refusing stale DTBO image temporary file")
    try:
        temporary.write_bytes(bytes(image))
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    verified = inspect_dtbo_artifact(destination)
    if verified.entry_count != len(payloads) or verified.page_size != page_size:
        raise DeviceTreeError("packed DTBO image failed independent structural verification")


def execute_device_tree_build(
    profile: DeviceProfile,
    kernel_plan: KernelBuildPlan,
    lock: KernelToolchainLock,
    kernel_authority: KernelAuthorityRecord,
    device_tree_plan: DeviceTreeBuildPlan,
    *,
    checkout: Path,
    toolchain_root: Path,
    output_root: Path,
    dtbo_image: Path,
    jobs: int = 1,
    runner: Callable[..., Any] = subprocess.run,
    base_env: Mapping[str, str] | None = None,
    step_timeout_seconds: int = DEFAULT_STEP_TIMEOUT_SECONDS,
) -> DeviceTreeBuildRunEvidence:
    """Build DTBs in an already prepared exact kernel build root and verify bytes."""
    if step_timeout_seconds < 60:
        raise DeviceTreeError("device-tree build timeout must be >= 60 seconds")
    if device_tree_plan.profile_id != profile.profile_id:
        raise DeviceTreeError("device-tree plan profile mismatch")
    if device_tree_plan.kernel_plan_sha256 != kernel_plan.plan_sha256():
        raise DeviceTreeError("device-tree plan/kernel plan mismatch")
    if device_tree_plan.kernel_authority_sha256 != kernel_authority.authority_sha256():
        raise DeviceTreeError("device-tree plan/kernel authority mismatch")

    source = _real_dir(checkout, "kernel checkout")
    toolchain = _real_dir(toolchain_root, "toolchain root")
    output = _real_dir(output_root, "kernel build output")
    verify_kernel_checkout(kernel_plan, source)
    bind_kernel_plan_to_toolchain(kernel_plan, lock, source)
    verify_materialized_toolchain(lock, toolchain)
    config = verify_generated_kernel_config(kernel_plan, output / ".config")
    image = verify_arm64_kernel_image(
        kernel_plan,
        output / "arch" / kernel_plan.arch / "boot" / kernel_plan.image_name,
    )
    if config.config_sha256 != kernel_authority.config_sha256 or config.config_size != kernel_authority.config_size:
        raise DeviceTreeError("prepared build root config does not match reviewed kernel authority")
    if image.image_sha256 != kernel_authority.image_sha256 or image.image_size != kernel_authority.image_size:
        raise DeviceTreeError("prepared build root Image does not match reviewed kernel authority")

    recipe = create_kernel_build_recipe(kernel_plan, lock, jobs=jobs)
    env = _execution_env(toolchain, recipe, base_env)
    try:
        _run_checked(
            runner,
            _make_argv(source, output, recipe, device_tree_plan.build_target, parallel=True),
            env=env,
            timeout=step_timeout_seconds,
        )
    except KernelContractError as exc:
        raise DeviceTreeError("source-locked device-tree build target failed") from exc

    dtb_path = _build_file(output, device_tree_plan.dtb_output, "DTB output")
    dtb = inspect_dtb_artifact(dtb_path)
    raw: list[RawOverlayEvidence] = []
    overlay_paths: list[Path] = []
    for relative in device_tree_plan.dtbo_outputs:
        path = _build_file(output, relative, "DTBO overlay output")
        evidence = inspect_dtb_artifact(path)
        if evidence.tree_count != 1:
            raise DeviceTreeError("each raw DTBO output must contain exactly one FDT")
        raw.append(
            RawOverlayEvidence(
                relative_path=relative,
                artifact_sha256=evidence.artifact_sha256,
                artifact_size=evidence.artifact_size,
                fdt_tree_count=evidence.tree_count,
                fdt_evidence_sha256=evidence.evidence_sha256(),
            )
        )
        overlay_paths.append(path)

    pack_android_dtbo_image(
        tuple(overlay_paths),
        dtbo_image,
        page_size=device_tree_plan.dtbo_page_size,
        table_version=device_tree_plan.dtbo_table_version,
    )
    dtbo = inspect_dtbo_artifact(dtbo_image)
    limit = profile.data.get("partition_limits", {}).get("dtbo")
    if not isinstance(limit, int) or limit <= 0 or dtbo.artifact_size > limit:
        raise DeviceTreeError("packed DTBO exceeds or lacks profile partition limit")
    return DeviceTreeBuildRunEvidence(
        schema_version=1,
        profile_id=profile.profile_id,
        device_tree_plan_sha256=device_tree_plan.plan_sha256(),
        kernel_authority_sha256=kernel_authority.authority_sha256(),
        kernel_config_sha256=config.config_sha256,
        kernel_image_sha256=image.image_sha256,
        dtb_relative_path=device_tree_plan.dtb_output,
        dtb_sha256=dtb.artifact_sha256,
        dtb_size=dtb.artifact_size,
        dtb_tree_count=dtb.tree_count,
        dtb_evidence_sha256=dtb.evidence_sha256(),
        raw_dtbo=tuple(raw),
        dtbo_image_sha256=dtbo.artifact_sha256,
        dtbo_image_size=dtbo.artifact_size,
        dtbo_entry_count=dtbo.entry_count,
        dtbo_evidence_sha256=dtbo.evidence_sha256(),
        hardware_verified=False,
        beta_gate_credit=False,
    )


def verify_device_tree_reproducibility(
    plan: DeviceTreeBuildPlan,
    run_a: DeviceTreeBuildRunEvidence,
    run_b: DeviceTreeBuildRunEvidence,
    *,
    build_root_a: Path,
    build_root_b: Path,
) -> DeviceTreeReproducibilityEvidence:
    root_a = _real_dir(build_root_a, "device-tree build A")
    root_b = _real_dir(build_root_b, "device-tree build B")
    if root_a == root_b:
        raise DeviceTreeError("device-tree reproducibility requires independent build roots")
    for label, run in (("A", run_a), ("B", run_b)):
        if run.schema_version != 1 or run.profile_id != plan.profile_id:
            raise DeviceTreeError(f"device-tree build {label} identity mismatch")
        if run.device_tree_plan_sha256 != plan.plan_sha256():
            raise DeviceTreeError(f"device-tree build {label} plan mismatch")
        if run.kernel_authority_sha256 != plan.kernel_authority_sha256:
            raise DeviceTreeError(f"device-tree build {label} authority mismatch")
        if run.hardware_verified is not False or run.beta_gate_credit is not False:
            raise DeviceTreeError("host device-tree evidence cannot claim hardware/Beta credit")
    exact = (
        run_a.kernel_config_sha256 == run_b.kernel_config_sha256
        and run_a.kernel_image_sha256 == run_b.kernel_image_sha256
        and run_a.dtb_sha256 == run_b.dtb_sha256
        and run_a.dtb_size == run_b.dtb_size
        and tuple((x.relative_path, x.artifact_sha256, x.artifact_size) for x in run_a.raw_dtbo)
        == tuple((x.relative_path, x.artifact_sha256, x.artifact_size) for x in run_b.raw_dtbo)
        and run_a.dtbo_image_sha256 == run_b.dtbo_image_sha256
        and run_a.dtbo_image_size == run_b.dtbo_image_size
        and run_a.dtbo_entry_count == run_b.dtbo_entry_count
    )
    if not exact:
        raise DeviceTreeError("strict DTB/DTBO A/B byte identity failed")
    return DeviceTreeReproducibilityEvidence(
        schema_version=1,
        profile_id=plan.profile_id,
        device_tree_plan_sha256=plan.plan_sha256(),
        kernel_authority_sha256=plan.kernel_authority_sha256,
        build_a_evidence_sha256=run_a.evidence_sha256(),
        build_b_evidence_sha256=run_b.evidence_sha256(),
        dtb_sha256=run_a.dtb_sha256,
        dtb_size=run_a.dtb_size,
        raw_dtbo=tuple((x.relative_path, x.artifact_sha256, x.artifact_size) for x in run_a.raw_dtbo),
        dtbo_image_sha256=run_a.dtbo_image_sha256,
        dtbo_image_size=run_a.dtbo_image_size,
        dtbo_entry_count=run_a.dtbo_entry_count,
        byte_identical=True,
        distinct_build_roots_verified=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def write_evidence(evidence: Any, destination: Path) -> str:
    if getattr(evidence, "schema_version", None) != 1:
        raise DeviceTreeError("unsupported device-tree evidence schema")
    if getattr(evidence, "hardware_verified", False) is not False:
        raise DeviceTreeError("host device-tree evidence cannot claim hardware verification")
    if getattr(evidence, "beta_gate_credit", False) is not False:
        raise DeviceTreeError("host device-tree evidence cannot claim Beta credit")
    if destination.exists():
        raise DeviceTreeError(f"refusing to overwrite device-tree evidence: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = evidence.canonical_json()
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists():
        raise DeviceTreeError("refusing stale device-tree evidence temporary file")
    try:
        temporary.write_text(payload, encoding="utf-8", newline="\n")
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return sha256(payload.encode("utf-8")).hexdigest()
