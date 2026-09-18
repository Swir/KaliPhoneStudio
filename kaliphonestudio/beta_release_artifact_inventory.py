"""Deterministic, non-authorizing Beta release artifact inventory.

This offline layer prepares exact SHA-256/size metadata for a reviewed physical
candidate.  It deliberately stops before publication: even a complete inventory
requires the later final manual release-gate review and cannot grant hardware or
Beta credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .physical_candidate_gate import PhysicalCandidateGateEvidence
from .physical_release_gate_audit import (
    PhysicalReleaseGateAuditError,
    load_physical_release_gate_audit_evidence,
)
from .rootfs_handoff_strategy_review import (
    RootfsHandoffStrategyReviewError,
    load_rootfs_handoff_strategy_review_evidence,
)

_POLICY = "beta-release-artifact-inventory-v1"
_MAX_EVIDENCE_BYTES = 4 * 1024 * 1024
_MAX_ARTIFACT_BYTES = 16 * 1024 * 1024 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_ROLE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_ALLOWED_ROLES = frozenset(
    {
        "candidate_boot",
        "kali_rootfs",
        "kernel_image",
        "dtb",
        "dtbo_image",
        "windows_host_bundle",
        "operator_instructions",
        "compatibility_matrix",
        "known_issues",
    }
)
_REQUIRED_ROLES = frozenset(
    {
        "candidate_boot",
        "kali_rootfs",
        "operator_instructions",
        "compatibility_matrix",
        "known_issues",
    }
)


class BetaReleaseArtifactInventoryError(ValueError):
    pass


@dataclass(frozen=True)
class ReleaseArtifactEntry:
    role: str
    filename: str
    size: int
    sha256: str


@dataclass(frozen=True)
class BetaReleaseArtifactInventoryEvidence:
    schema_version: int
    inventory_policy: str
    profile_id: str
    device_serial: str
    firmware_build: str
    firmware_fingerprint: str
    source_commit: str
    physical_candidate_gate_sha256: str
    physical_release_gate_audit_sha256: str
    rootfs_handoff_strategy_review_sha256: str
    artifacts: tuple[ReleaseArtifactEntry, ...]
    exact_files_verified: bool
    required_artifacts_present: bool
    beta_required_tests_all_reviewed_pass: bool
    kali_early_userspace_signal_present: bool
    ready_for_final_manual_release_review: bool
    manual_release_gate_review_required: bool
    release_publication_allowed: bool
    beta_release_authorized: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise BetaReleaseArtifactInventoryError(f"{label} must be a lowercase SHA-256")
    return value


def _text(value: object, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise BetaReleaseArtifactInventoryError(f"{label} must be non-empty bounded text")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise BetaReleaseArtifactInventoryError(f"{label} contains control data")
    return value


def _positive(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise BetaReleaseArtifactInventoryError(f"{label} must be a positive integer")
    return value


def _read_exact(path: Path, label: str, maximum: int) -> tuple[bytes, str, int]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise BetaReleaseArtifactInventoryError(f"{label} must be a regular non-symlink file")
    try:
        before = source.stat()
        if before.st_size <= 0 or before.st_size > maximum:
            raise BetaReleaseArtifactInventoryError(f"{label} size is outside the safety limit")
        digest = sha256()
        chunks: list[bytes] = []
        total = 0
        with source.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > maximum:
                    raise BetaReleaseArtifactInventoryError(f"{label} size is outside the safety limit")
                digest.update(chunk)
                if maximum <= _MAX_EVIDENCE_BYTES:
                    chunks.append(chunk)
        after = source.stat()
    except OSError as exc:
        raise BetaReleaseArtifactInventoryError(f"cannot read {label}: {exc}") from exc
    if total != before.st_size:
        raise BetaReleaseArtifactInventoryError(f"{label} size changed while being read")
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or getattr(before, "st_ino", None) != getattr(after, "st_ino", None)
    ):
        raise BetaReleaseArtifactInventoryError(f"{label} changed while being read")
    return b"".join(chunks), digest.hexdigest(), total


def _load_candidate_gate(path: Path) -> tuple[PhysicalCandidateGateEvidence, str, int]:
    raw, file_sha, file_size = _read_exact(path, "physical candidate gate", _MAX_EVIDENCE_BYTES)
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BetaReleaseArtifactInventoryError("physical candidate gate is not valid UTF-8 JSON") from exc
    expected = {item.name for item in fields(PhysicalCandidateGateEvidence)}
    if not isinstance(value, dict) or set(value) != expected:
        raise BetaReleaseArtifactInventoryError("physical candidate gate fields do not match schema-v1")
    try:
        gate = PhysicalCandidateGateEvidence(**value)
    except TypeError as exc:
        raise BetaReleaseArtifactInventoryError("physical candidate gate field types are invalid") from exc
    if gate.schema_version != 1:
        raise BetaReleaseArtifactInventoryError("physical candidate gate must be schema v1")
    if raw != gate.canonical_json().encode("utf-8"):
        raise BetaReleaseArtifactInventoryError("physical candidate gate is not canonical JSON")
    for value, label in (
        (gate.physical_baseline_bundle_sha256, "physical baseline bundle"),
        (gate.fastboot_capture_bundle_sha256, "Fastboot capture bundle"),
        (gate.fastboot_baseline_evidence_sha256, "Fastboot baseline evidence"),
        (gate.fastboot_transcript_sha256, "Fastboot transcript"),
        (gate.stock_provenance_sha256, "stock provenance"),
        (gate.stock_ota_sha256, "stock OTA"),
        (gate.stock_boot_sha256, "stock boot"),
        (gate.first_boot_manifest_sha256, "first-boot manifest"),
        (gate.first_boot_authority_bundle_sha256, "first-boot authority bundle"),
        (gate.boot_authorization_sha256, "boot authorization"),
        (gate.boot_plan_sha256, "boot plan"),
        (gate.boot_image_sha256, "boot image"),
        (gate.kernel_image_sha256, "kernel image"),
        (gate.rootfs_artifact_sha256, "rootfs artifact"),
    ):
        _sha(value, label)
    if gate.dtb_sha256 is not None:
        _sha(gate.dtb_sha256, "DTB")
    if gate.dtbo_image_sha256 is not None:
        _sha(gate.dtbo_image_sha256, "DTBO image")
    _positive(gate.boot_image_size, "boot image size")
    _text(gate.profile_id, "profile id", 128)
    _text(gate.device_serial, "device serial", 256)
    _text(gate.firmware_build, "firmware build", 512)
    _text(gate.firmware_fingerprint, "firmware fingerprint", 1024)
    if gate.reviewed_authorities_bound is not True or gate.exact_physical_baseline_bound is not True:
        raise BetaReleaseArtifactInventoryError("physical candidate gate is not exact/reviewed")
    if gate.ready_for_temporary_boot_offer is not True:
        raise BetaReleaseArtifactInventoryError("physical candidate gate is not ready for temporary boot")
    if gate.phone_storage_written is not False or gate.hardware_verified is not False or gate.beta_gate_credit is not False:
        raise BetaReleaseArtifactInventoryError("physical candidate gate contains forbidden write/hardware/Beta promotion")
    return gate, file_sha, file_size


def _artifact_entry(role: str, path: Path) -> ReleaseArtifactEntry:
    if not isinstance(role, str) or not _ROLE_RE.fullmatch(role) or role not in _ALLOWED_ROLES:
        raise BetaReleaseArtifactInventoryError(f"unsupported release artifact role: {role!r}")
    source = Path(path)
    filename = source.name
    if filename in {"", ".", ".."} or filename != Path(filename).name:
        raise BetaReleaseArtifactInventoryError(f"unsafe release artifact filename for role {role}")
    _, digest, size = _read_exact(source, f"release artifact {role}", _MAX_ARTIFACT_BYTES)
    return ReleaseArtifactEntry(role=role, filename=filename, size=size, sha256=digest)


def validate_beta_release_artifact_inventory_evidence(evidence: BetaReleaseArtifactInventoryEvidence) -> None:
    if not isinstance(evidence, BetaReleaseArtifactInventoryEvidence) or evidence.schema_version != 1:
        raise BetaReleaseArtifactInventoryError("Beta release artifact inventory must be schema-v1 typed evidence")
    if evidence.inventory_policy != _POLICY:
        raise BetaReleaseArtifactInventoryError("Beta release artifact inventory policy is unsupported")
    _text(evidence.profile_id, "profile id", 128)
    _text(evidence.device_serial, "device serial", 256)
    _text(evidence.firmware_build, "firmware build", 512)
    _text(evidence.firmware_fingerprint, "firmware fingerprint", 1024)
    if not isinstance(evidence.source_commit, str) or not _COMMIT_RE.fullmatch(evidence.source_commit):
        raise BetaReleaseArtifactInventoryError("source commit must be an exact lowercase 40-hex Git commit")
    for value, label in (
        (evidence.physical_candidate_gate_sha256, "physical candidate gate"),
        (evidence.physical_release_gate_audit_sha256, "physical release-gate audit"),
        (evidence.rootfs_handoff_strategy_review_sha256, "rootfs handoff strategy review"),
    ):
        _sha(value, label)
    if not isinstance(evidence.artifacts, tuple) or not evidence.artifacts:
        raise BetaReleaseArtifactInventoryError("release artifact inventory must contain artifacts")
    roles: set[str] = set()
    filenames: set[str] = set()
    for item in evidence.artifacts:
        if not isinstance(item, ReleaseArtifactEntry):
            raise BetaReleaseArtifactInventoryError("release artifact entry must be typed evidence")
        if item.role not in _ALLOWED_ROLES or not _ROLE_RE.fullmatch(item.role):
            raise BetaReleaseArtifactInventoryError("release artifact role is unsupported")
        if item.role in roles:
            raise BetaReleaseArtifactInventoryError("release artifact roles must be unique")
        if item.filename in filenames or item.filename in {"", ".", ".."} or Path(item.filename).name != item.filename:
            raise BetaReleaseArtifactInventoryError("release artifact filenames must be unique safe basenames")
        _positive(item.size, f"release artifact {item.role} size")
        _sha(item.sha256, f"release artifact {item.role}")
        roles.add(item.role)
        filenames.add(item.filename)
    required_present = _REQUIRED_ROLES.issubset(roles)
    if evidence.required_artifacts_present is not required_present:
        raise BetaReleaseArtifactInventoryError("required artifact presence flag drifted")
    expected_ready = (
        evidence.exact_files_verified
        and required_present
        and evidence.beta_required_tests_all_reviewed_pass
        and evidence.kali_early_userspace_signal_present
    )
    if evidence.ready_for_final_manual_release_review is not expected_ready:
        raise BetaReleaseArtifactInventoryError("manual release-review readiness flag drifted")
    if evidence.manual_release_gate_review_required is not True:
        raise BetaReleaseArtifactInventoryError("artifact inventory must require final manual release-gate review")
    for name in ("release_publication_allowed", "beta_release_authorized", "hardware_verified", "beta_gate_credit"):
        if getattr(evidence, name) is not False:
            raise BetaReleaseArtifactInventoryError(f"artifact inventory cannot promote {name}")


def build_beta_release_artifact_inventory(
    candidate_gate_path: Path,
    release_gate_audit_path: Path,
    strategy_review_path: Path,
    source_commit: str,
    artifacts: Mapping[str, Path],
) -> BetaReleaseArtifactInventoryEvidence:
    if not isinstance(source_commit, str) or not _COMMIT_RE.fullmatch(source_commit):
        raise BetaReleaseArtifactInventoryError("source commit must be an exact lowercase 40-hex Git commit")
    candidate, _, _ = _load_candidate_gate(Path(candidate_gate_path))
    try:
        audit = load_physical_release_gate_audit_evidence(Path(release_gate_audit_path))
        strategy = load_rootfs_handoff_strategy_review_evidence(Path(strategy_review_path))
    except (PhysicalReleaseGateAuditError, RootfsHandoffStrategyReviewError) as exc:
        raise BetaReleaseArtifactInventoryError(str(exc)) from exc

    identities = {
        (candidate.profile_id, candidate.device_serial, candidate.firmware_build, candidate.firmware_fingerprint),
        (audit.profile_id, audit.device_serial, audit.firmware_build, audit.firmware_fingerprint),
        (strategy.profile_id, strategy.device_serial, strategy.firmware_build, strategy.firmware_fingerprint),
    }
    if len(identities) != 1:
        raise BetaReleaseArtifactInventoryError("release inventory physical identity drifted across exact evidence")
    if strategy.physical_release_gate_audit_sha256 != audit.evidence_sha256():
        raise BetaReleaseArtifactInventoryError("rootfs strategy review is detached from exact release-gate audit")
    if strategy.strategy_design_accepted is not True or strategy.review_checks_complete is not True:
        raise BetaReleaseArtifactInventoryError("release inventory requires an accepted exact rootfs strategy design review")
    if strategy.rootfs_artifact_sha256 != candidate.rootfs_artifact_sha256:
        raise BetaReleaseArtifactInventoryError("strategy rootfs artifact differs from physical candidate")
    if audit.beta_required_tests_all_reviewed_pass is not True:
        raise BetaReleaseArtifactInventoryError("release inventory requires all Beta-required functional tests reviewed pass")
    if audit.kali_early_userspace_signal_present is not True:
        raise BetaReleaseArtifactInventoryError("release inventory requires Kali early-userspace signal in the exact dossier chain")

    if not isinstance(artifacts, Mapping) or not artifacts:
        raise BetaReleaseArtifactInventoryError("release artifacts must be a non-empty role-to-path mapping")
    entries = tuple(sorted((_artifact_entry(role, Path(path)) for role, path in artifacts.items()), key=lambda item: item.role))
    by_role = {item.role: item for item in entries}
    if set(by_role) != {item.role for item in entries}:
        raise BetaReleaseArtifactInventoryError("release artifact roles must be unique")
    if not _REQUIRED_ROLES.issubset(by_role):
        missing = sorted(_REQUIRED_ROLES.difference(by_role))
        raise BetaReleaseArtifactInventoryError(f"release inventory is missing required roles: {', '.join(missing)}")

    boot = by_role["candidate_boot"]
    if boot.sha256 != candidate.boot_image_sha256 or boot.size != candidate.boot_image_size:
        raise BetaReleaseArtifactInventoryError("candidate boot artifact differs from exact physical candidate gate")
    rootfs = by_role["kali_rootfs"]
    if rootfs.sha256 != candidate.rootfs_artifact_sha256 or rootfs.sha256 != strategy.rootfs_artifact_sha256:
        raise BetaReleaseArtifactInventoryError("Kali rootfs artifact digest differs from reviewed candidate/strategy")
    if rootfs.size != strategy.rootfs_artifact_size:
        raise BetaReleaseArtifactInventoryError("Kali rootfs artifact size differs from reviewed strategy evidence")
    if "kernel_image" in by_role and by_role["kernel_image"].sha256 != candidate.kernel_image_sha256:
        raise BetaReleaseArtifactInventoryError("kernel artifact differs from exact physical candidate gate")
    if candidate.dtb_sha256 is not None:
        if "dtb" not in by_role or by_role["dtb"].sha256 != candidate.dtb_sha256:
            raise BetaReleaseArtifactInventoryError("DTB artifact is required and must match exact physical candidate gate")
    if candidate.dtbo_image_sha256 is not None:
        if "dtbo_image" not in by_role or by_role["dtbo_image"].sha256 != candidate.dtbo_image_sha256:
            raise BetaReleaseArtifactInventoryError("DTBO artifact is required and must match exact physical candidate gate")

    evidence = BetaReleaseArtifactInventoryEvidence(
        schema_version=1,
        inventory_policy=_POLICY,
        profile_id=candidate.profile_id,
        device_serial=candidate.device_serial,
        firmware_build=candidate.firmware_build,
        firmware_fingerprint=candidate.firmware_fingerprint,
        source_commit=source_commit,
        physical_candidate_gate_sha256=candidate.evidence_sha256(),
        physical_release_gate_audit_sha256=audit.evidence_sha256(),
        rootfs_handoff_strategy_review_sha256=strategy.evidence_sha256(),
        artifacts=entries,
        exact_files_verified=True,
        required_artifacts_present=True,
        beta_required_tests_all_reviewed_pass=True,
        kali_early_userspace_signal_present=True,
        ready_for_final_manual_release_review=True,
        manual_release_gate_review_required=True,
        release_publication_allowed=False,
        beta_release_authorized=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    validate_beta_release_artifact_inventory_evidence(evidence)
    return evidence


def write_beta_release_artifact_inventory(
    evidence: BetaReleaseArtifactInventoryEvidence,
    destination: Path,
) -> str:
    validate_beta_release_artifact_inventory_evidence(evidence)
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise BetaReleaseArtifactInventoryError("refusing to overwrite Beta release artifact inventory")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise BetaReleaseArtifactInventoryError("refusing stale Beta release artifact inventory temporary path")
    try:
        temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
        temporary.replace(path)
    except OSError as exc:
        raise BetaReleaseArtifactInventoryError(f"cannot write Beta release artifact inventory: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()


def load_beta_release_artifact_inventory(path: Path) -> BetaReleaseArtifactInventoryEvidence:
    raw, _, _ = _read_exact(Path(path), "Beta release artifact inventory", _MAX_EVIDENCE_BYTES)
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BetaReleaseArtifactInventoryError("Beta release artifact inventory is not valid UTF-8 JSON") from exc
    expected = {item.name for item in fields(BetaReleaseArtifactInventoryEvidence)}
    if not isinstance(value, dict) or set(value) != expected or not isinstance(value.get("artifacts"), list):
        raise BetaReleaseArtifactInventoryError("Beta release artifact inventory fields do not match schema-v1")
    try:
        entries = tuple(ReleaseArtifactEntry(**item) for item in value["artifacts"])
        evidence = BetaReleaseArtifactInventoryEvidence(**{**value, "artifacts": entries})
    except (TypeError, KeyError) as exc:
        raise BetaReleaseArtifactInventoryError("Beta release artifact inventory field types are invalid") from exc
    validate_beta_release_artifact_inventory_evidence(evidence)
    if raw != evidence.canonical_json().encode("utf-8"):
        raise BetaReleaseArtifactInventoryError("Beta release artifact inventory is not canonical JSON")
    return evidence
