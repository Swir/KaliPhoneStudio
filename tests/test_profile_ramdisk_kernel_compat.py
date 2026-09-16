import copy
import json
from pathlib import Path

import pytest

from kaliphonestudio.profiles import ProfileError, validate_profile


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "devices" / "oneplus" / "avicii" / "profile.json"


def _data():
    return json.loads(PROFILE.read_text(encoding="utf-8"))


def test_avicii_profile_passes_ramdisk_kernel_compatibility_contract():
    data = _data()
    validate_profile(data)
    assert data["boot"]["ramdisk_compression"] == "lz4"
    assert data["kernel"]["required_configs"]["CONFIG_BLK_DEV_INITRD"] == "y"
    assert data["kernel"]["required_configs"]["CONFIG_RD_LZ4"] == "y"


def test_lz4_profile_rejects_missing_or_disabled_kernel_decompressor():
    for bad in (None, "n", "m"):
        data = copy.deepcopy(_data())
        if bad is None:
            data["kernel"]["required_configs"].pop("CONFIG_RD_LZ4")
        else:
            data["kernel"]["required_configs"]["CONFIG_RD_LZ4"] = bad
        with pytest.raises(ProfileError, match="CONFIG_RD_LZ4 must be y"):
            validate_profile(data)


def test_compressed_ramdisk_requires_initrd_support():
    data = copy.deepcopy(_data())
    data["kernel"]["required_configs"]["CONFIG_BLK_DEV_INITRD"] = "n"
    with pytest.raises(ProfileError, match="CONFIG_BLK_DEV_INITRD must be y"):
        validate_profile(data)


def test_gzip_profile_requires_gzip_decompressor_generically():
    data = copy.deepcopy(_data())
    data["boot"]["ramdisk_compression"] = "gzip"
    data["kernel"]["required_configs"].pop("CONFIG_RD_LZ4")
    data["kernel"]["required_configs"]["CONFIG_RD_GZIP"] = "y"
    validate_profile(data)

    data["kernel"]["required_configs"]["CONFIG_RD_GZIP"] = "n"
    with pytest.raises(ProfileError, match="CONFIG_RD_GZIP must be y"):
        validate_profile(data)


def test_uncompressed_ramdisk_does_not_require_a_decompressor_symbol():
    data = copy.deepcopy(_data())
    data["boot"]["ramdisk_compression"] = "none"
    data["kernel"]["required_configs"].pop("CONFIG_RD_LZ4")
    validate_profile(data)
