"""Guard the first physical temporary Fastboot boot with fresh fail-closed checks.

This module is deliberately narrower than a general Fastboot executor.  It accepts
only an already reviewed temporary-boot offer plus explicit profile confirmation,
re-verifies the exact local Fastboot executable and candidate boot image, performs
one fresh read-only serial-bound Fastboot probe, and only then may invoke the exact
``fastboot -s SERIAL boot IMAGE`` argv from the offer.

A successful Fastboot return code proves only that the host command was accepted.
It does not prove that the kernel booted, Kali userspace was reached, storage works,
or that any Beta hardware gate passed.  Persistent writes are never exposed here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from typing import Any, Callable

from .fastboot_baseline import FastbootBaselineEvidence, parse_fastboot_getvar_all
from .fastboot_capture import FastbootCaptureError, capture_fastboot_getvar_all
from .fastboot_capture_bundle import FastbootCaptureBundleEvidence
from .fastboot_tool import FastbootToolEvidence
from .physical_candidate_gate import PhysicalCandidateGateEvidence
from .profiles import DeviceProfile
from .temporary_boot_offer import (
    PreparedTemporaryBootOffer,
    TemporaryBootOfferError,
    TemporaryBootUserAuthorizationEvidence,
    verify_temporary_boot_offer,
)

DEFAULT_PROBE_TIMEOUT_SECONDS = 30
DEFAULT_BOOT_TIMEOUT_SECONDS = 120
MAX_BOOT_OUTPUT_BYTES = 2 * 1024 * 1024
_RUNTIME_PROBE_POLICY = "fresh-fastboot-devices+serial-getvar-all-before-boot-v1"
_EXECUTION_POLICY = "single-serial-fastboot-boot-no-persistent-write-v1"


class TemporaryBootExecutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class TemporaryBootRuntimeProbeEvidence:
    schema_version: int
    profile_id: str
    device_serial: str
    offer_sha256: str
    authorization_sha256: str
    baseline_evidence_sha256: str
    capture_bundle_sha256: str
    fresh_transcript_sha256: str
    fresh_transcript_size: int
    product: str
    current_slot: str | None
    slot_count: int | None
    unlocked: bool
    secure: bool
    bootloader_version: str | None
    baseband_version: str | None
    critical_variables_sha256: str
    probe_policy: str
    read_only: bool
    phone_storage_written: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TemporaryBootExecutionEvidence:
    schema_version: int
    profile_id: str
    device_serial: str
    offer_sha256: str
    authorization_sha256: str
    runtime_probe_sha256: str
    argv_sha256: str
    returncode: int
    output_sha256: str
    output_size: int
    execution_policy: str
    command_invoked: bool
    temporary_boot_executed: bool
    temporary_boot_command_succeeded: bool
    persistent_write: bool
    phone_storage_written: bool
    kali_userspace_verified: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _timeout(value: int, label: str, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1 or value > maximum:
        raise TemporaryBootExecutionError(f"{label} must be an integer between 1 and {maximum} seconds")
    return value


def _validate_authorization(
    offer: PreparedTemporaryBootOffer,
    authorization: TemporaryBootUserAuthorizationEvidence,
) -> None:
    if not isinstance(authorization, TemporaryBootUserAuthorizationEvidence) or authorization.schema_version != 1:
        raise TemporaryBootExecutionError("temporary-boot authorization must be schema-v1 typed evidence")
    if authorization.offer_sha256 != offer.evidence.evidence_sha256():
        raise TemporaryBootExecutionError("temporary-boot authorization is detached from the exact offer")
    if authorization.profile_id != offer.evidence.profile_id or authorization.device_serial != offer.evidence.device_serial:
        raise TemporaryBootExecutionError("temporary-boot authorization identity mismatch")
    if authorization.confirmation_text_sha256 != offer.evidence.confirmation_text_sha256:
        raise TemporaryBootExecutionError("temporary-boot authorization confirmation policy mismatch")
    if authorization.confirmation_verified is not True or authorization.execution_permitted is not True:
        raise TemporaryBootExecutionError("temporary-boot authorization does not permit execution")
    if (
        authorization.temporary_boot_executed is not False
        or authorization.persistent_write is not False
        or authorization.phone_storage_written is not False
        or authorization.hardware_verified is not False
        or authorization.beta_gate_credit is not False
    ):
        raise TemporaryBootExecutionError("temporary-boot authorization contains an invalid pre-execution claim")


def _validate_baseline_binding(
    profile: DeviceProfile,
    baseline: FastbootBaselineEvidence,
    capture: FastbootCaptureBundleEvidence,
) -> None:
    if not isinstance(baseline, FastbootBaselineEvidence) or baseline.schema_version != 1:
        raise TemporaryBootExecutionError("Fastboot baseline must be schema-v1 typed evidence")
    if baseline.profile_id != profile.profile_id or capture.profile_id != profile.profile_id:
        raise TemporaryBootExecutionError("Fastboot baseline/capture profile mismatch")
    if baseline.evidence_sha256() != capture.baseline_evidence_sha256:
        raise TemporaryBootExecutionError("Fastboot baseline is detached from capture bundle")
    if baseline.serialno != capture.device_serial or baseline.product != capture.product:
        raise TemporaryBootExecutionError("Fastboot baseline/capture device identity mismatch")
    if (
        baseline.firmware_build != capture.firmware_build
        or baseline.firmware_fingerprint != capture.firmware_fingerprint
    ):
        raise TemporaryBootExecutionError("Fastboot baseline/capture firmware identity mismatch")
    if baseline.beta_gate_credit is not False:
        raise TemporaryBootExecutionError("Fastboot baseline illegally claims Beta credit")
    if baseline.unlocked is not True:
        raise TemporaryBootExecutionError("temporary boot requires the reviewed baseline to report an unlocked bootloader")


def _critical_runtime_values(
    profile: DeviceProfile,
    baseline: FastbootBaselineEvidence,
    variables: dict[str, str],
) -> dict[str, str]:
    contract = profile.data.get("fastboot_probe")
    if not isinstance(contract, dict):
        raise TemporaryBootExecutionError("profile has no Fastboot probe contract")
    required = contract.get("required_vars")
    if not isinstance(required, list) or not all(isinstance(item, str) and item for item in required):
        raise TemporaryBootExecutionError("profile Fastboot required_vars contract is invalid")
    missing = [item for item in required if item not in variables]
    if missing:
        raise TemporaryBootExecutionError("fresh Fastboot probe is missing profile-required variables: " + ", ".join(missing))

    names = {
        "product": contract.get("identity_var"),
        "serialno": contract.get("serial_var"),
        "current_slot": contract.get("current_slot_var"),
        "slot_count": contract.get("slot_count_var"),
        "unlocked": contract.get("unlocked_var"),
        "secure": contract.get("secure_var"),
        "bootloader_version": contract.get("bootloader_version_var"),
        "baseband_version": contract.get("baseband_version_var"),
    }
    if not isinstance(names["product"], str) or not isinstance(names["serialno"], str):
        raise TemporaryBootExecutionError("profile Fastboot identity contract is invalid")

    critical: dict[str, str] = {}
    for label, key in names.items():
        if key is None:
            continue
        if not isinstance(key, str) or not key:
            raise TemporaryBootExecutionError(f"profile Fastboot {label} variable contract is invalid")
        if key not in variables:
            raise TemporaryBootExecutionError(f"fresh Fastboot probe is missing {key}")
        critical[key] = variables[key]

    expected: dict[str, object] = {
        names["product"]: baseline.product,
        names["serialno"]: baseline.serialno,
    }
    if names["current_slot"] is not None and baseline.current_slot is not None:
        expected[names["current_slot"]] = baseline.current_slot
    if names["slot_count"] is not None and baseline.slot_count is not None:
        expected[names["slot_count"]] = str(baseline.slot_count)
    if names["unlocked"] is not None:
        expected[names["unlocked"]] = "yes" if baseline.unlocked else "no"
    if names["secure"] is not None:
        expected[names["secure"]] = "yes" if baseline.secure else "no"
    if names["bootloader_version"] is not None and baseline.bootloader_version is not None:
        expected[names["bootloader_version"]] = baseline.bootloader_version
    if names["baseband_version"] is not None and baseline.baseband_version is not None:
        expected[names["baseband_version"]] = baseline.baseband_version

    for key, value in expected.items():
        if variables.get(key) != value:
            raise TemporaryBootExecutionError(f"fresh Fastboot probe drifted from reviewed baseline at {key}")
    if names["unlocked"] is not None and variables.get(names["unlocked"], "").strip().lower() != "yes":
        raise TemporaryBootExecutionError("fresh Fastboot probe does not report an unlocked bootloader")
    return dict(sorted(critical.items()))


def probe_temporary_boot_runtime(
    profile: DeviceProfile,
    offer: PreparedTemporaryBootOffer,
    authorization: TemporaryBootUserAuthorizationEvidence,
    gate: PhysicalCandidateGateEvidence,
    capture: FastbootCaptureBundleEvidence,
    tool: FastbootToolEvidence,
    baseline: FastbootBaselineEvidence,
    *,
    timeout_seconds: int = DEFAULT_PROBE_TIMEOUT_SECONDS,
    runner: Callable[..., Any] = subprocess.run,
) -> TemporaryBootRuntimeProbeEvidence:
    """Freshly revalidate exact files and read-only Fastboot identity before execution."""
    try:
        verify_temporary_boot_offer(offer, profile, gate, capture, tool)
    except TemporaryBootOfferError as exc:
        raise TemporaryBootExecutionError(str(exc)) from exc
    _validate_authorization(offer, authorization)
    _validate_baseline_binding(profile, baseline, capture)
    timeout = _timeout(timeout_seconds, "temporary-boot probe timeout", 300)
    try:
        transcript = capture_fastboot_getvar_all(
            offer.evidence.device_serial,
            fastboot=offer.fastboot_executable,
            timeout_seconds=timeout,
            runner=runner,
        )
        variables = parse_fastboot_getvar_all(transcript)
    except (FastbootCaptureError, ValueError) as exc:
        raise TemporaryBootExecutionError(f"fresh read-only Fastboot probe failed: {exc}") from exc
    critical = _critical_runtime_values(profile, baseline, variables)
    critical_payload = json.dumps(critical, sort_keys=True, separators=(",", ":")) + "\n"
    contract = profile.data["fastboot_probe"]

    def _value(name: str) -> str | None:
        key = contract.get(name)
        return variables.get(key) if isinstance(key, str) else None

    slot_count_value = _value("slot_count_var")
    slot_count = int(slot_count_value, 0) if slot_count_value is not None else None
    unlocked_value = _value("unlocked_var")
    secure_value = _value("secure_var")
    unlocked = unlocked_value is not None and unlocked_value.strip().lower() == "yes"
    secure = secure_value is not None and secure_value.strip().lower() == "yes"
    return TemporaryBootRuntimeProbeEvidence(
        schema_version=1,
        profile_id=profile.profile_id,
        device_serial=offer.evidence.device_serial,
        offer_sha256=offer.evidence.evidence_sha256(),
        authorization_sha256=authorization.evidence_sha256(),
        baseline_evidence_sha256=baseline.evidence_sha256(),
        capture_bundle_sha256=capture.evidence_sha256(),
        fresh_transcript_sha256=sha256(transcript).hexdigest(),
        fresh_transcript_size=len(transcript),
        product=_value("identity_var") or "",
        current_slot=_value("current_slot_var"),
        slot_count=slot_count,
        unlocked=unlocked,
        secure=secure,
        bootloader_version=_value("bootloader_version_var"),
        baseband_version=_value("baseband_version_var"),
        critical_variables_sha256=sha256(critical_payload.encode("utf-8")).hexdigest(),
        probe_policy=_RUNTIME_PROBE_POLICY,
        read_only=True,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def execute_temporary_boot_once(
    profile: DeviceProfile,
    offer: PreparedTemporaryBootOffer,
    authorization: TemporaryBootUserAuthorizationEvidence,
    gate: PhysicalCandidateGateEvidence,
    capture: FastbootCaptureBundleEvidence,
    tool: FastbootToolEvidence,
    baseline: FastbootBaselineEvidence,
    *,
    probe_timeout_seconds: int = DEFAULT_PROBE_TIMEOUT_SECONDS,
    boot_timeout_seconds: int = DEFAULT_BOOT_TIMEOUT_SECONDS,
    runner: Callable[..., Any] = subprocess.run,
) -> tuple[TemporaryBootRuntimeProbeEvidence, TemporaryBootExecutionEvidence]:
    """Invoke exactly one serial-bound temporary boot after a fresh read-only probe.

    This function never exposes ``flash``, ``erase``, ``set_active``, ``reboot`` or
    any other state-changing Fastboot verb.  It does not claim hardware success.
    """
    probe = probe_temporary_boot_runtime(
        profile,
        offer,
        authorization,
        gate,
        capture,
        tool,
        baseline,
        timeout_seconds=probe_timeout_seconds,
        runner=runner,
    )
    timeout = _timeout(boot_timeout_seconds, "temporary-boot execution timeout", 600)
    expected_argv = (
        str(offer.fastboot_executable),
        "-s",
        offer.evidence.device_serial,
        "boot",
        str(offer.boot_image),
    )
    if offer.argv != expected_argv:
        raise TemporaryBootExecutionError("temporary-boot argv drifted from the reviewed command policy")
    argv_payload = json.dumps(list(offer.argv), ensure_ascii=False, separators=(",", ":")) + "\n"
    try:
        result = runner(
            list(offer.argv),
            shell=False,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise TemporaryBootExecutionError("temporary Fastboot boot command failed to execute") from exc
    returncode = getattr(result, "returncode", None)
    output = getattr(result, "stdout", None)
    if not isinstance(returncode, int) or isinstance(returncode, bool):
        raise TemporaryBootExecutionError("temporary Fastboot boot runner returned an invalid status")
    if not isinstance(output, (bytes, bytearray)):
        raise TemporaryBootExecutionError("temporary Fastboot boot runner did not return byte output")
    output_bytes = bytes(output)
    if len(output_bytes) > MAX_BOOT_OUTPUT_BYTES:
        raise TemporaryBootExecutionError("temporary Fastboot boot output exceeds the safety size limit")
    evidence = TemporaryBootExecutionEvidence(
        schema_version=1,
        profile_id=profile.profile_id,
        device_serial=offer.evidence.device_serial,
        offer_sha256=offer.evidence.evidence_sha256(),
        authorization_sha256=authorization.evidence_sha256(),
        runtime_probe_sha256=probe.evidence_sha256(),
        argv_sha256=sha256(argv_payload.encode("utf-8")).hexdigest(),
        returncode=returncode,
        output_sha256=sha256(output_bytes).hexdigest(),
        output_size=len(output_bytes),
        execution_policy=_EXECUTION_POLICY,
        command_invoked=True,
        temporary_boot_executed=True,
        temporary_boot_command_succeeded=(returncode == 0),
        persistent_write=False,
        phone_storage_written=False,
        kali_userspace_verified=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    return probe, evidence


def _write_once(payload: str, destination: Path, label: str) -> str:
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise TemporaryBootExecutionError(f"refusing to overwrite {label}: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise TemporaryBootExecutionError(f"refusing stale {label} temporary path")
    try:
        temporary.write_text(payload, encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return sha256(payload.encode("utf-8")).hexdigest()


def write_temporary_boot_runtime_probe(
    evidence: TemporaryBootRuntimeProbeEvidence,
    destination: Path,
) -> str:
    if not isinstance(evidence, TemporaryBootRuntimeProbeEvidence) or evidence.schema_version != 1:
        raise TemporaryBootExecutionError("invalid temporary-boot runtime probe evidence")
    if (
        evidence.probe_policy != _RUNTIME_PROBE_POLICY
        or evidence.read_only is not True
        or evidence.phone_storage_written is not False
        or evidence.hardware_verified is not False
        or evidence.beta_gate_credit is not False
    ):
        raise TemporaryBootExecutionError("runtime probe evidence contains an invalid safety claim")
    return _write_once(evidence.canonical_json(), destination, "temporary-boot runtime probe evidence")


def write_temporary_boot_execution(
    evidence: TemporaryBootExecutionEvidence,
    destination: Path,
) -> str:
    if not isinstance(evidence, TemporaryBootExecutionEvidence) or evidence.schema_version != 1:
        raise TemporaryBootExecutionError("invalid temporary-boot execution evidence")
    if (
        evidence.execution_policy != _EXECUTION_POLICY
        or evidence.command_invoked is not True
        or evidence.temporary_boot_executed is not True
        or evidence.persistent_write is not False
        or evidence.phone_storage_written is not False
        or evidence.kali_userspace_verified is not False
        or evidence.hardware_verified is not False
        or evidence.beta_gate_credit is not False
    ):
        raise TemporaryBootExecutionError("temporary-boot execution evidence contains an invalid claim")
    return _write_once(evidence.canonical_json(), destination, "temporary-boot execution evidence")
