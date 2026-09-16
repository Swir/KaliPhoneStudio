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
from kaliphonestudio.device_tree import DeviceTreeCandidateEvidence
from kaliphonestudio.kernel_build_binding import KernelReproducibilityBindingEvidence
from kaliphonestudio.kernel_bundle import KernelCandidateEvidence
from kaliphonestudio.kernel_repro import KernelReproducibilityEvidence
from kaliphonestudio.kernel_toolchain_bundle import KernelToolchainCandidateEvidence
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


def kernel_repro_evidence(kernel=None, **changes):
    kernel = kernel or kernel_evidence()
    values = {
        "schema_version": 1,
        "profile_id": kernel.profile_id,
        "kernel_plan_sha256": kernel.kernel_plan_sha256,
        "source_commit": kernel.source_commit,
        "kernel_version": kernel.kernel_version,
        "config_sha256": kernel.config_sha256,
        "config_size": 2048,
        "image_sha256": kernel.image_sha256,
        "image_size": kernel.image_size,
        "build_a_config_evidence_sha256": "1" * 64,
        "build_b_config_evidence_sha256": "2" * 64,
        "build_a_image_evidence_sha256": "3" * 64,
        "build_b_image_evidence_sha256": "4" * 64,
        "distinct_build_roots_verified": True,
        "byte_identical": True,
        "beta_gate_credit": False,
    }
    values.update(changes)
    return KernelReproducibilityEvidence(**values)


def kernel_toolchain_evidence(kernel=None, **changes):
    kernel = kernel or kernel_evidence()
    values = {
        "schema_version": 1,
        "profile_id": kernel.profile_id,
        "kernel_plan_sha256": kernel.kernel_plan_sha256,
        "kernel_source_commit": kernel.source_commit,
        "toolchain_lock_sha256": "b" * 64,
        "source_evidence_sha256": "c" * 64,
        "binding_evidence_sha256": "d" * 64,
        "materialized_evidence_sha256": "e" * 64,
        "clang_revision": "r416183b",
        "clang_sha256": "f" * 64,
        "clang_size": 123456,
        "build_config_sha256": "1" * 64,
        "clang_prebuilt_bin": "prebuilts-master/clang/host/linux-x86/clang-r416183b/bin",
        "beta_gate_credit": False,
    }
    values.update(changes)
    return KernelToolchainCandidateEvidence(**values)


def kernel_execution_binding_evidence(kernel=None, repro=None, toolchain=None, **changes):
    kernel = kernel or kernel_evidence()
    repro = repro or kernel_repro_evidence(kernel)
    toolchain = toolchain or kernel_toolchain_evidence(kernel)
    values = {
        "schema_version": 1,
        "profile_id": kernel.profile_id,
        "kernel_plan_sha256": kernel.kernel_plan_sha256,
        "source_commit": kernel.source_commit,
        "toolchain_lock_sha256": toolchain.toolchain_lock_sha256,
        "build_recipe_sha256": "2" * 64,
        "reproducible_environment_sha256": "3" * 64,
        "build_a_run_evidence_sha256": "4" * 64,
        "build_b_run_evidence_sha256": "5" * 64,
        "reproducibility_evidence_sha256": repro.evidence_sha256(),
        "config_sha256": repro.config_sha256,
        "config_size": repro.config_size,
        "image_sha256": repro.image_sha256,
        "image_size": repro.image_size,
        "byte_identical": True,
        "distinct_build_roots_verified": True,
        "beta_gate_credit": False,
    }
    values.update(changes)
    return KernelReproducibilityBindingEvidence(**values)


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


def device_tree_evidence(plan, **changes):
    dtb = next(item for item in plan.inputs if item.name == "dtb")
    dtbo = next(item for item in plan.inputs if item.name == "dtbo")
    values = {
        "schema_version": 1,
        "profile_id": plan.profile_id,
        "boot_plan_sha256": plan.plan_sha256(),
        "format_lock_sha256": "e" * 64,
        "dtb_evidence_sha256": "f" * 64,
        "dtb_sha256": dtb.sha256,
        "dtb_size": dtb.size,
        "dtb_tree_count": 2,
        "dtbo_evidence_sha256": "1" * 64,
        "dtbo_sha256": dtbo.sha256,
        "dtbo_size": dtbo.size,
        "dtbo_entry_count": 3,
    }
    values.update(changes)
    return DeviceTreeCandidateEvidence(**values)


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


