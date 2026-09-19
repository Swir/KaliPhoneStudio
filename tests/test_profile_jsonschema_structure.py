from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "devices" / "oneplus" / "avicii" / "profile.json"
SCHEMA_PATH = ROOT / "devices" / "profile.schema.json"


def _validator():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def _profile() -> dict:
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def _messages(payload: dict) -> str:
    errors = sorted(_validator().iter_errors(payload), key=lambda error: list(error.absolute_path))
    return "\n".join(error.message for error in errors)


def test_checked_in_avicii_profile_passes_formal_nested_schema():
    assert list(_validator().iter_errors(_profile())) == []


def test_unknown_top_level_profile_field_fails_closed():
    payload = deepcopy(_profile())
    payload["future_magic_support"] = True
    assert "Additional properties are not allowed" in _messages(payload)


def test_boot_fastboot_and_ab_shapes_fail_closed_before_runtime_semantics():
    payload = deepcopy(_profile())
    payload["boot"]["ramdisk_compression"] = "auto"
    assert "is not one of" in _messages(payload)

    payload = deepcopy(_profile())
    del payload["fastboot_probe"]["serial_var"]
    assert "'serial_var' is a required property" in _messages(payload)

    payload = deepcopy(_profile())
    payload["ab_partitions"] = ["system", "vendor"]
    assert "does not contain items matching" in _messages(payload)


def test_kernel_and_device_tree_nested_contracts_reject_shape_drift():
    payload = deepcopy(_profile())
    payload["kernel"]["expected_version"] = "4.19"
    assert "does not match" in _messages(payload)

    payload = deepcopy(_profile())
    payload["kernel"]["required_configs"]["NOT_A_CONFIG"] = "y"
    assert "does not match" in _messages(payload)

    payload = deepcopy(_profile())
    payload["device_tree"]["dtbo_page_size"] = 0
    assert "less than the minimum" in _messages(payload)


def test_functional_hardware_schema_preserves_non_destructive_beta_contract():
    payload = deepcopy(_profile())
    test = payload["test_contract"]["functional_hardware"]["tests"][0]
    test["destructive"] = True
    assert "False was expected" in _messages(payload)

    payload = deepcopy(_profile())
    for test in payload["test_contract"]["functional_hardware"]["tests"]:
        test["required_for_beta"] = False
    assert "does not contain items matching" in _messages(payload)

    payload = deepcopy(_profile())
    test = payload["test_contract"]["functional_hardware"]["tests"][0]
    test["required_context_signals"] = ["unapproved_signal"]
    assert "is not one of" in _messages(payload)


def test_rootfs_discovery_contract_cannot_silently_authorize_selection_or_writes():
    payload = deepcopy(_profile())
    payload["rootfs_handoff"]["target_selection_allowed"] = True
    assert "False was expected" in _messages(payload)

    payload = deepcopy(_profile())
    payload["rootfs_handoff"]["persistent_write_authorized"] = True
    assert "False was expected" in _messages(payload)

    payload = deepcopy(_profile())
    payload["rootfs_handoff"]["layout_source_path"] = "../escape.xml"
    assert "does not match" in _messages(payload)
