from __future__ import annotations

import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / "BUILD_STATUS.json"
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def _load(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_reviewed_authority_status_identity_matches_immutable_records() -> None:
    status = _load(STATUS_PATH)
    specs = (
        (
            "kernel",
            "kernel_reproducibility_authority_run",
            "kernel_authority_commit",
            "kernel_authority_artifact_id",
            "kernel_authority_record",
        ),
        (
            "rootfs",
            "rootfs_reproducibility_authority_run",
            "rootfs_authority_commit",
            "rootfs_authority_artifact_id",
            "rootfs_authority_record",
        ),
        (
            "device-tree",
            "device_tree_reproducibility_authority_run",
            "device_tree_authority_commit",
            "device_tree_authority_artifact_id",
            "device_tree_authority_record",
        ),
    )
    for label, run_key, commit_key, artifact_key, record_key in specs:
        record_path = ROOT / status[record_key]
        record = _load(record_path)
        assert record.get("schema_version") == 1, label
        assert record.get("reviewed") is True, label
        assert record.get("strict_byte_identical") is True, label
        assert record.get("hardware_verified") is False, label
        assert record.get("beta_gate_credit") is False, label
        assert status[run_key] == record["authority_run_id"], label
        assert status[commit_key] == record["authority_commit"], label
        assert status[artifact_key] == record["authority_artifact_id"], label
        assert isinstance(status[run_key], int) and status[run_key] > 0, label
        assert isinstance(status[artifact_key], int) and status[artifact_key] > 0, label
        assert COMMIT_RE.fullmatch(status[commit_key]), label


def test_blocked_hardware_state_cannot_claim_beta_ready() -> None:
    status = _load(STATUS_PATH)
    assert status["hardware_verified"] is False
    assert status["beta_gate"] == "BLOCKED"
    assert status["project_progress_percent"] == 58
