from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WIZARD = ROOT / "scripts" / "start_ac2003_first_test_wizard.ps1"
OVERLAY = ROOT / "scripts" / "overlay_ac2003_first_test_wizard.ps1"
WINDOWS_CANDIDATE_WORKFLOW = ROOT / ".github" / "workflows" / "windows-beta-test-candidate.yml"


def test_first_test_wizard_reuses_reviewed_readonly_boundaries() -> None:
    text = WIZARD.read_text(encoding="utf-8")

    for needle in (
        'operator-pack\\readonly-baseline.ps1',
        'operator-pack\\host-preflight.ps1',
        '-CaptureAndroidIdentityOnly',
        '-AndroidIdentityEvidence',
        '-SessionDir',
        'FastbootAlreadyReady',
        'Read-Host',
        '@("devices")',
        'exactly one Fastboot device',
        'stock-android-identity-link.json',
        'physical-first-test-session.json',
        'fastboot\\fastboot-getvar-all.txt',
        'persistent_write_authorized',
        'phone_storage_written',
        'hardware_verified',
        'beta_gate_credit',
    ):
        assert needle in text


def test_first_test_wizard_binds_adb_and_fastboot_to_one_unchanged_toolchain() -> None:
    text = WIZARD.read_text(encoding="utf-8")

    for needle in (
        'Split-Path -Parent $AdbPath',
        'Split-Path -Parent $FastbootPath',
        '[StringComparison]::OrdinalIgnoreCase',
        'same Android Platform-Tools directory',
        '$AdbShaAtStart = (Get-FileHash -Algorithm SHA256 -Path $AdbPath)',
        '$FastbootShaAtStart = (Get-FileHash -Algorithm SHA256 -Path $FastbootPath)',
        'Host/Fastboot preflight failed before any phone interaction',
        'Captured ADB identity is not bound to the wizard-start ADB executable',
        'Android Platform-Tools executable changed between wizard phases',
        'Shared Platform-Tools directory',
    ):
        assert needle in text

    first_preflight = text.index('& pwsh -NoProfile -File $Preflight')
    first_phone_capture = text.index('-CaptureAndroidIdentityOnly')
    assert first_preflight < first_phone_capture


def test_windows_candidate_rebuilds_when_wizard_changes() -> None:
    text = WINDOWS_CANDIDATE_WORKFLOW.read_text(encoding="utf-8")

    assert text.count('"scripts/start_ac2003_first_test_wizard.ps1"') >= 2
    assert text.count('"scripts/overlay_ac2003_first_test_wizard.ps1"') >= 2
    assert 'tests/test_ac2003_first_test_wizard_contract.py' in text


def test_first_test_wizard_has_no_automatic_destructive_or_boot_command() -> None:
    text = WIZARD.read_text(encoding="utf-8").lower()

    # Explanatory prose deliberately says that adb reboot / fastboot boot are forbidden.
    # Test actual argv-shaped calls instead of rejecting those safety sentences.
    for forbidden_argv in (
        '@("reboot")',
        '@("boot")',
        '@("flash")',
        '@("erase")',
        '@("set_active")',
        '@("flashing")',
    ):
        assert forbidden_argv not in text

    assert 'invoke-readonlytool $fastbootpath @("devices")' in text
    for forbidden_promotion in (
        "persistent_write_authorized = $true",
        "phone_storage_written = $true",
        "hardware_verified = $true",
        "beta_gate_credit = $true",
    ):
        assert forbidden_promotion not in text


def test_wizard_requires_manual_mode_transition_by_default() -> None:
    text = WIZARD.read_text(encoding="utf-8")

    assert 'if (-not $FastbootAlreadyReady)' in text
    assert 'MANUAL MODE CHANGE REQUIRED' in text
    assert 'using the phone controls' in text
    assert 'Do not use an ADB reboot command' in text
    assert 'Read-Host "When the phone is visibly in Fastboot/bootloader, press ENTER"' in text


def test_candidate_overlay_packages_wizard_and_rebuilds_integrity_set() -> None:
    text = OVERLAY.read_text(encoding="utf-8")

    for needle in (
        'start_ac2003_first_test_wizard.ps1',
        'first-test-wizard.ps1',
        'first_test_wizard_included',
        'first_test_wizard_manual_fastboot_transition_required',
        'first_test_wizard_automatic_reboot',
        'first_test_wizard_temporary_boot_performed',
        'first_test_wizard_persistent_write_authorized',
        'first_test_wizard_beta_gate_credit',
        'BETA_TEST_CANDIDATE_SHA256.txt',
        'verify-candidate.ps1',
        'Get-FileHash -Algorithm SHA256',
        'Compress-Archive',
        '$ZipShaPath = "$ZipPath.sha256"',
    ):
        assert needle in text

    assert 'first_test_wizard_included -NotePropertyValue $true' in text
    assert 'first_test_wizard_manual_fastboot_transition_required -NotePropertyValue $true' in text
    for safe_false in (
        'first_test_wizard_automatic_reboot',
        'first_test_wizard_temporary_boot_performed',
        'first_test_wizard_persistent_write_authorized',
        'first_test_wizard_beta_gate_credit',
    ):
        assert safe_false in text


def test_candidate_overlay_does_not_authorize_release_or_phone_write() -> None:
    text = OVERLAY.read_text(encoding="utf-8").lower()

    # The overlay intentionally contains forbidden Fastboot verb strings only as
    # assertions that scan the packaged wizard. Do not mistake those guard strings
    # for executable device commands.
    for forbidden in (
        "gh release create",
        "beta_release = $true",
        "hardware_verified = $true",
        "phone_storage_written = $true",
        "persistent_write_authorized = $true",
    ):
        assert forbidden not in text

    assert 'first_test_wizard_persistent_write_authorized -notepropertyvalue $false' in text
    assert 'first_test_wizard_beta_gate_credit -notepropertyvalue $false' in text
