from copy import deepcopy
import json
from pathlib import Path

import pytest

from kaliphonestudio.profiles import PROFILE_SCHEMA_VERSION, ProfileError, discover_profiles, validate_profile


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "devices" / "oneplus" / "avicii" / "profile.json"
SCHEMA_PATH = ROOT / "devices" / "profile.schema.json"


def _profile() -> dict:
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def test_repository_profiles_satisfy_schema_contract():
    profiles = discover_profiles(ROOT / "devices")
    assert profiles
    assert profiles[0].data["schema_version"] == PROFILE_SCHEMA_VERSION == 3


def test_formal_schema_declares_same_profile_version_and_typed_identity_contract():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["properties"]["schema_version"]["const"] == PROFILE_SCHEMA_VERSION
    assert "identity_signals" in schema["required"]
    identity = schema["$defs"]["identitySignals"]
    assert set(identity["properties"]) == {"schema_version", "product", "model", "board"}
    assert identity["properties"]["schema_version"]["const"] == 1


def test_profile_requires_recovery_and_hardware_contract():
    data = _profile()
    del data["recovery_notes"]
    with pytest.raises(ProfileError, match="recovery_notes"):
        validate_profile(data)

    data = _profile()
    data["test_contract"]["hardware_beta"] = []
    with pytest.raises(ProfileError, match="hardware_beta"):
        validate_profile(data)


def test_profile_sources_must_be_commit_pinned_https_and_unique():
    data = deepcopy(_profile())
    data["sources"][0]["commit"] = "lineage-22.1"
    with pytest.raises(ProfileError, match="40-character"):
        validate_profile(data)

    data = deepcopy(_profile())
    data["sources"][0]["url"] = "http://example.invalid/device-tree"
    with pytest.raises(ProfileError, match="HTTPS"):
        validate_profile(data)

    data = deepcopy(_profile())
    data["sources"][1]["name"] = data["sources"][0]["name"]
    with pytest.raises(ProfileError, match="source names must be unique"):
        validate_profile(data)


def test_profile_requires_firmware_hints():
    data = _profile()
    data["firmware_hints"] = []
    with pytest.raises(ProfileError, match="firmware_hints"):
        validate_profile(data)


def test_identity_contract_requires_strong_product_and_canonical_values():
    data = deepcopy(_profile())
    data["identity_signals"]["product"]["strength"] = "weak"
    with pytest.raises(ProfileError, match="product must be declared as a strong"):
        validate_profile(data)

    data = deepcopy(_profile())
    data["identity_signals"]["product"]["values"] = ["different"]
    with pytest.raises(ProfileError, match="include profile codename"):
        validate_profile(data)

    data = deepcopy(_profile())
    data["identity_signals"]["model"]["values"] = ["different"]
    with pytest.raises(ProfileError, match="include profile model"):
        validate_profile(data)

    data = deepcopy(_profile())
    data["identity_signals"]["board"]["values"] = ["different"]
    with pytest.raises(ProfileError, match="include bootloader_board_name"):
        validate_profile(data)


def test_identity_values_and_aliases_are_normalization_safe():
    data = deepcopy(_profile())
    data["identity_signals"]["model"]["values"] = ["AC2003", " ac2003 "]
    with pytest.raises(ProfileError, match="unique after normalization"):
        validate_profile(data)

    data = deepcopy(_profile())
    data["aliases"] = ["OnePlus Nord", " oneplus nord "]
    with pytest.raises(ProfileError, match="aliases must be unique"):
        validate_profile(data)

    data = deepcopy(_profile())
    data["aliases"] = ["undeclared-display-alias"]
    with pytest.raises(ProfileError, match="also be declared in identity_signals"):
        validate_profile(data)


def test_identity_contract_rejects_unknown_signals_and_fields():
    data = deepcopy(_profile())
    data["identity_signals"]["usb"] = {"strength": "strong", "values": ["x"]}
    with pytest.raises(ProfileError, match="unsupported signals"):
        validate_profile(data)

    data = deepcopy(_profile())
    data["identity_signals"]["product"]["comment"] = "not part of safety contract"
    with pytest.raises(ProfileError, match="only strength and values"):
        validate_profile(data)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("header_version", "2", "header_version"),
        ("page_size", 3000, "power of two"),
        ("kernel_image", "", "kernel_image"),
        ("include_dtb", 1, "include_dtb"),
        ("separate_dtbo", "yes", "separate_dtbo"),
        ("ramdisk_compression", "auto", "ramdisk_compression"),
    ],
)
def test_boot_contract_is_strictly_typed_and_bounded(field, value, message):
    data = deepcopy(_profile())
    data["boot"][field] = value
    with pytest.raises(ProfileError, match=message):
        validate_profile(data)


def test_ab_contract_requires_safe_unique_boot_partition():
    data = deepcopy(_profile())
    data["ab_partitions"] = ["system", "system"]
    with pytest.raises(ProfileError, match="duplicates"):
        validate_profile(data)

    data = deepcopy(_profile())
    data["ab_partitions"] = ["system", "vendor"]
    with pytest.raises(ProfileError, match="boot"):
        validate_profile(data)

    data = deepcopy(_profile())
    data["ab_partitions"] = ["boot", "../vbmeta"]
    with pytest.raises(ProfileError, match="unsafe"):
        validate_profile(data)


def test_profile_id_vendor_and_codename_must_match_and_use_safe_components():
    data = deepcopy(_profile())
    data["profile_id"] = "oneplus/different"
    with pytest.raises(ProfileError, match="codename"):
        validate_profile(data)

    data = deepcopy(_profile())
    data["vendor"] = "different-vendor"
    with pytest.raises(ProfileError, match="vendor"):
        validate_profile(data)

    data = deepcopy(_profile())
    data["profile_id"] = "OnePlus/avicii"
    with pytest.raises(ProfileError, match="lowercase"):
        validate_profile(data)


def test_kernel_contract_resolves_exactly_one_pinned_source_and_matches_boot_contract():
    data = deepcopy(_profile())
    data["kernel"]["source_name"] = "missing kernel source"
    with pytest.raises(ProfileError, match="resolve exactly one"):
        validate_profile(data)

    data = deepcopy(_profile())
    data["kernel"]["arch"] = "x86_64"
    with pytest.raises(ProfileError, match="kernel.arch"):
        validate_profile(data)

    data = deepcopy(_profile())
    data["kernel"]["image_name"] = "Image.gz"
    with pytest.raises(ProfileError, match="kernel.image_name"):
        validate_profile(data)


def test_kernel_contract_rejects_unsafe_paths_flags_and_config_requirements():
    data = deepcopy(_profile())
    data["kernel"]["defconfig"] = "../escape_defconfig"
    with pytest.raises(ProfileError, match="kernel.defconfig"):
        validate_profile(data)

    data = deepcopy(_profile())
    data["kernel"]["config_fragments"] = ["vendor/debugfs.config", "vendor/debugfs.config"]
    with pytest.raises(ProfileError, match="duplicates"):
        validate_profile(data)

    data = deepcopy(_profile())
    data["kernel"]["make_flags"] = {"ARCH;rm": "arm64"}
    with pytest.raises(ProfileError, match="unsafe variable"):
        validate_profile(data)

    data = deepcopy(_profile())
    data["kernel"]["required_configs"] = {"NOT_A_CONFIG": "y"}
    with pytest.raises(ProfileError, match="invalid CONFIG_"):
        validate_profile(data)

    data = deepcopy(_profile())
    data["kernel"]["required_configs"] = {"CONFIG_SECCOMP": "auto"}
    with pytest.raises(ProfileError, match="must be y, m or n"):
        validate_profile(data)
