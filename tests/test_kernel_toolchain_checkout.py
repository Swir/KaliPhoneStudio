from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from kaliphonestudio.kernel_toolchain import KernelToolchainError, load_kernel_toolchain_lock
from kaliphonestudio.kernel_toolchain_checkout import capture_local_git_source_evidence


SOURCE_URL = "https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86"


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def _make_checkout_and_lock(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    _git(repo, "config", "user.name", "KaliPhoneStudio Tests")
    _git(repo, "config", "user.email", "tests@example.invalid")

    subtree = repo / "clang-r416183b"
    (subtree / "bin").mkdir(parents=True)
    (subtree / "AndroidVersion.txt").write_text(
        "12.0.5\nbased on r416183b\n", encoding="utf-8", newline="\n"
    )
    (subtree / "manifest_7284624.xml").write_text(
        "<manifest><project name=\"llvm-project\" revision=\"c935d99d7cf2016289302412d708641d52d2f7ee\"/></manifest>\n",
        encoding="utf-8",
        newline="\n",
    )
    (subtree / "bin" / "clang").write_bytes(b"locked-clang-fixture\n")

    _git(repo, "add", "clang-r416183b")
    _git(repo, "commit", "--quiet", "-m", "fixture")
    _git(repo, "remote", "add", "origin", SOURCE_URL)

    commit = _git(repo, "rev-parse", "HEAD")
    data: dict[str, object] = {
        "schema_version": 1,
        "name": "AOSP Android Clang r416183b fixture",
        "source_url": SOURCE_URL,
        "source_commit": commit,
        "subtree": "clang-r416183b",
        "tree_sha1": _git(repo, "rev-parse", f"{commit}:clang-r416183b"),
        "bin_tree_sha1": _git(repo, "rev-parse", f"{commit}:clang-r416183b/bin"),
        "android_version_blob_sha1": _git(
            repo, "rev-parse", f"{commit}:clang-r416183b/AndroidVersion.txt"
        ),
        "manifest_blob_sha1": _git(
            repo, "rev-parse", f"{commit}:clang-r416183b/manifest_7284624.xml"
        ),
        "android_version": "12.0.5",
        "clang_revision": "r416183b",
        "build_id": "7284624",
        "llvm_project_commit": "c935d99d7cf2016289302412d708641d52d2f7ee",
        "expected_clang_banner": "Android (7284624, based on r416183b) clang version 12.0.5",
        "host": "linux-x86_64",
        "beta_gate_credit": False,
    }
    lock_path = tmp_path / "lock.json"
    lock_path.write_text(json.dumps(data), encoding="utf-8")
    return repo, lock_path, data


def test_local_git_capture_verifies_exact_object_graph(tmp_path: Path):
    repo, lock_path, data = _make_checkout_and_lock(tmp_path)
    lock = load_kernel_toolchain_lock(lock_path)

    evidence = capture_local_git_source_evidence(lock, repo)

    assert evidence.source_commit == data["source_commit"]
    assert evidence.tree_sha1 == data["tree_sha1"]
    assert evidence.bin_tree_sha1 == data["bin_tree_sha1"]
    assert evidence.android_version_blob_sha1 == data["android_version_blob_sha1"]
    assert evidence.manifest_blob_sha1 == data["manifest_blob_sha1"]
    assert evidence.beta_gate_credit is False
    assert len(evidence.evidence_sha256()) == 64


def test_local_git_capture_rejects_dirty_tracked_content(tmp_path: Path):
    repo, lock_path, _ = _make_checkout_and_lock(tmp_path)
    lock = load_kernel_toolchain_lock(lock_path)
    (repo / "clang-r416183b" / "AndroidVersion.txt").write_text(
        "12.0.5\nbased on r416183b\nchanged\n", encoding="utf-8"
    )

    with pytest.raises(KernelToolchainError, match="modified tracked content"):
        capture_local_git_source_evidence(lock, repo)


def test_local_git_capture_rejects_wrong_origin(tmp_path: Path):
    repo, lock_path, _ = _make_checkout_and_lock(tmp_path)
    lock = load_kernel_toolchain_lock(lock_path)
    _git(repo, "remote", "set-url", "origin", "https://example.invalid/not-the-lock")

    with pytest.raises(KernelToolchainError, match="origin does not match"):
        capture_local_git_source_evidence(lock, repo)


def test_local_git_capture_rejects_locked_object_substitution(tmp_path: Path):
    repo, lock_path, data = _make_checkout_and_lock(tmp_path)
    data["bin_tree_sha1"] = "0" * 40
    lock_path.write_text(json.dumps(data), encoding="utf-8")
    lock = load_kernel_toolchain_lock(lock_path)

    with pytest.raises(KernelToolchainError, match="local Git object mismatch"):
        capture_local_git_source_evidence(lock, repo)
