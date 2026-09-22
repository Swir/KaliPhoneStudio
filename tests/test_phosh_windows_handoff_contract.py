from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGER = ROOT / "scripts" / "package_windows_beta_test_candidate.ps1"
VERIFIER = ROOT / "scripts" / "verify_windows_beta_test_candidate.ps1"
SMOKE = ROOT / "scripts" / "smoke_windows_beta_test_candidate.ps1"
RUNBOOK = ROOT / "docs" / "AC2003_PHOSH_HANDOFF.md"
MAIN = ROOT / "main.py"


def test_frozen_cli_dispatches_host_only_phosh_handoff() -> None:
    text = MAIN.read_text(encoding="utf-8")
    assert 'PHOSH_OPERATOR_COMMAND = "phosh"' in text
    assert "phosh_operator_main(args[1:])" in text


def test_windows_candidate_packages_reviewed_phosh_authority_and_runbooks() -> None:
    text = PACKAGER.read_text(encoding="utf-8")
    for needle in (
        "AC2003_PHOSH_HANDOFF.md",
        "PHOSH_FIRST_BOOT_BINDING.md",
        "PHOSH_SUCCESSOR_CANDIDATE.md",
        "PHOSH_PHYSICAL_CANDIDATE_ADAPTER.md",
        "phosh-rootfs-authority.json",
        "phosh-rootfs-review-packet.json",
        "phosh_handoff_included = $true",
        "phosh_reviewed_authority_included = $true",
        "phosh_rootfs_bytes_included = $false",
        "Reviewed Phosh handoff: INCLUDED",
    ):
        assert needle in text
    assert "fastboot flash " not in text.lower()
    assert "phone_storage_written = $true" not in text.lower()


def test_candidate_verifier_locks_exact_reviewed_phosh_authority() -> None:
    text = VERIFIER.read_text(encoding="utf-8")
    for needle in (
        "$Info.phosh_handoff_included -ne $true",
        "$Info.phosh_reviewed_authority_included -ne $true",
        "$Info.phosh_rootfs_bytes_included -ne $false",
        "c6f8088a5253983703768bced4e936c9c228f89d804df25ff9b172c8467c764e",
        "881665284",
        "d2fef9b14f8100ad87a9a3429aeacb998f3c7a63dd00b161e4f8dfc518fa1ed7",
        "strict_byte_identical",
        "ready_for_first_boot_binding",
    ):
        assert needle in text


def test_frozen_windows_smoke_exercises_phosh_help_and_fail_closed_adapter() -> None:
    text = SMOKE.read_text(encoding="utf-8")
    for needle in (
        '"phosh"',
        '"build-first-boot-binding"',
        '"build-successor-candidate"',
        '"bind-physical-candidate"',
        "should-not-phosh-adapter.json",
        "Frozen Phosh physical adapter did not fail closed",
        "Frozen reviewed Phosh handoff CLI: PASS",
    ):
        assert needle in text
    for forbidden in ("fastboot flash ", "fastboot erase ", "fastboot set_active "):
        assert forbidden not in text.lower()


def test_operator_runbook_is_exact_and_does_not_promote_physical_credit() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    for needle in (
        "phosh build-first-boot-binding",
        "phosh build-successor-candidate",
        "phosh bind-physical-candidate",
        "phosh-rootfs-authority.json",
        "phosh-rootfs-review-packet.json",
        "ready_for_physical_staging_review=true",
        "rootfs_staged=false",
        "phone_storage_written=false",
        "hardware_verified=false",
        "beta_gate_credit=false",
        "c6f8088a5253983703768bced4e936c9c228f89d804df25ff9b172c8467c764e",
    ):
        assert needle in text
    assert "fastboot flash " not in text.lower()
