"""Offline binding of physical Kali early-userspace markers to one exact candidate.

A successful Fastboot command is not enough to prove that the kernel reached the
intended Kali rootfs. This module consumes a previously successful temporary-boot
execution record, the exact physical-candidate host gate, deterministic Kali
rootfs proof-overlay evidence, and an operator-captured console/log transcript.

Matching markers remain unreviewed physical observation evidence. They never
become automatic hardware support or Beta-gate credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .kali_early_userspace import (
    KaliEarlyUserspaceProbeBundleEvidence,
    validate_kali_early_userspace_probe_bundle_evidence,
)
from .physical_boot_observation import validate_temporary_boot_execution_evidence
from .physical_candidate_gate import PhysicalCandidateGateEvidence
from .profiles import DeviceProfile
from .temporary_boot_execution import TemporaryBootExecutionEvidence

MAX_TRANSCRIPT_BYTES = 8 * 1024 * 1024
MAX_MARKER_DUPLICATES = 8
_POLICY = "exact-kali-rootfs-systemd-early-binding-v1"
_STAGE = b"KPS_KALI_STAGE=rootfs-systemd-early-v1"
_PREFIXES = {
    "probe": b"KPS_KALI_PROBE_ID=",
    "manifest": b"KPS_KALI_MANIFEST_SHA256=",
    "authority": b"KPS_KALI_ROOTFS_AUTHORITY_SHA256=",
    "artifact": b"KPS_KALI_ROOTFS_ARTIFACT_SHA256=",
}


class PhysicalKaliEarlyUserspaceError(ValueError):
    pass


@dataclass(frozen=True)
class PhysicalKaliEarlyUserspaceEvidence:
    schema_version: int
    profile_id: str
    device_serial: str
    temporary_boot_execution_sha256: str
    physical_candidate_gate_sha256: str
    early_userspace_bundle_evidence_sha256: str
    first_boot_manifest_sha256: str
    first_boot_authority_bundle_sha256: str
    rootfs_authority_sha256: str
    rootfs_artifact_sha256: str
    probe_id: str
    transcript_sha256: str
    transcript_size: int
    stage_marker_count: int
    probe_marker_count: int
    manifest_marker_count: int
    rootfs_authority_marker_count: int
    rootfs_artifact_marker_count: int
    observation_policy: str
    temporary_boot_command_succeeded: bool
    exact_candidate_identity_bound: bool
    exact_rootfs_identity_bound: bool
    kali_systemd_early_signal_observed: bool
    kali_rootfs_signal_observed: bool
    kali_early_userspace_verified: bool
    manual_review_required: bool
    phone_storage_written: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise PhysicalKaliEarlyUserspaceError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PhysicalKaliEarlyUserspaceError(f"{label} must be a non-empty string")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise PhysicalKaliEarlyUserspaceError(f"{label} contains control data")
    return value


def _validate_gate(gate: PhysicalCandidateGateEvidence) -> None:
    if not isinstance(gate, PhysicalCandidateGateEvidence) or gate.schema_version != 1:
        raise PhysicalKaliEarlyUserspaceError("physical candidate gate must be schema-v1 typed evidence")
    _text(gate.profile_id, "physical candidate gate profile_id")
    _text(gate.device_serial, "physical candidate gate serial")
    for value, label in (
        (gate.first_boot_manifest_sha256, "first-boot manifest"),
        (gate.first_boot_authority_bundle_sha256, "first-boot authority bundle"),
        (gate.boot_authorization_sha256, "boot authorization"),
        (gate.boot_image_sha256, "boot image"),
        (gate.rootfs_artifact_sha256, "rootfs artifact"),
        (gate.evidence_sha256(), "physical candidate gate evidence"),
    ):
        _sha(value, label)
    if (
        gate.reviewed_authorities_bound is not True
        or gate.exact_physical_baseline_bound is not True
        or gate.ready_for_temporary_boot_offer is not True
        or gate.temporary_boot_executed is not False
        or gate.phone_storage_written is not False
        or gate.hardware_verified is not False
        or gate.beta_gate_credit is not False
    ):
        raise PhysicalKaliEarlyUserspaceError("physical candidate gate has invalid readiness/safety state")


def _read_transcript(path: Path) -> bytes:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalKaliEarlyUserspaceError("Kali early-userspace transcript must be a regular non-symlink file")
    try:
        before = source.stat()
    except OSError as exc:
        raise PhysicalKaliEarlyUserspaceError(f"cannot stat Kali early-userspace transcript: {exc}") from exc
    if before.st_size <= 0 or before.st_size > MAX_TRANSCRIPT_BYTES:
        raise PhysicalKaliEarlyUserspaceError("Kali early-userspace transcript size is outside the safety limit")
    try:
        payload = source.read_bytes()
        after = source.stat()
    except OSError as exc:
        raise PhysicalKaliEarlyUserspaceError(f"cannot read Kali early-userspace transcript: {exc}") from exc
    if len(payload) != before.st_size or (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise PhysicalKaliEarlyUserspaceError("Kali early-userspace transcript changed while being verified")
    return payload


def _count_exact(lines: list[bytes], expected: bytes, prefix: bytes, label: str) -> int:
    count = sum(line == expected for line in lines)
    conflicting = {line for line in lines if line.startswith(prefix) and line != expected}
    if conflicting:
        raise PhysicalKaliEarlyUserspaceError(f"Kali early-userspace transcript contains conflicting {label} marker")
    if count < 1:
        raise PhysicalKaliEarlyUserspaceError(f"Kali early-userspace transcript is missing exact {label} marker")
    if count > MAX_MARKER_DUPLICATES:
        raise PhysicalKaliEarlyUserspaceError(f"Kali early-userspace transcript contains implausible {label} marker duplicates")
    return count


def _marker_counts(payload: bytes, bundle: KaliEarlyUserspaceProbeBundleEvidence) -> tuple[int, int, int, int, int]:
    lines = payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"\n")
    expected = (
        (_STAGE, b"KPS_KALI_STAGE=", "stage"),
        (_PREFIXES["probe"] + bundle.probe_id.encode("ascii"), _PREFIXES["probe"], "probe id"),
        (_PREFIXES["manifest"] + bundle.first_boot_manifest_sha256.encode("ascii"), _PREFIXES["manifest"], "manifest"),
        (_PREFIXES["authority"] + bundle.rootfs_authority_sha256.encode("ascii"), _PREFIXES["authority"], "rootfs authority"),
        (_PREFIXES["artifact"] + bundle.rootfs_artifact_sha256.encode("ascii"), _PREFIXES["artifact"], "rootfs artifact"),
    )
    values = tuple(_count_exact(lines, marker, prefix, label) for marker, prefix, label in expected)
    return values[0], values[1], values[2], values[3], values[4]


def record_physical_kali_early_userspace_observation(
    profile: DeviceProfile,
    execution: TemporaryBootExecutionEvidence,
    gate: PhysicalCandidateGateEvidence,
    bundle: KaliEarlyUserspaceProbeBundleEvidence,
    transcript: Path,
) -> PhysicalKaliEarlyUserspaceEvidence:
    try:
        validate_temporary_boot_execution_evidence(execution)
    except ValueError as exc:
        raise PhysicalKaliEarlyUserspaceError(str(exc)) from exc
    _validate_gate(gate)
    try:
        validate_kali_early_userspace_probe_bundle_evidence(bundle)
    except ValueError as exc:
        raise PhysicalKaliEarlyUserspaceError(str(exc)) from exc

    profile_id = _text(getattr(profile, "profile_id", None), "profile_id")
    if execution.profile_id != profile_id or gate.profile_id != profile_id or bundle.profile_id != profile_id:
        raise PhysicalKaliEarlyUserspaceError("profile, execution, candidate gate and Kali proof bundle do not match")
    if execution.device_serial != gate.device_serial:
        raise PhysicalKaliEarlyUserspaceError("temporary-boot serial differs from physical candidate gate")
    if execution.authorization_sha256 != gate.boot_authorization_sha256:
        raise PhysicalKaliEarlyUserspaceError("temporary-boot authorization differs from physical candidate gate")
    if bundle.first_boot_manifest_sha256 != gate.first_boot_manifest_sha256:
        raise PhysicalKaliEarlyUserspaceError("Kali proof bundle is detached from physical candidate manifest")
    if bundle.first_boot_authority_bundle_sha256 != gate.first_boot_authority_bundle_sha256:
        raise PhysicalKaliEarlyUserspaceError("Kali proof bundle is detached from physical candidate authorities")
    if bundle.rootfs_artifact_sha256 != gate.rootfs_artifact_sha256:
        raise PhysicalKaliEarlyUserspaceError("Kali proof bundle rootfs differs from physical candidate rootfs")
    if execution.phone_storage_written is not False or execution.persistent_write is not False:
        raise PhysicalKaliEarlyUserspaceError("temporary-boot execution unexpectedly records persistent storage writes")

    raw = _read_transcript(transcript)
    stage, probe, manifest, authority, artifact = _marker_counts(raw, bundle)
    evidence = PhysicalKaliEarlyUserspaceEvidence(
        schema_version=1,
        profile_id=profile_id,
        device_serial=execution.device_serial,
        temporary_boot_execution_sha256=_sha(execution.evidence_sha256(), "temporary-boot execution evidence"),
        physical_candidate_gate_sha256=_sha(gate.evidence_sha256(), "physical candidate gate evidence"),
        early_userspace_bundle_evidence_sha256=_sha(bundle.evidence_sha256(), "Kali early-userspace bundle evidence"),
        first_boot_manifest_sha256=bundle.first_boot_manifest_sha256,
        first_boot_authority_bundle_sha256=bundle.first_boot_authority_bundle_sha256,
        rootfs_authority_sha256=bundle.rootfs_authority_sha256,
        rootfs_artifact_sha256=bundle.rootfs_artifact_sha256,
        probe_id=bundle.probe_id,
        transcript_sha256=sha256(raw).hexdigest(),
        transcript_size=len(raw),
        stage_marker_count=stage,
        probe_marker_count=probe,
        manifest_marker_count=manifest,
        rootfs_authority_marker_count=authority,
        rootfs_artifact_marker_count=artifact,
        observation_policy=_POLICY,
        temporary_boot_command_succeeded=True,
        exact_candidate_identity_bound=True,
        exact_rootfs_identity_bound=True,
        kali_systemd_early_signal_observed=True,
        kali_rootfs_signal_observed=True,
        kali_early_userspace_verified=False,
        manual_review_required=True,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    validate_physical_kali_early_userspace_evidence(evidence)
    return evidence


def validate_physical_kali_early_userspace_evidence(evidence: PhysicalKaliEarlyUserspaceEvidence) -> None:
    if not isinstance(evidence, PhysicalKaliEarlyUserspaceEvidence) or evidence.schema_version != 1:
        raise PhysicalKaliEarlyUserspaceError("physical Kali early-userspace evidence must be schema-v1 typed evidence")
    _text(evidence.profile_id, "profile_id")
    _text(evidence.device_serial, "device serial")
    for value, label in (
        (evidence.temporary_boot_execution_sha256, "temporary-boot execution"),
        (evidence.physical_candidate_gate_sha256, "physical candidate gate"),
        (evidence.early_userspace_bundle_evidence_sha256, "Kali early-userspace bundle"),
        (evidence.first_boot_manifest_sha256, "first-boot manifest"),
        (evidence.first_boot_authority_bundle_sha256, "first-boot authority bundle"),
        (evidence.rootfs_authority_sha256, "rootfs authority"),
        (evidence.rootfs_artifact_sha256, "rootfs artifact"),
        (evidence.probe_id, "probe id"),
        (evidence.transcript_sha256, "transcript"),
    ):
        _sha(value, label)
    if evidence.transcript_size <= 0 or evidence.transcript_size > MAX_TRANSCRIPT_BYTES:
        raise PhysicalKaliEarlyUserspaceError("physical Kali early-userspace transcript size is invalid")
    for count, label in (
        (evidence.stage_marker_count, "stage"),
        (evidence.probe_marker_count, "probe"),
        (evidence.manifest_marker_count, "manifest"),
        (evidence.rootfs_authority_marker_count, "rootfs authority"),
        (evidence.rootfs_artifact_marker_count, "rootfs artifact"),
    ):
        if not isinstance(count, int) or isinstance(count, bool) or not (1 <= count <= MAX_MARKER_DUPLICATES):
            raise PhysicalKaliEarlyUserspaceError(f"physical Kali early-userspace {label} marker count is invalid")
    if evidence.observation_policy != _POLICY:
        raise PhysicalKaliEarlyUserspaceError("physical Kali early-userspace observation policy is unsupported")
    if (
        evidence.temporary_boot_command_succeeded is not True
        or evidence.exact_candidate_identity_bound is not True
        or evidence.exact_rootfs_identity_bound is not True
        or evidence.kali_systemd_early_signal_observed is not True
        or evidence.kali_rootfs_signal_observed is not True
        or evidence.kali_early_userspace_verified is not False
        or evidence.manual_review_required is not True
        or evidence.phone_storage_written is not False
        or evidence.hardware_verified is not False
        or evidence.beta_gate_credit is not False
    ):
        raise PhysicalKaliEarlyUserspaceError("physical Kali early-userspace evidence contains an invalid verification claim")


def write_physical_kali_early_userspace_evidence(evidence: PhysicalKaliEarlyUserspaceEvidence, destination: Path) -> str:
    validate_physical_kali_early_userspace_evidence(evidence)
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise PhysicalKaliEarlyUserspaceError(f"refusing to overwrite physical Kali early-userspace evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise PhysicalKaliEarlyUserspaceError("refusing stale physical Kali early-userspace evidence temporary path")
    payload = evidence.canonical_json()
    try:
        temporary.write_text(payload, encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()


def load_physical_candidate_gate_evidence(path: Path) -> PhysicalCandidateGateEvidence:
    raw = _load_json(Path(path), "physical candidate gate evidence")
    expected = {item.name for item in fields(PhysicalCandidateGateEvidence)}
    if set(raw) != expected:
        raise PhysicalKaliEarlyUserspaceError("physical candidate gate evidence fields do not match schema-v1")
    try:
        gate = PhysicalCandidateGateEvidence(**raw)
    except TypeError as exc:
        raise PhysicalKaliEarlyUserspaceError("physical candidate gate evidence types are invalid") from exc
    _validate_gate(gate)
    return gate


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise PhysicalKaliEarlyUserspaceError(f"{label} must be a regular non-symlink file")
    raw = path.read_bytes()
    if not raw or len(raw) > 2 * 1024 * 1024:
        raise PhysicalKaliEarlyUserspaceError(f"{label} size is outside the safety limit")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalKaliEarlyUserspaceError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise PhysicalKaliEarlyUserspaceError(f"{label} must be a JSON object")
    return value
