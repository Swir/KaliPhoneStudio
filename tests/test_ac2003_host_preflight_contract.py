from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = ROOT / "scripts" / "preflight_ac2003_first_test.ps1"
READONLY_BASELINE = ROOT / "scripts" / "start_ac2003_readonly_baseline.ps1"
PACKAGER = ROOT / "scripts" / "package_windows_beta_test_candidate.ps1"
VERIFIER = ROOT / "scripts" / "verify_windows_beta_test_candidate.ps1"
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


def test_readonly_baseline_launcher_runs_only_guarded_first_session_path() -> None:
    text = READONLY_BASELINE.read_text(encoding="utf-8")

    for needle in (
        "operator-pack\\host-preflight.ps1",
        "operator-pack\\fastboot-tool-policy.json",
        "KaliPhoneStudioCLI\\KaliPhoneStudioCLI.exe",
        "begin-physical-test-session",
        '"--profile-id", "oneplus/avicii"',
        '"--confirm-token", "AC2003"',
        '"--fastboot-policy", $PolicyPath',
        "physical-first-test-session.json",
        "fastboot-getvar-all.txt",
        "fastboot-baseline.json",
        "fastboot-tool.json",
        "fastboot-capture-bundle.json",
        "read_only_baseline_only -ne $true",
        "temporary_boot_performed -ne $false",
        "persistent_write_authorized -ne $false",
        "phone_storage_written -ne $false",
        "hardware_verified -ne $false",
        "beta_gate_credit -ne $false",
        "Get-FileHash -Algorithm SHA256",
        "Physical interaction performed: true (read-only Fastboot baseline only)",
        "Persistent phone write authorized: false",
    ):
        assert needle in text

    lowered = text.lower()
    for forbidden in (
        "execute-temporary-boot-once",
        "--execute-temporary-boot",
        "fastboot boot ",
        "fastboot flash ",
        "fastboot erase ",
        "fastboot set_active ",
        "fastboot flashing ",
        "adb ",
        "invoke-webrequest",
        "invoke-restmethod",
    ):
        assert forbidden not in lowered


def test_windows_candidate_packages_and_executes_host_preflight_smoke() -> None:
    text = PACKAGER.read_text(encoding="utf-8")

    for needle in (
        '"scripts/preflight_ac2003_first_test.ps1" = "host-preflight.ps1"',
        '"scripts/start_ac2003_readonly_baseline.ps1" = "readonly-baseline.ps1"',
        ".\\operator-pack\\host-preflight.ps1",
        ".\\operator-pack\\readonly-baseline.ps1",
        "-FastbootExecutable",
        "host_preflight_included = $true",
        "host_preflight_device_interaction = $false",
        "readonly_baseline_launcher_included = $true",
        "readonly_baseline_device_interaction = $true",
        "readonly_baseline_persistent_write_authorized = $false",
        "fastboot.cmd",
        "platform_tools_version",
        "kps-packaging-smoke",
        "AC2003 host preflight packaging smoke failed",
        "Host-only AC2003 preflight: PASS",
        "One-command AC2003 read-only baseline launcher: INCLUDED",
    ):
        assert needle in text

    assert "fastboot --version" in text
    assert "begin-physical-test-session" in text
    for forbidden in ("fastboot flash ", "fastboot erase ", "fastboot set_active "):
        assert forbidden not in text.lower()


def test_integrity_verifier_fail_closes_host_preflight_and_fastboot_policy() -> None:
    text = VERIFIER.read_text(encoding="utf-8")

    for needle in (
        "host_preflight_included -ne $true",
        "host_preflight_device_interaction -ne $false",
        "readonly_baseline_launcher_included -ne $true",
        "readonly_baseline_device_interaction -ne $true",
        "readonly_baseline_persistent_write_authorized -ne $false",
        'Join-Path $OperatorPack "host-preflight.ps1"',
        'Join-Path $OperatorPack "readonly-baseline.ps1"',
        'Join-Path $OperatorPack "fastboot-tool-policy.json"',
        "Packaged Fastboot policy is not exact",
        "platform_tools_version",
        "unsafe hardware/Beta claims",
        "Host preflight device interaction: false",
        "One-command AC2003 read-only baseline launcher included: true",
        "Read-only baseline persistent write authorized: false",
    ):
        assert needle in text


def test_windows_candidate_ci_tracks_and_runs_host_preflight_contract() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert text.count('"scripts/preflight_ac2003_first_test.ps1"') == 2
    assert text.count('"scripts/start_ac2003_readonly_baseline.ps1"') == 2
    assert "tests/test_ac2003_host_preflight_contract.py" in text
    assert "Package, host-preflight, read-only baseline launcher and self-verify integrated AC2003 host test candidate" in text
