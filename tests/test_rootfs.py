import io
import json
from pathlib import Path
import tarfile

import pytest

from kaliphonestudio.rootfs import (
    RootfsError,
    create_reproducible_rootfs_evidence,
    load_rootfs_source_lock,
    package_manifest_from_rootfs,
    repository_snapshot_from_dict,
    repository_snapshot_from_inrelease,
    verify_rootfs_artifact,
    write_package_manifest,
    write_rootfs_artifact_evidence,
)

ROOT = Path(__file__).parents[1]
LOCK_PATH = ROOT / "tools" / "rootfs-source-lock.json"


def snapshot(lock):
    return repository_snapshot_from_dict(
        {
            "schema_version": 2,
            "mirror": lock.mirror,
            "suite": lock.suite,
            "architecture": lock.architecture,
            "signing_key_fingerprint": lock.archive_key_fingerprint,
            "inrelease_sha256": "a" * 64,
            "package_indexes": [
                {
                    "path": "main/binary-arm64/Packages.xz",
                    "size": 1024,
                    "sha256": "b" * 64,
                },
                {
                    "path": "non-free/binary-arm64/Packages.xz",
                    "size": 512,
                    "sha256": "c" * 64,
                },
            ],
        }
    )


def rootfs_tar(path: Path, *, packages=None, extra=b"") -> Path:
    packages = packages or [
        ("base-files", "1.0", "arm64"),
        ("kali-defaults", "2.0", "all"),
    ]
    status = ""
    for package, version, architecture in packages:
        status += (
            f"Package: {package}\n"
            "Status: install ok installed\n"
            f"Architecture: {architecture}\n"
            f"Version: {version}\n\n"
        )
    with tarfile.open(path, "w:xz") as archive:
        payload = status.encode()
        member = tarfile.TarInfo("./var/lib/dpkg/status")
        member.size = len(payload)
        member.mtime = 0
        archive.addfile(member, io.BytesIO(payload))
        if extra:
            extra_member = tarfile.TarInfo("./etc/build-marker")
            extra_member.size = len(extra)
            extra_member.mtime = 0
            archive.addfile(extra_member, io.BytesIO(extra))
    return path


def test_repository_rootfs_lock_is_exact_and_fail_closed():
    lock = load_rootfs_source_lock(LOCK_PATH)
    assert lock.schema_version == 2
    assert lock.source_commit == "20238a2f2d547d7989a4dec287d4f5ef528ed701"
    assert lock.release_tag == "2026.2"
    assert lock.architecture == "arm64"
    assert lock.suite == "kali-rolling"
    assert lock.mirror == "https://http.kali.org/kali"
    assert lock.archive_key_fingerprint == "827C8569F2518CC677FECA1AED65462EC8D5E4C5"
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


def test_rootfs_lock_rejects_http_mirror(tmp_path):
    raw = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    raw["build_contract"]["mirror"] = "http://http.kali.org/kali"
    raw["build_contract"]["command"][-1] = "http://http.kali.org/kali"
    bad = tmp_path / "rootfs-source-lock.json"
    bad.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RootfsError, match="HTTPS"):
        load_rootfs_source_lock(bad)


def test_rootfs_lock_rejects_missing_repository_evidence_requirement(tmp_path):
    raw = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    raw["build_contract"]["repository_evidence_required"] = False
    bad = tmp_path / "rootfs-source-lock.json"
    bad.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RootfsError, match="repository snapshot evidence"):
        load_rootfs_source_lock(bad)


def test_inrelease_parser_captures_only_locked_arch_indexes():
    lock = load_rootfs_source_lock(LOCK_PATH)
    inrelease = (
        "-----BEGIN PGP SIGNED MESSAGE-----\nHash: SHA256\n\n"
        "Origin: Kali\nSuite: kali-rolling\n"
        "SHA256:\n"
        f" {'1'*64} 100 main/binary-arm64/Packages.xz\n"
        f" {'2'*64} 200 contrib/binary-arm64/Packages.gz\n"
        f" {'3'*64} 300 main/binary-amd64/Packages.xz\n"
        "-----BEGIN PGP SIGNATURE-----\n"
    ).encode()
    evidence = repository_snapshot_from_inrelease(
        lock, inrelease, signing_key_fingerprint=lock.archive_key_fingerprint
    )
    assert [item.path for item in evidence.package_indexes] == [
        "contrib/binary-arm64/Packages.gz",
        "main/binary-arm64/Packages.xz",
    ]
    assert evidence.signing_key_fingerprint == lock.archive_key_fingerprint


