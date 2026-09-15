from hashlib import sha256
from pathlib import Path

import pytest

from kaliphonestudio.extractor import ExtractionError, ExtractorLock, verify_extractor


def test_accepts_exact_extractor_sha_and_pinned_source(tmp_path: Path):
    tool = tmp_path / "payload-dumper-go"
    tool.write_bytes(b"test extractor binary")
    digest = sha256(tool.read_bytes()).hexdigest()
    assert verify_extractor(ExtractorLock(tool, digest)) == digest


def test_rejects_extractor_hash_mismatch(tmp_path: Path):
    tool = tmp_path / "payload-dumper-go"
    tool.write_bytes(b"unexpected")
    with pytest.raises(ExtractionError, match="mismatch"):
        verify_extractor(ExtractorLock(tool, "0" * 64))


def test_rejects_non_sha_lock(tmp_path: Path):
    tool = tmp_path / "payload-dumper-go"
    tool.write_bytes(b"x")
    with pytest.raises(ExtractionError, match="SHA-256"):
        verify_extractor(ExtractorLock(tool, "latest"))


def test_rejects_unpinned_source_commit(tmp_path: Path):
    tool = tmp_path / "payload-dumper-go"
    tool.write_bytes(b"x")
    digest = sha256(tool.read_bytes()).hexdigest()
    lock = ExtractorLock(tool, digest, source_commit="main")
    with pytest.raises(ExtractionError, match="full commit"):
        verify_extractor(lock)
