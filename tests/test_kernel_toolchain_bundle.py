from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from kaliphonestudio.kernel_contract import KernelContractError, create_kernel_build_plan
from kaliphonestudio.kernel_toolchain import (
    KernelToolchainSourceEvidence,
    MaterializedKernelToolchainEvidence,
    load_kernel_toolchain_lock,
)
from kaliphonestudio.kernel_toolchain_binding import KernelToolchainBindingEvidence
from kaliphonestudio.kernel_toolchain_bundle import create_kernel_toolchain_candidate_evidence
from kaliphonestudio.profiles import get_profile


ROOT = Path(__file__).resolve().parents[1]


def fixtures():
    plan = create_kernel_build_plan(get_profile(ROOT / "devices", "oneplus/avicii"))
    lock = load_kernel_toolchain_lock(ROOT / "tools" / "kernel-toolchain-lock.json")
    source = KernelToolchainSourceEvidence(
        schema_version=1,
        lock_sha256=lock.lock_sha256(),
        source_url=lock.source_url,
        source_commit=lock.source_commit,
        subtree=lock.subtree,
        tree_sha1=lock.tree_sha1,
        bin_tree_sha1=lock.bin_tree_sha1,
        android_version_blob_sha1=lock.android_version_blob_sha1,
        manifest_blob_sha1=lock.manifest_blob_sha1,
        android_version=lock.android_version,
        clang_revision=lock.clang_revision,
        build_id=lock.build_id,
        llvm_project_commit=lock.llvm_project_commit,
        beta_gate_credit=False,
    )
    binding = KernelToolchainBindingEvidence(
        schema_version=1,
        profile_id=plan.profile_id,
        kernel_plan_sha256=plan.plan_sha256(),
        kernel_source_commit=plan.source_commit,
        toolchain_lock_sha256=lock.lock_sha256(),
        clang_revision=lock.clang_revision,
        build_config_path="build.config.common",
        build_config_sha256="a" * 64,
        llvm_mode="1",
        clang_prebuilt_bin="prebuilts-master/clang/host/linux-x86/clang-r416183b/bin",
        beta_gate_credit=False,
    )
    materialized = MaterializedKernelToolchainEvidence(
        schema_version=1,
        lock_sha256=lock.lock_sha256(),
        clang_sha256="b" * 64,
        clang_size=123456,
        android_version_sha256="c" * 64,
        clang_banner_verified=True,
        beta_gate_credit=False,
    )
    return plan, lock, source, binding, materialized


def test_bundle_binds_exact_source_checkout_and_compiler_bytes():
    plan, lock, source, binding, materialized = fixtures()
    evidence = create_kernel_toolchain_candidate_evidence(
        plan, lock, source, binding, materialized
    )
    assert evidence.profile_id == "oneplus/avicii"
    assert evidence.kernel_plan_sha256 == plan.plan_sha256()
    assert evidence.toolchain_lock_sha256 == lock.lock_sha256()
    assert evidence.source_evidence_sha256 == source.evidence_sha256()
    assert evidence.binding_evidence_sha256 == binding.evidence_sha256()
    assert evidence.materialized_evidence_sha256 == materialized.evidence_sha256()
    assert evidence.clang_revision == "r416183b"
    assert evidence.clang_sha256 == "b" * 64
    assert evidence.clang_size == 123456
    assert evidence.build_config_sha256 == "a" * 64
    assert evidence.beta_gate_credit is False
    assert len(evidence.evidence_sha256()) == 64


def test_bundle_rejects_source_lock_substitution():
    plan, lock, source, binding, materialized = fixtures()
    with pytest.raises(KernelContractError, match="source evidence does not match"):
        create_kernel_toolchain_candidate_evidence(
            plan, lock, replace(source, lock_sha256="0" * 64), binding, materialized
        )


def test_bundle_rejects_kernel_plan_substitution():
    plan, lock, source, binding, materialized = fixtures()
    with pytest.raises(KernelContractError, match="kernel plan digest"):
        create_kernel_toolchain_candidate_evidence(
            plan,
            lock,
            source,
            replace(binding, kernel_plan_sha256="0" * 64),
            materialized,
        )


def test_bundle_rejects_unverified_materialized_compiler():
    plan, lock, source, binding, materialized = fixtures()
    with pytest.raises(KernelContractError, match="banner is not verified"):
        create_kernel_toolchain_candidate_evidence(
            plan,
            lock,
            source,
            binding,
            replace(materialized, clang_banner_verified=False),
        )


def test_bundle_rejects_source_object_drift_even_with_same_lock_digest():
    plan, lock, source, binding, materialized = fixtures()
    with pytest.raises(KernelContractError, match="subtree tree drifted"):
        create_kernel_toolchain_candidate_evidence(
            plan,
            lock,
            replace(source, tree_sha1="0" * 40),
            binding,
            materialized,
        )


def test_bundle_rejects_any_host_evidence_claiming_beta_credit():
    plan, lock, source, binding, materialized = fixtures()
    with pytest.raises(KernelContractError, match="cannot claim hardware Beta credit"):
        create_kernel_toolchain_candidate_evidence(
            plan,
            lock,
            source,
            replace(binding, beta_gate_credit=True),
            materialized,
        )
