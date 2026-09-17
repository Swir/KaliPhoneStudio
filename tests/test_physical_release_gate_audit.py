from dataclasses import replace
from hashlib import sha256

import pytest

from kaliphonestudio.physical_bringup_dossier import (
    DossierFileEvidence,
    PhysicalBringupDossierEvidence,
    write_physical_bringup_dossier_evidence,
)
from kaliphonestudio.physical_bringup_dossier_review import (
    PhysicalBringupDossierReviewRecord,
    bind_physical_bringup_dossier_review,
    write_physical_bringup_dossier_review_evidence,
)
from kaliphonestudio.physical_bringup_dossier_verify import (
    PhysicalBringupDossierVerificationEvidence,
    write_physical_bringup_dossier_verification_evidence,
)
from kaliphonestudio.physical_hardware_result_bundle import (
    PhysicalHardwareResultBundleEvidence,
    write_physical_hardware_result_bundle_evidence,
)
from kaliphonestudio.physical_hardware_test_plan import (
    PhysicalHardwareTestPlanEvidence,
    write_physical_hardware_test_plan,
)
from kaliphonestudio.physical_hardware_test_plan_review import (
    PhysicalHardwareTestPlanReviewRecord,
    bind_physical_hardware_test_plan_review,
    write_physical_hardware_test_plan_review_evidence,
)
from kaliphonestudio.physical_release_gate_audit import (
    PhysicalReleaseGateAuditError,
    build_physical_release_gate_audit_from_files,
    load_physical_release_gate_audit_evidence,
    validate_physical_release_gate_audit_evidence,
    write_physical_release_gate_audit_evidence,
)


def _digest(ch: str) -> str:
    return ch * 64


