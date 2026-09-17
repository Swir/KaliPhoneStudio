from dataclasses import asdict, replace
import json
from pathlib import Path

import pytest

from kaliphonestudio.kernel_authority import (
    authority_from_dict,
    build_reviewed_kernel_authority,
    load_kernel_authority,
    verify_kernel_authority,
    write_kernel_authority,
)
from kaliphonestudio.kernel_build_binding import bind_kernel_reproducibility_to_build_runs
from kaliphonestudio.kernel_build_runner import KernelBuildRunEvidence
from kaliphonestudio.kernel_contract import KernelContractError, create_kernel_build_plan
from kaliphonestudio.kernel_repro import KernelReproducibilityEvidence
from kaliphonestudio.kernel_toolchain import load_kernel_toolchain_lock
from kaliphonestudio.profiles import get_profile


ROOT = Path(__file__).resolve().parents[1]


def _plan_and_lock():
    plan = create_kernel_build_plan(get_profile(ROOT / "devices", "oneplus/avicii"))
    lock = load_kernel_toolchain_lock(ROOT / "tools" / "kernel-toolchain-lock.json")
    return plan, lock


def _run(plan, lock, *, suffix: str = "a", **changes):
    values = {
        "schema_version": 1,
        "profile_id": plan.profile_id,
        "kernel_plan_sha256": plan.plan_sha256(),
        "source_commit": plan.source_commit,
        "toolchain_lock_sha256": lock.lock_sha256(),
        "checkout_evidence_sha256": "1" * 64,
        "toolchain_binding_evidence_sha256": "2" * 64,
        "materialized_toolchain_evidence_sha256": "3" * 64,
        "build_recipe_sha256": "4" * 64,
        "reproducible_environment_sha256": "5" * 64,
        "config_evidence_sha256": ("6" if suffix == "a" else "7") * 64,
        "config_sha256": "8" * 64,
        "config_size": 2048,
        "image_evidence_sha256": ("9" if suffix == "a" else "a") * 64,
        "image_sha256": "b" * 64,
        "image_size": 4096,
        "arm64_magic_verified": True,
        "beta_gate_credit": False,
    }
    values.update(changes)
    return KernelBuildRunEvidence(**values)


def _chain():
    plan, lock = _plan_and_lock()
    build_a = _run(plan, lock, suffix="a")
    build_b = _run(plan, lock, suffix="b")
    repro = KernelReproducibilityEvidence(
        schema_version=1,
        profile_id=plan.profile_id,
        kernel_plan_sha256=plan.plan_sha256(),
        source_commit=plan.source_commit,
        kernel_version=plan.expected_kernel_version,
        config_sha256="8" * 64,
        config_size=2048,
        image_sha256="b" * 64,
        image_size=4096,
        build_a_config_evidence_sha256=build_a.config_evidence_sha256,
        build_b_config_evidence_sha256=build_b.config_evidence_sha256,
        build_a_image_evidence_sha256=build_a.image_evidence_sha256,
        build_b_image_evidence_sha256=build_b.image_evidence_sha256,
        distinct_build_roots_verified=True,
        byte_identical=True,
        beta_gate_credit=False,
    )
    binding = bind_kernel_reproducibility_to_build_runs(plan, lock, repro, build_a, build_b)
    return plan, lock, repro, binding, build_a, build_b


def _authority():
    plan, lock, repro, binding, build_a, build_b = _chain()
    authority = build_reviewed_kernel_authority(
        authority_name="oneplus-avicii-kernel-test",
        authority_run_id=123456,
        authority_commit="c" * 40,
        authority_artifact_id=654321,
        plan=plan,
        lock=lock,
        reproducibility=repro,
        binding=binding,
        build_a=build_a,
        build_b=build_b,
        reviewed=True,
    )
    return authority, plan, lock, repro, binding, build_a, build_b


def test_reviewed_authority_binds_complete_host_chain(tmp_path: Path):
    authority, plan, lock, repro, binding, build_a, build_b = _authority()

    verify_kernel_authority(authority, plan, lock, repro, binding, build_a, build_b)
    assert authority.strict_byte_identical is True
    assert authority.distinct_build_roots_verified is True
    assert authority.reviewed is True
    assert authority.hardware_verified is False
    assert authority.beta_gate_credit is False
    assert authority.reproducibility_evidence_sha256 == repro.evidence_sha256()
    assert authority.reproducibility_binding_sha256 == binding.evidence_sha256()
    assert authority.build_a_run_evidence_sha256 == build_a.evidence_sha256()
    assert authority.build_b_run_evidence_sha256 == build_b.evidence_sha256()

    path = tmp_path / "authority.json"
    digest = write_kernel_authority(authority, path)
    assert digest == authority.authority_sha256()
    assert load_kernel_authority(path) == authority
    with pytest.raises(KernelContractError, match="refusing to overwrite"):
        write_kernel_authority(authority, path)


def test_authority_creation_requires_explicit_review():
    plan, lock, repro, binding, build_a, build_b = _chain()
    with pytest.raises(KernelContractError, match="reviewed=True"):
        build_reviewed_kernel_authority(
            authority_name="oneplus-avicii-kernel-test",
            authority_run_id=1,
            authority_commit="c" * 40,
            authority_artifact_id=2,
            plan=plan,
            lock=lock,
            reproducibility=repro,
            binding=binding,
            build_a=build_a,
            build_b=build_b,
            reviewed=False,
        )


def test_authority_rejects_hardware_or_beta_claims():
    authority, *_rest = _authority()
    raw = asdict(authority)
    raw["hardware_verified"] = True
    with pytest.raises(KernelContractError, match="hardware verification"):
        authority_from_dict(raw)
    raw = asdict(authority)
    raw["beta_gate_credit"] = True
    with pytest.raises(KernelContractError, match="Beta-gate credit"):
        authority_from_dict(raw)


def test_authority_rejects_detached_binding_or_artifact_identity():
    authority, plan, lock, repro, binding, build_a, build_b = _authority()
    detached = replace(binding, reproducibility_evidence_sha256="d" * 64)
    with pytest.raises(KernelContractError, match="binding does not match"):
        verify_kernel_authority(authority, plan, lock, repro, detached, build_a, build_b)

    raw = asdict(authority)
    raw["image_sha256"] = "e" * 64
    altered = authority_from_dict(raw)
    with pytest.raises(KernelContractError, match="image_sha256"):
        verify_kernel_authority(altered, plan, lock, repro, binding, build_a, build_b)


def test_authority_parser_rejects_field_injection_and_non_strict_record():
    authority, *_ = _authority()
    raw = asdict(authority)
    raw["unexpected"] = "x"
    with pytest.raises(KernelContractError, match="invalid kernel authority record fields"):
        authority_from_dict(raw)

    raw = asdict(authority)
    raw["strict_byte_identical"] = False
    with pytest.raises(KernelContractError, match="strict byte-identical"):
        authority_from_dict(raw)


def test_load_rejects_symlink_authority(tmp_path: Path):
    authority, *_ = _authority()
    real = tmp_path / "real.json"
    real.write_text(authority.canonical_json(), encoding="utf-8")
    link = tmp_path / "link.json"
    try:
        link.symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(KernelContractError, match="non-symlink"):
        load_kernel_authority(link)