def create_candidate(
    boot,
    plan,
    kernel,
    lock,
    snapshot,
    evidence,
    rootfs,
    *,
    trees=None,
    repro=None,
    toolchain=None,
    execution=None,
):
    repro = repro or kernel_repro_evidence(kernel)
    toolchain = toolchain or kernel_toolchain_evidence(kernel)
    execution = execution or kernel_execution_binding_evidence(kernel, repro, toolchain)
    return create_first_boot_candidate_manifest(
        boot,
        plan,
        kernel,
        lock,
        snapshot,
        evidence,
        kernel_reproducibility_evidence=repro,
        kernel_reproducibility_binding_evidence=execution,
        kernel_toolchain_evidence=toolchain,
        device_tree_evidence=trees or device_tree_evidence(plan),
        rootfs_artifact=rootfs,
    )


def make_candidate(
    tmp_path,
    *,
    kernel=None,
    plan=None,
    boot=None,
    trees=None,
    repro=None,
    toolchain=None,
    execution=None,
):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    kernel = kernel or kernel_evidence()
    plan = plan or boot_plan(kernel)
    boot = boot or boot_authorization(plan)
    trees = trees or device_tree_evidence(plan)
    repro = repro or kernel_repro_evidence(kernel)
    toolchain = toolchain or kernel_toolchain_evidence(kernel)
    execution = execution or kernel_execution_binding_evidence(kernel, repro, toolchain)
    manifest = create_candidate(
        boot,
        plan,
        kernel,
        lock,
        snapshot,
        evidence,
        rootfs,
        trees=trees,
        repro=repro,
        toolchain=toolchain,
        execution=execution,
    )
    return (
        manifest,
        lock,
        snapshot,
        evidence,
        rootfs,
        kernel,
        plan,
        boot,
        trees,
        repro,
        toolchain,
        execution,
    )


def test_candidate_binds_boot_kernel_execution_toolchain_repro_device_tree_firmware_and_rootfs_evidence(tmp_path):
    (
        manifest,
        _lock,
        _snapshot,
        evidence,
        _rootfs,
        kernel,
        plan,
        boot,
        trees,
        repro,
        toolchain,
        execution,
    ) = make_candidate(tmp_path)
    assert manifest.schema_version == 8
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
    assert manifest.kernel_reproducibility_evidence_sha256 == repro.evidence_sha256()
    assert manifest.kernel_reproducibility_binding_evidence_sha256 == execution.evidence_sha256()
    assert manifest.kernel_build_recipe_sha256 == execution.build_recipe_sha256
    assert manifest.kernel_reproducible_environment_sha256 == execution.reproducible_environment_sha256
    assert manifest.kernel_build_a_run_evidence_sha256 == execution.build_a_run_evidence_sha256
    assert manifest.kernel_build_b_run_evidence_sha256 == execution.build_b_run_evidence_sha256
    assert manifest.kernel_reproducible is True
    assert manifest.kernel_distinct_build_roots_verified is True
    assert manifest.kernel_toolchain_evidence_sha256 == toolchain.evidence_sha256()
    assert manifest.kernel_toolchain_lock_sha256 == toolchain.toolchain_lock_sha256
    assert manifest.kernel_toolchain_materialized_evidence_sha256 == toolchain.materialized_evidence_sha256
    assert manifest.kernel_clang_revision == "r416183b"
    assert manifest.kernel_clang_sha256 == toolchain.clang_sha256
    assert manifest.kernel_build_config_sha256 == toolchain.build_config_sha256
    assert manifest.device_tree_evidence_sha256 == trees.evidence_sha256()
    assert manifest.dtb_sha256 == "c" * 64
    assert manifest.dtbo_sha256 == "d" * 64
    assert manifest.dtb_tree_count == 2
    assert manifest.dtbo_entry_count == 3
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
        create_candidate(boot, plan, kernel, lock, snapshot, evidence, rootfs)


def test_candidate_rejects_missing_device_binding(tmp_path):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    kernel = kernel_evidence()
    plan = boot_plan(kernel)
    boot = boot_authorization(plan, device_serial="")
    with pytest.raises(RootfsError, match="verified device binding"):
        create_candidate(boot, plan, kernel, lock, snapshot, evidence, rootfs)


def test_candidate_rejects_malformed_boot_or_baseline_hash(tmp_path):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    kernel = kernel_evidence()
    plan = boot_plan(kernel)
    boot = boot_authorization(plan, image_sha256="not-a-hash")
    with pytest.raises(RootfsError, match="image SHA-256"):
        create_candidate(boot, plan, kernel, lock, snapshot, evidence, rootfs)

    boot = boot_authorization(plan, fastboot_baseline_sha256="not-a-hash")
    with pytest.raises(RootfsError, match="fastboot baseline SHA-256"):
        create_candidate(boot, plan, kernel, lock, snapshot, evidence, rootfs)


