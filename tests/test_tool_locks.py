import json
from pathlib import Path

import pytest

from kaliphonestudio.tool_locks import ToolLockError, load_tool_lock

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "tools" / "extractor-locks.json"
WINDOWS_REVIEWED_SHA256 = "72495e8300283ab5c8943827b1c6dd09c308dc11f0fc5c77074a99d0517fbff8"


def test_repository_extractor_lock_is_pinned_and_authorized():
    lock = load_tool_lock(LOCK)
    assert lock.extractor == "payload-dumper-go"
    assert len(lock.source_commit) == 40
    assert lock.toolchain == "go"
    assert lock.toolchain_version == "1.27.0"
    assert "-trimpath" in lock.build_command
    assert "-buildvcs=false" in lock.build_command
    assert "-ldflags=-buildid=" in lock.build_command
    assert set(lock.artifacts) == {"linux-amd64", "windows-amd64"}
    assert lock.require_artifact("linux-amd64").sha256 == "a9e5806356af76b11643f3129b5516a638e9dc0c53cefd40b665a916683c83d0"
    assert lock.require_artifact("windows-amd64").sha256 == WINDOWS_REVIEWED_SHA256
    with pytest.raises(ToolLockError, match="no locked extractor artifact"):
        lock.require_artifact("darwin-amd64")


def test_rejects_unpinned_source(tmp_path):
    data = json.loads(LOCK.read_text(encoding="utf-8"))
    data["source"]["commit"] = "main"
    path = tmp_path / "lock.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ToolLockError, match="full commit"):
        load_tool_lock(path)


def test_rejects_missing_toolchain_version(tmp_path):
    data = json.loads(LOCK.read_text(encoding="utf-8"))
    data["build"].pop("toolchain_version")
    path = tmp_path / "lock.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ToolLockError, match="toolchain version"):
        load_tool_lock(path)


def test_rejects_unversioned_toolchain(tmp_path):
    data = json.loads(LOCK.read_text(encoding="utf-8"))
    data["build"]["toolchain_version"] = "latest"
    path = tmp_path / "lock.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ToolLockError, match="toolchain version"):
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
