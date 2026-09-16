import gzip
import os
from pathlib import Path

import pytest

from kaliphonestudio.initramfs import (
    InitramfsError,
    build_reproducible_initramfs,
    inspect_initramfs_artifact,
    verify_initramfs_artifact,
    write_initramfs_evidence,
)
from kaliphonestudio.lz4_legacy import LEGACY_MAGIC_BYTES, decompress_legacy


def _stage(root: Path) -> Path:
    root.mkdir()
    init = root / "init"
    init.write_text("#!/bin/sh\necho rescue\n", encoding="utf-8")
    init.chmod(0o755)
    etc = root / "etc"
    etc.mkdir()
    etc.chmod(0o755)
    config = etc / "rescue.conf"
    config.write_text("ssh=disabled\nnetwork=disabled\n", encoding="utf-8")
    config.chmod(0o644)
    bin_dir = root / "bin"
    bin_dir.mkdir()
    bin_dir.chmod(0o755)
    os.symlink("../init", bin_dir / "rescue-init")
    return root


def test_initramfs_is_byte_identical_across_independent_staging_trees(tmp_path):
    first_stage = _stage(tmp_path / "stage-a")
    second_stage = _stage(tmp_path / "stage-b")

    # Host mtimes are deliberately different; the archive contract normalizes them.
    os.utime(first_stage / "init", (1_000_000, 1_000_000))
    os.utime(second_stage / "init", (2_000_000, 2_000_000))

    first_out = tmp_path / "a.cpio.gz"
    second_out = tmp_path / "b.cpio.gz"
    first = build_reproducible_initramfs(first_stage, first_out)
    second = build_reproducible_initramfs(second_stage, second_out)

    assert first.reproducible is True
    assert first.archive_format == "cpio-newc"
    assert first.compression == "gzip-mtime0-level9"
    assert first.artifact_sha256 == second.artifact_sha256
    assert first.entry_manifest_sha256 == second.entry_manifest_sha256
    assert first.init_sha256 == second.init_sha256
    assert first_out.read_bytes() == second_out.read_bytes()
    raw = gzip.decompress(first_out.read_bytes())
    assert raw.startswith(b"070701")
    assert b"TRAILER!!!\x00" in raw
    inspection = inspect_initramfs_artifact(first, first_out)
    assert inspection.entry_count == first.entry_count
    assert inspection.entry_manifest_sha256 == first.entry_manifest_sha256
    verify_initramfs_artifact(first, first_out)


def test_lz4_initramfs_is_byte_identical_and_structurally_verified(tmp_path):
    first_stage = _stage(tmp_path / "stage-a")
    second_stage = _stage(tmp_path / "stage-b")
    os.utime(first_stage / "init", (10, 20))
    os.utime(second_stage / "init", (30, 40))

    first_out = tmp_path / "a.cpio.lz4"
    second_out = tmp_path / "b.cpio.lz4"
    first = build_reproducible_initramfs(first_stage, first_out, compression="lz4")
    second = build_reproducible_initramfs(second_stage, second_out, compression="lz4")

    assert first.compression == "lz4-legacy-literal-v1"
    assert first.artifact_sha256 == second.artifact_sha256
    assert first.entry_manifest_sha256 == second.entry_manifest_sha256
    assert first_out.read_bytes() == second_out.read_bytes()
    assert first_out.read_bytes().startswith(LEGACY_MAGIC_BYTES)
    raw, stream = decompress_legacy(first_out.read_bytes())
    assert stream.block_count >= 1
    assert raw.startswith(b"070701")
    assert b"TRAILER!!!\x00" in raw
    inspection = inspect_initramfs_artifact(first, first_out)
    assert inspection.compression == "lz4-legacy-literal-v1"
    assert inspection.init_sha256 == first.init_sha256


def test_initramfs_evidence_is_canonical_and_detects_post_build_drift(tmp_path):
    stage = _stage(tmp_path / "stage")
    artifact = tmp_path / "rescue.cpio.gz"
    evidence = build_reproducible_initramfs(stage, artifact)
    evidence_path = tmp_path / "evidence" / "initramfs.json"

    digest = write_initramfs_evidence(evidence, evidence_path)
    assert digest == evidence.evidence_sha256()
    assert evidence_path.read_text(encoding="utf-8") == evidence.canonical_json()

    artifact.write_bytes(artifact.read_bytes() + b"tamper")
    with pytest.raises(InitramfsError, match="changed after reproducibility verification"):
        verify_initramfs_artifact(evidence, artifact)


def test_initramfs_requires_executable_regular_init(tmp_path):
    stage = tmp_path / "stage"
    stage.mkdir()
    init = stage / "init"
    init.write_text("#!/bin/sh\n", encoding="utf-8")
    init.chmod(0o644)

    with pytest.raises(InitramfsError, match="must be executable"):
        build_reproducible_initramfs(stage, tmp_path / "bad.cpio.gz")


def test_initramfs_rejects_setuid_or_setgid_content(tmp_path):
    stage = _stage(tmp_path / "stage")
    privileged = stage / "bin" / "privileged"
    privileged.write_text("nope\n", encoding="utf-8")
    privileged.chmod(0o4755)

    with pytest.raises(InitramfsError, match="setuid/setgid"):
        build_reproducible_initramfs(stage, tmp_path / "bad.cpio.gz")


def test_initramfs_rejects_world_writable_regular_file(tmp_path):
    stage = _stage(tmp_path / "stage")
    unsafe = stage / "etc" / "unsafe.conf"
    unsafe.write_text("unsafe=yes\n", encoding="utf-8")
    unsafe.chmod(0o666)

    with pytest.raises(InitramfsError, match="world-writable"):
        build_reproducible_initramfs(stage, tmp_path / "bad.cpio.lz4", compression="lz4")


def test_initramfs_refuses_existing_output(tmp_path):
    stage = _stage(tmp_path / "stage")
    output = tmp_path / "existing.cpio.gz"
    output.write_bytes(b"keep-me")

    with pytest.raises(InitramfsError, match="refusing to overwrite"):
        build_reproducible_initramfs(stage, output)
    assert output.read_bytes() == b"keep-me"
