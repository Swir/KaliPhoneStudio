from pathlib import Path
import json
import pytest

from kaliphonestudio.profiles import ProfileError, discover_profiles, identify_profile, validate_profile
from kaliphonestudio.safety import SafetyError, VerifiedDevice, inactive_slot, persistent_target, require_confirmation

ROOT = Path(__file__).resolve().parents[1]
DEVICES = ROOT / "devices"


def test_all_profiles_validate_and_ids_are_unique():
    profiles = discover_profiles(DEVICES)
    assert profiles
    assert len({p.profile_id for p in profiles}) == len(profiles)


def test_avicii_identification_is_profile_driven_and_requires_strong_signal():
    profiles = discover_profiles(DEVICES)
    assert identify_profile(profiles, product="avicii").profile_id == "oneplus/avicii"
    assert identify_profile(profiles, model="AC2003").profile_id == "oneplus/avicii"
    assert identify_profile(profiles, model="OnePlus Nord").profile_id == "oneplus/avicii"
    assert identify_profile(profiles, product="avicii", board="lito").profile_id == "oneplus/avicii"

    with pytest.raises(ProfileError, match="got 0"):
        identify_profile(profiles, board="lito")


def test_unknown_device_fails_closed():
    with pytest.raises(ProfileError):
        identify_profile(discover_profiles(DEVICES), product="definitely-unknown")


def test_profile_confirmation_token():
    profile = discover_profiles(DEVICES)[0]
    require_confirmation(profile, profile.confirmation_text)
    with pytest.raises(SafetyError):
        require_confirmation(profile, "WRONG")


def test_inactive_slot_is_deterministic():
    assert inactive_slot("a") == "b"
    assert inactive_slot("b") == "a"
    with pytest.raises(SafetyError):
        inactive_slot("x")


def test_persistent_write_targets_inactive_slot_only():
    profile = discover_profiles(DEVICES)[0]
    dev = VerifiedDevice(profile.profile_id, "SERIAL", "a", True)
    assert persistent_target(profile, dev, "boot") == "boot_b"
    with pytest.raises(SafetyError):
        persistent_target(profile, dev, "userdata")


def test_schema_rejects_missing_fields():
    data = json.loads((DEVICES / "oneplus" / "avicii" / "profile.json").read_text(encoding="utf-8"))
    data.pop("confirmation_text")
    with pytest.raises(ProfileError):
        validate_profile(data)

    data = json.loads((DEVICES / "oneplus" / "avicii" / "profile.json").read_text(encoding="utf-8"))
    data.pop("identity_signals")
    with pytest.raises(ProfileError, match="identity_signals"):
        validate_profile(data)
