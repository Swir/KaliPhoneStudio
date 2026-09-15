import json
from pathlib import Path

import pytest

from kaliphonestudio.tool_locks import ToolLockError, load_tool_lock

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "tools" / "extractor-locks.json"


def test_repository_extractor_lock_is_pinned_and_fail_closed():
    lock = load_tool_lock(LOCK)
    assert lock.extractor == "payload-dumper-go"
    assert len(lock.source_commit) == 40
    assert "-trimpath" in lock.build_command
    assert lock.artifacts == {}
    with pytest.raises(ToolLockError, match="no locked extractor artifact"):
        lock.require_artifact("windows-amd64")


def test_rejects_unpinned_source(tmp_path):
    data = json.loads(LOCK.read_text(encoding="utf-8"))
    data["source"]["commit"] = "main"
    path = tmp_path / "lock.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ToolLockError, match="full commit"):
        load_tool_lock(path)


def test_accepts_and_resolves_locked_artifact(tmp_path):
    data = json.loads(LOCK.read_text(encoding="utf-8"))
    data["artifacts"]["linux-amd64"] = {"sha256": "a" * 64}
    path = tmp_path / "lock.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    lock = load_tool_lock(path)
    assert lock.require_artifact("linux-amd64").sha256 == "a" * 64


def test_rejects_malformed_artifact_hash(tmp_path):
    data = json.loads(LOCK.read_text(encoding="utf-8"))
    data["artifacts"]["linux-amd64"] = {"sha256": "not-a-hash"}
    path = tmp_path / "lock.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ToolLockError, match="invalid SHA-256"):
        load_tool_lock(path)
