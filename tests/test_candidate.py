import io
from pathlib import Path
import tarfile

import pytest

from kaliphonestudio.boot_authorization import TemporaryBootAuthorization
from kaliphonestudio.candidate import (
    create_first_boot_candidate_manifest,
    write_first_boot_candidate_manifest,
)
from kaliphonestudio.rootfs import (
    RootfsError,
    create_reproducible_rootfs_evidence,
    load_rootfs_source_lock,
    repository_snapshot_from_dict,
)

ROOT = Path(__file__).parents[1]


def rootfs_tar(path: Path) -> Path:
    status = (
        "Package: base-files\n"
        "Status: install ok installed\n"
        "Architecture: arm64\n"
        "Version: 1.0\n\n"
    ).encode()
    with tarfile.open(path, "w:xz") as archive:
        member = tarfile.TarInfo("./var/lib/dpkg/status")
        member.size = len(status)
        member.mtime = 0
        archive.addfile(member, io.BytesIO(status))
    return path


def fixture_rootfs(tmp_path):
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
    first = rootfs_tar(tmp_path / "rootfs-a.tar.xz")
    second = rootfs_tar(tmp_path / "rootfs-b.tar.xz")
    evidence = create_reproducible_rootfs_evidence(
        lock, snapshot, first_artifact=first, second_artifact=second
    )
    return lock, snapshot, evidence, first


def boot_authorization(**changes):
    values = {
        "schema_version": 1,
        "profile_id": "oneplus/avicii",
        "device_serial": "SERIAL123",
        "plan_sha256": "1" * 64,
        "stock_boot_sha256": "2" * 64,
        "stock_ota_sha256": "3" * 64,
        "image_sha256": "4" * 64,
        "image_size": 8192,
        "reproducible": True,
        "structurally_verified": True,
    }
    values.update(changes)
    return TemporaryBootAuthorization(**values)


def test_candidate_binds_boot_authorization_and_rootfs_evidence(tmp_path):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    boot = boot_authorization()
    manifest = create_first_boot_candidate_manifest(
        boot, lock, snapshot, evidence, rootfs_artifact=rootfs
    )
    assert manifest.schema_version == 2
    assert manifest.profile_id == "oneplus/avicii"
    assert manifest.device_serial == "SERIAL123"
    assert manifest.boot_authorization_sha256 == boot.authorization_sha256()
    assert manifest.rootfs_evidence_sha256 == evidence.evidence_sha256()
    assert manifest.rootfs_package_manifest_sha256 == evidence.package_manifest_sha256
    assert manifest.rootfs_package_count == 1

    destination = tmp_path / "candidate" / "first-boot.json"
    assert write_first_boot_candidate_manifest(manifest, destination) == manifest.manifest_sha256()
    assert destination.read_text(encoding="utf-8") == manifest.canonical_json()


def test_candidate_rejects_unverified_boot_authorization(tmp_path):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    boot = boot_authorization(structurally_verified=False)
    with pytest.raises(RootfsError, match="fully verified boot authorization"):
        create_first_boot_candidate_manifest(
            boot, lock, snapshot, evidence, rootfs_artifact=rootfs
        )


def test_candidate_rejects_missing_device_binding(tmp_path):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    boot = boot_authorization(device_serial="")
    with pytest.raises(RootfsError, match="verified device binding"):
        create_first_boot_candidate_manifest(
            boot, lock, snapshot, evidence, rootfs_artifact=rootfs
        )


def test_candidate_rejects_malformed_boot_hash(tmp_path):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    boot = boot_authorization(image_sha256="not-a-hash")
    with pytest.raises(RootfsError, match="image SHA-256"):
        create_first_boot_candidate_manifest(
            boot, lock, snapshot, evidence, rootfs_artifact=rootfs
        )


def test_candidate_rejects_rootfs_drift_after_reproducibility_proof(tmp_path):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    rootfs.write_bytes(b"tampered")
    with pytest.raises(RootfsError, match="changed after reproducibility verification"):
        create_first_boot_candidate_manifest(
            boot_authorization(), lock, snapshot, evidence, rootfs_artifact=rootfs
        )
