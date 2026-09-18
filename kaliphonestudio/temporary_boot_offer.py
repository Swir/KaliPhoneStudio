"""Prepare a strictly scoped temporary-Fastboot-boot offer without executing it.

The physical-candidate gate proves that one exact device/firmware/candidate chain is
eligible to *offer* a temporary boot.  Before an offer can exist, schema-v2 now also
requires the exact stock/candidate boot-identity binding produced from re-inspected
boot bytes, component identities, optional AVB layout and profile-required DTBO.
The module then rehashes the exact Fastboot executable and candidate boot image,
joins them to the original read-only Fastboot capture/tool evidence, and produces
one argv-only command plan.  It never invokes subprocesses and never writes phone
storage.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re

from .fastboot_capture_bundle import FastbootCaptureBundleEvidence
from .fastboot_tool import FastbootToolEvidence, MAX_FASTBOOT_BINARY_BYTES
from .physical_boot_identity_binding import PhysicalBootIdentityBindingEvidence
from .physical_candidate_gate import PhysicalCandidateGateEvidence
from .profiles import DeviceProfile
from .safety import SafetyError, require_confirmation
from .temporary_boot_binding import (
    TemporaryBootBindingError,
    require_temporary_boot_identity_binding,
)

_COMMAND_POLICY = "fastboot-serial-temporary-boot-only-v2-exact-boot-identity"
_MAX_BOOT_IMAGE_BYTES = 1024 * 1024 * 1024
_SERIAL_RE = re.compile(r"^[!-~]{1,128}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class TemporaryBootOfferError(ValueError):
    pass


@dataclass(frozen=True)
class TemporaryBootOfferEvidence:
    schema_version: int
    profile_id: str
    device_serial: str
    physical_candidate_gate_sha256: str
    physical_boot_identity_binding_sha256: str
    fastboot_capture_bundle_sha256: str
    fastboot_tool_evidence_sha256: str
    fastboot_tool_policy_sha256: str
    fastboot_executable_sha256: str
    fastboot_executable_size: int
    platform_tools_version: str
    boot_image_sha256: str
    boot_image_size: int
    confirmation_text_sha256: str
    command_policy: str
    persistent_write: bool
    phone_storage_written: bool
    temporary_boot_executed: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PreparedTemporaryBootOffer:
    evidence: TemporaryBootOfferEvidence
    boot_identity_binding: PhysicalBootIdentityBindingEvidence
    fastboot_executable: Path
    boot_image: Path
    argv: tuple[str, ...]


@dataclass(frozen=True)
class TemporaryBootUserAuthorizationEvidence:
    schema_version: int
    offer_sha256: str
    profile_id: str
    device_serial: str
    confirmation_text_sha256: str
    confirmation_verified: bool
    execution_permitted: bool
    temporary_boot_executed: bool
    persistent_write: bool
    phone_storage_written: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise TemporaryBootOfferError(f"{label} must be a lowercase SHA-256")
    return value


def _positive(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise TemporaryBootOfferError(f"{label} must be a positive integer")
    return value


def _serial(value: object) -> str:
    if not isinstance(value, str) or not _SERIAL_RE.fullmatch(value):
        raise TemporaryBootOfferError("temporary-boot serial contains unsafe data")
    if value.startswith("-") or any(ch.isspace() for ch in value):
        raise TemporaryBootOfferError("temporary-boot serial contains unsafe data")
    return value


def _confirmation(profile: DeviceProfile) -> str:
    value = profile.confirmation_text
    if not isinstance(value, str) or not value or len(value) > 128:
        raise TemporaryBootOfferError("profile confirmation text is invalid")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise TemporaryBootOfferError("profile confirmation text contains control data")
    return value


def _hash_regular(path: Path, *, maximum: int, label: str) -> tuple[Path, str, int]:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise TemporaryBootOfferError(f"{label} must be a regular non-symlink file")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise TemporaryBootOfferError(f"cannot resolve {label}") from exc
    if resolved.is_symlink() or not resolved.is_file():
        raise TemporaryBootOfferError(f"{label} must resolve to a regular file")
    before = resolved.stat()
    if before.st_size <= 0 or before.st_size > maximum:
        raise TemporaryBootOfferError(f"{label} size is outside the safety bound")
    digest = sha256()
    size = 0
    with resolved.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    after = resolved.stat()
    if (
        size != before.st_size
        or after.st_size != before.st_size
        or after.st_mtime_ns != before.st_mtime_ns
    ):
        raise TemporaryBootOfferError(f"{label} changed while being verified")
    return resolved, digest.hexdigest(), size


def prepare_temporary_boot_offer(
    profile: DeviceProfile,
    gate: PhysicalCandidateGateEvidence,
    capture: FastbootCaptureBundleEvidence,
    tool: FastbootToolEvidence,
    *,
    boot_identity_binding: PhysicalBootIdentityBindingEvidence,
    fastboot_executable: Path,
    boot_image: Path,
) -> PreparedTemporaryBootOffer:
    """Prepare one exact ``fastboot -s SERIAL boot IMAGE`` argv; never execute it."""
    profile_id = profile.profile_id
    if not isinstance(gate, PhysicalCandidateGateEvidence) or gate.schema_version != 1:
        raise TemporaryBootOfferError("physical candidate gate must be schema-v1 typed evidence")
    if gate.profile_id != profile_id:
        raise TemporaryBootOfferError("physical candidate gate profile mismatch")
    serial = _serial(gate.device_serial)
    if gate.ready_for_temporary_boot_offer is not True:
        raise TemporaryBootOfferError("physical candidate gate does not allow a temporary-boot offer")
    if (
        gate.temporary_boot_executed is not False
        or gate.phone_storage_written is not False
        or gate.hardware_verified is not False
        or gate.beta_gate_credit is not False
    ):
        raise TemporaryBootOfferError("physical candidate gate contains an invalid host-only claim")

    try:
        binding_sha = require_temporary_boot_identity_binding(
            profile,
            gate,
            boot_identity_binding,
        )
    except TemporaryBootBindingError as exc:
        raise TemporaryBootOfferError(str(exc)) from exc

    if not isinstance(capture, FastbootCaptureBundleEvidence) or capture.schema_version != 1:
        raise TemporaryBootOfferError("Fastboot capture bundle must be schema-v1 typed evidence")
    if capture.evidence_sha256() != gate.fastboot_capture_bundle_sha256:
        raise TemporaryBootOfferError("Fastboot capture bundle is detached from physical candidate gate")
    if capture.profile_id != profile_id or capture.device_serial != serial:
        raise TemporaryBootOfferError("Fastboot capture bundle identity mismatch")
    if (
        capture.baseline_evidence_sha256 != gate.fastboot_baseline_evidence_sha256
        or capture.transcript_sha256 != gate.fastboot_transcript_sha256
    ):
        raise TemporaryBootOfferError("Fastboot capture baseline/transcript is detached from gate")
    if (
        capture.read_only is not True
        or capture.phone_storage_written is not False
        or capture.hardware_verified is not False
        or capture.beta_gate_credit is not False
    ):
        raise TemporaryBootOfferError("Fastboot capture bundle is not read-only host evidence")

    if not isinstance(tool, FastbootToolEvidence) or tool.schema_version != 1 or tool.tool != "fastboot":
        raise TemporaryBootOfferError("Fastboot tool evidence is unsupported")
    if tool.evidence_sha256() != capture.fastboot_tool_evidence_sha256:
        raise TemporaryBootOfferError("Fastboot tool evidence is detached from capture bundle")
    if tool.policy_sha256 != capture.fastboot_tool_policy_sha256:
        raise TemporaryBootOfferError("Fastboot tool policy is detached from capture bundle")
    if (
        tool.executable_sha256 != capture.fastboot_executable_sha256
        or tool.executable_size != capture.fastboot_executable_size
        or tool.observed_platform_tools_version != capture.platform_tools_version
    ):
        raise TemporaryBootOfferError("Fastboot executable/version identity drifted from capture")
    if tool.required_platform_tools_version != tool.observed_platform_tools_version:
        raise TemporaryBootOfferError("Fastboot tool evidence does not prove the reviewed exact version")
    if tool.hardware_verified is not False or tool.beta_gate_credit is not False:
        raise TemporaryBootOfferError("Fastboot tool evidence illegally claims hardware/Beta credit")

    executable, executable_sha, executable_size = _hash_regular(
        fastboot_executable,
        maximum=MAX_FASTBOOT_BINARY_BYTES,
        label="Fastboot executable",
    )
    if executable.name != tool.executable_filename:
        raise TemporaryBootOfferError("Fastboot executable filename differs from reviewed tool evidence")
    if executable_sha != tool.executable_sha256 or executable_size != tool.executable_size:
        raise TemporaryBootOfferError("Fastboot executable bytes differ from reviewed capture tool")

    image, image_sha, image_size = _hash_regular(
        boot_image,
        maximum=_MAX_BOOT_IMAGE_BYTES,
        label="candidate boot image",
    )
    if image_sha != gate.boot_image_sha256 or image_size != gate.boot_image_size:
        raise TemporaryBootOfferError("candidate boot image bytes differ from physical candidate gate")
    if (
        image_sha != boot_identity_binding.candidate_boot_sha256
        or image_size != boot_identity_binding.candidate_boot_size
    ):
        raise TemporaryBootOfferError("candidate boot image bytes differ from exact boot identity binding")
    try:
        boot_limit = profile.data["partition_limits"]["boot"]
    except (KeyError, TypeError) as exc:
        raise TemporaryBootOfferError("profile does not define a boot partition limit") from exc
    if not isinstance(boot_limit, int) or isinstance(boot_limit, bool) or boot_limit <= 0:
        raise TemporaryBootOfferError("profile boot partition limit is invalid")
    if image_size > boot_limit:
        raise TemporaryBootOfferError("candidate boot image exceeds profile boot partition limit")

    confirmation = _confirmation(profile)
    for value, label in (
        (gate.evidence_sha256(), "physical candidate gate SHA-256"),
        (binding_sha, "physical boot identity binding SHA-256"),
        (capture.evidence_sha256(), "Fastboot capture bundle SHA-256"),
        (tool.evidence_sha256(), "Fastboot tool evidence SHA-256"),
        (tool.policy_sha256, "Fastboot tool policy SHA-256"),
        (executable_sha, "Fastboot executable SHA-256"),
        (image_sha, "candidate boot image SHA-256"),
    ):
        _sha(value, label)
    _positive(executable_size, "Fastboot executable size")
    _positive(image_size, "candidate boot image size")

    evidence = TemporaryBootOfferEvidence(
        schema_version=2,
        profile_id=profile_id,
        device_serial=serial,
        physical_candidate_gate_sha256=gate.evidence_sha256(),
        physical_boot_identity_binding_sha256=binding_sha,
        fastboot_capture_bundle_sha256=capture.evidence_sha256(),
        fastboot_tool_evidence_sha256=tool.evidence_sha256(),
        fastboot_tool_policy_sha256=tool.policy_sha256,
        fastboot_executable_sha256=executable_sha,
        fastboot_executable_size=executable_size,
        platform_tools_version=tool.observed_platform_tools_version,
        boot_image_sha256=image_sha,
        boot_image_size=image_size,
        confirmation_text_sha256=sha256(confirmation.encode("utf-8")).hexdigest(),
        command_policy=_COMMAND_POLICY,
        persistent_write=False,
        phone_storage_written=False,
        temporary_boot_executed=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    argv = (str(executable), "-s", serial, "boot", str(image))
    return PreparedTemporaryBootOffer(
        evidence=evidence,
        boot_identity_binding=boot_identity_binding,
        fastboot_executable=executable,
        boot_image=image,
        argv=argv,
    )


def verify_temporary_boot_offer(
    offer: PreparedTemporaryBootOffer,
    profile: DeviceProfile,
    gate: PhysicalCandidateGateEvidence,
    capture: FastbootCaptureBundleEvidence,
    tool: FastbootToolEvidence,
) -> None:
    expected = prepare_temporary_boot_offer(
        profile,
        gate,
        capture,
        tool,
        boot_identity_binding=offer.boot_identity_binding,
        fastboot_executable=offer.fastboot_executable,
        boot_image=offer.boot_image,
    )
    if offer != expected:
        raise TemporaryBootOfferError("temporary-boot offer no longer matches exact inputs")


def authorize_temporary_boot_offer(
    offer: PreparedTemporaryBootOffer,
    profile: DeviceProfile,
    typed_confirmation: str,
) -> TemporaryBootUserAuthorizationEvidence:
    """Record explicit profile-specific user confirmation; still do not execute Fastboot."""
    if offer.evidence.schema_version != 2:
        raise TemporaryBootOfferError("temporary-boot offer must use schema-v2 exact-identity binding")
    if offer.evidence.profile_id != profile.profile_id:
        raise TemporaryBootOfferError("temporary-boot offer belongs to a different profile")
    if offer.evidence.physical_boot_identity_binding_sha256 != offer.boot_identity_binding.evidence_sha256():
        raise TemporaryBootOfferError("temporary-boot offer is detached from exact boot identity binding")
    confirmation = _confirmation(profile)
    confirmation_sha = sha256(confirmation.encode("utf-8")).hexdigest()
    if offer.evidence.confirmation_text_sha256 != confirmation_sha:
        raise TemporaryBootOfferError("temporary-boot offer confirmation policy drifted")
    try:
        require_confirmation(profile, typed_confirmation)
    except SafetyError as exc:
        raise TemporaryBootOfferError(str(exc)) from exc
    return TemporaryBootUserAuthorizationEvidence(
        schema_version=1,
        offer_sha256=offer.evidence.evidence_sha256(),
        profile_id=profile.profile_id,
        device_serial=offer.evidence.device_serial,
        confirmation_text_sha256=confirmation_sha,
        confirmation_verified=True,
        execution_permitted=True,
        temporary_boot_executed=False,
        persistent_write=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def write_temporary_boot_offer(evidence: TemporaryBootOfferEvidence, destination: Path) -> str:
    if not isinstance(evidence, TemporaryBootOfferEvidence) or evidence.schema_version != 2:
        raise TemporaryBootOfferError("invalid schema-v2 temporary-boot offer evidence")
    _sha(
        evidence.physical_boot_identity_binding_sha256,
        "physical boot identity binding SHA-256",
    )
    if (
        evidence.persistent_write is not False
        or evidence.phone_storage_written is not False
        or evidence.temporary_boot_executed is not False
        or evidence.hardware_verified is not False
        or evidence.beta_gate_credit is not False
    ):
        raise TemporaryBootOfferError("temporary-boot offer evidence contains an invalid execution/write claim")
    if evidence.command_policy != _COMMAND_POLICY:
        raise TemporaryBootOfferError("temporary-boot command policy mismatch")
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise TemporaryBootOfferError(f"refusing to overwrite temporary-boot offer evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise TemporaryBootOfferError("refusing stale temporary-boot offer temporary path")
    try:
        temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()
