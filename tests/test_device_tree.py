from hashlib import sha256
from pathlib import Path
import struct

import pytest

from kaliphonestudio.boot_builder import BootBuildPlan, BuildInput
from kaliphonestudio.device_tree import (
    DeviceTreeError,
    bind_device_tree_candidate_evidence,
    inspect_dtb_artifact,
    inspect_dtbo_artifact,
    load_device_tree_format_locks,
)
from kaliphonestudio.profiles import get_profile


ROOT = Path(__file__).parents[1]


def fdt_blob(*, version=17, last_comp_version=16) -> bytes:
    reserve = b"\x00" * 16
    structure = struct.pack(">4I", 1, 0, 2, 9)
    strings = b"x\x00"
    off_mem = 40
    off_struct = off_mem + len(reserve)
    off_strings = off_struct + len(structure)
    total = off_strings + len(strings)
    header = struct.pack(
        ">10I",
        0xD00DFEED,
        total,
        off_struct,
        off_strings,
        off_mem,
        version,
        last_comp_version,
        0,
        len(strings),
        len(structure),
    )
    return header + reserve + structure + strings


def dtbo_blob(*, overlay=None, page_size=4096) -> bytes:
    overlay = overlay or fdt_blob()
    header_size = 32
    entry_size = 32
    entries_offset = header_size
    payload_offset = header_size + entry_size
    total_size = payload_offset + len(overlay)
    header = struct.pack(
        ">8I",
        0xD7B7AB1E,
        total_size,
        header_size,
        entry_size,
        1,
        entries_offset,
        page_size,
        0,
    )
    entry = struct.pack(">8I", len(overlay), payload_offset, 0, 0, 0, 0, 0, 0)
    return header + entry + overlay


def write_artifacts(tmp_path):
    dtb = tmp_path / "dtb"
    dtbo = tmp_path / "dtbo"
    dtb.write_bytes(fdt_blob() + b"\x00\x00")
    dtbo.write_bytes(dtbo_blob())
    return dtb, dtbo


def build_plan(dtb: Path, dtbo: Path) -> BootBuildPlan:
    return BootBuildPlan(
        schema_version=1,
        profile_id="oneplus/avicii",
        stock_boot_sha256="1" * 64,
        stock_ota_sha256="2" * 64,
        header_version=2,
        page_size=4096,
        ramdisk_compression="lz4",
        kernel_cmdline=(),
        inputs=(
            BuildInput("kernel", "Image", 4096, "3" * 64),
            BuildInput("ramdisk", "rescue.cpio.lz4", 2048, "4" * 64),
            BuildInput("dtb", dtb.name, dtb.stat().st_size, sha256(dtb.read_bytes()).hexdigest()),
            BuildInput("dtbo", dtbo.name, dtbo.stat().st_size, sha256(dtbo.read_bytes()).hexdigest()),
        ),
    )


def test_inspect_dtb_supports_zero_padded_concatenated_fdt(tmp_path):
    artifact = tmp_path / "dtb"
    one = fdt_blob()
    artifact.write_bytes(one + b"\x00\x00" + one)
    evidence = inspect_dtb_artifact(artifact)
    assert evidence.schema_version == 1
    assert evidence.tree_count == 2
    assert evidence.fdt_versions == (17, 17)
    assert evidence.artifact_sha256 == sha256(artifact.read_bytes()).hexdigest()


def test_dtb_rejects_invalid_header_and_nonzero_garbage(tmp_path):
    bad = tmp_path / "bad.dtb"
    bad.write_bytes(b"BAD!" + fdt_blob()[4:])
    with pytest.raises(DeviceTreeError, match="FDT magic"):
        inspect_dtb_artifact(bad)

    garbage = tmp_path / "garbage.dtb"
    garbage.write_bytes(fdt_blob() + b"\x00\x00\x00\x01")
    with pytest.raises(DeviceTreeError):
        inspect_dtb_artifact(garbage)


