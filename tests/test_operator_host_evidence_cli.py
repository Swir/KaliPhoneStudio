from __future__ import annotations

import json
from pathlib import Path

from kaliphonestudio.candidate_authority_bundle import FirstBootAuthorityBundleEvidence
from kaliphonestudio.operator_evidence_workspace import ALL_EVIDENCE_COMMANDS, main as workspace_main
from kaliphonestudio.operator_host_evidence_cli import HOST_EVIDENCE_COMMANDS, main as host_main
from kaliphonestudio.phosh_candidate_binding import load_phosh_candidate_binding
from kaliphonestudio.phosh_rootfs_binding import (
    PhoshRootfsAuthorityBindingEvidence,
    write_phosh_rootfs_authority_binding,
)


def _candidate() -> FirstBootAuthorityBundleEvidence:
    return FirstBootAuthorityBundleEvidence(
        schema_version=1,
        profile_id="oneplus/avicii",
        first_boot_manifest_sha256="1" * 64,
        kernel_binding_sha256="2" * 64,
        rootfs_binding_sha256="3" * 64,
        device_tree_binding_sha256="4" * 64,
        kernel_authority_sha256="5" * 64,
        rootfs_authority_sha256="6" * 64,
        device_tree_authority_sha256="8" * 64,
        kernel_authority_run_id=101,
        kernel_authority_commit="a" * 40,
        kernel_authority_artifact_id=201,
        rootfs_authority_run_id=102,
        rootfs_authority_commit="b" * 40,
        rootfs_authority_artifact_id=202,
        device_tree_authority_run_id=103,
        device_tree_authority_commit="c" * 40,
        device_tree_authority_artifact_id=203,
        kernel_image_sha256="9" * 64,
        rootfs_artifact_sha256="7" * 64,
        dtb_sha256="d" * 64,
        dtbo_image_sha256="e" * 64,
        all_authorities_reviewed=True,
        all_required_artifacts_strict=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def _phosh() -> PhoshRootfsAuthorityBindingEvidence:
    required = ("mobian-phosh", "mobian-phosh-phone", "squeekboard")
    return PhoshRootfsAuthorityBindingEvidence(
        schema_version=1,
        binding_policy="phosh-rootfs-authority-binding-v1",
        phosh_source_lock_sha256="f" * 64,
        phosh_upstream_commit="d" * 40,
        rootfs_authority_sha256="6" * 64,
        rootfs_authority_name="kali-arm64-phosh",
        rootfs_authority_commit="b" * 40,
        rootfs_release_tag="kali-rolling",
        rootfs_variant="full",
        rootfs_artifact_sha256="7" * 64,
        rootfs_artifact_size=4_194_304,
        package_manifest_sha256="0" * 64,
        package_count=128,
        required_packages=required,
        installed_required_packages=tuple((name, "1.0-kps", "arm64") for name in required),
        host_userspace_package_contract_satisfied=True,
        rootfs_authority_reviewed=True,
        ready_for_physical_candidate_binding=True,
        physical_validation_required=True,
        display_verified=False,
        touch_verified=False,
        hardware_verified=False,
        beta_release_authorized=False,
        beta_gate_credit=False,
    )


def _inputs(tmp_path: Path) -> tuple[Path, Path]:
    candidate_path = tmp_path / "candidate-authority-bundle.json"
    candidate_path.write_text(_candidate().canonical_json(), encoding="utf-8", newline="\n")
    phosh_path = tmp_path / "phosh-rootfs-binding.json"
    write_phosh_rootfs_authority_binding(_phosh(), phosh_path)
    return candidate_path, phosh_path


def test_unified_workspace_lists_phosh_candidate_command(capsys):
    assert HOST_EVIDENCE_COMMANDS == ("bind-phosh-candidate",)
    assert "bind-phosh-candidate" in ALL_EVIDENCE_COMMANDS
    assert workspace_main(["--help"]) == 0
    out = capsys.readouterr().out.lower()
    assert "bind-phosh-candidate" in out
    assert "do not connect to a phone" in out
    assert "no hardware/beta credit" in out


def test_unified_workspace_binds_exact_phosh_candidate_without_promotion(tmp_path: Path, capsys):
    candidate_path, phosh_path = _inputs(tmp_path)
    out_path = tmp_path / "phosh-candidate-binding.json"

    rc = workspace_main(
        [
            "bind-phosh-candidate",
            "--candidate-authority-bundle",
            str(candidate_path),
            "--phosh-rootfs-binding",
            str(phosh_path),
            "--out",
            str(out_path),
        ]
    )

    assert rc == 0
    out = capsys.readouterr().out.lower()
    assert "physical interaction/device command: no" in out
    assert "storage target/persistent write: no" in out
    assert "display/touch/hardware/beta credit: no" in out
    evidence = load_phosh_candidate_binding(out_path)
    assert evidence.profile_id == "oneplus/avicii"
    assert evidence.provenance_cross_bound is True
    assert evidence.ready_for_physical_phosh_validation is True
    assert evidence.display_verified is False
    assert evidence.touch_verified is False
    assert evidence.hardware_verified is False
    assert evidence.beta_release_authorized is False
    assert evidence.beta_gate_credit is False


def test_host_cli_json_summary_keeps_all_safety_flags_false(tmp_path: Path, capsys):
    candidate_path, phosh_path = _inputs(tmp_path)
    out_path = tmp_path / "phosh-candidate-binding.json"

    rc = host_main(
        [
            "--json",
            "bind-phosh-candidate",
            "--candidate-authority-bundle",
            str(candidate_path),
            "--phosh-rootfs-binding",
            str(phosh_path),
            "--out",
            str(out_path),
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "bind-phosh-candidate"
    assert payload["physical_interaction_performed"] is False
    assert payload["external_device_command_executed"] is False
    assert payload["storage_target_selected"] is False
    assert payload["persistent_write_authorized"] is False
    assert payload["phone_storage_written"] is False
    assert payload["display_verified"] is False
    assert payload["touch_verified"] is False
    assert payload["hardware_verified"] is False
    assert payload["beta_release_authorized"] is False
    assert payload["beta_gate_credit"] is False
    assert payload["ready_for_physical_phosh_validation"] is True


def test_unified_workspace_missing_inputs_fail_closed_without_output(tmp_path: Path, capsys):
    out_path = tmp_path / "must-not-exist.json"
    rc = workspace_main(
        [
            "bind-phosh-candidate",
            "--candidate-authority-bundle",
            str(tmp_path / "missing-candidate.json"),
            "--phosh-rootfs-binding",
            str(tmp_path / "missing-phosh.json"),
            "--out",
            str(out_path),
        ]
    )

    assert rc == 2
    assert not out_path.exists()
    assert "evidence workflow error" in capsys.readouterr().err.lower()
