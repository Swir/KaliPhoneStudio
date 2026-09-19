from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from kaliphonestudio.phosh import load_phosh_source_lock
from kaliphonestudio.phosh_build import (
    PhoshBuildError, create_phosh_rootfs_build_evidence, create_phosh_rootfs_build_plan,
    load_phosh_rootfs_build_contract, render_family_supplement_recipe,
)

LOCK = Path("tools/phosh-source-lock.json")
CONTRACT = Path("tools/phosh-rootfs-build-contract.json")


def load():
    source = load_phosh_source_lock(LOCK)
    contract = load_phosh_rootfs_build_contract(CONTRACT, source)
    return source, contract


def test_build_contract_is_bound_and_non_promoting():
    source, contract = load()
    assert contract.phosh_source_lock_sha256 == source.lock_sha256()
    assert contract.architecture == "arm64"
    assert contract.environment == "phosh"
    assert contract.family == "qcom"
    assert contract.mirror.startswith("https://")
    assert contract.double_build_required is True
    assert contract.canonicalization_required is True
    assert contract.physical_validation_required is True
    assert contract.hardware_verified is False
    assert contract.beta_gate_credit is False


def test_build_plan_executes_rootfs_template_not_device_image_builder():
    source, contract = load()
    plan = create_phosh_rootfs_build_plan(source, contract)
    joined = " ".join(plan.base_argv)
    assert plan.base_argv[0] == "debos"
    assert plan.base_argv[-1] == "rootfs.yaml"
    assert "environment:phosh" in plan.base_argv
    assert "architecture:arm64" in plan.base_argv
    assert "nonfree:true" in plan.base_argv
    assert "contrib:true" in plan.base_argv
    assert "suite:forky" in plan.base_argv
    assert f"mirror:{contract.mirror}" in plan.base_argv
    assert "build.sh" not in joined
    assert "image.yaml" not in joined
    assert "sdm845" not in joined
    assert "pinephone" not in joined
    assert "avicii" not in joined
    assert plan.hardware_verified is False
    assert plan.beta_gate_credit is False


def test_family_stage_installs_only_locked_qcom_phosh_supplement():
    source, contract = load()
    recipe = render_family_supplement_recipe(source, contract).decode("utf-8")
    qcom = next(item for item in source.recipes if item.path == "devices/qcom/packages-phosh.yaml")
    for package in qcom.packages:
        assert f"      - {package}\n" in recipe
    common = next(item for item in source.recipes if item.path == "include/packages-phosh.yaml")
    assert f"      - {common.packages[0]}\n" not in recipe
    assert "devices/qcom/packages-base.yaml" not in recipe
    assert "sdm845" not in recipe
    assert "avicii" not in recipe
    assert "action: pack" in recipe


def test_bad_source_lock_binding_fails_closed():
    source, contract = load()
    broken = replace(contract, phosh_source_lock_sha256="0" * 64)
    with pytest.raises(PhoshBuildError, match="not bound"):
        create_phosh_rootfs_build_plan(source, broken)


def test_host_contract_cannot_grant_hardware_or_beta_credit():
    source, contract = load()
    with pytest.raises(PhoshBuildError, match="cannot grant hardware/Beta credit"):
        create_phosh_rootfs_build_plan(source, replace(contract, hardware_verified=True))
    with pytest.raises(PhoshBuildError, match="cannot grant hardware/Beta credit"):
        create_phosh_rootfs_build_plan(source, replace(contract, beta_gate_credit=True))


def test_single_build_evidence_is_explicitly_non_authoritative():
    source, contract = load()
    plan = create_phosh_rootfs_build_plan(source, contract)
    evidence = create_phosh_rootfs_build_evidence(plan, artifact_sha256="1" * 64, artifact_size=512 * 1024 * 1024, package_manifest_sha256="2" * 64, package_count=500, phosh_package_contract_satisfied=True)
    assert evidence.phosh_package_contract_satisfied is True
    assert evidence.reproducibility_authority is False
    assert evidence.physical_validation_required is True
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False


def test_incomplete_phosh_package_contract_cannot_emit_build_evidence():
    source, contract = load()
    plan = create_phosh_rootfs_build_plan(source, contract)
    with pytest.raises(PhoshBuildError, match="not satisfied"):
        create_phosh_rootfs_build_evidence(plan, artifact_sha256="1" * 64, artifact_size=1, package_manifest_sha256="2" * 64, package_count=1, phosh_package_contract_satisfied=False)
