"""Import bounded physical boot logs without automatically granting hardware credit.

The temporary-boot executor can prove which exact host command was issued, but a
Fastboot return code cannot prove that the phone actually ran the intended kernel
or userspace. This module binds one raw physical-console/log capture to the exact
temporary-boot execution and offer, then detects only source-locked machine
markers and well-known diagnostic strings.

Raw captures are evidence inputs, not trusted assertions. Marker detection may
make an observation eligible for later human/hardware review, but evidence from
this module always records ``hardware_verified=false`` and
``beta_gate_credit=false``.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from .rescue_payload import RescuePayloadError, load_rescue_payload_lock
from .temporary_boot_execution import TemporaryBootExecutionEvidence
from .temporary_boot_offer import TemporaryBootOfferEvidence

SCHEMA_VERSION = 1
CONTRACT_SCHEMA_VERSION = 1
MAX_CAPTURE_BYTES = 16 * 1024 * 1024
MAX_LOCK_BYTES = 256 * 1024
MAX_INIT_BYTES = 256 * 1024
RESCUE_MARKER = "KPS_RESCUE_INIT_REACHED_V1"
RESCUE_SHELL_MARKER = "Entering local rescue shell. Persistent storage is not mounted automatically."
KERNEL_BANNER_MARKER = "Linux version "
_TEMPORARY_BOOT_COMMAND_POLICY = "fastboot-serial-temporary-boot-only-v1"
_TEMPORARY_BOOT_EXECUTION_POLICY = "single-serial-fastboot-boot-no-persistent-write-v1"
_SOURCE_KINDS = frozenset({"serial-console", "uart", "usb-serial", "operator-console-log"})
_PANIC_MARKERS = (
    b"Kernel panic - not syncing",
    b"Unable to handle kernel",
    b"Internal error: Oops",
    b"Oops:",
    b"BUG:",
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PhysicalBootObservationError(ValueError):
    pass


@dataclass(frozen=True)
class RescueObservationContract:
    schema_version: int
    payload_id: str
    payload_lock_file_sha256: str
    payload_source_lock_sha256: str
    init_relative_path: str
    init_sha256: str
    marker: str
    marker_sha256: str
    network_default: str
    ssh_default: str

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PhysicalBootObservationEvidence:
    schema_version: int
    profile_id: str
    device_serial: str
    temporary_boot_execution_sha256: str
    temporary_boot_offer_sha256: str
    physical_candidate_gate_sha256: str
    boot_image_sha256: str
    rescue_observation_contract_sha256: str
    rescue_payload_lock_file_sha256: str
    rescue_init_sha256: str
    source_kind: str
    raw_capture_sha256: str
    raw_capture_size: int
    normalized_text_sha256: str
    normalized_text_size: int
    fastboot_command_succeeded: bool
    kernel_banner_observed: bool
    rescue_init_marker_observed: bool
    rescue_shell_marker_observed: bool
    panic_marker_observed: bool
    first_rescue_marker_offset: int | None
    first_panic_marker: str | None
    observation_review_eligible: bool
    review_required: bool
    phone_storage_written_by_observer: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise PhysicalBootObservationError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _regular_bounded(path: Path, *, maximum: int, label: str) -> tuple[Path, bytes]:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise PhysicalBootObservationError(f"{label} must be a regular non-symlink file")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise PhysicalBootObservationError(f"cannot resolve {label}") from exc
    before = resolved.stat()
    if before.st_size <= 0 or before.st_size > maximum:
        raise PhysicalBootObservationError(f"{label} size is outside the safety bound")
    payload = resolved.read_bytes()
    after = resolved.stat()
    if (
        len(payload) != before.st_size
        or after.st_size != before.st_size
        or after.st_mtime_ns != before.st_mtime_ns
    ):
        raise PhysicalBootObservationError(f"{label} changed while being read")
    return resolved, payload


def load_rescue_observation_contract(
    lock_path: Path,
    repository_root: Path,
) -> RescueObservationContract:
    """Bind the machine marker to the exact checked source-lock and /init bytes."""
    resolved_lock, raw_lock = _regular_bounded(
        lock_path, maximum=MAX_LOCK_BYTES, label="rescue payload lock"
    )
    try:
        typed = load_rescue_payload_lock(resolved_lock)
    except RescuePayloadError as exc:
        raise PhysicalBootObservationError(str(exc)) from exc
    try:
        raw = json.loads(raw_lock.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalBootObservationError("rescue payload lock is not strict UTF-8 JSON") from exc
    materials = raw.get("materials") if isinstance(raw, dict) else None
    if not isinstance(materials, dict):
        raise PhysicalBootObservationError("rescue payload lock lacks materials")
    expected_init_sha256 = _sha(materials.get("init_sha256"), "rescue materials.init_sha256")

    root = Path(repository_root)
    if root.is_symlink() or not root.is_dir():
        raise PhysicalBootObservationError("repository root must be a real directory")
    try:
        root = root.resolve(strict=True)
    except OSError as exc:
        raise PhysicalBootObservationError("cannot resolve repository root") from exc
    init_candidate = root.joinpath(*typed.init_template.split("/"))
    if init_candidate.is_symlink():
        raise PhysicalBootObservationError("rescue /init template must not be a symlink")
    try:
        init_path = init_candidate.resolve(strict=True)
    except OSError as exc:
        raise PhysicalBootObservationError("rescue /init template is missing") from exc
    if root != init_path and root not in init_path.parents:
        raise PhysicalBootObservationError("rescue /init template escapes repository root")
    if not init_path.is_file():
        raise PhysicalBootObservationError("rescue /init template must be a regular file")
    init_before = init_path.stat()
    if init_before.st_size <= 0 or init_before.st_size > MAX_INIT_BYTES:
        raise PhysicalBootObservationError("rescue /init template size is outside the safety bound")
    init_bytes = init_path.read_bytes()
    init_after = init_path.stat()
    if (
        len(init_bytes) != init_before.st_size
        or init_after.st_size != init_before.st_size
        or init_after.st_mtime_ns != init_before.st_mtime_ns
    ):
        raise PhysicalBootObservationError("rescue /init template changed while being read")
    actual_init_sha256 = sha256(init_bytes).hexdigest()
    if actual_init_sha256 != expected_init_sha256:
        raise PhysicalBootObservationError("rescue /init bytes do not match the source-lock materials digest")
    marker_bytes = RESCUE_MARKER.encode("ascii")
    if init_bytes.count(marker_bytes) != 1:
        raise PhysicalBootObservationError("rescue /init must contain exactly one source-locked marker literal")
    if typed.network_default != "disabled" or typed.ssh_default != "disabled":
        raise PhysicalBootObservationError("rescue observation contract requires network and SSH disabled")

    return RescueObservationContract(
        schema_version=CONTRACT_SCHEMA_VERSION,
        payload_id=typed.payload_id,
        payload_lock_file_sha256=sha256(raw_lock).hexdigest(),
        payload_source_lock_sha256=typed.lock_sha256(),
        init_relative_path=typed.init_template,
        init_sha256=actual_init_sha256,
        marker=RESCUE_MARKER,
        marker_sha256=sha256(marker_bytes).hexdigest(),
        network_default="disabled",
        ssh_default="disabled",
    )


def _validate_execution_and_offer(
    execution: TemporaryBootExecutionEvidence,
    offer: TemporaryBootOfferEvidence,
) -> None:
    if not isinstance(execution, TemporaryBootExecutionEvidence) or execution.schema_version != 1:
        raise PhysicalBootObservationError("temporary-boot execution must be schema-v1 typed evidence")
    if not isinstance(offer, TemporaryBootOfferEvidence) or offer.schema_version != 1:
        raise PhysicalBootObservationError("temporary-boot offer must be schema-v1 typed evidence")
    if execution.execution_policy != _TEMPORARY_BOOT_EXECUTION_POLICY:
        raise PhysicalBootObservationError("temporary-boot execution policy mismatch")
    if offer.command_policy != _TEMPORARY_BOOT_COMMAND_POLICY:
        raise PhysicalBootObservationError("temporary-boot offer command policy mismatch")
    if execution.offer_sha256 != offer.evidence_sha256():
        raise PhysicalBootObservationError("temporary-boot execution is detached from the exact offer")
    if execution.profile_id != offer.profile_id or execution.device_serial != offer.device_serial:
        raise PhysicalBootObservationError("temporary-boot execution/offer identity mismatch")
    if execution.command_invoked is not True or execution.temporary_boot_executed is not True:
        raise PhysicalBootObservationError("temporary-boot execution evidence does not record an invoked boot")
    if not isinstance(execution.temporary_boot_command_succeeded, bool):
        raise PhysicalBootObservationError("temporary-boot command success flag must be boolean")
    if (
        execution.persistent_write is not False
        or execution.phone_storage_written is not False
        or execution.kali_userspace_verified is not False
        or execution.hardware_verified is not False
        or execution.beta_gate_credit is not False
    ):
        raise PhysicalBootObservationError("temporary-boot execution contains an invalid pre-review claim")
    if (
        offer.persistent_write is not False
        or offer.phone_storage_written is not False
        or offer.temporary_boot_executed is not False
        or offer.hardware_verified is not False
        or offer.beta_gate_credit is not False
    ):
        raise PhysicalBootObservationError("temporary-boot offer contains an invalid host-only claim")
    _sha(offer.physical_candidate_gate_sha256, "physical candidate gate digest")
    _sha(offer.boot_image_sha256, "boot image digest")


def _normalize_console_bytes(payload: bytes) -> bytes:
    return payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def create_physical_boot_observation(
    execution: TemporaryBootExecutionEvidence,
    offer: TemporaryBootOfferEvidence,
    contract: RescueObservationContract,
    *,
    raw_capture: Path,
    source_kind: str,
) -> PhysicalBootObservationEvidence:
    """Hash one physical log and record marker observations without auto-approval."""
    _validate_execution_and_offer(execution, offer)
    if not isinstance(contract, RescueObservationContract) or contract.schema_version != 1:
        raise PhysicalBootObservationError("rescue observation contract must be schema-v1 typed evidence")
    if contract.marker != RESCUE_MARKER:
        raise PhysicalBootObservationError("rescue observation marker contract mismatch")
    if source_kind not in _SOURCE_KINDS:
        raise PhysicalBootObservationError(
            "source_kind must be one of: " + ", ".join(sorted(_SOURCE_KINDS))
        )
    _path, raw = _regular_bounded(
        raw_capture, maximum=MAX_CAPTURE_BYTES, label="physical boot capture"
    )
    normalized = _normalize_console_bytes(raw)
    marker_bytes = contract.marker.encode("ascii")
    shell_bytes = RESCUE_SHELL_MARKER.encode("ascii")
    kernel_bytes = KERNEL_BANNER_MARKER.encode("ascii")
    rescue_offset = normalized.find(marker_bytes)
    panic_hits = [(normalized.find(marker), marker) for marker in _PANIC_MARKERS]
    panic_hits = [(offset, marker) for offset, marker in panic_hits if offset >= 0]
    panic_hits.sort(key=lambda item: item[0])
    first_panic = panic_hits[0][1].decode("ascii", errors="strict") if panic_hits else None
    rescue_seen = rescue_offset >= 0
    shell_seen = shell_bytes in normalized
    kernel_seen = kernel_bytes in normalized
    panic_seen = bool(panic_hits)
    review_eligible = bool(
        execution.temporary_boot_command_succeeded
        and rescue_seen
        and shell_seen
        and not panic_seen
    )
    return PhysicalBootObservationEvidence(
        schema_version=SCHEMA_VERSION,
        profile_id=execution.profile_id,
        device_serial=execution.device_serial,
        temporary_boot_execution_sha256=execution.evidence_sha256(),
        temporary_boot_offer_sha256=offer.evidence_sha256(),
        physical_candidate_gate_sha256=offer.physical_candidate_gate_sha256,
        boot_image_sha256=offer.boot_image_sha256,
        rescue_observation_contract_sha256=contract.evidence_sha256(),
        rescue_payload_lock_file_sha256=contract.payload_lock_file_sha256,
        rescue_init_sha256=contract.init_sha256,
        source_kind=source_kind,
        raw_capture_sha256=sha256(raw).hexdigest(),
        raw_capture_size=len(raw),
        normalized_text_sha256=sha256(normalized).hexdigest(),
        normalized_text_size=len(normalized),
        fastboot_command_succeeded=execution.temporary_boot_command_succeeded,
        kernel_banner_observed=kernel_seen,
        rescue_init_marker_observed=rescue_seen,
        rescue_shell_marker_observed=shell_seen,
        panic_marker_observed=panic_seen,
        first_rescue_marker_offset=rescue_offset if rescue_seen else None,
        first_panic_marker=first_panic,
        observation_review_eligible=review_eligible,
        review_required=True,
        phone_storage_written_by_observer=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def write_physical_boot_observation(
    evidence: PhysicalBootObservationEvidence,
    destination: Path,
) -> str:
    if not isinstance(evidence, PhysicalBootObservationEvidence) or evidence.schema_version != 1:
        raise PhysicalBootObservationError("invalid physical boot observation evidence")
    if (
        evidence.review_required is not True
        or evidence.phone_storage_written_by_observer is not False
        or evidence.hardware_verified is not False
        or evidence.beta_gate_credit is not False
    ):
        raise PhysicalBootObservationError("physical boot observation contains an invalid automatic claim")
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise PhysicalBootObservationError("refusing to overwrite physical boot observation evidence")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise PhysicalBootObservationError("refusing stale physical boot observation temporary path")
    payload = evidence.canonical_json()
    try:
        temporary.write_text(payload, encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()
