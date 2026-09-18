from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_windows_build_toolchain_is_exactly_pinned_to_patched_pyinstaller() -> None:
    requirements = (ROOT / "build" / "windows-requirements.txt").read_text(encoding="utf-8")
    assert "pyinstaller==6.22.3" in requirements
    assert "pyinstaller-hooks-contrib==2026.7" in requirements
    assert "pyinstaller<" not in requirements.lower()


def test_windows_build_is_onedir_and_bundles_offline_safety_inputs() -> None:
    script = (ROOT / "scripts" / "build_windows.ps1").read_text(encoding="utf-8")
    assert '"--onedir"' in script
    assert '"--onefile"' not in script
    assert '"--noupx"' in script
    assert '"--windowed"' in script
    assert '"--console"' in script
    assert '"KaliPhoneStudio"' in script
    assert '"KaliPhoneStudioCLI"' in script
    for variable, destination in (
        ("$DevicesPath", "devices"),
        ("$AssetsPath", "assets"),
        ("$ToolsPath", "tools"),
        ("$BuildStatusPath", "."),
        ("$BetaGatePath", "."),
    ):
        assert variable in script
        assert f"${{{variable[1:]}}};{destination}" in script
    assert "--specpath" in script
    assert '"PySide6.QtSvg"' in script
    assert "unsigned development host artifacts" in script
    assert "Beta releases" in script


def test_windows_ci_executes_frozen_safety_smoke_tests_before_artifact_upload() -> None:
    workflow = (ROOT / ".github" / "workflows" / "windows-host-build.yml").read_text(
        encoding="utf-8"
    )
    assert "runs-on: windows-latest" in workflow
    assert 'python-version: "3.12"' in workflow
    assert "./scripts/build_windows.ps1" in workflow
    assert "tests/test_windows_packaging_contract.py" in workflow
    assert "tests/test_physical_fastboot_capture.py" in workflow
    assert "tests/test_stock_baseline_ingress.py" in workflow
    for command in (
        "--list-profiles --json",
        "--doctor --profile-id oneplus/avicii --json",
        "--recovery-guide --profile-id oneplus/avicii --json",
        "--export-diagnostics",
        "capture-fastboot-baseline --help",
        "prepare-stock-provenance --help",
        "bind-physical-stock-baseline --help",
    ):
        assert command in workflow
    for invariant in (
        'doctor["physical_interaction_performed"] is False',
        'doctor["hardware_verified"] is False',
        'doctor["beta_gate_credit"] is False',
        'recovery["persistent_write_authorized"] is False',
        'bundle["privacy"]["external_commands_executed"] is False',
        'bundle["privacy"]["device_queried"] is False',
        'bundle["privacy"]["absolute_tool_paths_exported"] is False',
        'bundle["hardware_verified"] is False',
        'bundle["beta_gate_credit"] is False',
        'assert "read-only" in capture_help',
        'assert "--confirm-token" in capture_help',
        'assert "offline" in stock_help',
        'assert "--ota" in stock_help',
        'assert "--payload" in stock_help',
        'assert "offline" in bind_help',
        'assert "--baseline-evidence" in bind_help',
        'assert "--confirm-token" in refusal',
    ):
        assert invariant in workflow
    assert "$LASTEXITCODE -ne 2" in workflow
    assert "dist/should-not-exist" in workflow
    assert "dist/should-not-stock.json" in workflow
    assert "dist/should-not-bind.json" in workflow
    assert "WINDOWS_HOST_BUILD_SHA256.txt" in workflow
    assert "WINDOWS_HOST_BUILD_INFO.json" in workflow
    assert "signed = $false" in workflow
    assert "hardware_verified = $false" in workflow
    assert "beta_release = $false" in workflow
    assert "beta_gate_credit = $false" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "retention-days: 7" in workflow


def test_windows_build_documentation_keeps_release_gate_separate() -> None:
    documentation = (ROOT / "docs" / "WINDOWS_HOST_BUILD.md").read_text(encoding="utf-8")
    assert "unsigned" in documentation.lower()
    assert "development" in documentation.lower()
    assert "not a Beta release" in documentation
    assert "hardware_verified=false" in documentation
    assert "beta_gate_credit=false" in documentation
    assert "onedir" in documentation
    assert "capture-fastboot-baseline" in documentation
    assert "--confirm-token" in documentation
    assert "never performs a persistent phone write" in documentation
