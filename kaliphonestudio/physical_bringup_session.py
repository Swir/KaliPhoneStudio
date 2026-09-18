"""Cross-bind physical bring-up evidence without granting hardware or Beta credit.

KaliPhoneStudio intentionally records physical bring-up in separate evidence
layers: candidate identity, temporary rescue observation, read-only diagnostics,
explicit functional probes, storage discovery, manual storage review and (when
available) Kali early-userspace markers.  This module adds one fail-closed
*session bundle* that proves those records belong to the same profile/device and
exact candidate/evidence chain.

The bundle is an audit/hand-off artifact only.  It cannot choose a storage
location, bind a ``/dev/...`` path, authorize a write, mark hardware verified, or
satisfy the Beta gate.  In particular, a storage review accepted for later
strategy design is mirrored as a fact but never promoted to target selection or
handoff readiness.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .physical_boot_observation import (
    PhysicalBootObservationEvidence,
    PhysicalBootObservationError,
    validate_physical_boot_observation_evidence,
)
from .physical_campaign_admission import (
    PhysicalCampaignAdmissionError,
    require_current_physical_campaign_observation,
)
from .physical_candidate_gate import PhysicalCandidateGateEvidence
from .physical_kali_early_userspace import (
    PhysicalKaliEarlyUserspaceEvidence,
    PhysicalKaliEarlyUserspaceError,
    validate_physical_kali_early_userspace_evidence,
)
from .physical_rescue_diagnostics import (
    PhysicalRescueDiagnosticsEvidence,
    PhysicalRescueDiagnosticsError,
    validate_physical_rescue_diagnostics_evidence,
)
from .physical_rescue_functional_probes import (
    PhysicalRescueFunctionalProbeEvidence,
    PhysicalRescueFunctionalProbeError,
    validate_physical_rescue_functional_probe_evidence,
)
from .physical_storage_discovery import (
    PhysicalStorageDiscoveryEvidence,
    PhysicalStorageDiscoveryError,
    validate_physical_storage_discovery_evidence,
)
from .physical_storage_review import (
    PhysicalStorageReviewEvidence,
    PhysicalStorageReviewError,
    validate_physical_storage_review_evidence,
)

_SESSION_POLICY = "physical-bringup-evidence-chain-v1"
_MAX_EVIDENCE_BYTES = 4 * 1024 * 1024


class PhysicalBringupSessionError(ValueError):
    pass


@dataclass(frozen=True)
class PhysicalBringupSessionEvidence:
    schema_version: int
    session_policy: str
    profile_id: str
    device_serial: str
    firmware_build: str
    firmware_fingerprint: str
    physical_candidate_gate_sha256: str
    physical_boot_observation_sha256: str
    rescue_diagnostics_sha256: str
    rescue_functional_probe_sha256: str
    physical_storage_discovery_sha256: str
    physical_storage_review_sha256: str
    rootfs_handoff_assessment_sha256: str
    rootfs_handoff_contract_sha256: str
    rootfs_authority_sha256: str
    rootfs_artifact_sha256: str
    rootfs_artifact_size: int
    rescue_transcript_sha256: str
    rescue_probe_id: str
    discovery_report_sha256: str
    recovery_plan_sha256: str
    storage_review_record_sha256: str
    storage_review_notes_sha256: str
    kali_early_userspace_evidence_sha256: str | None
    kali_early_userspace_transcript_sha256: str | None
    kali_early_userspace_probe_id: str | None
    rescue_chain_complete: bool
    storage_discovery_chain_complete: bool
    storage_review_recorded: bool
    storage_review_accepted_for_strategy_design: bool
    kali_early_userspace_signal_present: bool
    manual_review_required: bool
    target_selected: bool
    storage_path_bound: bool
    write_authorized: bool
    handoff_ready: bool
    storage_verified: bool
    charging_battery_verified: bool
    display_touch_verified: bool
    recovery_verified: bool
    kali_early_userspace_verified: bool
    phone_storage_written: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _sha(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise PhysicalBringupSessionError(f"{label} must be a lowercase SHA-256")
    return value


def _text(value: object, label: str, max_len: int = 1024) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len:
        raise PhysicalBringupSessionError(f"{label} must be non-empty bounded text")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise PhysicalBringupSessionError(f"{label} contains control data")
    return value


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PhysicalBringupSessionError(f"{label} must be a positive integer")
    return value


def _validate_candidate_gate(gate: PhysicalCandidateGateEvidence) -> None:
    if not isinstance(gate, PhysicalCandidateGateEvidence) or gate.schema_version != 1:
        raise PhysicalBringupSessionError("physical candidate gate must be schema-v1 typed evidence")
    _text(gate.profile_id, "candidate profile id", 128)
    _text(gate.device_serial, "candidate device serial", 256)
    _text(gate.firmware_build, "candidate firmware build", 512)
    _text(gate.firmware_fingerprint, "candidate firmware fingerprint", 1024)
    for value, label in (
        (gate.evidence_sha256(), "physical candidate gate"),
        (gate.physical_baseline_bundle_sha256, "physical baseline bundle"),
        (gate.fastboot_capture_bundle_sha256, "Fastboot capture bundle"),
        (gate.fastboot_baseline_evidence_sha256, "Fastboot baseline"),
        (gate.fastboot_transcript_sha256, "Fastboot transcript"),
        (gate.stock_provenance_sha256, "stock provenance"),
        (gate.stock_ota_sha256, "stock OTA"),
        (gate.stock_boot_sha256, "stock boot"),
        (gate.first_boot_manifest_sha256, "first-boot manifest"),
        (gate.first_boot_authority_bundle_sha256, "first-boot authority bundle"),
        (gate.boot_authorization_sha256, "boot authorization"),
        (gate.boot_plan_sha256, "boot plan"),
        (gate.boot_image_sha256, "boot image"),
        (gate.kernel_image_sha256, "kernel image"),
        (gate.rootfs_artifact_sha256, "rootfs artifact"),
    ):
        _sha(value, label)
    if gate.dtb_sha256 is not None:
        _sha(gate.dtb_sha256, "DTB")
    if gate.dtbo_image_sha256 is not None:
        _sha(gate.dtbo_image_sha256, "DTBO image")
    _positive_int(gate.boot_image_size, "candidate boot image size")
    if (
        gate.reviewed_authorities_bound is not True
        or gate.exact_physical_baseline_bound is not True
        or gate.ready_for_temporary_boot_offer is not True
        or gate.temporary_boot_executed is not False
        or gate.phone_storage_written is not False
        or gate.hardware_verified is not False
        or gate.beta_gate_credit is not False
    ):
        raise PhysicalBringupSessionError("physical candidate gate has invalid readiness/safety state")


def _require_same_identity(label: str, profile_id: str, serial: str, item: object) -> None:
    if getattr(item, "profile_id", None) != profile_id:
        raise PhysicalBringupSessionError(f"{label} profile differs from physical candidate")
    if getattr(item, "device_serial", None) != serial:
        raise PhysicalBringupSessionError(f"{label} serial differs from physical candidate")


def _validate_inputs(
    gate: PhysicalCandidateGateEvidence,
    observation: PhysicalBootObservationEvidence,
    diagnostics: PhysicalRescueDiagnosticsEvidence,
    functional: PhysicalRescueFunctionalProbeEvidence,
    discovery: PhysicalStorageDiscoveryEvidence,
    review: PhysicalStorageReviewEvidence,
    early_userspace: PhysicalKaliEarlyUserspaceEvidence | None,
) -> None:
    _validate_candidate_gate(gate)
    try:
        require_current_physical_campaign_observation(observation)
    except PhysicalCampaignAdmissionError as exc:
        raise PhysicalBringupSessionError(str(exc)) from exc
    try:
        validate_physical_boot_observation_evidence(observation)
        validate_physical_rescue_diagnostics_evidence(diagnostics)
        validate_physical_rescue_functional_probe_evidence(functional)
        validate_physical_storage_discovery_evidence(discovery)
        validate_physical_storage_review_evidence(review)
        if early_userspace is not None:
            validate_physical_kali_early_userspace_evidence(early_userspace)
    except (
        PhysicalBootObservationError,
        PhysicalRescueDiagnosticsError,
        PhysicalRescueFunctionalProbeError,
        PhysicalStorageDiscoveryError,
        PhysicalStorageReviewError,
        PhysicalKaliEarlyUserspaceError,
        ValueError,
    ) as exc:
        raise PhysicalBringupSessionError(str(exc)) from exc


def bind_physical_bringup_session(
    gate: PhysicalCandidateGateEvidence,
    observation: PhysicalBootObservationEvidence,
    diagnostics: PhysicalRescueDiagnosticsEvidence,
    functional: PhysicalRescueFunctionalProbeEvidence,
    discovery: PhysicalStorageDiscoveryEvidence,
    review: PhysicalStorageReviewEvidence,
    *,
    early_userspace: PhysicalKaliEarlyUserspaceEvidence | None = None,
) -> PhysicalBringupSessionEvidence:
    """Bind an exact rescue/storage review chain and optional Kali marker record.

    This is deliberately offline and non-operational.  No path in this function
    invokes Fastboot/ADB, selects storage, mounts/decrypts filesystems or writes a
    phone.  A successfully bound session remains manual-review-only.
    """
    _validate_inputs(gate, observation, diagnostics, functional, discovery, review, early_userspace)

    profile_id = gate.profile_id
    serial = gate.device_serial
    for label, item in (
        ("physical boot observation", observation),
        ("rescue diagnostics", diagnostics),
        ("rescue functional probe", functional),
        ("physical storage discovery", discovery),
        ("physical storage review", review),
    ):
        _require_same_identity(label, profile_id, serial, item)
    if early_userspace is not None:
        _require_same_identity("Kali early-userspace observation", profile_id, serial, early_userspace)

    gate_sha = gate.evidence_sha256()
    observation_sha = observation.evidence_sha256()
    diagnostics_sha = diagnostics.evidence_sha256()
    functional_sha = functional.evidence_sha256()
    discovery_sha = discovery.evidence_sha256()
    review_sha = review.evidence_sha256()

    if diagnostics.physical_boot_observation_sha256 != observation_sha:
        raise PhysicalBringupSessionError("rescue diagnostics are detached from the supplied boot observation")
    if functional.physical_boot_observation_sha256 != observation_sha:
        raise PhysicalBringupSessionError("functional probes are detached from the supplied boot observation")
    if functional.rescue_diagnostics_sha256 != diagnostics_sha:
        raise PhysicalBringupSessionError("functional probes are detached from the supplied rescue diagnostics")
    if discovery.physical_candidate_gate_sha256 != gate_sha:
        raise PhysicalBringupSessionError("storage discovery is detached from the supplied physical candidate gate")
    if discovery.rescue_diagnostics_sha256 != diagnostics_sha:
        raise PhysicalBringupSessionError("storage discovery is detached from the supplied rescue diagnostics")
    if discovery.rescue_functional_probe_sha256 != functional_sha:
        raise PhysicalBringupSessionError("storage discovery is detached from the supplied functional probes")
    if review.physical_storage_discovery_sha256 != discovery_sha:
        raise PhysicalBringupSessionError("storage review is detached from the supplied discovery evidence")

    exact_pairs = (
        (review.physical_candidate_gate_sha256, discovery.physical_candidate_gate_sha256, "candidate gate"),
        (review.rootfs_handoff_assessment_sha256, discovery.rootfs_handoff_assessment_sha256, "rootfs handoff assessment"),
        (review.rootfs_handoff_contract_sha256, discovery.rootfs_handoff_contract_sha256, "rootfs handoff contract"),
        (review.rootfs_authority_sha256, discovery.rootfs_authority_sha256, "rootfs authority"),
        (review.rootfs_artifact_sha256, discovery.rootfs_artifact_sha256, "rootfs artifact"),
        (review.rescue_diagnostics_sha256, discovery.rescue_diagnostics_sha256, "rescue diagnostics"),
        (review.rescue_functional_probe_sha256, discovery.rescue_functional_probe_sha256, "functional probe"),
        (review.transcript_sha256, discovery.transcript_sha256, "rescue transcript"),
        (review.rescue_probe_id, discovery.rescue_probe_id, "rescue probe id"),
        (review.discovery_report_sha256, discovery.discovery_report_sha256, "storage discovery report"),
        (review.recovery_plan_sha256, discovery.recovery_plan_sha256, "recovery plan"),
    )
    for left, right, label in exact_pairs:
        if left != right:
            raise PhysicalBringupSessionError(f"storage review {label} drifted from discovery evidence")
    if review.rootfs_artifact_size != discovery.rootfs_artifact_size:
        raise PhysicalBringupSessionError("storage review rootfs size drifted from discovery evidence")

    if gate.firmware_build != discovery.firmware_build or gate.firmware_build != review.firmware_build:
        raise PhysicalBringupSessionError("physical firmware build drifted across candidate/storage evidence")
    if (
        gate.firmware_fingerprint != discovery.firmware_fingerprint
        or gate.firmware_fingerprint != review.firmware_fingerprint
    ):
        raise PhysicalBringupSessionError("physical firmware fingerprint drifted across candidate/storage evidence")
    if gate.rootfs_artifact_sha256 != discovery.rootfs_artifact_sha256:
        raise PhysicalBringupSessionError("reviewed rootfs artifact drifted from physical candidate")

    if not (
        observation.transcript_sha256
        == diagnostics.transcript_sha256
        == functional.transcript_sha256
        == discovery.transcript_sha256
        == review.transcript_sha256
    ):
        raise PhysicalBringupSessionError("rescue transcript identity drifted across physical evidence layers")
    if not (
        observation.rescue_probe_id
        == diagnostics.rescue_probe_id
        == functional.rescue_probe_id
        == discovery.rescue_probe_id
        == review.rescue_probe_id
    ):
        raise PhysicalBringupSessionError("rescue probe identity drifted across physical evidence layers")

    early_sha: str | None = None
    early_transcript: str | None = None
    early_probe: str | None = None
    early_present = early_userspace is not None
    if early_userspace is not None:
        if early_userspace.physical_candidate_gate_sha256 != gate_sha:
            raise PhysicalBringupSessionError("Kali early-userspace evidence is detached from physical candidate gate")
        if early_userspace.first_boot_manifest_sha256 != gate.first_boot_manifest_sha256:
            raise PhysicalBringupSessionError("Kali early-userspace manifest differs from physical candidate")
        if early_userspace.first_boot_authority_bundle_sha256 != gate.first_boot_authority_bundle_sha256:
            raise PhysicalBringupSessionError("Kali early-userspace authority bundle differs from physical candidate")
        if early_userspace.rootfs_authority_sha256 != discovery.rootfs_authority_sha256:
            raise PhysicalBringupSessionError("Kali early-userspace rootfs authority differs from storage evidence")
        if early_userspace.rootfs_artifact_sha256 != gate.rootfs_artifact_sha256:
            raise PhysicalBringupSessionError("Kali early-userspace rootfs artifact differs from physical candidate")
        early_sha = early_userspace.evidence_sha256()
        early_transcript = early_userspace.transcript_sha256
        early_probe = early_userspace.probe_id

    evidence = PhysicalBringupSessionEvidence(
        schema_version=1,
        session_policy=_SESSION_POLICY,
        profile_id=profile_id,
        device_serial=serial,
        firmware_build=gate.firmware_build,
        firmware_fingerprint=gate.firmware_fingerprint,
        physical_candidate_gate_sha256=gate_sha,
        physical_boot_observation_sha256=observation_sha,
        rescue_diagnostics_sha256=diagnostics_sha,
        rescue_functional_probe_sha256=functional_sha,
        physical_storage_discovery_sha256=discovery_sha,
        physical_storage_review_sha256=review_sha,
        rootfs_handoff_assessment_sha256=discovery.rootfs_handoff_assessment_sha256,
        rootfs_handoff_contract_sha256=discovery.rootfs_handoff_contract_sha256,
        rootfs_authority_sha256=discovery.rootfs_authority_sha256,
        rootfs_artifact_sha256=discovery.rootfs_artifact_sha256,
        rootfs_artifact_size=discovery.rootfs_artifact_size,
        rescue_transcript_sha256=observation.transcript_sha256,
        rescue_probe_id=observation.rescue_probe_id,
        discovery_report_sha256=discovery.discovery_report_sha256,
        recovery_plan_sha256=discovery.recovery_plan_sha256,
        storage_review_record_sha256=review.review_record_sha256,
        storage_review_notes_sha256=review.review_notes_sha256,
        kali_early_userspace_evidence_sha256=early_sha,
        kali_early_userspace_transcript_sha256=early_transcript,
        kali_early_userspace_probe_id=early_probe,
        rescue_chain_complete=True,
        storage_discovery_chain_complete=True,
        storage_review_recorded=review.review_recorded,
        storage_review_accepted_for_strategy_design=review.accepted_for_strategy_design,
        kali_early_userspace_signal_present=early_present,
        manual_review_required=True,
        target_selected=False,
        storage_path_bound=False,
        write_authorized=False,
        handoff_ready=False,
        storage_verified=False,
        charging_battery_verified=False,
        display_touch_verified=False,
        recovery_verified=False,
        kali_early_userspace_verified=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    validate_physical_bringup_session_evidence(evidence)
    return evidence


def validate_physical_bringup_session_evidence(evidence: PhysicalBringupSessionEvidence) -> None:
    if not isinstance(evidence, PhysicalBringupSessionEvidence) or evidence.schema_version != 1:
        raise PhysicalBringupSessionError("physical bring-up session must be schema-v1 typed evidence")
    if evidence.session_policy != _SESSION_POLICY:
        raise PhysicalBringupSessionError("physical bring-up session policy is unsupported")
    _text(evidence.profile_id, "session profile id", 128)
    _text(evidence.device_serial, "session device serial", 256)
    _text(evidence.firmware_build, "session firmware build", 512)
    _text(evidence.firmware_fingerprint, "session firmware fingerprint", 1024)
    for value, label in (
        (evidence.physical_candidate_gate_sha256, "physical candidate gate"),
        (evidence.physical_boot_observation_sha256, "physical boot observation"),
        (evidence.rescue_diagnostics_sha256, "rescue diagnostics"),
        (evidence.rescue_functional_probe_sha256, "rescue functional probe"),
        (evidence.physical_storage_discovery_sha256, "physical storage discovery"),
        (evidence.physical_storage_review_sha256, "physical storage review"),
        (evidence.rootfs_handoff_assessment_sha256, "rootfs handoff assessment"),
        (evidence.rootfs_handoff_contract_sha256, "rootfs handoff contract"),
        (evidence.rootfs_authority_sha256, "rootfs authority"),
        (evidence.rootfs_artifact_sha256, "rootfs artifact"),
        (evidence.rescue_transcript_sha256, "rescue transcript"),
        (evidence.rescue_probe_id, "rescue probe id"),
        (evidence.discovery_report_sha256, "storage discovery report"),
        (evidence.recovery_plan_sha256, "recovery plan"),
        (evidence.storage_review_record_sha256, "storage review record"),
        (evidence.storage_review_notes_sha256, "storage review notes"),
    ):
        _sha(value, label)
    _positive_int(evidence.rootfs_artifact_size, "rootfs artifact size")

    optional = (
        evidence.kali_early_userspace_evidence_sha256,
        evidence.kali_early_userspace_transcript_sha256,
        evidence.kali_early_userspace_probe_id,
    )
    if evidence.kali_early_userspace_signal_present:
        if any(value is None for value in optional):
            raise PhysicalBringupSessionError("Kali early-userspace signal requires complete optional identity fields")
        for value, label in zip(optional, ("Kali early-userspace evidence", "Kali early-userspace transcript", "Kali early-userspace probe id")):
            _sha(value, label)
    elif any(value is not None for value in optional):
        raise PhysicalBringupSessionError("Kali early-userspace identity cannot be present when signal flag is false")

    positive = (
        evidence.rescue_chain_complete,
        evidence.storage_discovery_chain_complete,
        evidence.storage_review_recorded,
        evidence.manual_review_required,
    )
    if any(value is not True for value in positive):
        raise PhysicalBringupSessionError("physical bring-up session is missing a required audit/review flag")
    if not isinstance(evidence.storage_review_accepted_for_strategy_design, bool):
        raise PhysicalBringupSessionError("storage strategy-design acceptance flag must be boolean")
    if not isinstance(evidence.kali_early_userspace_signal_present, bool):
        raise PhysicalBringupSessionError("Kali early-userspace signal flag must be boolean")

    forbidden_claims = (
        evidence.target_selected,
        evidence.storage_path_bound,
        evidence.write_authorized,
        evidence.handoff_ready,
        evidence.storage_verified,
        evidence.charging_battery_verified,
        evidence.display_touch_verified,
        evidence.recovery_verified,
        evidence.kali_early_userspace_verified,
        evidence.phone_storage_written,
        evidence.hardware_verified,
        evidence.beta_gate_credit,
    )
    if any(value is not False for value in forbidden_claims):
        raise PhysicalBringupSessionError("physical bring-up session contains an unsupported target/write/hardware/Beta claim")


def _read_json(path: Path, label: str) -> dict[str, Any]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalBringupSessionError(f"{label} must be a regular non-symlink file")
    before = source.stat()
    raw = source.read_bytes()
    after = source.stat()
    if before.st_size <= 0 or before.st_size > _MAX_EVIDENCE_BYTES or len(raw) != before.st_size:
        raise PhysicalBringupSessionError(f"{label} size is outside the safety limit")
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise PhysicalBringupSessionError(f"{label} changed while being read")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalBringupSessionError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise PhysicalBringupSessionError(f"{label} must be a JSON object")
    return value


def load_physical_bringup_session_evidence(path: Path) -> PhysicalBringupSessionEvidence:
    raw = _read_json(path, "physical bring-up session evidence")
    expected = {item.name for item in fields(PhysicalBringupSessionEvidence)}
    if set(raw) != expected:
        raise PhysicalBringupSessionError("physical bring-up session evidence fields do not match schema-v1")
    try:
        evidence = PhysicalBringupSessionEvidence(**raw)
    except TypeError as exc:
        raise PhysicalBringupSessionError("physical bring-up session evidence types are invalid") from exc
    validate_physical_bringup_session_evidence(evidence)
    return evidence


def write_physical_bringup_session_evidence(
    evidence: PhysicalBringupSessionEvidence,
    destination: Path,
) -> str:
    validate_physical_bringup_session_evidence(evidence)
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise PhysicalBringupSessionError(f"refusing to overwrite physical bring-up session evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise PhysicalBringupSessionError("refusing stale physical bring-up session temporary path")
    payload = evidence.canonical_json()
    try:
        temporary.write_text(payload, encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()
