from __future__ import annotations

import ast
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from kaliphonestudio import operator_evidence_workspace
from kaliphonestudio import operator_strategy_evidence_cli
from kaliphonestudio.rootfs_handoff_strategy_review import RootfsHandoffStrategyReviewRecord


ROOT = Path(__file__).resolve().parents[1]


def _record() -> RootfsHandoffStrategyReviewRecord:
    return RootfsHandoffStrategyReviewRecord(
        schema_version=1,
        review_policy="reversible-rootfs-handoff-strategy-review-v1",
        profile_id="oneplus/avicii",
        device_serial="SERIAL-CI",
        reviewer="reviewer-ci",
        decision="rejected",
        candidate_partition_role="userdata",
        staging_subpath="kaliphonestudio/rootfs-stage",
        required_free_bytes=1,
        rootfs_artifact_sha256="a" * 64,
        recovery_plan_sha256="b" * 64,
        exact_physical_chain_reviewed=False,
        capacity_evidence_reviewed=False,
        filesystem_encryption_reviewed=False,
        rollback_plan_reviewed=False,
        forbidden_partition_policy_reviewed=False,
        no_raw_device_path_reviewed=False,
        no_write_authorization_reviewed=False,
        target_selected=False,
        storage_path_bound=False,
        trial_execution_allowed=False,
        write_authorized=False,
        phone_storage_written=False,
    )


def test_unified_workspace_exposes_strategy_review_commands(capsys) -> None:
    expected = (
        "prepare-rootfs-handoff-strategy-review",
        "bind-rootfs-handoff-strategy-review",
    )
    assert operator_strategy_evidence_cli.STRATEGY_EVIDENCE_COMMANDS == expected
    assert len(operator_evidence_workspace.ALL_EVIDENCE_COMMANDS) == len(
        set(operator_evidence_workspace.ALL_EVIDENCE_COMMANDS)
    )
    assert operator_evidence_workspace.main(["--help"]) == 0
    help_text = capsys.readouterr().out.lower()
    for command in expected:
        assert command in help_text


def test_strategy_workspace_has_no_subprocess_or_device_execution_import() -> None:
    source = (ROOT / "kaliphonestudio/operator_strategy_evidence_cli.py").read_text(encoding="utf-8")
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


def test_missing_strategy_inputs_fail_closed_without_outputs(tmp_path: Path) -> None:
    record = tmp_path / "record.json"
    notes = tmp_path / "notes.txt"
    rc = operator_evidence_workspace.main(
        [
            "prepare-rootfs-handoff-strategy-review",
            "--storage-discovery", str(tmp_path / "missing-discovery.json"),
            "--storage-review", str(tmp_path / "missing-review.json"),
            "--reviewer", "reviewer-ci",
            "--candidate-partition-role", "userdata",
            "--staging-subpath", "kaliphonestudio/rootfs-stage",
            "--required-free-bytes", "1",
            "--record-out", str(record),
            "--notes-out", str(notes),
        ]
    )
    assert rc == 2
    assert not record.exists()
    assert not notes.exists()


