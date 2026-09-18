"""Deterministic, non-authorizing Beta release review manifest.

This offline layer consumes one exact Beta release artifact inventory, re-hashes
all release files from a single directory, and emits canonical manifest metadata
plus deterministic SHA256SUMS text for a later independent release-gate review.
It performs no device, network or publication action and cannot grant hardware
or Beta credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from .beta_release_artifact_inventory import (
    BetaReleaseArtifactInventoryError,
    BetaReleaseArtifactInventoryEvidence,
    ReleaseArtifactEntry,
    load_beta_release_artifact_inventory,
)

_POLICY = "beta-release-review-manifest-v1"
_PROJECT = "KaliPhoneStudio"
_MAX_EVIDENCE_BYTES = 4 * 1024 * 1024
_MAX_ARTIFACT_BYTES = 16 * 1024 * 1024 * 1024
_SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
_SAFE_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9][A-Za-z0-9.-]{0,63})?$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class BetaReleaseReviewManifestError(ValueError):
    pass


@dataclass(frozen=True)
class BetaReleaseReviewManifestEvidence:
    schema_version: int
    manifest_policy: str
    project: str
    version: str
    profile_id: str
    device_serial: str
    firmware_build: str
    firmware_fingerprint: str
    source_commit: str
    artifact_inventory_sha256: str
    artifacts: tuple[ReleaseArtifactEntry, ...]
    artifact_count: int
    sha256sums_sha256: str
    sha256sums_size: int
    exact_artifacts_reverified: bool
    inventory_ready_for_final_manual_release_review: bool
    final_manual_release_gate_review_required: bool
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
        raise BetaReleaseReviewManifestError(f"{label} must be a lowercase SHA-256")
    return value


def _positive(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise BetaReleaseReviewManifestError(f"{label} must be a positive integer")
    return value


def _safe_text(value: object, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise BetaReleaseReviewManifestError(f"{label} must be non-empty bounded text")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise BetaReleaseReviewManifestError(f"{label} contains control data")
    return value


def _safe_filename(value: object) -> str:
    if not isinstance(value, str) or not _SAFE_FILENAME_RE.fullmatch(value):
        raise BetaReleaseReviewManifestError(
            "release artifact filenames must use a safe ASCII basename (letters, digits, dot, underscore, plus, hyphen)"
        )
    if Path(value).name != value or value in {".", ".."}:
        raise BetaReleaseReviewManifestError("release artifact filename is not a safe basename")
    return value


def _read_exact(path: Path, label: str, maximum: int) -> tuple[bytes, str, int]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise BetaReleaseReviewManifestError(f"{label} must be a regular non-symlink file")
    try:
        before = source.stat()
        if before.st_size <= 0 or before.st_size > maximum:
            raise BetaReleaseReviewManifestError(f"{label} size is outside the safety limit")
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
                    raise BetaReleaseReviewManifestError(f"{label} size is outside the safety limit")
                digest.update(chunk)
                if maximum <= _MAX_EVIDENCE_BYTES:
                    chunks.append(chunk)
        after = source.stat()
    except OSError as exc:
        raise BetaReleaseReviewManifestError(f"cannot read {label}: {exc}") from exc
    if total != before.st_size:
        raise BetaReleaseReviewManifestError(f"{label} size changed while being read")
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or getattr(before, "st_ino", None) != getattr(after, "st_ino", None)
    ):
        raise BetaReleaseReviewManifestError(f"{label} changed while being read")
    return b"".join(chunks), digest.hexdigest(), total


def _validate_inventory_admission(inventory: BetaReleaseArtifactInventoryEvidence) -> None:
    if inventory.ready_for_final_manual_release_review is not True:
        raise BetaReleaseReviewManifestError("artifact inventory is not ready for final manual release review")
    if inventory.manual_release_gate_review_required is not True:
        raise BetaReleaseReviewManifestError("artifact inventory must require final manual release-gate review")
    for name in ("release_publication_allowed", "beta_release_authorized", "hardware_verified", "beta_gate_credit"):
        if getattr(inventory, name) is not False:
            raise BetaReleaseReviewManifestError(f"artifact inventory contains forbidden promotion: {name}")
    if not isinstance(inventory.source_commit, str) or not _COMMIT_RE.fullmatch(inventory.source_commit):
        raise BetaReleaseReviewManifestError("artifact inventory source commit is invalid")
    if not inventory.artifacts:
        raise BetaReleaseReviewManifestError("artifact inventory is empty")
    for item in inventory.artifacts:
        _safe_filename(item.filename)
        _positive(item.size, f"artifact {item.role} size")
        _sha(item.sha256, f"artifact {item.role}")


def build_sha256sums_text(artifacts: tuple[ReleaseArtifactEntry, ...]) -> str:
    if not artifacts:
        raise BetaReleaseReviewManifestError("cannot build SHA256SUMS for an empty artifact set")
    seen: set[str] = set()
    lines: list[str] = []
    for item in sorted(artifacts, key=lambda entry: entry.filename):
        filename = _safe_filename(item.filename)
        if filename in seen:
            raise BetaReleaseReviewManifestError("release artifact filenames must be unique")
        seen.add(filename)
        lines.append(f"{_sha(item.sha256, f'artifact {item.role}')}  {filename}\n")
    return "".join(lines)


def build_beta_release_review_manifest(
    inventory_path: Path,
    release_dir: Path,
    version: str,
) -> tuple[BetaReleaseReviewManifestEvidence, str]:
    if not isinstance(version, str) or not _SAFE_VERSION_RE.fullmatch(version):
        raise BetaReleaseReviewManifestError("version must be a bounded semantic-version-like identifier")
    try:
        inventory = load_beta_release_artifact_inventory(Path(inventory_path))
    except BetaReleaseArtifactInventoryError as exc:
        raise BetaReleaseReviewManifestError(str(exc)) from exc
    _validate_inventory_admission(inventory)

    root = Path(release_dir)
    if root.is_symlink() or not root.is_dir():
        raise BetaReleaseReviewManifestError("release directory must be a regular non-symlink directory")

    reverified: list[ReleaseArtifactEntry] = []
    for expected in inventory.artifacts:
        filename = _safe_filename(expected.filename)
        source = root / filename
        _, digest, size = _read_exact(source, f"release artifact {expected.role}", _MAX_ARTIFACT_BYTES)
        if digest != expected.sha256 or size != expected.size:
            raise BetaReleaseReviewManifestError(
                f"release artifact {expected.role} differs from exact artifact inventory"
            )
        reverified.append(expected)

    artifacts = tuple(sorted(reverified, key=lambda item: item.role))
    checksums = build_sha256sums_text(artifacts)
    checksums_bytes = checksums.encode("utf-8")
    evidence = BetaReleaseReviewManifestEvidence(
        schema_version=1,
        manifest_policy=_POLICY,
        project=_PROJECT,
        version=version,
        profile_id=inventory.profile_id,
        device_serial=inventory.device_serial,
        firmware_build=inventory.firmware_build,
        firmware_fingerprint=inventory.firmware_fingerprint,
        source_commit=inventory.source_commit,
        artifact_inventory_sha256=inventory.evidence_sha256(),
        artifacts=artifacts,
        artifact_count=len(artifacts),
        sha256sums_sha256=sha256(checksums_bytes).hexdigest(),
        sha256sums_size=len(checksums_bytes),
        exact_artifacts_reverified=True,
        inventory_ready_for_final_manual_release_review=True,
        final_manual_release_gate_review_required=True,
        release_publication_allowed=False,
        beta_release_authorized=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    validate_beta_release_review_manifest_evidence(evidence)
    return evidence, checksums


def validate_beta_release_review_manifest_evidence(evidence: BetaReleaseReviewManifestEvidence) -> None:
    if not isinstance(evidence, BetaReleaseReviewManifestEvidence) or evidence.schema_version != 1:
        raise BetaReleaseReviewManifestError("Beta release review manifest must be schema-v1 typed evidence")
    if evidence.manifest_policy != _POLICY or evidence.project != _PROJECT:
        raise BetaReleaseReviewManifestError("Beta release review manifest policy/project is unsupported")
    if not _SAFE_VERSION_RE.fullmatch(evidence.version):
        raise BetaReleaseReviewManifestError("Beta release review manifest version is invalid")
    _safe_text(evidence.profile_id, "profile id", 128)
    _safe_text(evidence.device_serial, "device serial", 256)
    _safe_text(evidence.firmware_build, "firmware build", 512)
    _safe_text(evidence.firmware_fingerprint, "firmware fingerprint", 1024)
    if not _COMMIT_RE.fullmatch(evidence.source_commit):
        raise BetaReleaseReviewManifestError("source commit must be an exact lowercase 40-hex Git commit")
    _sha(evidence.artifact_inventory_sha256, "artifact inventory")
    _sha(evidence.sha256sums_sha256, "SHA256SUMS")
    _positive(evidence.sha256sums_size, "SHA256SUMS size")
    if not isinstance(evidence.artifacts, tuple) or not evidence.artifacts:
        raise BetaReleaseReviewManifestError("Beta release review manifest must contain artifacts")
    if evidence.artifact_count != len(evidence.artifacts):
        raise BetaReleaseReviewManifestError("artifact count drifted")
    if evidence.artifact_count <= 0:
        raise BetaReleaseReviewManifestError("artifact count must be positive")
    roles: set[str] = set()
    filenames: set[str] = set()
    for item in evidence.artifacts:
        if not isinstance(item, ReleaseArtifactEntry):
            raise BetaReleaseReviewManifestError("manifest artifact entries must be typed")
        if item.role in roles:
            raise BetaReleaseReviewManifestError("manifest artifact roles must be unique")
        filename = _safe_filename(item.filename)
        if filename in filenames:
            raise BetaReleaseReviewManifestError("manifest artifact filenames must be unique")
        _positive(item.size, f"artifact {item.role} size")
        _sha(item.sha256, f"artifact {item.role}")
        roles.add(item.role)
        filenames.add(filename)
    expected_checksums = build_sha256sums_text(evidence.artifacts).encode("utf-8")
    if evidence.sha256sums_sha256 != sha256(expected_checksums).hexdigest():
        raise BetaReleaseReviewManifestError("SHA256SUMS digest drifted from manifest artifacts")
    if evidence.sha256sums_size != len(expected_checksums):
        raise BetaReleaseReviewManifestError("SHA256SUMS size drifted from manifest artifacts")
    if evidence.exact_artifacts_reverified is not True:
        raise BetaReleaseReviewManifestError("manifest must reverify every exact artifact")
    if evidence.inventory_ready_for_final_manual_release_review is not True:
        raise BetaReleaseReviewManifestError("manifest requires review-ready artifact inventory")
    if evidence.final_manual_release_gate_review_required is not True:
        raise BetaReleaseReviewManifestError("manifest must require final manual release-gate review")
    for name in ("release_publication_allowed", "beta_release_authorized", "hardware_verified", "beta_gate_credit"):
        if getattr(evidence, name) is not False:
            raise BetaReleaseReviewManifestError(f"review manifest cannot promote {name}")


def write_beta_release_review_manifest_bundle(
    evidence: BetaReleaseReviewManifestEvidence,
    checksums_text: str,
    manifest_destination: Path,
    checksums_destination: Path,
) -> str:
    validate_beta_release_review_manifest_evidence(evidence)
    expected = build_sha256sums_text(evidence.artifacts)
    if checksums_text != expected:
        raise BetaReleaseReviewManifestError("SHA256SUMS text differs from manifest artifact set")
    manifest_path = Path(manifest_destination)
    checksums_path = Path(checksums_destination)
    if manifest_path == checksums_path:
        raise BetaReleaseReviewManifestError("manifest and SHA256SUMS outputs must be different files")
    for destination in (manifest_path, checksums_path):
        if destination.exists() or destination.is_symlink():
            raise BetaReleaseReviewManifestError(f"refusing to overwrite existing output: {destination}")

    created: list[Path] = []
    try:
        for destination, text in (
            (manifest_path, evidence.canonical_json()),
            (checksums_path, checksums_text),
        ):
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
            created.append(destination)
    except OSError as exc:
        for destination in created:
            try:
                destination.unlink()
            except OSError:
                pass
        raise BetaReleaseReviewManifestError(f"cannot write review manifest bundle: {exc}") from exc
    return evidence.evidence_sha256()


def load_beta_release_review_manifest(path: Path) -> BetaReleaseReviewManifestEvidence:
    raw, _, _ = _read_exact(Path(path), "Beta release review manifest", _MAX_EVIDENCE_BYTES)
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BetaReleaseReviewManifestError("Beta release review manifest is not valid UTF-8 JSON") from exc
    expected = {item.name for item in fields(BetaReleaseReviewManifestEvidence)}
    if not isinstance(value, dict) or set(value) != expected or not isinstance(value.get("artifacts"), list):
        raise BetaReleaseReviewManifestError("Beta release review manifest fields do not match schema-v1")
    try:
        artifacts = tuple(ReleaseArtifactEntry(**item) for item in value["artifacts"])
        evidence = BetaReleaseReviewManifestEvidence(**{**value, "artifacts": artifacts})
    except (TypeError, KeyError) as exc:
        raise BetaReleaseReviewManifestError("Beta release review manifest field types are invalid") from exc
    validate_beta_release_review_manifest_evidence(evidence)
    if raw != evidence.canonical_json().encode("utf-8"):
        raise BetaReleaseReviewManifestError("Beta release review manifest is not canonical JSON")
    return evidence
