"""Bind post-fastboot physical console observations to one exact rescue candidate.

This module never talks to a phone. It consumes immutable evidence from the
single-command temporary-boot executor plus an operator-captured console/log
transcript. A transcript is accepted only when it contains the exact deterministic
rescue probe id embedded into the reviewed rescue ramdisk and the explicit
``init-reached`` stage marker.

Even a matching transcript remains *unreviewed physical observation evidence*.
It does not automatically prove Kali rootfs, storage, charging, display/touch,
recovery, hardware support, or Beta readiness.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .profiles import DeviceProfile
from .rescue_candidate import (
    RescueCandidateEvidence,
    validate_rescue_candidate_evidence,
)
from .temporary_boot_execution import TemporaryBootExecutionEvidence


MAX_TRANSCRIPT_BYTES = 8 * 1024 * 1024
MAX_MARKER_DUPLICATES = 8
_STAGE_MARKER = b"KPS_RESCUE_STAGE=init-reached-v1"
_PROBE_PREFIX = b"KPS_RESCUE_PROBE_ID="
_OBSERVATION_POLICY = "exact-rescue-probe-console-binding-v1"


class PhysicalBootObservationError(ValueError):
    pass


@dataclass(frozen=True)
class PhysicalBootObservationEvidence:
    schema_version: int
    profile_id: str
    device_serial: str
    execution_evidence_sha256: str
    offer_sha256: str
    rescue_candidate_evidence_sha256: str
    rescue_ramdisk_sha256: str
    rescue_probe_id: str
    transcript_sha256: str
    transcript_size: int
    stage_marker_count: int
    probe_marker_count: int
    observation_policy: str
    physical_observation_recorded: bool
    temporary_boot_command_succeeded: bool
    rescue_init_observed: bool
    kali_early_userspace_verified: bool
    storage_verified: bool
    display_touch_verified: bool
    charging_battery_verified: bool
    recovery_verified: bool
    manual_review_required: bool
    phone_storage_written: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalBootObservationError(f"{label} must be a regular non-symlink file")
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise PhysicalBootObservationError(f"cannot read {label}: {exc}") from exc
    if not raw or len(raw) > 2 * 1024 * 1024:
        raise PhysicalBootObservationError(f"{label} size is outside the safety limit")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalBootObservationError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise PhysicalBootObservationError(f"{label} must be a JSON object")
    return value


def load_temporary_boot_execution_evidence(path: Path) -> TemporaryBootExecutionEvidence:
    raw = _load_json(path, "temporary-boot execution evidence")
    expected = {item.name for item in fields(TemporaryBootExecutionEvidence)}
    if set(raw) != expected:
        raise PhysicalBootObservationError("temporary-boot execution evidence fields do not match schema-v1")
    try:
        evidence = TemporaryBootExecutionEvidence(**raw)
    except TypeError as exc:
        raise PhysicalBootObservationError("temporary-boot execution evidence types are invalid") from exc
    validate_temporary_boot_execution_evidence(evidence)
    return evidence


def validate_temporary_boot_execution_evidence(evidence: TemporaryBootExecutionEvidence) -> None:
    if not isinstance(evidence, TemporaryBootExecutionEvidence) or evidence.schema_version != 1:
        raise PhysicalBootObservationError("temporary-boot execution must be schema-v1 typed evidence")
    if not isinstance(evidence.profile_id, str) or "/" not in evidence.profile_id:
        raise PhysicalBootObservationError("temporary-boot execution profile_id is invalid")
    if not isinstance(evidence.device_serial, str) or not evidence.device_serial:
        raise PhysicalBootObservationError("temporary-boot execution serial is invalid")
    if evidence.returncode != 0 or evidence.temporary_boot_command_succeeded is not True:
        raise PhysicalBootObservationError("physical boot observation requires a successful Fastboot boot command")
    if evidence.command_invoked is not True or evidence.temporary_boot_executed is not True:
        raise PhysicalBootObservationError("temporary-boot execution evidence does not record an invoked boot")
    if (
        evidence.persistent_write is not False
        or evidence.phone_storage_written is not False
        or evidence.kali_userspace_verified is not False
        or evidence.hardware_verified is not False
        or evidence.beta_gate_credit is not False
    ):
        raise PhysicalBootObservationError("temporary-boot execution evidence contains an invalid physical claim")
    for value, label in (
        (evidence.offer_sha256, "offer"),
        (evidence.authorization_sha256, "authorization"),
        (evidence.runtime_probe_sha256, "runtime probe"),
        (evidence.argv_sha256, "argv"),
        (evidence.output_sha256, "output"),
    ):
        if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
            raise PhysicalBootObservationError(f"temporary-boot {label} digest is invalid")
    if not isinstance(evidence.output_size, int) or isinstance(evidence.output_size, bool) or evidence.output_size < 0:
        raise PhysicalBootObservationError("temporary-boot output size is invalid")


def _read_transcript(path: Path) -> bytes:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalBootObservationError("physical console transcript must be a regular non-symlink file")
    try:
        before = source.stat()
    except OSError as exc:
        raise PhysicalBootObservationError(f"cannot stat physical console transcript: {exc}") from exc
    if before.st_size <= 0 or before.st_size > MAX_TRANSCRIPT_BYTES:
        raise PhysicalBootObservationError("physical console transcript size is outside the safety limit")
    try:
        payload = source.read_bytes()
        after = source.stat()
    except OSError as exc:
        raise PhysicalBootObservationError(f"cannot read physical console transcript: {exc}") from exc
    if len(payload) != before.st_size or (
        before.st_size,
        before.st_mtime_ns,
        before.st_ino,
    ) != (
        after.st_size,
        after.st_mtime_ns,
        after.st_ino,
    ):
        raise PhysicalBootObservationError("physical console transcript changed while being verified")
    return payload


def _marker_counts(payload: bytes, expected_probe_id: str) -> tuple[int, int]:
    normalized = payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    lines = normalized.split(b"\n")
    expected_probe = _PROBE_PREFIX + expected_probe_id.encode("ascii")
    stage_count = sum(line == _STAGE_MARKER for line in lines)
    probe_count = sum(line == expected_probe for line in lines)
    stage_lines = {line for line in lines if line.startswith(b"KPS_RESCUE_STAGE=")}
    probe_lines = {line for line in lines if line.startswith(_PROBE_PREFIX)}
    if stage_lines - {_STAGE_MARKER}:
        raise PhysicalBootObservationError("physical console transcript contains a conflicting rescue stage marker")
    if probe_lines - {expected_probe}:
        raise PhysicalBootObservationError("physical console transcript contains a conflicting rescue probe id")
    if stage_count < 1 or probe_count < 1:
        raise PhysicalBootObservationError("physical console transcript does not contain the exact rescue proof markers")
    if stage_count > MAX_MARKER_DUPLICATES or probe_count > MAX_MARKER_DUPLICATES:
        raise PhysicalBootObservationError("physical console transcript contains an implausible number of rescue proof markers")
    return stage_count, probe_count


def record_physical_boot_observation(
    profile: DeviceProfile,
    execution: TemporaryBootExecutionEvidence,
    rescue: RescueCandidateEvidence,
    console_transcript: Path,
) -> PhysicalBootObservationEvidence:
    """Create unreviewed physical observation evidence from exact rescue markers.

    The function is deliberately offline: it does not execute Fastboot, open a
    serial port, or modify phone storage. It only binds an already captured raw
    transcript to exact prior execution/rescue evidence.
    """
    validate_temporary_boot_execution_evidence(execution)
    try:
        validate_rescue_candidate_evidence(rescue)
    except ValueError as exc:
        raise PhysicalBootObservationError(str(exc)) from exc
    if profile.profile_id != execution.profile_id or profile.profile_id != rescue.profile_id:
        raise PhysicalBootObservationError("profile, temporary-boot execution and rescue candidate do not match")
    payload = _read_transcript(console_transcript)
    stage_count, probe_count = _marker_counts(payload, rescue.rescue_probe_id)
    evidence = PhysicalBootObservationEvidence(
        schema_version=1,
        profile_id=profile.profile_id,
        device_serial=execution.device_serial,
        execution_evidence_sha256=execution.evidence_sha256(),
        offer_sha256=execution.offer_sha256,
        rescue_candidate_evidence_sha256=rescue.evidence_sha256(),
        rescue_ramdisk_sha256=rescue.ramdisk_sha256,
        rescue_probe_id=rescue.rescue_probe_id,
        transcript_sha256=sha256(payload).hexdigest(),
        transcript_size=len(payload),
        stage_marker_count=stage_count,
        probe_marker_count=probe_count,
        observation_policy=_OBSERVATION_POLICY,
        physical_observation_recorded=True,
        temporary_boot_command_succeeded=True,
        rescue_init_observed=True,
        kali_early_userspace_verified=False,
        storage_verified=False,
        display_touch_verified=False,
        charging_battery_verified=False,
        recovery_verified=False,
        manual_review_required=True,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    validate_physical_boot_observation_evidence(evidence)
    return evidence


def validate_physical_boot_observation_evidence(evidence: PhysicalBootObservationEvidence) -> None:
    if not isinstance(evidence, PhysicalBootObservationEvidence) or evidence.schema_version != 1:
        raise PhysicalBootObservationError("physical boot observation must be schema-v1 typed evidence")
    for value, label in (
        (evidence.execution_evidence_sha256, "execution evidence"),
        (evidence.offer_sha256, "offer"),
        (evidence.rescue_candidate_evidence_sha256, "rescue candidate evidence"),
        (evidence.rescue_ramdisk_sha256, "rescue ramdisk"),
        (evidence.rescue_probe_id, "rescue probe id"),
        (evidence.transcript_sha256, "console transcript"),
    ):
        if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
            raise PhysicalBootObservationError(f"{label} digest/id is invalid")
    if evidence.observation_policy != _OBSERVATION_POLICY:
        raise PhysicalBootObservationError("physical boot observation policy is unsupported")
    if evidence.transcript_size <= 0 or evidence.transcript_size > MAX_TRANSCRIPT_BYTES:
        raise PhysicalBootObservationError("physical boot observation transcript size is invalid")
    if not (1 <= evidence.stage_marker_count <= MAX_MARKER_DUPLICATES):
        raise PhysicalBootObservationError("physical boot observation stage marker count is invalid")
    if not (1 <= evidence.probe_marker_count <= MAX_MARKER_DUPLICATES):
        raise PhysicalBootObservationError("physical boot observation probe marker count is invalid")
    if (
        evidence.physical_observation_recorded is not True
        or evidence.temporary_boot_command_succeeded is not True
        or evidence.rescue_init_observed is not True
        or evidence.manual_review_required is not True
    ):
        raise PhysicalBootObservationError("physical boot observation is missing required positive observation flags")
    if (
        evidence.kali_early_userspace_verified is not False
        or evidence.storage_verified is not False
        or evidence.display_touch_verified is not False
        or evidence.charging_battery_verified is not False
        or evidence.recovery_verified is not False
        or evidence.phone_storage_written is not False
        or evidence.hardware_verified is not False
        or evidence.beta_gate_credit is not False
    ):
        raise PhysicalBootObservationError("physical boot observation contains an unsupported hardware/Beta claim")


def write_physical_boot_observation_evidence(
    evidence: PhysicalBootObservationEvidence,
    destination: Path,
) -> str:
    validate_physical_boot_observation_evidence(evidence)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise PhysicalBootObservationError("refusing to overwrite physical boot observation evidence")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise PhysicalBootObservationError("refusing to overwrite physical boot observation temporary path")
    temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
    temporary.replace(destination)
    return evidence.evidence_sha256()
