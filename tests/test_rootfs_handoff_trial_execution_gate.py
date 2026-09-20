from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

import kaliphonestudio.rootfs_handoff_trial_execution_gate as gate_module
from kaliphonestudio.rootfs_handoff_fresh_revalidation import RootfsHandoffFreshRevalidationEvidence
from kaliphonestudio.rootfs_handoff_trial_execution_gate import (
    RootfsHandoffTrialExecutionGateError,
    build_rootfs_handoff_trial_execution_gate,
    load_rootfs_handoff_trial_execution_gate_evidence,
    write_rootfs_handoff_trial_execution_gate_evidence,
)
from kaliphonestudio.rootfs_handoff_trial_plan import RootfsHandoffTrialPlan
from kaliphonestudio.rootfs_handoff_trial_preflight import RootfsHandoffTrialPreflightEvidence


def _sha(ch: str) -> str:
    return ch * 64


def _revalidation(*, discovery: str, report: str, free_bytes: int = 10_000_000_000) -> RootfsHandoffFreshRevalidationEvidence:
    return RootfsHandoffFreshRevalidationEvidence(
        schema_version=1,
        revalidation_policy="reversible-rootfs-handoff-fresh-target-revalidation-v1",
        profile_id="oneplus/avicii",
        device_serial="SERIAL123",
        firmware_build="AC2003_11.F.18",
        firmware_fingerprint="oneplus/avicii/ac2003:12/example:user/release-keys",
        target_binding_sha256=_sha("a"),
        previous_physical_storage_discovery_sha256=_sha("b"),
        fresh_physical_storage_discovery_sha256=discovery,
        fresh_physical_storage_discovery_report_sha256=report,
        fresh_physical_storage_discovery_report_size=4096,
        candidate_partition_role="userdata",
        observed_kernel_name="sda",
        observed_filesystem="ext4",
        observed_encryption_state="unlocked",
        observed_free_bytes=free_bytes,
        required_free_bytes=4_000_000_000,
        staging_subpath="kaliphonestudio/rootfs",
        rootfs_artifact_sha256=_sha("7"),
        rootfs_artifact_size=1024,
        recovery_plan_sha256=_sha("8"),
        fresh_capture_chain_distinct=True,
        exact_logical_identity_matches=True,
        fresh_filesystem_identity_matches=True,
        fresh_encryption_state_acceptable=True,
        fresh_capacity_sufficient=True,
        recovery_plan_matches=True,
        fresh_device_revalidated=True,
        ready_for_separate_manual_trial_authorization=True,
        manual_trial_authorization_required=True,
        physical_gate_still_incomplete=True,
        raw_device_path_bound=False,
        mount_target_bound=False,
        trial_execution_allowed=False,
        write_authorized=False,
        handoff_ready=False,
        persistent_write_performed=False,
        phone_storage_written=False,
        storage_verified=False,
        recovery_verified=False,
        hardware_verified=False,
        beta_release_authorized=False,
        beta_gate_credit=False,
    )


def _chain() -> tuple[
    RootfsHandoffTrialPlan,
    RootfsHandoffTrialPreflightEvidence,
    RootfsHandoffFreshRevalidationEvidence,
    RootfsHandoffFreshRevalidationEvidence,
]:
    authorized = _revalidation(discovery=_sha("c"), report=_sha("d"))
    execution = _revalidation(discovery=_sha("e"), report=_sha("f"), free_bytes=11_000_000_000)
    plan = RootfsHandoffTrialPlan(
        schema_version=1,
        plan_policy="rootfs-handoff-interactive-trial-plan-v1",
        profile_id="oneplus/avicii",
        device_serial="SERIAL123",
        firmware_build="AC2003_11.F.18",
        firmware_fingerprint="oneplus/avicii/ac2003:12/example:user/release-keys",
        trial_authorization_sha256=_sha("9"),
        target_binding_sha256=_sha("a"),
        fresh_revalidation_sha256=authorized.evidence_sha256(),
        candidate_partition_role="userdata",
        observed_kernel_name="sda",
        observed_filesystem="ext4",
        observed_encryption_state="unlocked",
        observed_free_bytes=10_000_000_000,
        required_free_bytes=4_000_000_000,
        staging_subpath="kaliphonestudio/rootfs",
        rootfs_artifact_sha256=_sha("7"),
        rootfs_artifact_size=1024,
        recovery_plan_sha256=_sha("8"),
        exact_authorization_chain_bound=True,
        live_device_identity_recheck_required=True,
        live_firmware_recheck_required=True,
        live_target_identity_recheck_required=True,
        live_filesystem_encryption_capacity_recheck_required=True,
        rootfs_local_hash_recheck_required=True,
        recovery_readiness_recheck_required=True,
        explicit_operator_confirmation_required=True,
        write_scope_confirmation_required=True,
        plan_ready_for_later_interactive_executor=True,
        physical_gate_still_incomplete=True,
        raw_device_path_bound=False,
        mount_target_bound=False,
        trial_execution_allowed=False,
        persistent_write_authorized=False,
        persistent_write_performed=False,
        phone_storage_written=False,
        storage_verified=False,
        recovery_verified=False,
        hardware_verified=False,
        beta_release_authorized=False,
        beta_gate_credit=False,
    )
    preflight = RootfsHandoffTrialPreflightEvidence(
        schema_version=1,
        preflight_policy="rootfs-handoff-local-rootfs-preflight-v1",
        profile_id=plan.profile_id,
        device_serial=plan.device_serial,
        firmware_build=plan.firmware_build,
        firmware_fingerprint=plan.firmware_fingerprint,
        trial_plan_sha256=plan.evidence_sha256(),
        trial_authorization_sha256=plan.trial_authorization_sha256,
        target_binding_sha256=plan.target_binding_sha256,
        fresh_revalidation_sha256=plan.fresh_revalidation_sha256,
        candidate_partition_role=plan.candidate_partition_role,
        observed_kernel_name=plan.observed_kernel_name,
        observed_filesystem=plan.observed_filesystem,
        observed_encryption_state=plan.observed_encryption_state,
        observed_free_bytes=plan.observed_free_bytes,
        required_free_bytes=plan.required_free_bytes,
        staging_subpath=plan.staging_subpath,
        rootfs_artifact_sha256=plan.rootfs_artifact_sha256,
        rootfs_artifact_size=plan.rootfs_artifact_size,
        recovery_plan_sha256=plan.recovery_plan_sha256,
        exact_trial_plan_bound=True,
        local_rootfs_exact_bytes_verified=True,
        live_device_identity_recheck_required=True,
        live_firmware_recheck_required=True,
        live_target_identity_recheck_required=True,
        live_filesystem_encryption_capacity_recheck_required=True,
        recovery_readiness_recheck_required=True,
        explicit_operator_confirmation_required=True,
        write_scope_confirmation_required=True,
        interactive_executor_still_required=True,
        physical_gate_still_incomplete=True,
        physical_interaction_performed=False,
        external_device_command_executed=False,
        raw_device_path_bound=False,
        mount_target_bound=False,
        trial_execution_allowed=False,
        persistent_write_authorized=False,
        persistent_write_performed=False,
        phone_storage_written=False,
        storage_verified=False,
        recovery_verified=False,
        hardware_verified=False,
        beta_release_authorized=False,
        beta_gate_credit=False,
    )
    return plan, preflight, authorized, execution


