from dataclasses import replace
from types import SimpleNamespace

import pytest

import kaliphonestudio.rootfs_handoff_strategy_review as strategy
from kaliphonestudio.rootfs_handoff_strategy_review import (
    RootfsHandoffStrategyReviewError,
    RootfsHandoffStrategyReviewEvidence,
    RootfsHandoffStrategyReviewRecord,
    bind_rootfs_handoff_strategy_review,
    load_rootfs_handoff_strategy_review_evidence,
    parse_rootfs_handoff_strategy_review_record,
    write_rootfs_handoff_strategy_review_evidence,
)


def _digest(ch: str) -> str:
    return ch * 64


def _record(*, decision="accepted_for_trial_design", complete=True, role="userdata"):
    return RootfsHandoffStrategyReviewRecord(
        schema_version=1,
        review_policy="reversible-rootfs-handoff-strategy-review-v1",
        profile_id="oneplus/avicii",
        device_serial="SERIAL-STRATEGY-001",
        reviewer="strategy-reviewer",
        decision=decision,
        candidate_partition_role=role,
        staging_subpath="kaliphonestudio/rootfs-stage",
        required_free_bytes=900_000_000,
        rootfs_artifact_sha256=_digest("a"),
        recovery_plan_sha256=_digest("b"),
        exact_physical_chain_reviewed=complete,
        capacity_evidence_reviewed=complete,
        filesystem_encryption_reviewed=complete,
        rollback_plan_reviewed=complete,
        forbidden_partition_policy_reviewed=complete,
        no_raw_device_path_reviewed=complete,
        no_write_authorization_reviewed=complete,
        target_selected=False,
        storage_path_bound=False,
        trial_execution_allowed=False,
        write_authorized=False,
        phone_storage_written=False,
    )


def _chain(monkeypatch):
    for name in (
        "validate_physical_storage_discovery_evidence",
        "validate_physical_storage_review_evidence",
        "validate_physical_bringup_dossier_evidence",
        "validate_physical_bringup_dossier_review_evidence",
        "validate_physical_release_gate_audit_evidence",
    ):
        monkeypatch.setattr(strategy, name, lambda value: None)

    discovery = SimpleNamespace(
        profile_id="oneplus/avicii",
        device_serial="SERIAL-STRATEGY-001",
        firmware_build="AC2003_11_F.23",
        firmware_fingerprint="OnePlus/avicii/avicii:12/RKQ1/test:user/release-keys",
        partition_hint="userdata",
        forbidden_partitions=("boot", "vendor_boot", "dtbo", "vbmeta", "super", "metadata"),
        evidence_sha256=lambda: _digest("1"),
    )
    storage_review = SimpleNamespace(
        profile_id=discovery.profile_id,
        device_serial=discovery.device_serial,
        firmware_build=discovery.firmware_build,
        firmware_fingerprint=discovery.firmware_fingerprint,
        physical_storage_discovery_sha256=_digest("1"),
        accepted_for_strategy_design=True,
        further_strategy_review_required=True,
        rootfs_artifact_sha256=_digest("a"),
        rootfs_artifact_size=800_000_000,
        recovery_plan_sha256=_digest("b"),
        evidence_sha256=lambda: _digest("2"),
    )
    dossier = SimpleNamespace(
        profile_id=discovery.profile_id,
        device_serial=discovery.device_serial,
        firmware_build=discovery.firmware_build,
        firmware_fingerprint=discovery.firmware_fingerprint,
        rootfs_artifact_sha256=_digest("a"),
        storage_review_accepted_for_strategy_design=True,
        exact_file_set_verified=True,
        files=(
            SimpleNamespace(role="physical_storage_discovery", sha256=_digest("1")),
            SimpleNamespace(role="physical_storage_review", sha256=_digest("2")),
        ),
        evidence_sha256=lambda: _digest("3"),
    )
    dossier_review = SimpleNamespace(
        profile_id=discovery.profile_id,
        device_serial=discovery.device_serial,
        firmware_build=discovery.firmware_build,
        firmware_fingerprint=discovery.firmware_fingerprint,
        physical_bringup_dossier_sha256=_digest("3"),
        accepted_for_strategy_review=True,
        separate_strategy_review_required=True,
        evidence_sha256=lambda: _digest("4"),
    )
    audit = SimpleNamespace(
        profile_id=discovery.profile_id,
        device_serial=discovery.device_serial,
        firmware_build=discovery.firmware_build,
        firmware_fingerprint=discovery.firmware_fingerprint,
        physical_bringup_dossier_sha256=_digest("3"),
        dossier_review_sha256=_digest("4"),
        cross_campaign_context_verified=True,
        exact_files_verified=True,
        dossier_review_accepted_for_strategy_review=True,
        physical_gate_still_incomplete=True,
        target_selected=False,
        storage_path_bound=False,
        write_authorized=False,
        project_support_claim_authorized=False,
        persistent_write_performed=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_release_authorized=False,
        beta_gate_credit=False,
        evidence_sha256=lambda: _digest("5"),
    )
    return discovery, storage_review, dossier, dossier_review, audit


