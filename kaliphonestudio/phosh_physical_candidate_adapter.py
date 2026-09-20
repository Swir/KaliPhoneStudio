"""Bind a reviewed Phosh successor candidate to an existing exact physical gate.

This adapter is intentionally host-only. It joins the immutable Phosh successor
candidate to the already-reviewed physical-candidate gate for the same phone,
firmware, Fastboot baseline, boot image, kernel and device-tree identity.

A successful adapter record means only that the replacement Phosh rootfs is
cryptographically scoped to the same physical campaign identity. It does not select
a storage target, stage the rootfs, execute Fastboot, authorize a temporary boot,
write phone storage, verify hardware, or grant Beta credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, TypeVar

from .phosh_successor_candidate import (
    PhoshSuccessorCandidateError,
    PhoshSuccessorCandidateManifest,
    validate_phosh_successor_candidate,
)
from .physical_candidate_gate import PhysicalCandidateGateEvidence
from .stable_file import StableFileError, read_stable_regular_file

_POLICY = "phosh-successor-physical-gate-adapter-v1"
_MAX_EVIDENCE_BYTES = 2 * 1024 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
T = TypeVar("T")


class PhoshPhysicalCandidateAdapterError(ValueError):
    """Raised when a Phosh successor cannot be scoped to one physical gate."""


@dataclass(frozen=True)
class PhoshPhysicalCandidateAdapterEvidence:
    schema_version: int
    adapter_policy: str
    profile_id: str
    device_serial: str
    firmware_build: str
    firmware_fingerprint: str
    physical_candidate_gate_sha256: str
    physical_baseline_bundle_sha256: str
    fastboot_baseline_evidence_sha256: str
    fastboot_transcript_sha256: str
    stock_ota_sha256: str
    stock_boot_sha256: str
    base_first_boot_manifest_sha256: str
    base_candidate_authority_bundle_sha256: str
    phosh_successor_candidate_sha256: str
    phosh_first_boot_binding_sha256: str
    boot_authorization_sha256: str
    boot_plan_sha256: str
    boot_image_sha256: str
    boot_image_size: int
    kernel_image_sha256: str
    dtb_sha256: str | None
    dtbo_image_sha256: str | None
    superseded_rootfs_artifact_sha256: str
    phosh_rootfs_authority_sha256: str
    phosh_review_packet_sha256: str
    rootfs_artifact_sha256: str
    rootfs_artifact_size: int
    rootfs_package_manifest_sha256: str
    rootfs_package_count: int
    exact_physical_gate_bound: bool
    reviewed_phosh_successor_bound: bool
    ready_for_physical_staging_review: bool
    physical_validation_required: bool
    staging_target_selected: bool
    rootfs_staged: bool
    temporary_boot_authorized: bool
    temporary_boot_executed: bool
    phone_storage_written: bool
    hardware_verified: bool
    beta_release_authorized: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise PhoshPhysicalCandidateAdapterError(f"{label} must be a lowercase SHA-256")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PhoshPhysicalCandidateAdapterError(f"{label} must be a non-empty string")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise PhoshPhysicalCandidateAdapterError(f"{label} contains control data")
    return value


def _positive(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PhoshPhysicalCandidateAdapterError(f"{label} must be a positive integer")
    return value


def _optional_sha(value: object, label: str) -> None:
    if value is not None:
        _sha(value, label)


def _validate_physical_gate(gate: PhysicalCandidateGateEvidence) -> None:
    if not isinstance(gate, PhysicalCandidateGateEvidence) or gate.schema_version != 1:
        raise PhoshPhysicalCandidateAdapterError(
            "physical candidate gate must be schema-v1 typed evidence"
        )
    for label, value in (
        ("profile_id", gate.profile_id),
        ("device_serial", gate.device_serial),
        ("firmware_build", gate.firmware_build),
        ("firmware_fingerprint", gate.firmware_fingerprint),
    ):
        _text(value, label)
    for label, value in (
        ("physical baseline bundle", gate.physical_baseline_bundle_sha256),
        ("Fastboot capture bundle", gate.fastboot_capture_bundle_sha256),
        ("Fastboot baseline", gate.fastboot_baseline_evidence_sha256),
        ("Fastboot transcript", gate.fastboot_transcript_sha256),
        ("stock provenance", gate.stock_provenance_sha256),
        ("stock OTA", gate.stock_ota_sha256),
        ("stock boot", gate.stock_boot_sha256),
        ("first-boot manifest", gate.first_boot_manifest_sha256),
        ("first-boot authority bundle", gate.first_boot_authority_bundle_sha256),
        ("boot authorization", gate.boot_authorization_sha256),
        ("boot plan", gate.boot_plan_sha256),
        ("boot image", gate.boot_image_sha256),
        ("kernel image", gate.kernel_image_sha256),
        ("legacy rootfs artifact", gate.rootfs_artifact_sha256),
    ):
        _sha(value, label)
    _positive(gate.boot_image_size, "boot image size")
    _optional_sha(gate.dtb_sha256, "DTB")
    _optional_sha(gate.dtbo_image_sha256, "DTBO")
    if (
        gate.reviewed_authorities_bound is not True
        or gate.exact_physical_baseline_bound is not True
        or gate.ready_for_temporary_boot_offer is not True
    ):
        raise PhoshPhysicalCandidateAdapterError(
            "physical candidate gate is not reviewed/baseline-bound/offer-ready"
        )
    for name in (
        "temporary_boot_executed",
        "phone_storage_written",
        "hardware_verified",
        "beta_gate_credit",
    ):
        if getattr(gate, name) is not False:
            raise PhoshPhysicalCandidateAdapterError(
                f"physical candidate gate cannot enter adapter with {name}=true"
            )


def validate_phosh_physical_candidate_adapter(
    evidence: PhoshPhysicalCandidateAdapterEvidence,
) -> None:
    if (
        not isinstance(evidence, PhoshPhysicalCandidateAdapterEvidence)
        or evidence.schema_version != 1
    ):
        raise PhoshPhysicalCandidateAdapterError(
            "Phosh physical candidate adapter must be schema-v1 typed evidence"
        )
    if evidence.adapter_policy != _POLICY:
        raise PhoshPhysicalCandidateAdapterError(
            "unsupported Phosh physical candidate adapter policy"
        )
    for label, value in (
        ("profile_id", evidence.profile_id),
        ("device_serial", evidence.device_serial),
        ("firmware_build", evidence.firmware_build),
        ("firmware_fingerprint", evidence.firmware_fingerprint),
    ):
        _text(value, label)
    for label, value in (
        ("physical candidate gate", evidence.physical_candidate_gate_sha256),
        ("physical baseline bundle", evidence.physical_baseline_bundle_sha256),
        ("Fastboot baseline", evidence.fastboot_baseline_evidence_sha256),
        ("Fastboot transcript", evidence.fastboot_transcript_sha256),
        ("stock OTA", evidence.stock_ota_sha256),
        ("stock boot", evidence.stock_boot_sha256),
        ("base first-boot manifest", evidence.base_first_boot_manifest_sha256),
        ("base candidate authority bundle", evidence.base_candidate_authority_bundle_sha256),
        ("Phosh successor candidate", evidence.phosh_successor_candidate_sha256),
        ("Phosh first-boot binding", evidence.phosh_first_boot_binding_sha256),
        ("boot authorization", evidence.boot_authorization_sha256),
        ("boot plan", evidence.boot_plan_sha256),
        ("boot image", evidence.boot_image_sha256),
        ("kernel image", evidence.kernel_image_sha256),
        ("superseded rootfs", evidence.superseded_rootfs_artifact_sha256),
        ("Phosh rootfs authority", evidence.phosh_rootfs_authority_sha256),
        ("Phosh review packet", evidence.phosh_review_packet_sha256),
        ("Phosh rootfs artifact", evidence.rootfs_artifact_sha256),
        ("Phosh package manifest", evidence.rootfs_package_manifest_sha256),
    ):
        _sha(value, label)
    _positive(evidence.boot_image_size, "boot image size")
    _positive(evidence.rootfs_artifact_size, "Phosh rootfs artifact size")
    _positive(evidence.rootfs_package_count, "Phosh package count")
    _optional_sha(evidence.dtb_sha256, "DTB")
    _optional_sha(evidence.dtbo_image_sha256, "DTBO")
    if evidence.superseded_rootfs_artifact_sha256 == evidence.rootfs_artifact_sha256:
        raise PhoshPhysicalCandidateAdapterError(
            "Phosh rootfs must differ from superseded physical-gate rootfs"
        )
    for name in (
        "exact_physical_gate_bound",
        "reviewed_phosh_successor_bound",
        "ready_for_physical_staging_review",
        "physical_validation_required",
    ):
        if getattr(evidence, name) is not True:
            raise PhoshPhysicalCandidateAdapterError(
                f"Phosh physical adapter requires {name}=true"
            )
    for name in (
        "staging_target_selected",
        "rootfs_staged",
        "temporary_boot_authorized",
        "temporary_boot_executed",
        "phone_storage_written",
        "hardware_verified",
        "beta_release_authorized",
        "beta_gate_credit",
    ):
        if getattr(evidence, name) is not False:
            raise PhoshPhysicalCandidateAdapterError(
                f"host adapter cannot promote {name}"
            )


def bind_phosh_successor_to_physical_gate(
    successor: PhoshSuccessorCandidateManifest,
    physical_gate: PhysicalCandidateGateEvidence,
) -> PhoshPhysicalCandidateAdapterEvidence:
    """Cross-bind one reviewed Phosh successor to one exact physical campaign gate."""
    try:
        validate_phosh_successor_candidate(successor)
    except PhoshSuccessorCandidateError as exc:
        raise PhoshPhysicalCandidateAdapterError(str(exc)) from exc
    _validate_physical_gate(physical_gate)

    for observed, expected, label in (
        (successor.profile_id, physical_gate.profile_id, "profile"),
        (successor.device_serial, physical_gate.device_serial, "device serial"),
        (successor.firmware_build, physical_gate.firmware_build, "firmware build"),
        (
            successor.firmware_fingerprint,
            physical_gate.firmware_fingerprint,
            "firmware fingerprint",
        ),
        (
            successor.fastboot_baseline_sha256,
            physical_gate.fastboot_baseline_evidence_sha256,
            "Fastboot baseline",
        ),
        (
            successor.base_first_boot_manifest_sha256,
            physical_gate.first_boot_manifest_sha256,
            "base first-boot manifest",
        ),
        (
            successor.base_candidate_authority_bundle_sha256,
            physical_gate.first_boot_authority_bundle_sha256,
            "base authority bundle",
        ),
        (
            successor.boot_authorization_sha256,
            physical_gate.boot_authorization_sha256,
            "boot authorization",
        ),
        (successor.boot_plan_sha256, physical_gate.boot_plan_sha256, "boot plan"),
        (successor.boot_image_sha256, physical_gate.boot_image_sha256, "boot image"),
        (successor.boot_image_size, physical_gate.boot_image_size, "boot image size"),
        (successor.kernel_image_sha256, physical_gate.kernel_image_sha256, "kernel image"),
        (successor.dtb_sha256, physical_gate.dtb_sha256, "DTB"),
        (successor.dtbo_image_sha256, physical_gate.dtbo_image_sha256, "DTBO"),
        (
            successor.superseded_rootfs_artifact_sha256,
            physical_gate.rootfs_artifact_sha256,
            "superseded rootfs",
        ),
    ):
        if observed != expected:
            raise PhoshPhysicalCandidateAdapterError(
                f"Phosh successor {label} is detached from exact physical candidate gate"
            )

    evidence = PhoshPhysicalCandidateAdapterEvidence(
        schema_version=1,
        adapter_policy=_POLICY,
        profile_id=successor.profile_id,
        device_serial=successor.device_serial,
        firmware_build=successor.firmware_build,
        firmware_fingerprint=successor.firmware_fingerprint,
        physical_candidate_gate_sha256=physical_gate.evidence_sha256(),
        physical_baseline_bundle_sha256=physical_gate.physical_baseline_bundle_sha256,
        fastboot_baseline_evidence_sha256=physical_gate.fastboot_baseline_evidence_sha256,
        fastboot_transcript_sha256=physical_gate.fastboot_transcript_sha256,
        stock_ota_sha256=physical_gate.stock_ota_sha256,
        stock_boot_sha256=physical_gate.stock_boot_sha256,
        base_first_boot_manifest_sha256=successor.base_first_boot_manifest_sha256,
        base_candidate_authority_bundle_sha256=successor.base_candidate_authority_bundle_sha256,
        phosh_successor_candidate_sha256=successor.manifest_sha256(),
        phosh_first_boot_binding_sha256=successor.phosh_first_boot_binding_sha256,
        boot_authorization_sha256=successor.boot_authorization_sha256,
        boot_plan_sha256=successor.boot_plan_sha256,
        boot_image_sha256=successor.boot_image_sha256,
        boot_image_size=successor.boot_image_size,
        kernel_image_sha256=successor.kernel_image_sha256,
        dtb_sha256=successor.dtb_sha256,
        dtbo_image_sha256=successor.dtbo_image_sha256,
        superseded_rootfs_artifact_sha256=successor.superseded_rootfs_artifact_sha256,
        phosh_rootfs_authority_sha256=successor.phosh_rootfs_authority_sha256,
        phosh_review_packet_sha256=successor.phosh_review_packet_sha256,
        rootfs_artifact_sha256=successor.rootfs_artifact_sha256,
        rootfs_artifact_size=successor.rootfs_artifact_size,
        rootfs_package_manifest_sha256=successor.rootfs_package_manifest_sha256,
        rootfs_package_count=successor.rootfs_package_count,
        exact_physical_gate_bound=True,
        reviewed_phosh_successor_bound=True,
        ready_for_physical_staging_review=True,
        physical_validation_required=True,
        staging_target_selected=False,
        rootfs_staged=False,
        temporary_boot_authorized=False,
        temporary_boot_executed=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_release_authorized=False,
        beta_gate_credit=False,
    )
    validate_phosh_physical_candidate_adapter(evidence)
    return evidence


def _load_typed_canonical(cls: type[T], path: Path, label: str) -> T:
    try:
        payload, _identity = read_stable_regular_file(
            Path(path), max_bytes=_MAX_EVIDENCE_BYTES, label=label
        )
    except StableFileError as exc:
        raise PhoshPhysicalCandidateAdapterError(str(exc)) from exc
    try:
        raw: Any = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhoshPhysicalCandidateAdapterError(
            f"{label} is not valid UTF-8 JSON"
        ) from exc
    expected = {item.name for item in fields(cls)}
    if not isinstance(raw, dict) or set(raw) != expected:
        raise PhoshPhysicalCandidateAdapterError(
            f"{label} fields do not match typed schema"
        )
    try:
        evidence = cls(**raw)
    except (TypeError, ValueError) as exc:
        raise PhoshPhysicalCandidateAdapterError(
            f"{label} field types are invalid"
        ) from exc
    canonical = getattr(evidence, "canonical_json", None)
    if not callable(canonical) or payload != canonical().encode("utf-8"):
        raise PhoshPhysicalCandidateAdapterError(f"{label} is not canonical JSON")
    return evidence


def build_phosh_physical_candidate_adapter_from_paths(
    successor_candidate_path: Path,
    physical_candidate_gate_path: Path,
) -> PhoshPhysicalCandidateAdapterEvidence:
    successor = _load_typed_canonical(
        PhoshSuccessorCandidateManifest,
        successor_candidate_path,
        "Phosh successor candidate",
    )
    physical_gate = _load_typed_canonical(
        PhysicalCandidateGateEvidence,
        physical_candidate_gate_path,
        "physical candidate gate",
    )
    return bind_phosh_successor_to_physical_gate(successor, physical_gate)


def load_phosh_physical_candidate_adapter(
    path: Path,
) -> PhoshPhysicalCandidateAdapterEvidence:
    evidence = _load_typed_canonical(
        PhoshPhysicalCandidateAdapterEvidence,
        Path(path),
        "Phosh physical candidate adapter",
    )
    validate_phosh_physical_candidate_adapter(evidence)
    return evidence


def write_phosh_physical_candidate_adapter(
    evidence: PhoshPhysicalCandidateAdapterEvidence,
    destination: Path,
) -> str:
    validate_phosh_physical_candidate_adapter(evidence)
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise PhoshPhysicalCandidateAdapterError(
            f"refusing to overwrite Phosh physical candidate adapter: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise PhoshPhysicalCandidateAdapterError(
            "refusing stale Phosh physical candidate adapter temporary path"
        )
    try:
        temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()
