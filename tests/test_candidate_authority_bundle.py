from dataclasses import fields, replace

import pytest

from kaliphonestudio.candidate import FirstBootCandidateManifest
from kaliphonestudio.candidate_authority_bundle import (
    CandidateAuthorityBundleError,
    bind_first_boot_authority_bundle,
    write_first_boot_authority_bundle,
)
from kaliphonestudio.candidate_device_tree_authority import FirstBootDeviceTreeAuthorityEvidence
from kaliphonestudio.candidate_kernel_authority import FirstBootKernelAuthorityEvidence
from kaliphonestudio.candidate_rootfs_authority import FirstBootRootfsAuthorityEvidence


PROFILE = "oneplus/avicii"
KERNEL_AUTH = "1" * 64
ROOTFS_AUTH = "2" * 64
DT_AUTH = "3" * 64
KERNEL_IMAGE = "4" * 64
ROOTFS_ARTIFACT = "5" * 64
DTB = "6" * 64
DTBO = "7" * 64


def manifest(**changes):
    values = {}
    texts = {
        "profile_id": PROFILE,
        "device_serial": "SERIAL123",
        "firmware_build": "AC2003_11_F.22",
        "firmware_fingerprint": "OnePlus/avicii/avicii:test",
        "kernel_source_commit": "a" * 40,
        "kernel_version": "4.19.300",
        "kernel_clang_revision": "r416183b",
    }
    bools = {"kernel_reproducible", "kernel_distinct_build_roots_verified"}
    optionals = {"dtb_sha256", "dtb_size", "dtb_tree_count", "dtbo_sha256", "dtbo_size", "dtbo_entry_count"}
    for field in fields(FirstBootCandidateManifest):
        name = field.name
        if name == "schema_version":
            values[name] = 8
        elif name in texts:
            values[name] = texts[name]
        elif name in bools:
            values[name] = True
        elif name in optionals:
            values[name] = None
        elif name.endswith("_sha256"):
            values[name] = "b" * 64
        elif name.endswith("_size") or name.endswith("_count"):
            values[name] = 1
        else:
            raise AssertionError(name)
    values.update(
        kernel_image_sha256=KERNEL_IMAGE,
        kernel_image_size=43878416,
        rootfs_artifact_sha256=ROOTFS_ARTIFACT,
        rootfs_artifact_size=137460600,
        dtb_sha256=DTB,
        dtb_size=32768,
        dtb_tree_count=1,
        dtbo_sha256=DTBO,
        dtbo_size=16384,
        dtbo_entry_count=1,
    )
    values.update(changes)
    return FirstBootCandidateManifest(**values)


