from __future__ import annotations

import ast
from pathlib import Path

from kaliphonestudio import operator_bringup_evidence_cli, operator_evidence_dispatch


ROOT = Path(__file__).resolve().parents[1]


def test_dispatch_exposes_one_shared_evidence_surface() -> None:
    assert operator_evidence_dispatch.ALL_EVIDENCE_COMMANDS[-6:] == (
        "bind-bringup-session",
        "build-bringup-dossier",
        "verify-bringup-dossier",
        "prepare-bringup-dossier-review",
        "bind-bringup-dossier-review",
        "build-release-gate-audit",
    )
    assert len(operator_evidence_dispatch.ALL_EVIDENCE_COMMANDS) == len(
        set(operator_evidence_dispatch.ALL_EVIDENCE_COMMANDS)
    )


def test_bringup_extension_has_no_subprocess_or_device_tool_import() -> None:
    source = (ROOT / "kaliphonestudio" / "operator_bringup_evidence_cli.py").read_text(encoding="utf-8")
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


def test_shared_help_lists_late_audit_commands_and_safety(capsys) -> None:
    assert operator_evidence_dispatch.main(["--help"]) == 0
    text = " ".join(capsys.readouterr().out.lower().split())
    assert "offline exact-file evidence workspace" in text
    assert "do not connect to a phone" in text
    assert "do not run adb/fastboot" in text
    assert "do not select storage targets" in text
    assert "no hardware/beta credit" in text
    for command in operator_bringup_evidence_cli.BRINGUP_EVIDENCE_COMMANDS:
        assert command in text


def test_missing_session_inputs_fail_closed_without_output(tmp_path: Path) -> None:
    out = tmp_path / "should-not-session.json"
    rc = operator_evidence_dispatch.main(
        [
            "bind-bringup-session",
            "--candidate-gate", str(tmp_path / "missing-candidate.json"),
            "--boot-observation", str(tmp_path / "missing-boot.json"),
            "--rescue-diagnostics", str(tmp_path / "missing-rescue.json"),
            "--functional-probes", str(tmp_path / "missing-probes.json"),
            "--storage-discovery", str(tmp_path / "missing-storage.json"),
            "--storage-review", str(tmp_path / "missing-review.json"),
            "--out", str(out),
        ]
    )
    assert rc == 2
    assert not out.exists()


def test_incomplete_dossier_early_userspace_pair_fails_before_output(tmp_path: Path) -> None:
    out = tmp_path / "should-not-dossier.json"
    rc = operator_evidence_dispatch.main(
        [
            "build-bringup-dossier",
            "--session", str(tmp_path / "missing-session.json"),
            "--candidate-gate", str(tmp_path / "missing-candidate.json"),
            "--boot-observation", str(tmp_path / "missing-boot.json"),
            "--rescue-diagnostics", str(tmp_path / "missing-rescue.json"),
            "--functional-probes", str(tmp_path / "missing-probes.json"),
            "--storage-discovery", str(tmp_path / "missing-storage.json"),
            "--storage-review", str(tmp_path / "missing-review.json"),
            "--rescue-transcript", str(tmp_path / "missing-transcript.txt"),
            "--storage-discovery-report", str(tmp_path / "missing-report.json"),
            "--recovery-plan", str(tmp_path / "missing-recovery.txt"),
            "--storage-review-record", str(tmp_path / "missing-review-record.json"),
            "--storage-review-notes", str(tmp_path / "missing-review-notes.txt"),
            "--kali-early-userspace-evidence", str(tmp_path / "missing-early.json"),
            "--out", str(out),
        ]
    )
    assert rc == 2
    assert not out.exists()


def test_missing_dossier_verification_inputs_fail_closed_without_output(tmp_path: Path) -> None:
    out = tmp_path / "should-not-verification.json"
    rc = operator_evidence_dispatch.main(
        [
            "verify-bringup-dossier",
            "--dossier", str(tmp_path / "missing-dossier.json"),
            "--file", f"physical_candidate_gate={tmp_path / 'missing-candidate.json'}",
            "--out", str(out),
        ]
    )
    assert rc == 2
    assert not out.exists()


def test_missing_dossier_fails_closed_without_review_templates(tmp_path: Path) -> None:
    record = tmp_path / "should-not-record.json"
    notes = tmp_path / "should-not-notes.txt"
    rc = operator_evidence_dispatch.main(
        [
            "prepare-bringup-dossier-review",
            "--dossier", str(tmp_path / "missing-dossier.json"),
            "--reviewer", "reviewer-ci",
            "--record-out", str(record),
            "--notes-out", str(notes),
        ]
    )
    assert rc == 2
    assert not record.exists()
    assert not notes.exists()


def test_missing_dossier_review_chain_fails_closed_without_output(tmp_path: Path) -> None:
    out = tmp_path / "should-not-dossier-review.json"
    rc = operator_evidence_dispatch.main(
        [
            "bind-bringup-dossier-review",
            "--dossier", str(tmp_path / "missing-dossier.json"),
            "--verification", str(tmp_path / "missing-verification.json"),
            "--review-record", str(tmp_path / "missing-record.json"),
            "--review-notes", str(tmp_path / "missing-notes.txt"),
            "--out", str(out),
        ]
    )
    assert rc == 2
    assert not out.exists()


def test_missing_cross_campaign_inputs_fail_closed_without_audit(tmp_path: Path) -> None:
    out = tmp_path / "should-not-audit.json"
    rc = operator_evidence_dispatch.main(
        [
            "build-release-gate-audit",
            "--dossier", str(tmp_path / "missing-dossier.json"),
            "--dossier-verification", str(tmp_path / "missing-verification.json"),
            "--dossier-review", str(tmp_path / "missing-dossier-review.json"),
            "--functional-result-bundle", str(tmp_path / "missing-results.json"),
            "--test-plan", str(tmp_path / "missing-plan.json"),
            "--test-plan-review", str(tmp_path / "missing-plan-review.json"),
            "--out", str(out),
        ]
    )
    assert rc == 2
    assert not out.exists()
