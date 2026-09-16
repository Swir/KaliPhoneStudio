from pathlib import Path
import copy
import sys

import pytest

from kaliphonestudio.boot_builder import assemble_boot_image_reproducibly, create_boot_build_plan, mkbootimg_argv, source_locked_assembler_prefix, verify_boot_build_plan, write_boot_build_plan
from kaliphonestudio.boot_image import BootImageError
from kaliphonestudio.profiles import DeviceProfile, get_profile
from kaliphonestudio.provenance import StockBootProvenance

ROOT = Path(__file__).parents[1]
PROFILE = get_profile(ROOT / "devices", "oneplus/avicii")

def provenance(profile_id="oneplus/avicii", header=2):
    return StockBootProvenance(schema_version=1, profile_id=profile_id, ota_sha256="a"*64, ota_size=10, payload_sha256="b"*64, payload_metadata_sha256="c"*64, payload_size=9, boot_sha256="d"*64, boot_size=4096, boot_header_version=header, firmware_metadata={"post-build":"exact-build"})

def inputs(tmp_path):
    paths={}
    for name in ("kernel","ramdisk","dtb","dtbo"):
        p=tmp_path/name; p.write_bytes((name+"-bytes").encode()); paths[name]=p
    return paths

def make_plan(tmp_path):
    p=inputs(tmp_path); return create_boot_build_plan(PROFILE, provenance(), kernel=p["kernel"], ramdisk=p["ramdisk"], dtb=p["dtb"], dtbo=p["dtbo"]),p

def test_plan_is_deterministic_and_profile_driven(tmp_path):
    plan,p=make_plan(tmp_path); two=create_boot_build_plan(PROFILE, provenance(), kernel=p["kernel"], ramdisk=p["ramdisk"], dtb=p["dtb"], dtbo=p["dtbo"])
    assert plan==two and plan.plan_sha256()==two.plan_sha256(); assert plan.header_version==PROFILE.data["boot"]["header_version"]; assert [x.name for x in plan.inputs]==["kernel","ramdisk","dtb","dtbo"]

def test_plan_binds_stock_provenance_to_profile(tmp_path):
    p=inputs(tmp_path)
    with pytest.raises(BootImageError,match="profile"): create_boot_build_plan(PROFILE, provenance("vendor/other"), kernel=p["kernel"], ramdisk=p["ramdisk"], dtb=p["dtb"], dtbo=p["dtbo"])

def test_plan_rejects_stock_header_mismatch(tmp_path):
    p=inputs(tmp_path)
    with pytest.raises(BootImageError,match="header"): create_boot_build_plan(PROFILE, provenance(header=4), kernel=p["kernel"], ramdisk=p["ramdisk"], dtb=p["dtb"], dtbo=p["dtbo"])

def test_plan_requires_profile_declared_dtb_and_dtbo(tmp_path):
    p=inputs(tmp_path)
    with pytest.raises(BootImageError,match="DTB"): create_boot_build_plan(PROFILE, provenance(), kernel=p["kernel"], ramdisk=p["ramdisk"], dtbo=p["dtbo"])
    with pytest.raises(BootImageError,match="DTBO"): create_boot_build_plan(PROFILE, provenance(), kernel=p["kernel"], ramdisk=p["ramdisk"], dtb=p["dtb"])

def test_plan_rejects_unexpected_dtb_for_other_profile(tmp_path):
    p=inputs(tmp_path); data=copy.deepcopy(PROFILE.data); data["boot"]["include_dtb"]=False; other=DeviceProfile(path=PROFILE.path,data=data)
    with pytest.raises(BootImageError,match="does not permit"): create_boot_build_plan(other, provenance(), kernel=p["kernel"], ramdisk=p["ramdisk"], dtb=p["dtb"], dtbo=p["dtbo"])

def test_plan_revalidation_accepts_unchanged_inputs(tmp_path):
    plan,_=make_plan(tmp_path); verify_boot_build_plan(plan,PROFILE,provenance(),input_dir=tmp_path)

def test_plan_revalidation_detects_input_drift(tmp_path):
    plan,p=make_plan(tmp_path); p["kernel"].write_bytes(b"tampered-kernel")
    with pytest.raises(BootImageError,match="changed: kernel"): verify_boot_build_plan(plan,PROFILE,provenance(),input_dir=tmp_path)

