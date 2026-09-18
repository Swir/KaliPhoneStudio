from __future__ import annotations

import ast
from pathlib import Path

import main as root_entry
from kaliphonestudio import operator_evidence_cli


ROOT = Path(__file__).resolve().parents[1]


def test_evidence_workspace_exposes_review_gated_rescue_storage_and_functional_stages() -> None:
    assert operator_evidence_cli.EVIDENCE_COMMANDS == (
        "record-rescue-diagnostics",
        "record-hardware-survey",
        "prepare-hardware-survey-review",
        "bind-hardware-survey-review",
        "prepare-storage-review",
        "bind-storage-review",
        "build-functional-test-plan",
        "prepare-functional-test-plan-review",
        "bind-functional-test-plan-review",
        "prepare-functional-test-observation",
        "bind-functional-test-observation",
        "prepare-functional-test-result-review",
        "bind-functional-test-result-review",
        "summarize-functional-test-results",
        "build-functional-result-bundle",
    )
    help_text = " ".join(operator_evidence_cli._build_parser().format_help().lower().split())
    assert "offline exact-file evidence workspace" in help_text
    assert "do not connect to a phone" in help_text
    assert "do not run adb/fastboot" in help_text
    assert "do not select storage targets" in help_text
    assert "no hardware/beta credit" in help_text


def test_evidence_workspace_has_no_subprocess_or_device_tool_import() -> None:
    source = (ROOT / "kaliphonestudio" / "operator_evidence_cli.py").read_text(encoding="utf-8")
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


def test_missing_rescue_inputs_fail_closed_without_output(tmp_path: Path) -> None:
    destination = tmp_path / "should-not-rescue.json"
    rc = operator_evidence_cli.main(
        [
            "record-rescue-diagnostics",
            "--profile-id",
            "oneplus/avicii",
            "--observation-evidence",
            str(tmp_path / "missing-observation.json"),
            "--console-transcript",
            str(tmp_path / "missing-transcript.txt"),
            "--out",
            str(destination),
        ]
    )
    assert rc == 2
    assert not destination.exists()


def test_missing_storage_discovery_fails_closed_without_template(tmp_path: Path) -> None:
    destination = tmp_path / "should-not-storage-review.json"
    rc = operator_evidence_cli.main(
        [
            "prepare-storage-review",
            "--discovery-evidence",
            str(tmp_path / "missing-storage.json"),
            "--reviewer",
            "reviewer-ci",
            "--out",
            str(destination),
        ]
    )
    assert rc == 2
    assert not destination.exists()


def test_missing_hardware_review_fails_closed_without_functional_plan(tmp_path: Path) -> None:
    destination = tmp_path / "should-not-functional-plan.json"
    rc = operator_evidence_cli.main(
        [
            "build-functional-test-plan",
            "--profile-id",
            "oneplus/avicii",
            "--hardware-review-evidence",
            str(tmp_path / "missing-review.json"),
            "--out",
            str(destination),
        ]
    )
    assert rc == 2
    assert not destination.exists()


def test_missing_exact_plan_review_fails_closed_without_observation_template(tmp_path: Path) -> None:
    destination = tmp_path / "should-not-observation-template.json"
    rc = operator_evidence_cli.main(
        [
            "prepare-functional-test-observation",
            "--test-plan",
            str(tmp_path / "missing-plan.json"),
            "--test-plan-review-evidence",
            str(tmp_path / "missing-plan-review.json"),
            "--test-id",
            "display",
            "--operator",
            "operator-ci",
            "--out",
            str(destination),
        ]
    )
    assert rc == 2
    assert not destination.exists()


def test_missing_observation_fails_closed_without_result_review_template(tmp_path: Path) -> None:
    destination = tmp_path / "should-not-result-review-template.json"
    rc = operator_evidence_cli.main(
        [
            "prepare-functional-test-result-review",
            "--observation-evidence",
            str(tmp_path / "missing-observation.json"),
            "--reviewer",
            "reviewer-ci",
            "--out",
            str(destination),
        ]
    )
    assert rc == 2
    assert not destination.exists()


def test_missing_exact_campaign_files_fail_closed_without_result_bundle(tmp_path: Path) -> None:
    destination = tmp_path / "should-not-functional-result-bundle.json"
    rc = operator_evidence_cli.main(
        [
            "build-functional-result-bundle",
            "--test-plan",
            str(tmp_path / "missing-plan.json"),
            "--test-plan-review-evidence",
            str(tmp_path / "missing-plan-review.json"),
            "--summary-evidence",
            str(tmp_path / "missing-summary.json"),
            "--out",
            str(destination),
        ]
    )
    assert rc == 2
    assert not destination.exists()


def test_root_entrypoint_routes_evidence_group_without_falling_into_gui(monkeypatch) -> None:
    seen: list[str] = []

    def fake_evidence(argv):
        seen.extend(argv)
        return 17

    monkeypatch.setattr(root_entry, "operator_evidence_main", fake_evidence)
    rc = root_entry.main(["evidence", "prepare-storage-review", "--help"])
    assert rc == 17
    assert seen == ["prepare-storage-review", "--help"]
