import json
from pathlib import Path

import pytest

from kaliphonestudio.rootfs import (
    RootfsError,
    create_reproducible_rootfs_evidence,
    load_rootfs_source_lock,
    repository_snapshot_from_dict,
    verify_rootfs_artifact,
    write_rootfs_artifact_evidence,
)

ROOT = Path(__file__).parents[1]
LOCK_PATH = ROOT / "tools" / "rootfs-source-lock.json"


def snapshot(lock):
    return repository_snapshot_from_dict(
        {
            "schema_version": 1,
            "mirror": lock.mirror,
            "suite": lock.suite,
            "architecture": lock.architecture,
            "inrelease_sha256": "a" * 64,
            "package_index_sha256s": ["b" * 64, "c" * 64],
            "package_manifest_sha256": "d" * 64,
        }
    )


def test_repository_rootfs_lock_is_exact_and_fail_closed():
    lock = load_rootfs_source_lock(LOCK_PATH)
    assert lock.source_commit == "20238a2f2d547d7989a4dec287d4f5ef528ed701"
    assert lock.release_tag == "2026.2"
    assert lock.architecture == "arm64"
    assert lock.suite == "kali-rolling"
    assert lock.repository_evidence_required is True
    assert lock.double_build_required is True
    assert "arm64" in lock.command


def test_rootfs_lock_rejects_moving_source_ref(tmp_path):
    raw = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    raw["source"]["commit"] = "main"
    bad = tmp_path / "rootfs-source-lock.json"
    bad.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RootfsError, match="full 40-hex commit"):
        load_rootfs_source_lock(bad)


def test_rootfs_lock_rejects_missing_repository_evidence_requirement(tmp_path):
    raw = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    raw["build_contract"]["repository_evidence_required"] = False
    bad = tmp_path / "rootfs-source-lock.json"
    bad.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RootfsError, match="repository snapshot evidence"):
        load_rootfs_source_lock(bad)


def test_identical_double_build_emits_verifiable_evidence(tmp_path):
    lock = load_rootfs_source_lock(LOCK_PATH)
    repo = snapshot(lock)
    first = tmp_path / "kalifs-arm64-a.tar.xz"
    second = tmp_path / "kalifs-arm64-b.tar.xz"
    payload = b"deterministic-rootfs-fixture" * 64
    first.write_bytes(payload)
    second.write_bytes(payload)

    evidence = create_reproducible_rootfs_evidence(
        lock, repo, first_artifact=first, second_artifact=second
    )
    assert evidence.reproducible is True
    assert evidence.architecture == "arm64"
    verify_rootfs_artifact(lock, repo, evidence, artifact=first)

    destination = tmp_path / "evidence" / "rootfs-artifact.json"
    assert write_rootfs_artifact_evidence(evidence, destination) == evidence.evidence_sha256()
    assert destination.read_text(encoding="utf-8") == evidence.canonical_json()


def test_nonidentical_double_build_fails_closed(tmp_path):
    lock = load_rootfs_source_lock(LOCK_PATH)
    repo = snapshot(lock)
    first = tmp_path / "a.tar.xz"
    second = tmp_path / "b.tar.xz"
    first.write_bytes(b"build-a")
    second.write_bytes(b"build-b")
    with pytest.raises(RootfsError, match="not reproducible"):
        create_reproducible_rootfs_evidence(
            lock, repo, first_artifact=first, second_artifact=second
        )


def test_repository_snapshot_must_match_locked_suite_arch_and_mirror(tmp_path):
    lock = load_rootfs_source_lock(LOCK_PATH)
    repo = repository_snapshot_from_dict(
        {
            "schema_version": 1,
            "mirror": lock.mirror,
            "suite": lock.suite,
            "architecture": "amd64",
            "inrelease_sha256": "a" * 64,
            "package_index_sha256s": ["b" * 64],
            "package_manifest_sha256": "c" * 64,
        }
    )
    first = tmp_path / "a.tar.xz"
    second = tmp_path / "b.tar.xz"
    first.write_bytes(b"same")
    second.write_bytes(b"same")
    with pytest.raises(RootfsError, match="does not match rootfs source lock"):
        create_reproducible_rootfs_evidence(
            lock, repo, first_artifact=first, second_artifact=second
        )


def test_verified_rootfs_artifact_rejects_post_build_drift(tmp_path):
    lock = load_rootfs_source_lock(LOCK_PATH)
    repo = snapshot(lock)
    first = tmp_path / "a.tar.xz"
    second = tmp_path / "b.tar.xz"
    first.write_bytes(b"same-rootfs")
    second.write_bytes(b"same-rootfs")
    evidence = create_reproducible_rootfs_evidence(
        lock, repo, first_artifact=first, second_artifact=second
    )
    first.write_bytes(b"tampered-rootfs")
    with pytest.raises(RootfsError, match="changed after reproducibility verification"):
        verify_rootfs_artifact(lock, repo, evidence, artifact=first)


def test_repository_snapshot_rejects_malformed_hash():
    lock = load_rootfs_source_lock(LOCK_PATH)
    with pytest.raises(RootfsError, match="InRelease"):
        repository_snapshot_from_dict(
            {
                "schema_version": 1,
                "mirror": lock.mirror,
                "suite": lock.suite,
                "architecture": lock.architecture,
                "inrelease_sha256": "not-a-hash",
                "package_index_sha256s": ["b" * 64],
                "package_manifest_sha256": "c" * 64,
            }
        )
