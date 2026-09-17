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

ATTESTATION = (
    "I reviewed the exact physical storage discovery evidence and recovery plan; "
    "this decision does not select a storage target or authorize a write."
)


def _discovery(*, ready: bool = True) -> PhysicalStorageDiscoveryEvidence:
    return PhysicalStorageDiscoveryEvidence(
        schema_version=1,
        profile_id="oneplus/avicii",
        device_serial="SERIAL123",
        firmware_build="AC2003_11.F.17",
        firmware_fingerprint="OnePlus/avicii/avicii:12/RKQ1/build:user/release-keys",
        rootfs_handoff_assessment_sha256="ab" * 32,
        rootfs_handoff_contract_sha256="cd" * 32,
        physical_candidate_gate_sha256="ef" * 32,
        rootfs_authority_sha256="12" * 32,
        rootfs_artifact_sha256="34" * 32,
        rootfs_artifact_size=137460600,
        rescue_diagnostics_sha256="56" * 32,
        rescue_functional_probe_sha256="78" * 32,
        transcript_sha256="9a" * 32,
        rescue_probe_id="bc" * 32,
        discovery_report_sha256="de" * 32,
        discovery_report_size=2048,
        recovery_plan_sha256="f0" * 32,
        recovery_plan_size=512,
        storage_bus="ufs",
        partition_hint="userdata",
        expected_filesystems=("f2fs",),
        expected_encryption_features=("fileencryption=ice", "wrappedkey"),
        forbidden_partitions=("boot", "metadata", "super", "system", "vendor"),
        block_device_count=1,
        filesystem_observation_count=1,
        encryption_observation_count=1,
        free_space_observation_count=1,
        topology_bound_to_rescue_diagnostics=ready,
        storage_bus_signal_observed=ready,
        filesystem_identity_observed=ready,
        expected_filesystem_observed=ready,
        encryption_state_observed=ready,
        expected_encryption_features_observed=ready,
        free_space_observed=ready,
        recovery_plan_bound=True,
        all_required_categories_recorded=ready,
        discovery_ready_for_manual_review=ready,
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


def _record(discovery: PhysicalStorageDiscoveryEvidence, decision: str = "approve_for_strategy_design") -> dict:
    return {
        "schema_version": 1,
        "profile_id": discovery.profile_id,
        "device_serial": discovery.device_serial,
        "review_policy": "human-storage-discovery-review-v1",
        "review_scope": "discovery-evidence-only-no-target-v1",
        "reviewer_id": "reviewer-01",
        "decision": decision,
        "physical_storage_discovery_sha256": discovery.evidence_sha256(),
        "discovery_report_sha256": discovery.discovery_report_sha256,
        "recovery_plan_sha256": discovery.recovery_plan_sha256,
        "target_selected": False,
        "storage_path_bound": False,
        "write_authorized": False,
        "phone_storage_written": False,
        "attestation": ATTESTATION,
    }


def _bind(*, ready: bool = True, decision: str = "approve_for_strategy_design"):
    discovery = _discovery(ready=ready)
    record = parse_physical_storage_review_record(_record(discovery, decision))
    return bind_physical_storage_review(
        discovery, record, review_record_sha256="11" * 32, review_record_size=1024
    )


def test_review_ready_can_only_enable_offline_strategy_design():
    evidence = _bind()
    assert evidence.manual_review_completed is True
    assert evidence.strategy_design_allowed is True
    assert evidence.target_selected is False
    assert evidence.storage_path_bound is False
    assert evidence.write_authorized is False
    assert evidence.handoff_ready is False
    assert evidence.storage_verified is False
    assert evidence.recovery_verified is False
    assert evidence.phone_storage_written is False
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False


def test_non_review_ready_discovery_cannot_be_approved():
    discovery = _discovery(ready=False)
    record = parse_physical_storage_review_record(_record(discovery))
    with pytest.raises(PhysicalStorageReviewError, match="not review-ready"):
        bind_physical_storage_review(
            discovery, record, review_record_sha256="11" * 32, review_record_size=100
        )


def test_rejection_is_recordable_without_strategy_design_permission():
    evidence = _bind(ready=False, decision="reject")
    assert evidence.manual_review_completed is True
    assert evidence.strategy_design_allowed is False


def test_review_record_rejects_target_write_claims_and_wrong_attestation():
    discovery = _discovery()
    raw = _record(discovery)
    raw["target_selected"] = True
    with pytest.raises(PhysicalStorageReviewError, match="target_selected=false"):
        parse_physical_storage_review_record(raw)
    raw = _record(discovery)
    raw["attestation"] = "approved"
    with pytest.raises(PhysicalStorageReviewError, match="attestation"):
        parse_physical_storage_review_record(raw)


def test_binding_rejects_identity_and_digest_drift():
    discovery = _discovery()
    raw = _record(discovery)
    raw["device_serial"] = "OTHER"
    record = parse_physical_storage_review_record(raw)
    with pytest.raises(PhysicalStorageReviewError, match="serial mismatch"):
        bind_physical_storage_review(discovery, record, review_record_sha256="11" * 32, review_record_size=100)
    raw = _record(discovery)
    raw["discovery_report_sha256"] = "22" * 32
    record = parse_physical_storage_review_record(raw)
    with pytest.raises(PhysicalStorageReviewError, match="discovery-report digest mismatch"):
        bind_physical_storage_review(discovery, record, review_record_sha256="11" * 32, review_record_size=100)
    raw = _record(discovery)
    raw["recovery_plan_sha256"] = "33" * 32
    record = parse_physical_storage_review_record(raw)
    with pytest.raises(PhysicalStorageReviewError, match="recovery-plan digest mismatch"):
        bind_physical_storage_review(discovery, record, review_record_sha256="11" * 32, review_record_size=100)


def test_validator_rejects_target_hardware_or_beta_promotion():
    evidence = _bind()
    for changed in (
        replace(evidence, target_selected=True),
        replace(evidence, write_authorized=True),
        replace(evidence, handoff_ready=True),
        replace(evidence, hardware_verified=True),
        replace(evidence, beta_gate_credit=True),
    ):
        with pytest.raises(PhysicalStorageReviewError, match="unsupported target/write/hardware claim"):
            validate_physical_storage_review_evidence(changed)


def test_exact_review_bytes_are_bound_and_output_is_immutable(tmp_path: Path):
    discovery = _discovery()
    record_path = tmp_path / "review.json"
    raw = json.dumps(_record(discovery), indent=2, sort_keys=True).encode() + b"\n"
    record_path.write_bytes(raw)
    record, digest, size = load_physical_storage_review_record(record_path)
    assert digest == sha256(raw).hexdigest()
    assert size == len(raw)
    assert record.reviewer_id == "reviewer-01"
    evidence = record_physical_storage_review(discovery, record_path)
    assert evidence.review_record_sha256 == digest
    destination = tmp_path / "review-evidence.json"
    assert write_physical_storage_review_evidence(evidence, destination) == evidence.evidence_sha256()
    assert load_physical_storage_review_evidence(destination) == evidence
    with pytest.raises(PhysicalStorageReviewError, match="overwrite"):
        write_physical_storage_review_evidence(evidence, destination)


def test_review_record_loader_rejects_symlink(tmp_path: Path):
    discovery = _discovery()
    record_path = tmp_path / "review.json"
    record_path.write_text(json.dumps(_record(discovery)), encoding="utf-8")
    link = tmp_path / "review-link.json"
    link.symlink_to(record_path)
    with pytest.raises(PhysicalStorageReviewError, match="non-symlink"):
        load_physical_storage_review_record(link)
