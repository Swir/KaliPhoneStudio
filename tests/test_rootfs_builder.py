from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from kaliphonestudio.rootfs import RootfsError, load_rootfs_source_lock
from scripts import run_locked_rootfs_build as builder
from scripts import verify_live_kali_snapshot as snapshot_guard

ROOT = Path(__file__).parents[1]
LOCK_PATH = ROOT / "tools" / "rootfs-source-lock.json"


def _tool_map(tmp_path: Path) -> dict[str, str]:
    result = {}
    for name in builder._REQUIRED_HOST_TOOLS:
        path = tmp_path / name
        path.write_text("tool\n", encoding="utf-8")
        path.chmod(0o755)
        result[name] = str(path)
    return result


def _snapshot_file(tmp_path: Path, inrelease: bytes) -> Path:
    lock = load_rootfs_source_lock(LOCK_PATH)
    path = tmp_path / "repository-snapshot.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "mirror": lock.mirror,
                "suite": lock.suite,
                "architecture": lock.architecture,
                "signing_key_fingerprint": lock.archive_key_fingerprint,
                "inrelease_sha256": sha256(inrelease).hexdigest(),
                "package_indexes": [
                    {
                        "path": "main/binary-arm64/Packages.xz",
                        "size": 123,
                        "sha256": "b" * 64,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _inrelease_file(tmp_path: Path, payload: bytes) -> Path:
    path = tmp_path / "InRelease"
    path.write_bytes(payload)
    return path


def test_host_preflight_preserves_static_qemu_and_creates_upstream_sentinel(tmp_path, monkeypatch):
    checkout = tmp_path / "builder"
    checkout.mkdir()
    tool_dir = tmp_path / "tools"
    tool_dir.mkdir()
    tools = _tool_map(tool_dir)
    monkeypatch.setattr(builder, "_git_output", lambda checkout, *args: "")
    monkeypatch.setattr(
        builder.shutil,
        "which",
        lambda name: None if name == "qemu-aarch64" else tools.get(name),
    )

    sentinel = builder._prepare_host_environment(checkout)
    assert sentinel == checkout / ".dep_check"
    assert sentinel.read_text(encoding="utf-8") == builder._DEP_CHECK_MARKER


def test_host_preflight_fails_closed_without_static_qemu(tmp_path, monkeypatch):
    checkout = tmp_path / "builder"
    checkout.mkdir()
    tool_dir = tmp_path / "tools"
    tool_dir.mkdir()
    tools = _tool_map(tool_dir)
    tools.pop("qemu-aarch64-static")
    monkeypatch.setattr(builder, "_git_output", lambda checkout, *args: "")
    monkeypatch.setattr(builder.shutil, "which", lambda name: tools.get(name))

    with pytest.raises(RootfsError, match="qemu-aarch64-static"):
        builder._prepare_host_environment(checkout)


def test_host_preflight_rejects_dynamic_qemu_precedence(tmp_path, monkeypatch):
    checkout = tmp_path / "builder"
    checkout.mkdir()
    tool_dir = tmp_path / "tools"
    tool_dir.mkdir()
    tools = _tool_map(tool_dir)
    dynamic = tool_dir / "qemu-aarch64"
    dynamic.write_text("dynamic\n", encoding="utf-8")
    dynamic.chmod(0o755)
    tools["qemu-aarch64"] = str(dynamic)
    monkeypatch.setattr(builder, "_git_output", lambda checkout, *args: "")
    monkeypatch.setattr(builder.shutil, "which", lambda name: tools.get(name))

    with pytest.raises(RootfsError, match="dynamic qemu-aarch64"):
        builder._prepare_host_environment(checkout)


def test_captured_repository_guard_accepts_exact_signed_snapshot_state(tmp_path):
    lock = load_rootfs_source_lock(LOCK_PATH)
    inrelease = b"signed-kali-inrelease\n"
    snapshot = _snapshot_file(tmp_path, inrelease)
    raw = _inrelease_file(tmp_path, inrelease)

    digest = snapshot_guard.verify_captured_inrelease(lock, snapshot, raw)
    assert digest == sha256(inrelease).hexdigest()


def test_captured_repository_guard_rejects_tampered_inrelease(tmp_path):
    lock = load_rootfs_source_lock(LOCK_PATH)
    snapshot = _snapshot_file(tmp_path, b"captured-state\n")
    raw = _inrelease_file(tmp_path, b"tampered-state\n")

    with pytest.raises(RootfsError, match="does not match repository snapshot"):
        snapshot_guard.verify_captured_inrelease(lock, snapshot, raw)


def test_pair_start_guard_accepts_live_state_equal_to_capture(tmp_path, monkeypatch):
    lock = load_rootfs_source_lock(LOCK_PATH)
    inrelease = b"signed-kali-inrelease\n"
    snapshot = _snapshot_file(tmp_path, inrelease)
    raw = _inrelease_file(tmp_path, inrelease)
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(stdout=inrelease, stderr=b"")

    monkeypatch.setattr(snapshot_guard.subprocess, "run", fake_run)
    digest = snapshot_guard.verify_live_snapshot(lock, snapshot, raw)
    assert digest == sha256(inrelease).hexdigest()
    assert calls
    assert calls[0][0][0] == "curl"
    assert "=https" in calls[0][0]
    assert calls[0][0][-1].startswith("https://")
    assert calls[0][1]["shell"] is False


def test_pair_start_guard_rejects_mirror_drift(tmp_path, monkeypatch):
    lock = load_rootfs_source_lock(LOCK_PATH)
    captured = b"captured-state\n"
    snapshot = _snapshot_file(tmp_path, captured)
    raw = _inrelease_file(tmp_path, captured)
    monkeypatch.setattr(
        snapshot_guard.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=b"new-state\n", stderr=b""),
    )

    with pytest.raises(RootfsError, match="refusing to start the reproducibility pair"):
        snapshot_guard.verify_live_snapshot(lock, snapshot, raw)
