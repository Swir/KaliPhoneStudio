from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from kaliphonestudio.boot_authorization import TemporaryBootAuthorization
from kaliphonestudio.boot_builder import BootBuildPlan, BuildInput
from kaliphonestudio.candidate import FirstBootCandidateManifest
from kaliphonestudio.candidate_authority_bundle import FirstBootAuthorityBundleEvidence
from kaliphonestudio.physical_baseline_bundle import PhysicalBaselineBundleEvidence
from kaliphonestudio.physical_candidate_gate import (
    PhysicalCandidateGateError,
    bind_physical_candidate_gate,
    verify_physical_candidate_gate,
    write_physical_candidate_gate,
)
from kaliphonestudio.profiles import DeviceProfile


def _h(label: str) -> str:
    return sha256(label.encode("utf-8")).hexdigest()


def _profile() -> DeviceProfile:
    return DeviceProfile(
        path=Path("devices/oneplus/avicii/profile.json"),
        data={
            "profile_id": "oneplus/avicii",
            "boot": {
                "header_version": 2,
                "page_size": 4096,
                "kernel_image": "Image",
                "include_dtb": True,
                "separate_dtbo": True,
                "ramdisk_compression": "lz4",
            },
            "partition_limits": {"boot": 100663296},
            "kernel_cmdline": ["console=ttyMSM0", "rootwait"],
        },
    )


