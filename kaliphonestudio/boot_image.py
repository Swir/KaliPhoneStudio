"""Fail-closed boot image preflight helpers.

This module performs host-side structural checks only. It does not flash or boot
anything and intentionally does not claim device compatibility.
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


def _read_header_version(header: bytes) -> int | None:
    # Android boot header v1/v2 stores header_version at offset 40.
    if len(header) < 44 or not header.startswith(ANDROID_MAGIC):
        return None
    return struct.unpack_from("<I", header, 40)[0]


def inspect_boot_image(path: Path, profile: DeviceProfile) -> BootImageReport:
    if not path.is_file():
        raise BootImageError(f"boot image does not exist: {path}")
    size = path.stat().st_size
    if size <= 0:
        raise BootImageError("boot image is empty")
    limit = int(profile.data["partition_limits"]["boot"])
    digest = sha256()
    with path.open("rb") as fh:
        header = fh.read(4096)
        digest.update(header)
        while chunk := fh.read(1024 * 1024):
            digest.update(chunk)
    version = _read_header_version(header)
    return BootImageReport(
        path=path,
        size=size,
        sha256=digest.hexdigest(),
        android_magic=header.startswith(ANDROID_MAGIC),
        header_version=version,
        within_partition_limit=size <= limit,
    )


def require_candidate_compatible(report: BootImageReport, profile: DeviceProfile) -> None:
    if not report.android_magic:
        raise BootImageError("candidate is not an Android boot image")
    expected = int(profile.data["boot"]["header_version"])
    if report.header_version != expected:
        raise BootImageError(
            f"boot header mismatch: candidate={report.header_version}, expected={expected}"
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
