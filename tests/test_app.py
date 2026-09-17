from __future__ import annotations

import json
from pathlib import Path

from kaliphonestudio import app
from kaliphonestudio.operator_diagnostics import load_operator_bundle


DEVICES_ROOT = Path(__file__).resolve().parents[1] / "devices"


def test_profile_catalog_lists_validated_avicii_profile() -> None:
    catalog = app.load_profile_catalog(DEVICES_ROOT)
    matches = [item for item in catalog if item.profile_id == "oneplus/avicii"]
    assert len(matches) == 1
    item = matches[0]
    assert item.model == "AC2003"
    assert item.arch == "arm64"
    assert item.ramdisk_compression == "lz4"
    assert item.ab_device is True
    assert item.hardware_beta_test_count > 0


def test_list_profiles_json_is_machine_readable_and_deterministic(capsys) -> None:
    rc = app.main(["--devices-root", str(DEVICES_ROOT), "--list-profiles", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert [item["profile_id"] for item in payload] == sorted(item["profile_id"] for item in payload)
    avicii = next(item for item in payload if item["profile_id"] == "oneplus/avicii")
    assert avicii["display_name"] == "OnePlus Nord AC2003"
    assert avicii["boot_header_version"] == 2


def test_profile_json_never_claims_hardware_or_beta_credit(capsys) -> None:
    rc = app.main(
        [
            "--devices-root",
            str(DEVICES_ROOT),
            "--profile-id",
            "oneplus/avicii",
            "--json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["profile_id"] == "oneplus/avicii"
    assert payload["hardware_verified"] is False
    assert payload["beta_gate_credit"] is False


def test_unknown_profile_fails_closed(capsys) -> None:
    rc = app.main(
        ["--devices-root", str(DEVICES_ROOT), "--profile-id", "unknown/device", "--json"]
    )
    assert rc == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "unknown profile" in captured.err.lower()


def test_doctor_json_is_offline_and_non_promoting(capsys) -> None:
    rc = app.main(
        [
            "--devices-root",
            str(DEVICES_ROOT),
            "--doctor",
            "--profile-id",
            "oneplus/avicii",
            "--json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["selected_profile_id"] == "oneplus/avicii"
    assert payload["physical_interaction_performed"] is False
    assert payload["hardware_verified"] is False
    assert payload["beta_gate_credit"] is False
    assert payload["beta_gate"] == "BLOCKED"


def test_recovery_guide_requires_profile(capsys) -> None:
    rc = app.main(["--devices-root", str(DEVICES_ROOT), "--recovery-guide"])
    assert rc == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "requires --profile-id" in captured.err


def test_recovery_guide_json_is_profile_driven_and_non_promoting(capsys) -> None:
    rc = app.main(
        [
            "--devices-root",
            str(DEVICES_ROOT),
            "--recovery-guide",
            "--profile-id",
            "oneplus/avicii",
            "--json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["profile_id"] == "oneplus/avicii"
    assert payload["preferred_boot_mode"] == "temporary-fastboot-boot"
    assert payload["persistent_write_authorized"] is False
    assert payload["hardware_verified"] is False
    assert payload["beta_gate_credit"] is False


def test_export_diagnostics_writes_valid_redacted_bundle(tmp_path: Path, capsys) -> None:
    destination = tmp_path / "operator-diagnostics.json"
    rc = app.main(
        [
            "--devices-root",
            str(DEVICES_ROOT),
            "--export-diagnostics",
            str(destination),
            "--profile-id",
            "oneplus/avicii",
            "--json",
        ]
    )
    assert rc == 0
    cli_result = json.loads(capsys.readouterr().out)
    assert cli_result["path"] == str(destination)
    assert len(cli_result["sha256"]) == 64
    assert cli_result["hardware_verified"] is False
    assert cli_result["beta_gate_credit"] is False

    bundle = load_operator_bundle(destination)
    assert bundle["diagnostics"]["selected_profile_id"] == "oneplus/avicii"
    assert bundle["recovery_guide"]["profile_id"] == "oneplus/avicii"
    assert bundle["privacy"]["external_commands_executed"] is False
    assert bundle["privacy"]["device_queried"] is False
    assert bundle["privacy"]["absolute_tool_paths_exported"] is False


def test_importing_app_does_not_require_qt() -> None:
    # PySide6 is deliberately absent from the minimal tests.yml environment;
    # importing the application must therefore remain safe for CLI/CI use.
    assert callable(app.main)
    assert callable(app.load_profile_catalog)
