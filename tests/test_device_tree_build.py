from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import struct

import pytest

from kaliphonestudio.device_tree import DeviceTreeError, inspect_dtbo_artifact
from kaliphonestudio.device_tree_build import (
    DeviceTreeBuildRunEvidence,
    RawOverlayEvidence,
    create_device_tree_build_plan,
    pack_android_dtbo_image,
    verify_device_tree_reproducibility,
)
from kaliphonestudio.kernel_authority import load_kernel_authority
from kaliphonestudio.kernel_contract import create_kernel_build_plan
from kaliphonestudio.profiles import get_profile


ROOT = Path(__file__).parents[1]
AUTHORITY = ROOT / "evidence" / "authorities" / "oneplus-avicii-kernel-4.19.300-2026-09-17.json"
FORMAT_LOCK = ROOT / "tools" / "device-tree-format-locks.json"


def fdt_blob() -> bytes:
    reserve = b"\x00" * 16
    structure = struct.pack(">4I", 1, 0, 2, 9)
    strings = b"x\x00"
    off_mem = 40
    off_struct = off_mem + len(reserve)
    off_strings = off_struct + len(structure)
    total = off_strings + len(strings)
    header = struct.pack(
        ">10I", 0xD00DFEED, total, off_struct, off_strings, off_mem,
        17, 16, 0, len(strings), len(structure),
    )
    return header + reserve + structure + strings


def plan():
    profile = get_profile(ROOT / "devices", "oneplus/avicii")
    kernel_plan = create_kernel_build_plan(profile)
    authority = load_kernel_authority(AUTHORITY)
    return profile, kernel_plan, authority, create_device_tree_build_plan(
        profile, kernel_plan, authority, format_lock=FORMAT_LOCK
    )


def test_profile_drives_exact_avicii_outputs_without_core_hardcoding():
    profile, kernel_plan, authority, dt_plan = plan()
    assert dt_plan.profile_id == "oneplus/avicii"
    assert dt_plan.source_commit == kernel_plan.source_commit == authority.source_commit
    assert dt_plan.build_target == "dtbs"
    assert dt_plan.dtb_output.endswith("vendor/20801/lito.dtb")
    assert dt_plan.dtbo_outputs == (
        "arch/arm64/boot/dts/vendor/20801/avicii-overlay.dtbo",
    )
    assert dt_plan.dtbo_page_size == profile.data["boot"]["page_size"] == 4096
    assert dt_plan.kernel_authority_sha256 == authority.authority_sha256()


def test_plan_rejects_detached_kernel_authority():
    profile, kernel_plan, authority, _dt_plan = plan()
    detached = replace(authority, source_commit="0" * 40)
    with pytest.raises(DeviceTreeError, match="source does not match"):
        create_device_tree_build_plan(profile, kernel_plan, detached, format_lock=FORMAT_LOCK)


def test_deterministic_dtbo_packer_is_byte_identical_and_structurally_valid(tmp_path):
    one = tmp_path / "one.dtbo"
    two = tmp_path / "two.dtbo"
    one.write_bytes(fdt_blob())
    two.write_bytes(fdt_blob())
    a = tmp_path / "a.img"
    b = tmp_path / "b.img"
    pack_android_dtbo_image((one, two), a, page_size=4096)
    pack_android_dtbo_image((one, two), b, page_size=4096)
    assert a.read_bytes() == b.read_bytes()
    evidence = inspect_dtbo_artifact(a)
    assert evidence.entry_count == 2
    assert evidence.page_size == 4096
    assert evidence.table_version == 0
    assert a.stat().st_size % 4096 == 0


def test_packer_rejects_concatenated_or_malformed_overlay(tmp_path):
    overlay = tmp_path / "bad.dtbo"
    overlay.write_bytes(fdt_blob() + b"\x00\x00\x00\x00" + fdt_blob())
    with pytest.raises(DeviceTreeError):
        pack_android_dtbo_image((overlay,), tmp_path / "out.img", page_size=4096)


def _run(dt_plan, suffix: str = ""):
    overlay = RawOverlayEvidence(
        relative_path=dt_plan.dtbo_outputs[0],
        artifact_sha256=("a" if not suffix else suffix) * 64,
        artifact_size=4096,
        fdt_tree_count=1,
        fdt_evidence_sha256="b" * 64,
    )
    return DeviceTreeBuildRunEvidence(
        schema_version=1,
        profile_id=dt_plan.profile_id,
        device_tree_plan_sha256=dt_plan.plan_sha256(),
        kernel_authority_sha256=dt_plan.kernel_authority_sha256,
        kernel_config_sha256="c" * 64,
        kernel_image_sha256="d" * 64,
        dtb_relative_path=dt_plan.dtb_output,
        dtb_sha256="e" * 64,
        dtb_size=8192,
        dtb_tree_count=1,
        dtb_evidence_sha256="f" * 64,
        raw_dtbo=(overlay,),
        dtbo_image_sha256="1" * 64,
        dtbo_image_size=12288,
        dtbo_entry_count=1,
        dtbo_evidence_sha256="2" * 64,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def test_strict_repro_pair_requires_identical_artifacts_and_distinct_roots(tmp_path):
    _profile, _kernel_plan, _authority, dt_plan = plan()
    a_root = tmp_path / "a"
    b_root = tmp_path / "b"
    a_root.mkdir(); b_root.mkdir()
    a = _run(dt_plan)
    b = _run(dt_plan)
    evidence = verify_device_tree_reproducibility(
        dt_plan, a, b, build_root_a=a_root, build_root_b=b_root
    )
    assert evidence.byte_identical is True
    assert evidence.distinct_build_roots_verified is True
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False

    with pytest.raises(DeviceTreeError, match="strict DTB/DTBO"):
        verify_device_tree_reproducibility(
            dt_plan, a, _run(dt_plan, "9"), build_root_a=a_root, build_root_b=b_root
        )
    with pytest.raises(DeviceTreeError, match="independent build roots"):
        verify_device_tree_reproducibility(
            dt_plan, a, b, build_root_a=a_root, build_root_b=a_root
        )