def test_candidate_rejects_missing_firmware_identity(tmp_path):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    kernel = kernel_evidence()
    plan = boot_plan(kernel)
    with pytest.raises(RootfsError, match="firmware build"):
        create_candidate(
            boot_authorization(plan, firmware_build=""),
            plan,
            kernel,
            lock,
            snapshot,
            evidence,
            rootfs,
        )


def test_candidate_rejects_kernel_not_bound_to_boot_plan(tmp_path):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    kernel = kernel_evidence(image_sha256="e" * 64)
    plan = boot_plan(kernel_evidence())
    boot = boot_authorization(plan)
    with pytest.raises(RootfsError, match="does not match the kernel embedded"):
        create_candidate(boot, plan, kernel, lock, snapshot, evidence, rootfs)


def test_candidate_rejects_boot_plan_not_bound_to_authorization(tmp_path):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    kernel = kernel_evidence()
    plan = boot_plan(kernel)
    boot = boot_authorization(plan, plan_sha256="f" * 64)
    with pytest.raises(RootfsError, match="plan digest"):
        create_candidate(boot, plan, kernel, lock, snapshot, evidence, rootfs)


def test_candidate_rejects_kernel_reproducibility_image_drift(tmp_path):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    kernel = kernel_evidence()
    plan = boot_plan(kernel)
    repro = kernel_repro_evidence(kernel, image_sha256="e" * 64)
    with pytest.raises(RootfsError, match="reproducible kernel Image does not match"):
        create_candidate(
            boot_authorization(plan), plan, kernel, lock, snapshot, evidence, rootfs, repro=repro
        )


def test_candidate_rejects_kernel_reproducibility_without_distinct_roots(tmp_path):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    kernel = kernel_evidence()
    plan = boot_plan(kernel)
    repro = kernel_repro_evidence(kernel, distinct_build_roots_verified=False)
    with pytest.raises(RootfsError, match="distinct build-root"):
        create_candidate(
            boot_authorization(plan), plan, kernel, lock, snapshot, evidence, rootfs, repro=repro
        )


def test_candidate_rejects_kernel_reproducibility_hardware_credit(tmp_path):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    kernel = kernel_evidence()
    plan = boot_plan(kernel)
    repro = kernel_repro_evidence(kernel, beta_gate_credit=True)
    with pytest.raises(RootfsError, match="cannot claim hardware Beta credit"):
        create_candidate(
            boot_authorization(plan), plan, kernel, lock, snapshot, evidence, rootfs, repro=repro
        )


def test_candidate_rejects_execution_binding_reproducibility_digest_drift(tmp_path):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    kernel = kernel_evidence()
    plan = boot_plan(kernel)
    repro = kernel_repro_evidence(kernel)
    toolchain = kernel_toolchain_evidence(kernel)
    execution = kernel_execution_binding_evidence(
        kernel,
        repro,
        toolchain,
        reproducibility_evidence_sha256="0" * 64,
    )
    with pytest.raises(RootfsError, match="does not match reproducibility evidence"):
        create_candidate(
            boot_authorization(plan),
            plan,
            kernel,
            lock,
            snapshot,
            evidence,
            rootfs,
            repro=repro,
            toolchain=toolchain,
            execution=execution,
        )


def test_candidate_rejects_execution_binding_toolchain_drift(tmp_path):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    kernel = kernel_evidence()
    plan = boot_plan(kernel)
    repro = kernel_repro_evidence(kernel)
    toolchain = kernel_toolchain_evidence(kernel)
    execution = kernel_execution_binding_evidence(
        kernel,
        repro,
        toolchain,
        toolchain_lock_sha256="0" * 64,
    )
    with pytest.raises(RootfsError, match="execution binding toolchain lock drifted"):
        create_candidate(
            boot_authorization(plan),
            plan,
            kernel,
            lock,
            snapshot,
            evidence,
            rootfs,
            repro=repro,
            toolchain=toolchain,
            execution=execution,
        )


