from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = ROOT / "scripts" / "preflight_ac2003_first_test.ps1"
PACKAGER = ROOT / "scripts" / "package_windows_beta_test_candidate.ps1"
WORKFLOW = ROOT / ".github" / "workflows" / "windows-beta-test-candidate.yml"


def test_host_preflight_is_integrity_first_exact_fastboot_and_device_free() -> None:
    text = PREFLIGHT.read_text(encoding="utf-8")

    for needle in (
        "operator-pack\\verify-candidate.ps1",
        "operator-pack\\fastboot-tool-policy.json",
        "KaliPhoneStudioCLI\\KaliPhoneStudioCLI.exe",
        "operator-tools\\payload-dumper-go.exe",
        "Get-FileHash -Algorithm SHA256",
        'version_policy -ne "exact"',
        "platform_tools_version",
        "& $FastbootPath --version",
        "Candidate integrity: PASS",
        "Device command executed: false",
        "Persistent phone write authorized: false",
        "Hardware verified: false",
        "Beta gate credit: false",
    ):
        assert needle in text

    lowered = text.lower()
    for forbidden in (
        "fastboot devices",
        "fastboot getvar",
        "fastboot boot ",
        "fastboot flash ",
        "fastboot erase ",
        "fastboot set_active ",
        "adb ",
        "invoke-webrequest",
        "invoke-restmethod",
    ):
        assert forbidden not in lowered


def test_windows_candidate_packages_and_executes_host_preflight_smoke() -> None:
    text = PACKAGER.read_text(encoding="utf-8")

    for needle in (
        '"scripts/preflight_ac2003_first_test.ps1" = "host-preflight.ps1"',
        ".\\operator-pack\\host-preflight.ps1",
        "-FastbootExecutable",
        "host_preflight_included = $true",
        "host_preflight_device_interaction = $false",
        "fastboot.cmd",
        "platform_tools_version",
        "kps-packaging-smoke",
        "AC2003 host preflight packaging smoke failed",
        "Host-only AC2003 preflight: PASS",
    ):
        assert needle in text

    assert "fastboot --version" in text
    for forbidden in ("fastboot flash ", "fastboot erase ", "fastboot set_active "):
        assert forbidden not in text.lower()


def test_windows_candidate_ci_tracks_and_runs_host_preflight_contract() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert text.count('"scripts/preflight_ac2003_first_test.ps1"') == 2
    assert "tests/test_ac2003_host_preflight_contract.py" in text
    assert "Package, host-preflight and self-verify integrated AC2003 host test candidate" in text
