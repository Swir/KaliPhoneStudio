from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from kaliphonestudio.profile_registry_audit import (
    ProfileRegistryAuditError,
    audit_profile_registry,
    main as audit_main,
)
from kaliphonestudio.profiles import ProfileError, discover_profiles, identify_profile


ROOT = Path(__file__).resolve().parents[1]
DEVICES = ROOT / "devices"
SOURCE_PROFILE = DEVICES / "oneplus" / "avicii" / "profile.json"


def _load_source() -> dict[str, object]:
    return json.loads(SOURCE_PROFILE.read_text(encoding="utf-8"))


def _write_profile(root: Path, data: dict[str, object]) -> None:
    vendor, codename = str(data["profile_id"]).split("/", 1)
    destination = root / vendor / codename / "profile.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")


def _real_registry_copy(root: Path) -> dict[str, object]:
    original = _load_source()
    _write_profile(root, original)
    return original


def _second_profile(
    *,
    confirmation: str = "EX100",
    board: str = "billie-board",
    product_values: list[str] | None = None,
) -> dict[str, object]:
    data = deepcopy(_load_source())
    data.update(
        {
            "profile_id": "example/billie",
            "vendor": "Example",
            "display_name": "Example Billie EX100",
            "codename": "billie",
            "model": "EX100",
            "confirmation_text": confirmation,
            "aliases": ["Billie Phone", "BilliePhone", board],
            "bootloader_board_name": board,
            "firmware_hints": ["billie", "EX100"],
        }
    )
    data["identity_signals"] = {
        "schema_version": 1,
        "product": {
            "strength": "strong",
            "values": product_values if product_values is not None else ["billie"],
        },
        "model": {"strength": "strong", "values": ["EX100", "Billie Phone", "BilliePhone"]},
        "board": {"strength": "weak", "values": [board]},
    }
    return data


def test_real_registry_passes_fail_closed_audit():
    result = audit_profile_registry(DEVICES)
    assert result.schema_version == 2
    assert result.status == "pass"
    assert result.profile_count >= 1
    assert "oneplus/avicii" in result.profile_ids
    assert result.identity_probe_count >= result.profile_count * 3
    assert result.strong_identity_probe_count >= result.profile_count * 2
    assert result.weak_identity_probe_count >= result.profile_count
    assert result.canonical_identity_bundle_count == result.profile_count
    assert result.confirmation_tokens_unique is True
    assert result.weak_identity_alone_allowed is False
    assert result.ambiguous_identity_allowed is False
    assert result.physical_interaction_performed is False
    assert result.external_device_command_executed is False
    assert result.storage_target_selected is False
    assert result.persistent_write_authorized is False
    assert result.phone_storage_written is False
    assert result.hardware_verified is False
    assert result.beta_gate_credit is False


def test_duplicate_confirmation_token_is_rejected(tmp_path: Path):
    root = tmp_path / "devices"
    original = _real_registry_copy(root)
    _write_profile(root, _second_profile(confirmation=str(original["confirmation_text"])))

    with pytest.raises(ProfileRegistryAuditError, match="confirmation_text collision"):
        audit_profile_registry(root)


def test_confirmation_token_collision_is_casefolded(tmp_path: Path):
    root = tmp_path / "devices"
    original = _real_registry_copy(root)
    _write_profile(root, _second_profile(confirmation=str(original["confirmation_text"]).lower()))

    with pytest.raises(ProfileRegistryAuditError, match="confirmation_text collision"):
        audit_profile_registry(root)


def test_generic_confirmation_token_is_rejected(tmp_path: Path):
    root = tmp_path / "devices"
    original = _real_registry_copy(root)
    original["confirmation_text"] = "YES"
    _write_profile(root, original)

    with pytest.raises(ProfileRegistryAuditError, match="profile-specific"):
        audit_profile_registry(root)


def test_cross_profile_strong_product_collision_is_rejected(tmp_path: Path):
    root = tmp_path / "devices"
    _real_registry_copy(root)
    second = _second_profile(product_values=["billie", "avicii"])
    _write_profile(root, second)

    with pytest.raises(ProfileRegistryAuditError, match="strong identity probe"):
        audit_profile_registry(root)


def test_shared_weak_bootloader_board_is_allowed_but_cannot_identify(tmp_path: Path):
    root = tmp_path / "devices"
    _real_registry_copy(root)
    _write_profile(root, _second_profile(board="lito"))

    result = audit_profile_registry(root)
    assert result.status == "pass"
    assert result.shared_weak_identity_value_count == 1
    assert result.weak_identity_alone_allowed is False

    profiles = discover_profiles(root)
    with pytest.raises(ProfileError, match="got 0"):
        identify_profile(profiles, board="lito")
    assert identify_profile(profiles, product="avicii", board="lito").profile_id == "oneplus/avicii"
    assert identify_profile(profiles, product="billie", board="lito").profile_id == "example/billie"


def test_weak_value_cannot_shadow_a_strong_value_for_same_signal(tmp_path: Path):
    root = tmp_path / "devices"
    original = _real_registry_copy(root)
    original["identity_signals"]["board"]["strength"] = "strong"
    _write_profile(root, original)
    second = _second_profile(board="lito")
    _write_profile(root, second)

    with pytest.raises(ProfileRegistryAuditError, match="weak identity probe"):
        audit_profile_registry(root)


def test_cli_json_reports_typed_identity_and_safety_boundaries(capsys: pytest.CaptureFixture[str]):
    assert audit_main(["--devices-root", str(DEVICES), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "pass"
    assert payload["strong_identity_probe_count"] >= 2
    assert payload["weak_identity_probe_count"] >= 1
    assert payload["weak_identity_alone_allowed"] is False
    assert payload["ambiguous_identity_allowed"] is False
    assert payload["physical_interaction_performed"] is False
    assert payload["external_device_command_executed"] is False
    assert payload["persistent_write_authorized"] is False
    assert payload["hardware_verified"] is False
    assert payload["beta_gate_credit"] is False


def test_empty_registry_fails_closed(tmp_path: Path):
    root = tmp_path / "devices"
    root.mkdir()
    with pytest.raises(ProfileRegistryAuditError, match="registry is empty"):
        audit_profile_registry(root)
