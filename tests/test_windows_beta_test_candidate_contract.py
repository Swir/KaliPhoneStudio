from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "windows-beta-test-candidate.yml"
RUNBOOK = ROOT / "docs" / "AC2003_FIRST_TEST.md"
VERIFIER = ROOT / "scripts" / "verify_windows_beta_test_candidate.ps1"


def test_beta_test_candidate_workflow_freezes_exact_windows_operator_surface() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "runs-on: windows-latest" in workflow
    assert 'python-version: "3.12"' in workflow
    assert "./scripts/build_windows.ps1" in workflow
    assert "tests/test_windows_beta_test_candidate_contract.py" in workflow
    assert "tests/test_operator_beta_release_evidence_cli.py" in workflow
    assert "tests/test_physical_fastboot_capture.py" in workflow
    assert "tests/test_stock_baseline_ingress.py" in workflow
    assert "tests/test_physical_candidate_operator.py" in workflow
    assert "tests/test_temporary_boot_execution.py" in workflow

    for command in (
        "capture-fastboot-baseline",
        "extract-stock-boot-from-ota",
        "bind-physical-stock-baseline",
        "bind-physical-candidate-gate",
        "prepare-temporary-boot-offer",
        "execute-temporary-boot-once",
        "build-beta-artifact-inventory",
        "build-beta-review-manifest",
    ):
        assert command in workflow

    assert "--confirm-token" in workflow
    assert "--extractor-platform" in workflow
    assert "--execute-temporary-boot" in workflow
    assert "$LASTEXITCODE -ne 2" in workflow
    assert "$global:LASTEXITCODE = 0" in workflow

    for refused_path in (
        "dist/should-not-capture",
        "dist/should-not-stock",
        "dist/should-not-probe.json",
        "dist/should-not-execute.json",
        "dist/should-not-inventory.json",
    ):
        assert refused_path in workflow


def test_beta_test_candidate_contains_exact_operator_pack_and_integrity_files() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    for source, staged in (
        ("docs/AC2003_FIRST_TEST.md", "dist/operator-pack/AC2003_FIRST_TEST.md"),
        ("docs/BETA_RELEASE_OPERATOR_WORKSPACE.md", "dist/operator-pack/BETA_RELEASE_OPERATOR_WORKSPACE.md"),
        ("BETA_RELEASE_GATE.md", "dist/operator-pack/BETA_RELEASE_GATE.md"),
        ("BUILD_STATUS.json", "dist/operator-pack/BUILD_STATUS.json"),
        ("devices/oneplus/avicii/profile.json", "dist/operator-pack/profile.json"),
        ("tools/fastboot-tool-policy.json", "dist/operator-pack/fastboot-tool-policy.json"),
        ("tools/extractor-locks.json", "dist/operator-pack/extractor-locks.json"),
        ("scripts/verify_windows_beta_test_candidate.ps1", "dist/operator-pack/verify-candidate.ps1"),
    ):
        assert source in workflow
        assert staged in workflow

    assert "BETA_TEST_CANDIDATE_SHA256.txt" in workflow
    assert "BETA_TEST_CANDIDATE_INFO.json" in workflow
    assert 'Get-Item "dist/BETA_TEST_CANDIDATE_INFO.json"' in workflow
    assert '& "dist/operator-pack/verify-candidate.ps1" -CandidateRoot "dist"' in workflow
    assert "KaliPhoneStudio-AC2003-beta-test-candidate.zip" in workflow
    assert "KaliPhoneStudio-AC2003-beta-test-candidate.zip.sha256" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "retention-days: 7" in workflow


def test_candidate_metadata_cannot_claim_physical_or_beta_success() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert 'kind = "kaliphonestudio-unsigned-ac2003-beta-test-candidate"' in workflow
    assert 'profile_id = "oneplus/avicii"' in workflow
    assert "signed = $false" in workflow
    assert "physical_gate_passed = $false" in workflow
    assert "hardware_verified = $false" in workflow
    assert "beta_release = $false" in workflow
    assert "beta_gate_credit = $false" in workflow

    forbidden_publishers = (
        "softprops/action-gh-release",
        "gh release create",
        "actions/create-release",
        "release_publication_allowed = $true",
        "beta_release = $true",
        "hardware_verified = $true",
        "beta_gate_credit = $true",
    )
    for needle in forbidden_publishers:
        assert needle not in workflow


def test_offline_candidate_verifier_checks_hashes_and_non_release_flags() -> None:
    verifier = VERIFIER.read_text(encoding="utf-8")

    assert "BETA_TEST_CANDIDATE_INFO.json" in verifier
    assert "BETA_TEST_CANDIDATE_SHA256.txt" in verifier
    assert "Get-FileHash -Algorithm SHA256" in verifier
    assert "Manifest path escapes candidate root" in verifier
    assert "SHA-256 mismatch" in verifier
    assert '"kaliphonestudio-unsigned-ac2003-beta-test-candidate"' in verifier
    assert '"oneplus/avicii"' in verifier
    assert "$Info.physical_gate_passed -ne $false" in verifier
    assert "$Info.hardware_verified -ne $false" in verifier
    assert "$Info.beta_release -ne $false" in verifier
    assert "$Info.beta_gate_credit -ne $false" in verifier

    forbidden = (
        "Invoke-WebRequest",
        "Invoke-RestMethod",
        "Start-BitsTransfer",
        "fastboot ",
        "adb ",
        "gh release",
    )
    for needle in forbidden:
        assert needle not in verifier


def test_ac2003_first_test_runbook_is_recovery_first_and_exact_evidence_driven() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")

    assert "OnePlus Nord AC2003" in runbook
    assert "oneplus/avicii" in runbook
    assert "not a public Beta" in runbook
    assert "recovery-first" in runbook
    assert "persistent phone write" in runbook
    assert "exact OxygenOS build" in runbook
    assert "full firmware fingerprint" in runbook

    for command in (
        "capture-fastboot-baseline",
        "extract-stock-boot-from-ota",
        "bind-physical-stock-baseline",
        "bind-physical-candidate-gate",
        "prepare-temporary-boot-offer",
        "execute-temporary-boot-once",
        "build-beta-artifact-inventory",
        "build-beta-review-manifest",
    ):
        assert command in runbook

    assert '--confirm-token "AC2003"' in runbook
    assert "--extractor-platform windows-amd64" in runbook
    assert "--execute-temporary-boot" in runbook
    assert "A Fastboot return code is not proof that Kali booted" in runbook
    assert "exercised recovery/rollback" in runbook


def test_runbook_does_not_recommend_persistent_fastboot_write_commands() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")

    # The words may appear in explicit stop-condition prose, but the runbook must
    # not present any of them as executable Fastboot command examples.
    forbidden_command_fragments = (
        "fastboot flash ",
        "fastboot erase ",
        "fastboot set_active ",
        "fastboot flashing ",
    )
    lowered = runbook.lower()
    for fragment in forbidden_command_fragments:
        assert fragment not in lowered
