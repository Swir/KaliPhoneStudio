from dataclasses import replace
from pathlib import Path

import pytest

from kaliphonestudio.device_tree import DeviceTreeError
from kaliphonestudio.device_tree_authority import (
    authority_from_dict,
    build_reviewed_device_tree_authority,
    load_device_tree_authority,
    verify_device_tree_authority,
    write_device_tree_authority,
)
from kaliphonestudio.device_tree_build import (
    DeviceTreeBuildPlan,
    DeviceTreeBuildRunEvidence,
    DeviceTreeReproducibilityEvidence,
    RawOverlayEvidence,
)


def fixtures():
    plan = DeviceTreeBuildPlan(
        schema_version=1,
        profile_id="oneplus/avicii",
        kernel_plan_sha256="a" * 64,
        kernel_authority_sha256="b" * 64,
        source_commit="c" * 40,
        build_target="dtbs",
        dtb_output="arch/arm64/boot/dts/vendor/20801/lito.dtb",
        dtbo_outputs=("arch/arm64/boot/dts/vendor/20801/avicii-overlay.dtbo",),
        dtbo_page_size=4096,
        dtbo_table_version=0,
        format_lock_sha256="d" * 64,
    )
    overlay = RawOverlayEvidence(
        relative_path=plan.dtbo_outputs[0],
        artifact_sha256="e" * 64,
        artifact_size=8192,
        fdt_tree_count=1,
        fdt_evidence_sha256="f" * 64,
    )
    run = DeviceTreeBuildRunEvidence(
        schema_version=1,
        profile_id=plan.profile_id,
        device_tree_plan_sha256=plan.plan_sha256(),
        kernel_authority_sha256=plan.kernel_authority_sha256,
        kernel_config_sha256="1" * 64,
        kernel_image_sha256="2" * 64,
        dtb_relative_path=plan.dtb_output,
        dtb_sha256="3" * 64,
        dtb_size=32768,
        dtb_tree_count=1,
        dtb_evidence_sha256="4" * 64,
        raw_dtbo=(overlay,),
        dtbo_image_sha256="5" * 64,
        dtbo_image_size=16384,
        dtbo_entry_count=1,
        dtbo_evidence_sha256="6" * 64,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    repro = DeviceTreeReproducibilityEvidence(
        schema_version=1,
        profile_id=plan.profile_id,
        device_tree_plan_sha256=plan.plan_sha256(),
        kernel_authority_sha256=plan.kernel_authority_sha256,
        build_a_evidence_sha256=run.evidence_sha256(),
        build_b_evidence_sha256=run.evidence_sha256(),
        dtb_sha256=run.dtb_sha256,
        dtb_size=run.dtb_size,
        raw_dtbo=((overlay.relative_path, overlay.artifact_sha256, overlay.artifact_size),),
        dtbo_image_sha256=run.dtbo_image_sha256,
        dtbo_image_size=run.dtbo_image_size,
        dtbo_entry_count=run.dtbo_entry_count,
        byte_identical=True,
        distinct_build_roots_verified=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    return plan, run, repro


def authority(plan, run, repro):
    return build_reviewed_device_tree_authority(
        authority_name="oneplus-avicii-dt-2026-09-17",
        authority_run_id=123,
        authority_commit="7" * 40,
        authority_artifact_id=456,
        plan=plan,
        run_a=run,
        run_b=run,
        reproducibility=repro,
        reviewed=True,
    )


def test_authority_binds_complete_strict_chain_without_hardware_credit(tmp_path: Path):
    plan, run, repro = fixtures()
    record = authority(plan, run, repro)
    verify_device_tree_authority(record, plan, run, run, repro)
    assert record.strict_byte_identical is True
    assert record.distinct_build_roots_verified is True
    assert record.reviewed is True
    assert record.hardware_verified is False
    assert record.beta_gate_credit is False
    target = tmp_path / "authority.json"
    digest = write_device_tree_authority(record, target)
    assert digest == record.authority_sha256()
    assert load_device_tree_authority(target) == record


def test_authority_creation_requires_explicit_review():
    plan, run, repro = fixtures()
    with pytest.raises(DeviceTreeError, match="reviewed=True"):
        build_reviewed_device_tree_authority(
            authority_name="oneplus-avicii-dt-2026-09-17",
            authority_run_id=1,
            authority_commit="7" * 40,
            authority_artifact_id=2,
            plan=plan,
            run_a=run,
            run_b=run,
            reproducibility=repro,
            reviewed=False,
        )


def test_authority_rejects_detached_reproducibility():
    plan, run, repro = fixtures()
    record = authority(plan, run, repro)
    detached = replace(repro, dtb_sha256="8" * 64)
    with pytest.raises(DeviceTreeError, match="evidence mismatch"):
        verify_device_tree_authority(record, plan, run, run, detached)


def test_authority_rejects_detached_build_record():
    plan, run, repro = fixtures()
    record = authority(plan, run, repro)
    detached = replace(run, dtbo_image_sha256="8" * 64)
    with pytest.raises(DeviceTreeError, match="evidence mismatch|detached"):
        verify_device_tree_authority(record, plan, detached, run, repro)


def test_authority_parser_rejects_host_hardware_or_beta_claims():
    plan, run, repro = fixtures()
    raw = record_dict = __import__("dataclasses").asdict(authority(plan, run, repro))
    raw["hardware_verified"] = True
    with pytest.raises(DeviceTreeError, match="cannot claim"):
        authority_from_dict(raw)
    raw = record_dict.copy()
    raw["hardware_verified"] = False
    raw["beta_gate_credit"] = True
    with pytest.raises(DeviceTreeError, match="cannot claim"):
        authority_from_dict(raw)


def test_authority_writer_is_immutable(tmp_path: Path):
    plan, run, repro = fixtures()
    record = authority(plan, run, repro)
    target = tmp_path / "authority.json"
    write_device_tree_authority(record, target)
    with pytest.raises(DeviceTreeError, match="overwrite"):
        write_device_tree_authority(record, target)