def kernel_binding(candidate):
    return FirstBootKernelAuthorityEvidence(
        schema_version=1,
        profile_id=PROFILE,
        first_boot_manifest_sha256=candidate.manifest_sha256(),
        kernel_authority_sha256=KERNEL_AUTH,
        authority_name="kernel-authority",
        authority_run_id=11,
        authority_commit="c" * 40,
        authority_artifact_id=12,
        source_commit=candidate.kernel_source_commit,
        kernel_plan_sha256=candidate.kernel_plan_sha256,
        toolchain_lock_sha256=candidate.kernel_toolchain_lock_sha256,
        build_recipe_sha256=candidate.kernel_build_recipe_sha256,
        reproducible_environment_sha256=candidate.kernel_reproducible_environment_sha256,
        build_a_run_evidence_sha256=candidate.kernel_build_a_run_evidence_sha256,
        build_b_run_evidence_sha256=candidate.kernel_build_b_run_evidence_sha256,
        reproducibility_evidence_sha256=candidate.kernel_reproducibility_evidence_sha256,
        reproducibility_binding_sha256=candidate.kernel_reproducibility_binding_evidence_sha256,
        config_sha256=candidate.kernel_config_sha256,
        config_size=166055,
        image_sha256=KERNEL_IMAGE,
        image_size=candidate.kernel_image_size,
        strict_byte_identical=True,
        distinct_build_roots_verified=True,
        reviewed=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def rootfs_binding(candidate):
    return FirstBootRootfsAuthorityEvidence(
        schema_version=1,
        profile_id=PROFILE,
        first_boot_manifest_sha256=candidate.manifest_sha256(),
        first_boot_rootfs_provenance_sha256="8" * 64,
        rootfs_authority_sha256=ROOTFS_AUTH,
        authority_name="rootfs-authority",
        authority_run_id=21,
        authority_commit="d" * 40,
        authority_artifact_id=22,
        release_tag="2026.2",
        architecture="arm64",
        variant="minimal",
        rootfs_evidence_sha256=candidate.rootfs_evidence_sha256,
        rootfs_canonicalization_binding_sha256="9" * 64,
        canonicalization_policy_sha256="a" * 64,
        artifact_sha256=ROOTFS_ARTIFACT,
        artifact_size=candidate.rootfs_artifact_size,
        package_manifest_sha256=candidate.rootfs_package_manifest_sha256,
        package_count=candidate.rootfs_package_count,
        source_lock_sha256=candidate.rootfs_source_lock_sha256,
        repository_snapshot_sha256=candidate.repository_snapshot_sha256,
        inrelease_sha256="c" * 64,
        strict_byte_identical=True,
        reviewed=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def dt_binding(candidate):
    return FirstBootDeviceTreeAuthorityEvidence(
        schema_version=1,
        profile_id=PROFILE,
        first_boot_manifest_sha256=candidate.manifest_sha256(),
        device_tree_authority_sha256=DT_AUTH,
        device_tree_plan_sha256="d" * 64,
        kernel_authority_sha256=KERNEL_AUTH,
        authority_name="dt-authority",
        authority_run_id=31,
        authority_commit="e" * 40,
        authority_artifact_id=32,
        format_lock_sha256=candidate.device_tree_format_lock_sha256,
        dtb_sha256=DTB,
        dtb_size=candidate.dtb_size,
        raw_dtbo=(("arch/arm64/boot/dts/vendor/20801/avicii-overlay.dtbo", "f" * 64, 8192),),
        dtbo_image_sha256=DTBO,
        dtbo_image_size=candidate.dtbo_size,
        dtbo_entry_count=candidate.dtbo_entry_count,
        strict_byte_identical=True,
        distinct_build_roots_verified=True,
        reviewed=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def test_bundle_binds_all_authorities_to_same_manifest(tmp_path):
    candidate = manifest()
    kernel = kernel_binding(candidate)
    rootfs = rootfs_binding(candidate)
    dt = dt_binding(candidate)
    evidence = bind_first_boot_authority_bundle(candidate, kernel, rootfs, dt)
    assert evidence.first_boot_manifest_sha256 == candidate.manifest_sha256()
    assert evidence.kernel_authority_sha256 == KERNEL_AUTH
    assert evidence.rootfs_authority_sha256 == ROOTFS_AUTH
    assert evidence.device_tree_authority_sha256 == DT_AUTH
    assert evidence.kernel_image_sha256 == KERNEL_IMAGE
    assert evidence.rootfs_artifact_sha256 == ROOTFS_ARTIFACT
    assert evidence.dtb_sha256 == DTB
    assert evidence.dtbo_image_sha256 == DTBO
    assert evidence.all_authorities_reviewed is True
    assert evidence.all_required_artifacts_strict is True
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False
    out = tmp_path / "bundle.json"
    digest = write_first_boot_authority_bundle(evidence, out)
    assert digest == evidence.evidence_sha256()


def test_bundle_rejects_binding_from_different_manifest():
    candidate = manifest()
    detached = manifest(device_serial="OTHER")
    with pytest.raises(CandidateAuthorityBundleError, match="detached from first-boot manifest"):
        bind_first_boot_authority_bundle(
            candidate,
            kernel_binding(candidate),
            rootfs_binding(detached),
            dt_binding(candidate),
        )


def test_bundle_rejects_dt_authority_from_different_kernel():
    candidate = manifest()
    with pytest.raises(CandidateAuthorityBundleError, match="different reviewed kernel authority"):
        bind_first_boot_authority_bundle(
            candidate,
            kernel_binding(candidate),
            rootfs_binding(candidate),
            replace(dt_binding(candidate), kernel_authority_sha256="0" * 64),
        )


def test_bundle_rejects_artifact_substitution():
    candidate = manifest()
    with pytest.raises(CandidateAuthorityBundleError, match="rootfs differs"):
        bind_first_boot_authority_bundle(
            candidate,
            kernel_binding(candidate),
            replace(rootfs_binding(candidate), artifact_sha256="0" * 64),
            dt_binding(candidate),
        )
    with pytest.raises(CandidateAuthorityBundleError, match="DTBO differs"):
        bind_first_boot_authority_bundle(
            candidate,
            kernel_binding(candidate),
            rootfs_binding(candidate),
            replace(dt_binding(candidate), dtbo_image_sha256="0" * 64),
        )


def test_bundle_rejects_nonreviewed_or_hardware_claims():
    candidate = manifest()
    with pytest.raises(CandidateAuthorityBundleError, match="not reviewed"):
        bind_first_boot_authority_bundle(
            candidate,
            replace(kernel_binding(candidate), reviewed=False),
            rootfs_binding(candidate),
            dt_binding(candidate),
        )
    with pytest.raises(CandidateAuthorityBundleError, match="cannot claim hardware/Beta credit"):
        bind_first_boot_authority_bundle(
            candidate,
            kernel_binding(candidate),
            replace(rootfs_binding(candidate), hardware_verified=True),
            dt_binding(candidate),
        )


def test_bundle_writer_refuses_overwrite(tmp_path):
    candidate = manifest()
    evidence = bind_first_boot_authority_bundle(
        candidate,
        kernel_binding(candidate),
        rootfs_binding(candidate),
        dt_binding(candidate),
    )
    out = tmp_path / "bundle.json"
    write_first_boot_authority_bundle(evidence, out)
    with pytest.raises(CandidateAuthorityBundleError, match="overwrite"):
        write_first_boot_authority_bundle(evidence, out)
