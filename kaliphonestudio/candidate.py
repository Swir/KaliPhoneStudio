"""Host-side first-boot candidate manifest binding boot, kernel, device-tree and Kali userspace evidence."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re

from .boot_authorization import TemporaryBootAuthorization
from .boot_builder import BootBuildPlan
from .device_tree import DeviceTreeCandidateEvidence
from .kernel_bundle import KernelCandidateEvidence
from .kernel_repro import KernelReproducibilityEvidence
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
    kernel_reproducibility_evidence_sha256: str
    kernel_reproducible: bool
    kernel_distinct_build_roots_verified: bool
    device_tree_evidence_sha256: str
    device_tree_format_lock_sha256: str
    dtb_sha256: str | None
    dtb_size: int | None
    dtb_tree_count: int | None
    dtbo_sha256: str | None
    dtbo_size: int | None
    dtbo_entry_count: int | None
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


def _single_plan_input(plan: BootBuildPlan, name: str, *, required: bool):
    if plan.schema_version != 1:
        raise RootfsError("unsupported boot build plan schema")
    matches = [item for item in plan.inputs if item.name == name]
    if required and len(matches) != 1:
        raise RootfsError(f"boot build plan must contain exactly one {name} input")
    if not required and len(matches) > 1:
        raise RootfsError(f"boot build plan contains duplicate {name} inputs")
    return matches[0] if matches else None


def _verify_kernel_reproducibility_binding(
    kernel: KernelCandidateEvidence,
    reproducibility: KernelReproducibilityEvidence,
) -> None:
    if reproducibility.schema_version != 1:
        raise RootfsError("unsupported kernel reproducibility evidence schema")
    if reproducibility.profile_id != kernel.profile_id:
        raise RootfsError("kernel reproducibility evidence profile does not match kernel candidate")
    if reproducibility.kernel_plan_sha256 != kernel.kernel_plan_sha256:
        raise RootfsError("kernel reproducibility evidence does not match kernel plan digest")
    if reproducibility.source_commit != kernel.source_commit:
        raise RootfsError("kernel reproducibility evidence source commit drifted")
    if reproducibility.kernel_version != kernel.kernel_version:
        raise RootfsError("kernel reproducibility evidence version drifted")
    if reproducibility.config_sha256 != kernel.config_sha256:
        raise RootfsError("reproducible kernel config does not match kernel candidate")
    if reproducibility.image_sha256 != kernel.image_sha256:
        raise RootfsError("reproducible kernel Image does not match kernel candidate")
    if reproducibility.image_size != kernel.image_size:
        raise RootfsError("reproducible kernel Image size does not match kernel candidate")
    if reproducibility.config_size <= 0:
        raise RootfsError("kernel reproducibility evidence contains invalid config size")
    if reproducibility.distinct_build_roots_verified is not True:
        raise RootfsError("kernel reproducibility evidence lacks distinct build-root verification")
    if reproducibility.byte_identical is not True:
        raise RootfsError("kernel reproducibility evidence is not byte-identical")
    if reproducibility.beta_gate_credit is not False:
        raise RootfsError("host kernel reproducibility evidence cannot claim hardware Beta credit")
    if not _SHA256_RE.fullmatch(reproducibility.evidence_sha256()):
        raise RootfsError("kernel reproducibility evidence digest is invalid")


def _verify_device_tree_binding(plan: BootBuildPlan, evidence: DeviceTreeCandidateEvidence) -> None:
    if evidence.schema_version != 1:
        raise RootfsError("unsupported device-tree candidate evidence schema")
    if evidence.profile_id != plan.profile_id:
        raise RootfsError("device-tree evidence profile does not match boot build plan")
    if evidence.boot_plan_sha256 != plan.plan_sha256():
        raise RootfsError("device-tree evidence does not match boot build plan digest")
    for value, label in (
        (evidence.evidence_sha256(), "device-tree evidence SHA-256"),
        (evidence.format_lock_sha256, "device-tree format lock SHA-256"),
    ):
        if not _SHA256_RE.fullmatch(value):
            raise RootfsError(f"device-tree candidate contains invalid {label}")

    dtb_input = _single_plan_input(plan, "dtb", required=False)
    if dtb_input is None:
        if any(value is not None for value in (evidence.dtb_sha256, evidence.dtb_size, evidence.dtb_tree_count, evidence.dtb_evidence_sha256)):
            raise RootfsError("device-tree evidence contains DTB data absent from boot build plan")
    else:
        if not evidence.dtb_sha256 or not _SHA256_RE.fullmatch(evidence.dtb_sha256):
            raise RootfsError("device-tree candidate contains invalid DTB SHA-256")
        if not evidence.dtb_evidence_sha256 or not _SHA256_RE.fullmatch(evidence.dtb_evidence_sha256):
            raise RootfsError("device-tree candidate contains invalid DTB evidence SHA-256")
        if evidence.dtb_size != dtb_input.size or evidence.dtb_sha256 != dtb_input.sha256:
            raise RootfsError("verified DTB evidence does not match the DTB embedded in the boot plan")
        if not isinstance(evidence.dtb_tree_count, int) or isinstance(evidence.dtb_tree_count, bool) or evidence.dtb_tree_count <= 0:
            raise RootfsError("device-tree candidate contains invalid DTB tree count")

    dtbo_input = _single_plan_input(plan, "dtbo", required=False)
    if dtbo_input is None:
        if any(value is not None for value in (evidence.dtbo_sha256, evidence.dtbo_size, evidence.dtbo_entry_count, evidence.dtbo_evidence_sha256)):
            raise RootfsError("device-tree evidence contains DTBO data absent from boot build plan")
    else:
        if not evidence.dtbo_sha256 or not _SHA256_RE.fullmatch(evidence.dtbo_sha256):
            raise RootfsError("device-tree candidate contains invalid DTBO SHA-256")
        if not evidence.dtbo_evidence_sha256 or not _SHA256_RE.fullmatch(evidence.dtbo_evidence_sha256):
            raise RootfsError("device-tree candidate contains invalid DTBO evidence SHA-256")
        if evidence.dtbo_size != dtbo_input.size or evidence.dtbo_sha256 != dtbo_input.sha256:
            raise RootfsError("verified DTBO evidence does not match the DTBO embedded in the boot plan")
        if not isinstance(evidence.dtbo_entry_count, int) or isinstance(evidence.dtbo_entry_count, bool) or evidence.dtbo_entry_count <= 0:
            raise RootfsError("device-tree candidate contains invalid DTBO entry count")


def create_first_boot_candidate_manifest(
    boot: TemporaryBootAuthorization,
    boot_plan: BootBuildPlan,
    kernel_evidence: KernelCandidateEvidence,
    rootfs_lock: RootfsSourceLock,
    repository_snapshot: RepositorySnapshotEvidence,
    rootfs_evidence: RootfsArtifactEvidence,
    *,
    kernel_reproducibility_evidence: KernelReproducibilityEvidence,
    device_tree_evidence: DeviceTreeCandidateEvidence,
    rootfs_artifact: Path,
) -> FirstBootCandidateManifest:
    """Bind verified boot, reproducible kernel, DTB/DTBO and rootfs evidence.

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

    boot_kernel = _single_plan_input(boot_plan, "kernel", required=True)
    if boot_kernel.sha256 != kernel_evidence.image_sha256 or boot_kernel.size != kernel_evidence.image_size:
        raise RootfsError("verified kernel evidence does not match the kernel embedded in the boot plan")

    _verify_kernel_reproducibility_binding(kernel_evidence, kernel_reproducibility_evidence)
    _verify_device_tree_binding(boot_plan, device_tree_evidence)

    verify_rootfs_artifact(
        rootfs_lock,
        repository_snapshot,
        rootfs_evidence,
        artifact=rootfs_artifact,
    )
    return FirstBootCandidateManifest(
        schema_version=6,
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
        kernel_reproducibility_evidence_sha256=kernel_reproducibility_evidence.evidence_sha256(),
        kernel_reproducible=True,
        kernel_distinct_build_roots_verified=True,
        device_tree_evidence_sha256=device_tree_evidence.evidence_sha256(),
        device_tree_format_lock_sha256=device_tree_evidence.format_lock_sha256,
        dtb_sha256=device_tree_evidence.dtb_sha256,
        dtb_size=device_tree_evidence.dtb_size,
        dtb_tree_count=device_tree_evidence.dtb_tree_count,
        dtbo_sha256=device_tree_evidence.dtbo_sha256,
        dtbo_size=device_tree_evidence.dtbo_size,
        dtbo_entry_count=device_tree_evidence.dtbo_entry_count,
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
