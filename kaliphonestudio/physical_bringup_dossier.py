"""Exact-file audit dossier for one physical bring-up session.

The dossier binds the canonical PhysicalBringupSessionEvidence file to every
raw/evidence file that the session names by SHA-256.  It is deliberately
non-operational: it performs no phone I/O, target selection, mounting,
decryption, flashing, or write authorization.

A complete dossier proves only that a reviewer has one internally consistent
set of bytes to inspect.  It never grants storage, recovery, hardware, or Beta
credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from .physical_bringup_session import (
    PhysicalBringupSessionEvidence,
    PhysicalBringupSessionError,
    validate_physical_bringup_session_evidence,
)

_DOSSIER_POLICY = "physical-bringup-exact-file-dossier-v1"
_MAX_JSON_BYTES = 4 * 1024 * 1024
_MAX_TEXT_BYTES = 32 * 1024 * 1024
_MAX_ROOTFS_BYTES = 8 * 1024 * 1024 * 1024
_CHUNK_SIZE = 1024 * 1024

_REQUIRED_EVIDENCE_ROLES = (
    "physical_candidate_gate",
    "physical_boot_observation",
    "rescue_diagnostics",
    "rescue_functional_probe",
    "physical_storage_discovery",
    "physical_storage_review",
)
_REQUIRED_RAW_ROLES = (
    "rescue_transcript",
    "storage_discovery_report",
    "recovery_plan",
    "storage_review_record",
    "storage_review_notes",
)
_OPTIONAL_EARLY_EVIDENCE_ROLE = "kali_early_userspace_evidence"
_OPTIONAL_EARLY_TRANSCRIPT_ROLE = "kali_early_userspace_transcript"
_SESSION_ROLE = "physical_bringup_session"
_ROOTFS_ROLE = "rootfs_artifact"


class PhysicalBringupDossierError(ValueError):
    pass


@dataclass(frozen=True)
class DossierFileEvidence:
    role: str
    sha256: str
    size: int
    canonical_json_required: bool


@dataclass(frozen=True)
class PhysicalBringupDossierEvidence:
    schema_version: int
    dossier_policy: str
    profile_id: str
    device_serial: str
    firmware_build: str
    firmware_fingerprint: str
    physical_bringup_session_sha256: str
    rootfs_authority_sha256: str
    rootfs_artifact_sha256: str
    rootfs_artifact_size: int
    rescue_probe_id: str
    storage_review_accepted_for_strategy_design: bool
    kali_early_userspace_signal_present: bool
    required_file_count: int
    supplied_file_count: int
    exact_file_set_verified: bool
    rootfs_artifact_file_verified: bool
    files: tuple[DossierFileEvidence, ...]
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


def _sha(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise PhysicalBringupDossierError(f"{label} must be a lowercase SHA-256")
    return value


def _text(value: object, label: str, max_len: int) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len:
        raise PhysicalBringupDossierError(f"{label} must be non-empty bounded text")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise PhysicalBringupDossierError(f"{label} contains control data")
    return value


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PhysicalBringupDossierError(f"{label} must be a positive integer")
    return value


def _read_and_hash(
    path: Path,
    *,
    label: str,
    max_bytes: int,
    require_nonempty: bool = True,
) -> tuple[str, int, bytes | None]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalBringupDossierError(f"{label} must be a regular non-symlink file")
    before = source.stat()
    if before.st_size < 0 or before.st_size > max_bytes:
        raise PhysicalBringupDossierError(f"{label} exceeds the safety size limit")
    if require_nonempty and before.st_size == 0:
        raise PhysicalBringupDossierError(f"{label} must not be empty")
    digest = sha256()
    captured = bytearray() if before.st_size <= _MAX_JSON_BYTES else None
    with source.open("rb") as handle:
        while True:
            chunk = handle.read(_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
            if captured is not None:
                captured.extend(chunk)
    after = source.stat()
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or getattr(before, "st_ino", None) != getattr(after, "st_ino", None)
    ):
        raise PhysicalBringupDossierError(f"{label} changed while being read")
    if captured is not None and len(captured) != before.st_size:
        raise PhysicalBringupDossierError(f"{label} changed while being read")
    return digest.hexdigest(), before.st_size, None if captured is None else bytes(captured)


def _verify_file(
    role: str,
    path: Path,
    expected_sha256: str,
    *,
    max_bytes: int,
    canonical_json: bytes | None = None,
    canonical_json_required: bool = False,
) -> DossierFileEvidence:
    expected = _sha(expected_sha256, f"{role} expected digest")
    actual, size, raw = _read_and_hash(path, label=role, max_bytes=max_bytes)
    if actual != expected:
        raise PhysicalBringupDossierError(
            f"{role} SHA-256 differs from the bound physical bring-up session"
        )
    if canonical_json is not None:
        if raw is None or raw != canonical_json:
            raise PhysicalBringupDossierError(
                f"{role} bytes are not the canonical JSON bound by the supplied evidence"
            )
    return DossierFileEvidence(
        role=role,
        sha256=actual,
        size=size,
        canonical_json_required=canonical_json is not None or canonical_json_required,
    )


def _expected_evidence_digests(session: PhysicalBringupSessionEvidence) -> dict[str, str]:
    values = {
        "physical_candidate_gate": session.physical_candidate_gate_sha256,
        "physical_boot_observation": session.physical_boot_observation_sha256,
        "rescue_diagnostics": session.rescue_diagnostics_sha256,
        "rescue_functional_probe": session.rescue_functional_probe_sha256,
        "physical_storage_discovery": session.physical_storage_discovery_sha256,
        "physical_storage_review": session.physical_storage_review_sha256,
    }
    if session.kali_early_userspace_signal_present:
        if session.kali_early_userspace_evidence_sha256 is None:
            raise PhysicalBringupDossierError(
                "session signals Kali early userspace without evidence identity"
            )
        values[_OPTIONAL_EARLY_EVIDENCE_ROLE] = session.kali_early_userspace_evidence_sha256
    return values


def _expected_raw_digests(session: PhysicalBringupSessionEvidence) -> dict[str, str]:
    values = {
        "rescue_transcript": session.rescue_transcript_sha256,
        "storage_discovery_report": session.discovery_report_sha256,
        "recovery_plan": session.recovery_plan_sha256,
        "storage_review_record": session.storage_review_record_sha256,
        "storage_review_notes": session.storage_review_notes_sha256,
    }
    if session.kali_early_userspace_signal_present:
        if session.kali_early_userspace_transcript_sha256 is None:
            raise PhysicalBringupDossierError(
                "session signals Kali early userspace without transcript identity"
            )
        values[_OPTIONAL_EARLY_TRANSCRIPT_ROLE] = session.kali_early_userspace_transcript_sha256
    return values


def build_physical_bringup_dossier(
    session: PhysicalBringupSessionEvidence,
    *,
    session_file: Path,
    evidence_files: Mapping[str, Path],
    raw_files: Mapping[str, Path],
    rootfs_artifact: Path | None = None,
) -> PhysicalBringupDossierEvidence:
    """Bind the exact on-disk byte set for one already-created bring-up session."""
    try:
        validate_physical_bringup_session_evidence(session)
    except (PhysicalBringupSessionError, ValueError) as exc:
        raise PhysicalBringupDossierError(str(exc)) from exc

    evidence_expected = _expected_evidence_digests(session)
    raw_expected = _expected_raw_digests(session)
    if set(evidence_files) != set(evidence_expected):
        missing = sorted(set(evidence_expected) - set(evidence_files))
        extra = sorted(set(evidence_files) - set(evidence_expected))
        raise PhysicalBringupDossierError(
            f"evidence file roles do not match session; missing={missing} extra={extra}"
        )
    if set(raw_files) != set(raw_expected):
        missing = sorted(set(raw_expected) - set(raw_files))
        extra = sorted(set(raw_files) - set(raw_expected))
        raise PhysicalBringupDossierError(
            f"raw file roles do not match session; missing={missing} extra={extra}"
        )

    records: list[DossierFileEvidence] = []
    records.append(
        _verify_file(
            _SESSION_ROLE,
            session_file,
            session.evidence_sha256(),
            max_bytes=_MAX_JSON_BYTES,
            canonical_json=session.canonical_json().encode("utf-8"),
        )
    )
    for role in sorted(evidence_expected):
        records.append(
            _verify_file(
                role,
                evidence_files[role],
                evidence_expected[role],
                max_bytes=_MAX_JSON_BYTES,
                canonical_json_required=True,
            )
        )
    for role in sorted(raw_expected):
        records.append(
            _verify_file(
                role,
                raw_files[role],
                raw_expected[role],
                max_bytes=_MAX_TEXT_BYTES,
            )
        )

    rootfs_verified = False
    if rootfs_artifact is not None:
        record = _verify_file(
            _ROOTFS_ROLE,
            rootfs_artifact,
            session.rootfs_artifact_sha256,
            max_bytes=_MAX_ROOTFS_BYTES,
        )
        if record.size != session.rootfs_artifact_size:
            raise PhysicalBringupDossierError(
                "rootfs artifact size differs from the bound physical bring-up session"
            )
        records.append(record)
        rootfs_verified = True

    required_count = 1 + len(evidence_expected) + len(raw_expected)
    records.sort(key=lambda item: item.role)
    dossier = PhysicalBringupDossierEvidence(
        schema_version=1,
        dossier_policy=_DOSSIER_POLICY,
        profile_id=session.profile_id,
        device_serial=session.device_serial,
        firmware_build=session.firmware_build,
        firmware_fingerprint=session.firmware_fingerprint,
        physical_bringup_session_sha256=session.evidence_sha256(),
        rootfs_authority_sha256=session.rootfs_authority_sha256,
        rootfs_artifact_sha256=session.rootfs_artifact_sha256,
        rootfs_artifact_size=session.rootfs_artifact_size,
        rescue_probe_id=session.rescue_probe_id,
        storage_review_accepted_for_strategy_design=session.storage_review_accepted_for_strategy_design,
        kali_early_userspace_signal_present=session.kali_early_userspace_signal_present,
        required_file_count=required_count,
        supplied_file_count=len(records),
        exact_file_set_verified=True,
        rootfs_artifact_file_verified=rootfs_verified,
        files=tuple(records),
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
    validate_physical_bringup_dossier_evidence(dossier)
    return dossier


def validate_physical_bringup_dossier_evidence(
    evidence: PhysicalBringupDossierEvidence,
) -> None:
    if not isinstance(evidence, PhysicalBringupDossierEvidence) or evidence.schema_version != 1:
        raise PhysicalBringupDossierError("physical bring-up dossier must be schema-v1 typed evidence")
    if evidence.dossier_policy != _DOSSIER_POLICY:
        raise PhysicalBringupDossierError("physical bring-up dossier policy is unsupported")
    _text(evidence.profile_id, "dossier profile id", 128)
    _text(evidence.device_serial, "dossier device serial", 256)
    _text(evidence.firmware_build, "dossier firmware build", 512)
    _text(evidence.firmware_fingerprint, "dossier firmware fingerprint", 1024)
    _sha(evidence.physical_bringup_session_sha256, "physical bring-up session")
    _sha(evidence.rootfs_authority_sha256, "rootfs authority")
    _sha(evidence.rootfs_artifact_sha256, "rootfs artifact")
    _sha(evidence.rescue_probe_id, "rescue probe id")
    _positive_int(evidence.rootfs_artifact_size, "rootfs artifact size")
    _positive_int(evidence.required_file_count, "required file count")
    _positive_int(evidence.supplied_file_count, "supplied file count")
    if evidence.exact_file_set_verified is not True or evidence.manual_review_required is not True:
        raise PhysicalBringupDossierError("physical bring-up dossier is missing required audit flags")
    if not isinstance(evidence.rootfs_artifact_file_verified, bool):
        raise PhysicalBringupDossierError("rootfs artifact file verification flag must be boolean")
    if not isinstance(evidence.storage_review_accepted_for_strategy_design, bool):
        raise PhysicalBringupDossierError("storage strategy-design acceptance flag must be boolean")
    if not isinstance(evidence.kali_early_userspace_signal_present, bool):
        raise PhysicalBringupDossierError("Kali early-userspace signal flag must be boolean")

    if evidence.supplied_file_count != len(evidence.files):
        raise PhysicalBringupDossierError("dossier file count does not match file records")
    expected_roles = {
        _SESSION_ROLE,
        *_REQUIRED_EVIDENCE_ROLES,
        *_REQUIRED_RAW_ROLES,
    }
    if evidence.kali_early_userspace_signal_present:
        expected_roles.update({_OPTIONAL_EARLY_EVIDENCE_ROLE, _OPTIONAL_EARLY_TRANSCRIPT_ROLE})
    if evidence.required_file_count != len(expected_roles):
        raise PhysicalBringupDossierError("dossier required file count is inconsistent")
    expected_min = evidence.required_file_count + (1 if evidence.rootfs_artifact_file_verified else 0)
    if evidence.supplied_file_count != expected_min:
        raise PhysicalBringupDossierError("dossier supplied file count is inconsistent")
    roles: set[str] = set()
    for item in evidence.files:
        if not isinstance(item, DossierFileEvidence):
            raise PhysicalBringupDossierError("dossier file record has invalid type")
        _text(item.role, "dossier file role", 128)
        if item.role in roles:
            raise PhysicalBringupDossierError("dossier contains duplicate file roles")
        roles.add(item.role)
        _sha(item.sha256, f"{item.role} digest")
        _positive_int(item.size, f"{item.role} size")
        if not isinstance(item.canonical_json_required, bool):
            raise PhysicalBringupDossierError("canonical-json flag must be boolean")
    allowed_roles = set(expected_roles)
    if evidence.rootfs_artifact_file_verified:
        allowed_roles.add(_ROOTFS_ROLE)
    if roles != allowed_roles:
        raise PhysicalBringupDossierError("dossier file roles do not match the bound session shape")
    if evidence.rootfs_artifact_file_verified != (_ROOTFS_ROLE in roles):
        raise PhysicalBringupDossierError("rootfs artifact verification flag does not match file records")

    forbidden = (
        evidence.target_selected,
        evidence.storage_path_bound,
        evidence.write_authorized,
        evidence.handoff_ready,
        evidence.storage_verified,
        evidence.recovery_verified,
        evidence.hardware_verified,
        evidence.beta_gate_credit,
    )
    if any(value is not False for value in forbidden):
        raise PhysicalBringupDossierError(
            "physical bring-up dossier contains an unsupported target/write/hardware/Beta claim"
        )


def load_physical_bringup_dossier_evidence(path: Path) -> PhysicalBringupDossierEvidence:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalBringupDossierError(
            "physical bring-up dossier evidence must be a regular non-symlink file"
        )
    before = source.stat()
    raw = source.read_bytes()
    after = source.stat()
    if (
        before.st_size <= 0
        or before.st_size > _MAX_JSON_BYTES
        or len(raw) != before.st_size
    ):
        raise PhysicalBringupDossierError("physical bring-up dossier evidence size is outside the safety limit")
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or getattr(before, "st_ino", None) != getattr(after, "st_ino", None)
    ):
        raise PhysicalBringupDossierError("physical bring-up dossier evidence changed while being read")
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalBringupDossierError("physical bring-up dossier evidence is not valid UTF-8 JSON") from exc
    expected = {item.name for item in fields(PhysicalBringupDossierEvidence)}
    if not isinstance(value, dict) or set(value) != expected:
        raise PhysicalBringupDossierError("physical bring-up dossier evidence fields do not match schema-v1")
    files = value.get("files")
    if not isinstance(files, list):
        raise PhysicalBringupDossierError("physical bring-up dossier files must be a list")
    try:
        value["files"] = tuple(DossierFileEvidence(**item) for item in files)
        evidence = PhysicalBringupDossierEvidence(**value)
    except (TypeError, ValueError) as exc:
        raise PhysicalBringupDossierError("physical bring-up dossier evidence types are invalid") from exc
    validate_physical_bringup_dossier_evidence(evidence)
    return evidence


def write_physical_bringup_dossier_evidence(
    evidence: PhysicalBringupDossierEvidence,
    destination: Path,
) -> str:
    validate_physical_bringup_dossier_evidence(evidence)
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise PhysicalBringupDossierError(f"refusing to overwrite physical bring-up dossier: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise PhysicalBringupDossierError("refusing stale physical bring-up dossier temporary path")
    payload = evidence.canonical_json()
    try:
        temporary.write_text(payload, encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()
