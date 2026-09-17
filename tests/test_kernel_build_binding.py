from dataclasses import replace
import json
from pathlib import Path

import pytest

from kaliphonestudio.kernel_build_binding import (
    bind_kernel_reproducibility_to_build_runs,
    load_kernel_build_run_evidence,
    load_kernel_reproducibility_evidence,
    write_kernel_reproducibility_binding_evidence,
)
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


def _run(plan, lock, **changes):
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
        "config_evidence_sha256": "6" * 64,
        "config_sha256": "7" * 64,
        "config_size": 2048,
        "image_evidence_sha256": "8" * 64,
        "image_sha256": "9" * 64,
        "image_size": 4096,
        "arm64_magic_verified": True,
        "beta_gate_credit": False,
    }
    values.update(changes)
    return KernelBuildRunEvidence(**values)


def _repro(plan, **changes):
    values = {
        "schema_version": 1,
        "profile_id": plan.profile_id,
        "kernel_plan_sha256": plan.plan_sha256(),
        "source_commit": plan.source_commit,
        "kernel_version": plan.expected_kernel_version,
        "config_sha256": "7" * 64,
        "config_size": 2048,
        "image_sha256": "9" * 64,
        "image_size": 4096,
        "build_a_config_evidence_sha256": "6" * 64,
        "build_b_config_evidence_sha256": "6" * 64,
        "build_a_image_evidence_sha256": "8" * 64,
        "build_b_image_evidence_sha256": "8" * 64,
        "distinct_build_roots_verified": True,
        "byte_identical": True,
        "beta_gate_credit": False,
    }
    values.update(changes)
    return KernelReproducibilityEvidence(**values)


def test_binding_proves_strict_repro_outputs_came_from_one_locked_recipe(tmp_path):
    plan, lock = _plan_and_lock()
    build_a = _run(plan, lock)
    build_b = _run(plan, lock)
    repro = _repro(plan)

    evidence = bind_kernel_reproducibility_to_build_runs(plan, lock, repro, build_a, build_b)

    assert evidence.schema_version == 1
    assert evidence.profile_id == plan.profile_id
    assert evidence.kernel_plan_sha256 == plan.plan_sha256()
    assert evidence.toolchain_lock_sha256 == lock.lock_sha256()
    assert evidence.build_recipe_sha256 == build_a.build_recipe_sha256
    assert evidence.reproducible_environment_sha256 == build_a.reproducible_environment_sha256
    assert evidence.build_a_run_evidence_sha256 == build_a.evidence_sha256()
    assert evidence.build_b_run_evidence_sha256 == build_b.evidence_sha256()
    assert evidence.reproducibility_evidence_sha256 == repro.evidence_sha256()
    assert evidence.config_sha256 == repro.config_sha256
    assert evidence.image_sha256 == repro.image_sha256
    assert evidence.byte_identical is True
    assert evidence.distinct_build_roots_verified is True
    assert evidence.beta_gate_credit is False

    destination = tmp_path / "evidence" / "kernel-repro-binding.json"
    digest = write_kernel_reproducibility_binding_evidence(evidence, destination)
    assert digest == evidence.evidence_sha256()
    assert destination.read_text(encoding="utf-8") == evidence.canonical_json()
    with pytest.raises(KernelContractError, match="refusing to overwrite"):
        write_kernel_reproducibility_binding_evidence(evidence, destination)


def test_binding_rejects_recipe_or_environment_drift():
    plan, lock = _plan_and_lock()
    build_a = _run(plan, lock)
    repro = _repro(plan)

    with pytest.raises(KernelContractError, match="different canonical build recipes"):
        bind_kernel_reproducibility_to_build_runs(
            plan, lock, repro, build_a, _run(plan, lock, build_recipe_sha256="e" * 64)
        )
    with pytest.raises(KernelContractError, match="different reproducibility environments"):
        bind_kernel_reproducibility_to_build_runs(
            plan, lock, repro, build_a, _run(plan, lock, reproducible_environment_sha256="f" * 64)
        )


def test_binding_rejects_toolchain_or_output_substitution():
    plan, lock = _plan_and_lock()
    build_a = _run(plan, lock)
    repro = _repro(plan)

    with pytest.raises(KernelContractError, match="toolchain lock"):
        bind_kernel_reproducibility_to_build_runs(
            plan, lock, repro, build_a, _run(plan, lock, toolchain_lock_sha256="0" * 64)
        )
    with pytest.raises(KernelContractError, match="build B Image does not match"):
        bind_kernel_reproducibility_to_build_runs(
            plan,
            lock,
            replace(repro, build_b_image_evidence_sha256="e" * 64),
            build_a,
            _run(plan, lock, image_sha256="e" * 64, image_evidence_sha256="e" * 64),
        )


def test_binding_rejects_detached_per_build_verifier_evidence():
    plan, lock = _plan_and_lock()
    build_a = _run(plan, lock)
    build_b = _run(plan, lock)

    with pytest.raises(KernelContractError, match="build A config verifier evidence"):
        bind_kernel_reproducibility_to_build_runs(
            plan,
            lock,
            _repro(plan, build_a_config_evidence_sha256="a" * 64),
            build_a,
            build_b,
        )
    with pytest.raises(KernelContractError, match="build B Image verifier evidence"):
        bind_kernel_reproducibility_to_build_runs(
            plan,
            lock,
            _repro(plan, build_b_image_evidence_sha256="b" * 64),
            build_a,
            build_b,
        )


def test_binding_rejects_host_evidence_claiming_hardware_credit():
    plan, lock = _plan_and_lock()
    build_a = _run(plan, lock)
    repro = _repro(plan)

    with pytest.raises(KernelContractError, match="hardware/Beta credit"):
        bind_kernel_reproducibility_to_build_runs(
            plan, lock, repro, build_a, _run(plan, lock, beta_gate_credit=True)
        )
    with pytest.raises(KernelContractError, match="hardware/Beta credit"):
        bind_kernel_reproducibility_to_build_runs(
            plan, lock, replace(repro, beta_gate_credit=True), build_a, _run(plan, lock)
        )


def test_strict_evidence_loaders_reject_schema_field_injection(tmp_path):
    plan, lock = _plan_and_lock()
    run = _run(plan, lock)
    repro = _repro(plan)

    run_path = tmp_path / "run.json"
    run_path.write_text(run.canonical_json(), encoding="utf-8")
    assert load_kernel_build_run_evidence(run_path) == run

    repro_path = tmp_path / "repro.json"
    repro_path.write_text(repro.canonical_json(), encoding="utf-8")
    assert load_kernel_reproducibility_evidence(repro_path) == repro

    injected = json.loads(run.canonical_json())
    injected["unexpected"] = "data"
    run_path.write_text(json.dumps(injected), encoding="utf-8")
    with pytest.raises(KernelContractError, match="fields mismatch"):
        load_kernel_build_run_evidence(run_path)
