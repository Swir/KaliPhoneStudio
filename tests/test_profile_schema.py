from copy import deepcopy
import json
from pathlib import Path

import pytest

from kaliphonestudio.profiles import PROFILE_SCHEMA_VERSION, ProfileError, discover_profiles, validate_profile


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "devices" / "oneplus" / "avicii" / "profile.json"


def _profile() -> dict:
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def test_repository_profiles_satisfy_schema_contract():
    profiles = discover_profiles(ROOT / "devices")
    assert profiles
    assert profiles[0].data["schema_version"] == PROFILE_SCHEMA_VERSION


def test_profile_requires_recovery_and_hardware_contract():
    data = _profile()
    del data["recovery_notes"]
    with pytest.raises(ProfileError, match="recovery_notes"):
        validate_profile(data)

    data = _profile()
    data["test_contract"]["hardware_beta"] = []
    with pytest.raises(ProfileError, match="hardware_beta"):
        validate_profile(data)


def test_profile_sources_must_be_commit_pinned():
    data = deepcopy(_profile())
    data["sources"][0]["commit"] = "lineage-22.1"
    with pytest.raises(ProfileError, match="40-character"):
        validate_profile(data)


def test_profile_requires_firmware_hints():
    data = _profile()
    data["firmware_hints"] = []
    with pytest.raises(ProfileError, match="firmware_hints"):
        validate_profile(data)
