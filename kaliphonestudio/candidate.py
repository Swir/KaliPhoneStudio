"""Host-side first-boot candidate manifest binding boot, kernel and Kali userspace evidence."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re

from .boot_authorization import TemporaryBootAuthorization
from .boot_builder import BootBuildPlan
from .kernel_bundle import KernelCandidateEvidence
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
    fastboot_baseline_sha256: str
    firmware_build: str
    firmware_fingerprint: str
    boot_authorization_sha256: str
    boot_plan_sha256: str
    boot_image_sha256: str
    boot_image_size: int
    kernel_evidence_sha256: str
    kernel_plan_sha256: str
    kernel_source_commit: str
    kernel_version: str
    kernel_config_sha256: str
    kernel_image_sha256: str
    kernel_image_size: int
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


def _require_boot_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise RootfsError(f"temporary-boot authorization contains invalid {label}")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise RootfsError(f"temporary-boot authorization contains invalid {label}")


def _kernel_input_from_boot_plan(plan: BootBuildPlan):
    if plan.schema_version != 1:
        raise RootfsError("unsupported boot build plan schema")
    matches = [item for item in plan.inputs if item.name == "kernel"]
    if len(matches) != 1:
        raise RootfsError("boot build plan must contain exactly one kernel input")
    return matches[0]


def create_first_boot_candidate_manifest(
    boot: TemporaryBootAuthorization,
    boot_plan: BootBuildPlan,
    kernel_evidence: KernelCandidateEvidence,
    rootfs_lock: RootfsSourceLock,
    repository_snapshot: RepositorySnapshotEvidence,
    rootfs_evidence: RootfsArtifactEvidence,
    *,
    rootfs_artifact: Path,
) -> FirstBootCandidateManifest:
    """Bind already-verified boot, kernel and rootfs evidence.

    The result is host-side evidence only. It is deliberately not hardware-success
    evidence and does not execute fastboot or write any phone partition.
    """
    if boot.schema_version != 2:
        raise RootfsError("unsupported temporary-boot authorization schema")
    if not boot.profile_id or not boot.device_serial:
        raise RootfsError("first-boot candidate requires a verified device binding")
    if not boot.reproducible or not boot.structurally_verified:
        raise RootfsError("first-boot candidate requires fully verified boot authorization")
    if boot.image_size <= 0:
        raise RootfsError("temporary-boot authorization contains invalid image evidence")
    _require_boot_hash(boot.fastboot_baseline_sha256, "fastboot baseline SHA-256")
    _require_boot_hash(boot.plan_sha256, "plan SHA-256")
    _require_boot_hash(boot.stock_boot_sha256, "stock boot SHA-256")
    _require_boot_hash(boot.stock_ota_sha256, "stock OTA SHA-256")
    _require_boot_hash(boot.image_sha256, "image SHA-256")
    _require_boot_text(boot.firmware_build, "firmware build")
    _require_boot_text(boot.firmware_fingerprint, "firmware fingerprint")

    if boot_plan.profile_id != boot.profile_id:
        raise RootfsError("boot build plan profile does not match temporary-boot authorization")
    if boot_plan.plan_sha256() != boot.plan_sha256:
        raise RootfsError("boot build plan digest does not match temporary-boot authorization")

    if kernel_evidence.schema_version != 1:
        raise RootfsError("unsupported kernel candidate evidence schema")
    if kernel_evidence.profile_id != boot.profile_id:
        raise RootfsError("kernel candidate profile does not match temporary-boot authorization")
    if kernel_evidence.arm64_magic_verified is not True:
        raise RootfsError("kernel candidate lacks ARM64 Image verification")
    for value, label in (
        (kernel_evidence.evidence_sha256(), "kernel evidence SHA-256"),
        (kernel_evidence.kernel_plan_sha256, "kernel plan SHA-256"),
        (kernel_evidence.config_sha256, "kernel config SHA-256"),
        (kernel_evidence.image_sha256, "kernel image SHA-256"),
    ):
        if not _SHA256_RE.fullmatch(value):
            raise RootfsError(f"kernel candidate contains invalid {label}")
    if kernel_evidence.image_size <= 0:
        raise RootfsError("kernel candidate contains invalid image size")

    boot_kernel = _kernel_input_from_boot_plan(boot_plan)
    if boot_kernel.sha256 != kernel_evidence.image_sha256 or boot_kernel.size != kernel_evidence.image_size:
        raise RootfsError("verified kernel evidence does not match the kernel embedded in the boot plan")

    verify_rootfs_artifact(
        rootfs_lock,
        repository_snapshot,
        rootfs_evidence,
        artifact=rootfs_artifact,
    )
    return FirstBootCandidateManifest(
        schema_version=4,
        profile_id=boot.profile_id,
        device_serial=boot.device_serial,
        fastboot_baseline_sha256=boot.fastboot_baseline_sha256,
        firmware_build=boot.firmware_build,
        firmware_fingerprint=boot.firmware_fingerprint,
        boot_authorization_sha256=boot.authorization_sha256(),
        boot_plan_sha256=boot_plan.plan_sha256(),
        boot_image_sha256=boot.image_sha256,
        boot_image_size=boot.image_size,
        kernel_evidence_sha256=kernel_evidence.evidence_sha256(),
        kernel_plan_sha256=kernel_evidence.kernel_plan_sha256,
        kernel_source_commit=kernel_evidence.source_commit,
        kernel_version=kernel_evidence.kernel_version,
        kernel_config_sha256=kernel_evidence.config_sha256,
        kernel_image_sha256=kernel_evidence.image_sha256,
        kernel_image_size=kernel_evidence.image_size,
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
