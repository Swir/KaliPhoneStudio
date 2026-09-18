"""Bind bounded read-only hardware-presence survey markers to one rescue boot.

The survey is deliberately observational. It records only sysfs-visible presence/state
signals already emitted by the rescue init and never turns those signals into a claim
that display, touch, USB, networking, Bluetooth, audio, thermal, power or any other
hardware function actually works. Real hardware verification remains a separate manual
physical gate.

New hardware-survey records require the current schema-v2 physical boot observation.
Historical schema-v1 observations remain readable for audit, but cannot seed a new
presence survey after the runtime/recovery-bound observation contract became current.
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

_SURVEY_POLICY = "readonly-hardware-presence-v1"
_BEGIN = f"KPS_SURVEY_BEGIN={_SURVEY_POLICY}"
_END = f"KPS_SURVEY_END={_SURVEY_POLICY}"
_DIAG_END = "KPS_DIAG_END=readonly-sysfs-inventory-v1"
_PREFIX = "KPS_SURVEY_"
_MAX_RECORDS = 512
_MAX_RECORD_VALUE = 128
_SAFE_VALUE_RE = re.compile(r"^[A-Za-z0-9._:+-]{1,128}$")
_ALLOWED_KINDS = {
    "USB_UDC": 1,
    "USB_DEVICE": 4,
    "NET": 3,
    "RFKILL": 5,
    "SOUND": 2,
    "THERMAL": 3,
    "INPUT": 2,
    "GRAPHICS": 2,
    "DRM": 2,
    "POWER": 4,
}


class PhysicalHardwareSurveyError(ValueError):
    pass


@dataclass(frozen=True)
class HardwareSurveyRecord:
    kind: str
    values: tuple[str, ...]

    def canonical_line(self) -> str:
        return f"{self.kind}=" + "|".join(self.values)


@dataclass(frozen=True)
class PhysicalHardwareSurveyEvidence:
    schema_version: int
    profile_id: str
    device_serial: str
    physical_boot_observation_sha256: str
    physical_rescue_diagnostics_sha256: str
    transcript_sha256: str
    rescue_probe_id: str
    survey_policy: str
    normalized_survey_sha256: str
    survey_record_count: int
    usb_udc_record_count: int
    usb_device_record_count: int
    net_record_count: int
    rfkill_record_count: int
    sound_record_count: int
    thermal_record_count: int
    input_record_count: int
    graphics_record_count: int
    drm_record_count: int
    power_record_count: int
    usb_signal_observed: bool
    network_signal_observed: bool
    wifi_signal_observed: bool
    bluetooth_signal_observed: bool
    audio_signal_observed: bool
    thermal_signal_observed: bool
    input_signal_observed: bool
    display_signal_observed: bool
    power_signal_observed: bool
    records: tuple[HardwareSurveyRecord, ...]
    hardware_survey_recorded: bool
    manual_review_required: bool
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


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise PhysicalHardwareSurveyError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _read_transcript(path: Path, observation: PhysicalBootObservationEvidence) -> bytes:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalHardwareSurveyError(
            "hardware survey transcript must be a regular non-symlink file"
        )
    try:
        before = source.stat()
        payload = source.read_bytes()
        after = source.stat()
    except OSError as exc:
        raise PhysicalHardwareSurveyError(f"cannot read hardware survey transcript: {exc}") from exc
    if before.st_size <= 0 or before.st_size > MAX_TRANSCRIPT_BYTES:
        raise PhysicalHardwareSurveyError("hardware survey transcript size is outside the safety limit")
    if len(payload) != before.st_size or (
        before.st_size,
        before.st_mtime_ns,
        before.st_ino,
    ) != (
        after.st_size,
        after.st_mtime_ns,
        after.st_ino,
    ):
        raise PhysicalHardwareSurveyError("hardware survey transcript changed while being verified")
    actual = sha256(payload).hexdigest()
    if actual != observation.transcript_sha256 or len(payload) != observation.transcript_size:
        raise PhysicalHardwareSurveyError(
            "hardware survey transcript is not the transcript bound by physical boot observation"
        )
    return payload


def _parse_record(line: str) -> HardwareSurveyRecord:
    if not line.startswith(_PREFIX) or "=" not in line:
        raise PhysicalHardwareSurveyError("invalid hardware survey record")
    key, raw = line[len(_PREFIX) :].split("=", 1)
    if key not in _ALLOWED_KINDS:
        raise PhysicalHardwareSurveyError(f"unsupported hardware survey record kind: {key}")
    values = tuple(raw.split("|"))
    if len(values) != _ALLOWED_KINDS[key]:
        raise PhysicalHardwareSurveyError(f"hardware survey {key} field count drifted")
    for value in values:
        if len(value) > _MAX_RECORD_VALUE or not _SAFE_VALUE_RE.fullmatch(value):
            raise PhysicalHardwareSurveyError(f"hardware survey {key} contains unsafe field data")
    return HardwareSurveyRecord(kind=key, values=values)


def _extract_records(payload: bytes, expected_probe_id: str) -> tuple[HardwareSurveyRecord, ...]:
    lines = payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"\n")
    begin_marker, end_marker = _BEGIN.encode("ascii"), _END.encode("ascii")
    begins = [i for i, line in enumerate(lines) if line == begin_marker]
    ends = [i for i, line in enumerate(lines) if line == end_marker]
    if len(begins) != 1 or len(ends) != 1:
        raise PhysicalHardwareSurveyError(
            "hardware survey transcript must contain exactly one survey block"
        )
    begin, end = begins[0], ends[0]
    if begin >= end:
        raise PhysicalHardwareSurveyError("hardware survey block order is invalid")

    probe = f"KPS_RESCUE_PROBE_ID={expected_probe_id}".encode("ascii")
    stage = b"KPS_RESCUE_STAGE=init-reached-v1"
    diag_end = _DIAG_END.encode("ascii")
    probe_positions = [i for i, line in enumerate(lines) if line == probe]
    stage_positions = [i for i, line in enumerate(lines) if line == stage]
    diag_positions = [i for i, line in enumerate(lines) if line == diag_end]
    if (
        not probe_positions
        or not stage_positions
        or len(diag_positions) != 1
        or min(probe_positions) >= begin
        or min(stage_positions) >= begin
        or diag_positions[0] >= begin
    ):
        raise PhysicalHardwareSurveyError(
            "hardware survey is not preceded by the exact rescue/diagnostic proof chain"
        )

    prefix = _PREFIX.encode("ascii")
    for index, line in enumerate(lines):
        if line.startswith(prefix) and line not in {begin_marker, end_marker} and not (
            begin < index < end
        ):
            raise PhysicalHardwareSurveyError(
                "hardware survey marker appears outside the locked survey block"
            )
    record_lines = [line for line in lines[begin + 1 : end] if line]
    if len(record_lines) > _MAX_RECORDS:
        raise PhysicalHardwareSurveyError("hardware survey record count exceeds safety limit")
    result: list[HardwareSurveyRecord] = []
    for line in record_lines:
        try:
            text = line.decode("ascii", errors="strict")
        except UnicodeDecodeError as exc:
            raise PhysicalHardwareSurveyError(
                "machine-readable hardware survey record is not ASCII-clean"
            ) from exc
        result.append(_parse_record(text))
    return tuple(result)


def _normalized_digest(records: tuple[HardwareSurveyRecord, ...]) -> str:
    body = "\n".join(f"KPS_SURVEY_{item.canonical_line()}" for item in records)
    payload = (_BEGIN + "\n" + body + ("\n" if body else "") + _END + "\n").encode("ascii")
    return sha256(payload).hexdigest()


def _wifi_signal(records: tuple[HardwareSurveyRecord, ...]) -> bool:
    for record in records:
        lowered = " ".join(record.values).lower()
        if record.kind == "RFKILL" and any(token in lowered for token in ("wlan", "wifi", "wireless")):
            return True
        if record.kind == "NET" and any(token in record.values[0].lower() for token in ("wlan", "wifi")):
            return True
    return False


def _bluetooth_signal(records: tuple[HardwareSurveyRecord, ...]) -> bool:
    return any(
        record.kind == "RFKILL" and "bluetooth" in " ".join(record.values).lower()
        for record in records
    )


def record_physical_hardware_survey(
    profile: DeviceProfile,
    observation: PhysicalBootObservationEvidence,
    diagnostics: PhysicalRescueDiagnosticsEvidence,
    console_transcript: Path,
) -> PhysicalHardwareSurveyEvidence:
    """Bind one read-only hardware-presence survey to an already proven rescue transcript."""
    try:
        require_current_physical_boot_observation_for_rescue(observation)
    except PhysicalRescueDiagnosticsError as exc:
        raise PhysicalHardwareSurveyError(str(exc)) from exc
    try:
        validate_physical_rescue_diagnostics_evidence(diagnostics)
    except PhysicalRescueDiagnosticsError as exc:
        raise PhysicalHardwareSurveyError(str(exc)) from exc
    if not isinstance(profile, DeviceProfile) or profile.profile_id != observation.profile_id:
        raise PhysicalHardwareSurveyError("profile does not match physical boot observation")
    if diagnostics.profile_id != observation.profile_id or diagnostics.device_serial != observation.device_serial:
        raise PhysicalHardwareSurveyError("rescue diagnostics identity does not match boot observation")
    if diagnostics.physical_boot_observation_sha256 != observation.evidence_sha256():
        raise PhysicalHardwareSurveyError("rescue diagnostics are detached from boot observation")
    if diagnostics.transcript_sha256 != observation.transcript_sha256:
        raise PhysicalHardwareSurveyError("rescue diagnostics transcript does not match boot observation")
    if diagnostics.rescue_probe_id != observation.rescue_probe_id:
        raise PhysicalHardwareSurveyError("rescue diagnostics probe id does not match boot observation")

    payload = _read_transcript(console_transcript, observation)
    records = _extract_records(payload, observation.rescue_probe_id)
    counts = {kind: sum(record.kind == kind for record in records) for kind in _ALLOWED_KINDS}
    evidence = PhysicalHardwareSurveyEvidence(
        schema_version=1,
        profile_id=observation.profile_id,
        device_serial=observation.device_serial,
        physical_boot_observation_sha256=observation.evidence_sha256(),
        physical_rescue_diagnostics_sha256=diagnostics.evidence_sha256(),
        transcript_sha256=observation.transcript_sha256,
        rescue_probe_id=observation.rescue_probe_id,
        survey_policy=_SURVEY_POLICY,
        normalized_survey_sha256=_normalized_digest(records),
        survey_record_count=len(records),
        usb_udc_record_count=counts["USB_UDC"],
        usb_device_record_count=counts["USB_DEVICE"],
        net_record_count=counts["NET"],
        rfkill_record_count=counts["RFKILL"],
        sound_record_count=counts["SOUND"],
        thermal_record_count=counts["THERMAL"],
        input_record_count=counts["INPUT"],
        graphics_record_count=counts["GRAPHICS"],
        drm_record_count=counts["DRM"],
        power_record_count=counts["POWER"],
        usb_signal_observed=(counts["USB_UDC"] + counts["USB_DEVICE"]) > 0,
        network_signal_observed=counts["NET"] > 0,
        wifi_signal_observed=_wifi_signal(records),
        bluetooth_signal_observed=_bluetooth_signal(records),
        audio_signal_observed=counts["SOUND"] > 0,
        thermal_signal_observed=counts["THERMAL"] > 0,
        input_signal_observed=counts["INPUT"] > 0,
        display_signal_observed=(counts["GRAPHICS"] + counts["DRM"]) > 0,
        power_signal_observed=counts["POWER"] > 0,
        records=records,
        hardware_survey_recorded=True,
        manual_review_required=True,
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
    validate_physical_hardware_survey_evidence(evidence)
    return evidence


def validate_physical_hardware_survey_evidence(evidence: PhysicalHardwareSurveyEvidence) -> None:
    if not isinstance(evidence, PhysicalHardwareSurveyEvidence) or evidence.schema_version != 1:
        raise PhysicalHardwareSurveyError("physical hardware survey must be schema-v1 typed evidence")
    if not isinstance(evidence.profile_id, str) or "/" not in evidence.profile_id:
        raise PhysicalHardwareSurveyError("hardware survey profile_id is invalid")
    if not isinstance(evidence.device_serial, str) or not evidence.device_serial:
        raise PhysicalHardwareSurveyError("hardware survey serial is invalid")
    for value, label in (
        (evidence.physical_boot_observation_sha256, "physical boot observation"),
        (evidence.physical_rescue_diagnostics_sha256, "physical rescue diagnostics"),
        (evidence.transcript_sha256, "transcript"),
        (evidence.rescue_probe_id, "rescue probe id"),
        (evidence.normalized_survey_sha256, "normalized hardware survey"),
    ):
        _digest(value, label)
    if evidence.survey_policy != _SURVEY_POLICY:
        raise PhysicalHardwareSurveyError("physical hardware survey policy is unsupported")
    if not isinstance(evidence.records, tuple) or len(evidence.records) > _MAX_RECORDS:
        raise PhysicalHardwareSurveyError("hardware survey records are invalid")

    recomputed = {kind: 0 for kind in _ALLOWED_KINDS}
    for record in evidence.records:
        if not isinstance(record, HardwareSurveyRecord):
            raise PhysicalHardwareSurveyError("hardware survey contains an untyped record")
        if _parse_record(f"KPS_SURVEY_{record.canonical_line()}") != record:
            raise PhysicalHardwareSurveyError("hardware survey record canonicalization drifted")
        recomputed[record.kind] += 1

    count_values = (
        evidence.survey_record_count,
        evidence.usb_udc_record_count,
        evidence.usb_device_record_count,
        evidence.net_record_count,
        evidence.rfkill_record_count,
        evidence.sound_record_count,
        evidence.thermal_record_count,
        evidence.input_record_count,
        evidence.graphics_record_count,
        evidence.drm_record_count,
        evidence.power_record_count,
    )
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in count_values):
        raise PhysicalHardwareSurveyError("hardware survey counts must be non-negative integers")
    expected_counts = tuple(
        recomputed[key]
        for key in (
            "USB_UDC",
            "USB_DEVICE",
            "NET",
            "RFKILL",
            "SOUND",
            "THERMAL",
            "INPUT",
            "GRAPHICS",
            "DRM",
            "POWER",
        )
    )
    if evidence.survey_record_count != len(evidence.records) or count_values[1:] != expected_counts:
        raise PhysicalHardwareSurveyError("hardware survey counts drifted")
    if evidence.normalized_survey_sha256 != _normalized_digest(evidence.records):
        raise PhysicalHardwareSurveyError("hardware survey normalized digest drifted")

    expected_flags = {
        "usb_signal_observed": (recomputed["USB_UDC"] + recomputed["USB_DEVICE"]) > 0,
        "network_signal_observed": recomputed["NET"] > 0,
        "wifi_signal_observed": _wifi_signal(evidence.records),
        "bluetooth_signal_observed": _bluetooth_signal(evidence.records),
        "audio_signal_observed": recomputed["SOUND"] > 0,
        "thermal_signal_observed": recomputed["THERMAL"] > 0,
        "input_signal_observed": recomputed["INPUT"] > 0,
        "display_signal_observed": (recomputed["GRAPHICS"] + recomputed["DRM"]) > 0,
        "power_signal_observed": recomputed["POWER"] > 0,
    }
    for name, expected in expected_flags.items():
        if getattr(evidence, name) is not expected:
            raise PhysicalHardwareSurveyError(f"hardware survey {name} flag drifted")
    if evidence.hardware_survey_recorded is not True or evidence.manual_review_required is not True:
        raise PhysicalHardwareSurveyError("hardware survey is missing record/review flags")

    unsupported_claims = (
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
    )
    if any(value is not False for value in unsupported_claims):
        raise PhysicalHardwareSurveyError("hardware survey contains an unsupported hardware/Beta claim")


def load_physical_hardware_survey_evidence(path: Path) -> PhysicalHardwareSurveyEvidence:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalHardwareSurveyError("hardware survey evidence must be a regular non-symlink file")
    raw_bytes = source.read_bytes()
    if not raw_bytes or len(raw_bytes) > 4 * 1024 * 1024:
        raise PhysicalHardwareSurveyError("hardware survey evidence size is outside the safety limit")
    try:
        raw: Any = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalHardwareSurveyError("hardware survey evidence is not valid UTF-8 JSON") from exc
    if not isinstance(raw, dict) or set(raw) != {item.name for item in fields(PhysicalHardwareSurveyEvidence)}:
        raise PhysicalHardwareSurveyError("hardware survey evidence fields do not match schema-v1")
    records_raw = raw.get("records")
    if not isinstance(records_raw, list):
        raise PhysicalHardwareSurveyError("hardware survey records are not a JSON array")
    records: list[HardwareSurveyRecord] = []
    for item in records_raw:
        if not isinstance(item, dict) or set(item) != {"kind", "values"} or not isinstance(item.get("values"), list):
            raise PhysicalHardwareSurveyError("hardware survey record JSON is invalid")
        records.append(HardwareSurveyRecord(kind=item["kind"], values=tuple(item["values"])))
    raw["records"] = tuple(records)
    try:
        evidence = PhysicalHardwareSurveyEvidence(**raw)
        validate_physical_hardware_survey_evidence(evidence)
    except TypeError as exc:
        raise PhysicalHardwareSurveyError("hardware survey evidence is invalid") from exc
    if raw_bytes != evidence.canonical_json().encode("utf-8"):
        raise PhysicalHardwareSurveyError("hardware survey evidence is not canonical JSON")
    return evidence


def write_physical_hardware_survey_evidence(
    evidence: PhysicalHardwareSurveyEvidence, destination: Path
) -> str:
    validate_physical_hardware_survey_evidence(evidence)
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise PhysicalHardwareSurveyError("refusing to overwrite hardware survey evidence")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = evidence.canonical_json().encode("utf-8")
    path.write_bytes(payload)
    return sha256(payload).hexdigest()
