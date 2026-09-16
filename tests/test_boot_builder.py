from pathlib import Path
import copy

import pytest

from kaliphonestudio.boot_builder import create_boot_build_plan
from kaliphonestudio.boot_image import BootImageError
from kaliphonestudio.profiles import DeviceProfile, get_profile
from kaliphonestudio.provenance import StockBootProvenance

ROOT = Path(__file__).parents[1]
PROFILE = get_profile(ROOT / "devices", "oneplus/avicii")


def provenance(profile_id="oneplus/avicii", header=2):
    return StockBootProvenance(
        schema_version=1, profile_id=profile_id, ota_sha256="a" * 64, ota_size=10,
        payload_sha256="b" * 64, payload_metadata_sha256="c" * 64, payload_size=9,
        boot_sha256="d" * 64, boot_size=4096, boot_header_version=header,
        firmware_metadata={"post-build": "exact-build"},
    )


def inputs(tmp_path):
    paths = {}
    for name in ("kernel", "ramdisk", "dtb", "dtbo"):
        p = tmp_path / name
        p.write_bytes((name + "-bytes").encode())
        paths[name] = p
    return paths


def test_plan_is_deterministic_and_profile_driven(tmp_path):
    p = inputs(tmp_path)
    one = create_boot_build_plan(PROFILE, provenance(), kernel=p["kernel"], ramdisk=p["ramdisk"], dtb=p["dtb"], dtbo=p["dtbo"])
    two = create_boot_build_plan(PROFILE, provenance(), kernel=p["kernel"], ramdisk=p["ramdisk"], dtb=p["dtb"], dtbo=p["dtbo"])
    assert one == two
    assert one.plan_sha256() == two.plan_sha256()
    assert one.header_version == PROFILE.data["boot"]["header_version"]
    assert one.page_size == PROFILE.data["boot"]["page_size"]
    assert [x.name for x in one.inputs] == ["kernel", "ramdisk", "dtb", "dtbo"]


def test_plan_binds_stock_provenance_to_profile(tmp_path):
    p = inputs(tmp_path)
    with pytest.raises(BootImageError, match="profile"):
        create_boot_build_plan(PROFILE, provenance("vendor/other"), kernel=p["kernel"], ramdisk=p["ramdisk"], dtb=p["dtb"], dtbo=p["dtbo"])


def test_plan_rejects_stock_header_mismatch(tmp_path):
    p = inputs(tmp_path)
    with pytest.raises(BootImageError, match="header"):
        create_boot_build_plan(PROFILE, provenance(header=4), kernel=p["kernel"], ramdisk=p["ramdisk"], dtb=p["dtb"], dtbo=p["dtbo"])


def test_plan_requires_profile_declared_dtb_and_dtbo(tmp_path):
    p = inputs(tmp_path)
    with pytest.raises(BootImageError, match="DTB"):
        create_boot_build_plan(PROFILE, provenance(), kernel=p["kernel"], ramdisk=p["ramdisk"], dtbo=p["dtbo"])
    with pytest.raises(BootImageError, match="DTBO"):
        create_boot_build_plan(PROFILE, provenance(), kernel=p["kernel"], ramdisk=p["ramdisk"], dtb=p["dtb"])


def test_plan_rejects_unexpected_dtb_for_other_profile(tmp_path):
    p = inputs(tmp_path)
    data = copy.deepcopy(PROFILE.data)
    data["boot"]["include_dtb"] = False
    other = DeviceProfile(path=PROFILE.path, data=data)
    with pytest.raises(BootImageError, match="does not permit"):
        create_boot_build_plan(other, provenance(), kernel=p["kernel"], ramdisk=p["ramdisk"], dtb=p["dtb"], dtbo=p["dtbo"])