def _objects():
    profile = _profile()
    physical = PhysicalBaselineBundleEvidence(
        schema_version=1,
        profile_id=profile.profile_id,
        device_serial="ABC123",
        product="lito",
        firmware_build="AC2003_11.F.22",
        firmware_fingerprint="OnePlus/avicii/avicii:12/RKQ1/test:user/release-keys",
        fastboot_capture_bundle_sha256=_h("capture"),
        fastboot_baseline_evidence_sha256=_h("baseline"),
        fastboot_transcript_sha256=_h("transcript"),
        stock_provenance_sha256=_h("stock-provenance"),
        stock_ota_sha256=_h("ota"),
        stock_ota_size=10_000,
        stock_payload_sha256=_h("payload"),
        stock_payload_metadata_sha256=_h("payload-metadata"),
        stock_payload_size=9_000,
        stock_boot_sha256=_h("stock-boot"),
        stock_boot_size=4_000,
        stock_boot_header_version=2,
        firmware_metadata_sha256=_h("firmware-metadata"),
        baseline_matches_exact_stock_ota=True,
        ready_for_candidate_instantiation=True,
        temporary_boot_authorized=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    kernel_sha = _h("kernel")
    dtb_sha = _h("dtb")
    dtbo_sha = _h("dtbo")
    plan = BootBuildPlan(
        schema_version=1,
        profile_id=profile.profile_id,
        stock_boot_sha256=physical.stock_boot_sha256,
        stock_ota_sha256=physical.stock_ota_sha256,
        header_version=2,
        page_size=4096,
        ramdisk_compression="lz4",
        kernel_cmdline=("console=ttyMSM0", "rootwait"),
        inputs=(
            BuildInput("kernel", "Image", 43_878_416, kernel_sha),
            BuildInput("ramdisk", "ramdisk.lz4", 1_000_000, _h("ramdisk")),
            BuildInput("dtb", "lito.dtb", 406_620, dtb_sha),
            BuildInput("dtbo", "dtbo.img", 352_256, dtbo_sha),
        ),
    )
    boot = TemporaryBootAuthorization(
        schema_version=2,
        profile_id=profile.profile_id,
        device_serial=physical.device_serial,
        fastboot_baseline_sha256=physical.fastboot_baseline_evidence_sha256,
        firmware_build=physical.firmware_build,
        firmware_fingerprint=physical.firmware_fingerprint,
        plan_sha256=plan.plan_sha256(),
        stock_boot_sha256=physical.stock_boot_sha256,
        stock_ota_sha256=physical.stock_ota_sha256,
        image_sha256=_h("candidate-boot"),
        image_size=60_000_000,
        reproducible=True,
        structurally_verified=True,
    )
    rootfs_sha = _h("rootfs")
    manifest = FirstBootCandidateManifest(
        schema_version=8,
        profile_id=profile.profile_id,
        device_serial=physical.device_serial,
        fastboot_baseline_sha256=physical.fastboot_baseline_evidence_sha256,
        firmware_build=physical.firmware_build,
        firmware_fingerprint=physical.firmware_fingerprint,
        boot_authorization_sha256=boot.authorization_sha256(),
        boot_plan_sha256=plan.plan_sha256(),
        boot_image_sha256=boot.image_sha256,
        boot_image_size=boot.image_size,
        kernel_evidence_sha256=_h("kernel-evidence"),
        kernel_plan_sha256=_h("kernel-plan"),
        kernel_source_commit="a" * 40,
        kernel_version="4.19.300",
        kernel_config_sha256=_h("kernel-config"),
        kernel_image_sha256=kernel_sha,
        kernel_image_size=43_878_416,
        kernel_reproducibility_evidence_sha256=_h("kernel-repro"),
        kernel_reproducibility_binding_evidence_sha256=_h("kernel-repro-binding"),
        kernel_build_recipe_sha256=_h("kernel-recipe"),
        kernel_reproducible_environment_sha256=_h("kernel-env"),
        kernel_build_a_run_evidence_sha256=_h("kernel-a"),
        kernel_build_b_run_evidence_sha256=_h("kernel-b"),
        kernel_reproducible=True,
        kernel_distinct_build_roots_verified=True,
        kernel_toolchain_evidence_sha256=_h("toolchain-evidence"),
        kernel_toolchain_lock_sha256=_h("toolchain-lock"),
        kernel_toolchain_source_evidence_sha256=_h("toolchain-source"),
        kernel_toolchain_binding_evidence_sha256=_h("toolchain-binding"),
        kernel_toolchain_materialized_evidence_sha256=_h("toolchain-materialized"),
        kernel_clang_revision="clang-r416183b",
        kernel_clang_sha256=_h("clang"),
        kernel_clang_size=123_456,
        kernel_build_config_sha256=_h("build-config"),
        device_tree_evidence_sha256=_h("dt-evidence"),
        device_tree_format_lock_sha256=_h("dt-format-lock"),
        dtb_sha256=dtb_sha,
        dtb_size=406_620,
        dtb_tree_count=1,
        dtbo_sha256=dtbo_sha,
        dtbo_size=352_256,
        dtbo_entry_count=1,
        rootfs_evidence_sha256=_h("rootfs-evidence"),
        rootfs_artifact_sha256=rootfs_sha,
        rootfs_artifact_size=137_460_600,
        rootfs_package_manifest_sha256=_h("packages"),
        rootfs_package_count=269,
        rootfs_source_lock_sha256=_h("rootfs-lock"),
        repository_snapshot_sha256=_h("repo-snapshot"),
    )
    authorities = FirstBootAuthorityBundleEvidence(
        schema_version=1,
        profile_id=profile.profile_id,
        first_boot_manifest_sha256=manifest.manifest_sha256(),
        kernel_binding_sha256=_h("kernel-binding"),
        rootfs_binding_sha256=_h("rootfs-binding"),
        device_tree_binding_sha256=_h("dt-binding"),
        kernel_authority_sha256=_h("kernel-authority"),
        rootfs_authority_sha256=_h("rootfs-authority"),
        device_tree_authority_sha256=_h("dt-authority"),
        kernel_authority_run_id=1,
        kernel_authority_commit="b" * 40,
        kernel_authority_artifact_id=11,
        rootfs_authority_run_id=2,
        rootfs_authority_commit="c" * 40,
        rootfs_authority_artifact_id=22,
        device_tree_authority_run_id=3,
        device_tree_authority_commit="d" * 40,
        device_tree_authority_artifact_id=33,
        kernel_image_sha256=kernel_sha,
        rootfs_artifact_sha256=rootfs_sha,
        dtb_sha256=dtb_sha,
        dtbo_image_sha256=dtbo_sha,
        all_authorities_reviewed=True,
        all_required_artifacts_strict=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    return profile, physical, manifest, authorities, boot, plan


def test_valid_gate_only_allows_temporary_boot_offer() -> None:
    items = _objects()
    evidence = bind_physical_candidate_gate(*items)
    assert evidence.ready_for_temporary_boot_offer is True
    assert evidence.reviewed_authorities_bound is True
    assert evidence.exact_physical_baseline_bound is True
    assert evidence.temporary_boot_executed is False
    assert evidence.phone_storage_written is False
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False
    verify_physical_candidate_gate(evidence, *items)


def test_rejects_serial_drift() -> None:
    profile, physical, manifest, authorities, boot, plan = _objects()
    with pytest.raises(PhysicalCandidateGateError, match="serial"):
        bind_physical_candidate_gate(
            profile, physical, replace(manifest, device_serial="OTHER"), authorities, boot, plan
        )


def test_rejects_detached_authority_manifest() -> None:
    profile, physical, manifest, authorities, boot, plan = _objects()
    authorities = replace(authorities, first_boot_manifest_sha256=_h("other-manifest"))
    with pytest.raises(PhysicalCandidateGateError, match="authority bundle"):
        bind_physical_candidate_gate(profile, physical, manifest, authorities, boot, plan)


def test_rejects_stock_provenance_drift() -> None:
    profile, physical, manifest, authorities, boot, plan = _objects()
    boot = replace(boot, stock_boot_sha256=_h("other-stock"))
    with pytest.raises(PhysicalCandidateGateError, match="stock provenance"):
        bind_physical_candidate_gate(profile, physical, manifest, authorities, boot, plan)


def test_rejects_boot_image_drift() -> None:
    profile, physical, manifest, authorities, boot, plan = _objects()
    manifest = replace(manifest, boot_image_sha256=_h("other-boot"))
    authorities = replace(authorities, first_boot_manifest_sha256=manifest.manifest_sha256())
    with pytest.raises(PhysicalCandidateGateError, match="boot image"):
        bind_physical_candidate_gate(profile, physical, manifest, authorities, boot, plan)


def test_rejects_kernel_input_drift() -> None:
    profile, physical, manifest, authorities, boot, plan = _objects()
    inputs = list(plan.inputs)
    inputs[0] = replace(inputs[0], sha256=_h("other-kernel"))
    changed = replace(plan, inputs=tuple(inputs))
    boot = replace(boot, plan_sha256=changed.plan_sha256())
    manifest = replace(
        manifest,
        boot_plan_sha256=changed.plan_sha256(),
        boot_authorization_sha256=boot.authorization_sha256(),
    )
    authorities = replace(authorities, first_boot_manifest_sha256=manifest.manifest_sha256())
    with pytest.raises(PhysicalCandidateGateError, match="kernel input"):
        bind_physical_candidate_gate(profile, physical, manifest, authorities, boot, changed)


def test_rejects_profile_layout_drift() -> None:
    profile, physical, manifest, authorities, boot, plan = _objects()
    changed = replace(plan, header_version=1)
    boot = replace(boot, plan_sha256=changed.plan_sha256())
    manifest = replace(
        manifest,
        boot_plan_sha256=changed.plan_sha256(),
        boot_authorization_sha256=boot.authorization_sha256(),
    )
    authorities = replace(authorities, first_boot_manifest_sha256=manifest.manifest_sha256())
    with pytest.raises(PhysicalCandidateGateError, match="boot contract"):
        bind_physical_candidate_gate(profile, physical, manifest, authorities, boot, changed)


def test_rejects_host_evidence_that_claims_execution_or_hardware(tmp_path: Path) -> None:
    evidence = bind_physical_candidate_gate(*_objects())
    with pytest.raises(PhysicalCandidateGateError, match="execution/writes"):
        write_physical_candidate_gate(replace(evidence, temporary_boot_executed=True), tmp_path / "gate.json")
    with pytest.raises(PhysicalCandidateGateError, match="hardware/Beta"):
        write_physical_candidate_gate(replace(evidence, hardware_verified=True), tmp_path / "gate.json")


def test_writer_is_immutable(tmp_path: Path) -> None:
    evidence = bind_physical_candidate_gate(*_objects())
    destination = tmp_path / "gate.json"
    digest = write_physical_candidate_gate(evidence, destination)
    assert digest == evidence.evidence_sha256()
    assert destination.read_text(encoding="utf-8") == evidence.canonical_json()
    with pytest.raises(PhysicalCandidateGateError, match="overwrite"):
        write_physical_candidate_gate(evidence, destination)
