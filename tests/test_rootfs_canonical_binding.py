import io
import json
from dataclasses import replace
from pathlib import Path
import tarfile

import pytest

from kaliphonestudio.rootfs import (
    RootfsError,
    create_reproducible_rootfs_evidence,
    load_rootfs_source_lock,
    repository_snapshot_from_dict,
)
from kaliphonestudio.rootfs_canonical import canonicalize_rootfs_archive
from kaliphonestudio.rootfs_canonical_binding import (
    canonicalization_evidence_from_dict,
    canonicalization_policy_sha256,
    create_rootfs_canonicalization_binding,
    rootfs_artifact_evidence_from_dict,
    verify_rootfs_canonicalization_binding,
    write_rootfs_canonicalization_binding,
)


ROOT = Path(__file__).resolve().parents[1]


def _add_file(archive: tarfile.TarFile, name: str, data: bytes, mtime: int) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.uid = 0
    info.gid = 0
    info.mode = 0o600 if name.endswith("/etc/shadow") else 0o644
    info.mtime = mtime
    archive.addfile(info, io.BytesIO(data))


def _raw_rootfs(path: Path, *, marker: bytes, mtime: int) -> Path:
    prefix = "kali-arm64"
    status = (
        b"Package: base-files\n"
        b"Status: install ok installed\n"
        b"Version: 1.0\n"
        b"Architecture: arm64\n\n"
    )
    with tarfile.open(path, "w:xz", format=tarfile.PAX_FORMAT) as archive:
        _add_file(archive, f"{prefix}/var/lib/dpkg/status", status, mtime)
        _add_file(archive, f"{prefix}/etc/machine-id", marker * 32 + b"\n", mtime + 1)
        _add_file(archive, f"{prefix}/var/lib/dbus/machine-id", marker * 32 + b"\n", mtime + 2)
        _add_file(archive, f"{prefix}/etc/fake-hwclock.data", marker + b"-clock\n", mtime + 3)
        _add_file(
            archive,
            f"{prefix}/etc/shadow",
            b"root:!:0:0:99999:7:::\nkali:$y$" + marker + b"$hash:21000:0:99999:7:::\n",
            mtime + 4,
        )
        _add_file(archive, f"{prefix}/var/cache/ldconfig/aux-cache", marker + b"-cache", mtime + 5)
        _add_file(archive, f"{prefix}/usr/bin/payload", b"stable payload\n", mtime + 6)
    return path


def _fixture(tmp_path: Path):
    lock = load_rootfs_source_lock(ROOT / "tools" / "rootfs-source-lock.json")
    snapshot = repository_snapshot_from_dict(
        {
            "schema_version": 2,
            "mirror": lock.mirror,
            "suite": lock.suite,
            "architecture": lock.architecture,
            "signing_key_fingerprint": lock.archive_key_fingerprint,
            "inrelease_sha256": "a" * 64,
            "package_indexes": [
                {"path": "main/binary-arm64/Packages.xz", "size": 100, "sha256": "b" * 64}
            ],
        }
    )
    raw_a = _raw_rootfs(tmp_path / "raw-a.tar.xz", marker=b"a", mtime=100)
    raw_b = _raw_rootfs(tmp_path / "raw-b.tar.xz", marker=b"b", mtime=900)
    canonical_a_path = tmp_path / "canonical-a.tar.xz"
    canonical_b_path = tmp_path / "canonical-b.tar.xz"
    canonical_a = canonicalize_rootfs_archive(raw_a, canonical_a_path)
    canonical_b = canonicalize_rootfs_archive(raw_b, canonical_b_path)
    assert canonical_a_path.read_bytes() == canonical_b_path.read_bytes()
    rootfs_evidence = create_reproducible_rootfs_evidence(
        lock,
        snapshot,
        first_artifact=canonical_a_path,
        second_artifact=canonical_b_path,
    )
    return lock, snapshot, rootfs_evidence, canonical_a_path, canonical_a, canonical_b


