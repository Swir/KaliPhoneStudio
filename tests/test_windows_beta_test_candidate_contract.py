from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "windows-beta-test-candidate.yml"
RUNBOOK = ROOT / "docs" / "AC2003_FIRST_TEST.md"
OFFLINE_PREP = ROOT / "docs" / "AC2003_OFFLINE_CANDIDATE_PREPARATION.md"
VERIFIER = ROOT / "scripts" / "verify_windows_beta_test_candidate.ps1"
SMOKE = ROOT / "scripts" / "smoke_windows_beta_test_candidate.ps1"
PACKAGER = ROOT / "scripts" / "package_windows_beta_test_candidate.ps1"
WINDOWS_EXTRACTOR_SHA256 = "9a4848ff93b28a9c2f9dbf52b11e09184242ff192032187d70079df5dfb9a616"


def test_workflow_builds_exact_integrated_windows_candidate() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    exact_head = "${{ github.event.pull_request.head.sha || github.sha }}"

    for needle in (
        "push:",
        "branches: [main]",
        f"ref: {exact_head}",
        'python-version: "3.12"',
        "actions/setup-go@v6",
        'go-version: "1.27.0"',
        "mingw-w64-x86_64-gcc",
        "mingw-w64-x86_64-xz",
        "CGO_ENABLED=1",
        "./scripts/build_windows.ps1",
        './scripts/build_windows_operator_extractor.ps1 -OutputDir "dist/operator-tools"',
        './scripts/smoke_windows_beta_test_candidate.ps1 -CandidateRoot "dist"',
        "./scripts/package_windows_beta_test_candidate.ps1",
        f'-SourceCommit "{exact_head}"',
        "tests/test_windows_operator_extractor_contract.py",
        "tests/test_windows_beta_test_candidate_contract.py",
        "docs/AC2003_OFFLINE_CANDIDATE_PREPARATION.md",
        "docs/BETA_RELEASE_ARTIFACT_INVENTORY.md",
        "docs/BETA_RELEASE_REVIEW_MANIFEST.md",
        "actions/upload-artifact@v4",
        "KaliPhoneStudio-AC2003-beta-test-candidate.zip",
        "KaliPhoneStudio-AC2003-beta-test-candidate.zip.sha256",
        "retention-days: 7",
    ):
        assert needle in workflow

    for forbidden in (
        "softprops/action-gh-release",
        "gh release create",
        "actions/create-release",
    ):
        assert forbidden not in workflow


def test_frozen_smoke_covers_bundled_extractor_and_fail_closed_operator_surface() -> None:
    smoke = SMOKE.read_text(encoding="utf-8")

    for needle in (
        "operator-tools",
        "payload-dumper-go.exe",
        "tools\\extractor-locks.json",
        "Get-FileHash -Algorithm SHA256",
        "all_non_system_imports_resolved",
        '$env:PATH = "$env:SystemRoot\\System32;$env:SystemRoot"',
        "begin-physical-test-session",
        "capture-fastboot-baseline",
        "extract-stock-boot-from-ota",
        "bind-physical-stock-baseline",
        "bind-physical-candidate-gate",
        "bind-physical-boot-identity",
        "build-physical-recovery-readiness",
        "prepare-physical-candidate-offline",
        "prepare-temporary-boot-offer",
        "execute-temporary-boot-once",
        "build-beta-artifact-inventory",
        "build-beta-review-manifest",
        "should-not-session",
        "should-not-capture",
        "should-not-stock",
        "should-not-boot-identity.json",
        "should-not-recovery-readiness.json",
        "should-not-probe.json",
        "should-not-execute.json",
        "should-not-inventory.json",
        "$LASTEXITCODE -ne 2",
        "Physical interaction performed: false",
    ):
        assert needle in smoke

    assert "--extractor $Extractor" in smoke
    assert "--execute-temporary-boot" not in smoke
    for forbidden in ("fastboot flash ", "fastboot erase ", "fastboot set_active "):
        assert forbidden not in smoke.lower()


def test_packager_includes_exact_operator_tools_in_integrity_set_and_zip() -> None:
    packager = PACKAGER.read_text(encoding="utf-8")

    for needle in (
        "operator-tools",
        "payload-dumper-go.exe",
        "operator-extractor-manifest.json",
        "operator-extractor-runtime.json",
        "payload-dumper-go-LICENSE.txt",
        "operator_extractor_included = $true",
        'operator_extractor_platform = "windows-amd64"',
        "operator_extractor_sha256 = $ExpectedExtractorSha",
        "operator_extractor_runtime_dependency_count",
        "BETA_TEST_CANDIDATE_SHA256.txt",
        "BETA_TEST_CANDIDATE_INFO.json",
        "START_HERE.txt",
        "AC2003_FIRST_TEST.md",
        "AC2003_OFFLINE_CANDIDATE_PREPARATION.md",
        "BETA_RELEASE_OPERATOR_WORKSPACE.md",
        "BETA_RELEASE_ARTIFACT_INVENTORY.md",
        "BETA_RELEASE_REVIEW_MANIFEST.md",
        "WINDOWS_OPERATOR_EXTRACTOR.md",
        "verify-candidate.ps1",
        "$Files += Get-ChildItem -Path $Target -Recurse -File",
        "$GuiRoot, $CliRoot, $ToolsRoot, $OperatorPack",
        "KaliPhoneStudio-AC2003-beta-test-candidate.zip",
        "physical_gate_passed = $false",
        "hardware_verified = $false",
        "beta_release = $false",
        "beta_gate_credit = $false",
        "Release-prep files do not authorize publication",
    ):
        assert needle in packager

    assert "no separate download/search required" in packager
    for forbidden in ("gh release", "fastboot flash ", "phone_storage_written = $true"):
        assert forbidden not in packager.lower()


