import os
from pathlib import Path

import pytest

from kaliphonestudio.boot_builder import BootBuildPlan, BuildInput
from kaliphonestudio.boot_image import BootImageError
from kaliphonestudio.initramfs import InitramfsError, build_reproducible_initramfs
from kaliphonestudio.initramfs_binding import (
    bind_initramfs_to_boot_plan,
    write_initramfs_boot_binding,
)


def _stage(root: Path) -> Path:
    root.mkdir()
    init = root / "init"
    init.write_text("#!/bin/sh\necho early-rescue\n", encoding="utf-8")
    init.chmod(0o755)
    etc = root / "etc"
    etc.mkdir()
    (etc / "mode").write_text("rescue\n", encoding="utf-8")
    os.utime(init, (123, 456))
    return root


def _plan(artifact: Path, digest: str, *, compression: str = "gzip") -> BootBuildPlan:
    kernel = BuildInput("kernel", "Image", 4, "1" * 64)
    ramdisk = BuildInput("ramdisk", artifact.name, artifact.stat().st_size, digest)
    return BootBuildPlan(
        schema_version=1,
        profile_id="test/device",
        stock_boot_sha256="2" * 64,
        stock_ota_sha256="3" * 64,
        header_version=2,
        page_size=4096,
        ramdisk_compression=compression,
        kernel_cmdline=(),
        inputs=(kernel, ramdisk),
    )


def test_verified_initramfs_binds_exactly_to_planned_ramdisk(tmp_path):
    artifact = tmp_path / "rescue.cpio.gz"
    evidence = build_reproducible_initramfs(_stage(tmp_path / "stage"), artifact)
    plan = _plan(artifact, evidence.artifact_sha256)

    binding = bind_initramfs_to_boot_plan(plan, evidence, artifact=artifact)
    assert binding.verified is True
    assert binding.profile_id == "test/device"
    assert binding.boot_plan_sha256 == plan.plan_sha256()
    assert binding.initramfs_evidence_sha256 == evidence.evidence_sha256()
    assert binding.ramdisk_sha256 == evidence.artifact_sha256
    assert binding.ramdisk_size == artifact.stat().st_size
    assert binding.init_sha256 == evidence.init_sha256
    assert binding.ramdisk_compression == "gzip"

    output = tmp_path / "binding.json"
    assert write_initramfs_boot_binding(binding, output) == binding.evidence_sha256()
    assert output.read_text(encoding="utf-8") == binding.canonical_json()


def test_verified_lz4_initramfs_binds_to_lz4_boot_plan(tmp_path):
    artifact = tmp_path / "rescue.cpio.lz4"
    evidence = build_reproducible_initramfs(
        _stage(tmp_path / "stage"), artifact, compression="lz4"
    )
    plan = _plan(artifact, evidence.artifact_sha256, compression="lz4")

    binding = bind_initramfs_to_boot_plan(plan, evidence, artifact=artifact)
    assert binding.verified is True
    assert binding.ramdisk_compression == "lz4"
    assert binding.ramdisk_sha256 == evidence.artifact_sha256
    assert binding.initramfs_evidence_sha256 == evidence.evidence_sha256()


def test_binding_rejects_ramdisk_bytes_not_approved_by_plan(tmp_path):
    artifact = tmp_path / "rescue.cpio.gz"
    evidence = build_reproducible_initramfs(_stage(tmp_path / "stage"), artifact)
    plan = _plan(artifact, "4" * 64)

    with pytest.raises(BootImageError, match="does not match the boot plan"):
        bind_initramfs_to_boot_plan(plan, evidence, artifact=artifact)


def test_binding_rejects_profile_compression_mismatch(tmp_path):
    artifact = tmp_path / "rescue.cpio.gz"
    evidence = build_reproducible_initramfs(_stage(tmp_path / "stage"), artifact)
    plan = _plan(artifact, evidence.artifact_sha256, compression="lz4")

    with pytest.raises(BootImageError, match="compression does not match"):
        bind_initramfs_to_boot_plan(plan, evidence, artifact=artifact)


def test_binding_rejects_tampering_after_initramfs_verification(tmp_path):
    artifact = tmp_path / "rescue.cpio.gz"
    evidence = build_reproducible_initramfs(_stage(tmp_path / "stage"), artifact)
    plan = _plan(artifact, evidence.artifact_sha256)
    artifact.write_bytes(artifact.read_bytes() + b"tampered")

    with pytest.raises(InitramfsError, match="changed after reproducibility verification"):
        bind_initramfs_to_boot_plan(plan, evidence, artifact=artifact)
