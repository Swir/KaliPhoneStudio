import io
from pathlib import Path
import tarfile

import pytest

from kaliphonestudio.boot_authorization import TemporaryBootAuthorization
from kaliphonestudio.boot_builder import BootBuildPlan, BuildInput
from kaliphonestudio.candidate import (
    create_first_boot_candidate_manifest,
    write_first_boot_candidate_manifest,
)
from kaliphonestudio.kernel_bundle import KernelCandidateEvidence
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


def kernel_evidence(**changes):
    values = {
        "schema_version": 1,
        "profile_id": "oneplus/avicii",
        "kernel_plan_sha256": "5" * 64,
        "source_commit": "f" * 40,
        "kernel_version": "4.19.300",
        "checkout_evidence_sha256": "6" * 64,
        "config_evidence_sha256": "7" * 64,
        "image_evidence_sha256": "8" * 64,
        "config_sha256": "9" * 64,
        "image_sha256": "a" * 64,
        "image_size": 4096,
        "arm64_magic_verified": True,
    }
    values.update(changes)
    return KernelCandidateEvidence(**values)


def boot_plan(kernel=None):
    kernel = kernel or kernel_evidence()
    return BootBuildPlan(
        schema_version=1,
        profile_id="oneplus/avicii",
        stock_boot_sha256="2" * 64,
        stock_ota_sha256="3" * 64,
        header_version=2,
        page_size=4096,
        ramdisk_compression="lz4",
        kernel_cmdline=(),
        inputs=(
            BuildInput("kernel", "Image", kernel.image_size, kernel.image_sha256),
            BuildInput("ramdisk", "rescue.cpio.lz4", 2048, "b" * 64),
            BuildInput("dtb", "dtb", 1024, "c" * 64),
            BuildInput("dtbo", "dtbo", 1024, "d" * 64),
        ),
    )


def boot_authorization(plan=None, **changes):
    plan = plan or boot_plan()
    values = {
        "schema_version": 2,
        "profile_id": "oneplus/avicii",
        "device_serial": "SERIAL123",
        "fastboot_baseline_sha256": "0" * 64,
        "firmware_build": "AC2003_11_F.22",
        "firmware_fingerprint": "OnePlus/avicii/avicii:13/test/F.22:user/release-keys",
        "plan_sha256": plan.plan_sha256(),
        "stock_boot_sha256": "2" * 64,
        "stock_ota_sha256": "3" * 64,
        "image_sha256": "4" * 64,
        "image_size": 8192,
        "reproducible": True,
        "structurally_verified": True,
    }
    values.update(changes)
    return TemporaryBootAuthorization(**values)


def test_candidate_binds_boot_kernel_firmware_and_rootfs_evidence(tmp_path):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    kernel = kernel_evidence()
    plan = boot_plan(kernel)
    boot = boot_authorization(plan)
    manifest = create_first_boot_candidate_manifest(
        boot, plan, kernel, lock, snapshot, evidence, rootfs_artifact=rootfs
    )
    assert manifest.schema_version == 4
    assert manifest.profile_id == "oneplus/avicii"
    assert manifest.device_serial == "SERIAL123"
    assert manifest.fastboot_baseline_sha256 == "0" * 64
    assert manifest.firmware_build == "AC2003_11_F.22"
    assert manifest.firmware_fingerprint == boot.firmware_fingerprint
    assert manifest.boot_authorization_sha256 == boot.authorization_sha256()
    assert manifest.boot_plan_sha256 == plan.plan_sha256()
    assert manifest.kernel_evidence_sha256 == kernel.evidence_sha256()
    assert manifest.kernel_source_commit == kernel.source_commit
    assert manifest.kernel_config_sha256 == kernel.config_sha256
    assert manifest.kernel_image_sha256 == kernel.image_sha256
    assert manifest.rootfs_evidence_sha256 == evidence.evidence_sha256()
    assert manifest.rootfs_package_manifest_sha256 == evidence.package_manifest_sha256
    assert manifest.rootfs_package_count == 1

    destination = tmp_path / "candidate" / "first-boot.json"
    assert write_first_boot_candidate_manifest(manifest, destination) == manifest.manifest_sha256()
    assert destination.read_text(encoding="utf-8") == manifest.canonical_json()


def test_candidate_rejects_unverified_boot_authorization(tmp_path):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    kernel = kernel_evidence()
    plan = boot_plan(kernel)
    boot = boot_authorization(plan, structurally_verified=False)
    with pytest.raises(RootfsError, match="fully verified boot authorization"):
        create_first_boot_candidate_manifest(
            boot, plan, kernel, lock, snapshot, evidence, rootfs_artifact=rootfs
        )


def test_candidate_rejects_missing_device_binding(tmp_path):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    kernel = kernel_evidence()
    plan = boot_plan(kernel)
    boot = boot_authorization(plan, device_serial="")
    with pytest.raises(RootfsError, match="verified device binding"):
        create_first_boot_candidate_manifest(
            boot, plan, kernel, lock, snapshot, evidence, rootfs_artifact=rootfs
        )


def test_candidate_rejects_malformed_boot_or_baseline_hash(tmp_path):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    kernel = kernel_evidence()
    plan = boot_plan(kernel)
    boot = boot_authorization(plan, image_sha256="not-a-hash")
    with pytest.raises(RootfsError, match="image SHA-256"):
        create_first_boot_candidate_manifest(
            boot, plan, kernel, lock, snapshot, evidence, rootfs_artifact=rootfs
        )

    boot = boot_authorization(plan, fastboot_baseline_sha256="not-a-hash")
    with pytest.raises(RootfsError, match="fastboot baseline SHA-256"):
        create_first_boot_candidate_manifest(
            boot, plan, kernel, lock, snapshot, evidence, rootfs_artifact=rootfs
        )


def test_candidate_rejects_missing_firmware_identity(tmp_path):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    kernel = kernel_evidence()
    plan = boot_plan(kernel)
    with pytest.raises(RootfsError, match="firmware build"):
        create_first_boot_candidate_manifest(
            boot_authorization(plan, firmware_build=""),
            plan,
            kernel,
            lock,
            snapshot,
            evidence,
            rootfs_artifact=rootfs,
        )


def test_candidate_rejects_kernel_not_bound_to_boot_plan(tmp_path):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    kernel = kernel_evidence(image_sha256="e" * 64)
    plan = boot_plan(kernel_evidence())
    boot = boot_authorization(plan)
    with pytest.raises(RootfsError, match="does not match the kernel embedded"):
        create_first_boot_candidate_manifest(
            boot, plan, kernel, lock, snapshot, evidence, rootfs_artifact=rootfs
        )


def test_candidate_rejects_boot_plan_not_bound_to_authorization(tmp_path):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    kernel = kernel_evidence()
    plan = boot_plan(kernel)
    boot = boot_authorization(plan, plan_sha256="f" * 64)
    with pytest.raises(RootfsError, match="plan digest"):
        create_first_boot_candidate_manifest(
            boot, plan, kernel, lock, snapshot, evidence, rootfs_artifact=rootfs
        )


def test_candidate_rejects_rootfs_drift_after_reproducibility_proof(tmp_path):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    kernel = kernel_evidence()
    plan = boot_plan(kernel)
    rootfs.write_bytes(b"tampered")
    with pytest.raises(RootfsError, match="changed after reproducibility verification"):
        create_first_boot_candidate_manifest(
            boot_authorization(plan),
            plan,
            kernel,
            lock,
            snapshot,
            evidence,
            rootfs_artifact=rootfs,
        )
