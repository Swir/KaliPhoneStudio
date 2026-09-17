"""Manual review for one exact physical hardware-presence survey.

This layer records human review of the bounded sysfs-only survey produced during
one exact rescue boot. Acceptance means only that the survey is usable as
context for later subsystem-specific functional testing. It never turns
presence into functional support, hardware verification, or Beta credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from .physical_hardware_survey import (
    PhysicalHardwareSurveyError,
    PhysicalHardwareSurveyEvidence,
    load_physical_hardware_survey_evidence,
    validate_physical_hardware_survey_evidence,
)

_REVIEW_POLICY = "manual-physical-hardware-survey-review-v1"
_ALLOWED_DECISIONS = frozenset({"accepted_as_context", "rejected"})
_MAX_REVIEW_RECORD_BYTES = 512 * 1024
_MAX_REVIEW_NOTES_BYTES = 2 * 1024 * 1024
_SAFE_REVIEWER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+-]{0,127}$")


class PhysicalHardwareReviewError(ValueError):
    pass


@dataclass(frozen=True)
class PhysicalHardwareReviewRecord:
    schema_version: int
    review_policy: str
    profile_id: str
    device_serial: str
    reviewer: str
    decision: str
    physical_context_reviewed: bool
    survey_integrity_reviewed: bool
    usb_presence_reviewed: bool
    network_radio_presence_reviewed: bool
    audio_presence_reviewed: bool
    input_display_presence_reviewed: bool
    thermal_power_presence_reviewed: bool
    limitations_understood: bool
    functional_hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"


@dataclass(frozen=True)
class PhysicalHardwareReviewEvidence:
    schema_version: int
    review_policy: str
    profile_id: str
    device_serial: str
    physical_hardware_survey_sha256: str
    physical_boot_observation_sha256: str
    physical_rescue_diagnostics_sha256: str
    transcript_sha256: str
    rescue_probe_id: str
    normalized_survey_sha256: str
    survey_record_count: int
    review_record_sha256: str
    review_record_size: int
    review_notes_sha256: str
    review_notes_size: int
    reviewer: str
    decision: str
    physical_context_reviewed: bool
    survey_integrity_reviewed: bool
    usb_presence_reviewed: bool
    network_radio_presence_reviewed: bool
    audio_presence_reviewed: bool
    input_display_presence_reviewed: bool
    thermal_power_presence_reviewed: bool
    limitations_understood: bool
    review_checks_complete: bool
    review_recorded: bool
    accepted_as_context: bool
    functional_testing_required: bool
    usb_signal_observed: bool
    network_signal_observed: bool
    wifi_signal_observed: bool
    bluetooth_signal_observed: bool
    audio_signal_observed: bool
    thermal_signal_observed: bool
    input_signal_observed: bool
    display_signal_observed: bool
    power_signal_observed: bool
    display_verified: bool
    touch_verified: bool
    usb_verified: bool
    wifi_verified: bool
    bluetooth_verified: bool
    audio_verified: bool
    modem_verified: bool
    power_charging_verified: bool
    thermal_verified: bool
    storage_verified: bool
    recovery_verified: bool
    phone_storage_written: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _safe_text(value: object, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise PhysicalHardwareReviewError(f"{label} must be non-empty bounded text")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise PhysicalHardwareReviewError(f"{label} contains control data")
    return value


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise PhysicalHardwareReviewError(f"{label} must be a lowercase SHA-256")
    return value


def _positive(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PhysicalHardwareReviewError(f"{label} must be a positive integer")
    return value


def _read_exact(path: Path, label: str, maximum: int) -> tuple[bytes, str, int]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalHardwareReviewError(f"{label} must be a regular non-symlink file")
    try:
        before = source.stat()
        raw = source.read_bytes()
        after = source.stat()
    except OSError as exc:
        raise PhysicalHardwareReviewError(f"cannot read {label}: {exc}") from exc
    if before.st_size <= 0 or before.st_size > maximum or len(raw) != before.st_size:
        raise PhysicalHardwareReviewError(f"{label} size is outside the safety limit")
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise PhysicalHardwareReviewError(f"{label} changed while being read")
    return raw, sha256(raw).hexdigest(), len(raw)


def parse_physical_hardware_review_record(raw: object) -> PhysicalHardwareReviewRecord:
    expected = {item.name for item in fields(PhysicalHardwareReviewRecord)}
    if not isinstance(raw, dict) or set(raw) != expected:
        raise PhysicalHardwareReviewError("hardware review record fields do not match schema-v1")
    if raw["schema_version"] != 1 or raw["review_policy"] != _REVIEW_POLICY:
        raise PhysicalHardwareReviewError("unsupported hardware review record schema/policy")
    reviewer = raw["reviewer"]
    if not isinstance(reviewer, str) or not _SAFE_REVIEWER_RE.fullmatch(reviewer):
        raise PhysicalHardwareReviewError("hardware reviewer must be a safe bounded identifier")
    if raw["decision"] not in _ALLOWED_DECISIONS:
        raise PhysicalHardwareReviewError("hardware review decision is unsupported")
    flags = (
        "physical_context_reviewed",
        "survey_integrity_reviewed",
        "usb_presence_reviewed",
        "network_radio_presence_reviewed",
        "audio_presence_reviewed",
        "input_display_presence_reviewed",
        "thermal_power_presence_reviewed",
        "limitations_understood",
        "functional_hardware_verified",
        "beta_gate_credit",
    )
    for name in flags:
        if not isinstance(raw[name], bool):
            raise PhysicalHardwareReviewError(f"{name} must be boolean")
    if raw["functional_hardware_verified"] is not False or raw["beta_gate_credit"] is not False:
        raise PhysicalHardwareReviewError("hardware survey review cannot grant functional/Beta credit")
    return PhysicalHardwareReviewRecord(**raw)


def load_physical_hardware_review_record(path: Path) -> tuple[PhysicalHardwareReviewRecord, str, int]:
    raw, digest, size = _read_exact(path, "hardware review record", _MAX_REVIEW_RECORD_BYTES)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalHardwareReviewError("hardware review record is not valid UTF-8 JSON") from exc
    record = parse_physical_hardware_review_record(value)
    if raw != record.canonical_json().encode("utf-8"):
        raise PhysicalHardwareReviewError("hardware review record is not canonical JSON")
    return record, digest, size


def read_physical_hardware_review_notes(path: Path) -> tuple[str, int]:
    raw, digest, size = _read_exact(path, "hardware review notes", _MAX_REVIEW_NOTES_BYTES)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PhysicalHardwareReviewError("hardware review notes must be UTF-8") from exc
    if not text.strip() or "\x00" in text:
        raise PhysicalHardwareReviewError("hardware review notes are empty or contain NUL data")
    return digest, size


def make_rejected_hardware_review_record(
    survey: PhysicalHardwareSurveyEvidence,
    reviewer: str,
) -> PhysicalHardwareReviewRecord:
    try:
        validate_physical_hardware_survey_evidence(survey)
    except PhysicalHardwareSurveyError as exc:
        raise PhysicalHardwareReviewError(str(exc)) from exc
    if not isinstance(reviewer, str) or not _SAFE_REVIEWER_RE.fullmatch(reviewer):
        raise PhysicalHardwareReviewError("hardware reviewer must be a safe bounded identifier")
    return PhysicalHardwareReviewRecord(
        schema_version=1,
        review_policy=_REVIEW_POLICY,
        profile_id=survey.profile_id,
        device_serial=survey.device_serial,
        reviewer=reviewer,
        decision="rejected",
        physical_context_reviewed=False,
        survey_integrity_reviewed=False,
        usb_presence_reviewed=False,
        network_radio_presence_reviewed=False,
        audio_presence_reviewed=False,
        input_display_presence_reviewed=False,
        thermal_power_presence_reviewed=False,
        limitations_understood=False,
        functional_hardware_verified=False,
        beta_gate_credit=False,
    )


def bind_physical_hardware_review(
    survey: PhysicalHardwareSurveyEvidence,
    review: PhysicalHardwareReviewRecord,
    *,
    review_record_sha256: str,
    review_record_size: int,
    review_notes_sha256: str,
    review_notes_size: int,
) -> PhysicalHardwareReviewEvidence:
    try:
        validate_physical_hardware_survey_evidence(survey)
    except PhysicalHardwareSurveyError as exc:
        raise PhysicalHardwareReviewError(str(exc)) from exc
    if review.profile_id != survey.profile_id or review.device_serial != survey.device_serial:
        raise PhysicalHardwareReviewError("hardware review identity does not match survey")
    checks = (
        review.physical_context_reviewed,
        review.survey_integrity_reviewed,
        review.usb_presence_reviewed,
        review.network_radio_presence_reviewed,
        review.audio_presence_reviewed,
        review.input_display_presence_reviewed,
        review.thermal_power_presence_reviewed,
        review.limitations_understood,
    )
    complete = all(checks)
    accepted = (
        review.decision == "accepted_as_context"
        and survey.hardware_survey_recorded is True
        and survey.manual_review_required is True
        and survey.survey_record_count > 0
        and complete
    )
    if review.decision == "accepted_as_context" and not accepted:
        raise PhysicalHardwareReviewError(
            "cannot accept hardware survey context until a non-empty exact survey and every review check are complete"
        )
    evidence = PhysicalHardwareReviewEvidence(
        schema_version=1,
        review_policy=_REVIEW_POLICY,
        profile_id=survey.profile_id,
        device_serial=survey.device_serial,
        physical_hardware_survey_sha256=survey.evidence_sha256(),
        physical_boot_observation_sha256=survey.physical_boot_observation_sha256,
        physical_rescue_diagnostics_sha256=survey.physical_rescue_diagnostics_sha256,
        transcript_sha256=survey.transcript_sha256,
        rescue_probe_id=survey.rescue_probe_id,
        normalized_survey_sha256=survey.normalized_survey_sha256,
        survey_record_count=survey.survey_record_count,
        review_record_sha256=_sha(review_record_sha256, "hardware review record"),
        review_record_size=_positive(review_record_size, "hardware review record size"),
        review_notes_sha256=_sha(review_notes_sha256, "hardware review notes"),
        review_notes_size=_positive(review_notes_size, "hardware review notes size"),
        reviewer=review.reviewer,
        decision=review.decision,
        physical_context_reviewed=review.physical_context_reviewed,
        survey_integrity_reviewed=review.survey_integrity_reviewed,
        usb_presence_reviewed=review.usb_presence_reviewed,
        network_radio_presence_reviewed=review.network_radio_presence_reviewed,
        audio_presence_reviewed=review.audio_presence_reviewed,
        input_display_presence_reviewed=review.input_display_presence_reviewed,
        thermal_power_presence_reviewed=review.thermal_power_presence_reviewed,
        limitations_understood=review.limitations_understood,
        review_checks_complete=complete,
        review_recorded=True,
        accepted_as_context=accepted,
        functional_testing_required=True,
        usb_signal_observed=survey.usb_signal_observed,
        network_signal_observed=survey.network_signal_observed,
        wifi_signal_observed=survey.wifi_signal_observed,
        bluetooth_signal_observed=survey.bluetooth_signal_observed,
        audio_signal_observed=survey.audio_signal_observed,
        thermal_signal_observed=survey.thermal_signal_observed,
        input_signal_observed=survey.input_signal_observed,
        display_signal_observed=survey.display_signal_observed,
        power_signal_observed=survey.power_signal_observed,
        display_verified=False,
        touch_verified=False,
        usb_verified=False,
        wifi_verified=False,
        bluetooth_verified=False,
        audio_verified=False,
        modem_verified=False,
        power_charging_verified=False,
        thermal_verified=False,
        storage_verified=False,
        recovery_verified=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    validate_physical_hardware_review_evidence(evidence)
    return evidence


def validate_physical_hardware_review_evidence(evidence: PhysicalHardwareReviewEvidence) -> None:
    if not isinstance(evidence, PhysicalHardwareReviewEvidence) or evidence.schema_version != 1:
        raise PhysicalHardwareReviewError("physical hardware review must be schema-v1 typed evidence")
    if evidence.review_policy != _REVIEW_POLICY:
        raise PhysicalHardwareReviewError("physical hardware review policy is unsupported")
    _safe_text(evidence.profile_id, "hardware review profile id", 128)
    _safe_text(evidence.device_serial, "hardware review serial", 256)
    if not _SAFE_REVIEWER_RE.fullmatch(evidence.reviewer):
        raise PhysicalHardwareReviewError("hardware review reviewer identifier is invalid")
    if evidence.decision not in _ALLOWED_DECISIONS:
        raise PhysicalHardwareReviewError("hardware review decision is unsupported")
    for value, label in (
        (evidence.physical_hardware_survey_sha256, "physical hardware survey"),
        (evidence.physical_boot_observation_sha256, "physical boot observation"),
        (evidence.physical_rescue_diagnostics_sha256, "physical rescue diagnostics"),
        (evidence.transcript_sha256, "rescue transcript"),
        (evidence.rescue_probe_id, "rescue probe id"),
        (evidence.normalized_survey_sha256, "normalized hardware survey"),
        (evidence.review_record_sha256, "hardware review record"),
        (evidence.review_notes_sha256, "hardware review notes"),
    ):
        _sha(value, label)
    if not isinstance(evidence.survey_record_count, int) or isinstance(evidence.survey_record_count, bool) or evidence.survey_record_count < 0:
        raise PhysicalHardwareReviewError("hardware review survey count must be a non-negative integer")
    _positive(evidence.review_record_size, "hardware review record size")
    _positive(evidence.review_notes_size, "hardware review notes size")
    checks = (
        evidence.physical_context_reviewed,
        evidence.survey_integrity_reviewed,
        evidence.usb_presence_reviewed,
        evidence.network_radio_presence_reviewed,
        evidence.audio_presence_reviewed,
        evidence.input_display_presence_reviewed,
        evidence.thermal_power_presence_reviewed,
        evidence.limitations_understood,
    )
    signal_flags = (
        evidence.usb_signal_observed,
        evidence.network_signal_observed,
        evidence.wifi_signal_observed,
        evidence.bluetooth_signal_observed,
        evidence.audio_signal_observed,
        evidence.thermal_signal_observed,
        evidence.input_signal_observed,
        evidence.display_signal_observed,
        evidence.power_signal_observed,
    )
    if any(not isinstance(value, bool) for value in checks + signal_flags):
        raise PhysicalHardwareReviewError("hardware review check/signal flags must be boolean")
    if evidence.review_checks_complete is not all(checks):
        raise PhysicalHardwareReviewError("hardware review completeness flag drifted")
    expected_accepted = evidence.decision == "accepted_as_context" and evidence.survey_record_count > 0 and evidence.review_checks_complete
    if evidence.accepted_as_context is not expected_accepted:
        raise PhysicalHardwareReviewError("hardware review contextual acceptance flag drifted")
    if evidence.review_recorded is not True or evidence.functional_testing_required is not True:
        raise PhysicalHardwareReviewError("hardware review is missing required audit flags")
    if any(value is not False for value in (
        evidence.display_verified,
        evidence.touch_verified,
        evidence.usb_verified,
        evidence.wifi_verified,
        evidence.bluetooth_verified,
        evidence.audio_verified,
        evidence.modem_verified,
        evidence.power_charging_verified,
        evidence.thermal_verified,
        evidence.storage_verified,
        evidence.recovery_verified,
        evidence.phone_storage_written,
        evidence.hardware_verified,
        evidence.beta_gate_credit,
    )):
        raise PhysicalHardwareReviewError("hardware survey review contains unsupported functional/write/hardware/Beta claim")


def load_physical_hardware_review_evidence(path: Path) -> PhysicalHardwareReviewEvidence:
    raw, _digest_value, _size = _read_exact(path, "hardware review evidence", 4 * 1024 * 1024)
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalHardwareReviewError("hardware review evidence is not valid UTF-8 JSON") from exc
    expected = {item.name for item in fields(PhysicalHardwareReviewEvidence)}
    if not isinstance(value, dict) or set(value) != expected:
        raise PhysicalHardwareReviewError("hardware review evidence fields do not match schema-v1")
    try:
        evidence = PhysicalHardwareReviewEvidence(**value)
        validate_physical_hardware_review_evidence(evidence)
    except (TypeError, PhysicalHardwareReviewError) as exc:
        raise PhysicalHardwareReviewError("hardware review evidence is invalid") from exc
    if raw != evidence.canonical_json().encode("utf-8"):
        raise PhysicalHardwareReviewError("hardware review evidence is not canonical JSON")
    return evidence


def write_physical_hardware_review_evidence(evidence: PhysicalHardwareReviewEvidence, destination: Path) -> str:
    validate_physical_hardware_review_evidence(evidence)
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise PhysicalHardwareReviewError("refusing to overwrite existing hardware review evidence")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = evidence.canonical_json()
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
    except OSError as exc:
        raise PhysicalHardwareReviewError(f"cannot write hardware review evidence: {exc}") from exc
    return evidence.evidence_sha256()


def review_physical_hardware_survey_files(
    survey_evidence_path: Path,
    review_record_path: Path,
    review_notes_path: Path,
) -> PhysicalHardwareReviewEvidence:
    try:
        survey = load_physical_hardware_survey_evidence(survey_evidence_path)
    except PhysicalHardwareSurveyError as exc:
        raise PhysicalHardwareReviewError(str(exc)) from exc
    record, record_sha, record_size = load_physical_hardware_review_record(review_record_path)
    notes_sha, notes_size = read_physical_hardware_review_notes(review_notes_path)
    return bind_physical_hardware_review(
        survey,
        record,
        review_record_sha256=record_sha,
        review_record_size=record_size,
        review_notes_sha256=notes_sha,
        review_notes_size=notes_size,
    )
