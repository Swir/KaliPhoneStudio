from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]


def test_project_version_exists():
    text = (ROOT / "kaliphonestudio" / "__init__.py").read_text(encoding="utf-8")
    assert "0.6.0-dev" in text


def test_first_device_profile_contract():
    path = ROOT / "devices" / "oneplus" / "avicii" / "profile.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["profile_id"] == "oneplus/avicii"
    assert data["model"] == "AC2003"
    assert data["codename"] == "avicii"
    assert data["confirmation_text"] == "AC2003"
    assert data["boot"]["header_version"] == 2
    assert data["partition_limits"]["boot"] > 0


def test_beta_gate_is_present():
    gate = (ROOT / "BETA_RELEASE_GATE.md").read_text(encoding="utf-8")
    assert "temporary boot" in gate.lower()
    assert "recovery" in gate.lower()
