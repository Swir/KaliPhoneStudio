from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import kaliphonestudio.physical_bringup_session as session
from kaliphonestudio.physical_bringup_session import (
    PhysicalBringupSessionError,
    bind_physical_bringup_session,
    load_physical_bringup_session_evidence,
    validate_physical_bringup_session_evidence,
    write_physical_bringup_session_evidence,
)


def _digest(char: str) -> str:
    return char * 64


def _item(digest: str, **kwargs):
    obj = SimpleNamespace(**kwargs)
    obj.evidence_sha256 = lambda: digest
    return obj


def _chain(*, accepted: bool = True, early: bool = False):
    profile = "oneplus/avicii"
    serial = "SERIAL123"
    transcript = _digest("a")
    probe = _digest("b")
    gate_sha = _digest("c")
    observation_sha = _digest("d")
    diagnostics_sha = _digest("e")
    functional_sha = _digest("f")
    discovery_sha = _digest("1")
    review_sha = _digest("2")
    rootfs = _digest("3")
    authority = _digest("4")
    handoff = _digest("5")
    contract = _digest("6")
    report = _digest("7")
    recovery = _digest("8")
    manifest = _digest("9")
    authority_bundle = _digest("0")

    gate = _item(
        gate_sha,
        profile_id=profile,
        device_serial=serial,
        firmware_build="OxygenOS-test-build",
        firmware_fingerprint="oneplus/avicii/test:user/release-keys",
        rootfs_artifact_sha256=rootfs,
        first_boot_manifest_sha256=manifest,
        first_boot_authority_bundle_sha256=authority_bundle,
    )
    observation = _item(
        observation_sha,
        profile_id=profile,
        device_serial=serial,
        transcript_sha256=transcript,
        rescue_probe_id=probe,
    )
    diagnostics = _item(
        diagnostics_sha,
        profile_id=profile,
        device_serial=serial,
        physical_boot_observation_sha256=observation_sha,
        transcript_sha256=transcript,
        rescue_probe_id=probe,
    )
    functional = _item(
        functional_sha,
        profile_id=profile,
        device_serial=serial,
        physical_boot_observation_sha256=observation_sha,
        rescue_diagnostics_sha256=diagnostics_sha,
        transcript_sha256=transcript,
        rescue_probe_id=probe,
    )
    discovery = _item(
        discovery_sha,
        profile_id=profile,
        device_serial=serial,
        firmware_build=gate.firmware_build,
        firmware_fingerprint=gate.firmware_fingerprint,
        physical_candidate_gate_sha256=gate_sha,
        rescue_diagnostics_sha256=diagnostics_sha,
        rescue_functional_probe_sha256=functional_sha,
        rootfs_handoff_assessment_sha256=handoff,
        rootfs_handoff_contract_sha256=contract,
        rootfs_authority_sha256=authority,
        rootfs_artifact_sha256=rootfs,
        rootfs_artifact_size=137460600,
        transcript_sha256=transcript,
        rescue_probe_id=probe,
        discovery_report_sha256=report,
        recovery_plan_sha256=recovery,
    )
    review = _item(
        review_sha,
        profile_id=profile,
        device_serial=serial,
        firmware_build=gate.firmware_build,
        firmware_fingerprint=gate.firmware_fingerprint,
        physical_storage_discovery_sha256=discovery_sha,
        physical_candidate_gate_sha256=gate_sha,
        rescue_diagnostics_sha256=diagnostics_sha,
        rescue_functional_probe_sha256=functional_sha,
        rootfs_handoff_assessment_sha256=handoff,
        rootfs_handoff_contract_sha256=contract,
        rootfs_authority_sha256=authority,
        rootfs_artifact_sha256=rootfs,
        rootfs_artifact_size=137460600,
        transcript_sha256=transcript,
        rescue_probe_id=probe,
        discovery_report_sha256=report,
        recovery_plan_sha256=recovery,
        review_record_sha256=_digest("a"),
        review_notes_sha256=_digest("b"),
        review_recorded=True,
        accepted_for_strategy_design=accepted,
    )
    early_evidence = None
    if early:
        early_evidence = _item(
            _digest("e"),
            profile_id=profile,
            device_serial=serial,
            physical_candidate_gate_sha256=gate_sha,
            first_boot_manifest_sha256=manifest,
            first_boot_authority_bundle_sha256=authority_bundle,
            rootfs_authority_sha256=authority,
            rootfs_artifact_sha256=rootfs,
            transcript_sha256=_digest("f"),
            probe_id=_digest("d"),
        )
    return gate, observation, diagnostics, functional, discovery, review, early_evidence


@pytest.fixture(autouse=True)
def _skip_upstream_revalidation(monkeypatch: pytest.MonkeyPatch) -> None:
    # The upstream evidence types have their own focused contract tests.  These
    # tests isolate the new cross-layer binding invariants and output safety.
    monkeypatch.setattr(session, "_validate_inputs", lambda *args, **kwargs: None)


