"""Cross-campaign release-gate audit packet for one physical bring-up context.

This offline layer binds the exact physical bring-up dossier + verification +
accepted dossier review to the exact physical functional-result bundle and the
canonical test plan/review used by that bundle. It exists to prevent a release
review from accidentally mixing evidence from different phones/candidates.

It performs no phone I/O, selects no storage target, authorizes no write and
never grants hardware or Beta release credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .physical_bringup_dossier import (
    PhysicalBringupDossierError,
    PhysicalBringupDossierEvidence,
    load_physical_bringup_dossier_evidence,
    validate_physical_bringup_dossier_evidence,
)
from .physical_bringup_dossier_review import (
    PhysicalBringupDossierReviewError,
    PhysicalBringupDossierReviewEvidence,
    load_physical_bringup_dossier_review_evidence,
    load_physical_bringup_dossier_verification_for_review,
    validate_physical_bringup_dossier_review_evidence,
)
from .physical_bringup_dossier_verify import (
    PhysicalBringupDossierVerificationEvidence,
    validate_physical_bringup_dossier_verification_evidence,
)
from .physical_hardware_result_bundle import (
    PhysicalHardwareResultBundleError,
    PhysicalHardwareResultBundleEvidence,
    load_physical_hardware_result_bundle_evidence,
    validate_physical_hardware_result_bundle_evidence,
)
from .physical_hardware_test_plan import (
    PhysicalHardwareTestPlanError,
    PhysicalHardwareTestPlanEvidence,
    load_physical_hardware_test_plan,
    validate_physical_hardware_test_plan,
)
from .physical_hardware_test_plan_review import (
    PhysicalHardwareTestPlanReviewError,
    PhysicalHardwareTestPlanReviewEvidence,
    load_physical_hardware_test_plan_review_evidence,
    validate_physical_hardware_test_plan_review_evidence,
)

_AUDIT_POLICY = "physical-release-gate-cross-campaign-audit-v1"
_MAX_JSON_BYTES = 32 * 1024 * 1024


class PhysicalReleaseGateAuditError(ValueError):
    pass


@dataclass(frozen=True)
class PhysicalReleaseGateAuditEvidence:
    schema_version: int
    audit_policy: str
    profile_id: str
    device_serial: str
    firmware_build: str
    firmware_fingerprint: str
    physical_bringup_dossier_sha256: str
    physical_bringup_dossier_file_sha256: str
    physical_bringup_dossier_file_size: int
    dossier_verification_sha256: str
    dossier_verification_file_sha256: str
    dossier_verification_file_size: int
    dossier_review_sha256: str
    dossier_review_file_sha256: str
    dossier_review_file_size: int
    dossier_reviewer: str
    dossier_review_accepted_for_strategy_review: bool
    physical_hardware_result_bundle_sha256: str
    physical_hardware_result_bundle_file_sha256: str
    physical_hardware_result_bundle_file_size: int
    physical_hardware_test_plan_sha256: str
    physical_hardware_test_plan_file_sha256: str
    physical_hardware_test_plan_file_size: int
    physical_hardware_test_plan_review_sha256: str
    physical_hardware_test_plan_review_file_sha256: str
    physical_hardware_test_plan_review_file_size: int
    plan_reviewer: str
    physical_boot_observation_sha256: str
    physical_rescue_diagnostics_sha256: str
    rescue_transcript_sha256: str
    rescue_probe_id: str
    functional_hardware_contract_sha256: str
    beta_required_test_count: int
    beta_required_reviewed_pass_count: int
    beta_required_remaining_count: int
    beta_required_tests_all_reviewed_pass: bool
    kali_early_userspace_signal_present: bool
    cross_campaign_context_verified: bool
    exact_files_verified: bool
    manual_release_gate_review_required: bool
    physical_gate_still_incomplete: bool
    target_selected: bool
    storage_path_bound: bool
    write_authorized: bool
    project_support_claim_authorized: bool
    persistent_write_performed: bool
    phone_storage_written: bool
    hardware_verified: bool
    beta_release_authorized: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise PhysicalReleaseGateAuditError(f"{label} must be a lowercase SHA-256")
    return value


def _positive(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PhysicalReleaseGateAuditError(f"{label} must be a positive integer")
    return value


def _nonnegative(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise PhysicalReleaseGateAuditError(f"{label} must be a non-negative integer")
    return value


def _safe_text(value: object, label: str, maximum: int = 1024) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise PhysicalReleaseGateAuditError(f"{label} must be non-empty bounded text")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise PhysicalReleaseGateAuditError(f"{label} contains control data")
    return value


def _read_exact(path: Path, label: str) -> tuple[bytes, str, int]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalReleaseGateAuditError(f"{label} must be a regular non-symlink file")
    try:
        before = source.stat()
        raw = source.read_bytes()
        after = source.stat()
    except OSError as exc:
        raise PhysicalReleaseGateAuditError(f"cannot read {label}: {exc}") from exc
    if before.st_size <= 0 or before.st_size > _MAX_JSON_BYTES or len(raw) != before.st_size:
        raise PhysicalReleaseGateAuditError(f"{label} size is outside the safety limit")
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or getattr(before, "st_ino", None) != getattr(after, "st_ino", None)
    ):
        raise PhysicalReleaseGateAuditError(f"{label} changed while being read")
    return raw, sha256(raw).hexdigest(), len(raw)


def _require_canonical(raw: bytes, canonical_json: str, digest: str, label: str) -> None:
    canonical = canonical_json.encode("utf-8")
    if raw != canonical:
        raise PhysicalReleaseGateAuditError(f"{label} is not the exact canonical evidence bytes")
    if digest != sha256(canonical).hexdigest():
        raise PhysicalReleaseGateAuditError(f"{label} digest drifted while being verified")


def _dossier_role_digest(dossier: PhysicalBringupDossierEvidence, role: str) -> str:
    matches = [item.sha256 for item in dossier.files if item.role == role]
    if len(matches) != 1:
        raise PhysicalReleaseGateAuditError(f"dossier must contain exactly one {role} role")
    return matches[0]


def _validate_cross_campaign(
    dossier: PhysicalBringupDossierEvidence,
    verification: PhysicalBringupDossierVerificationEvidence,
    dossier_review: PhysicalBringupDossierReviewEvidence,
    result_bundle: PhysicalHardwareResultBundleEvidence,
    plan: PhysicalHardwareTestPlanEvidence,
    plan_review: PhysicalHardwareTestPlanReviewEvidence,
) -> None:
    try:
        validate_physical_bringup_dossier_evidence(dossier)
        validate_physical_bringup_dossier_verification_evidence(verification)
        validate_physical_bringup_dossier_review_evidence(dossier_review)
        validate_physical_hardware_result_bundle_evidence(result_bundle)
        validate_physical_hardware_test_plan(plan)
        validate_physical_hardware_test_plan_review_evidence(plan_review)
    except (
        PhysicalBringupDossierError,
        PhysicalBringupDossierReviewError,
        PhysicalHardwareResultBundleError,
        PhysicalHardwareTestPlanError,
        PhysicalHardwareTestPlanReviewError,
        ValueError,
    ) as exc:
        raise PhysicalReleaseGateAuditError(str(exc)) from exc

    if dossier.storage_review_accepted_for_strategy_design is not True:
        raise PhysicalReleaseGateAuditError("release-gate audit requires an accepted physical storage review in the dossier")
    if dossier.exact_file_set_verified is not True or verification.exact_file_set_verified is not True:
        raise PhysicalReleaseGateAuditError("release-gate audit requires an exact verified dossier file set")
    if dossier_review.accepted_for_strategy_review is not True or dossier_review.decision != "accepted_for_strategy_review":
        raise PhysicalReleaseGateAuditError("release-gate audit requires an accepted dossier review")
    if dossier_review.physical_bringup_dossier_sha256 != dossier.evidence_sha256():
        raise PhysicalReleaseGateAuditError("dossier review is detached from the exact dossier")
    if dossier_review.dossier_verification_sha256 != verification.evidence_sha256():
        raise PhysicalReleaseGateAuditError("dossier review is detached from the exact dossier verification")
    if verification.physical_bringup_dossier_sha256 != dossier.evidence_sha256():
        raise PhysicalReleaseGateAuditError("dossier verification is detached from the exact dossier")

    identities = {
        (dossier.profile_id, dossier.device_serial),
        (verification.profile_id, verification.device_serial),
        (dossier_review.profile_id, dossier_review.device_serial),
        (result_bundle.profile_id, result_bundle.device_serial),
        (plan.profile_id, plan.device_serial),
        (plan_review.profile_id, plan_review.device_serial),
    }
    if len(identities) != 1:
        raise PhysicalReleaseGateAuditError("release-gate audit profile/device identity drifted across campaigns")

    if result_bundle.exact_files_verified is not True or result_bundle.manual_release_gate_review_required is not True:
        raise PhysicalReleaseGateAuditError("functional result bundle is not exact-file release-review input")
    if result_bundle.physical_hardware_test_plan_sha256 != plan.evidence_sha256():
        raise PhysicalReleaseGateAuditError("functional result bundle is detached from the exact test plan")
    if result_bundle.physical_hardware_test_plan_review_sha256 != plan_review.evidence_sha256():
        raise PhysicalReleaseGateAuditError("functional result bundle is detached from the exact test-plan review")
    if plan_review.accepted_for_physical_execution is not True or plan_review.decision != "accepted":
        raise PhysicalReleaseGateAuditError("release-gate audit requires the accepted exact test-plan review")
    if plan_review.physical_hardware_test_plan_sha256 != plan.evidence_sha256():
        raise PhysicalReleaseGateAuditError("test-plan review is detached from the exact test plan")

    if _dossier_role_digest(dossier, "physical_boot_observation") != plan.physical_boot_observation_sha256:
        raise PhysicalReleaseGateAuditError("functional campaign boot observation differs from bring-up dossier")
    if _dossier_role_digest(dossier, "rescue_diagnostics") != plan.physical_rescue_diagnostics_sha256:
        raise PhysicalReleaseGateAuditError("functional campaign rescue diagnostics differ from bring-up dossier")
    if _dossier_role_digest(dossier, "rescue_transcript") != plan.transcript_sha256:
        raise PhysicalReleaseGateAuditError("functional campaign rescue transcript differs from bring-up dossier")
    if dossier.rescue_probe_id != plan.rescue_probe_id:
        raise PhysicalReleaseGateAuditError("functional campaign rescue probe differs from bring-up dossier")
    if result_bundle.functional_hardware_contract_sha256 != plan.functional_hardware_contract_sha256:
        raise PhysicalReleaseGateAuditError("functional result bundle contract differs from exact test plan")


def build_physical_release_gate_audit_from_files(
    dossier_path: Path,
    dossier_verification_path: Path,
    dossier_review_path: Path,
    result_bundle_path: Path,
    test_plan_path: Path,
    test_plan_review_path: Path,
) -> PhysicalReleaseGateAuditEvidence:
    paths = (
        (Path(dossier_path), "physical bring-up dossier"),
        (Path(dossier_verification_path), "physical bring-up dossier verification"),
        (Path(dossier_review_path), "physical bring-up dossier review"),
        (Path(result_bundle_path), "physical functional result bundle"),
        (Path(test_plan_path), "physical hardware test plan"),
        (Path(test_plan_review_path), "physical hardware test-plan review"),
    )
    read = [_read_exact(path, label) for path, label in paths]

    try:
        dossier = load_physical_bringup_dossier_evidence(paths[0][0])
        verification = load_physical_bringup_dossier_verification_for_review(paths[1][0])
        dossier_review = load_physical_bringup_dossier_review_evidence(paths[2][0])
        result_bundle = load_physical_hardware_result_bundle_evidence(paths[3][0])
        plan = load_physical_hardware_test_plan(paths[4][0])
        plan_review = load_physical_hardware_test_plan_review_evidence(paths[5][0])
    except (
        PhysicalBringupDossierError,
        PhysicalBringupDossierReviewError,
        PhysicalHardwareResultBundleError,
        PhysicalHardwareTestPlanError,
        PhysicalHardwareTestPlanReviewError,
    ) as exc:
        raise PhysicalReleaseGateAuditError(str(exc)) from exc

    objects = (dossier, verification, dossier_review, result_bundle, plan, plan_review)
    labels = tuple(label for _, label in paths)
    for (raw, digest, _), obj, label in zip(read, objects, labels):
        _require_canonical(raw, obj.canonical_json(), digest, label)

    _validate_cross_campaign(dossier, verification, dossier_review, result_bundle, plan, plan_review)

    _, dossier_file_sha, dossier_file_size = read[0]
    _, verification_file_sha, verification_file_size = read[1]
    _, dossier_review_file_sha, dossier_review_file_size = read[2]
    _, result_file_sha, result_file_size = read[3]
    _, plan_file_sha, plan_file_size = read[4]
    _, plan_review_file_sha, plan_review_file_size = read[5]

    if result_bundle.physical_hardware_test_plan_file_sha256 != plan_file_sha:
        raise PhysicalReleaseGateAuditError("functional result bundle exact plan-file identity drifted")
    if result_bundle.physical_hardware_test_plan_file_size != plan_file_size:
        raise PhysicalReleaseGateAuditError("functional result bundle exact plan-file size drifted")
    if result_bundle.physical_hardware_test_plan_review_file_sha256 != plan_review_file_sha:
        raise PhysicalReleaseGateAuditError("functional result bundle exact plan-review-file identity drifted")
    if result_bundle.physical_hardware_test_plan_review_file_size != plan_review_file_size:
        raise PhysicalReleaseGateAuditError("functional result bundle exact plan-review-file size drifted")

    evidence = PhysicalReleaseGateAuditEvidence(
        schema_version=1,
        audit_policy=_AUDIT_POLICY,
        profile_id=dossier.profile_id,
        device_serial=dossier.device_serial,
        firmware_build=dossier.firmware_build,
        firmware_fingerprint=dossier.firmware_fingerprint,
        physical_bringup_dossier_sha256=dossier.evidence_sha256(),
        physical_bringup_dossier_file_sha256=dossier_file_sha,
        physical_bringup_dossier_file_size=dossier_file_size,
        dossier_verification_sha256=verification.evidence_sha256(),
        dossier_verification_file_sha256=verification_file_sha,
        dossier_verification_file_size=verification_file_size,
        dossier_review_sha256=dossier_review.evidence_sha256(),
        dossier_review_file_sha256=dossier_review_file_sha,
        dossier_review_file_size=dossier_review_file_size,
        dossier_reviewer=dossier_review.reviewer,
        dossier_review_accepted_for_strategy_review=True,
        physical_hardware_result_bundle_sha256=result_bundle.evidence_sha256(),
        physical_hardware_result_bundle_file_sha256=result_file_sha,
        physical_hardware_result_bundle_file_size=result_file_size,
        physical_hardware_test_plan_sha256=plan.evidence_sha256(),
        physical_hardware_test_plan_file_sha256=plan_file_sha,
        physical_hardware_test_plan_file_size=plan_file_size,
        physical_hardware_test_plan_review_sha256=plan_review.evidence_sha256(),
        physical_hardware_test_plan_review_file_sha256=plan_review_file_sha,
        physical_hardware_test_plan_review_file_size=plan_review_file_size,
        plan_reviewer=plan_review.reviewer,
        physical_boot_observation_sha256=plan.physical_boot_observation_sha256,
        physical_rescue_diagnostics_sha256=plan.physical_rescue_diagnostics_sha256,
        rescue_transcript_sha256=plan.transcript_sha256,
        rescue_probe_id=plan.rescue_probe_id,
        functional_hardware_contract_sha256=plan.functional_hardware_contract_sha256,
        beta_required_test_count=result_bundle.beta_required_test_count,
        beta_required_reviewed_pass_count=result_bundle.beta_required_reviewed_pass_count,
        beta_required_remaining_count=result_bundle.beta_required_remaining_count,
        beta_required_tests_all_reviewed_pass=result_bundle.beta_required_tests_all_reviewed_pass,
        kali_early_userspace_signal_present=dossier.kali_early_userspace_signal_present,
        cross_campaign_context_verified=True,
        exact_files_verified=True,
        manual_release_gate_review_required=True,
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
    )
    validate_physical_release_gate_audit_evidence(evidence)
    return evidence


def validate_physical_release_gate_audit_evidence(evidence: PhysicalReleaseGateAuditEvidence) -> None:
    if not isinstance(evidence, PhysicalReleaseGateAuditEvidence) or evidence.schema_version != 1:
        raise PhysicalReleaseGateAuditError("physical release-gate audit must be schema-v1 typed evidence")
    if evidence.audit_policy != _AUDIT_POLICY:
        raise PhysicalReleaseGateAuditError("physical release-gate audit policy is unsupported")
    _safe_text(evidence.profile_id, "release-gate audit profile id", 128)
    _safe_text(evidence.device_serial, "release-gate audit device serial", 256)
    _safe_text(evidence.firmware_build, "release-gate audit firmware build", 512)
    _safe_text(evidence.firmware_fingerprint, "release-gate audit firmware fingerprint", 1024)
    _safe_text(evidence.dossier_reviewer, "release-gate dossier reviewer", 128)
    _safe_text(evidence.plan_reviewer, "release-gate plan reviewer", 128)
    for value, label in (
        (evidence.physical_bringup_dossier_sha256, "physical bring-up dossier"),
        (evidence.physical_bringup_dossier_file_sha256, "physical bring-up dossier file"),
        (evidence.dossier_verification_sha256, "dossier verification"),
        (evidence.dossier_verification_file_sha256, "dossier verification file"),
        (evidence.dossier_review_sha256, "dossier review"),
        (evidence.dossier_review_file_sha256, "dossier review file"),
        (evidence.physical_hardware_result_bundle_sha256, "physical functional result bundle"),
        (evidence.physical_hardware_result_bundle_file_sha256, "physical functional result bundle file"),
        (evidence.physical_hardware_test_plan_sha256, "physical hardware test plan"),
        (evidence.physical_hardware_test_plan_file_sha256, "physical hardware test plan file"),
        (evidence.physical_hardware_test_plan_review_sha256, "physical hardware test-plan review"),
        (evidence.physical_hardware_test_plan_review_file_sha256, "physical hardware test-plan review file"),
        (evidence.physical_boot_observation_sha256, "physical boot observation"),
        (evidence.physical_rescue_diagnostics_sha256, "physical rescue diagnostics"),
        (evidence.rescue_transcript_sha256, "rescue transcript"),
        (evidence.rescue_probe_id, "rescue probe id"),
        (evidence.functional_hardware_contract_sha256, "functional hardware contract"),
    ):
        _sha(value, label)
    for value, label in (
        (evidence.physical_bringup_dossier_file_size, "physical bring-up dossier file size"),
        (evidence.dossier_verification_file_size, "dossier verification file size"),
        (evidence.dossier_review_file_size, "dossier review file size"),
        (evidence.physical_hardware_result_bundle_file_size, "physical functional result bundle file size"),
        (evidence.physical_hardware_test_plan_file_size, "physical hardware test plan file size"),
        (evidence.physical_hardware_test_plan_review_file_size, "physical hardware test-plan review file size"),
    ):
        _positive(value, label)
    for value, label in (
        (evidence.beta_required_test_count, "Beta-required test count"),
        (evidence.beta_required_reviewed_pass_count, "Beta-required reviewed-pass count"),
        (evidence.beta_required_remaining_count, "Beta-required remaining count"),
    ):
        _nonnegative(value, label)
    if evidence.beta_required_reviewed_pass_count > evidence.beta_required_test_count:
        raise PhysicalReleaseGateAuditError("release-gate audit Beta reviewed-pass count is impossible")
    if evidence.beta_required_remaining_count != evidence.beta_required_test_count - evidence.beta_required_reviewed_pass_count:
        raise PhysicalReleaseGateAuditError("release-gate audit Beta remaining count drifted")
    expected_all = (
        evidence.beta_required_test_count > 0
        and evidence.beta_required_reviewed_pass_count == evidence.beta_required_test_count
    )
    if evidence.beta_required_tests_all_reviewed_pass is not expected_all:
        raise PhysicalReleaseGateAuditError("release-gate audit Beta coverage flag drifted")
    if evidence.dossier_review_accepted_for_strategy_review is not True:
        raise PhysicalReleaseGateAuditError("release-gate audit requires accepted exact dossier review")
    if evidence.cross_campaign_context_verified is not True or evidence.exact_files_verified is not True:
        raise PhysicalReleaseGateAuditError("release-gate audit must preserve exact cross-campaign verification")
    if evidence.manual_release_gate_review_required is not True or evidence.physical_gate_still_incomplete is not True:
        raise PhysicalReleaseGateAuditError("release-gate audit must remain manual-review-only and physically incomplete")
    forbidden = (
        evidence.target_selected,
        evidence.storage_path_bound,
        evidence.write_authorized,
        evidence.project_support_claim_authorized,
        evidence.persistent_write_performed,
        evidence.phone_storage_written,
        evidence.hardware_verified,
        evidence.beta_release_authorized,
        evidence.beta_gate_credit,
    )
    if any(value is not False for value in forbidden):
        raise PhysicalReleaseGateAuditError("release-gate audit contains forbidden target/write/support/hardware/Beta promotion")
    if not isinstance(evidence.kali_early_userspace_signal_present, bool):
        raise PhysicalReleaseGateAuditError("release-gate audit Kali early-userspace signal flag must be boolean")


def load_physical_release_gate_audit_evidence(path: Path) -> PhysicalReleaseGateAuditEvidence:
    raw, _, _ = _read_exact(Path(path), "physical release-gate audit")
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalReleaseGateAuditError("physical release-gate audit is not valid UTF-8 JSON") from exc
    expected = {item.name for item in fields(PhysicalReleaseGateAuditEvidence)}
    if not isinstance(value, dict) or set(value) != expected:
        raise PhysicalReleaseGateAuditError("physical release-gate audit fields do not match schema-v1")
    try:
        evidence = PhysicalReleaseGateAuditEvidence(**value)
        validate_physical_release_gate_audit_evidence(evidence)
    except (TypeError, PhysicalReleaseGateAuditError) as exc:
        raise PhysicalReleaseGateAuditError("physical release-gate audit evidence is invalid") from exc
    if raw != evidence.canonical_json().encode("utf-8"):
        raise PhysicalReleaseGateAuditError("physical release-gate audit is not canonical JSON")
    return evidence


def write_physical_release_gate_audit_evidence(
    evidence: PhysicalReleaseGateAuditEvidence,
    destination: Path,
) -> str:
    validate_physical_release_gate_audit_evidence(evidence)
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise PhysicalReleaseGateAuditError("refusing to overwrite physical release-gate audit evidence")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise PhysicalReleaseGateAuditError("refusing stale physical release-gate audit temporary path")
    try:
        temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
        temporary.replace(path)
    except OSError as exc:
        raise PhysicalReleaseGateAuditError(f"cannot write physical release-gate audit evidence: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()
