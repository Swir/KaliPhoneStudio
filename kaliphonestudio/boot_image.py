"""Fail-closed, profile-driven boot image preflight helpers.

Host-side structural checks only. This module never flashes or boots a device
and does not claim hardware compatibility. Optional AVB footer inspection is
structural/provenance evidence only; cryptographic AVB verification remains a
separate release requirement.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import struct

from .profiles import DeviceProfile

ANDROID_MAGIC = b"ANDROID!"
LEGACY_V0_HEADER_SIZE = 1632
LEGACY_V1_HEADER_SIZE = 1648
LEGACY_V2_HEADER_SIZE = 1660
AVB_FOOTER_MAGIC = b"AVBf"
AVB_FOOTER_SIZE = 64
AVB_VBMETA_MAGIC = b"AVB0"
AVB_VBMETA_HEADER_SIZE = 256


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
    page_size: int | None = None
    kernel_size: int | None = None
    ramdisk_size: int | None = None
    second_size: int | None = None
    recovery_dtbo_size: int | None = None
    recovery_dtbo_offset: int | None = None
    declared_header_size: int | None = None
    dtb_size: int | None = None
    expected_payload_end: int | None = None
    kernel_sha256: str | None = None
    ramdisk_sha256: str | None = None
    second_sha256: str | None = None
    recovery_dtbo_sha256: str | None = None
    dtb_sha256: str | None = None
    avb_footer_present: bool = False
    avb_footer_version_major: int | None = None
    avb_footer_version_minor: int | None = None
    avb_original_image_size: int | None = None
    avb_vbmeta_offset: int | None = None
    avb_vbmeta_size: int | None = None
    avb_vbmeta_sha256: str | None = None
    avb_vbmeta_header_valid: bool | None = None
    avb_structural_errors: tuple[str, ...] = ()
    structural_errors: tuple[str, ...] = ()


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


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _u64(data: bytes, offset: int) -> int:
    return struct.unpack_from("<Q", data, offset)[0]


def _align(value: int, page_size: int) -> int:
    if value == 0:
        return 0
    return ((value + page_size - 1) // page_size) * page_size


def _hash_file_range(path: Path, offset: int, size: int) -> str | None:
    if size == 0:
        return None
    digest = sha256()
    remaining = size
    with path.open("rb") as fh:
        fh.seek(offset)
        while remaining:
            chunk = fh.read(min(1024 * 1024, remaining))
            if not chunk:
                raise BootImageError("boot image changed or truncated while hashing a component")
            digest.update(chunk)
            remaining -= len(chunk)
    return digest.hexdigest()


def _legacy_layout_report(
    header: bytes,
    *,
    image_size: int,
    header_version: int,
    contract: BootBuildContract,
) -> dict[str, object]:
    """Parse and validate Android legacy boot header v0/v1/v2 layout fields.

    AOSP defines each legacy component as page-aligned. v2 additionally requires
    a non-empty DTB. This parser deliberately validates only the legacy family;
    a profile requesting a newer header cannot silently inherit v2 assumptions.
    """
    errors: list[str] = []
    minimum_header = {
        0: LEGACY_V0_HEADER_SIZE,
        1: LEGACY_V1_HEADER_SIZE,
        2: LEGACY_V2_HEADER_SIZE,
    }[header_version]
    if len(header) < minimum_header:
        return {
            "page_size": None,
            "kernel_size": None,
            "ramdisk_size": None,
            "second_size": None,
            "recovery_dtbo_size": None,
            "recovery_dtbo_offset": None,
            "declared_header_size": None,
            "dtb_size": None,
            "expected_payload_end": None,
            "component_ranges": (),
            "structural_errors": (f"boot header is truncated before v{header_version} header end",),
        }

    kernel_size = _u32(header, 8)
    ramdisk_size = _u32(header, 16)
    second_size = _u32(header, 24)
    page_size = _u32(header, 36)
    recovery_dtbo_size = _u32(header, 1632) if header_version >= 1 else 0
    recovery_dtbo_offset = _u64(header, 1636) if header_version >= 1 else 0
    declared_header_size = _u32(header, 1644) if header_version >= 1 else LEGACY_V0_HEADER_SIZE
    dtb_size = _u32(header, 1648) if header_version >= 2 else 0

    if page_size <= 0 or page_size & (page_size - 1):
        errors.append("boot header page_size is not a positive power of two")
    elif page_size != contract.page_size:
        errors.append(
            f"boot header page_size mismatch: candidate={page_size}, expected={contract.page_size}"
        )

    if kernel_size == 0:
        errors.append("boot header declares an empty kernel")
    if ramdisk_size == 0:
        errors.append("boot header declares an empty ramdisk")
    if header_version >= 2 and dtb_size == 0:
        errors.append("boot header v2 declares an empty DTB")

    if header_version >= 1 and declared_header_size != minimum_header:
        errors.append(
            f"boot header_size mismatch: candidate={declared_header_size}, expected={minimum_header}"
        )

    expected_end: int | None = None
    component_ranges: list[tuple[str, int, int]] = []
    if page_size > 0 and not (page_size & (page_size - 1)):
        if page_size < minimum_header:
            errors.append("boot page is smaller than the declared header structure")
        cursor = page_size
        component_ranges.append(("kernel", cursor, kernel_size))
        cursor += _align(kernel_size, page_size)
        component_ranges.append(("ramdisk", cursor, ramdisk_size))
        cursor += _align(ramdisk_size, page_size)
        component_ranges.append(("second", cursor, second_size))
        cursor += _align(second_size, page_size)
        expected_recovery_offset = cursor
        if recovery_dtbo_size:
            if recovery_dtbo_offset != expected_recovery_offset:
                errors.append(
                    "recovery_dtbo_offset does not match the page-aligned legacy boot layout"
                )
            component_ranges.append(("recovery_dtbo", cursor, recovery_dtbo_size))
            cursor += _align(recovery_dtbo_size, page_size)
        if header_version >= 2:
            component_ranges.append(("dtb", cursor, dtb_size))
            cursor += _align(dtb_size, page_size)
        expected_end = cursor
        if image_size < expected_end:
            errors.append(
                f"boot image is truncated: size={image_size}, expected_payload_end={expected_end}"
            )

    return {
        "page_size": page_size,
        "kernel_size": kernel_size,
        "ramdisk_size": ramdisk_size,
        "second_size": second_size,
        "recovery_dtbo_size": recovery_dtbo_size,
        "recovery_dtbo_offset": recovery_dtbo_offset,
        "declared_header_size": declared_header_size,
        "dtb_size": dtb_size,
        "expected_payload_end": expected_end,
        "component_ranges": tuple(component_ranges),
        "structural_errors": tuple(errors),
    }


def _inspect_avb_footer(path: Path, *, image_size: int, expected_payload_end: int | None) -> dict[str, object]:
    """Inspect an optional AOSP AVB footer and its embedded vbmeta blob.

    This validates only byte layout and bounds. It deliberately does not verify
    signatures, hashes, rollback indexes or trust roots.
    """
    empty = {
        "avb_footer_present": False,
        "avb_footer_version_major": None,
        "avb_footer_version_minor": None,
        "avb_original_image_size": None,
        "avb_vbmeta_offset": None,
        "avb_vbmeta_size": None,
        "avb_vbmeta_sha256": None,
        "avb_vbmeta_header_valid": None,
        "avb_structural_errors": (),
    }
    if image_size < AVB_FOOTER_SIZE:
        return empty

    with path.open("rb") as fh:
        fh.seek(image_size - AVB_FOOTER_SIZE)
        footer = fh.read(AVB_FOOTER_SIZE)
    if len(footer) != AVB_FOOTER_SIZE or not footer.startswith(AVB_FOOTER_MAGIC):
        return empty

    errors: list[str] = []
    _, version_major, version_minor, original_size, vbmeta_offset, vbmeta_size = struct.unpack(
        ">4sIIQQQ28x", footer
    )
    footer_offset = image_size - AVB_FOOTER_SIZE

    if original_size <= 0:
        errors.append("AVB footer original_image_size must be positive")
    if expected_payload_end is not None and original_size < expected_payload_end:
        errors.append("AVB original image is smaller than the declared boot payload")
    if vbmeta_size < AVB_VBMETA_HEADER_SIZE:
        errors.append("AVB footer vbmeta_size is smaller than the vbmeta header")
    if vbmeta_offset < original_size:
        errors.append("AVB vbmeta_offset precedes original_image_size")
    if vbmeta_offset > footer_offset or vbmeta_size > footer_offset - min(vbmeta_offset, footer_offset):
        errors.append("AVB vbmeta range escapes the image before the footer")

    vbmeta_digest: str | None = None
    vbmeta_header_valid: bool | None = None
    if not errors:
        with path.open("rb") as fh:
            fh.seek(vbmeta_offset)
            vbmeta = fh.read(vbmeta_size)
        if len(vbmeta) != vbmeta_size:
            errors.append("AVB vbmeta blob is truncated")
        else:
            vbmeta_digest = sha256(vbmeta).hexdigest()
            vbmeta_header_valid = vbmeta.startswith(AVB_VBMETA_MAGIC)
            if not vbmeta_header_valid:
                errors.append("AVB vbmeta magic is invalid")
            elif len(vbmeta) >= AVB_VBMETA_HEADER_SIZE:
                _, _required_major, _required_minor, auth_size, aux_size = struct.unpack_from(
                    ">4sIIQQ", vbmeta, 0
                )
                declared_vbmeta_size = AVB_VBMETA_HEADER_SIZE + auth_size + aux_size
                if declared_vbmeta_size != vbmeta_size:
                    errors.append(
                        "AVB vbmeta block sizes do not match footer-declared vbmeta_size"
                    )

    return {
        "avb_footer_present": True,
        "avb_footer_version_major": version_major,
        "avb_footer_version_minor": version_minor,
        "avb_original_image_size": original_size,
        "avb_vbmeta_offset": vbmeta_offset,
        "avb_vbmeta_size": vbmeta_size,
        "avb_vbmeta_sha256": vbmeta_digest,
        "avb_vbmeta_header_valid": vbmeta_header_valid,
        "avb_structural_errors": tuple(errors),
    }


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

    android_magic = header.startswith(ANDROID_MAGIC)
    header_version = _read_header_version(header)
    layout: dict[str, object] = {
        "page_size": None,
        "kernel_size": None,
        "ramdisk_size": None,
        "second_size": None,
        "recovery_dtbo_size": None,
        "recovery_dtbo_offset": None,
        "declared_header_size": None,
        "dtb_size": None,
        "expected_payload_end": None,
        "component_ranges": (),
        "structural_errors": (),
    }
    if android_magic and header_version in {0, 1, 2}:
        layout = _legacy_layout_report(
            header,
            image_size=size,
            header_version=header_version,
            contract=contract,
        )

    component_hashes: dict[str, str | None] = {
        "kernel": None,
        "ramdisk": None,
        "second": None,
        "recovery_dtbo": None,
        "dtb": None,
    }
    if not layout["structural_errors"]:
        for name, offset, component_size in layout["component_ranges"]:
            if offset + component_size <= size:
                component_hashes[name] = _hash_file_range(path, offset, component_size)

    avb = _inspect_avb_footer(
        path,
        image_size=size,
        expected_payload_end=layout["expected_payload_end"],
    )

    return BootImageReport(
        path=path,
        size=size,
        sha256=digest.hexdigest(),
        android_magic=android_magic,
        header_version=header_version,
        within_partition_limit=size <= contract.boot_partition_limit,
        page_size=layout["page_size"],
        kernel_size=layout["kernel_size"],
        ramdisk_size=layout["ramdisk_size"],
        second_size=layout["second_size"],
        recovery_dtbo_size=layout["recovery_dtbo_size"],
        recovery_dtbo_offset=layout["recovery_dtbo_offset"],
        declared_header_size=layout["declared_header_size"],
        dtb_size=layout["dtb_size"],
        expected_payload_end=layout["expected_payload_end"],
        kernel_sha256=component_hashes["kernel"],
        ramdisk_sha256=component_hashes["ramdisk"],
        second_sha256=component_hashes["second"],
        recovery_dtbo_sha256=component_hashes["recovery_dtbo"],
        dtb_sha256=component_hashes["dtb"],
        avb_footer_present=avb["avb_footer_present"],
        avb_footer_version_major=avb["avb_footer_version_major"],
        avb_footer_version_minor=avb["avb_footer_version_minor"],
        avb_original_image_size=avb["avb_original_image_size"],
        avb_vbmeta_offset=avb["avb_vbmeta_offset"],
        avb_vbmeta_size=avb["avb_vbmeta_size"],
        avb_vbmeta_sha256=avb["avb_vbmeta_sha256"],
        avb_vbmeta_header_valid=avb["avb_vbmeta_header_valid"],
        avb_structural_errors=avb["avb_structural_errors"],
        structural_errors=layout["structural_errors"],
    )


def require_candidate_compatible(report: BootImageReport, profile: DeviceProfile) -> None:
    contract = boot_build_contract(profile)
    if not report.android_magic:
        raise BootImageError("candidate is not an Android boot image")
    if report.header_version != contract.header_version:
        raise BootImageError(
            f"boot header mismatch: candidate={report.header_version}, expected={contract.header_version}"
        )
    if report.header_version in {0, 1, 2} and report.structural_errors:
        raise BootImageError("invalid boot image layout: " + "; ".join(report.structural_errors))
    if report.avb_footer_present and report.avb_structural_errors:
        raise BootImageError("invalid AVB footer/vbmeta layout: " + "; ".join(report.avb_structural_errors))
    if not report.within_partition_limit:
        raise BootImageError("candidate exceeds profile boot partition limit")


def require_stock_candidate_pair(stock: BootImageReport, candidate: BootImageReport, profile: DeviceProfile) -> None:
    require_candidate_compatible(stock, profile)
    require_candidate_compatible(candidate, profile)
    if stock.header_version != candidate.header_version:
        raise BootImageError("stock/candidate boot header versions differ")
    if stock.sha256 == candidate.sha256:
        raise BootImageError("candidate is byte-identical to stock image")
