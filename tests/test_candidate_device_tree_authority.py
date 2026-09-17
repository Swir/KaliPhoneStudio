from dataclasses import fields, replace

import pytest

from kaliphonestudio.candidate import FirstBootCandidateManifest
from kaliphonestudio.candidate_device_tree_authority import (
    bind_first_boot_candidate_to_device_tree_authority,
    write_first_boot_device_tree_authority_evidence,
)
from kaliphonestudio.candidate_kernel_authority import FirstBootKernelAuthorityEvidence
from kaliphonestudio.device_tree import DeviceTreeError
from kaliphonestudio.device_tree_authority import DeviceTreeAuthorityRecord
from kaliphonestudio.device_tree_build import DeviceTreeBuildPlan


DTB_SHA = "1" * 64
DTBO_SHA = "2" * 64
FORMAT_SHA = "3" * 64
KERNEL_AUTH_SHA = "4" * 64


def manifest(**changes):
    values = {}
    texts = {
        "profile_id": "oneplus/avicii",
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
    values.update({
        "device_tree_format_lock_sha256": FORMAT_SHA,
        "dtb_sha256": DTB_SHA,
        "dtb_size": 32768,
        "dtb_tree_count": 1,
        "dtbo_sha256": DTBO_SHA,
        "dtbo_size": 16384,
        "dtbo_entry_count": 1,
    })
    values.update(changes)
    return FirstBootCandidateManifest(**values)


def plan():
    return DeviceTreeBuildPlan(
        schema_version=1,
        profile_id="oneplus/avicii",
        kernel_plan_sha256="c" * 64,
        kernel_authority_sha256=KERNEL_AUTH_SHA,
        source_commit="a" * 40,
        build_target="dtbs",
        dtb_output="arch/arm64/boot/dts/vendor/20801/lito.dtb",
        dtbo_outputs=("arch/arm64/boot/dts/vendor/20801/avicii-overlay.dtbo",),
        dtbo_page_size=4096,
        dtbo_table_version=0,
        format_lock_sha256=FORMAT_SHA,
    )


def authority(dt_plan):
    return DeviceTreeAuthorityRecord(
        schema_version=1,
        authority_name="oneplus-avicii-dt-test",
        authority_run_id=100,
        authority_commit="d" * 40,
        authority_artifact_id=200,
        profile_id="oneplus/avicii",
        device_tree_plan_sha256=dt_plan.plan_sha256(),
        kernel_authority_sha256=KERNEL_AUTH_SHA,
        build_a_evidence_sha256="e" * 64,
        build_b_evidence_sha256="f" * 64,
        reproducibility_evidence_sha256="0" * 64,
        dtb_sha256=DTB_SHA,
        dtb_size=32768,
        raw_dtbo=((dt_plan.dtbo_outputs[0], "5" * 64, 8192),),
        dtbo_image_sha256=DTBO_SHA,
        dtbo_image_size=16384,
        dtbo_entry_count=1,
        strict_byte_identical=True,
        distinct_build_roots_verified=True,
        reviewed=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def kernel_binding(candidate):
    return FirstBootKernelAuthorityEvidence(
        schema_version=1,
        profile_id=candidate.profile_id,
        first_boot_manifest_sha256=candidate.manifest_sha256(),
        kernel_authority_sha256=KERNEL_AUTH_SHA,
        authority_name="kernel-test",
        authority_run_id=1,
        authority_commit="6" * 40,
        authority_artifact_id=2,
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
        image_sha256=candidate.kernel_image_sha256,
        image_size=candidate.kernel_image_size,
        strict_byte_identical=True,
        distinct_build_roots_verified=True,
        reviewed=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def test_candidate_binds_dt_authority_to_same_reviewed_kernel_authority(tmp_path):
    candidate = manifest()
    dt_plan = plan()
    record = authority(dt_plan)
    kernel = kernel_binding(candidate)
    evidence = bind_first_boot_candidate_to_device_tree_authority(candidate, dt_plan, record, kernel)
    assert evidence.first_boot_manifest_sha256 == candidate.manifest_sha256()
    assert evidence.device_tree_authority_sha256 == record.authority_sha256()
    assert evidence.kernel_authority_sha256 == kernel.kernel_authority_sha256 == KERNEL_AUTH_SHA
    assert evidence.dtb_sha256 == DTB_SHA
    assert evidence.dtbo_image_sha256 == DTBO_SHA
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False
    out = tmp_path / "dt-authority-binding.json"
    digest = write_first_boot_device_tree_authority_evidence(evidence, out)
    assert digest == evidence.evidence_sha256()


def test_candidate_rejects_different_kernel_authority():
    candidate = manifest()
    dt_plan = plan()
    with pytest.raises(DeviceTreeError, match="authorities do not match"):
        bind_first_boot_candidate_to_device_tree_authority(
            candidate,
            dt_plan,
            authority(dt_plan),
            replace(kernel_binding(candidate), kernel_authority_sha256="9" * 64),
        )


def test_candidate_rejects_dt_artifact_or_format_lock_drift():
    candidate = manifest()
    dt_plan = plan()
    record = authority(dt_plan)
    with pytest.raises(DeviceTreeError, match="DTB"):
        bind_first_boot_candidate_to_device_tree_authority(
            replace(candidate, dtb_sha256="8" * 64), dt_plan, record,
            kernel_binding(replace(candidate, dtb_sha256="8" * 64)),
        )
    with pytest.raises(DeviceTreeError, match="format lock"):
        changed = replace(candidate, device_tree_format_lock_sha256="8" * 64)
        bind_first_boot_candidate_to_device_tree_authority(
            changed, dt_plan, record, kernel_binding(changed)
        )


def test_candidate_rejects_detached_kernel_binding_manifest():
    candidate = manifest()
    dt_plan = plan()
    kernel = replace(kernel_binding(candidate), first_boot_manifest_sha256="8" * 64)
    with pytest.raises(DeviceTreeError, match="detached from first-boot manifest"):
        bind_first_boot_candidate_to_device_tree_authority(candidate, dt_plan, authority(dt_plan), kernel)