def test_binding_connects_both_raw_audits_to_exact_strict_rootfs(tmp_path):
    lock, snapshot, rootfs_evidence, artifact, canonical_a, canonical_b = _fixture(tmp_path)
    binding = create_rootfs_canonicalization_binding(
        lock,
        snapshot,
        rootfs_evidence,
        artifact=artifact,
        canonical_a=canonical_a,
        canonical_b=canonical_b,
    )

    assert binding.schema_version == 1
    assert binding.rootfs_evidence_sha256 == rootfs_evidence.evidence_sha256()
    assert binding.source_lock_sha256 == lock.lock_sha256()
    assert binding.repository_snapshot_sha256 == snapshot.evidence_sha256()
    assert binding.canonicalization_policy_sha256 == canonicalization_policy_sha256()
    assert binding.canonicalization_a_evidence_sha256 == canonical_a.evidence_sha256()
    assert binding.canonicalization_b_evidence_sha256 == canonical_b.evidence_sha256()
    assert binding.raw_a_sha256 == canonical_a.input_sha256
    assert binding.raw_b_sha256 == canonical_b.input_sha256
    assert binding.artifact_sha256 == rootfs_evidence.artifact_sha256
    assert binding.strict_byte_identical is True
    assert binding.beta_gate_credit is False

    verify_rootfs_canonicalization_binding(
        binding,
        lock,
        snapshot,
        rootfs_evidence,
        artifact=artifact,
        canonical_a=canonical_a,
        canonical_b=canonical_b,
    )

    destination = tmp_path / "evidence" / "rootfs-canonical-binding.json"
    digest = write_rootfs_canonicalization_binding(binding, destination)
    assert digest == binding.evidence_sha256()
    assert destination.read_text(encoding="utf-8") == binding.canonical_json()
    with pytest.raises(RootfsError, match="overwrite"):
        write_rootfs_canonicalization_binding(binding, destination)


def test_binding_rejects_canonical_output_substitution(tmp_path):
    lock, snapshot, rootfs_evidence, artifact, canonical_a, canonical_b = _fixture(tmp_path)
    changed = replace(canonical_b, output_sha256="f" * 64)
    with pytest.raises(RootfsError, match="output hash"):
        create_rootfs_canonicalization_binding(
            lock,
            snapshot,
            rootfs_evidence,
            artifact=artifact,
            canonical_a=canonical_a,
            canonical_b=changed,
        )


def test_binding_rejects_pair_shape_and_beta_credit_drift(tmp_path):
    lock, snapshot, rootfs_evidence, artifact, canonical_a, canonical_b = _fixture(tmp_path)
    changed_shape = replace(canonical_b, archive_prefix="other")
    with pytest.raises(RootfsError, match="archive prefix"):
        create_rootfs_canonicalization_binding(
            lock,
            snapshot,
            rootfs_evidence,
            artifact=artifact,
            canonical_a=canonical_a,
            canonical_b=changed_shape,
        )

    credited = replace(canonical_b, beta_gate_credit=True)
    with pytest.raises(RootfsError, match="Beta credit"):
        create_rootfs_canonicalization_binding(
            lock,
            snapshot,
            rootfs_evidence,
            artifact=artifact,
            canonical_a=canonical_a,
            canonical_b=credited,
        )


def test_strict_json_loaders_reject_unknown_or_nonreproducible_records(tmp_path):
    lock, snapshot, rootfs_evidence, artifact, canonical_a, canonical_b = _fixture(tmp_path)

    canonical_raw = json.loads(canonical_a.canonical_json())
    assert canonicalization_evidence_from_dict(canonical_raw) == canonical_a
    canonical_raw["unexpected"] = True
    with pytest.raises(RootfsError, match="schema"):
        canonicalization_evidence_from_dict(canonical_raw)

    rootfs_raw = json.loads(rootfs_evidence.canonical_json())
    assert rootfs_artifact_evidence_from_dict(rootfs_raw) == rootfs_evidence
    rootfs_raw["reproducible"] = False
    with pytest.raises(RootfsError, match="not reproducible"):
        rootfs_artifact_evidence_from_dict(rootfs_raw)
