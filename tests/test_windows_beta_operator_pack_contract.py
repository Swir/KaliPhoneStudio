from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGER = ROOT / "scripts" / "package_windows_beta_test_candidate.ps1"


POST_BOOT_DOCS = (
    "OPERATOR_WORKSPACE.md",
    "KALI_EARLY_USERSPACE_PROOF.md",
    "ROOTFS_HANDOFF_STRATEGY_REVIEW.md",
    "ROOTFS_HANDOFF_TARGET_BINDING.md",
    "ROOTFS_HANDOFF_FRESH_REVALIDATION.md",
    "ROOTFS_HANDOFF_TRIAL_PLAN.md",
    "ROOTFS_HANDOFF_TRIAL_PREFLIGHT.md",
    "ROOTFS_HANDOFF_TRIAL_AUTHORIZATION.md",
    "ROOTFS_HANDOFF_TRIAL_EXECUTION_GATE.md",
    "ROOTFS_HANDOFF_TRIAL_METADATA_MANIFEST.md",
    "ROOTFS_HANDOFF_TRIAL_PAYLOAD_MANIFEST.md",
    "ROOTFS_HANDOFF_INTERACTIVE_EXECUTOR.md",
    "ROOTFS_TRIAL_CHAIN_AUDIT.md",
)


def test_windows_candidate_packages_complete_offline_post_boot_chain() -> None:
    text = PACKAGER.read_text(encoding="utf-8")

    for filename in POST_BOOT_DOCS:
        assert f'"docs/{filename}" = "{filename}"' in text
        assert f'.\\operator-pack\\{filename}' in text
        assert (ROOT / "docs" / filename).is_file()

    for needle in (
        "offline_post_boot_operator_chain_included = $true",
        "rootfs_interactive_staging_auto_run = $false",
        "rootfs_persistent_write_authorized = $false",
        "packaged operator references instead of searching the repository or Internet",
        "local-console, explicit-confirmation",
        "does not stage rootfs bytes or authorize a phone write",
    ):
        assert needle in text


def test_operator_pack_does_not_turn_documentation_into_write_authority() -> None:
    text = PACKAGER.read_text(encoding="utf-8").lower()

    for forbidden in (
        "fastboot flash ",
        "fastboot erase ",
        "fastboot set_active ",
        "phone_storage_written = $true",
        "rootfs_persistent_write_authorized = $true",
        "rootfs_interactive_staging_auto_run = $true",
        "physical_gate_passed = $true",
        "hardware_verified = $true",
        "beta_release = $true",
        "beta_gate_credit = $true",
    ):
        assert forbidden not in text
