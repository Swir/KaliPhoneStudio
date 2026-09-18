from pathlib import Path
import copy
import struct

import pytest

from kaliphonestudio.boot_image import (
    BootImageError,
    boot_build_contract,
    inspect_boot_image,
    require_candidate_compatible,
    require_stock_candidate_pair,
)
from kaliphonestudio.profiles import DeviceProfile, get_profile

ROOT = Path(__file__).parents[1]
PROFILE = get_profile(ROOT / "devices", "oneplus/avicii")


def _align(value: int, page_size: int) -> int:
    return 0 if value == 0 else ((value + page_size - 1) // page_size) * page_size


def image(
    tmp_path: Path,
    name: str,
    version: int = 2,
    marker: bytes = b"x",
    *,
    page_size: int = 4096,
    kernel_size: int = 32,
    ramdisk_size: int = 24,
    second_size: int = 0,
    recovery_dtbo_size: int = 0,
    recovery_dtbo_offset: int | None = None,
    header_size: int = 1660,
    dtb_size: int = 16,
    truncate_by: int = 0,
) -> Path:
    if version != 2:
        data = bytearray(4096)
        data[:8] = b"ANDROID!"
        struct.pack_into("<I", data, 40, version)
        data[128:128 + len(marker)] = marker
    else:
        recovery_offset = (
            page_size
            + _align(kernel_size, page_size)
            + _align(ramdisk_size, page_size)
            + _align(second_size, page_size)
        )
        expected_end = recovery_offset + _align(recovery_dtbo_size, page_size) + _align(dtb_size, page_size)
        data = bytearray(expected_end)
        data[:8] = b"ANDROID!"
        struct.pack_into("<I", data, 8, kernel_size)
        struct.pack_into("<I", data, 16, ramdisk_size)
        struct.pack_into("<I", data, 24, second_size)
        struct.pack_into("<I", data, 36, page_size)
        struct.pack_into("<I", data, 40, 2)
        struct.pack_into("<I", data, 1632, recovery_dtbo_size)
        struct.pack_into(
            "<Q", data, 1636,
            recovery_offset if recovery_dtbo_offset is None else recovery_dtbo_offset,
        )
        struct.pack_into("<I", data, 1644, header_size)
        struct.pack_into("<I", data, 1648, dtb_size)
        struct.pack_into("<Q", data, 1652, 0x10000000)
        data[128:128 + len(marker)] = marker
        if truncate_by:
            data = data[:-truncate_by]
    p = tmp_path / name
    p.write_bytes(data)
    return p


def mutated_profile(mutator) -> DeviceProfile:
    data = copy.deepcopy(PROFILE.data)
    mutator(data)
    return DeviceProfile(path=PROFILE.path, data=data)


def test_build_contract_is_profile_driven():
    contract = boot_build_contract(PROFILE)
    assert contract.profile_id == "oneplus/avicii"
    assert contract.header_version == 2
    assert contract.page_size == 4096
    assert contract.kernel_image == "Image"
    assert contract.include_dtb is True
    assert contract.separate_dtbo is True
    assert contract.ramdisk_compression == "lz4"
    assert contract.boot_partition_limit == PROFILE.data["partition_limits"]["boot"]
    assert contract.kernel_cmdline == tuple(PROFILE.data["kernel_cmdline"])


def test_build_contract_rejects_invalid_page_size():
    profile = mutated_profile(lambda d: d["boot"].update(page_size=3000))
    with pytest.raises(BootImageError):
        boot_build_contract(profile)


def test_build_contract_rejects_unknown_ramdisk_compression():
    profile = mutated_profile(lambda d: d["boot"].update(ramdisk_compression="magic"))
    with pytest.raises(BootImageError):
        boot_build_contract(profile)


def test_build_contract_rejects_duplicate_cmdline():
    profile = mutated_profile(lambda d: d.update(kernel_cmdline=["a=1", "a=1"]))
    with pytest.raises(BootImageError):
        boot_build_contract(profile)


def test_accepts_structurally_valid_profile_v2_image(tmp_path):
    report = inspect_boot_image(image(tmp_path, "candidate.img"), PROFILE)
    require_candidate_compatible(report, PROFILE)
    assert report.header_version == 2
    assert report.page_size == 4096
    assert report.kernel_size == 32
    assert report.ramdisk_size == 24
    assert report.dtb_size == 16
    assert report.declared_header_size == 1660
    assert report.expected_payload_end == 16384
    assert report.structural_errors == ()
    assert len(report.sha256) == 64


def test_rejects_wrong_header_version(tmp_path):
    report = inspect_boot_image(image(tmp_path, "candidate.img", version=4), PROFILE)
    with pytest.raises(BootImageError, match="header mismatch"):
        require_candidate_compatible(report, PROFILE)


def test_rejects_v2_page_size_mismatch(tmp_path):
    report = inspect_boot_image(image(tmp_path, "candidate.img", page_size=2048), PROFILE)
    with pytest.raises(BootImageError, match="page_size mismatch"):
        require_candidate_compatible(report, PROFILE)


def test_rejects_v2_empty_kernel_ramdisk_or_dtb(tmp_path):
    for field, kwargs in (
        ("kernel", {"kernel_size": 0}),
        ("ramdisk", {"ramdisk_size": 0}),
        ("DTB", {"dtb_size": 0}),
    ):
        report = inspect_boot_image(image(tmp_path, f"empty-{field}.img", **kwargs), PROFILE)
        with pytest.raises(BootImageError, match=f"empty {field}"):
            require_candidate_compatible(report, PROFILE)


def test_rejects_v2_wrong_declared_header_size(tmp_path):
    report = inspect_boot_image(image(tmp_path, "candidate.img", header_size=1648), PROFILE)
    with pytest.raises(BootImageError, match="header_size mismatch"):
        require_candidate_compatible(report, PROFILE)


def test_rejects_truncated_page_aligned_payload(tmp_path):
    report = inspect_boot_image(image(tmp_path, "candidate.img", truncate_by=1), PROFILE)
    assert report.expected_payload_end == 16384
    with pytest.raises(BootImageError, match="truncated"):
        require_candidate_compatible(report, PROFILE)


def test_rejects_inconsistent_recovery_dtbo_offset(tmp_path):
    report = inspect_boot_image(
        image(
            tmp_path,
            "candidate.img",
            recovery_dtbo_size=32,
            recovery_dtbo_offset=4096,
        ),
        PROFILE,
    )
    with pytest.raises(BootImageError, match="recovery_dtbo_offset"):
        require_candidate_compatible(report, PROFILE)


def test_stock_candidate_pair_must_differ(tmp_path):
    p = image(tmp_path, "stock.img")
    stock = inspect_boot_image(p, PROFILE)
    candidate = inspect_boot_image(p, PROFILE)
    with pytest.raises(BootImageError):
        require_stock_candidate_pair(stock, candidate, PROFILE)


def test_stock_candidate_pair_accepts_structural_match(tmp_path):
    stock = inspect_boot_image(image(tmp_path, "stock.img", marker=b"stock"), PROFILE)
    candidate = inspect_boot_image(image(tmp_path, "candidate.img", marker=b"candidate"), PROFILE)
    require_stock_candidate_pair(stock, candidate, PROFILE)
