from __future__ import annotations

import ast
from pathlib import Path

from kaliphonestudio import operator_evidence_workspace
from kaliphonestudio import operator_release_evidence_cli


ROOT = Path(__file__).resolve().parents[1]


def test_unified_workspace_exposes_late_physical_audit_stages(capsys) -> None:
    expected_late = (
        "bind-bringup-session",
        "build-bringup-dossier",
        "verify-bringup-dossier",
        "prepare-bringup-dossier-review",
        "bind-bringup-dossier-review",
        "build-release-gate-audit",
    )
    assert operator_release_evidence_cli.LATE_EVIDENCE_COMMANDS == expected_late
    assert len(operator_evidence_workspace.ALL_EVIDENCE_COMMANDS) == len(
        set(operator_evidence_workspace.ALL_EVIDENCE_COMMANDS)
    )
    assert operator_evidence_workspace.main(["--help"]) == 0
    help_text = " ".join(capsys.readouterr().out.lower().split())
    assert "offline exact-file evidence workspace" in help_text
    assert "do not connect to a phone" in help_text
    assert "do not run adb/fastboot" in help_text
    assert "do not select storage targets" in help_text
    assert "no hardware/beta credit" in help_text
    for command in expected_late:
        assert command in help_text


def test_late_workspace_has_no_subprocess_or_device_execution_import() -> None:
    for relative in (
        "kaliphonestudio/operator_release_evidence_cli.py",
        "kaliphonestudio/operator_evidence_workspace.py",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        assert "subprocess" not in imported
        assert not any(name.endswith("fastboot_tool") for name in imported)
        assert not any(name.endswith("physical_fastboot_capture") for name in imported)
        assert not any(name.endswith("temporary_boot_execution") for name in imported)


def test_missing_session_inputs_fail_closed_without_output(tmp_path: Path) -> None:
    destination = tmp_path / "should-not-session.json"
    rc = operator_evidence_workspace.main(
        [
            "bind-bringup-session",
            "--candidate-gate",
            str(tmp_path / "missing-candidate.json"),
            "--boot-observation",
            str(tmp_path / "missing-boot.json"),
            "--rescue-diagnostics",
            str(tmp_path / "missing-rescue.json"),
            "--functional-probes",
            str(tmp_path / "missing-probes.json"),
            "--storage-discovery",
            str(tmp_path / "missing-storage.json"),
            "--storage-review",
            str(tmp_path / "missing-storage-review.json"),
            "--out",
            str(destination),
        ]
    )
    assert rc == 2
    assert not destination.exists()


def test_missing_session_fails_closed_without_dossier(tmp_path: Path) -> None:
    destination = tmp_path / "should-not-dossier.json"
    rc = operator_evidence_workspace.main(
        [
            "build-bringup-dossier",
            "--session",
            str(tmp_path / "missing-session.json"),
            "--candidate-gate",
            str(tmp_path / "missing-candidate.json"),
            "--boot-observation",
            str(tmp_path / "missing-boot.json"),
            "--rescue-diagnostics",
            str(tmp_path / "missing-rescue.json"),
            "--functional-probes",
            str(tmp_path / "missing-probes.json"),
            "--storage-discovery",
            str(tmp_path / "missing-storage.json"),
            "--storage-review",
            str(tmp_path / "missing-storage-review.json"),
            "--rescue-transcript",
            str(tmp_path / "missing-rescue.txt"),
            "--storage-discovery-report",
            str(tmp_path / "missing-storage-report.txt"),
            "--recovery-plan",
            str(tmp_path / "missing-recovery.txt"),
            "--storage-review-record",
            str(tmp_path / "missing-storage-review-record.json"),
            "--storage-review-notes",
            str(tmp_path / "missing-storage-review-notes.txt"),
            "--out",
            str(destination),
        ]
    )
    assert rc == 2
    assert not destination.exists()


def test_missing_dossier_fails_closed_without_reverification(tmp_path: Path) -> None:
    destination = tmp_path / "should-not-verification.json"
    rc = operator_evidence_workspace.main(
        [
            "verify-bringup-dossier",
            "--dossier",
            str(tmp_path / "missing-dossier.json"),
            "--file",
            f"physical_candidate_gate={tmp_path / 'missing-candidate.json'}",
            "--out",
            str(destination),
        ]
    )
    assert rc == 2
    assert not destination.exists()


def test_missing_dossier_fails_closed_without_review_templates(tmp_path: Path) -> None:
    record = tmp_path / "should-not-review.json"
    notes = tmp_path / "should-not-review.txt"
    rc = operator_evidence_workspace.main(
        [
            "prepare-bringup-dossier-review",
            "--dossier",
            str(tmp_path / "missing-dossier.json"),
            "--reviewer",
            "reviewer-ci",
            "--record-out",
            str(record),
            "--notes-out",
            str(notes),
        ]
    )
    assert rc == 2
    assert not record.exists()
    assert not notes.exists()


def test_missing_review_chain_fails_closed_without_review_evidence(tmp_path: Path) -> None:
    destination = tmp_path / "should-not-dossier-review-evidence.json"
    rc = operator_evidence_workspace.main(
        [
            "bind-bringup-dossier-review",
            "--dossier",
            str(tmp_path / "missing-dossier.json"),
            "--verification",
            str(tmp_path / "missing-verification.json"),
            "--review-record",
            str(tmp_path / "missing-review-record.json"),
            "--review-notes",
            str(tmp_path / "missing-review-notes.txt"),
            "--out",
            str(destination),
        ]
    )
    assert rc == 2
    assert not destination.exists()


def test_missing_cross_campaign_inputs_fail_closed_without_release_audit(tmp_path: Path) -> None:
    destination = tmp_path / "should-not-release-audit.json"
    rc = operator_evidence_workspace.main(
        [
            "build-release-gate-audit",
            "--dossier",
            str(tmp_path / "missing-dossier.json"),
            "--dossier-verification",
            str(tmp_path / "missing-verification.json"),
            "--dossier-review",
            str(tmp_path / "missing-dossier-review.json"),
            "--functional-result-bundle",
            str(tmp_path / "missing-result-bundle.json"),
            "--test-plan",
            str(tmp_path / "missing-plan.json"),
            "--test-plan-review",
            str(tmp_path / "missing-plan-review.json"),
            "--out",
            str(destination),
        ]
    )
    assert rc == 2
    assert not destination.exists()


def test_review_template_pair_write_is_atomic_on_preexisting_output(tmp_path: Path) -> None:
    record = tmp_path / "record.json"
    notes = tmp_path / "notes.txt"
    notes.write_text("existing\n", encoding="utf-8")
    try:
        operator_release_evidence_cli._write_pair_exclusive(record, "{}\n", notes, "notes\n")
    except ValueError as exc:
        assert "refusing to overwrite existing output" in str(exc)
    else:
        raise AssertionError("pair writer unexpectedly overwrote an existing output")
    assert not record.exists()
    assert notes.read_text(encoding="utf-8") == "existing\n"
