"""Parse read-only rescue diagnostics from one exact physical boot transcript.

The rescue init emits a bounded machine-readable inventory between one BEGIN/END
pair after its exact candidate probe markers. This module only parses a transcript
already bound by PhysicalBootObservationEvidence; it performs no phone I/O and
never converts inventory signals into hardware/Beta verification.

New rescue-diagnostic records are admitted only from schema-v2 physical boot
observations, which carry the exact runtime-probe, recovery-readiness and
post-probe material-revalidation chain. Historical schema-v1 observations remain
loadable and validatable for audit/readback, but cannot seed a new rescue campaign.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from .physical_boot_observation import (
    MAX_TRANSCRIPT_BYTES,
    PhysicalBootObservationEvidence,
    PhysicalBootObservationError,
    validate_physical_boot_observation_evidence,
)
from .profiles import DeviceProfile

_DIAG_POLICY = "readonly-sysfs-inventory-v1"
_BEGIN = f"KPS_DIAG_BEGIN={_DIAG_POLICY}"
_END = f"KPS_DIAG_END={_DIAG_POLICY}"
_PREFIX = "KPS_DIAG_"
_MAX_RECORDS = 512
_MAX_RECORD_VALUE = 128
_SAFE_VALUE_RE = re.compile(r"^[A-Za-z0-9._:+-]{1,128}$")
_ALLOWED_KINDS = {
    "BLOCK": 3,
    "SCSI_HOST": 2,
    "POWER": 8,
    "INPUT": 2,
    "GRAPHICS": 2,
    "DRM": 2,
}


class PhysicalRescueDiagnosticsError(ValueError):
    pass


@dataclass(frozen=True)
class RescueDiagnosticRecord:
    kind: str
    values: tuple[str, ...]

    def canonical_line(self) -> str:
        return f"{self.kind}=" + "|".join(self.values)


@dataclass(frozen=True)
class PhysicalRescueDiagnosticsEvidence:
    schema_version: int
    profile_id: str
    device_serial: str
    physical_boot_observation_sha256: str
    transcript_sha256: str
    rescue_probe_id: str
    diagnostics_policy: str
    normalized_diagnostics_sha256: str
    diagnostic_record_count: int
    block_record_count: int
    scsi_host_record_count: int
    power_record_count: int
    input_record_count: int
    graphics_record_count: int
    drm_record_count: int
    ufs_signal_observed: bool
    battery_signal_observed: bool
    input_signal_observed: bool
    graphics_signal_observed: bool
    records: tuple[RescueDiagnosticRecord, ...]
    physical_diagnostics_recorded: bool
    manual_review_required: bool
    storage_verified: bool
    display_touch_verified: bool
    charging_battery_verified: bool
    recovery_verified: bool
    phone_storage_written: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise PhysicalRescueDiagnosticsError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _read_transcript(path: Path, expected: PhysicalBootObservationEvidence) -> bytes:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalRescueDiagnosticsError("rescue diagnostics transcript must be a regular non-symlink file")
    try:
        before = source.stat()
        payload = source.read_bytes()
        after = source.stat()
    except OSError as exc:
        raise PhysicalRescueDiagnosticsError(f"cannot read rescue diagnostics transcript: {exc}") from exc
    if before.st_size <= 0 or before.st_size > MAX_TRANSCRIPT_BYTES:
        raise PhysicalRescueDiagnosticsError("rescue diagnostics transcript size is outside the safety limit")
    if len(payload) != before.st_size or (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise PhysicalRescueDiagnosticsError("rescue diagnostics transcript changed while being verified")
    actual = sha256(payload).hexdigest()
    if actual != expected.transcript_sha256 or len(payload) != expected.transcript_size:
        raise PhysicalRescueDiagnosticsError("rescue diagnostics transcript is not the transcript bound by physical boot observation")
    return payload


def _parse_record(line: str) -> RescueDiagnosticRecord:
    if not line.startswith(_PREFIX) or "=" not in line:
        raise PhysicalRescueDiagnosticsError("invalid rescue diagnostic record")
    key, raw = line[len(_PREFIX):].split("=", 1)
    if key not in _ALLOWED_KINDS:
        raise PhysicalRescueDiagnosticsError(f"unsupported rescue diagnostic record kind: {key}")
    values = tuple(raw.split("|"))
    if len(values) != _ALLOWED_KINDS[key]:
        raise PhysicalRescueDiagnosticsError(f"rescue diagnostic {key} field count drifted")
    for value in values:
        if len(value) > _MAX_RECORD_VALUE or not _SAFE_VALUE_RE.fullmatch(value):
            raise PhysicalRescueDiagnosticsError(f"rescue diagnostic {key} contains unsafe field data")
    return RescueDiagnosticRecord(kind=key, values=values)


def _extract_records(payload: bytes, expected_probe_id: str) -> tuple[RescueDiagnosticRecord, ...]:
    lines = payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"\n")
    begin_marker, end_marker = _BEGIN.encode("ascii"), _END.encode("ascii")
    begins = [i for i, line in enumerate(lines) if line == begin_marker]
    ends = [i for i, line in enumerate(lines) if line == end_marker]
    if len(begins) != 1 or len(ends) != 1:
        raise PhysicalRescueDiagnosticsError("rescue diagnostics transcript must contain exactly one diagnostic block")
    begin, end = begins[0], ends[0]
    if begin >= end:
        raise PhysicalRescueDiagnosticsError("rescue diagnostics block order is invalid")
    expected_probe = f"KPS_RESCUE_PROBE_ID={expected_probe_id}".encode("ascii")
    stage_marker = b"KPS_RESCUE_STAGE=init-reached-v1"
    probe_positions = [i for i, line in enumerate(lines) if line == expected_probe]
    stage_positions = [i for i, line in enumerate(lines) if line == stage_marker]
    if not probe_positions or not stage_positions or min(probe_positions) >= begin or min(stage_positions) >= begin:
        raise PhysicalRescueDiagnosticsError("rescue diagnostics block is not preceded by exact rescue proof markers")
    prefix = _PREFIX.encode("ascii")
    for i, line in enumerate(lines):
        if line.startswith(prefix) and line not in {begin_marker, end_marker} and not (begin < i < end):
            raise PhysicalRescueDiagnosticsError("rescue diagnostic marker appears outside the locked diagnostic block")
    record_lines = [line for line in lines[begin + 1:end] if line]
    if len(record_lines) > _MAX_RECORDS:
        raise PhysicalRescueDiagnosticsError("rescue diagnostic record count exceeds safety limit")
    result: list[RescueDiagnosticRecord] = []
    for line in record_lines:
        try:
            text = line.decode("ascii", errors="strict")
        except UnicodeDecodeError as exc:
            raise PhysicalRescueDiagnosticsError("machine-readable rescue diagnostic record is not ASCII-clean") from exc
        result.append(_parse_record(text))
    return tuple(result)


def _normalized_digest(records: tuple[RescueDiagnosticRecord, ...]) -> str:
    payload = (_BEGIN + "\n" + "\n".join(f"KPS_DIAG_{item.canonical_line()}" for item in records) + "\n" + _END + "\n").encode("ascii")
    return sha256(payload).hexdigest()


def _contains_ufs(records: tuple[RescueDiagnosticRecord, ...]) -> bool:
    return any(record.kind == "SCSI_HOST" and any("ufs" in value.lower() for value in record.values) for record in records)


def _contains_battery(records: tuple[RescueDiagnosticRecord, ...]) -> bool:
    return any(record.kind == "POWER" and ("battery" in record.values[0].lower() or "battery" in record.values[1].lower()) for record in records)


def require_current_physical_boot_observation_for_rescue(
    observation: PhysicalBootObservationEvidence,
) -> None:
    """Require the current exact runtime/recovery-bound physical observation.

    Generic observation validation intentionally remains backward compatible with
    schema-v1 evidence so historical campaigns stay auditable. New rescue evidence
    must not be created from that legacy shape because it predates the exact
    runtime-probe, recovery-readiness and post-probe revalidation binding.
    """
    try:
        validate_physical_boot_observation_evidence(observation)
    except PhysicalBootObservationError as exc:
        raise PhysicalRescueDiagnosticsError(str(exc)) from exc
    if observation.schema_version != 2:
        raise PhysicalRescueDiagnosticsError(
            "new rescue evidence requires schema-v2 physical boot observation with exact runtime/recovery binding"
        )


def record_physical_rescue_diagnostics(profile: DeviceProfile, observation: PhysicalBootObservationEvidence, console_transcript: Path) -> PhysicalRescueDiagnosticsEvidence:
    """Bind read-only inventory to one current exact physical transcript."""
    require_current_physical_boot_observation_for_rescue(observation)
    if not isinstance(profile, DeviceProfile) or profile.profile_id != observation.profile_id:
        raise PhysicalRescueDiagnosticsError("profile does not match physical boot observation")
    payload = _read_transcript(console_transcript, observation)
    records = _extract_records(payload, observation.rescue_probe_id)
    counts = {kind: sum(item.kind == kind for item in records) for kind in _ALLOWED_KINDS}
    evidence = PhysicalRescueDiagnosticsEvidence(
        schema_version=1,
        profile_id=observation.profile_id,
        device_serial=observation.device_serial,
        physical_boot_observation_sha256=observation.evidence_sha256(),
        transcript_sha256=observation.transcript_sha256,
        rescue_probe_id=observation.rescue_probe_id,
        diagnostics_policy=_DIAG_POLICY,
        normalized_diagnostics_sha256=_normalized_digest(records),
        diagnostic_record_count=len(records),
        block_record_count=counts["BLOCK"],
        scsi_host_record_count=counts["SCSI_HOST"],
        power_record_count=counts["POWER"],
        input_record_count=counts["INPUT"],
        graphics_record_count=counts["GRAPHICS"],
        drm_record_count=counts["DRM"],
        ufs_signal_observed=_contains_ufs(records),
        battery_signal_observed=_contains_battery(records),
        input_signal_observed=counts["INPUT"] > 0,
        graphics_signal_observed=(counts["GRAPHICS"] + counts["DRM"]) > 0,
        records=records,
        physical_diagnostics_recorded=True,
        manual_review_required=True,
        storage_verified=False,
        display_touch_verified=False,
        charging_battery_verified=False,
        recovery_verified=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    validate_physical_rescue_diagnostics_evidence(evidence)
    return evidence


def validate_physical_rescue_diagnostics_evidence(evidence: PhysicalRescueDiagnosticsEvidence) -> None:
    if not isinstance(evidence, PhysicalRescueDiagnosticsEvidence) or evidence.schema_version != 1:
        raise PhysicalRescueDiagnosticsError("physical rescue diagnostics must be schema-v1 typed evidence")
    if not isinstance(evidence.profile_id, str) or "/" not in evidence.profile_id:
        raise PhysicalRescueDiagnosticsError("physical rescue diagnostics profile_id is invalid")
    if not isinstance(evidence.device_serial, str) or not evidence.device_serial:
        raise PhysicalRescueDiagnosticsError("physical rescue diagnostics serial is invalid")
    for value, label in ((evidence.physical_boot_observation_sha256, "physical boot observation"), (evidence.transcript_sha256, "transcript"), (evidence.rescue_probe_id, "rescue probe id"), (evidence.normalized_diagnostics_sha256, "normalized diagnostics")):
        _digest(value, label)
    if evidence.diagnostics_policy != _DIAG_POLICY:
        raise PhysicalRescueDiagnosticsError("physical rescue diagnostics policy is unsupported")
    if not isinstance(evidence.records, tuple) or len(evidence.records) > _MAX_RECORDS:
        raise PhysicalRescueDiagnosticsError("physical rescue diagnostics records are invalid")
    recomputed = {kind: 0 for kind in _ALLOWED_KINDS}
    for record in evidence.records:
        if not isinstance(record, RescueDiagnosticRecord) or _parse_record(f"KPS_DIAG_{record.canonical_line()}") != record:
            raise PhysicalRescueDiagnosticsError("physical rescue diagnostic record canonicalization drifted")
        recomputed[record.kind] += 1
    count_values = (evidence.diagnostic_record_count, evidence.block_record_count, evidence.scsi_host_record_count, evidence.power_record_count, evidence.input_record_count, evidence.graphics_record_count, evidence.drm_record_count)
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in count_values):
        raise PhysicalRescueDiagnosticsError("physical rescue diagnostic counts must be non-negative integers")
    actual_counts = tuple(recomputed[k] for k in ("BLOCK", "SCSI_HOST", "POWER", "INPUT", "GRAPHICS", "DRM"))
    if count_values[1:] != actual_counts or evidence.diagnostic_record_count != len(evidence.records):
        raise PhysicalRescueDiagnosticsError("physical rescue diagnostic counts drifted")
    if evidence.normalized_diagnostics_sha256 != _normalized_digest(evidence.records):
        raise PhysicalRescueDiagnosticsError("physical rescue normalized diagnostic digest drifted")
    if evidence.ufs_signal_observed is not _contains_ufs(evidence.records):
        raise PhysicalRescueDiagnosticsError("physical rescue UFS signal flag drifted")
    if evidence.battery_signal_observed is not _contains_battery(evidence.records):
        raise PhysicalRescueDiagnosticsError("physical rescue battery signal flag drifted")
    if evidence.input_signal_observed is not (recomputed["INPUT"] > 0):
        raise PhysicalRescueDiagnosticsError("physical rescue input signal flag drifted")
    if evidence.graphics_signal_observed is not ((recomputed["GRAPHICS"] + recomputed["DRM"]) > 0):
        raise PhysicalRescueDiagnosticsError("physical rescue graphics signal flag drifted")
    if evidence.physical_diagnostics_recorded is not True or evidence.manual_review_required is not True:
        raise PhysicalRescueDiagnosticsError("physical rescue diagnostics are missing review/record flags")
    if (evidence.storage_verified is not False or evidence.display_touch_verified is not False or evidence.charging_battery_verified is not False or evidence.recovery_verified is not False or evidence.phone_storage_written is not False or evidence.hardware_verified is not False or evidence.beta_gate_credit is not False):
        raise PhysicalRescueDiagnosticsError("physical rescue diagnostics contain an unsupported hardware/Beta claim")


def load_physical_boot_observation_for_diagnostics(path: Path) -> PhysicalBootObservationEvidence:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalRescueDiagnosticsError("physical boot observation evidence must be a regular non-symlink file")
    raw_bytes = source.read_bytes()
    if not raw_bytes or len(raw_bytes) > 2 * 1024 * 1024:
        raise PhysicalRescueDiagnosticsError("physical boot observation evidence size is outside the safety limit")
    try:
        raw = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalRescueDiagnosticsError("physical boot observation evidence is not valid UTF-8 JSON") from exc
    if not isinstance(raw, dict) or set(raw) != {item.name for item in fields(PhysicalBootObservationEvidence)}:
        raise PhysicalRescueDiagnosticsError("physical boot observation evidence fields do not match schema-v1/v2")
    try:
        evidence = PhysicalBootObservationEvidence(**raw)
        validate_physical_boot_observation_evidence(evidence)
    except (TypeError, PhysicalBootObservationError) as exc:
        raise PhysicalRescueDiagnosticsError("physical boot observation evidence is invalid") from exc
    return evidence


def load_physical_rescue_diagnostics_evidence(path: Path) -> PhysicalRescueDiagnosticsEvidence:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalRescueDiagnosticsError("physical rescue diagnostics evidence must be a regular non-symlink file")
    raw_bytes = source.read_bytes()
    if not raw_bytes or len(raw_bytes) > 4 * 1024 * 1024:
        raise PhysicalRescueDiagnosticsError("physical rescue diagnostics evidence size is outside the safety limit")
    try:
        raw: Any = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalRescueDiagnosticsError("physical rescue diagnostics evidence is not valid UTF-8 JSON") from exc
    if not isinstance(raw, dict) or set(raw) != {item.name for item in fields(PhysicalRescueDiagnosticsEvidence)}:
        raise PhysicalRescueDiagnosticsError("physical rescue diagnostics fields do not match schema-v1")
    records = raw.get("records")
    if not isinstance(records, list):
        raise PhysicalRescueDiagnosticsError("physical rescue diagnostics records are malformed")
    typed: list[RescueDiagnosticRecord] = []
    for item in records:
        if not isinstance(item, dict) or set(item) != {"kind", "values"} or not isinstance(item.get("values"), list):
            raise PhysicalRescueDiagnosticsError("physical rescue diagnostic record is malformed")
        typed.append(RescueDiagnosticRecord(kind=item["kind"], values=tuple(item["values"])))
    raw["records"] = tuple(typed)
    try:
        evidence = PhysicalRescueDiagnosticsEvidence(**raw)
    except TypeError as exc:
        raise PhysicalRescueDiagnosticsError("physical rescue diagnostics evidence types are invalid") from exc
    validate_physical_rescue_diagnostics_evidence(evidence)
    return evidence


def write_physical_rescue_diagnostics_evidence(evidence: PhysicalRescueDiagnosticsEvidence, destination: Path) -> str:
    validate_physical_rescue_diagnostics_evidence(evidence)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise PhysicalRescueDiagnosticsError("refusing to overwrite physical rescue diagnostics evidence")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise PhysicalRescueDiagnosticsError("refusing to overwrite physical rescue diagnostics temporary path")
    try:
        temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()