@pytest.mark.parametrize(
    ("candidate_role", "required_free_bytes", "staging_subpath"),
    [
        ("boot", 100, "kaliphonestudio/rootfs-stage"),
        ("userdata", 99, "kaliphonestudio/rootfs-stage"),
        ("userdata", 100, "/dev/block/sda"),
    ],
)
def test_prepare_rejects_unsafe_or_drifted_strategy_template_inputs(
    monkeypatch,
    tmp_path: Path,
    candidate_role: str,
    required_free_bytes: int,
    staging_subpath: str,
) -> None:
    discovery = SimpleNamespace(
        profile_id="oneplus/avicii",
        device_serial="SERIAL-CI",
        partition_hint="userdata",
        forbidden_partitions=("boot", "vendor_boot", "dtbo", "vbmeta", "super", "metadata"),
        evidence_sha256=lambda: "1" * 64,
    )
    storage_review = SimpleNamespace(
        physical_storage_discovery_sha256="1" * 64,
        accepted_for_strategy_design=True,
        rootfs_artifact_size=100,
        rootfs_artifact_sha256="a" * 64,
        recovery_plan_sha256="b" * 64,
    )
    monkeypatch.setattr(operator_strategy_evidence_cli, "load_physical_storage_discovery_evidence", lambda path: discovery)
    monkeypatch.setattr(operator_strategy_evidence_cli, "load_physical_storage_review_evidence", lambda path: storage_review)
    record = tmp_path / "record.json"
    notes = tmp_path / "notes.txt"
    rc = operator_evidence_workspace.main(
        [
            "prepare-rootfs-handoff-strategy-review",
            "--storage-discovery", str(tmp_path / "discovery.json"),
            "--storage-review", str(tmp_path / "review.json"),
            "--reviewer", "reviewer-ci",
            "--candidate-partition-role", candidate_role,
            "--staging-subpath", staging_subpath,
            "--required-free-bytes", str(required_free_bytes),
            "--record-out", str(record),
            "--notes-out", str(notes),
        ]
    )
    assert rc == 2
    assert not record.exists()
    assert not notes.exists()


def test_missing_bind_inputs_fail_closed_without_evidence(tmp_path: Path) -> None:
    destination = tmp_path / "strategy-evidence.json"
    rc = operator_evidence_workspace.main(
        [
            "bind-rootfs-handoff-strategy-review",
            "--storage-discovery", str(tmp_path / "missing-discovery.json"),
            "--storage-review", str(tmp_path / "missing-storage-review.json"),
            "--dossier", str(tmp_path / "missing-dossier.json"),
            "--dossier-review", str(tmp_path / "missing-dossier-review.json"),
            "--release-gate-audit", str(tmp_path / "missing-audit.json"),
            "--review-record", str(tmp_path / "missing-record.json"),
            "--review-notes", str(tmp_path / "missing-notes.txt"),
            "--out", str(destination),
        ]
    )
    assert rc == 2
    assert not destination.exists()


def test_bind_recomputes_canonical_record_identity_before_upstream_load(monkeypatch, tmp_path: Path) -> None:
    record = _record()
    canonical = record.canonical_json().encode("utf-8")
    monkeypatch.setattr(
        operator_strategy_evidence_cli,
        "load_rootfs_handoff_strategy_review_record",
        lambda path: (record, "f" * 64, len(canonical)),
    )
    called = False

    def unexpected(_path):
        nonlocal called
        called = True
        raise AssertionError("upstream evidence load must not happen after detached record metadata")

    monkeypatch.setattr(operator_strategy_evidence_cli, "load_physical_storage_discovery_evidence", unexpected)
    destination = tmp_path / "strategy-evidence.json"
    rc = operator_evidence_workspace.main(
        [
            "bind-rootfs-handoff-strategy-review",
            "--storage-discovery", str(tmp_path / "discovery.json"),
            "--storage-review", str(tmp_path / "storage-review.json"),
            "--dossier", str(tmp_path / "dossier.json"),
            "--dossier-review", str(tmp_path / "dossier-review.json"),
            "--release-gate-audit", str(tmp_path / "audit.json"),
            "--review-record", str(tmp_path / "record.json"),
            "--review-notes", str(tmp_path / "notes.txt"),
            "--out", str(destination),
        ]
    )
    assert sha256(canonical).hexdigest() != "f" * 64
    assert rc == 2
    assert called is False
    assert not destination.exists()


def test_strategy_template_pair_write_is_atomic_on_preexisting_output(tmp_path: Path) -> None:
    record = tmp_path / "record.json"
    notes = tmp_path / "notes.txt"
    notes.write_text("existing\n", encoding="utf-8")
    try:
        operator_strategy_evidence_cli._write_pair_exclusive(record, "{}\n", notes, "notes\n")
    except ValueError as exc:
        assert "refusing to overwrite existing output" in str(exc)
    else:
        raise AssertionError("pair writer unexpectedly overwrote an existing output")
    assert not record.exists()
    assert notes.read_text(encoding="utf-8") == "existing\n"
