"""Fail-closed, profile-driven boot image preflight helpers.

Host-side structural checks only. This module never flashes or boots a device
and does not claim hardware compatibility.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import struct

from .profiles import DeviceProfile

ANDROID_MAGIC = b"ANDROID!"


class BootImageError(ValueError):
    pass


@dataclass(frozen=True)
class BootImageReport:
    path: Path
    size: int
    sha256: str
    android_magic: bool
    header_version: int | None
    within_partition_limit: bool


@dataclass(frozen=True)
class BootBuildContract:
    profile_id: str
    header_version: int
    page_size: int
    kernel_image: str
    include_dtb: bool
    separate_dtbo: bool
    ramdisk_compression: str
    boot_partition_limit: int
    kernel_cmdline: tuple[str, ...]


def boot_build_contract(profile: DeviceProfile) -> BootBuildContract:
    """Resolve all boot-layout knowledge from a validated device profile."""
    boot = profile.data["boot"]
    page_size = int(boot.get("page_size", 0))
    kernel_image = str(boot.get("kernel_image", "")).strip()
    compression = str(boot.get("ramdisk_compression", "")).strip().lower()
    if page_size <= 0 or page_size & (page_size - 1):
        raise BootImageError("profile boot.page_size must be a positive power of two")
    if not kernel_image:
        raise BootImageError("profile boot.kernel_image is required")
    if compression not in {"gzip", "lz4", "none"}:
        raise BootImageError("unsupported profile ramdisk compression")
    cmdline = tuple(str(x).strip() for x in profile.data.get("kernel_cmdline", []))
    if any(not x for x in cmdline) or len(cmdline) != len(set(cmdline)):
        raise BootImageError("kernel_cmdline entries must be non-empty and unique")
    return BootBuildContract(
        profile_id=profile.profile_id,
        header_version=int(boot["header_version"]),
        page_size=page_size,
        kernel_image=kernel_image,
        include_dtb=bool(boot.get("include_dtb", False)),
        separate_dtbo=bool(boot.get("separate_dtbo", False)),
        ramdisk_compression=compression,
        boot_partition_limit=int(profile.data["partition_limits"]["boot"]),
        kernel_cmdline=cmdline,
    )


def _read_header_version(header: bytes) -> int | None:
    if len(header) < 44 or not header.startswith(ANDROID_MAGIC):
        return None
    return struct.unpack_from("<I", header, 40)[0]


def inspect_boot_image(path: Path, profile: DeviceProfile) -> BootImageReport:
    if not path.is_file():
        raise BootImageError(f"boot image does not exist: {path}")
    size = path.stat().st_size
    if size <= 0:
        raise BootImageError("boot image is empty")
    contract = boot_build_contract(profile)
    digest = sha256()
    with path.open("rb") as fh:
        header = fh.read(max(4096, contract.page_size))
        digest.update(header)
        while chunk := fh.read(1024 * 1024):
            digest.update(chunk)
    return BootImageReport(
        path=path,
        size=size,
        sha256=digest.hexdigest(),
        android_magic=header.startswith(ANDROID_MAGIC),
        header_version=_read_header_version(header),
        within_partition_limit=size <= contract.boot_partition_limit,
    )


def require_candidate_compatible(report: BootImageReport, profile: DeviceProfile) -> None:
    contract = boot_build_contract(profile)
    if not report.android_magic:
        raise BootImageError("candidate is not an Android boot image")
    if report.header_version != contract.header_version:
        raise BootImageError(
            f"boot header mismatch: candidate={report.header_version}, expected={contract.header_version}"
        )
    if not report.within_partition_limit:
        raise BootImageError("candidate exceeds profile boot partition limit")


def require_stock_candidate_pair(stock: BootImageReport, candidate: BootImageReport, profile: DeviceProfile) -> None:
    require_candidate_compatible(stock, profile)
    require_candidate_compatible(candidate, profile)
    if stock.header_version != candidate.header_version:
        raise BootImageError("stock/candidate boot header versions differ")
    if stock.sha256 == candidate.sha256:
        raise BootImageError("candidate is byte-identical to stock image")
