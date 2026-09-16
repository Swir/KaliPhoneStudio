from __future__ import annotations

import json
from pathlib import Path

from kaliphonestudio import app


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


def test_importing_app_does_not_require_qt() -> None:
    # PySide6 is deliberately absent from the minimal tests.yml environment;
    # importing the application must therefore remain safe for CLI/CI use.
    assert callable(app.main)
    assert callable(app.load_profile_catalog)
