from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import pytest

from kaliphonestudio.physical_storage_discovery import PhysicalStorageDiscoveryEvidence
from kaliphonestudio.physical_storage_review import (
    PhysicalStorageReviewError,
    bind_physical_storage_review,
    load_physical_storage_review_evidence,
    load_physical_storage_review_record,
    parse_physical_storage_review_record,
    record_physical_storage_review,
    validate_physical_storage_review_evidence,
    write_physical_storage_review_evidence,
)

D = "11" * 32
E = "22" * 32
F = "33" * 32
G = "44" * 32
H = "55" * 32
I = "66" * 32
J = "77" * 32
K = "88" * 32
L = "99" * 32
M = "aa" * 32
N = "bb" * 32
O = "cc" * 32


def _discovery(*, ready: bool = True) -> PhysicalStorageDiscoveryEvidence:
    common = ready
    return PhysicalStorageDiscoveryEvidence(
        schema_version=1,
        profile_id="oneplus/avicii",
        device_serial="SERIAL123",
        firmware_build="AC2003_11.F.17",
        firmware_fingerprint="OnePlus/avicii/avicii:12/RKQ1/build:user/release-keys",
        rootfs_handoff_assessment_sha256=D,
        rootfs_handoff_contract_sha256=E,
        physical_candidate_gate_sha256=F,
        rootfs_authority_sha256=G,
        rootfs_artifact_sha256=H,
        rootfs_artifact_size=137460600,
        rescue_diagnostics_sha256=I,
        rescue_functional_probe_sha256=J,
        transcript_sha256=K,
        rescue_probe_id=L,
        discovery_report_sha256=M,
        discovery_report_size=1234,
        recovery_plan_sha256=N,
        recovery_plan_size=512,
        storage_bus="ufs",
        partition_hint="userdata",
        expected_filesystems=("f2fs",),
        expected_encryption_features=("fileencryption=ice", "wrappedkey"),
        forbidden_partitions=("boot", "metadata", "super", "system", "userdata_a"),
        block_device_count=1,
        filesystem_observation_count=1,
        encryption_observation_count=1,
        free_space_observation_count=1,
        topology_bound_to_rescue_diagnostics=common,
        storage_bus_signal_observed=common,
        filesystem_identity_observed=common,
        expected_filesystem_observed=common,
        encryption_state_observed=common,
        expected_encryption_features_observed=common,
        free_space_observed=common,
        recovery_plan_bound=True,
        all_required_categories_recorded=common,
        discovery_ready_for_manual_review=common,
        target_selected=False,
        storage_path_bound=False,
        write_authorized=False,
        handoff_ready=False,
        storage_verified=False,
        recovery_verified=False,
        phone_storage_written=False,
        manual_review_required=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def _review_dict(*, decision: str = "accepted_for_strategy_design", all_checks: bool = True) -> dict:
    return {
        "schema_version": 1,
        "profile_id": "oneplus/avicii",
        "device_serial": "SERIAL123",
        "review_policy": "manual-physical-storage-review-v1",
        "reviewer": "operator-1",
        "decision": decision,
        "physical_context_reviewed": all_checks,
        "topology_reviewed": all_checks,
        "filesystem_reviewed": all_checks,
        "encryption_reviewed": all_checks,
        "free_space_reviewed": all_checks,
        "recovery_plan_reviewed": all_checks,
        "evidence_chain_reviewed": all_checks,
        "target_selected": False,
        "storage_path_bound": False,
        "write_authorized": False,
    }


def _bind(*, ready: bool = True, decision: str = "accepted_for_strategy_design", all_checks: bool = True):
    return bind_physical_storage_review(
        _discovery(ready=ready),
        parse_physical_storage_review_record(_review_dict(decision=decision, all_checks=all_checks)),
        review_record_sha256=O,
        review_record_size=700,
        review_notes_sha256="dd" * 32,
        review_notes_size=300,
    )


def test_complete_review_accepts_only_for_later_strategy_design():
    evidence = _bind()
    assert evidence.source_discovery_ready_for_manual_review is True
    assert evidence.review_checks_complete is True
    assert evidence.review_recorded is True
    assert evidence.accepted_for_strategy_design is True
    assert evidence.further_strategy_review_required is True
    assert evidence.target_selected is False
    assert evidence.storage_path_bound is False
    assert evidence.write_authorized is False
    assert evidence.handoff_ready is False
    assert evidence.storage_verified is False
    assert evidence.recovery_verified is False
    assert evidence.phone_storage_written is False
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False


def test_rejection_can_be_recorded_without_completing_every_positive_check():
    evidence = _bind(decision="rejected", all_checks=False)
    assert evidence.review_checks_complete is False
    assert evidence.accepted_for_strategy_design is False
    assert evidence.review_recorded is True


def test_acceptance_fails_closed_when_discovery_is_not_review_ready():
    with pytest.raises(PhysicalStorageReviewError, match="cannot accept discovery"):
        _bind(ready=False)
    with pytest.raises(PhysicalStorageReviewError, match="cannot accept discovery"):
        _bind(all_checks=False)


def test_review_parser_rejects_target_write_claims_unknown_fields_and_unsafe_reviewer():
    raw = _review_dict()
    raw["target_selected"] = True
    with pytest.raises(PhysicalStorageReviewError, match="target_selected=false"):
        parse_physical_storage_review_record(raw)

    raw = _review_dict()
    raw["device_path"] = "/dev/block/sda18"
    with pytest.raises(PhysicalStorageReviewError, match="fields do not match"):
        parse_physical_storage_review_record(raw)

    raw = _review_dict()
    raw["reviewer"] = "bad reviewer/name"
    with pytest.raises(PhysicalStorageReviewError, match="safe bounded identifier"):
        parse_physical_storage_review_record(raw)


def test_review_binding_rejects_profile_or_serial_drift():
    raw = _review_dict()
    raw["profile_id"] = "other/device"
    with pytest.raises(PhysicalStorageReviewError, match="profile mismatch"):
        bind_physical_storage_review(
            _discovery(),
            parse_physical_storage_review_record(raw),
            review_record_sha256=O,
            review_record_size=1,
            review_notes_sha256="dd" * 32,
            review_notes_size=1,
        )

    raw = _review_dict()
    raw["device_serial"] = "OTHER"
    with pytest.raises(PhysicalStorageReviewError, match="serial mismatch"):
        bind_physical_storage_review(
            _discovery(),
            parse_physical_storage_review_record(raw),
            review_record_sha256=O,
            review_record_size=1,
            review_notes_sha256="dd" * 32,
            review_notes_size=1,
        )


def test_review_evidence_validator_rejects_handoff_or_beta_promotion():
    evidence = _bind()
    with pytest.raises(PhysicalStorageReviewError, match="unsupported target/write/hardware claim"):
        validate_physical_storage_review_evidence(replace(evidence, handoff_ready=True))
    with pytest.raises(PhysicalStorageReviewError, match="unsupported target/write/hardware claim"):
        validate_physical_storage_review_evidence(replace(evidence, beta_gate_credit=True))
    with pytest.raises(PhysicalStorageReviewError, match="lifecycle state"):
        validate_physical_storage_review_evidence(replace(evidence, further_strategy_review_required=False))


def test_exact_review_bytes_notes_and_immutable_output_are_bound(tmp_path: Path):
    review_path = tmp_path / "review.json"
    review_bytes = json.dumps(_review_dict(), indent=2, sort_keys=True).encode("utf-8") + b"\n"
    review_path.write_bytes(review_bytes)
    notes_path = tmp_path / "notes.txt"
    notes_bytes = b"Reviewed topology, filesystem, encryption, free space, evidence chain and recovery plan.\n"
    notes_path.write_bytes(notes_bytes)

    evidence = record_physical_storage_review(_discovery(), review_path, notes_path)
    assert evidence.review_record_sha256 == sha256(review_bytes).hexdigest()
    assert evidence.review_record_size == len(review_bytes)
    assert evidence.review_notes_sha256 == sha256(notes_bytes).hexdigest()
    assert evidence.review_notes_size == len(notes_bytes)

    destination = tmp_path / "physical-storage-review.json"
    digest = write_physical_storage_review_evidence(evidence, destination)
    assert digest == evidence.evidence_sha256()
    assert load_physical_storage_review_evidence(destination) == evidence
    with pytest.raises(PhysicalStorageReviewError, match="overwrite"):
        write_physical_storage_review_evidence(evidence, destination)


def test_review_record_loader_rejects_symlink(tmp_path: Path):
    review = tmp_path / "review.json"
    review.write_text(json.dumps(_review_dict()) + "\n", encoding="utf-8")
    loaded, digest, size = load_physical_storage_review_record(review)
    assert loaded.reviewer == "operator-1"
    assert digest == sha256(review.read_bytes()).hexdigest()
    assert size == len(review.read_bytes())
    link = tmp_path / "review-link.json"
    link.symlink_to(review)
    with pytest.raises(PhysicalStorageReviewError, match="non-symlink"):
        load_physical_storage_review_record(link)
