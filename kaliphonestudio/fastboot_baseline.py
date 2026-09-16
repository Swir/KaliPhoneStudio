"""Offline, profile-driven evidence for a captured ``fastboot getvar all`` baseline.

This module deliberately does not invoke fastboot.  It only validates a transcript
captured by an operator and binds it to an exact device profile and firmware
baseline.  Importing evidence is not a Beta hardware-success claim.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .profiles import DeviceProfile
from .safety import SafetyError, VerifiedDevice


MAX_TRANSCRIPT_BYTES = 2 * 1024 * 1024
MAX_VARIABLES = 2048
MAX_KEY_LENGTH = 128
MAX_VALUE_LENGTH = 4096


class FastbootBaselineError(ValueError):
    pass


@dataclass(frozen=True)
class FastbootBaselineEvidence:
    schema_version: int
    profile_id: str
    transcript_sha256: str
    transcript_size: int
    firmware_build: str
    firmware_fingerprint: str
    product: str
    serialno: str
    current_slot: str | None
    slot_count: int | None
    unlocked: bool
    secure: bool
    bootloader_version: str | None
    baseband_version: str | None
    variables: dict[str, str]
    beta_gate_credit: bool = False

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _require_text(value: str, label: str, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise FastbootBaselineError(f"{label} must be text")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > maximum:
        raise FastbootBaselineError(f"{label} must be non-empty and at most {maximum} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in cleaned):
        raise FastbootBaselineError(f"{label} contains control characters")
    return cleaned


def _decode_transcript(payload: bytes) -> str:
    if not payload:
        raise FastbootBaselineError("fastboot transcript is empty")
    if len(payload) > MAX_TRANSCRIPT_BYTES:
        raise FastbootBaselineError("fastboot transcript exceeds the safety size limit")
    if b"\x00" in payload:
        raise FastbootBaselineError("fastboot transcript contains NUL bytes")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FastbootBaselineError("fastboot transcript must be valid UTF-8") from exc
    for ch in text:
        code = ord(ch)
        if code < 0x20 and ch not in "\r\n\t":
            raise FastbootBaselineError("fastboot transcript contains unsafe control bytes")
    return text


def parse_fastboot_getvar_all(payload: bytes) -> dict[str, str]:
    """Parse a saved fastboot transcript and reject ambiguous evidence.

    The parser accepts the ordinary ``(bootloader) key: value`` form as well as
    bare ``key: value`` lines.  Noise emitted by the host fastboot client is
    ignored, while explicit command failures and conflicting duplicate variables
    fail closed.
    """
    text = _decode_transcript(payload)
    variables: dict[str, str] = {}
    for original in text.splitlines():
        line = original.strip()
        if not line:
            continue
        lowered = line.lower()
        if lowered.startswith("failed (") or lowered.startswith("fastboot: error:"):
            raise FastbootBaselineError("fastboot transcript records a failed command")
        if line.startswith("(bootloader)"):
            line = line[len("(bootloader)"):].lstrip()
        elif line.startswith("INFO") and ": " in line[4:]:
            line = line[4:].lstrip()
        elif lowered.startswith(("finished.", "total time:", "waiting for any device")):
            continue

        if ": " not in line:
            # Host-side status/noise is intentionally not treated as evidence.
            continue
        key, value = line.split(": ", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            continue
        if len(key) > MAX_KEY_LENGTH or len(value) > MAX_VALUE_LENGTH:
            raise FastbootBaselineError("fastboot variable exceeds the safety length limit")
        if any(ord(ch) < 0x21 or ord(ch) > 0x7E for ch in key):
            raise FastbootBaselineError(f"unsafe fastboot variable name: {key!r}")
        if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
            raise FastbootBaselineError(f"unsafe fastboot value for {key!r}")
        previous = variables.get(key)
        if previous is not None and previous != value:
            raise FastbootBaselineError(f"conflicting duplicate fastboot variable: {key}")
        variables[key] = value
        if len(variables) > MAX_VARIABLES:
            raise FastbootBaselineError("fastboot transcript contains too many variables")
    if not variables:
        raise FastbootBaselineError("fastboot transcript contains no usable variables")
    return variables


def _parse_yes_no(value: str, label: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "yes":
        return True
    if normalized == "no":
        return False
    raise FastbootBaselineError(f"{label} must be yes or no")


def _parse_positive_int(value: str, label: str) -> int:
    try:
        parsed = int(value.strip(), 0)
    except ValueError as exc:
        raise FastbootBaselineError(f"{label} must be an integer") from exc
    if parsed <= 0:
        raise FastbootBaselineError(f"{label} must be positive")
    return parsed


def _probe_contract(profile: DeviceProfile) -> dict[str, Any]:
    contract = profile.data.get("fastboot_probe")
    if not isinstance(contract, dict):
        raise FastbootBaselineError("profile has no validated fastboot_probe contract")
    return contract


def capture_fastboot_baseline(
    profile: DeviceProfile,
    *,
    transcript: Path,
    firmware_build: str,
    firmware_fingerprint: str,
) -> FastbootBaselineEvidence:
    """Validate an offline capture and return canonical identity/firmware evidence."""
    if not transcript.is_file():
        raise FastbootBaselineError(f"fastboot transcript not found: {transcript}")
    payload = transcript.read_bytes()
    variables = parse_fastboot_getvar_all(payload)
    contract = _probe_contract(profile)

    missing = [key for key in contract["required_vars"] if key not in variables]
    if missing:
        raise FastbootBaselineError(
            "fastboot transcript is missing required profile variables: " + ", ".join(missing)
        )

    identity_var = contract["identity_var"]
    serial_var = contract["serial_var"]
    product = _require_text(variables[identity_var], identity_var, maximum=256)
    serialno = _require_text(variables[serial_var], serial_var, maximum=128)
    if any(ch.isspace() for ch in serialno):
        raise FastbootBaselineError("fastboot serial contains whitespace")
    if not profile.matches(product=product):
        raise FastbootBaselineError(
            f"fastboot product {product!r} does not identify profile {profile.profile_id}"
        )

    current_slot: str | None = None
    slot_count: int | None = None
    if profile.data.get("ab_device"):
        current_slot = variables[contract["current_slot_var"]].strip().lower()
        if current_slot not in {"a", "b"}:
            raise FastbootBaselineError("current-slot must be a or b for an A/B profile")
        slot_count = _parse_positive_int(variables[contract["slot_count_var"]], "slot-count")
        expected = contract.get("expected_slot_count")
        if expected is not None and slot_count != expected:
            raise FastbootBaselineError(
                f"slot-count {slot_count} does not match profile expectation {expected}"
            )

    unlocked = _parse_yes_no(variables[contract["unlocked_var"]], contract["unlocked_var"])
    secure = _parse_yes_no(variables[contract["secure_var"]], contract["secure_var"])

    bootloader_var = contract.get("bootloader_version_var")
    baseband_var = contract.get("baseband_version_var")
    bootloader_version = variables.get(bootloader_var) if bootloader_var else None
    baseband_version = variables.get(baseband_var) if baseband_var else None

    build = _require_text(firmware_build, "firmware_build", maximum=256)
    fingerprint = _require_text(firmware_fingerprint, "firmware_fingerprint", maximum=512)

    return FastbootBaselineEvidence(
        schema_version=1,
        profile_id=profile.profile_id,
        transcript_sha256=sha256(payload).hexdigest(),
        transcript_size=len(payload),
        firmware_build=build,
        firmware_fingerprint=fingerprint,
        product=product,
        serialno=serialno,
        current_slot=current_slot,
        slot_count=slot_count,
        unlocked=unlocked,
        secure=secure,
        bootloader_version=bootloader_version,
        baseband_version=baseband_version,
        variables=dict(sorted(variables.items())),
        beta_gate_credit=False,
    )


def require_device_matches_baseline(
    profile: DeviceProfile,
    baseline: FastbootBaselineEvidence,
    device: VerifiedDevice,
) -> None:
    """Require later verified-device identity to refer to the captured baseline.

    Unlock state and active slot may legitimately change after a stock baseline is
    captured, so this binding intentionally uses the immutable profile + serial.
    """
    if baseline.schema_version != 1:
        raise SafetyError("unsupported fastboot baseline schema")
    if baseline.profile_id != profile.profile_id or device.profile_id != profile.profile_id:
        raise SafetyError("fastboot baseline/device profile mismatch")
    if not baseline.serialno or baseline.serialno != device.serial:
        raise SafetyError("verified device serial does not match fastboot baseline")


def write_fastboot_baseline_evidence(
    evidence: FastbootBaselineEvidence,
    destination: Path,
) -> str:
    if destination.exists():
        raise FastbootBaselineError(f"refusing to overwrite existing evidence: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists():
        temporary.unlink()
    temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
    temporary.replace(destination)
    return evidence.evidence_sha256()