def test_offline_candidate_verifier_rechecks_operator_tool_lock_and_runtime_closure() -> None:
    verifier = VERIFIER.read_text(encoding="utf-8")

    for needle in (
        "BETA_TEST_CANDIDATE_INFO.json",
        "BETA_TEST_CANDIDATE_SHA256.txt",
        "Get-FileHash -Algorithm SHA256",
        "Manifest path escapes candidate root",
        "SHA-256 mismatch",
        '"kaliphonestudio-unsigned-ac2003-beta-test-candidate"',
        '"oneplus/avicii"',
        "operator_extractor_included",
        "operator_extractor_platform",
        "operator_extractor_sha256",
        "operator-tools",
        "payload-dumper-go.exe",
        "operator-extractor-manifest.json",
        "operator-extractor-runtime.json",
        "payload-dumper-go-LICENSE.txt",
        "all_non_system_imports_resolved",
        "$Info.physical_gate_passed -ne $false",
        "$Info.hardware_verified -ne $false",
        "$Info.beta_release -ne $false",
        "$Info.beta_gate_credit -ne $false",
    ):
        assert needle in verifier

    for forbidden in (
        "Invoke-WebRequest",
        "Invoke-RestMethod",
        "Start-BitsTransfer",
        "fastboot ",
        "adb ",
        "gh release",
    ):
        assert forbidden not in verifier


def test_runbook_is_recovery_first_and_uses_packaged_candidate_contract() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")
    assert "OnePlus Nord AC2003" in runbook
    assert "oneplus/avicii" in runbook
    assert "not a public Beta" in runbook
    assert "recovery-first" in runbook
    assert "persistent phone write" in runbook
    assert "exact OxygenOS build" in runbook
    assert "full firmware fingerprint" in runbook

    for command in (
        "begin-physical-test-session",
        "capture-fastboot-baseline",
        "extract-stock-boot-from-ota",
        "bind-physical-stock-baseline",
        "bind-physical-candidate-gate",
        "bind-physical-boot-identity",
        "build-physical-recovery-readiness",
        "prepare-physical-candidate-offline",
        "prepare-temporary-boot-offer",
        "execute-temporary-boot-once",
        "build-beta-artifact-inventory",
        "build-beta-review-manifest",
    ):
        assert command in runbook

    for needle in (
        'pwsh -NoProfile -File .\\operator-pack\\verify-candidate.ps1 -CandidateRoot .',
        '$Extractor = (Resolve-Path ".\\operator-tools\\payload-dumper-go.exe").Path',
        '$Fastboot = (Resolve-Path "<PATH_TO_REVIEWED_FASTBOOT_EXE>").Path',
        '--extractor "$Extractor"',
        '--fastboot-executable "$Fastboot"',
        '--confirm-token "AC2003"',
        "--extractor-platform windows-amd64",
        "--execute-temporary-boot",
        "A Fastboot return code is not proof that Kali booted",
        "exercised recovery/rollback",
    ):
        assert needle in runbook

    assert "<PATH_TO_REVIEWED_PAYLOAD_DUMPER_GO_EXE>" not in runbook


def test_offline_candidate_runbook_requires_packaged_extractor_not_manual_search() -> None:
    text = OFFLINE_PREP.read_text(encoding="utf-8")

    for needle in (
        '$Extractor = (Resolve-Path ".\\operator-tools\\payload-dumper-go.exe").Path',
        '$Fastboot = (Resolve-Path "<PATH_TO_REVIEWED_FASTBOOT_EXE>").Path',
        "prepare-physical-candidate-offline",
        '--extractor "$Extractor"',
        '--fastboot-executable "$Fastboot"',
        "do not download or search for another copy",
        "re-hashes the extractor again immediately before use",
    ):
        assert needle in text

    assert "<PATH_TO_REVIEWED_PAYLOAD_DUMPER_GO_EXE>" not in text


def test_no_persistent_fastboot_write_examples_are_present() -> None:
    texts = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (RUNBOOK, OFFLINE_PREP, VERIFIER, SMOKE, PACKAGER)
    ).lower()
    for fragment in (
        "fastboot flash ",
        "fastboot erase ",
        "fastboot set_active ",
        "fastboot flashing ",
    ):
        assert fragment not in texts


def test_exact_windows_extractor_digest_remains_the_reviewed_authority() -> None:
    locks = (ROOT / "tools" / "extractor-locks.json").read_text(encoding="utf-8")
    assert WINDOWS_EXTRACTOR_SHA256 in locks
