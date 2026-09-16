"""Canonical binding of kernel plans to locked compiler evidence.

A kernel build is not adequately identified by an Image hash alone: the exact
compiler source identity, materialized compiler bytes and kernel checkout build
configuration must all agree with the approved kernel plan.  This host-side
bundle keeps that evidence together without granting hardware/Beta credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import re

from .kernel_contract import KernelBuildPlan, KernelContractError
from .kernel_toolchain import (
    KernelToolchainLock,
    KernelToolchainSourceEvidence,
    MaterializedKernelToolchainEvidence,
)
from .kernel_toolchain_binding import KernelToolchainBindingEvidence


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class KernelToolchainCandidateEvidence:
    schema_version: int
    profile_id: str
    kernel_plan_sha256: str
    kernel_source_commit: str
    toolchain_lock_sha256: str
    source_evidence_sha256: str
    binding_evidence_sha256: str
    materialized_evidence_sha256: str
    clang_revision: str
    clang_sha256: str
    clang_size: int
    build_config_sha256: str
    clang_prebuilt_bin: str
    beta_gate_credit: bool = False

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _require_sha256(value: str, label: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise KernelContractError(f"invalid {label}")


def create_kernel_toolchain_candidate_evidence(
    plan: KernelBuildPlan,
    lock: KernelToolchainLock,
    source: KernelToolchainSourceEvidence,
    binding: KernelToolchainBindingEvidence,
    materialized: MaterializedKernelToolchainEvidence,
) -> KernelToolchainCandidateEvidence:
    """Bind source, checkout selection and concrete compiler bytes to one plan."""
    if plan.schema_version != 1:
        raise KernelContractError("unsupported kernel build plan schema")
    if lock.schema_version != 1:
        raise KernelContractError("unsupported kernel toolchain lock schema")
    if source.schema_version != 1:
        raise KernelContractError("unsupported kernel toolchain source evidence schema")
    if binding.schema_version != 1:
        raise KernelContractError("unsupported kernel toolchain binding evidence schema")
    if materialized.schema_version != 1:
        raise KernelContractError("unsupported materialized kernel toolchain evidence schema")

    lock_digest = lock.lock_sha256()
    plan_digest = plan.plan_sha256()
    for digest, label in (
        (lock_digest, "kernel toolchain lock SHA-256"),
        (plan_digest, "kernel plan SHA-256"),
        (source.evidence_sha256(), "kernel toolchain source evidence SHA-256"),
        (binding.evidence_sha256(), "kernel toolchain binding evidence SHA-256"),
        (materialized.evidence_sha256(), "materialized kernel toolchain evidence SHA-256"),
        (materialized.clang_sha256, "clang SHA-256"),
        (binding.build_config_sha256, "kernel build config SHA-256"),
        (materialized.android_version_sha256, "AndroidVersion SHA-256"),
    ):
        _require_sha256(digest, label)

    if source.lock_sha256 != lock_digest:
        raise KernelContractError("toolchain source evidence does not match the selected lock")
    if materialized.lock_sha256 != lock_digest:
        raise KernelContractError("materialized compiler evidence does not match the selected lock")
    if binding.toolchain_lock_sha256 != lock_digest:
        raise KernelContractError("kernel/compiler binding does not match the selected lock")
    if binding.profile_id != plan.profile_id:
        raise KernelContractError("kernel/compiler binding profile does not match kernel plan")
    if binding.kernel_plan_sha256 != plan_digest:
        raise KernelContractError("kernel/compiler binding does not match kernel plan digest")
    if binding.kernel_source_commit != plan.source_commit:
        raise KernelContractError("kernel/compiler binding source commit does not match kernel plan")

    expected_source_values = (
        (source.source_url, lock.source_url, "source URL"),
        (source.source_commit, lock.source_commit, "source commit"),
        (source.subtree, lock.subtree, "subtree"),
        (source.tree_sha1, lock.tree_sha1, "subtree tree"),
        (source.bin_tree_sha1, lock.bin_tree_sha1, "bin tree"),
        (source.android_version_blob_sha1, lock.android_version_blob_sha1, "AndroidVersion blob"),
        (source.manifest_blob_sha1, lock.manifest_blob_sha1, "manifest blob"),
        (source.android_version, lock.android_version, "Android version"),
        (source.clang_revision, lock.clang_revision, "clang revision"),
        (source.build_id, lock.build_id, "build id"),
        (source.llvm_project_commit, lock.llvm_project_commit, "LLVM project commit"),
    )
    for actual, expected, label in expected_source_values:
        if actual != expected:
            raise KernelContractError(f"kernel toolchain source evidence {label} drifted")

    if binding.clang_revision != lock.clang_revision:
        raise KernelContractError("kernel/compiler binding clang revision drifted")
    if materialized.clang_banner_verified is not True:
        raise KernelContractError("materialized clang banner is not verified")
    if not isinstance(materialized.clang_size, int) or isinstance(materialized.clang_size, bool) or materialized.clang_size <= 0:
        raise KernelContractError("materialized clang size is invalid")
    if source.beta_gate_credit is not False or binding.beta_gate_credit is not False or materialized.beta_gate_credit is not False:
        raise KernelContractError("host toolchain evidence cannot claim hardware Beta credit")
    if lock.beta_gate_credit is not False:
        raise KernelContractError("kernel toolchain lock cannot claim hardware Beta credit")

    return KernelToolchainCandidateEvidence(
        schema_version=1,
        profile_id=plan.profile_id,
        kernel_plan_sha256=plan_digest,
        kernel_source_commit=plan.source_commit,
        toolchain_lock_sha256=lock_digest,
        source_evidence_sha256=source.evidence_sha256(),
        binding_evidence_sha256=binding.evidence_sha256(),
        materialized_evidence_sha256=materialized.evidence_sha256(),
        clang_revision=lock.clang_revision,
        clang_sha256=materialized.clang_sha256,
        clang_size=materialized.clang_size,
        build_config_sha256=binding.build_config_sha256,
        clang_prebuilt_bin=binding.clang_prebuilt_bin,
        beta_gate_credit=False,
    )