def test_exact_chain_binds_without_promoting_storage_or_beta() -> None:
    gate, observation, diagnostics, functional, discovery, review, _early = _chain()
    evidence = bind_physical_bringup_session(
        gate, observation, diagnostics, functional, discovery, review
    )
    assert evidence.rescue_chain_complete is True
    assert evidence.storage_discovery_chain_complete is True
    assert evidence.storage_review_recorded is True
    assert evidence.storage_review_accepted_for_strategy_design is True
    assert evidence.kali_early_userspace_signal_present is False
    assert evidence.target_selected is False
    assert evidence.storage_path_bound is False
    assert evidence.write_authorized is False
    assert evidence.handoff_ready is False
    assert evidence.storage_verified is False
    assert evidence.phone_storage_written is False
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False
    validate_physical_bringup_session_evidence(evidence)


def test_rejected_manual_review_is_bound_without_becoming_strategy_acceptance() -> None:
    gate, observation, diagnostics, functional, discovery, review, _early = _chain(accepted=False)
    evidence = bind_physical_bringup_session(
        gate, observation, diagnostics, functional, discovery, review
    )
    assert evidence.storage_review_recorded is True
    assert evidence.storage_review_accepted_for_strategy_design is False
    assert evidence.write_authorized is False


def test_detached_diagnostics_are_rejected() -> None:
    gate, observation, diagnostics, functional, discovery, review, _early = _chain()
    functional.rescue_diagnostics_sha256 = _digest("0")
    with pytest.raises(PhysicalBringupSessionError, match="functional probes are detached"):
        bind_physical_bringup_session(gate, observation, diagnostics, functional, discovery, review)


def test_detached_review_is_rejected() -> None:
    gate, observation, diagnostics, functional, discovery, review, _early = _chain()
    review.physical_storage_discovery_sha256 = _digest("0")
    with pytest.raises(PhysicalBringupSessionError, match="storage review is detached"):
        bind_physical_bringup_session(gate, observation, diagnostics, functional, discovery, review)


def test_transcript_or_probe_drift_is_rejected() -> None:
    gate, observation, diagnostics, functional, discovery, review, _early = _chain()
    discovery.transcript_sha256 = _digest("0")
    review.transcript_sha256 = discovery.transcript_sha256
    with pytest.raises(PhysicalBringupSessionError, match="transcript identity drifted"):
        bind_physical_bringup_session(gate, observation, diagnostics, functional, discovery, review)


def test_optional_kali_early_userspace_is_cross_bound_but_not_verified() -> None:
    gate, observation, diagnostics, functional, discovery, review, early = _chain(early=True)
    evidence = bind_physical_bringup_session(
        gate,
        observation,
        diagnostics,
        functional,
        discovery,
        review,
        early_userspace=early,
    )
    assert evidence.kali_early_userspace_signal_present is True
    assert evidence.kali_early_userspace_evidence_sha256 == early.evidence_sha256()
    assert evidence.kali_early_userspace_verified is False
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False


def test_optional_kali_rootfs_drift_is_rejected() -> None:
    gate, observation, diagnostics, functional, discovery, review, early = _chain(early=True)
    early.rootfs_artifact_sha256 = _digest("0")
    with pytest.raises(PhysicalBringupSessionError, match="rootfs artifact differs"):
        bind_physical_bringup_session(
            gate,
            observation,
            diagnostics,
            functional,
            discovery,
            review,
            early_userspace=early,
        )


def test_validator_rejects_any_write_or_hardware_promotion() -> None:
    gate, observation, diagnostics, functional, discovery, review, _early = _chain()
    evidence = bind_physical_bringup_session(
        gate, observation, diagnostics, functional, discovery, review
    )
    for field in (
        "target_selected",
        "storage_path_bound",
        "write_authorized",
        "handoff_ready",
        "storage_verified",
        "charging_battery_verified",
        "display_touch_verified",
        "recovery_verified",
        "kali_early_userspace_verified",
        "phone_storage_written",
        "hardware_verified",
        "beta_gate_credit",
    ):
        with pytest.raises(PhysicalBringupSessionError, match="unsupported"):
            validate_physical_bringup_session_evidence(replace(evidence, **{field: True}))


def test_optional_identity_requires_signal_flag() -> None:
    gate, observation, diagnostics, functional, discovery, review, _early = _chain()
    evidence = bind_physical_bringup_session(
        gate, observation, diagnostics, functional, discovery, review
    )
    with pytest.raises(PhysicalBringupSessionError, match="cannot be present"):
        validate_physical_bringup_session_evidence(
            replace(evidence, kali_early_userspace_probe_id=_digest("f"))
        )


def test_write_load_round_trip_and_refuse_overwrite(tmp_path: Path) -> None:
    gate, observation, diagnostics, functional, discovery, review, _early = _chain()
    evidence = bind_physical_bringup_session(
        gate, observation, diagnostics, functional, discovery, review
    )
    destination = tmp_path / "session.json"
    digest = write_physical_bringup_session_evidence(evidence, destination)
    assert digest == evidence.evidence_sha256()
    assert load_physical_bringup_session_evidence(destination) == evidence
    with pytest.raises(PhysicalBringupSessionError, match="refusing to overwrite"):
        write_physical_bringup_session_evidence(evidence, destination)
