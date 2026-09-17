"""Independent post-copy verification for a physical bring-up exact-file dossier.

This verifier is intentionally separate from dossier creation. It re-hashes the
canonical dossier and every role recorded inside it after archive/copy/transfer,
requires canonical JSON for evidence roles, and never performs phone I/O or
grants target/write/hardware/Beta credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Mapping

from .physical_bringup_dossier import (
    PhysicalBringupDossierEvidence,
    PhysicalBringupDossierError,
    validate_physical_bringup_dossier_evidence,
)

_POLICY = "physical-bringup-exact-file-dossier-reverify-v1"
_MAX_JSON_BYTES = 4 * 1024 * 1024
_MAX_TEXT_BYTES = 32 * 1024 * 1024
_MAX_ROOTFS_BYTES = 8 * 1024 * 1024 * 1024
_CHUNK = 1024 * 1024
_ROOTFS_ROLE = "rootfs_artifact"


@dataclass(frozen=True)
class PhysicalBringupDossierVerificationEvidence:
    schema_version: int
    verification_policy: str
    physical_bringup_dossier_sha256: str
    profile_id: str
    device_serial: str
    verified_role_count: int
    verified_byte_count: int
    canonical_json_role_count: int
    rootfs_artifact_file_verified: bool
    exact_file_set_verified: bool
    manual_review_required: bool
    target_selected: bool
    storage_path_bound: bool
    write_authorized: bool
    handoff_ready: bool
    storage_verified: bool
    recovery_verified: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _bounded_text(value: object, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise PhysicalBringupDossierError(f"{label} must be non-empty bounded text")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise PhysicalBringupDossierError(f"{label} contains control data")
    return value


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise PhysicalBringupDossierError(f"{label} must be a lowercase SHA-256")
    return value


def _positive(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PhysicalBringupDossierError(f"{label} must be a positive integer")
    return value


def _read_hash(path: Path, *, label: str, maximum: int) -> tuple[str, int, bytes | None]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalBringupDossierError(f"{label} must be a regular non-symlink file")
    before = source.stat()
    if before.st_size <= 0 or before.st_size > maximum:
        raise PhysicalBringupDossierError(f"{label} size is outside the verification safety limit")
    capture = bytearray() if before.st_size <= _MAX_JSON_BYTES else None
    digest = sha256()
    with source.open("rb") as handle:
        while True:
            chunk = handle.read(_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
            if capture is not None:
                capture.extend(chunk)
    after = source.stat()
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or getattr(before, "st_ino", None) != getattr(after, "st_ino", None)
    ):
        raise PhysicalBringupDossierError(f"{label} changed while being verified")
    return digest.hexdigest(), before.st_size, None if capture is None else bytes(capture)


def _canonical_json(raw: bytes, role: str) -> None:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalBringupDossierError(f"{role} is not valid canonical UTF-8 JSON") from exc
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    if raw != canonical.encode("utf-8"):
        raise PhysicalBringupDossierError(f"{role} is not encoded as canonical JSON")


def verify_physical_bringup_dossier_files(
    dossier: PhysicalBringupDossierEvidence,
    *,
    dossier_file: Path,
    role_files: Mapping[str, Path],
) -> PhysicalBringupDossierVerificationEvidence:
    """Reverify the exact dossier byte set after transfer/archive."""
    validate_physical_bringup_dossier_evidence(dossier)
    expected = {record.role: record for record in dossier.files}
    if set(role_files) != set(expected):
        missing = sorted(set(expected) - set(role_files))
        extra = sorted(set(role_files) - set(expected))
        raise PhysicalBringupDossierError(
            f"verification file roles do not match dossier; missing={missing} extra={extra}"
        )

    dossier_digest, dossier_size, dossier_raw = _read_hash(
        dossier_file, label="physical_bringup_dossier", maximum=_MAX_JSON_BYTES
    )
    if dossier_digest != dossier.evidence_sha256():
        raise PhysicalBringupDossierError("physical_bringup_dossier SHA-256 differs from supplied dossier")
    if dossier_raw != dossier.canonical_json().encode("utf-8"):
        raise PhysicalBringupDossierError("physical_bringup_dossier bytes are not canonical")

    total = dossier_size
    canonical_count = 1
    for role in sorted(expected):
        record = expected[role]
        maximum = _MAX_ROOTFS_BYTES if role == _ROOTFS_ROLE else (
            _MAX_JSON_BYTES if record.canonical_json_required else _MAX_TEXT_BYTES
        )
        actual, size, raw = _read_hash(role_files[role], label=role, maximum=maximum)
        if actual != record.sha256:
            raise PhysicalBringupDossierError(f"{role} SHA-256 differs from dossier record")
        if size != record.size:
            raise PhysicalBringupDossierError(f"{role} size differs from dossier record")
        if record.canonical_json_required:
            if raw is None:
                raise PhysicalBringupDossierError(f"{role} canonical JSON exceeds capture limit")
            _canonical_json(raw, role)
            canonical_count += 1
        total += size

    evidence = PhysicalBringupDossierVerificationEvidence(
        schema_version=1,
        verification_policy=_POLICY,
        physical_bringup_dossier_sha256=dossier.evidence_sha256(),
        profile_id=dossier.profile_id,
        device_serial=dossier.device_serial,
        verified_role_count=len(expected),
        verified_byte_count=total,
        canonical_json_role_count=canonical_count,
        rootfs_artifact_file_verified=dossier.rootfs_artifact_file_verified,
        exact_file_set_verified=True,
        manual_review_required=True,
        target_selected=False,
        storage_path_bound=False,
        write_authorized=False,
        handoff_ready=False,
        storage_verified=False,
        recovery_verified=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    validate_physical_bringup_dossier_verification_evidence(evidence)
    return evidence


def validate_physical_bringup_dossier_verification_evidence(
    evidence: PhysicalBringupDossierVerificationEvidence,
) -> None:
    if not isinstance(evidence, PhysicalBringupDossierVerificationEvidence) or evidence.schema_version != 1:
        raise PhysicalBringupDossierError("dossier verification must be schema-v1 typed evidence")
    if evidence.verification_policy != _POLICY:
        raise PhysicalBringupDossierError("dossier verification policy is unsupported")
    _sha(evidence.physical_bringup_dossier_sha256, "physical bring-up dossier")
    _bounded_text(evidence.profile_id, "verification profile id", 128)
    _bounded_text(evidence.device_serial, "verification device serial", 256)
    _positive(evidence.verified_role_count, "verified role count")
    _positive(evidence.verified_byte_count, "verified byte count")
    _positive(evidence.canonical_json_role_count, "canonical JSON role count")
    if evidence.canonical_json_role_count > evidence.verified_role_count + 1:
        raise PhysicalBringupDossierError("canonical JSON role count exceeds verified file set")
    if evidence.exact_file_set_verified is not True or evidence.manual_review_required is not True:
        raise PhysicalBringupDossierError("dossier verification is missing required audit flags")
    if not isinstance(evidence.rootfs_artifact_file_verified, bool):
        raise PhysicalBringupDossierError("rootfs verification flag must be boolean")
    if any(value is not False for value in (
        evidence.target_selected,
        evidence.storage_path_bound,
        evidence.write_authorized,
        evidence.handoff_ready,
        evidence.storage_verified,
        evidence.recovery_verified,
        evidence.hardware_verified,
        evidence.beta_gate_credit,
    )):
        raise PhysicalBringupDossierError(
            "dossier verification contains an unsupported target/write/hardware/Beta claim"
        )


def write_physical_bringup_dossier_verification_evidence(
    evidence: PhysicalBringupDossierVerificationEvidence,
    destination: Path,
) -> str:
    validate_physical_bringup_dossier_verification_evidence(evidence)
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise PhysicalBringupDossierError(f"refusing to overwrite dossier verification: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise PhysicalBringupDossierError("refusing stale dossier verification temporary path")
    payload = evidence.canonical_json()
    try:
        temporary.write_text(payload, encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()
