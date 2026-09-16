from pathlib import Path
import copy
import struct

import pytest

from kaliphonestudio.boot_image import BootImageError, boot_build_contract, inspect_boot_image, require_candidate_compatible, require_stock_candidate_pair
from kaliphonestudio.profiles import DeviceProfile, get_profile

ROOT = Path(__file__).parents[1]
PROFILE = get_profile(ROOT / "devices", "oneplus/avicii")


def image(tmp_path: Path, name: str, version: int = 2, marker: bytes = b"x") -> Path:
    data = bytearray(4096)
    data[:8] = b"ANDROID!"
    struct.pack_into("<I", data, 40, version)
    data[128:128 + len(marker)] = marker
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


def test_accepts_profile_header(tmp_path):
    report = inspect_boot_image(image(tmp_path, "candidate.img"), PROFILE)
    require_candidate_compatible(report, PROFILE)
    assert report.header_version == 2
    assert len(report.sha256) == 64


def test_rejects_wrong_header_version(tmp_path):
    report = inspect_boot_image(image(tmp_path, "candidate.img", version=4), PROFILE)
    with pytest.raises(BootImageError):
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