def test_inrelease_parser_rejects_wrong_signer():
    lock = load_rootfs_source_lock(LOCK_PATH)
    with pytest.raises(RootfsError, match="locked Kali archive key"):
        repository_snapshot_from_inrelease(
            lock,
            b"SHA256:\n " + b"1" * 64 + b" 1 main/binary-arm64/Packages.xz\n",
            signing_key_fingerprint="A" * 40,
        )


def test_identical_double_build_emits_verifiable_evidence(tmp_path):
    lock = load_rootfs_source_lock(LOCK_PATH)
    repo = snapshot(lock)
    first = rootfs_tar(tmp_path / "kalifs-arm64-a.tar.xz")
    second = rootfs_tar(tmp_path / "kalifs-arm64-b.tar.xz")

    evidence = create_reproducible_rootfs_evidence(
        lock, repo, first_artifact=first, second_artifact=second
    )
    assert evidence.reproducible is True
    assert evidence.architecture == "arm64"
    assert evidence.package_count == 2
    verify_rootfs_artifact(lock, repo, evidence, artifact=first)

    manifest, count = package_manifest_from_rootfs(first)
    assert count == 2
    assert manifest.decode().splitlines() == [
        "base-files\t1.0\tarm64",
        "kali-defaults\t2.0\tall",
    ]
    manifest_path = tmp_path / "evidence" / "packages.tsv"
    assert write_package_manifest(first, manifest_path) == evidence.package_manifest_sha256

    destination = tmp_path / "evidence" / "rootfs-artifact.json"
    assert write_rootfs_artifact_evidence(evidence, destination) == evidence.evidence_sha256()
    assert destination.read_text(encoding="utf-8") == evidence.canonical_json()


def test_nonidentical_double_build_fails_closed(tmp_path):
    lock = load_rootfs_source_lock(LOCK_PATH)
    repo = snapshot(lock)
    first = rootfs_tar(tmp_path / "a.tar.xz", extra=b"build-a")
    second = rootfs_tar(tmp_path / "b.tar.xz", extra=b"build-b")
    with pytest.raises(RootfsError, match="not reproducible"):
        create_reproducible_rootfs_evidence(
            lock, repo, first_artifact=first, second_artifact=second
        )


def test_repository_snapshot_must_match_locked_suite_arch_and_mirror(tmp_path):
    lock = load_rootfs_source_lock(LOCK_PATH)
    repo = repository_snapshot_from_dict(
        {
            "schema_version": 2,
            "mirror": lock.mirror,
            "suite": lock.suite,
            "architecture": "amd64",
            "signing_key_fingerprint": lock.archive_key_fingerprint,
            "inrelease_sha256": "a" * 64,
            "package_indexes": [
                {"path": "main/binary-amd64/Packages.xz", "size": 10, "sha256": "b" * 64}
            ],
        }
    )
    first = rootfs_tar(tmp_path / "a.tar.xz")
    second = rootfs_tar(tmp_path / "b.tar.xz")
    with pytest.raises(RootfsError, match="does not match rootfs source lock"):
        create_reproducible_rootfs_evidence(
            lock, repo, first_artifact=first, second_artifact=second
        )


def test_verified_rootfs_artifact_rejects_post_build_drift(tmp_path):
    lock = load_rootfs_source_lock(LOCK_PATH)
    repo = snapshot(lock)
    first = rootfs_tar(tmp_path / "a.tar.xz")
    second = rootfs_tar(tmp_path / "b.tar.xz")
    evidence = create_reproducible_rootfs_evidence(
        lock, repo, first_artifact=first, second_artifact=second
    )
    rootfs_tar(first, extra=b"tampered")
    with pytest.raises(RootfsError, match="changed after reproducibility verification"):
        verify_rootfs_artifact(lock, repo, evidence, artifact=first)


def test_repository_snapshot_rejects_malformed_hash():
    lock = load_rootfs_source_lock(LOCK_PATH)
    with pytest.raises(RootfsError, match="InRelease"):
        repository_snapshot_from_dict(
            {
                "schema_version": 2,
                "mirror": lock.mirror,
                "suite": lock.suite,
                "architecture": lock.architecture,
                "signing_key_fingerprint": lock.archive_key_fingerprint,
                "inrelease_sha256": "not-a-hash",
                "package_indexes": [
                    {"path": "main/binary-arm64/Packages.xz", "size": 10, "sha256": "c" * 64}
                ],
            }
        )
