from copy import deepcopy
import json
from pathlib import Path

import pytest

from kaliphonestudio.functional_hardware_contract import (
    FunctionalHardwareContractError,
    functional_hardware_contract_sha256,
    validate_functional_hardware_contract,
)
from kaliphonestudio.profiles import ProfileError, validate_profile

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "devices" / "oneplus" / "avicii" / "profile.json"


def _profile_data(path: Path = PROFILE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _contract():
    return _profile_data()["test_contract"]["functional_hardware"]


def test_every_repository_device_profile_has_a_strict_functional_hardware_contract():
    profile_paths = sorted((ROOT / "devices").glob("*/*/profile.json"))
    assert profile_paths, "at least one device profile is required"
    for path in profile_paths:
        data = _profile_data(path)
        assert "test_contract" in data, f"{path}: missing test_contract"
        assert "functional_hardware" in data["test_contract"], f"{path}: missing functional_hardware contract"
        normalized = validate_functional_hardware_contract(data["test_contract"]["functional_hardware"])
        assert normalized["tests"], f"{path}: functional hardware test list is empty"
        validate_profile(data)


def test_runtime_profile_validation_requires_functional_hardware_contract():
    data = _profile_data()
    del data["test_contract"]["functional_hardware"]
    with pytest.raises(ProfileError, match="functional_hardware is required"):
        validate_profile(data)


def test_runtime_profile_validation_rejects_unsafe_functional_hardware_policy():
    data = _profile_data()
    data["test_contract"]["functional_hardware"]["tests"][0]["persistent_write_allowed"] = True
    with pytest.raises(ProfileError, match="functional_hardware is invalid"):
        validate_profile(data)


def test_avicii_functional_hardware_contract_is_strict_and_deterministic():
    contract = _contract()
    normalized = validate_functional_hardware_contract(contract)
    assert normalized["schema_version"] == 1
    assert len(normalized["tests"]) >= 7
    assert any(item["required_for_beta"] for item in normalized["tests"])
    assert all(item["manual_review_required"] for item in normalized["tests"])
    assert all(not item["destructive"] and not item["persistent_write_allowed"] for item in normalized["tests"])
    assert functional_hardware_contract_sha256(contract) == functional_hardware_contract_sha256(deepcopy(contract))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("manual_review_required", False, "manual_review_required"),
        ("destructive", True, "destructive"),
        ("persistent_write_allowed", True, "persistent_write_allowed"),
        ("required_for_beta", "yes", "required_for_beta"),
        ("id", "../unsafe", "safe lowercase"),
    ],
)
def test_functional_hardware_contract_rejects_unsafe_test_permissions(field, value, message):
    contract = deepcopy(_contract())
    contract["tests"][0][field] = value
    with pytest.raises(FunctionalHardwareContractError, match=message):
        validate_functional_hardware_contract(contract)


def test_functional_hardware_contract_rejects_duplicates_unknown_signals_and_empty_observations():
    contract = deepcopy(_contract())
    contract["tests"].append(deepcopy(contract["tests"][0]))
    with pytest.raises(FunctionalHardwareContractError, match="unique"):
        validate_functional_hardware_contract(contract)

    contract = deepcopy(_contract())
    contract["tests"][0]["required_context_signals"] = ["made_up_signal"]
    with pytest.raises(FunctionalHardwareContractError, match="unsupported signal"):
        validate_functional_hardware_contract(contract)

    contract = deepcopy(_contract())
    contract["tests"][0]["required_observations"] = []
    with pytest.raises(FunctionalHardwareContractError, match="non-empty"):
        validate_functional_hardware_contract(contract)
