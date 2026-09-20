from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

from kaliphonestudio import operator_beta_release_evidence_cli
from kaliphonestudio import operator_evidence_workspace


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = (
    "build-beta-artifact-inventory",
    "build-beta-review-manifest",
)


def test_unified_workspace_exposes_beta_release_preparation_commands(capsys) -> None:
    assert operator_beta_release_evidence_cli.BETA_RELEASE_EVIDENCE_COMMANDS == EXPECTED
    assert operator_evidence_workspace.COMMAND_OWNERS[EXPECTED[0]] == "beta-release"
    assert operator_evidence_workspace.COMMAND_OWNERS[EXPECTED[1]] == "beta-release"
    assert operator_evidence_workspace.main(["--help"]) == 0
    output = " ".join(capsys.readouterr().out.lower().split())
    for command in EXPECTED:
        assert command in output
    assert "no hardware/beta credit" in output


def test_beta_release_workspace_has_no_device_network_or_publication_imports() -> None:
    source = (ROOT / "kaliphonestudio/operator_beta_release_evidence_cli.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    forbidden = {"subprocess", "requests", "urllib", "httpx", "socket"}
    assert imported.isdisjoint(forbidden)
    assert not any(name.endswith("fastboot_tool") for name in imported)
    assert not any(name.endswith("temporary_boot_execution") for name in imported)


def test_missing_inventory_inputs_fail_closed_without_output(tmp_path: Path) -> None:
    destination = tmp_path / "should-not-inventory.json"
    rc = operator_evidence_workspace.main(
        [
            "build-beta-artifact-inventory",
            "--candidate-gate", str(tmp_path / "missing-candidate.json"),
            "--release-gate-audit", str(tmp_path / "missing-release-audit.json"),
            "--strategy-review", str(tmp_path / "missing-strategy.json"),
            "--source-commit", "a" * 40,
            "--artifact", f"candidate_boot={tmp_path / 'missing-boot.img'}",
            "--artifact", f"kali_rootfs={tmp_path / 'missing-rootfs.tar.xz'}",
            "--artifact", f"operator_instructions={tmp_path / 'missing-instructions.md'}",
            "--artifact", f"compatibility_matrix={tmp_path / 'missing-matrix.md'}",
            "--artifact", f"known_issues={tmp_path / 'missing-known-issues.md'}",
            "--out", str(destination),
        ]
    )
    assert rc == 2
    assert not destination.exists()


def test_duplicate_artifact_role_fails_before_builder(monkeypatch, tmp_path: Path) -> None:
    called = False

    def unexpected(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("builder must not run for duplicate artifact role")

    monkeypatch.setattr(operator_beta_release_evidence_cli, "build_beta_release_artifact_inventory", unexpected)
    destination = tmp_path / "should-not-inventory.json"
    rc = operator_evidence_workspace.main(
        [
            "build-beta-artifact-inventory",
            "--candidate-gate", "candidate.json",
            "--release-gate-audit", "audit.json",
            "--strategy-review", "strategy.json",
            "--source-commit", "a" * 40,
            "--artifact", "candidate_boot=boot-a.img",
            "--artifact", "candidate_boot=boot-b.img",
            "--out", str(destination),
        ]
    )
    assert rc == 2
    assert called is False
    assert not destination.exists()


def test_inventory_success_delegates_and_keeps_release_blocked(monkeypatch, tmp_path: Path, capsys) -> None:
    evidence = SimpleNamespace(
        profile_id="oneplus/avicii",
        device_serial="SERIAL",
        source_commit="a" * 40,
        artifacts=(object(), object(), object(), object(), object()),
        required_artifacts_present=True,
        ready_for_final_manual_release_review=True,
        manual_release_gate_review_required=True,
    )
    observed: dict[str, object] = {}

    def build(candidate, audit, strategy, source_commit, artifacts):
        observed["artifacts"] = dict(artifacts)
        observed["source_commit"] = source_commit
        return evidence

    def write(value, destination):
        assert value is evidence
        observed["destination"] = destination
        return "b" * 64

    monkeypatch.setattr(operator_beta_release_evidence_cli, "build_beta_release_artifact_inventory", build)
    monkeypatch.setattr(operator_beta_release_evidence_cli, "write_beta_release_artifact_inventory", write)
    out = tmp_path / "inventory.json"
    rc = operator_evidence_workspace.main(
        [
            "--json",
            "build-beta-artifact-inventory",
            "--candidate-gate", "candidate.json",
            "--release-gate-audit", "audit.json",
            "--strategy-review", "strategy.json",
            "--source-commit", "a" * 40,
            "--artifact", "candidate_boot=boot.img",
            "--out", str(out),
        ]
    )
    assert rc == 0
    result = json.loads(capsys.readouterr().out)
    assert observed["artifacts"] == {"candidate_boot": Path("boot.img")}
    assert result["artifact_count"] == 5
    assert result["ready_for_final_manual_release_review"] is True
    assert result["manual_release_gate_review_required"] is True
    assert result["release_publication_allowed"] is False
    assert result["beta_release_authorized"] is False
    assert result["hardware_verified"] is False
    assert result["beta_gate_credit"] is False
    assert result["network_action_performed"] is False


def test_review_manifest_missing_inventory_fails_closed_without_pair(tmp_path: Path) -> None:
    manifest = tmp_path / "should-not-manifest.json"
    checksums = tmp_path / "should-not-SHA256SUMS"
    release_dir = tmp_path / "release"
    release_dir.mkdir()
    rc = operator_evidence_workspace.main(
        [
            "build-beta-review-manifest",
            "--inventory", str(tmp_path / "missing-inventory.json"),
            "--release-dir", str(release_dir),
            "--version", "0.6.67-dev",
            "--manifest-out", str(manifest),
            "--checksums-out", str(checksums),
        ]
    )
    assert rc == 2
    assert not manifest.exists()
    assert not checksums.exists()


def test_review_manifest_refuses_preexisting_pair_member_before_builder(monkeypatch, tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    checksums = tmp_path / "SHA256SUMS"
    checksums.write_text("existing\n", encoding="utf-8")

    def unexpected(*args, **kwargs):
        raise AssertionError("builder must not run when an output already exists")

    monkeypatch.setattr(operator_beta_release_evidence_cli, "build_beta_release_review_manifest", unexpected)
    rc = operator_evidence_workspace.main(
        [
            "build-beta-review-manifest",
            "--inventory", "inventory.json",
            "--release-dir", str(tmp_path),
            "--version", "0.6.67-dev",
            "--manifest-out", str(manifest),
            "--checksums-out", str(checksums),
        ]
    )
    assert rc == 2
    assert not manifest.exists()
    assert checksums.read_text(encoding="utf-8") == "existing\n"


def test_review_manifest_success_reports_exact_pair_and_no_authorization(monkeypatch, tmp_path: Path, capsys) -> None:
    evidence = SimpleNamespace(
        profile_id="oneplus/avicii",
        device_serial="SERIAL",
        source_commit="c" * 40,
        version="0.6.67-dev",
        artifact_count=5,
        sha256sums_sha256="d" * 64,
        exact_artifacts_reverified=True,
        final_manual_release_gate_review_required=True,
    )

    def build(inventory, release_dir, version):
        assert version == "0.6.67-dev"
        return evidence, "d" * 64 + "  artifact.bin\n"

    def write(value, checksums_text, manifest, checksums):
        assert value is evidence
        assert checksums_text.endswith("artifact.bin\n")
        return "e" * 64

    monkeypatch.setattr(operator_beta_release_evidence_cli, "build_beta_release_review_manifest", build)
    monkeypatch.setattr(operator_beta_release_evidence_cli, "write_beta_release_review_manifest_bundle", write)
    manifest = tmp_path / "manifest.json"
    checksums = tmp_path / "SHA256SUMS"
    rc = operator_evidence_workspace.main(
        [
            "--json",
            "build-beta-review-manifest",
            "--inventory", "inventory.json",
            "--release-dir", str(tmp_path),
            "--version", "0.6.67-dev",
            "--manifest-out", str(manifest),
            "--checksums-out", str(checksums),
        ]
    )
    assert rc == 0
    result = json.loads(capsys.readouterr().out)
    assert result["artifact_count"] == 5
    assert result["checksums_path"] == str(checksums)
    assert result["exact_artifacts_reverified"] is True
    assert result["final_manual_release_gate_review_required"] is True
    assert result["release_publication_performed"] is False
    assert result["release_publication_allowed"] is False
    assert result["beta_release_authorized"] is False
    assert result["beta_gate_credit"] is False
