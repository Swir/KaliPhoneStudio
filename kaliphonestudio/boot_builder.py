"""Deterministic, profile-driven boot build planning and host-side assembly."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import subprocess

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


@dataclass(frozen=True)
class BootAssemblyEvidence:
    schema_version: int
    profile_id: str
    plan_sha256: str
    image_sha256: str
    image_size: int
    reproducible: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"


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


def create_boot_build_plan(profile: DeviceProfile, provenance: StockBootProvenance, *, kernel: Path, ramdisk: Path, dtb: Path | None = None, dtbo: Path | None = None) -> BootBuildPlan:
    contract = boot_build_contract(profile)
    if provenance.profile_id != profile.profile_id:
        raise BootImageError("stock provenance profile does not match selected device profile")
    if provenance.boot_header_version != contract.header_version:
        raise BootImageError("stock provenance boot header does not match profile contract")
    if provenance.boot_size > contract.boot_partition_limit:
        raise BootImageError("stock provenance boot image exceeds profile partition limit")
    inputs = [_input("kernel", kernel), _input("ramdisk", ramdisk)]
    if contract.include_dtb:
        if dtb is None: raise BootImageError("profile requires a DTB build input")
        inputs.append(_input("dtb", dtb))
    elif dtb is not None: raise BootImageError("profile does not permit an in-boot DTB input")
    if contract.separate_dtbo:
        if dtbo is None: raise BootImageError("profile requires a separate DTBO build input")
        inputs.append(_input("dtbo", dtbo))
    elif dtbo is not None: raise BootImageError("profile does not permit a separate DTBO input")
    return BootBuildPlan(1, profile.profile_id, provenance.boot_sha256, provenance.ota_sha256, contract.header_version, contract.page_size, contract.ramdisk_compression, contract.kernel_cmdline, tuple(inputs))


def verify_boot_build_plan(plan: BootBuildPlan, profile: DeviceProfile, provenance: StockBootProvenance, *, input_dir: Path) -> None:
    if plan.schema_version != 1: raise BootImageError("unsupported boot build plan schema")
    contract = boot_build_contract(profile)
    if plan.profile_id != profile.profile_id or provenance.profile_id != profile.profile_id: raise BootImageError("boot build plan/profile provenance mismatch")
    if plan.stock_boot_sha256 != provenance.boot_sha256 or plan.stock_ota_sha256 != provenance.ota_sha256: raise BootImageError("stock provenance changed after boot build planning")
    if plan.header_version != contract.header_version or plan.page_size != contract.page_size: raise BootImageError("boot layout contract changed after planning")
    if plan.ramdisk_compression != contract.ramdisk_compression or plan.kernel_cmdline != contract.kernel_cmdline: raise BootImageError("boot policy changed after planning")
    expected_names = ["kernel", "ramdisk"] + (["dtb"] if contract.include_dtb else []) + (["dtbo"] if contract.separate_dtbo else [])
    if [item.name for item in plan.inputs] != expected_names: raise BootImageError("boot build plan input set/order does not match profile")
    for planned in plan.inputs:
        if Path(planned.path).name != planned.path or planned.path in {"", ".", ".."}: raise BootImageError(f"unsafe planned input path: {planned.name}")
        current = _input(planned.name, input_dir / planned.path)
        if current.size != planned.size or current.sha256 != planned.sha256: raise BootImageError(f"planned build input changed: {planned.name}")


def source_locked_assembler_prefix(plan: BootBuildPlan, *, lock_manifest: Path, exact_checkout: Path) -> tuple[str, str]:
    lock = require_assembler_for_header(load_boot_tool_locks(lock_manifest), plan.header_version)
    return lock.argv(exact_checkout)


def mkbootimg_argv(plan: BootBuildPlan, profile: DeviceProfile, provenance: StockBootProvenance, *, input_dir: Path, output: Path, lock_manifest: Path, exact_checkout: Path) -> tuple[str, ...]:
    verify_boot_build_plan(plan, profile, provenance, input_dir=input_dir)
    contract = boot_build_contract(profile)
    if plan.header_version not in {0, 1, 2}: raise BootImageError("legacy mkbootimg invocation supports header versions 0-2 only")
    if not output.name or output.name in {".", ".."}: raise BootImageError("invalid boot image output path")
    by_name = {item.name: item for item in plan.inputs}
    argv = [*source_locked_assembler_prefix(plan, lock_manifest=lock_manifest, exact_checkout=exact_checkout), "--header_version", str(plan.header_version), "--pagesize", str(plan.page_size), "--kernel", str(input_dir / by_name["kernel"].path), "--ramdisk", str(input_dir / by_name["ramdisk"].path)]
    if contract.include_dtb: argv.extend(("--dtb", str(input_dir / by_name["dtb"].path)))
    if plan.kernel_cmdline: argv.extend(("--cmdline", " ".join(plan.kernel_cmdline)))
    argv.extend(("--output", str(output)))
    return tuple(argv)


def assemble_boot_image_reproducibly(plan: BootBuildPlan, profile: DeviceProfile, provenance: StockBootProvenance, *, input_dir: Path, destination: Path, lock_manifest: Path, exact_checkout: Path, timeout_seconds: int = 120) -> BootAssemblyEvidence:
    """Assemble twice with the locked backend; publish only byte-identical output."""
    if timeout_seconds <= 0: raise BootImageError("assembler timeout must be positive")
    destination.parent.mkdir(parents=True, exist_ok=True)
    first = destination.with_name(destination.name + ".build1")
    second = destination.with_name(destination.name + ".build2")
    for candidate in (first, second):
        candidate.unlink(missing_ok=True)
        argv = mkbootimg_argv(plan, profile, provenance, input_dir=input_dir, output=candidate, lock_manifest=lock_manifest, exact_checkout=exact_checkout)
        try:
            subprocess.run(argv, check=True, shell=False, timeout=timeout_seconds, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except (subprocess.SubprocessError, OSError) as exc:
            candidate.unlink(missing_ok=True)
            first.unlink(missing_ok=True); second.unlink(missing_ok=True)
            raise BootImageError(f"source-locked boot assembler failed: {exc}") from exc
        if not candidate.is_file() or candidate.stat().st_size <= 0:
            first.unlink(missing_ok=True); second.unlink(missing_ok=True)
            raise BootImageError("boot assembler produced no usable image")
    first_bytes = first.read_bytes(); second_bytes = second.read_bytes()
    if first_bytes != second_bytes:
        first.unlink(missing_ok=True); second.unlink(missing_ok=True)
        raise BootImageError("boot assembly is not reproducible byte-for-byte")
    limit = boot_build_contract(profile).boot_partition_limit
    if len(first_bytes) > limit:
        first.unlink(missing_ok=True); second.unlink(missing_ok=True)
        raise BootImageError("assembled boot image exceeds profile partition limit")
    digest = sha256(first_bytes).hexdigest()
    first.replace(destination); second.unlink(missing_ok=True)
    return BootAssemblyEvidence(1, profile.profile_id, plan.plan_sha256(), digest, len(first_bytes), True)


def write_boot_build_plan(plan: BootBuildPlan, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = plan.canonical_json(); temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8", newline="\n"); temporary.replace(destination)
    return sha256(payload.encode("utf-8")).hexdigest()
