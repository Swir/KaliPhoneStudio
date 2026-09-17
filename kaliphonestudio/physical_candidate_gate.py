"""Fail-closed host gate binding one physical baseline to one reviewed first-boot candidate.

This module deliberately stops before device I/O.  It cross-checks the immutable
physical Fastboot/stock-provenance bundle, schema-v8 first-boot manifest, reviewed
kernel/rootfs/device-tree authority bundle, temporary-boot authorization and exact
boot plan.  A successful result means only that the *offer* of a temporary boot is
cryptographically well-scoped; it is not evidence that a boot was attempted or that
any hardware feature works.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re

from .boot_authorization import TemporaryBootAuthorization
from .boot_builder import BootBuildPlan
from .boot_image import BootImageError, boot_build_contract
from .candidate import FirstBootCandidateManifest
from .candidate_authority_bundle import FirstBootAuthorityBundleEvidence
from .physical_baseline_bundle import PhysicalBaselineBundleEvidence
from .profiles import DeviceProfile

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PhysicalCandidateGateError(ValueError):
    pass


@dataclass(frozen=True)
class PhysicalCandidateGateEvidence:
    schema_version: int
    profile_id: str
    device_serial: str
    firmware_build: str
    firmware_fingerprint: str
    physical_baseline_bundle_sha256: str
    fastboot_capture_bundle_sha256: str
    fastboot_baseline_evidence_sha256: str
    fastboot_transcript_sha256: str
    stock_provenance_sha256: str
    stock_ota_sha256: str
    stock_boot_sha256: str
    first_boot_manifest_sha256: str
    first_boot_authority_bundle_sha256: str
    boot_authorization_sha256: str
    boot_plan_sha256: str
    boot_image_sha256: str
    boot_image_size: int
    kernel_image_sha256: str
    rootfs_artifact_sha256: str
    dtb_sha256: str | None
    dtbo_image_sha256: str | None
    reviewed_authorities_bound: bool
    exact_physical_baseline_bound: bool
    ready_for_temporary_boot_offer: bool
    temporary_boot_executed: bool = False
    phone_storage_written: bool = False
    hardware_verified: bool = False
    beta_gate_credit: bool = False

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise PhysicalCandidateGateError(f"{label} must be a lowercase SHA-256")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PhysicalCandidateGateError(f"{label} must be a non-empty string")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise PhysicalCandidateGateError(f"{label} contains control data")
    return value


def _positive(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PhysicalCandidateGateError(f"{label} must be a positive integer")
    return value


def _plan_input(plan: BootBuildPlan, name: str, *, required: bool):
    matches = [item for item in plan.inputs if item.name == name]
    if required and len(matches) != 1:
        raise PhysicalCandidateGateError(f"boot plan must contain exactly one {name} input")
    if not required and len(matches) > 1:
        raise PhysicalCandidateGateError(f"boot plan contains duplicate {name} inputs")
    return matches[0] if matches else None


def bind_physical_candidate_gate(
    profile: DeviceProfile,
    physical: PhysicalBaselineBundleEvidence,
    manifest: FirstBootCandidateManifest,
    authorities: FirstBootAuthorityBundleEvidence,
    boot: TemporaryBootAuthorization,
    boot_plan: BootBuildPlan,
) -> PhysicalCandidateGateEvidence:
    """Cross-bind all host evidence required before a temporary-boot UI may be offered.

    The function performs no ADB/Fastboot command and writes no device storage.  It
    intentionally returns ``hardware_verified=false`` and ``beta_gate_credit=false``.
    """
    profile_id = _text(getattr(profile, "profile_id", None), "profile_id")

    if not isinstance(physical, PhysicalBaselineBundleEvidence) or physical.schema_version != 1:
        raise PhysicalCandidateGateError("physical baseline bundle must be schema v1 typed evidence")
    if physical.profile_id != profile_id:
        raise PhysicalCandidateGateError("physical baseline bundle profile mismatch")
    if physical.ready_for_candidate_instantiation is not True or physical.baseline_matches_exact_stock_ota is not True:
        raise PhysicalCandidateGateError("physical baseline bundle is not ready for candidate instantiation")
    if physical.temporary_boot_authorized is not False:
        raise PhysicalCandidateGateError("physical baseline bundle must not itself authorize temporary boot")
    if physical.hardware_verified is not False or physical.beta_gate_credit is not False:
        raise PhysicalCandidateGateError("physical baseline bundle cannot claim hardware/Beta credit")

    if not isinstance(manifest, FirstBootCandidateManifest) or manifest.schema_version != 8:
        raise PhysicalCandidateGateError("first-boot candidate must be schema v8 typed evidence")
    if manifest.profile_id != profile_id:
        raise PhysicalCandidateGateError("first-boot candidate profile mismatch")
    if manifest.device_serial != physical.device_serial:
        raise PhysicalCandidateGateError("candidate serial is detached from physical baseline")
    if manifest.firmware_build != physical.firmware_build or manifest.firmware_fingerprint != physical.firmware_fingerprint:
        raise PhysicalCandidateGateError("candidate firmware is detached from physical baseline")
    if manifest.fastboot_baseline_sha256 != physical.fastboot_baseline_evidence_sha256:
        raise PhysicalCandidateGateError("candidate Fastboot baseline digest is detached from physical bundle")

    if not isinstance(authorities, FirstBootAuthorityBundleEvidence) or authorities.schema_version != 1:
        raise PhysicalCandidateGateError("first-boot authority bundle must be schema v1 typed evidence")
    manifest_sha = _sha(manifest.manifest_sha256(), "first-boot manifest SHA-256")
    if authorities.profile_id != profile_id or authorities.first_boot_manifest_sha256 != manifest_sha:
        raise PhysicalCandidateGateError("authority bundle is detached from exact first-boot manifest")
    if authorities.all_authorities_reviewed is not True or authorities.all_required_artifacts_strict is not True:
        raise PhysicalCandidateGateError("authority bundle is not reviewed/strict")
    if authorities.hardware_verified is not False or authorities.beta_gate_credit is not False:
        raise PhysicalCandidateGateError("authority bundle cannot claim hardware/Beta credit")

    if not isinstance(boot, TemporaryBootAuthorization) or boot.schema_version != 2:
        raise PhysicalCandidateGateError("temporary-boot authorization must be schema v2 typed evidence")
    if boot.profile_id != profile_id or boot.device_serial != physical.device_serial:
        raise PhysicalCandidateGateError("temporary-boot authorization identity mismatch")
    if boot.fastboot_baseline_sha256 != physical.fastboot_baseline_evidence_sha256:
        raise PhysicalCandidateGateError("temporary-boot authorization baseline mismatch")
    if boot.firmware_build != physical.firmware_build or boot.firmware_fingerprint != physical.firmware_fingerprint:
        raise PhysicalCandidateGateError("temporary-boot authorization firmware mismatch")
    if boot.stock_ota_sha256 != physical.stock_ota_sha256 or boot.stock_boot_sha256 != physical.stock_boot_sha256:
        raise PhysicalCandidateGateError("temporary-boot authorization stock provenance mismatch")
    if boot.reproducible is not True or boot.structurally_verified is not True:
        raise PhysicalCandidateGateError("temporary-boot authorization is not reproducible/structurally verified")

    if not isinstance(boot_plan, BootBuildPlan) or boot_plan.schema_version != 1:
        raise PhysicalCandidateGateError("boot build plan must be schema v1 typed evidence")
    try:
        contract = boot_build_contract(profile)
    except BootImageError as exc:
        raise PhysicalCandidateGateError(str(exc)) from exc
    if boot_plan.profile_id != profile_id:
        raise PhysicalCandidateGateError("boot plan profile mismatch")
    if (
        boot_plan.header_version != contract.header_version
        or boot_plan.page_size != contract.page_size
        or boot_plan.ramdisk_compression != contract.ramdisk_compression
        or boot_plan.kernel_cmdline != contract.kernel_cmdline
    ):
        raise PhysicalCandidateGateError("boot plan no longer matches selected profile boot contract")
    if physical.stock_boot_header_version != contract.header_version:
        raise PhysicalCandidateGateError("physical stock boot header does not match selected profile")
    if boot.image_size > contract.boot_partition_limit:
        raise PhysicalCandidateGateError("candidate boot image exceeds profile partition limit")

    plan_sha = _sha(boot_plan.plan_sha256(), "boot plan SHA-256")
    if boot.plan_sha256 != plan_sha or manifest.boot_plan_sha256 != plan_sha:
        raise PhysicalCandidateGateError("boot plan is detached from candidate/authorization")
    if boot_plan.stock_ota_sha256 != physical.stock_ota_sha256 or boot_plan.stock_boot_sha256 != physical.stock_boot_sha256:
        raise PhysicalCandidateGateError("boot plan stock provenance mismatch")

    expected_names = ["kernel", "ramdisk"]
    if contract.include_dtb:
        expected_names.append("dtb")
    if contract.separate_dtbo:
        expected_names.append("dtbo")
    if [item.name for item in boot_plan.inputs] != expected_names:
        raise PhysicalCandidateGateError("boot plan input set/order does not match selected profile")
    for item in boot_plan.inputs:
        if Path(item.path).name != item.path or item.path in {"", ".", ".."}:
            raise PhysicalCandidateGateError(f"unsafe boot plan input path: {item.name}")
        _positive(item.size, f"boot plan {item.name} size")
        _sha(item.sha256, f"boot plan {item.name} SHA-256")

    if manifest.boot_authorization_sha256 != boot.authorization_sha256():
        raise PhysicalCandidateGateError("candidate temporary-boot authorization digest drifted")
    if manifest.boot_image_sha256 != boot.image_sha256 or manifest.boot_image_size != boot.image_size:
        raise PhysicalCandidateGateError("candidate boot image differs from temporary-boot authorization")

    kernel = _plan_input(boot_plan, "kernel", required=True)
    ramdisk = _plan_input(boot_plan, "ramdisk", required=True)
    if ramdisk is None:
        raise PhysicalCandidateGateError("boot plan lacks required ramdisk")
    if kernel.sha256 != manifest.kernel_image_sha256 or kernel.size != manifest.kernel_image_size:
        raise PhysicalCandidateGateError("boot plan kernel input differs from reviewed candidate kernel")

    if contract.include_dtb != (manifest.dtb_sha256 is not None):
        raise PhysicalCandidateGateError("candidate DTB presence does not match selected profile")
    dtb = _plan_input(boot_plan, "dtb", required=contract.include_dtb)
    if contract.include_dtb:
        if (
            dtb is None
            or manifest.dtb_size is None
            or dtb.sha256 != manifest.dtb_sha256
            or dtb.size != manifest.dtb_size
        ):
            raise PhysicalCandidateGateError("boot plan DTB differs from reviewed candidate DTB")

    if contract.separate_dtbo != (manifest.dtbo_sha256 is not None):
        raise PhysicalCandidateGateError("candidate DTBO presence does not match selected profile")
    dtbo = _plan_input(boot_plan, "dtbo", required=contract.separate_dtbo)
    if contract.separate_dtbo:
        if (
            dtbo is None
            or manifest.dtbo_size is None
            or dtbo.sha256 != manifest.dtbo_sha256
            or dtbo.size != manifest.dtbo_size
        ):
            raise PhysicalCandidateGateError("boot plan DTBO differs from reviewed candidate DTBO")

    for observed, expected, label in (
        (authorities.kernel_image_sha256, manifest.kernel_image_sha256, "kernel Image"),
        (authorities.rootfs_artifact_sha256, manifest.rootfs_artifact_sha256, "rootfs artifact"),
        (authorities.dtb_sha256, manifest.dtb_sha256, "DTB"),
        (authorities.dtbo_image_sha256, manifest.dtbo_sha256, "DTBO image"),
    ):
        if observed != expected:
            raise PhysicalCandidateGateError(f"authority bundle {label} differs from candidate")

    for value, label in (
        (physical.evidence_sha256(), "physical baseline bundle SHA-256"),
        (physical.fastboot_capture_bundle_sha256, "Fastboot capture bundle SHA-256"),
        (physical.fastboot_baseline_evidence_sha256, "Fastboot baseline evidence SHA-256"),
        (physical.fastboot_transcript_sha256, "Fastboot transcript SHA-256"),
        (physical.stock_provenance_sha256, "stock provenance SHA-256"),
        (physical.stock_ota_sha256, "stock OTA SHA-256"),
        (physical.stock_boot_sha256, "stock boot SHA-256"),
        (authorities.evidence_sha256(), "first-boot authority bundle SHA-256"),
        (boot.authorization_sha256(), "temporary-boot authorization SHA-256"),
        (boot.image_sha256, "boot image SHA-256"),
        (manifest.kernel_image_sha256, "kernel Image SHA-256"),
        (manifest.rootfs_artifact_sha256, "rootfs artifact SHA-256"),
    ):
        _sha(value, label)
    if manifest.dtb_sha256 is not None:
        _sha(manifest.dtb_sha256, "DTB SHA-256")
    if manifest.dtbo_sha256 is not None:
        _sha(manifest.dtbo_sha256, "DTBO SHA-256")
    _positive(boot.image_size, "boot image size")

    return PhysicalCandidateGateEvidence(
        schema_version=1,
        profile_id=profile_id,
        device_serial=_text(physical.device_serial, "device serial"),
        firmware_build=_text(physical.firmware_build, "firmware build"),
        firmware_fingerprint=_text(physical.firmware_fingerprint, "firmware fingerprint"),
        physical_baseline_bundle_sha256=physical.evidence_sha256(),
        fastboot_capture_bundle_sha256=physical.fastboot_capture_bundle_sha256,
        fastboot_baseline_evidence_sha256=physical.fastboot_baseline_evidence_sha256,
        fastboot_transcript_sha256=physical.fastboot_transcript_sha256,
        stock_provenance_sha256=physical.stock_provenance_sha256,
        stock_ota_sha256=physical.stock_ota_sha256,
        stock_boot_sha256=physical.stock_boot_sha256,
        first_boot_manifest_sha256=manifest_sha,
        first_boot_authority_bundle_sha256=authorities.evidence_sha256(),
        boot_authorization_sha256=boot.authorization_sha256(),
        boot_plan_sha256=plan_sha,
        boot_image_sha256=boot.image_sha256,
        boot_image_size=boot.image_size,
        kernel_image_sha256=manifest.kernel_image_sha256,
        rootfs_artifact_sha256=manifest.rootfs_artifact_sha256,
        dtb_sha256=manifest.dtb_sha256,
        dtbo_image_sha256=manifest.dtbo_sha256,
        reviewed_authorities_bound=True,
        exact_physical_baseline_bound=True,
        ready_for_temporary_boot_offer=True,
    )


def verify_physical_candidate_gate(
    evidence: PhysicalCandidateGateEvidence,
    profile: DeviceProfile,
    physical: PhysicalBaselineBundleEvidence,
    manifest: FirstBootCandidateManifest,
    authorities: FirstBootAuthorityBundleEvidence,
    boot: TemporaryBootAuthorization,
    boot_plan: BootBuildPlan,
) -> None:
    expected = bind_physical_candidate_gate(profile, physical, manifest, authorities, boot, boot_plan)
    if evidence != expected:
        raise PhysicalCandidateGateError("physical candidate gate does not match exact inputs")


def write_physical_candidate_gate(evidence: PhysicalCandidateGateEvidence, destination: Path) -> str:
    if not isinstance(evidence, PhysicalCandidateGateEvidence) or evidence.schema_version != 1:
        raise PhysicalCandidateGateError("invalid physical candidate gate evidence")
    if evidence.ready_for_temporary_boot_offer is not True:
        raise PhysicalCandidateGateError("physical candidate gate is not ready for temporary-boot offer")
    if evidence.temporary_boot_executed is not False or evidence.phone_storage_written is not False:
        raise PhysicalCandidateGateError("host gate cannot record device execution/writes")
    if evidence.hardware_verified is not False or evidence.beta_gate_credit is not False:
        raise PhysicalCandidateGateError("host gate cannot claim hardware/Beta credit")
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise PhysicalCandidateGateError(f"refusing to overwrite physical candidate gate: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise PhysicalCandidateGateError("refusing stale physical candidate gate temporary path")
    try:
        temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()