def _patch_chain(monkeypatch: pytest.MonkeyPatch, plan, preflight, authorized, execution) -> None:
    monkeypatch.setattr(gate_module, "load_rootfs_handoff_trial_plan", lambda _path: plan)
    monkeypatch.setattr(gate_module, "load_rootfs_handoff_trial_preflight_evidence", lambda _path: preflight)
    values = iter((authorized, execution))
    monkeypatch.setattr(gate_module, "load_rootfs_handoff_fresh_revalidation_evidence", lambda _path: next(values))


def test_execution_gate_accepts_second_distinct_exact_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    plan, preflight, authorized, execution = _chain()
    _patch_chain(monkeypatch, plan, preflight, authorized, execution)

    evidence = build_rootfs_handoff_trial_execution_gate(Path("plan"), Path("preflight"), Path("auth"), Path("execution"))

    assert evidence.execution_gate_passed is True
    assert evidence.distinct_execution_capture_bound is True
    assert evidence.execution_storage_discovery_sha256 == execution.fresh_physical_storage_discovery_sha256
    assert evidence.observed_free_bytes == execution.observed_free_bytes
    assert evidence.explicit_operator_confirmation_required is True
    assert evidence.raw_device_path_resolution_required is True
    assert evidence.interactive_writer_required is True
    assert evidence.trial_execution_allowed is False
    assert evidence.persistent_write_authorized is False
    assert evidence.phone_storage_written is False
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False


def test_execution_gate_rejects_reused_authorization_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    plan, preflight, authorized, execution = _chain()
    execution = replace(execution, fresh_physical_storage_discovery_sha256=authorized.fresh_physical_storage_discovery_sha256)
    _patch_chain(monkeypatch, plan, preflight, authorized, execution)

    with pytest.raises(RootfsHandoffTrialExecutionGateError, match="second distinct storage capture"):
        build_rootfs_handoff_trial_execution_gate(Path("plan"), Path("preflight"), Path("auth"), Path("execution"))


def test_execution_gate_rejects_live_firmware_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    plan, preflight, authorized, execution = _chain()
    execution = replace(execution, firmware_build="DIFFERENT_BUILD")
    _patch_chain(monkeypatch, plan, preflight, authorized, execution)

    with pytest.raises(RootfsHandoffTrialExecutionGateError, match="execution fresh revalidation firmware build drifted"):
        build_rootfs_handoff_trial_execution_gate(Path("plan"), Path("preflight"), Path("auth"), Path("execution"))


def test_execution_gate_rejects_detached_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    plan, preflight, authorized, execution = _chain()
    preflight = replace(preflight, trial_plan_sha256=_sha("0"))
    _patch_chain(monkeypatch, plan, preflight, authorized, execution)

    with pytest.raises(RootfsHandoffTrialExecutionGateError, match="preflight is detached"):
        build_rootfs_handoff_trial_execution_gate(Path("plan"), Path("preflight"), Path("auth"), Path("execution"))


def test_execution_gate_evidence_roundtrip_is_canonical_and_create_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plan, preflight, authorized, execution = _chain()
    _patch_chain(monkeypatch, plan, preflight, authorized, execution)
    evidence = build_rootfs_handoff_trial_execution_gate(Path("plan"), Path("preflight"), Path("auth"), Path("execution"))

    out = tmp_path / "execution-gate.json"
    digest = write_rootfs_handoff_trial_execution_gate_evidence(evidence, out)
    loaded = load_rootfs_handoff_trial_execution_gate_evidence(out)

    assert digest == evidence.evidence_sha256()
    assert loaded == evidence
    assert out.read_bytes() == evidence.canonical_json().encode("utf-8")
    with pytest.raises(RootfsHandoffTrialExecutionGateError, match="refusing to overwrite"):
        write_rootfs_handoff_trial_execution_gate_evidence(evidence, out)
