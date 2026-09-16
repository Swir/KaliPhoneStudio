from copy import deepcopy
import json
from pathlib import Path

import pytest

from kaliphonestudio.profiles import (
    PROFILE_SCHEMA_VERSION,
    ProfileError,
    discover_profiles,
    load_profile,
    validate_profile,
)


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "devices" / "oneplus" / "avicii" / "profile.json"


def _profile() -> dict:
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def test_repository_profiles_satisfy_schema_contract():
    profiles = discover_profiles(ROOT / "devices")
    assert profiles
    assert profiles[0].data["schema_version"] == PROFILE_SCHEMA_VERSION
    assert profiles[0].ramdisk_compression == "lz4"


def test_profile_requires_recovery_and_hardware_contract():
    data = _profile()
    del data["recovery_notes"]
    with pytest.raises(ProfileError, match="recovery_notes"):
        validate_profile(data)

    data = _profile()
    data["test_contract"]["hardware_beta"] = []
    with pytest.raises(ProfileError, match="hardware_beta"):
        validate_profile(data)


def test_profile_sources_must_be_commit_pinned_and_https():
    data = deepcopy(_profile())
    data["sources"][0]["commit"] = "lineage-22.1"
    with pytest.raises(ProfileError, match="40-character"):
        validate_profile(data)

    data = deepcopy(_profile())
    data["sources"][0]["url"] = "http://example.invalid/source"
    with pytest.raises(ProfileError, match="HTTPS"):
        validate_profile(data)


def test_profile_requires_firmware_hints():
    data = _profile()
    data["firmware_hints"] = []
    with pytest.raises(ProfileError, match="firmware_hints"):
        validate_profile(data)


def test_profile_id_rejects_path_traversal_like_identifiers():
    data = _profile()
    data["profile_id"] = "../avicii"
    with pytest.raises(ProfileError, match="safe lowercase"):
        validate_profile(data)


def test_boot_contract_is_strict_and_profile_driven():
    for key in (
        "header_version",
        "page_size",
        "kernel_image",
        "include_dtb",
        "separate_dtbo",
        "ramdisk_compression",
    ):
        data = deepcopy(_profile())
        del data["boot"][key]
        with pytest.raises(ProfileError, match="missing boot fields"):
            validate_profile(data)

    data = deepcopy(_profile())
    data["boot"]["header_version"] = "2"
    with pytest.raises(ProfileError, match="header_version"):
        validate_profile(data)

    data = deepcopy(_profile())
    data["boot"]["page_size"] = 3000
    with pytest.raises(ProfileError, match="power of two"):
        validate_profile(data)

    data = deepcopy(_profile())
    data["boot"]["kernel_image"] = "../Image"
    with pytest.raises(ProfileError, match="safe basename"):
        validate_profile(data)

    data = deepcopy(_profile())
    data["boot"]["include_dtb"] = 1
    with pytest.raises(ProfileError, match="include_dtb"):
        validate_profile(data)

    data = deepcopy(_profile())
    data["boot"]["ramdisk_compression"] = "auto"
    with pytest.raises(ProfileError, match="ramdisk_compression"):
        validate_profile(data)


def test_ab_contract_rejects_duplicate_or_unsafe_partition_names():
    data = deepcopy(_profile())
    data["ab_partitions"].append(data["ab_partitions"][0])
    with pytest.raises(ProfileError, match="duplicates"):
        validate_profile(data)

    data = deepcopy(_profile())
    data["partition_limits"]["../boot"] = data["partition_limits"].pop("boot")
    with pytest.raises(ProfileError, match="unsafe partition"):
        validate_profile(data)


def test_profile_id_must_match_registry_path(tmp_path: Path):
    profile_path = tmp_path / "devices" / "wrong" / "path" / "profile.json"
    profile_path.parent.mkdir(parents=True)
    profile_path.write_text(json.dumps(_profile()), encoding="utf-8")
    with pytest.raises(ProfileError, match="does not match"):
        load_profile(profile_path)
