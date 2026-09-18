"""Guard the first physical temporary Fastboot boot with fresh fail-closed checks.

This module is deliberately narrower than a general Fastboot executor. It accepts
only an already reviewed temporary-boot offer plus explicit profile confirmation,
re-verifies the exact local Fastboot executable and candidate boot image, requires
an exact stock/candidate boot-identity binding *and* exact physical recovery-readiness
material, performs one fresh read-only serial-bound Fastboot probe, and then
re-validates the exact host boot/recovery material again immediately before the
single allowed ``fastboot -s SERIAL boot IMAGE`` invocation.

A successful Fastboot return code proves only that the host command was accepted.
It does not prove that the kernel booted, Kali userspace was reached, storage works,
recovery was exercised, or that any Beta hardware gate passed. Persistent writes
are never exposed here.
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
from .physical_baseline_bundle import PhysicalBaselineBundleEvidence
from .physical_boot_identity_binding import PhysicalBootIdentityBindingEvidence
from .physical_candidate_gate import PhysicalCandidateGateEvidence
from .physical_recovery_readiness import (
    PhysicalRecoveryReadinessError,
    PhysicalRecoveryReadinessEvidence,
    verify_physical_recovery_readiness,
)
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
_RUNTIME_PROBE_POLICY = (
    "fresh-fastboot-devices+serial-getvar-all+exact-boot-identity+recovery-readiness-before-boot-v3"
)
_EXECUTION_POLICY = (
    "single-serial-fastboot-boot+post-probe-exact-material-revalidation+no-persistent-write-v4"
)


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
    physical_baseline_bundle_sha256: str
    boot_identity_binding_sha256: str
    recovery_readiness_sha256: str
    recovery_stock_boot_sha256: str
    fresh_transcript_sha256: str
    fresh_transcript_size: int
    product: str
    current_slot: str | None
    slot_count: int | None
    captured_active_slot: str | None
    expected_inactive_slot: str | None
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


def _valid_sha(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)


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


def _validate_boot_identity_binding(
    profile: DeviceProfile,
    gate: PhysicalCandidateGateEvidence,
    binding: PhysicalBootIdentityBindingEvidence,
    offer: PreparedTemporaryBootOffer,
) -> None:
    """Require the exact-byte stock/candidate binding before device I/O."""
    if not isinstance(binding, PhysicalBootIdentityBindingEvidence) or binding.schema_version != 1:
        raise TemporaryBootExecutionError("physical boot identity binding must be schema-v1 typed evidence")
    if binding.profile_id != profile.profile_id or gate.profile_id != profile.profile_id:
        raise TemporaryBootExecutionError("boot identity binding profile mismatch")
    if binding.device_serial != gate.device_serial or binding.device_serial != offer.evidence.device_serial:
        raise TemporaryBootExecutionError("boot identity binding device serial mismatch")
    if binding.physical_candidate_gate_sha256 != gate.evidence_sha256():
        raise TemporaryBootExecutionError("boot identity binding is detached from the physical candidate gate")
    if binding.physical_baseline_bundle_sha256 != gate.physical_baseline_bundle_sha256:
        raise TemporaryBootExecutionError("boot identity binding physical baseline is detached from the gate")
    if binding.stock_provenance_sha256 != gate.stock_provenance_sha256:
        raise TemporaryBootExecutionError("boot identity binding stock provenance is detached from the gate")
    if binding.boot_plan_sha256 != gate.boot_plan_sha256:
        raise TemporaryBootExecutionError("boot identity binding boot plan is detached from the gate")
    if binding.stock_boot_sha256 != gate.stock_boot_sha256:
        raise TemporaryBootExecutionError("boot identity binding stock boot differs from the gate")
    if (
        binding.candidate_boot_sha256 != gate.boot_image_sha256
        or binding.candidate_boot_size != gate.boot_image_size
        or binding.candidate_boot_sha256 != offer.evidence.boot_image_sha256
        or binding.candidate_boot_size != offer.evidence.boot_image_size
    ):
        raise TemporaryBootExecutionError("boot identity binding candidate boot differs from the exact offer/gate")
    if binding.candidate_kernel_sha256 != gate.kernel_image_sha256:
        raise TemporaryBootExecutionError("boot identity binding kernel differs from the reviewed gate")
    if binding.candidate_dtb_sha256 != gate.dtb_sha256:
        raise TemporaryBootExecutionError("boot identity binding DTB differs from the reviewed gate")
    if binding.candidate_external_dtbo_sha256 != gate.dtbo_image_sha256:
        raise TemporaryBootExecutionError("boot identity binding external DTBO differs from the reviewed gate")
    if (
        binding.stock_exact_bytes_verified is not True
        or binding.candidate_exact_bytes_verified is not True
        or binding.component_identity_bound is not True
        or binding.avb_layout_bound is not True
    ):
        raise TemporaryBootExecutionError("boot identity binding is not exact-byte/component/AVB complete")
    if (
        binding.temporary_boot_executed is not False
        or binding.phone_storage_written is not False
        or binding.hardware_verified is not False
        or binding.beta_gate_credit is not False
    ):
        raise TemporaryBootExecutionError("boot identity binding contains an invalid execution/write/hardware claim")


def _validate_recovery_readiness(
    profile: DeviceProfile,
    gate: PhysicalCandidateGateEvidence,
    binding: PhysicalBootIdentityBindingEvidence,
    baseline: FastbootBaselineEvidence,
    physical: PhysicalBaselineBundleEvidence,
    recovery: PhysicalRecoveryReadinessEvidence,
    offer: PreparedTemporaryBootOffer,
    *,
    stock_boot: Path,
) -> None:
    """Recompute the exact recovery-readiness record against local stock bytes."""
    if not isinstance(recovery, PhysicalRecoveryReadinessEvidence) or recovery.schema_version != 1:
        raise TemporaryBootExecutionError("physical recovery readiness must be schema-v1 typed evidence")
    try:
        verify_physical_recovery_readiness(
            recovery,
            profile,
            baseline,
            physical,
            binding,
            stock_boot=stock_boot,
        )
    except PhysicalRecoveryReadinessError as exc:
        raise TemporaryBootExecutionError(f"physical recovery readiness verification failed: {exc}") from exc

    if physical.evidence_sha256() != gate.physical_baseline_bundle_sha256:
        raise TemporaryBootExecutionError("recovery readiness physical baseline is detached from the candidate gate")
    if recovery.physical_baseline_bundle_sha256 != physical.evidence_sha256():
        raise TemporaryBootExecutionError("recovery readiness is detached from the exact physical baseline")
    if recovery.physical_boot_identity_binding_sha256 != binding.evidence_sha256():
        raise TemporaryBootExecutionError("recovery readiness is detached from the exact boot identity binding")
    if recovery.physical_candidate_gate_sha256 != gate.evidence_sha256():
        raise TemporaryBootExecutionError("recovery readiness is detached from the exact physical candidate gate")
    if recovery.fastboot_baseline_evidence_sha256 != baseline.evidence_sha256():
        raise TemporaryBootExecutionError("recovery readiness is detached from the exact Fastboot baseline")
    if recovery.boot_plan_sha256 != gate.boot_plan_sha256:
        raise TemporaryBootExecutionError("recovery readiness boot plan differs from the candidate gate")
    if recovery.stock_boot_sha256 != gate.stock_boot_sha256:
        raise TemporaryBootExecutionError("recovery readiness stock boot differs from the candidate gate")
    if (
        recovery.candidate_boot_sha256 != gate.boot_image_sha256
        or recovery.candidate_boot_size != gate.boot_image_size
        or recovery.candidate_boot_sha256 != offer.evidence.boot_image_sha256
        or recovery.candidate_boot_size != offer.evidence.boot_image_size
    ):
        raise TemporaryBootExecutionError("recovery readiness candidate boot differs from the exact offer/gate")
    if recovery.profile_id != profile.profile_id or recovery.device_serial != offer.evidence.device_serial:
        raise TemporaryBootExecutionError("recovery readiness device identity mismatch")
    if (
        recovery.firmware_build != baseline.firmware_build
        or recovery.firmware_fingerprint != baseline.firmware_fingerprint
    ):
        raise TemporaryBootExecutionError("recovery readiness firmware identity mismatch")
    if (
        recovery.stock_boot_material_present is not True
        or recovery.exact_stock_identity_bound is not True
        or recovery.slot_context_bound is not True
        or recovery.ready_for_temporary_boot_safety_review is not True
    ):
        raise TemporaryBootExecutionError("recovery readiness is incomplete for temporary-boot safety review")
    if (
        recovery.slot_switch_authorized is not False
        or recovery.inactive_slot_write_authorized is not False
        or recovery.persistent_write_authorized is not False
        or recovery.rollback_exercised is not False
        or recovery.recovery_verified is not False
        or recovery.hardware_verified is not False
        or recovery.beta_gate_credit is not False
    ):
        raise TemporaryBootExecutionError("recovery readiness contains an invalid authorization/recovery/hardware claim")


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
        raise TemporaryBootExecutionError(
            "fresh Fastboot probe is missing profile-required variables: " + ", ".join(missing)
        )

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


def _validate_runtime_recovery_slot_context(
    profile: DeviceProfile,
    recovery: PhysicalRecoveryReadinessEvidence,
    current_slot: str | None,
    slot_count: int | None,
) -> None:
    ab_device = profile.data.get("ab_device")
    if ab_device is True:
        if recovery.ab_device is not True:
            raise TemporaryBootExecutionError("recovery readiness A/B contract mismatch")
        if current_slot != recovery.captured_active_slot:
            raise TemporaryBootExecutionError("fresh active slot drifted from recovery readiness evidence")
        if slot_count != recovery.slot_count:
            raise TemporaryBootExecutionError("fresh slot count drifted from recovery readiness evidence")
        if recovery.captured_active_slot not in {"a", "b"} or recovery.expected_inactive_slot not in {"a", "b"}:
            raise TemporaryBootExecutionError("recovery readiness A/B slot context is incomplete")
        if recovery.captured_active_slot == recovery.expected_inactive_slot:
            raise TemporaryBootExecutionError("recovery readiness active/inactive slots are not distinct")
    elif ab_device is False:
        if recovery.ab_device is not False:
            raise TemporaryBootExecutionError("single-slot recovery readiness contract mismatch")
        if (
            recovery.captured_active_slot is not None
            or recovery.expected_inactive_slot is not None
            or recovery.slot_count is not None
        ):
            raise TemporaryBootExecutionError("single-slot recovery readiness invents A/B slot context")
    else:
        raise TemporaryBootExecutionError("profile ab_device contract must be boolean")


def _revalidate_pre_execution_material(
    profile: DeviceProfile,
    offer: PreparedTemporaryBootOffer,
    authorization: TemporaryBootUserAuthorizationEvidence,
    gate: PhysicalCandidateGateEvidence,
    binding: PhysicalBootIdentityBindingEvidence,
    capture: FastbootCaptureBundleEvidence,
    tool: FastbootToolEvidence,
    baseline: FastbootBaselineEvidence,
    physical: PhysicalBaselineBundleEvidence,
    recovery: PhysicalRecoveryReadinessEvidence,
    *,
    stock_boot: Path,
) -> None:
    """Close the host-side TOCTOU window after the fresh device probe.

    The read-only Fastboot probe can take measurable time. Re-hash the exact
    Fastboot executable, candidate boot image and stock recovery material after
    that probe and immediately before the allowed boot command. Any drift is a
    hard stop and no boot subprocess is invoked.
    """
    try:
        verify_temporary_boot_offer(offer, profile, gate, capture, tool)
    except TemporaryBootOfferError as exc:
        raise TemporaryBootExecutionError(f"pre-execution offer revalidation failed: {exc}") from exc
    _validate_boot_identity_binding(profile, gate, binding, offer)
    _validate_authorization(offer, authorization)
    _validate_baseline_binding(profile, baseline, capture)
    try:
        _validate_recovery_readiness(
            profile,
            gate,
            binding,
            baseline,
            physical,
            recovery,
            offer,
            stock_boot=stock_boot,
        )
    except TemporaryBootExecutionError as exc:
        raise TemporaryBootExecutionError(f"pre-execution recovery revalidation failed: {exc}") from exc


def probe_temporary_boot_runtime(
    profile: DeviceProfile,
    offer: PreparedTemporaryBootOffer,
    authorization: TemporaryBootUserAuthorizationEvidence,
    gate: PhysicalCandidateGateEvidence,
    binding: PhysicalBootIdentityBindingEvidence,
    capture: FastbootCaptureBundleEvidence,
    tool: FastbootToolEvidence,
    baseline: FastbootBaselineEvidence,
    physical: PhysicalBaselineBundleEvidence,
    recovery: PhysicalRecoveryReadinessEvidence,
    *,
    stock_boot: Path,
    timeout_seconds: int = DEFAULT_PROBE_TIMEOUT_SECONDS,
    runner: Callable[..., Any] = subprocess.run,
) -> TemporaryBootRuntimeProbeEvidence:
    """Revalidate exact files/recovery state, then perform one read-only Fastboot probe."""
    try:
        verify_temporary_boot_offer(offer, profile, gate, capture, tool)
    except TemporaryBootOfferError as exc:
        raise TemporaryBootExecutionError(str(exc)) from exc
    _validate_boot_identity_binding(profile, gate, binding, offer)
    _validate_authorization(offer, authorization)
    _validate_baseline_binding(profile, baseline, capture)
    _validate_recovery_readiness(
        profile,
        gate,
        binding,
        baseline,
        physical,
        recovery,
        offer,
        stock_boot=stock_boot,
    )
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
    try:
        slot_count = int(slot_count_value, 0) if slot_count_value is not None else None
    except ValueError as exc:
        raise TemporaryBootExecutionError("fresh Fastboot slot-count is not an integer") from exc
    current_slot = _value("current_slot_var")
    _validate_runtime_recovery_slot_context(profile, recovery, current_slot, slot_count)
    unlocked_value = _value("unlocked_var")
    secure_value = _value("secure_var")
    unlocked = unlocked_value is not None and unlocked_value.strip().lower() == "yes"
    secure = secure_value is not None and secure_value.strip().lower() == "yes"
    return TemporaryBootRuntimeProbeEvidence(
        schema_version=3,
        profile_id=profile.profile_id,
        device_serial=offer.evidence.device_serial,
        offer_sha256=offer.evidence.evidence_sha256(),
        authorization_sha256=authorization.evidence_sha256(),
        baseline_evidence_sha256=baseline.evidence_sha256(),
        capture_bundle_sha256=capture.evidence_sha256(),
        physical_baseline_bundle_sha256=physical.evidence_sha256(),
        boot_identity_binding_sha256=binding.evidence_sha256(),
        recovery_readiness_sha256=recovery.evidence_sha256(),
        recovery_stock_boot_sha256=recovery.stock_boot_sha256,
        fresh_transcript_sha256=sha256(transcript).hexdigest(),
        fresh_transcript_size=len(transcript),
        product=_value("identity_var") or "",
        current_slot=current_slot,
        slot_count=slot_count,
        captured_active_slot=recovery.captured_active_slot,
        expected_inactive_slot=recovery.expected_inactive_slot,
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
    binding: PhysicalBootIdentityBindingEvidence,
    capture: FastbootCaptureBundleEvidence,
    tool: FastbootToolEvidence,
    baseline: FastbootBaselineEvidence,
    physical: PhysicalBaselineBundleEvidence,
    recovery: PhysicalRecoveryReadinessEvidence,
    *,
    stock_boot: Path,
    probe_timeout_seconds: int = DEFAULT_PROBE_TIMEOUT_SECONDS,
    boot_timeout_seconds: int = DEFAULT_BOOT_TIMEOUT_SECONDS,
    runner: Callable[..., Any] = subprocess.run,
) -> tuple[TemporaryBootRuntimeProbeEvidence, TemporaryBootExecutionEvidence]:
    """Invoke exactly one serial-bound temporary boot after fail-closed checks.

    Exact boot identity and recovery readiness are validated before any Fastboot
    probe. The fresh probe then rechecks the device and A/B slot context. Finally,
    the exact Fastboot binary, candidate boot image, authorization bindings and
    local stock recovery material are revalidated *again* immediately before the
    one allowed ``boot`` verb. This closes the host-side probe-to-boot TOCTOU
    window without exposing persistent Fastboot operations.
    """
    probe = probe_temporary_boot_runtime(
        profile,
        offer,
        authorization,
        gate,
        binding,
        capture,
        tool,
        baseline,
        physical,
        recovery,
        stock_boot=stock_boot,
        timeout_seconds=probe_timeout_seconds,
        runner=runner,
    )

    # The read-only probe may take time. Do not trust file identity captured
    # before it: re-hash all executable/boot/recovery material at the last safe
    # boundary before invoking the single allowed Fastboot boot command.
    _revalidate_pre_execution_material(
        profile,
        offer,
        authorization,
        gate,
        binding,
        capture,
        tool,
        baseline,
        physical,
        recovery,
        stock_boot=stock_boot,
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
    if not isinstance(evidence, TemporaryBootRuntimeProbeEvidence) or evidence.schema_version != 3:
        raise TemporaryBootExecutionError("invalid temporary-boot runtime probe evidence")
    if (
        evidence.probe_policy != _RUNTIME_PROBE_POLICY
        or evidence.read_only is not True
        or evidence.phone_storage_written is not False
        or evidence.hardware_verified is not False
        or evidence.beta_gate_credit is not False
    ):
        raise TemporaryBootExecutionError("runtime probe evidence contains an invalid safety claim")
    for value, label in (
        (evidence.physical_baseline_bundle_sha256, "physical baseline"),
        (evidence.boot_identity_binding_sha256, "boot identity binding"),
        (evidence.recovery_readiness_sha256, "recovery readiness"),
        (evidence.recovery_stock_boot_sha256, "recovery stock boot"),
    ):
        if not _valid_sha(value):
            raise TemporaryBootExecutionError(f"runtime probe {label} digest is invalid")
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
