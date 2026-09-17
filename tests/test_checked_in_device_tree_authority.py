from pathlib import Path

from kaliphonestudio.device_tree_authority import (
    load_device_tree_authority,
    plan_from_json,
    reproducibility_from_json,
    run_from_json,
    verify_device_tree_authority,
)


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / "evidence" / "authorities" / "oneplus-avicii-dtb-dtbo-2026-09-17.json"
EVIDENCE = ROOT / "evidence" / "authorities" / "device-tree" / "oneplus-avicii-2026-09-17"


def test_checked_in_avicii_device_tree_authority_reconstructs_strict_chain():
    authority = load_device_tree_authority(AUTHORITY)
    plan = plan_from_json(EVIDENCE / "device-tree-plan.json")
    build_a = run_from_json(EVIDENCE / "device-tree-build-a.json")
    build_b = run_from_json(EVIDENCE / "device-tree-build-b.json")
    reproducibility = reproducibility_from_json(EVIDENCE / "device-tree-reproducibility.json")

    verify_device_tree_authority(authority, plan, build_a, build_b, reproducibility)

    assert authority.profile_id == "oneplus/avicii"
    assert authority.authority_run_id == 35196447576
    assert authority.authority_artifact_id == 10486420567
    assert authority.dtb_sha256 == "48b0902a99c10a11ff52680bf81e9fec2574ad687c58ea35a00fdbf7aefe40ce"
    assert authority.dtbo_image_sha256 == "212392a25add2aa60fdc73163bfdbf1acc082bc5e6e1f3ff1c975e88b857b895"
    assert authority.strict_byte_identical is True
    assert authority.distinct_build_roots_verified is True
    assert authority.reviewed is True
    assert authority.hardware_verified is False
    assert authority.beta_gate_credit is False
