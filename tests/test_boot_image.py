from pathlib import Path
import struct

import pytest

from kaliphonestudio.boot_image import BootImageError, inspect_boot_image, require_candidate_compatible, require_stock_candidate_pair
from kaliphonestudio.profiles import get_profile

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
