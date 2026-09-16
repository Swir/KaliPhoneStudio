"""Host-side first-boot candidate manifest binding boot and Kali userspace evidence."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re

from .boot_authorization import TemporaryBootAuthorization
from .rootfs import (
    RepositorySnapshotEvidence,
    RootfsArtifactEvidence,
    RootfsError,
    RootfsSourceLock,
    verify_rootfs_artifact,
)


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class FirstBootCandidateManifest:
    schema_version: int
    profile_id: str
    device_serial: str
    boot_authorization_sha256: str
    boot_image_sha256: str
    boot_image_size: int
    rootfs_evidence_sha256: str
    rootfs_artifact_sha256: str
    rootfs_artifact_size: int
    rootfs_package_manifest_sha256: str
    rootfs_package_count: int
    rootfs_source_lock_sha256: str
    repository_snapshot_sha256: str

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def manifest_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _require_boot_hash(value: str, label: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise RootfsError(f"temporary-boot authorization contains invalid {label}")


def create_first_boot_candidate_manifest(
    boot: TemporaryBootAuthorization,
    rootfs_lock: RootfsSourceLock,
    repository_snapshot: RepositorySnapshotEvidence,
    rootfs_evidence: RootfsArtifactEvidence,
    *,
    rootfs_artifact: Path,
) -> FirstBootCandidateManifest:
    """Bind already-verified boot authorization and rootfs evidence.

    The result is host-side evidence only. It is deliberately not hardware-success
    evidence and does not execute fastboot or write any phone partition.
    """
    if boot.schema_version != 1:
        raise RootfsError("unsupported temporary-boot authorization schema")
    if not boot.profile_id or not boot.device_serial:
        raise RootfsError("first-boot candidate requires a verified device binding")
    if not boot.reproducible or not boot.structurally_verified:
        raise RootfsError("first-boot candidate requires fully verified boot authorization")
    if boot.image_size <= 0:
        raise RootfsError("temporary-boot authorization contains invalid image evidence")
    _require_boot_hash(boot.plan_sha256, "plan SHA-256")
    _require_boot_hash(boot.stock_boot_sha256, "stock boot SHA-256")
    _require_boot_hash(boot.stock_ota_sha256, "stock OTA SHA-256")
    _require_boot_hash(boot.image_sha256, "image SHA-256")

    verify_rootfs_artifact(
        rootfs_lock,
        repository_snapshot,
        rootfs_evidence,
        artifact=rootfs_artifact,
    )
    return FirstBootCandidateManifest(
        schema_version=2,
        profile_id=boot.profile_id,
        device_serial=boot.device_serial,
        boot_authorization_sha256=boot.authorization_sha256(),
        boot_image_sha256=boot.image_sha256,
        boot_image_size=boot.image_size,
        rootfs_evidence_sha256=rootfs_evidence.evidence_sha256(),
        rootfs_artifact_sha256=rootfs_evidence.artifact_sha256,
        rootfs_artifact_size=rootfs_evidence.artifact_size,
        rootfs_package_manifest_sha256=rootfs_evidence.package_manifest_sha256,
        rootfs_package_count=rootfs_evidence.package_count,
        rootfs_source_lock_sha256=rootfs_lock.lock_sha256(),
        repository_snapshot_sha256=repository_snapshot.evidence_sha256(),
    )


def write_first_boot_candidate_manifest(manifest: FirstBootCandidateManifest, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = manifest.canonical_json()
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8", newline="\n")
    temporary.replace(destination)
    return manifest.manifest_sha256()
