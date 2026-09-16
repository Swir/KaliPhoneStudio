"""Deterministic, profile-driven boot build planning.

This module prepares and verifies auditable host-side build plans only. It never
flashes or boots a phone. Plans bind stock provenance and every build input by
SHA-256; they must be revalidated immediately before an assembler is invoked.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path

from .boot_image import BootImageError, boot_build_contract
from .boot_tools import load_boot_tool_locks, require_assembler_for_header
from .profiles import DeviceProfile
from .provenance import StockBootProvenance


@dataclass(frozen=True)
class BuildInput:
    name: str
    path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class BootBuildPlan:
    schema_version: int
    profile_id: str
    stock_boot_sha256: str
    stock_ota_sha256: str
    header_version: int
    page_size: int
    ramdisk_compression: str
    kernel_cmdline: tuple[str, ...]
    inputs: tuple[BuildInput, ...]

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def plan_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _input(name: str, path: Path) -> BuildInput:
    if not path.is_file():
        raise BootImageError(f"required build input does not exist: {name}: {path}")
    size = path.stat().st_size
    if size <= 0:
        raise BootImageError(f"required build input is empty: {name}")
    digest = sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1024 * 1024):
            digest.update(chunk)
    return BuildInput(name=name, path=path.name, size=size, sha256=digest.hexdigest())


def create_boot_build_plan(
    profile: DeviceProfile,
    provenance: StockBootProvenance,
    *,
    kernel: Path,
    ramdisk: Path,
    dtb: Path | None = None,
    dtbo: Path | None = None,
) -> BootBuildPlan:
    """Create a deterministic plan from profile policy plus immutable stock evidence."""
    contract = boot_build_contract(profile)
    if provenance.profile_id != profile.profile_id:
        raise BootImageError("stock provenance profile does not match selected device profile")
    if provenance.boot_header_version != contract.header_version:
        raise BootImageError("stock provenance boot header does not match profile contract")
    if provenance.boot_size > contract.boot_partition_limit:
        raise BootImageError("stock provenance boot image exceeds profile partition limit")

    inputs = [_input("kernel", kernel), _input("ramdisk", ramdisk)]
    if contract.include_dtb:
        if dtb is None:
            raise BootImageError("profile requires a DTB build input")
        inputs.append(_input("dtb", dtb))
    elif dtb is not None:
        raise BootImageError("profile does not permit an in-boot DTB input")

    if contract.separate_dtbo:
        if dtbo is None:
            raise BootImageError("profile requires a separate DTBO build input")
        inputs.append(_input("dtbo", dtbo))
    elif dtbo is not None:
        raise BootImageError("profile does not permit a separate DTBO input")

    return BootBuildPlan(
        schema_version=1,
        profile_id=profile.profile_id,
        stock_boot_sha256=provenance.boot_sha256,
        stock_ota_sha256=provenance.ota_sha256,
        header_version=contract.header_version,
        page_size=contract.page_size,
        ramdisk_compression=contract.ramdisk_compression,
        kernel_cmdline=contract.kernel_cmdline,
        inputs=tuple(inputs),
    )


def verify_boot_build_plan(
    plan: BootBuildPlan,
    profile: DeviceProfile,
    provenance: StockBootProvenance,
    *,
    input_dir: Path,
) -> None:
    """Fail closed if profile, stock evidence, or any planned input has drifted."""
    if plan.schema_version != 1:
        raise BootImageError("unsupported boot build plan schema")
    contract = boot_build_contract(profile)
    if plan.profile_id != profile.profile_id or provenance.profile_id != profile.profile_id:
        raise BootImageError("boot build plan/profile provenance mismatch")
    if plan.stock_boot_sha256 != provenance.boot_sha256 or plan.stock_ota_sha256 != provenance.ota_sha256:
        raise BootImageError("stock provenance changed after boot build planning")
    if plan.header_version != contract.header_version or plan.page_size != contract.page_size:
        raise BootImageError("boot layout contract changed after planning")
    if plan.ramdisk_compression != contract.ramdisk_compression or plan.kernel_cmdline != contract.kernel_cmdline:
        raise BootImageError("boot policy changed after planning")

    expected_names = ["kernel", "ramdisk"]
    if contract.include_dtb:
        expected_names.append("dtb")
    if contract.separate_dtbo:
        expected_names.append("dtbo")
    if [item.name for item in plan.inputs] != expected_names:
        raise BootImageError("boot build plan input set/order does not match profile")

    for planned in plan.inputs:
        if Path(planned.path).name != planned.path or planned.path in {"", ".", ".."}:
            raise BootImageError(f"unsafe planned input path: {planned.name}")
        current = _input(planned.name, input_dir / planned.path)
        if current.size != planned.size or current.sha256 != planned.sha256:
            raise BootImageError(f"planned build input changed: {planned.name}")


def source_locked_assembler_prefix(
    plan: BootBuildPlan,
    *,
    lock_manifest: Path,
    exact_checkout: Path,
) -> tuple[str, str]:
    """Resolve only an explicitly source-locked assembler for this plan's header."""
    locks = load_boot_tool_locks(lock_manifest)
    lock = require_assembler_for_header(locks, plan.header_version)
    return lock.argv(exact_checkout)


def mkbootimg_argv(
    plan: BootBuildPlan,
    profile: DeviceProfile,
    provenance: StockBootProvenance,
    *,
    input_dir: Path,
    output: Path,
    lock_manifest: Path,
    exact_checkout: Path,
) -> tuple[str, ...]:
    """Return the deterministic argv for a verified legacy Android boot image build.

    This is deliberately an invocation planner, not an executor. It revalidates
    every input immediately before constructing argv, never uses a PATH mkbootimg,
    and never treats the profile's separate DTBO as an in-boot recovery_dtbo.
    """
    verify_boot_build_plan(plan, profile, provenance, input_dir=input_dir)
    contract = boot_build_contract(profile)
    if plan.header_version not in {0, 1, 2}:
        raise BootImageError("legacy mkbootimg invocation supports header versions 0-2 only")
    if not output.name or output.name in {".", ".."}:
        raise BootImageError("invalid boot image output path")

    by_name = {item.name: item for item in plan.inputs}
    prefix = source_locked_assembler_prefix(
        plan, lock_manifest=lock_manifest, exact_checkout=exact_checkout
    )
    argv = [
        *prefix,
        "--header_version", str(plan.header_version),
        "--pagesize", str(plan.page_size),
        "--kernel", str(input_dir / by_name["kernel"].path),
        "--ramdisk", str(input_dir / by_name["ramdisk"].path),
    ]
    if contract.include_dtb:
        argv.extend(("--dtb", str(input_dir / by_name["dtb"].path)))
    if plan.kernel_cmdline:
        argv.extend(("--cmdline", " ".join(plan.kernel_cmdline)))
    argv.extend(("--output", str(output)))
    return tuple(argv)


def write_boot_build_plan(plan: BootBuildPlan, destination: Path) -> str:
    """Atomically persist canonical plan JSON and return its SHA-256."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = plan.canonical_json()
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8", newline="\n")
    temporary.replace(destination)
    return sha256(payload.encode("utf-8")).hexdigest()