def test_inspect_dtbo_verifies_android_table_and_embedded_overlay(tmp_path):
    artifact = tmp_path / "dtbo.img"
    artifact.write_bytes(dtbo_blob())
    evidence = inspect_dtbo_artifact(artifact)
    assert evidence.schema_version == 1
    assert evidence.entry_count == 1
    assert evidence.page_size == 4096
    assert evidence.table_version == 0
    assert len(evidence.overlay_sha256) == 1


def test_dtbo_rejects_invalid_table_contract(tmp_path):
    artifact = tmp_path / "bad-dtbo.img"
    payload = bytearray(dtbo_blob())
    struct.pack_into(">I", payload, 0, 0)
    artifact.write_bytes(payload)
    with pytest.raises(DeviceTreeError, match="magic"):
        inspect_dtbo_artifact(artifact)

    payload = bytearray(dtbo_blob())
    struct.pack_into(">I", payload, 24, 1000)
    artifact.write_bytes(payload)
    with pytest.raises(DeviceTreeError, match="page size"):
        inspect_dtbo_artifact(artifact)


def test_format_lock_is_full_commit_and_canonical():
    data, digest = load_device_tree_format_locks(ROOT / "tools" / "device-tree-format-locks.json")
    assert data["schema_version"] == 1
    assert {item["kind"] for item in data["references"]} == {"dtb", "dtbo"}
    assert len(digest) == 64
    assert all(len(item["commit"]) == 40 for item in data["references"])


def test_bind_device_tree_evidence_to_exact_profile_and_boot_plan(tmp_path):
    profile = get_profile(ROOT / "devices", "oneplus/avicii")
    dtb, dtbo = write_artifacts(tmp_path)
    plan = build_plan(dtb, dtbo)
    evidence = bind_device_tree_candidate_evidence(
        profile,
        plan,
        format_lock=ROOT / "tools" / "device-tree-format-locks.json",
        dtb=dtb,
        dtbo=dtbo,
    )
    assert evidence.profile_id == profile.profile_id
    assert evidence.boot_plan_sha256 == plan.plan_sha256()
    assert evidence.dtb_sha256 == sha256(dtb.read_bytes()).hexdigest()
    assert evidence.dtbo_sha256 == sha256(dtbo.read_bytes()).hexdigest()
    assert evidence.dtb_tree_count == 1
    assert evidence.dtbo_entry_count == 1


def test_bind_rejects_post_plan_dtb_drift(tmp_path):
    profile = get_profile(ROOT / "devices", "oneplus/avicii")
    dtb, dtbo = write_artifacts(tmp_path)
    plan = build_plan(dtb, dtbo)
    dtb.write_bytes(fdt_blob() + b"\x00\x00\x00\x00")
    with pytest.raises(DeviceTreeError, match="does not match the approved boot build plan"):
        bind_device_tree_candidate_evidence(
            profile,
            plan,
            format_lock=ROOT / "tools" / "device-tree-format-locks.json",
            dtb=dtb,
            dtbo=dtbo,
        )


def test_bind_rejects_profile_plan_mismatch(tmp_path):
    profile = get_profile(ROOT / "devices", "oneplus/avicii")
    dtb, dtbo = write_artifacts(tmp_path)
    plan = build_plan(dtb, dtbo)
    wrong = BootBuildPlan(
        schema_version=plan.schema_version,
        profile_id="other/device",
        stock_boot_sha256=plan.stock_boot_sha256,
        stock_ota_sha256=plan.stock_ota_sha256,
        header_version=plan.header_version,
        page_size=plan.page_size,
        ramdisk_compression=plan.ramdisk_compression,
        kernel_cmdline=plan.kernel_cmdline,
        inputs=plan.inputs,
    )
    with pytest.raises(DeviceTreeError, match="profile does not match"):
        bind_device_tree_candidate_evidence(
            profile,
            wrong,
            format_lock=ROOT / "tools" / "device-tree-format-locks.json",
            dtb=dtb,
            dtbo=dtbo,
        )
