import json
from hashlib import sha256
from pathlib import Path

import pytest

from kaliphonestudio.extractor import (
    ExtractionError,
    ExtractorLock,
    lock_from_manifest,
    verify_extractor,
)

ROOT = Path(__file__).resolve().parents[1]
REPO_LOCK = ROOT / "tools" / "extractor-locks.json"


def _direct_lock(tool: Path, digest: str, *, source_commit: str = "a" * 40) -> ExtractorLock:
    return ExtractorLock(tool, digest, "https://github.com/example/tool", source_commit)


def test_accepts_exact_extractor_sha_and_pinned_source(tmp_path: Path):
    tool = tmp_path / "payload-dumper-go"
    tool.write_bytes(b"test extractor binary")
    digest = sha256(tool.read_bytes()).hexdigest()
    assert verify_extractor(_direct_lock(tool, digest)) == digest


def test_rejects_extractor_hash_mismatch(tmp_path: Path):
    tool = tmp_path / "payload-dumper-go"
    tool.write_bytes(b"unexpected")
    with pytest.raises(ExtractionError, match="mismatch"):
        verify_extractor(_direct_lock(tool, "0" * 64))


def test_rejects_non_sha_lock(tmp_path: Path):
    tool = tmp_path / "payload-dumper-go"
    tool.write_bytes(b"x")
    with pytest.raises(ExtractionError, match="SHA-256"):
        verify_extractor(_direct_lock(tool, "latest"))


def test_rejects_unpinned_source_commit(tmp_path: Path):
    tool = tmp_path / "payload-dumper-go"
    tool.write_bytes(b"x")
    digest = sha256(tool.read_bytes()).hexdigest()
    with pytest.raises(ExtractionError, match="full commit"):
        verify_extractor(_direct_lock(tool, digest, source_commit="main"))


def test_repository_manifest_authorizes_no_unverified_binary(tmp_path: Path):
    tool = tmp_path / "payload-dumper-go"
    tool.write_bytes(b"anything")
    with pytest.raises(ExtractionError, match="not authorized"):
        lock_from_manifest(tool, REPO_LOCK, "windows-amd64")


def test_manifest_platform_hash_is_authoritative(tmp_path: Path):
    tool = tmp_path / "payload-dumper-go"
    tool.write_bytes(b"reproducible binary")
    digest = sha256(tool.read_bytes()).hexdigest()
    data = json.loads(REPO_LOCK.read_text(encoding="utf-8"))
    data["artifacts"]["test-amd64"] = {"sha256": digest}
    manifest = tmp_path / "locks.json"
    manifest.write_text(json.dumps(data), encoding="utf-8")

    lock = lock_from_manifest(tool, manifest, "test-amd64")
    assert lock.platform == "test-amd64"
    assert lock.sha256 == digest
    assert verify_extractor(lock) == digest


def test_manifest_lock_rejects_binary_different_from_authorized_hash(tmp_path: Path):
    tool = tmp_path / "payload-dumper-go"
    tool.write_bytes(b"tampered binary")
    data = json.loads(REPO_LOCK.read_text(encoding="utf-8"))
    data["artifacts"]["test-amd64"] = {"sha256": "0" * 64}
    manifest = tmp_path / "locks.json"
    manifest.write_text(json.dumps(data), encoding="utf-8")

    lock = lock_from_manifest(tool, manifest, "test-amd64")
    with pytest.raises(ExtractionError, match="mismatch"):
        verify_extractor(lock)
