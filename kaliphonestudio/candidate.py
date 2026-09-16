"""Host-side first-boot candidate manifest binding boot, kernel, compiler, device-tree and Kali userspace evidence."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re

from .boot_authorization import TemporaryBootAuthorization
from .boot_builder import BootBuildPlan
from .device_tree import DeviceTreeCandidateEvidence
from .kernel_build_binding import KernelReproducibilityBindingEvidence
from .kernel_build_runner import KernelBuildRunEvidence
from .kernel_bundle import KernelCandidateEvidence
from .kernel_repro import KernelReproducibilityEvidence
from .kernel_toolchain_bundle import KernelToolchainCandidateEvidence
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
    kernel_reproducibility_binding_evidence_sha256: str
    kernel_build_recipe_sha256: str
    kernel_reproducible_environment_sha256: str
    kernel_build_a_run_evidence_sha256: str
    kernel_build_b_run_evidence_sha256: str
    kernel_reproducible: bool
    kernel_distinct_build_roots_verified: bool
    kernel_toolchain_evidence_sha256: str
    kernel_toolchain_lock_sha256: str
    kernel_toolchain_source_evidence_sha256: str
    kernel_toolchain_binding_evidence_sha256: str
    kernel_toolchain_materialized_evidence_sha256: str
    kernel_clang_revision: str
    kernel_clang_sha256: str
    kernel_clang_size: int
    kernel_build_config_sha256: str
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


def _verify_kernel_toolchain_binding(
    kernel: KernelCandidateEvidence,
    toolchain: KernelToolchainCandidateEvidence,
) -> None:
    if toolchain.schema_version != 1:
        raise RootfsError("unsupported kernel toolchain candidate evidence schema")
    if toolchain.profile_id != kernel.profile_id:
        raise RootfsError("kernel toolchain evidence profile does not match kernel candidate")
    if toolchain.kernel_plan_sha256 != kernel.kernel_plan_sha256:
        raise RootfsError("kernel toolchain evidence does not match kernel plan digest")
    if toolchain.kernel_source_commit != kernel.source_commit:
        raise RootfsError("kernel toolchain evidence source commit drifted")
    if toolchain.beta_gate_credit is not False:
        raise RootfsError("host kernel toolchain evidence cannot claim hardware Beta credit")
    for value, label in (
        (toolchain.evidence_sha256(), "kernel toolchain evidence SHA-256"),
        (toolchain.toolchain_lock_sha256, "kernel toolchain lock SHA-256"),
        (toolchain.source_evidence_sha256, "kernel toolchain source evidence SHA-256"),
        (toolchain.binding_evidence_sha256, "kernel toolchain binding evidence SHA-256"),
        (toolchain.materialized_evidence_sha256, "materialized kernel toolchain evidence SHA-256"),
        (toolchain.clang_sha256, "kernel clang SHA-256"),
        (toolchain.build_config_sha256, "kernel build config SHA-256"),
    ):
        if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
            raise RootfsError(f"kernel toolchain candidate contains invalid {label}")
    if not isinstance(toolchain.clang_size, int) or isinstance(toolchain.clang_size, bool) or toolchain.clang_size <= 0:
        raise RootfsError("kernel toolchain candidate contains invalid clang size")
    if not isinstance(toolchain.clang_revision, str) or not toolchain.clang_revision.strip():
        raise RootfsError("kernel toolchain candidate contains invalid clang revision")


def _verify_kernel_build_run(
    kernel: KernelCandidateEvidence,
    toolchain: KernelToolchainCandidateEvidence,
    execution: KernelReproducibilityBindingEvidence,
    run: KernelBuildRunEvidence,
    *,
    expected_digest: str,
    label: str,
) -> None:
    if run.schema_version != 1:
        raise RootfsError(f"{label} has unsupported schema")
    if run.evidence_sha256() != expected_digest:
        raise RootfsError(f"{label} digest does not match kernel execution binding")
    if run.profile_id != kernel.profile_id:
        raise RootfsError(f"{label} profile does not match kernel candidate")
    if run.kernel_plan_sha256 != kernel.kernel_plan_sha256:
        raise RootfsError(f"{label} does not match kernel plan digest")
    if run.source_commit != kernel.source_commit:
        raise RootfsError(f"{label} source commit drifted")
    if run.toolchain_lock_sha256 != toolchain.toolchain_lock_sha256:
        raise RootfsError(f"{label} toolchain lock drifted")
    if run.checkout_evidence_sha256 != kernel.checkout_evidence_sha256:
        raise RootfsError(f"{label} checkout evidence does not match kernel candidate")
    if run.toolchain_binding_evidence_sha256 != toolchain.binding_evidence_sha256:
        raise RootfsError(f"{label} toolchain selection evidence drifted")
    if run.materialized_toolchain_evidence_sha256 != toolchain.materialized_evidence_sha256:
        raise RootfsError(f"{label} materialized compiler evidence drifted")
    if run.build_recipe_sha256 != execution.build_recipe_sha256:
        raise RootfsError(f"{label} build recipe does not match execution binding")
    if run.reproducible_environment_sha256 != execution.reproducible_environment_sha256:
        raise RootfsError(f"{label} reproducibility environment does not match execution binding")
    if run.config_evidence_sha256 != kernel.config_evidence_sha256:
        raise RootfsError(f"{label} config evidence does not match kernel candidate")
    if run.config_sha256 != kernel.config_sha256 or run.config_size != execution.config_size:
        raise RootfsError(f"{label} final config does not match accepted kernel evidence")
    if run.image_evidence_sha256 != kernel.image_evidence_sha256:
        raise RootfsError(f"{label} Image evidence does not match kernel candidate")
    if run.image_sha256 != kernel.image_sha256 or run.image_size != kernel.image_size:
        raise RootfsError(f"{label} final Image does not match accepted kernel evidence")
    if run.arm64_magic_verified is not True:
        raise RootfsError(f"{label} lacks ARM64 Image verification")
    if run.beta_gate_credit is not False:
        raise RootfsError(f"{label} cannot claim hardware Beta credit")


def _verify_kernel_execution_binding(
    kernel: KernelCandidateEvidence,
    reproducibility: KernelReproducibilityEvidence,
    toolchain: KernelToolchainCandidateEvidence,
    execution: KernelReproducibilityBindingEvidence,
    build_a: KernelBuildRunEvidence,
    build_b: KernelBuildRunEvidence,
) -> None:
    if execution.schema_version != 1:
        raise RootfsError("unsupported kernel reproducibility binding schema")
    if execution.profile_id != kernel.profile_id:
        raise RootfsError("kernel execution binding profile does not match kernel candidate")
    if execution.kernel_plan_sha256 != kernel.kernel_plan_sha256:
        raise RootfsError("kernel execution binding does not match kernel plan digest")
    if execution.source_commit != kernel.source_commit:
        raise RootfsError("kernel execution binding source commit drifted")
    if execution.toolchain_lock_sha256 != toolchain.toolchain_lock_sha256:
        raise RootfsError("kernel execution binding toolchain lock drifted")
    if execution.reproducibility_evidence_sha256 != reproducibility.evidence_sha256():
        raise RootfsError("kernel execution binding does not match reproducibility evidence")
    if execution.config_sha256 != reproducibility.config_sha256 or execution.config_size != reproducibility.config_size:
        raise RootfsError("kernel execution binding config does not match reproducibility evidence")
    if execution.image_sha256 != kernel.image_sha256 or execution.image_sha256 != reproducibility.image_sha256:
        raise RootfsError("kernel execution binding Image does not match kernel candidate")
    if execution.image_size != kernel.image_size or execution.image_size != reproducibility.image_size:
        raise RootfsError("kernel execution binding Image size does not match kernel candidate")
    if execution.byte_identical is not True or execution.distinct_build_roots_verified is not True:
        raise RootfsError("kernel execution binding does not prove independent byte-identical builds")
    if execution.beta_gate_credit is not False:
        raise RootfsError("host kernel execution binding cannot claim hardware Beta credit")
    for value, label in (
        (execution.evidence_sha256(), "kernel execution binding evidence SHA-256"),
        (execution.toolchain_lock_sha256, "kernel execution binding toolchain lock SHA-256"),
        (execution.build_recipe_sha256, "kernel build recipe SHA-256"),
        (execution.reproducible_environment_sha256, "kernel reproducible environment SHA-256"),
        (execution.build_a_run_evidence_sha256, "kernel build A run evidence SHA-256"),
        (execution.build_b_run_evidence_sha256, "kernel build B run evidence SHA-256"),
        (execution.reproducibility_evidence_sha256, "kernel reproducibility evidence SHA-256"),
    ):
        if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
            raise RootfsError(f"kernel execution binding contains invalid {label}")
    _verify_kernel_build_run(
        kernel,
        toolchain,
        execution,
        build_a,
        expected_digest=execution.build_a_run_evidence_sha256,
        label="kernel build A evidence",
    )
    _verify_kernel_build_run(
        kernel,
        toolchain,
        execution,
        build_b,
        expected_digest=execution.build_b_run_evidence_sha256,
        label="kernel build B evidence",
    )


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
    kernel_reproducibility_binding_evidence: KernelReproducibilityBindingEvidence,
    kernel_build_a_evidence: KernelBuildRunEvidence,
    kernel_build_b_evidence: KernelBuildRunEvidence,
    kernel_toolchain_evidence: KernelToolchainCandidateEvidence,
    device_tree_evidence: DeviceTreeCandidateEvidence,
    rootfs_artifact: Path,
) -> FirstBootCandidateManifest:
    """Bind verified boot, exact executed reproducible kernel+compiler, DTB/DTBO and rootfs evidence.

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
    _verify_kernel_toolchain_binding(kernel_evidence, kernel_toolchain_evidence)
    _verify_kernel_execution_binding(
        kernel_evidence,
        kernel_reproducibility_evidence,
        kernel_toolchain_evidence,
        kernel_reproducibility_binding_evidence,
        kernel_build_a_evidence,
        kernel_build_b_evidence,
    )
    _verify_device_tree_binding(boot_plan, device_tree_evidence)

    verify_rootfs_artifact(
        rootfs_lock,
        repository_snapshot,
        rootfs_evidence,
        artifact=rootfs_artifact,
    )
    return FirstBootCandidateManifest(
        schema_version=8,
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
        kernel_reproducibility_binding_evidence_sha256=kernel_reproducibility_binding_evidence.evidence_sha256(),
        kernel_build_recipe_sha256=kernel_reproducibility_binding_evidence.build_recipe_sha256,
        kernel_reproducible_environment_sha256=kernel_reproducibility_binding_evidence.reproducible_environment_sha256,
        kernel_build_a_run_evidence_sha256=kernel_reproducibility_binding_evidence.build_a_run_evidence_sha256,
        kernel_build_b_run_evidence_sha256=kernel_reproducibility_binding_evidence.build_b_run_evidence_sha256,
        kernel_reproducible=True,
        kernel_distinct_build_roots_verified=True,
        kernel_toolchain_evidence_sha256=kernel_toolchain_evidence.evidence_sha256(),
        kernel_toolchain_lock_sha256=kernel_toolchain_evidence.toolchain_lock_sha256,
        kernel_toolchain_source_evidence_sha256=kernel_toolchain_evidence.source_evidence_sha256,
        kernel_toolchain_binding_evidence_sha256=kernel_toolchain_evidence.binding_evidence_sha256,
        kernel_toolchain_materialized_evidence_sha256=kernel_toolchain_evidence.materialized_evidence_sha256,
        kernel_clang_revision=kernel_toolchain_evidence.clang_revision,
        kernel_clang_sha256=kernel_toolchain_evidence.clang_sha256,
        kernel_clang_size=kernel_toolchain_evidence.clang_size,
        kernel_build_config_sha256=kernel_toolchain_evidence.build_config_sha256,
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
