from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from kaliphonestudio.physical_bringup_dossier import (
    DossierFileEvidence,
    PhysicalBringupDossierEvidence,
)
from kaliphonestudio.physical_bringup_dossier_review import (
    PhysicalBringupDossierReviewError,
    PhysicalBringupDossierReviewRecord,
    bind_physical_bringup_dossier_review,
    load_physical_bringup_dossier_review_record,
    read_physical_bringup_dossier_review_notes,
    validate_physical_bringup_dossier_review_evidence,
)
from kaliphonestudio.physical_bringup_dossier_verify import (
    PhysicalBringupDossierVerificationEvidence,
)


def _digest(ch: str) -> str:
    return ch * 64


_ROLES = (
    "physical_bringup_session",
    "physical_candidate_gate",
    "physical_boot_observation",
    "rescue_diagnostics",
    "rescue_functional_probe",
    "physical_storage_discovery",
    "physical_storage_review",
    "rescue_transcript",
    "storage_discovery_report",
    "recovery_plan",
    "storage_review_record",
    "storage_review_notes",
)


def _dossier(*, storage_accepted: bool = True) -> PhysicalBringupDossierEvidence:
    files = tuple(
        DossierFileEvidence(
            role=role,
            sha256=_digest(hex((index % 15) + 1)[2:]),
            size=index + 10,
            canonical_json_required=role in {
                "physical_bringup_session",
                "physical_candidate_gate",
                "physical_boot_observation",
                "rescue_diagnostics",
                "rescue_functional_probe",
                "physical_storage_discovery",
                "physical_storage_review",
            },
        )
        for index, role in enumerate(_ROLES)
    )
    return PhysicalBringupDossierEvidence(
        schema_version=1,
        dossier_policy="physical-bringup-exact-file-dossier-v1",
        profile_id="vendor/test",
        device_serial="SERIAL-001",
        firmware_build="FW.1",
        firmware_fingerprint="vendor/test/device:1/test:user/release-keys",
        physical_bringup_session_sha256=_digest("1"),
        rootfs_authority_sha256=_digest("2"),
        rootfs_artifact_sha256=_digest("3"),
        rootfs_artifact_size=123456,
        rescue_probe_id=_digest("4"),
        storage_review_accepted_for_strategy_design=storage_accepted,
        kali_early_userspace_signal_present=False,
        required_file_count=12,
        supplied_file_count=12,
        exact_file_set_verified=True,
        rootfs_artifact_file_verified=False,
        files=files,
        manual_review_required=True,
        target_selected=False,
        storage_path_bound=False,
        write_authorized=False,
        handoff_ready=False,
        storage_verified=False,
        recovery_verified=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def _verification(dossier: PhysicalBringupDossierEvidence) -> PhysicalBringupDossierVerificationEvidence:
    return PhysicalBringupDossierVerificationEvidence(
        schema_version=1,
        verification_policy="physical-bringup-exact-file-dossier-reverify-v1",
        physical_bringup_dossier_sha256=dossier.evidence_sha256(),
        profile_id=dossier.profile_id,
        device_serial=dossier.device_serial,
        verified_role_count=12,
        verified_byte_count=4096,
        canonical_json_role_count=8,
        rootfs_artifact_file_verified=False,
        exact_file_set_verified=True,
        manual_review_required=True,
        target_selected=False,
        storage_path_bound=False,
        write_authorized=False,
        handoff_ready=False,
        storage_verified=False,
        recovery_verified=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def _review(*, decision: str = "accepted_for_strategy_review", complete: bool = True) -> PhysicalBringupDossierReviewRecord:
    return PhysicalBringupDossierReviewRecord(
        schema_version=1,
        review_policy="manual-physical-bringup-dossier-review-v1",
        profile_id="vendor/test",
        device_serial="SERIAL-001",
        reviewer="operator.test",
        decision=decision,
        physical_identity_reviewed=complete,
        firmware_stock_boot_reviewed=complete,
        candidate_authority_chain_reviewed=complete,
        rescue_evidence_chain_reviewed=complete,
        storage_review_chain_reviewed=complete,
        exact_file_set_reviewed=complete,
        recovery_plan_reviewed=complete,
        target_selected=False,
        storage_path_bound=False,
        write_authorized=False,
    )


def _bind(dossier: PhysicalBringupDossierEvidence, review: PhysicalBringupDossierReviewRecord):
    return bind_physical_bringup_dossier_review(
        dossier,
        _verification(dossier),
        review,
        review_record_sha256=_digest("a"),
        review_record_size=512,
        review_notes_sha256=_digest("b"),
        review_notes_size=128,
    )


def test_complete_review_accepts_only_for_later_strategy_review() -> None:
    evidence = _bind(_dossier(), _review())
    assert evidence.review_checks_complete is True
    assert evidence.dossier_review_completed is True
    assert evidence.accepted_for_strategy_review is True
    assert evidence.separate_strategy_review_required is True
    assert evidence.target_selected is False
    assert evidence.storage_path_bound is False
    assert evidence.write_authorized is False
    assert evidence.handoff_ready is False
    assert evidence.storage_verified is False
    assert evidence.recovery_verified is False
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False


def test_acceptance_requires_prior_storage_review_acceptance() -> None:
    dossier = _dossier(storage_accepted=False)
    with pytest.raises(PhysicalBringupDossierReviewError, match="cannot accept dossier"):
        _bind(dossier, _review())


def test_acceptance_requires_every_manual_check() -> None:
    with pytest.raises(PhysicalBringupDossierReviewError, match="cannot accept dossier"):
        _bind(_dossier(), _review(complete=False))


def test_rejected_review_can_record_incomplete_checks_without_credit() -> None:
    evidence = _bind(_dossier(storage_accepted=False), _review(decision="rejected", complete=False))
    assert evidence.review_checks_complete is False
    assert evidence.accepted_for_strategy_review is False
    assert evidence.separate_strategy_review_required is True


def test_detached_dossier_verification_is_rejected() -> None:
    dossier = _dossier()
    verification = replace(_verification(dossier), physical_bringup_dossier_sha256=_digest("f"))
    with pytest.raises(PhysicalBringupDossierReviewError, match="detached"):
        bind_physical_bringup_dossier_review(
            dossier,
            verification,
            _review(),
            review_record_sha256=_digest("a"),
            review_record_size=1,
            review_notes_sha256=_digest("b"),
            review_notes_size=1,
        )


def test_review_evidence_rejects_write_claim_tampering() -> None:
    evidence = _bind(_dossier(), _review())
    with pytest.raises(PhysicalBringupDossierReviewError, match="unsupported target/write/hardware/Beta claim"):
        validate_physical_bringup_dossier_review_evidence(replace(evidence, write_authorized=True))


def test_review_record_loader_requires_canonical_json_and_no_target(tmp_path: Path) -> None:
    path = tmp_path / "review.json"
    review = _review(decision="rejected", complete=False)
    path.write_text(review.canonical_json(), encoding="utf-8", newline="\n")
    loaded, digest, size = load_physical_bringup_dossier_review_record(path)
    assert loaded == review
    assert len(digest) == 64
    assert size == path.stat().st_size

    unsafe = replace(review, target_selected=True)
    path.write_text(unsafe.canonical_json(), encoding="utf-8", newline="\n")
    with pytest.raises(PhysicalBringupDossierReviewError, match="target_selected=false"):
        load_physical_bringup_dossier_review_record(path)


def test_review_notes_must_be_nonempty_utf8(tmp_path: Path) -> None:
    notes = tmp_path / "notes.txt"
    notes.write_text("Reviewed exact physical evidence chain.\n", encoding="utf-8")
    digest, size = read_physical_bringup_dossier_review_notes(notes)
    assert len(digest) == 64
    assert size > 0
    notes.write_text("\n", encoding="utf-8")
    with pytest.raises(PhysicalBringupDossierReviewError, match="empty"):
        read_physical_bringup_dossier_review_notes(notes)