def _bind(monkeypatch, record=None):
    chain = _chain(monkeypatch)
    return bind_rootfs_handoff_strategy_review(
        *chain,
        record or _record(),
        review_record_sha256=_digest("c"),
        review_record_size=512,
        review_notes_sha256=_digest("d"),
        review_notes_size=256,
    )


def test_accepts_only_design_and_never_execution_or_release(monkeypatch):
    evidence = _bind(monkeypatch)
    assert evidence.strategy_design_accepted is True
    assert evidence.review_checks_complete is True
    assert evidence.manual_target_binding_required is True
    assert evidence.physical_gate_still_incomplete is True
    assert evidence.target_selected is False
    assert evidence.storage_path_bound is False
    assert evidence.trial_execution_allowed is False
    assert evidence.write_authorized is False
    assert evidence.handoff_ready is False
    assert evidence.persistent_write_performed is False
    assert evidence.phone_storage_written is False
    assert evidence.hardware_verified is False
    assert evidence.beta_release_authorized is False
    assert evidence.beta_gate_credit is False


def test_rejects_detached_storage_review(monkeypatch):
    discovery, storage_review, dossier, dossier_review, audit = _chain(monkeypatch)
    storage_review.physical_storage_discovery_sha256 = _digest("f")
    with pytest.raises(RootfsHandoffStrategyReviewError, match="detached"):
        bind_rootfs_handoff_strategy_review(
            discovery, storage_review, dossier, dossier_review, audit, _record(),
            review_record_sha256=_digest("c"), review_record_size=1,
            review_notes_sha256=_digest("d"), review_notes_size=1,
        )


def test_rejects_system_partition_or_profile_hint_drift(monkeypatch):
    with pytest.raises(RootfsHandoffStrategyReviewError, match="profile-driven discovery hint"):
        _bind(monkeypatch, _record(role="super"))


def test_rejects_incomplete_acceptance(monkeypatch):
    with pytest.raises(RootfsHandoffStrategyReviewError, match="every mandatory review check"):
        _bind(monkeypatch, _record(complete=False))


def test_rejects_raw_or_absolute_staging_paths():
    raw = _record(decision="rejected").__dict__.copy()
    raw["staging_subpath"] = "/dev/block/sda"
    with pytest.raises(RootfsHandoffStrategyReviewError, match="absolute/raw device path"):
        parse_rootfs_handoff_strategy_review_record(raw)
    raw["staging_subpath"] = "C:\\raw\\path"
    with pytest.raises(RootfsHandoffStrategyReviewError, match="absolute/raw device path"):
        parse_rootfs_handoff_strategy_review_record(raw)


def test_evidence_round_trip_is_canonical_and_immutable(monkeypatch, tmp_path):
    evidence = _bind(monkeypatch)
    out = tmp_path / "strategy-review.json"
    digest = write_rootfs_handoff_strategy_review_evidence(evidence, out)
    assert digest == evidence.evidence_sha256()
    loaded = load_rootfs_handoff_strategy_review_evidence(out)
    assert loaded == evidence
    assert out.read_text(encoding="utf-8") == evidence.canonical_json()
    with pytest.raises(RootfsHandoffStrategyReviewError, match="overwrite"):
        write_rootfs_handoff_strategy_review_evidence(evidence, out)


def test_evidence_validator_rejects_any_promotion(monkeypatch):
    evidence = _bind(monkeypatch)
    for field in (
        "target_selected",
        "storage_path_bound",
        "trial_execution_allowed",
        "write_authorized",
        "handoff_ready",
        "persistent_write_performed",
        "phone_storage_written",
        "hardware_verified",
        "beta_release_authorized",
        "beta_gate_credit",
    ):
        promoted = replace(evidence, **{field: True})
        with pytest.raises(RootfsHandoffStrategyReviewError, match=field):
            strategy.validate_rootfs_handoff_strategy_review_evidence(promoted)
