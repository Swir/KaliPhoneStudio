from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]


def project_version() -> str:
    text = (ROOT / "kaliphonestudio" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    assert match, "kaliphonestudio.__version__ must be declared"
    return match.group(1)


def test_project_version_is_consistent_with_build_status():
    status = json.loads((ROOT / "BUILD_STATUS.json").read_text(encoding="utf-8"))
    assert project_version() == status["version"]


def test_current_version_is_consistent_across_active_status_docs():
    version = project_version()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert f"Current development line: `{version}`" in readme
    assert f"Current development line — {version}" in roadmap
    assert f"## {version} " in changelog


def test_progress_is_consistent_across_active_status_docs():
    status = json.loads((ROOT / "BUILD_STATUS.json").read_text(encoding="utf-8"))
    progress = status["project_progress_percent"]
    assert isinstance(progress, int) and 0 <= progress <= 100

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    assert f"**{progress}% complete**" in readme
    assert f"**{progress}% complete**" in roadmap


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
