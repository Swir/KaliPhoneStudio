from hashlib import sha256
from pathlib import Path
import copy
import struct

import pytest

from kaliphonestudio.boot_image import (
    AVB_FOOTER_SIZE,
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


def append_avb_footer(
    path: Path,
    *,
    vbmeta_magic: bytes = b"AVB0",
    auth_size: int = 0,
    aux_size: int = 0,
    footer_vbmeta_offset: int | None = None,
    footer_vbmeta_size: int | None = None,
    original_size: int | None = None,
) -> Path:
    original = path.read_bytes()
    vbmeta = bytearray(256 + auth_size + aux_size)
    struct.pack_into(">4sIIQQ", vbmeta, 0, vbmeta_magic, 1, 0, auth_size, aux_size)
    actual_offset = len(original)
    declared_offset = actual_offset if footer_vbmeta_offset is None else footer_vbmeta_offset
    declared_size = len(vbmeta) if footer_vbmeta_size is None else footer_vbmeta_size
    footer = struct.pack(
        ">4sIIQQQ28x",
        b"AVBf",
        1,
        0,
        len(original) if original_size is None else original_size,
        declared_offset,
        declared_size,
    )
    assert len(footer) == AVB_FOOTER_SIZE
    path.write_bytes(original + vbmeta + footer)
    return path


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
    assert report.avb_footer_present is False
    assert report.avb_structural_errors == ()
    assert report.kernel_sha256 == sha256(b"\0" * 32).hexdigest()
    assert report.ramdisk_sha256 == sha256(b"\0" * 24).hexdigest()
    assert report.second_sha256 is None
    assert report.dtb_sha256 == sha256(b"\0" * 16).hexdigest()
    assert len(report.sha256) == 64


def test_component_hashes_are_exact_declared_payload_bytes(tmp_path):
    path = image(tmp_path, "candidate.img")
    baseline = inspect_boot_image(path, PROFILE)
    payload = bytearray(path.read_bytes())
    payload[4096] = 0xA5
    path.write_bytes(payload)
    changed = inspect_boot_image(path, PROFILE)
    assert changed.kernel_sha256 != baseline.kernel_sha256
    assert changed.ramdisk_sha256 == baseline.ramdisk_sha256
    assert changed.dtb_sha256 == baseline.dtb_sha256


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


def test_accepts_structurally_valid_optional_avb_footer(tmp_path):
    path = append_avb_footer(image(tmp_path, "candidate.img"))
    report = inspect_boot_image(path, PROFILE)
    require_candidate_compatible(report, PROFILE)
    assert report.avb_footer_present is True
    assert report.avb_footer_version_major == 1
    assert report.avb_footer_version_minor == 0
    assert report.avb_original_image_size == 16384
    assert report.avb_vbmeta_offset == 16384
    assert report.avb_vbmeta_size == 256
    assert report.avb_vbmeta_header_valid is True
    assert report.avb_vbmeta_sha256 == sha256(path.read_bytes()[16384:16640]).hexdigest()
    assert report.avb_structural_errors == ()


def test_rejects_avb_vbmeta_range_that_escapes_before_footer(tmp_path):
    path = image(tmp_path, "candidate.img")
    original_size = path.stat().st_size
    append_avb_footer(
        path,
        footer_vbmeta_offset=original_size + 128,
        footer_vbmeta_size=256,
    )
    report = inspect_boot_image(path, PROFILE)
    with pytest.raises(BootImageError, match="vbmeta range escapes"):
        require_candidate_compatible(report, PROFILE)


def test_rejects_avb_invalid_vbmeta_magic(tmp_path):
    report = inspect_boot_image(
        append_avb_footer(image(tmp_path, "candidate.img"), vbmeta_magic=b"BAD0"),
        PROFILE,
    )
    assert report.avb_vbmeta_header_valid is False
    with pytest.raises(BootImageError, match="vbmeta magic"):
        require_candidate_compatible(report, PROFILE)


def test_rejects_avb_vbmeta_block_size_drift(tmp_path):
    path = append_avb_footer(image(tmp_path, "candidate.img"), auth_size=64)
    payload = bytearray(path.read_bytes())
    footer_offset = len(payload) - AVB_FOOTER_SIZE
    struct.pack_into(">Q", payload, footer_offset + 32, 256)
    path.write_bytes(payload)
    report = inspect_boot_image(path, PROFILE)
    with pytest.raises(BootImageError, match="block sizes"):
        require_candidate_compatible(report, PROFILE)


def test_rejects_avb_original_size_smaller_than_boot_payload(tmp_path):
    report = inspect_boot_image(
        append_avb_footer(image(tmp_path, "candidate.img"), original_size=8192),
        PROFILE,
    )
    with pytest.raises(BootImageError, match="smaller than the declared boot payload"):
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