def _plan():
    return PhysicalHardwareTestPlanEvidence(
        schema_version=1,
        plan_policy="physical-hardware-functional-test-plan-v1",
        profile_id="oneplus/avicii",
        device_serial="SERIAL-AUDIT-001",
        physical_hardware_review_sha256=_digest("1"),
        physical_hardware_survey_sha256=_digest("2"),
        physical_boot_observation_sha256=_digest("3"),
        physical_rescue_diagnostics_sha256=_digest("4"),
        transcript_sha256=_digest("5"),
        rescue_probe_id=_digest("6"),
        functional_hardware_contract_sha256=_digest("7"),
        tests=(
            {
                "id": "display",
                "required_for_beta": True,
                "manual_review_required": True,
                "destructive": False,
                "persistent_write_allowed": False,
                "required_context_signals": ["display_signal_observed"],
                "context_signals_satisfied": True,
                "required_observations": ["usable physical output is observed on the exact candidate"],
                "status": "pending",
            },
        ),
        test_count=1,
        beta_required_test_count=1,
        plan_ready_for_physical_execution=True,
        functional_tests_executed=False,
        functional_hardware_verified=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def _plan_review(plan):
    raw = plan.canonical_json().encode("utf-8")
    record = PhysicalHardwareTestPlanReviewRecord(
        schema_version=1,
        review_policy="manual-physical-hardware-functional-test-plan-review-v1",
        profile_id=plan.profile_id,
        device_serial=plan.device_serial,
        reviewer="plan-reviewer",
        decision="accepted",
        exact_plan_bytes_reviewed=True,
        exact_plan_identity_reviewed=True,
        functional_contract_reviewed=True,
        beta_required_scope_reviewed=True,
        context_readiness_reviewed=True,
        no_write_policy_reviewed=True,
        limitations_reviewed=True,
        functional_tests_executed=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    return bind_physical_hardware_test_plan_review(
        plan,
        record,
        plan_file_sha256=sha256(raw).hexdigest(),
        plan_file_size=len(raw),
        review_record_sha256=_digest("8"),
        review_record_size=256,
        review_notes_sha256=_digest("9"),
        review_notes_size=128,
    )


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


def _dossier(*, boot=_digest("3"), rescue=_digest("4"), transcript=_digest("5"), probe=_digest("6")):
    role_digests = {
        "physical_boot_observation": boot,
        "rescue_diagnostics": rescue,
        "rescue_transcript": transcript,
    }
    files = []
    fallback = "abcdef123456789"
    for index, role in enumerate(_ROLES):
        digest = role_digests.get(role, _digest(fallback[index % len(fallback)]))
        files.append(
            DossierFileEvidence(
                role=role,
                sha256=digest,
                size=index + 32,
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
        )
    return PhysicalBringupDossierEvidence(
        schema_version=1,
        dossier_policy="physical-bringup-exact-file-dossier-v1",
        profile_id="oneplus/avicii",
        device_serial="SERIAL-AUDIT-001",
        firmware_build="AC2003_11_F.23",
        firmware_fingerprint="OnePlus/avicii/avicii:12/RKQ1/test:user/release-keys",
        physical_bringup_session_sha256=_digest("a"),
        rootfs_authority_sha256=_digest("b"),
        rootfs_artifact_sha256=_digest("c"),
        rootfs_artifact_size=123456,
        rescue_probe_id=probe,
        storage_review_accepted_for_strategy_design=True,
        kali_early_userspace_signal_present=False,
        required_file_count=12,
        supplied_file_count=12,
        exact_file_set_verified=True,
        rootfs_artifact_file_verified=False,
        files=tuple(files),
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


def _verification(dossier):
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


def _dossier_review(dossier, verification, *, accepted=True):
    record = PhysicalBringupDossierReviewRecord(
        schema_version=1,
        review_policy="manual-physical-bringup-dossier-review-v1",
        profile_id=dossier.profile_id,
        device_serial=dossier.device_serial,
        reviewer="dossier-reviewer",
        decision="accepted_for_strategy_review" if accepted else "rejected",
        physical_identity_reviewed=accepted,
        firmware_stock_boot_reviewed=accepted,
        candidate_authority_chain_reviewed=accepted,
        rescue_evidence_chain_reviewed=accepted,
        storage_review_chain_reviewed=accepted,
        exact_file_set_reviewed=accepted,
        recovery_plan_reviewed=accepted,
        target_selected=False,
        storage_path_bound=False,
        write_authorized=False,
    )
    return bind_physical_bringup_dossier_review(
        dossier,
        verification,
        record,
        review_record_sha256=_digest("d"),
        review_record_size=256,
        review_notes_sha256=_digest("e"),
        review_notes_size=128,
    )


def _bundle(plan, plan_review, *, complete=True):
    if complete:
        row = {
            "id": "display",
            "required_for_beta": True,
            "summary_status": "reviewed_pass",
            "observation_present": True,
            "observation_evidence_sha256": _digest("1"),
            "observation_file_sha256": _digest("2"),
            "observation_file_size": 100,
            "result_review_present": True,
            "result_review_evidence_sha256": _digest("3"),
            "result_review_file_sha256": _digest("4"),
            "result_review_file_size": 100,
            "result_reviewer": "result-reviewer",
        }
        observations = reviews = reviewed = passed = beta_pass = 1
        remaining = 0
    else:
        row = {
            "id": "display",
            "required_for_beta": True,
            "summary_status": "pending",
            "observation_present": False,
            "observation_evidence_sha256": None,
            "observation_file_sha256": None,
            "observation_file_size": None,
            "result_review_present": False,
            "result_review_evidence_sha256": None,
            "result_review_file_sha256": None,
            "result_review_file_size": None,
            "result_reviewer": None,
        }
        observations = reviews = reviewed = passed = beta_pass = 0
        remaining = 1
    plan_raw = plan.canonical_json().encode("utf-8")
    review_raw = plan_review.canonical_json().encode("utf-8")
    return PhysicalHardwareResultBundleEvidence(
        schema_version=1,
        bundle_policy="physical-hardware-functional-result-bundle-v1",
        profile_id=plan.profile_id,
        device_serial=plan.device_serial,
        physical_hardware_test_plan_sha256=plan.evidence_sha256(),
        physical_hardware_test_plan_file_sha256=sha256(plan_raw).hexdigest(),
        physical_hardware_test_plan_file_size=len(plan_raw),
        physical_hardware_test_plan_review_sha256=plan_review.evidence_sha256(),
        physical_hardware_test_plan_review_file_sha256=sha256(review_raw).hexdigest(),
        physical_hardware_test_plan_review_file_size=len(review_raw),
        plan_review_reviewer=plan_review.reviewer,
        plan_review_accepted_for_physical_execution=True,
        functional_hardware_contract_sha256=plan.functional_hardware_contract_sha256,
        tests=(row,),
        test_count=1,
        observation_count=observations,
        result_review_count=reviews,
        reviewed_test_count=reviewed,
        reviewed_pass_count=passed,
        beta_required_test_count=1,
        beta_required_reviewed_pass_count=beta_pass,
        beta_required_remaining_count=remaining,
        beta_required_tests_all_reviewed_pass=complete,
        physical_hardware_test_summary_sha256=_digest("5"),
        physical_hardware_test_summary_file_sha256=_digest("6"),
        physical_hardware_test_summary_file_size=100,
        exact_files_verified=True,
        manual_release_gate_review_required=True,
        project_support_claim_authorized=False,
        persistent_write_performed=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def _write_set(tmp_path, *, dossier=None, accepted_dossier=True, complete_bundle=True):
    plan = _plan()
    plan_review = _plan_review(plan)
    dossier = dossier or _dossier()
    verification = _verification(dossier)
    dossier_review = _dossier_review(dossier, verification, accepted=accepted_dossier)
    bundle = _bundle(plan, plan_review, complete=complete_bundle)

    paths = {
        "dossier": tmp_path / "dossier.json",
        "verification": tmp_path / "dossier-verification.json",
        "dossier_review": tmp_path / "dossier-review.json",
        "bundle": tmp_path / "functional-result-bundle.json",
        "plan": tmp_path / "test-plan.json",
        "plan_review": tmp_path / "test-plan-review.json",
    }
    write_physical_bringup_dossier_evidence(dossier, paths["dossier"])
    write_physical_bringup_dossier_verification_evidence(verification, paths["verification"])
    write_physical_bringup_dossier_review_evidence(dossier_review, paths["dossier_review"])
    write_physical_hardware_result_bundle_evidence(bundle, paths["bundle"])
    write_physical_hardware_test_plan(plan, paths["plan"])
    write_physical_hardware_test_plan_review_evidence(plan_review, paths["plan_review"])
    return paths


def _build(paths):
    return build_physical_release_gate_audit_from_files(
        paths["dossier"],
        paths["verification"],
        paths["dossier_review"],
        paths["bundle"],
        paths["plan"],
        paths["plan_review"],
    )


def test_release_gate_audit_cross_binds_exact_campaigns_without_promotion(tmp_path):
    audit = _build(_write_set(tmp_path))
    assert audit.profile_id == "oneplus/avicii"
    assert audit.device_serial == "SERIAL-AUDIT-001"
    assert audit.cross_campaign_context_verified is True
    assert audit.exact_files_verified is True
    assert audit.dossier_review_accepted_for_strategy_review is True
    assert audit.beta_required_tests_all_reviewed_pass is True
    assert audit.beta_required_remaining_count == 0
    assert audit.kali_early_userspace_signal_present is False
    assert audit.manual_release_gate_review_required is True
    assert audit.physical_gate_still_incomplete is True
    assert audit.target_selected is False
    assert audit.write_authorized is False
    assert audit.hardware_verified is False
    assert audit.beta_release_authorized is False
    assert audit.beta_gate_credit is False

    output = tmp_path / "release-gate-audit.json"
    digest = write_physical_release_gate_audit_evidence(audit, output)
    assert digest == audit.evidence_sha256()
    assert load_physical_release_gate_audit_evidence(output) == audit
    with pytest.raises(PhysicalReleaseGateAuditError, match="overwrite"):
        write_physical_release_gate_audit_evidence(audit, output)


@pytest.mark.parametrize(
    ("dossier", "message"),
    [
        (_dossier(boot=_digest("f")), "boot observation"),
        (_dossier(rescue=_digest("f")), "rescue diagnostics"),
        (_dossier(transcript=_digest("f")), "rescue transcript"),
        (_dossier(probe=_digest("f")), "rescue probe"),
    ],
)
def test_release_gate_audit_rejects_cross_campaign_context_drift(tmp_path, dossier, message):
    with pytest.raises(PhysicalReleaseGateAuditError, match=message):
        _build(_write_set(tmp_path, dossier=dossier))


def test_release_gate_audit_rejects_unaccepted_dossier_review(tmp_path):
    with pytest.raises(PhysicalReleaseGateAuditError, match="accepted dossier review"):
        _build(_write_set(tmp_path, accepted_dossier=False))


def test_release_gate_audit_can_freeze_incomplete_functional_campaign_without_claiming_readiness(tmp_path):
    audit = _build(_write_set(tmp_path, complete_bundle=False))
    assert audit.beta_required_tests_all_reviewed_pass is False
    assert audit.beta_required_remaining_count == 1
    assert audit.physical_gate_still_incomplete is True
    assert audit.hardware_verified is False
    assert audit.beta_release_authorized is False
    assert audit.beta_gate_credit is False


def test_release_gate_audit_validation_rejects_any_promotion(tmp_path):
    audit = _build(_write_set(tmp_path))
    for changed in (
        replace(audit, target_selected=True),
        replace(audit, storage_path_bound=True),
        replace(audit, write_authorized=True),
        replace(audit, project_support_claim_authorized=True),
        replace(audit, persistent_write_performed=True),
        replace(audit, phone_storage_written=True),
        replace(audit, hardware_verified=True),
        replace(audit, beta_release_authorized=True),
        replace(audit, beta_gate_credit=True),
    ):
        with pytest.raises(PhysicalReleaseGateAuditError, match="forbidden"):
            validate_physical_release_gate_audit_evidence(changed)


def test_release_gate_audit_rejects_noncanonical_or_symlink_input(tmp_path):
    paths = _write_set(tmp_path)
    raw = paths["plan"].read_text(encoding="utf-8")
    paths["plan"].write_text(raw.rstrip() + "  \n", encoding="utf-8")
    with pytest.raises(PhysicalReleaseGateAuditError):
        _build(paths)

    paths = _write_set(tmp_path / "second")
    link = tmp_path / "linked-plan.json"
    try:
        link.symlink_to(paths["plan"])
    except OSError:
        pytest.skip("symlinks unavailable on this test platform")
    paths["plan"] = link
    with pytest.raises(PhysicalReleaseGateAuditError, match="non-symlink"):
        _build(paths)
