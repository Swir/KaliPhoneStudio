from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from kaliphonestudio.kernel_toolchain import (
    KernelToolchainError,
    capture_gitiles_source_evidence,
    create_source_evidence,
    load_kernel_toolchain_lock,
    verify_android_version_capture,
    verify_gitiles_tree_capture,
)


LOCK = {
    "schema_version": 1,
    "name": "AOSP Android Clang r416183b",
    "source_url": "https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86",
    "source_commit": "69e4b00fe608feec1bde77294dd648427644725f",
    "subtree": "clang-r416183b",
    "tree_sha1": "b2d417040452b5fb47ea22fb70d79741fa6ef455",
    "bin_tree_sha1": "6f8d6e866e540da23d80d599e959712f6de7fe85",
    "android_version_blob_sha1": "76b2048751fe7c55ebe3c713036dc1382d628d34",
    "manifest_blob_sha1": "41b501575f6db19a9361b0d62d62fe19ef62f47e",
    "android_version": "12.0.5",
    "clang_revision": "r416183b",
    "build_id": "7284624",
    "llvm_project_commit": "c935d99d7cf2016289302412d708641d52d2f7ee",
    "expected_clang_banner": "Android (7284624, based on r416183b) clang version 12.0.5",
    "host": "linux-x86_64",
    "beta_gate_credit": False,
}


def _write_lock(tmp_path: Path, mutate=None) -> Path:
    data = dict(LOCK)
    if mutate:
        mutate(data)
    path = tmp_path / "lock.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _tree_payload(*, tree_id=None, version_blob=None) -> bytes:
    payload = {
        "id": tree_id or LOCK["tree_sha1"],
        "entries": [
            {"mode": 33188, "type": "blob", "id": version_blob or LOCK["android_version_blob_sha1"], "name": "AndroidVersion.txt"},
            {"mode": 33188, "type": "blob", "id": LOCK["manifest_blob_sha1"], "name": "manifest_7284624.xml"},
            {"mode": 16384, "type": "tree", "id": LOCK["bin_tree_sha1"], "name": "bin"},
        ],
    }
    return b")]}'\n" + json.dumps(payload).encode("utf-8")


def test_repository_lock_parses_and_is_canonical(tmp_path: Path):
    lock = load_kernel_toolchain_lock(_write_lock(tmp_path))
    assert lock.clang_revision == "r416183b"
    assert lock.android_version == "12.0.5"
    assert lock.beta_gate_credit is False
    assert len(lock.lock_sha256()) == 64


@pytest.mark.parametrize(
    "mutator",
    [
        lambda d: d.__setitem__("source_url", "http://android.googlesource.com/x"),
        lambda d: d.__setitem__("source_commit", "deadbeef"),
        lambda d: d.__setitem__("subtree", "../clang-r416183b"),
        lambda d: d.__setitem__("beta_gate_credit", True),
        lambda d: d.__setitem__("expected_clang_banner", "clang 12"),
    ],
)
def test_lock_rejects_unsafe_or_weak_identity(tmp_path: Path, mutator):
    with pytest.raises(KernelToolchainError):
        load_kernel_toolchain_lock(_write_lock(tmp_path, mutator))


def test_gitiles_tree_requires_exact_subtree_and_metadata_objects(tmp_path: Path):
    lock = load_kernel_toolchain_lock(_write_lock(tmp_path))
    verify_gitiles_tree_capture(lock, _tree_payload())
    with pytest.raises(KernelToolchainError):
        verify_gitiles_tree_capture(lock, _tree_payload(tree_id="0" * 40))
    with pytest.raises(KernelToolchainError):
        verify_gitiles_tree_capture(lock, _tree_payload(version_blob="1" * 40))


def test_android_version_is_exact_not_substring(tmp_path: Path):
    lock = load_kernel_toolchain_lock(_write_lock(tmp_path))
    verify_android_version_capture(lock, b"12.0.5\nbased on r416183b\n")
    with pytest.raises(KernelToolchainError):
        verify_android_version_capture(lock, b"12.0.5-custom\nbased on r416183b\n")


def test_source_evidence_is_canonical_and_never_grants_beta_credit(tmp_path: Path):
    lock = load_kernel_toolchain_lock(_write_lock(tmp_path))
    evidence = create_source_evidence(
        lock,
        tree_payload=_tree_payload(),
        android_version_payload=b"12.0.5\nbased on r416183b\n",
    )
    assert evidence.beta_gate_credit is False
    assert evidence.tree_sha1 == LOCK["tree_sha1"]
    assert evidence.source_commit == LOCK["source_commit"]
    assert len(evidence.evidence_sha256()) == 64


class _Response:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, _limit):
        return self.payload


def test_gitiles_capture_uses_exact_locked_urls(tmp_path: Path):
    lock = load_kernel_toolchain_lock(_write_lock(tmp_path))
    seen = []

    def opener(request, timeout):
        seen.append((request.full_url, timeout))
        if request.full_url.endswith("/?format=JSON"):
            return _Response(_tree_payload())
        if request.full_url.endswith("/AndroidVersion.txt?format=TEXT"):
            return _Response(base64.b64encode(b"12.0.5\nbased on r416183b\n"))
        raise AssertionError(request.full_url)

    evidence = capture_gitiles_source_evidence(lock, opener=opener)
    assert evidence.lock_sha256 == lock.lock_sha256()
    assert len(seen) == 2
    assert all(LOCK["source_commit"] in url for url, _ in seen)
    assert all("/clang-r416183b/" in url for url, _ in seen)
