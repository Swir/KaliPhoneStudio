"""Profile-driven physical functional-hardware test contract.

This module defines what a device profile requires from later *physical* tests.
It never executes hardware actions and deliberately rejects destructive or
persistent-write permissions. Passing this host-side contract grants no
hardware or Beta credit.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Any


FUNCTIONAL_HARDWARE_SCHEMA_VERSION = 1
FUNCTIONAL_HARDWARE_POLICY = "profile-functional-hardware-tests-v1"
_SAFE_TEST_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_ALLOWED_CONTEXT_SIGNALS = frozenset(
    {
        "usb_signal_observed",
        "network_signal_observed",
        "wifi_signal_observed",
        "bluetooth_signal_observed",
        "audio_signal_observed",
        "thermal_signal_observed",
        "input_signal_observed",
        "display_signal_observed",
        "power_signal_observed",
    }
)
_TEST_FIELDS = frozenset(
    {
        "id",
        "required_for_beta",
        "manual_review_required",
        "destructive",
        "persistent_write_allowed",
        "required_context_signals",
        "required_observations",
    }
)


class FunctionalHardwareContractError(ValueError):
    pass


def _string_list(value: object, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise FunctionalHardwareContractError(f"{label} must be a {'possibly empty' if allow_empty else 'non-empty'} list")
    if any(not isinstance(item, str) or not item.strip() or len(item) > 512 for item in value):
        raise FunctionalHardwareContractError(f"{label} must contain bounded non-empty strings")
    if len(value) != len(set(value)):
        raise FunctionalHardwareContractError(f"{label} must not contain duplicates")
    return value


def validate_functional_hardware_contract(raw: object) -> dict[str, Any]:
    """Validate and return a normalized profile functional-test contract."""
    if not isinstance(raw, dict):
        raise FunctionalHardwareContractError("functional_hardware must be an object")
    if set(raw) != {"schema_version", "policy", "tests"}:
        raise FunctionalHardwareContractError("functional_hardware fields do not match schema-v1")
    if raw["schema_version"] != FUNCTIONAL_HARDWARE_SCHEMA_VERSION:
        raise FunctionalHardwareContractError("unsupported functional_hardware schema version")
    if raw["policy"] != FUNCTIONAL_HARDWARE_POLICY:
        raise FunctionalHardwareContractError("unsupported functional_hardware policy")
    tests = raw["tests"]
    if not isinstance(tests, list) or not tests:
        raise FunctionalHardwareContractError("functional_hardware.tests must be a non-empty list")

    normalized: list[dict[str, Any]] = []
    ids: list[str] = []
    for index, item in enumerate(tests):
        label = f"functional_hardware.tests[{index}]"
        if not isinstance(item, dict) or set(item) != _TEST_FIELDS:
            raise FunctionalHardwareContractError(f"{label} fields do not match schema-v1")
        test_id = item["id"]
        if not isinstance(test_id, str) or not _SAFE_TEST_ID_RE.fullmatch(test_id):
            raise FunctionalHardwareContractError(f"{label}.id must be a safe lowercase identifier")
        ids.append(test_id)
        for field in ("required_for_beta", "manual_review_required", "destructive", "persistent_write_allowed"):
            if not isinstance(item[field], bool):
                raise FunctionalHardwareContractError(f"{label}.{field} must be boolean")
        if item["manual_review_required"] is not True:
            raise FunctionalHardwareContractError(f"{label}.manual_review_required must be true")
        if item["destructive"] is not False:
            raise FunctionalHardwareContractError(f"{label}.destructive must be false")
        if item["persistent_write_allowed"] is not False:
            raise FunctionalHardwareContractError(f"{label}.persistent_write_allowed must be false")
        signals = _string_list(item["required_context_signals"], f"{label}.required_context_signals", allow_empty=True)
        unknown = sorted(set(signals) - _ALLOWED_CONTEXT_SIGNALS)
        if unknown:
            raise FunctionalHardwareContractError(f"{label}.required_context_signals contains unsupported signal(s): {', '.join(unknown)}")
        observations = _string_list(item["required_observations"], f"{label}.required_observations")
        normalized.append(
            {
                "id": test_id,
                "required_for_beta": item["required_for_beta"],
                "manual_review_required": True,
                "destructive": False,
                "persistent_write_allowed": False,
                "required_context_signals": list(signals),
                "required_observations": list(observations),
            }
        )

    if len(ids) != len(set(ids)):
        raise FunctionalHardwareContractError("functional_hardware test ids must be unique")
    if not any(item["required_for_beta"] for item in normalized):
        raise FunctionalHardwareContractError("functional_hardware must declare at least one Beta-required physical test")
    return {
        "schema_version": FUNCTIONAL_HARDWARE_SCHEMA_VERSION,
        "policy": FUNCTIONAL_HARDWARE_POLICY,
        "tests": normalized,
    }


def functional_hardware_contract_sha256(raw: object) -> str:
    normalized = validate_functional_hardware_contract(raw)
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":")) + "\n"
    return sha256(payload.encode("utf-8")).hexdigest()