def test_candidate_rejects_execution_binding_without_independent_byte_equality(tmp_path):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    kernel = kernel_evidence()
    plan = boot_plan(kernel)
    repro = kernel_repro_evidence(kernel)
    toolchain = kernel_toolchain_evidence(kernel)
    execution = kernel_execution_binding_evidence(
        kernel,
        repro,
        toolchain,
        byte_identical=False,
    )
    with pytest.raises(RootfsError, match="does not prove independent byte-identical builds"):
        create_candidate(
            boot_authorization(plan),
            plan,
            kernel,
            lock,
            snapshot,
            evidence,
            rootfs,
            repro=repro,
            toolchain=toolchain,
            execution=execution,
        )


def test_candidate_rejects_execution_binding_hardware_credit(tmp_path):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    kernel = kernel_evidence()
    plan = boot_plan(kernel)
    repro = kernel_repro_evidence(kernel)
    toolchain = kernel_toolchain_evidence(kernel)
    execution = kernel_execution_binding_evidence(
        kernel,
        repro,
        toolchain,
        beta_gate_credit=True,
    )
    with pytest.raises(RootfsError, match="execution binding cannot claim hardware Beta credit"):
        create_candidate(
            boot_authorization(plan),
            plan,
            kernel,
            lock,
            snapshot,
            evidence,
            rootfs,
            repro=repro,
            toolchain=toolchain,
            execution=execution,
        )


def test_candidate_rejects_toolchain_plan_drift(tmp_path):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    kernel = kernel_evidence()
    plan = boot_plan(kernel)
    toolchain = kernel_toolchain_evidence(kernel, kernel_plan_sha256="0" * 64)
    with pytest.raises(RootfsError, match="toolchain evidence does not match kernel plan"):
        create_candidate(
            boot_authorization(plan),
            plan,
            kernel,
            lock,
            snapshot,
            evidence,
            rootfs,
            toolchain=toolchain,
        )


def test_candidate_rejects_toolchain_source_commit_drift(tmp_path):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    kernel = kernel_evidence()
    plan = boot_plan(kernel)
    toolchain = kernel_toolchain_evidence(kernel, kernel_source_commit="0" * 40)
    with pytest.raises(RootfsError, match="toolchain evidence source commit drifted"):
        create_candidate(
            boot_authorization(plan),
            plan,
            kernel,
            lock,
            snapshot,
            evidence,
            rootfs,
            toolchain=toolchain,
        )


def test_candidate_rejects_toolchain_hardware_credit(tmp_path):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    kernel = kernel_evidence()
    plan = boot_plan(kernel)
    toolchain = kernel_toolchain_evidence(kernel, beta_gate_credit=True)
    with pytest.raises(RootfsError, match="toolchain evidence cannot claim hardware Beta credit"):
        create_candidate(
            boot_authorization(plan),
            plan,
            kernel,
            lock,
            snapshot,
            evidence,
            rootfs,
            toolchain=toolchain,
        )


def test_candidate_rejects_invalid_materialized_clang_size(tmp_path):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    kernel = kernel_evidence()
    plan = boot_plan(kernel)
    toolchain = kernel_toolchain_evidence(kernel, clang_size=0)
    with pytest.raises(RootfsError, match="invalid clang size"):
        create_candidate(
            boot_authorization(plan),
            plan,
            kernel,
            lock,
            snapshot,
            evidence,
            rootfs,
            toolchain=toolchain,
        )


def test_candidate_rejects_device_tree_plan_digest_drift(tmp_path):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    kernel = kernel_evidence()
    plan = boot_plan(kernel)
    trees = device_tree_evidence(plan, boot_plan_sha256="0" * 64)
    with pytest.raises(RootfsError, match="device-tree evidence does not match boot build plan digest"):
        create_candidate(
            boot_authorization(plan), plan, kernel, lock, snapshot, evidence, rootfs, trees=trees
        )


def test_candidate_rejects_dtbo_not_bound_to_boot_plan(tmp_path):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    kernel = kernel_evidence()
    plan = boot_plan(kernel)
    trees = device_tree_evidence(plan, dtbo_sha256="0" * 64)
    with pytest.raises(RootfsError, match="DTBO evidence does not match"):
        create_candidate(
            boot_authorization(plan), plan, kernel, lock, snapshot, evidence, rootfs, trees=trees
        )


def test_candidate_rejects_rootfs_drift_after_reproducibility_proof(tmp_path):
    lock, snapshot, evidence, rootfs = fixture_rootfs(tmp_path)
    kernel = kernel_evidence()
    plan = boot_plan(kernel)
    rootfs.write_bytes(b"tampered")
    with pytest.raises(RootfsError, match="changed after reproducibility verification"):
        create_candidate(
            boot_authorization(plan), plan, kernel, lock, snapshot, evidence, rootfs
        )
