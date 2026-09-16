"""Deterministic, profile-driven boot build planning.

This module prepares an auditable host-side build plan only. It never flashes or
boots a phone. A plan is accepted only when the stock image provenance belongs
to the selected profile and matches that profile's boot-layout contract.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path

from .boot_image import BootImageError, boot_build_contract
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