def test_plan_revalidation_detects_stock_provenance_drift(tmp_path):
    plan,_=make_plan(tmp_path); changed=provenance(); object.__setattr__(changed,"boot_sha256","e"*64)
    with pytest.raises(BootImageError,match="provenance changed"): verify_boot_build_plan(plan,PROFILE,changed,input_dir=tmp_path)

def test_plan_revalidation_detects_profile_policy_drift(tmp_path):
    plan,_=make_plan(tmp_path); data=copy.deepcopy(PROFILE.data); data["boot"]["page_size"]*=2; changed=DeviceProfile(path=PROFILE.path,data=data)
    with pytest.raises(BootImageError,match="layout contract changed"): verify_boot_build_plan(plan,changed,provenance(),input_dir=tmp_path)

def test_plan_persistence_is_canonical_and_hash_bound(tmp_path):
    plan,_=make_plan(tmp_path); destination=tmp_path/"evidence"/"boot-plan.json"; digest=write_boot_build_plan(plan,destination); assert destination.read_text()==plan.canonical_json(); assert digest==plan.plan_sha256()

def locked_checkout(tmp_path, body="# exact locked checkout fixture\n"):
    checkout=tmp_path/"mkbootimg-checkout"; checkout.mkdir(); (checkout/"mkbootimg.py").write_text(body); return checkout

def test_plan_resolves_only_source_locked_mkbootimg(tmp_path):
    plan,_=make_plan(tmp_path); checkout=locked_checkout(tmp_path); assert source_locked_assembler_prefix(plan,lock_manifest=ROOT/"tools"/"boot-tool-locks.json",exact_checkout=checkout)==("python",str(checkout/"mkbootimg.py"))

def test_mkbootimg_argv_is_deterministic_profile_driven_and_excludes_separate_dtbo(tmp_path):
    plan,_=make_plan(tmp_path); checkout=locked_checkout(tmp_path); kwargs=dict(input_dir=tmp_path,output=tmp_path/"candidate.img",lock_manifest=ROOT/"tools"/"boot-tool-locks.json",exact_checkout=checkout); one=mkbootimg_argv(plan,PROFILE,provenance(),**kwargs); two=mkbootimg_argv(plan,PROFILE,provenance(),**kwargs); assert one==two; assert "--dtb" in one and "--recovery_dtbo" not in one

def test_mkbootimg_argv_revalidates_inputs_at_invocation_boundary(tmp_path):
    plan,p=make_plan(tmp_path); checkout=locked_checkout(tmp_path); p["ramdisk"].write_bytes(b"changed-after-plan")
    with pytest.raises(BootImageError,match="changed: ramdisk"): mkbootimg_argv(plan,PROFILE,provenance(),input_dir=tmp_path,output=tmp_path/"candidate.img",lock_manifest=ROOT/"tools"/"boot-tool-locks.json",exact_checkout=checkout)

def test_reproducible_assembly_builds_twice_and_records_evidence(tmp_path, monkeypatch):
    plan,_=make_plan(tmp_path); checkout=locked_checkout(tmp_path)
    def fake_run(argv, **kwargs):
        Path(argv[argv.index("--output")+1]).write_bytes(b"ANDROID!deterministic-fixture")
        class R: returncode=0
        return R()
    monkeypatch.setattr("kaliphonestudio.boot_builder.subprocess.run",fake_run)
    out=tmp_path/"out"/"candidate.img"; ev=assemble_boot_image_reproducibly(plan,PROFILE,provenance(),input_dir=tmp_path,destination=out,lock_manifest=ROOT/"tools"/"boot-tool-locks.json",exact_checkout=checkout)
    assert out.read_bytes()==b"ANDROID!deterministic-fixture"; assert ev.reproducible and ev.image_size==len(out.read_bytes()); assert ev.plan_sha256==plan.plan_sha256()

def test_reproducible_assembly_rejects_nondeterministic_output(tmp_path, monkeypatch):
    plan,_=make_plan(tmp_path); checkout=locked_checkout(tmp_path); calls=[b"first",b"second"]
    def fake_run(argv, **kwargs): Path(argv[argv.index("--output")+1]).write_bytes(calls.pop(0))
    monkeypatch.setattr("kaliphonestudio.boot_builder.subprocess.run",fake_run)
    out=tmp_path/"candidate.img"
    with pytest.raises(BootImageError,match="not reproducible"): assemble_boot_image_reproducibly(plan,PROFILE,provenance(),input_dir=tmp_path,destination=out,lock_manifest=ROOT/"tools"/"boot-tool-locks.json",exact_checkout=checkout)
    assert not out.exists()
