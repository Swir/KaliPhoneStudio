"""Bind explicit read-only rescue functional probes to one exact physical transcript.

The rescue init only *generates* the probe helper in initramfs RAM. The helper is
never executed automatically and requires an explicit local ``--confirm-read-only``
argument. Its bounded raw block reads go only to ``/dev/null`` and its power
checks only read sysfs. This module is offline: it parses one transcript already
bound by PhysicalBootObservationEvidence and PhysicalRescueDiagnosticsEvidence.

New functional-probe records require the current schema-v2 physical boot
observation. Historical schema-v1 observations and their already-recorded
artifacts remain readable for audit, but cannot seed new functional-probe
evidence after the runtime/recovery-bound observation contract became current.

Successful probe records are still signals, not automatic hardware verification.
Storage, charging/battery, recovery, hardware and Beta flags remain false until a
separate manual physical review completes the corresponding release gate.
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
)
from .physical_rescue_diagnostics import (
    PhysicalRescueDiagnosticsEvidence,
    PhysicalRescueDiagnosticsError,
    require_current_physical_boot_observation_for_rescue,
    validate_physical_rescue_diagnostics_evidence,
)
from .profiles import DeviceProfile

_POLICY = "readonly-functional-probes-v1"
_BEGIN = f"KPS_PROBE_BEGIN={_POLICY}"
_END = f"KPS_PROBE_END={_POLICY}"
_PREFIX = "KPS_PROBE_"
_DIAG_END = b"KPS_DIAG_END=readonly-sysfs-inventory-v1"
_MAX_RECORDS = 64
_MAX_FIELD = 128
_SAFE_VALUE_RE = re.compile(r"^[A-Za-z0-9._:+-]{1,128}$")
_ALLOWED_KINDS = {"BLOCK_READ": 3, "BATTERY_SAMPLE": 8}
_ALLOWED_BLOCK_OUTCOMES = frozenset({"ok", "fail", "missing"})
_BLOCK_READ_BYTES = "4096"


class PhysicalRescueFunctionalProbeError(ValueError):
    pass


@dataclass(frozen=True)
class FunctionalProbeRecord:
    kind: str
    values: tuple[str, ...]

    def canonical_line(self) -> str:
        return f"{self.kind}=" + "|".join(self.values)


@dataclass(frozen=True)
class PhysicalRescueFunctionalProbeEvidence:
    schema_version: int
    profile_id: str
    device_serial: str
    physical_boot_observation_sha256: str
    rescue_diagnostics_sha256: str
    transcript_sha256: str
    rescue_probe_id: str
    probe_policy: str
    normalized_probe_sha256: str
    probe_record_count: int
    block_read_record_count: int
    block_read_success_count: int
    block_read_failure_count: int
    block_read_missing_count: int
    battery_sample_count: int
    battery_pair_count: int
    storage_read_signal_observed: bool
    battery_sampling_signal_observed: bool
    records: tuple[FunctionalProbeRecord, ...]
    explicit_local_authorization_required: bool
    physical_functional_probe_recorded: bool
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
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise PhysicalRescueFunctionalProbeError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _read_bound_transcript(path: Path, observation: PhysicalBootObservationEvidence) -> bytes:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalRescueFunctionalProbeError("functional probe transcript must be a regular non-symlink file")
    try:
        before = source.stat()
        payload = source.read_bytes()
        after = source.stat()
    except OSError as exc:
        raise PhysicalRescueFunctionalProbeError(f"cannot read functional probe transcript: {exc}") from exc
    if before.st_size <= 0 or before.st_size > MAX_TRANSCRIPT_BYTES:
        raise PhysicalRescueFunctionalProbeError("functional probe transcript size is outside the safety limit")
    if len(payload) != before.st_size or (
        before.st_size,
        before.st_mtime_ns,
        before.st_ino,
    ) != (
        after.st_size,
        after.st_mtime_ns,
        after.st_ino,
    ):
        raise PhysicalRescueFunctionalProbeError("functional probe transcript changed while being verified")
    actual = sha256(payload).hexdigest()
    if actual != observation.transcript_sha256 or len(payload) != observation.transcript_size:
        raise PhysicalRescueFunctionalProbeError("functional probe transcript is not the transcript bound by physical boot observation")
    return payload


def _parse_record(line: str) -> FunctionalProbeRecord:
    if not line.startswith(_PREFIX) or "=" not in line:
        raise PhysicalRescueFunctionalProbeError("invalid functional probe record")
    key, raw = line[len(_PREFIX):].split("=", 1)
    if key not in _ALLOWED_KINDS:
        raise PhysicalRescueFunctionalProbeError(f"unsupported functional probe record kind: {key}")
    values = tuple(raw.split("|"))
    if len(values) != _ALLOWED_KINDS[key]:
        raise PhysicalRescueFunctionalProbeError(f"functional probe {key} field count drifted")
    for value in values:
        if len(value) > _MAX_FIELD or not _SAFE_VALUE_RE.fullmatch(value):
            raise PhysicalRescueFunctionalProbeError(f"functional probe {key} contains unsafe field data")
    if key == "BLOCK_READ":
        if values[1] != _BLOCK_READ_BYTES:
            raise PhysicalRescueFunctionalProbeError("functional BLOCK_READ byte count drifted")
        if values[2] not in _ALLOWED_BLOCK_OUTCOMES:
            raise PhysicalRescueFunctionalProbeError("functional BLOCK_READ outcome is unsupported")
    else:
        if values[1] not in {"1", "2"}:
            raise PhysicalRescueFunctionalProbeError("functional BATTERY_SAMPLE sequence is unsupported")
    return FunctionalProbeRecord(kind=key, values=values)


def _extract_records(payload: bytes, expected_probe_id: str) -> tuple[FunctionalProbeRecord, ...]:
    lines = payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"\n")
    begin_marker, end_marker = _BEGIN.encode("ascii"), _END.encode("ascii")
    begins = [i for i, line in enumerate(lines) if line == begin_marker]
    ends = [i for i, line in enumerate(lines) if line == end_marker]
    if len(begins) != 1 or len(ends) != 1:
        raise PhysicalRescueFunctionalProbeError("functional probe transcript must contain exactly one probe block")
    begin, end = begins[0], ends[0]
    if begin >= end:
        raise PhysicalRescueFunctionalProbeError("functional probe block order is invalid")

    expected_rescue_probe = f"KPS_RESCUE_PROBE_ID={expected_probe_id}".encode("ascii")
    rescue_probe_positions = [i for i, line in enumerate(lines) if line == expected_rescue_probe]
    diag_end_positions = [i for i, line in enumerate(lines) if line == _DIAG_END]
    if not rescue_probe_positions or min(rescue_probe_positions) >= begin:
        raise PhysicalRescueFunctionalProbeError("functional probe block is not preceded by the exact rescue probe marker")
    if len(diag_end_positions) != 1 or diag_end_positions[0] >= begin:
        raise PhysicalRescueFunctionalProbeError("functional probe block is not preceded by the exact read-only diagnostic block")

    prefix = _PREFIX.encode("ascii")
    for i, line in enumerate(lines):
        if line.startswith(prefix) and line not in {begin_marker, end_marker} and not (begin < i < end):
            raise PhysicalRescueFunctionalProbeError("functional probe marker appears outside the locked probe block")
    record_lines = [line for line in lines[begin + 1:end] if line]
    if not record_lines:
        raise PhysicalRescueFunctionalProbeError("functional probe block is empty")
    if len(record_lines) > _MAX_RECORDS:
        raise PhysicalRescueFunctionalProbeError("functional probe record count exceeds safety limit")
    result: list[FunctionalProbeRecord] = []
    for line in record_lines:
        try:
            text = line.decode("ascii", errors="strict")
        except UnicodeDecodeError as exc:
            raise PhysicalRescueFunctionalProbeError("machine-readable functional probe record is not ASCII-clean") from exc
        result.append(_parse_record(text))
    return tuple(result)


def _normalized_digest(records: tuple[FunctionalProbeRecord, ...]) -> str:
    payload = (
        _BEGIN
        + "\n"
        + "\n".join(f"KPS_PROBE_{item.canonical_line()}" for item in records)
        + "\n"
        + _END
        + "\n"
    ).encode("ascii")
    return sha256(payload).hexdigest()


def _battery_pair_count(records: tuple[FunctionalProbeRecord, ...]) -> int:
    per_name: dict[str, set[str]] = {}
    for record in records:
        if record.kind == "BATTERY_SAMPLE":
            per_name.setdefault(record.values[0], set()).add(record.values[1])
    return sum(sequences == {"1", "2"} for sequences in per_name.values())


def record_physical_rescue_functional_probes(
    profile: DeviceProfile,
    observation: PhysicalBootObservationEvidence,
    diagnostics: PhysicalRescueDiagnosticsEvidence,
    console_transcript: Path,
) -> PhysicalRescueFunctionalProbeEvidence:
    """Bind explicitly invoked read-only functional probes to exact prior evidence."""
    try:
        require_current_physical_boot_observation_for_rescue(observation)
    except PhysicalRescueDiagnosticsError as exc:
        raise PhysicalRescueFunctionalProbeError(str(exc)) from exc
    try:
        validate_physical_rescue_diagnostics_evidence(diagnostics)
    except PhysicalRescueDiagnosticsError as exc:
        raise PhysicalRescueFunctionalProbeError(str(exc)) from exc
    if not isinstance(profile, DeviceProfile) or profile.profile_id != observation.profile_id:
        raise PhysicalRescueFunctionalProbeError("profile does not match physical boot observation")
    if diagnostics.profile_id != observation.profile_id or diagnostics.device_serial != observation.device_serial:
        raise PhysicalRescueFunctionalProbeError("rescue diagnostics do not match physical boot observation")
    if diagnostics.physical_boot_observation_sha256 != observation.evidence_sha256():
        raise PhysicalRescueFunctionalProbeError("rescue diagnostics are not bound to the supplied physical boot observation")
    if diagnostics.transcript_sha256 != observation.transcript_sha256:
        raise PhysicalRescueFunctionalProbeError("rescue diagnostics transcript does not match physical boot observation")
    if diagnostics.rescue_probe_id != observation.rescue_probe_id:
        raise PhysicalRescueFunctionalProbeError("rescue diagnostics probe id does not match physical boot observation")

    payload = _read_bound_transcript(console_transcript, observation)
    records = _extract_records(payload, observation.rescue_probe_id)
    block_records = [item for item in records if item.kind == "BLOCK_READ"]
    battery_records = [item for item in records if item.kind == "BATTERY_SAMPLE"]
    success = sum(item.values[2] == "ok" for item in block_records)
    failure = sum(item.values[2] == "fail" for item in block_records)
    missing = sum(item.values[2] == "missing" for item in block_records)
    battery_pairs = _battery_pair_count(records)

    evidence = PhysicalRescueFunctionalProbeEvidence(
        schema_version=1,
        profile_id=observation.profile_id,
        device_serial=observation.device_serial,
        physical_boot_observation_sha256=observation.evidence_sha256(),
        rescue_diagnostics_sha256=diagnostics.evidence_sha256(),
        transcript_sha256=observation.transcript_sha256,
        rescue_probe_id=observation.rescue_probe_id,
        probe_policy=_POLICY,
        normalized_probe_sha256=_normalized_digest(records),
        probe_record_count=len(records),
        block_read_record_count=len(block_records),
        block_read_success_count=success,
        block_read_failure_count=failure,
        block_read_missing_count=missing,
        battery_sample_count=len(battery_records),
        battery_pair_count=battery_pairs,
        storage_read_signal_observed=success > 0,
        battery_sampling_signal_observed=battery_pairs > 0,
        records=records,
        explicit_local_authorization_required=True,
        physical_functional_probe_recorded=True,
        manual_review_required=True,
        storage_verified=False,
        display_touch_verified=False,
        charging_battery_verified=False,
        recovery_verified=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    validate_physical_rescue_functional_probe_evidence(evidence)
    return evidence


def validate_physical_rescue_functional_probe_evidence(
    evidence: PhysicalRescueFunctionalProbeEvidence,
) -> None:
    if not isinstance(evidence, PhysicalRescueFunctionalProbeEvidence) or evidence.schema_version != 1:
        raise PhysicalRescueFunctionalProbeError("physical rescue functional probe must be schema-v1 typed evidence")
    if not isinstance(evidence.profile_id, str) or "/" not in evidence.profile_id:
        raise PhysicalRescueFunctionalProbeError("physical rescue functional probe profile_id is invalid")
    if not isinstance(evidence.device_serial, str) or not evidence.device_serial:
        raise PhysicalRescueFunctionalProbeError("physical rescue functional probe serial is invalid")
    for value, label in (
        (evidence.physical_boot_observation_sha256, "physical boot observation"),
        (evidence.rescue_diagnostics_sha256, "rescue diagnostics"),
        (evidence.transcript_sha256, "transcript"),
        (evidence.rescue_probe_id, "rescue probe id"),
        (evidence.normalized_probe_sha256, "normalized probe"),
    ):
        _digest(value, label)
    if evidence.probe_policy != _POLICY:
        raise PhysicalRescueFunctionalProbeError("physical rescue functional probe policy is unsupported")
    if not isinstance(evidence.records, tuple) or not evidence.records or len(evidence.records) > _MAX_RECORDS:
        raise PhysicalRescueFunctionalProbeError("physical rescue functional probe records are invalid")
    for record in evidence.records:
        if not isinstance(record, FunctionalProbeRecord) or _parse_record(f"KPS_PROBE_{record.canonical_line()}") != record:
            raise PhysicalRescueFunctionalProbeError("physical rescue functional probe record canonicalization drifted")
    block_records = [item for item in evidence.records if item.kind == "BLOCK_READ"]
    battery_records = [item for item in evidence.records if item.kind == "BATTERY_SAMPLE"]
    expected_counts = (
        len(evidence.records),
        len(block_records),
        sum(item.values[2] == "ok" for item in block_records),
        sum(item.values[2] == "fail" for item in block_records),
        sum(item.values[2] == "missing" for item in block_records),
        len(battery_records),
        _battery_pair_count(evidence.records),
    )
    actual_counts = (
        evidence.probe_record_count,
        evidence.block_read_record_count,
        evidence.block_read_success_count,
        evidence.block_read_failure_count,
        evidence.block_read_missing_count,
        evidence.battery_sample_count,
        evidence.battery_pair_count,
    )
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in actual_counts):
        raise PhysicalRescueFunctionalProbeError("physical rescue functional probe counts must be non-negative integers")
    if actual_counts != expected_counts:
        raise PhysicalRescueFunctionalProbeError("physical rescue functional probe counts drifted")
    if evidence.normalized_probe_sha256 != _normalized_digest(evidence.records):
        raise PhysicalRescueFunctionalProbeError("physical rescue functional probe normalized digest drifted")
    if evidence.storage_read_signal_observed is not (expected_counts[2] > 0):
        raise PhysicalRescueFunctionalProbeError("physical rescue storage-read signal flag drifted")
    if evidence.battery_sampling_signal_observed is not (expected_counts[6] > 0):
        raise PhysicalRescueFunctionalProbeError("physical rescue battery-sampling signal flag drifted")
    if (
        evidence.explicit_local_authorization_required is not True
        or evidence.physical_functional_probe_recorded is not True
        or evidence.manual_review_required is not True
    ):
        raise PhysicalRescueFunctionalProbeError("physical rescue functional probe is missing authorization/review flags")
    if (
        evidence.storage_verified is not False
        or evidence.display_touch_verified is not False
        or evidence.charging_battery_verified is not False
        or evidence.recovery_verified is not False
        or evidence.phone_storage_written is not False
        or evidence.hardware_verified is not False
        or evidence.beta_gate_credit is not False
    ):
        raise PhysicalRescueFunctionalProbeError("physical rescue functional probe contains an unsupported hardware/Beta claim")


def _load_json(path: Path, label: str, max_bytes: int = 4 * 1024 * 1024) -> dict[str, Any]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalRescueFunctionalProbeError(f"{label} must be a regular non-symlink file")
    raw = source.read_bytes()
    if not raw or len(raw) > max_bytes:
        raise PhysicalRescueFunctionalProbeError(f"{label} size is outside the safety limit")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalRescueFunctionalProbeError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise PhysicalRescueFunctionalProbeError(f"{label} must be a JSON object")
    return value


def load_physical_rescue_functional_probe_evidence(path: Path) -> PhysicalRescueFunctionalProbeEvidence:
    raw = _load_json(path, "physical rescue functional probe evidence")
    if set(raw) != {item.name for item in fields(PhysicalRescueFunctionalProbeEvidence)}:
        raise PhysicalRescueFunctionalProbeError("physical rescue functional probe fields do not match schema-v1")
    records = raw.get("records")
    if not isinstance(records, list):
        raise PhysicalRescueFunctionalProbeError("physical rescue functional probe records are malformed")
    typed: list[FunctionalProbeRecord] = []
    for item in records:
        if not isinstance(item, dict) or set(item) != {"kind", "values"} or not isinstance(item.get("values"), list):
            raise PhysicalRescueFunctionalProbeError("physical rescue functional probe record is malformed")
        typed.append(FunctionalProbeRecord(kind=item["kind"], values=tuple(item["values"])))
    raw["records"] = tuple(typed)
    try:
        evidence = PhysicalRescueFunctionalProbeEvidence(**raw)
    except TypeError as exc:
        raise PhysicalRescueFunctionalProbeError("physical rescue functional probe evidence types are invalid") from exc
    validate_physical_rescue_functional_probe_evidence(evidence)
    return evidence


def write_physical_rescue_functional_probe_evidence(
    evidence: PhysicalRescueFunctionalProbeEvidence,
    destination: Path,
) -> str:
    validate_physical_rescue_functional_probe_evidence(evidence)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise PhysicalRescueFunctionalProbeError("refusing to overwrite physical rescue functional probe evidence")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise PhysicalRescueFunctionalProbeError("refusing to overwrite physical rescue functional probe temporary path")
    try:
        temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()
