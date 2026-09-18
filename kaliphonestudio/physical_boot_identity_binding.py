"""Fail-closed exact-byte binding for stock and candidate boot-chain identities.

This module closes a host-side provenance gap between the exact stock OTA/boot
record and the already reviewed physical candidate gate.  It re-inspects the
exact stock and candidate boot image bytes, binds per-component identities and
optional AVB footer/vbmeta layout, and re-hashes the external DTBO when the
selected profile requires one.

It performs no ADB/Fastboot operation, never writes phone storage and never
claims that a candidate booted on real hardware.  A successful binding only
means that the immutable host-side evidence refers to the same exact bytes.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re

from .boot_builder import BootBuildPlan
from .boot_image import (
    BootImageError,
    BootImageReport,
    boot_build_contract,
    inspect_boot_image,
    require_stock_candidate_pair,
)
from .physical_baseline_bundle import PhysicalBaselineBundleEvidence
from .physical_candidate_gate import PhysicalCandidateGateEvidence
from .profiles import DeviceProfile
from .provenance import StockBootProvenance


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PhysicalBootIdentityBindingError(ValueError):
    pass


@dataclass(frozen=True)
class PhysicalBootIdentityBindingEvidence:
    schema_version: int
    profile_id: str
    device_serial: str
    physical_baseline_bundle_sha256: str
    physical_candidate_gate_sha256: str
    stock_provenance_sha256: str
    boot_plan_sha256: str

    stock_boot_sha256: str
    stock_boot_size: int
    stock_boot_header_version: int
    stock_kernel_sha256: str
    stock_kernel_size: int
    stock_ramdisk_sha256: str
    stock_ramdisk_size: int
    stock_second_sha256: str | None
    stock_second_size: int
    stock_recovery_dtbo_sha256: str | None
    stock_recovery_dtbo_size: int
    stock_dtb_sha256: str | None
    stock_dtb_size: int | None
    stock_avb_footer_present: bool
    stock_avb_footer_version_major: int | None
    stock_avb_footer_version_minor: int | None
    stock_avb_original_image_size: int | None
    stock_avb_vbmeta_offset: int | None
    stock_avb_vbmeta_size: int | None
    stock_avb_vbmeta_sha256: str | None

    candidate_boot_sha256: str
    candidate_boot_size: int
    candidate_boot_header_version: int
    candidate_kernel_sha256: str
    candidate_kernel_size: int
    candidate_ramdisk_sha256: str
    candidate_ramdisk_size: int
    candidate_second_sha256: str | None
    candidate_second_size: int
    candidate_recovery_dtbo_sha256: str | None
    candidate_recovery_dtbo_size: int
    candidate_dtb_sha256: str | None
    candidate_dtb_size: int | None
    candidate_external_dtbo_sha256: str | None
    candidate_external_dtbo_size: int | None
    candidate_avb_footer_present: bool
    candidate_avb_footer_version_major: int | None
    candidate_avb_footer_version_minor: int | None
    candidate_avb_original_image_size: int | None
    candidate_avb_vbmeta_offset: int | None
    candidate_avb_vbmeta_size: int | None
    candidate_avb_vbmeta_sha256: str | None

    stock_exact_bytes_verified: bool
    candidate_exact_bytes_verified: bool
    component_identity_bound: bool
    avb_layout_bound: bool
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
        raise PhysicalBootIdentityBindingError(f"{label} must be a lowercase SHA-256")
    return value


def _positive(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PhysicalBootIdentityBindingError(f"{label} must be a positive integer")
    return value


def _nonnegative(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise PhysicalBootIdentityBindingError(f"{label} must be a non-negative integer")
    return value


def _regular_file(path: Path, label: str) -> Path:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise PhysicalBootIdentityBindingError(f"{label} must be a regular non-symlink file: {candidate}")
    return candidate


def _stable_boot_report(path: Path, profile: DeviceProfile, label: str) -> BootImageReport:
    candidate = _regular_file(path, label)
    before = candidate.stat()
    try:
        report = inspect_boot_image(candidate, profile)
    except BootImageError as exc:
        raise PhysicalBootIdentityBindingError(f"{label} preflight failed: {exc}") from exc
    after = candidate.stat()
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or before.st_ino != after.st_ino
    ):
        raise PhysicalBootIdentityBindingError(f"{label} changed while being inspected")
    return report


def _stable_file_identity(path: Path, label: str) -> tuple[str, int]:
    candidate = _regular_file(path, label)
    before = candidate.stat()
    digest = sha256()
    with candidate.open("rb") as fh:
        while chunk := fh.read(1024 * 1024):
            digest.update(chunk)
    after = candidate.stat()
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or before.st_ino != after.st_ino
    ):
        raise PhysicalBootIdentityBindingError(f"{label} changed while being hashed")
    if after.st_size <= 0:
        raise PhysicalBootIdentityBindingError(f"{label} is empty")
    return digest.hexdigest(), after.st_size


def _required_component(report: BootImageReport, name: str, label: str) -> tuple[str, int]:
    digest = getattr(report, f"{name}_sha256")
    size = getattr(report, f"{name}_size")
    return _sha(digest, f"{label} {name} SHA-256"), _positive(size, f"{label} {name} size")


def _optional_component(report: BootImageReport, name: str, label: str) -> tuple[str | None, int]:
    digest = getattr(report, f"{name}_sha256")
    size = getattr(report, f"{name}_size")
    if size is None:
        if digest is not None:
            raise PhysicalBootIdentityBindingError(f"{label} {name} hash exists without a size")
        return None, 0
    size_int = _nonnegative(size, f"{label} {name} size")
    if size_int == 0:
        if digest is not None:
            raise PhysicalBootIdentityBindingError(f"{label} {name} hash exists for an empty component")
        return None, 0
    return _sha(digest, f"{label} {name} SHA-256"), size_int


def _optional_dtb(report: BootImageReport, *, required: bool, label: str) -> tuple[str | None, int | None]:
    digest = report.dtb_sha256
    size = report.dtb_size
    if required:
        return _sha(digest, f"{label} DTB SHA-256"), _positive(size, f"{label} DTB size")
    if digest is not None or size not in {None, 0}:
        raise PhysicalBootIdentityBindingError(f"{label} unexpectedly contains an in-boot DTB")
    return None, None


def _avb_identity(report: BootImageReport, label: str) -> dict[str, object]:
    if not report.avb_footer_present:
        values = (
            report.avb_footer_version_major,
            report.avb_footer_version_minor,
            report.avb_original_image_size,
            report.avb_vbmeta_offset,
            report.avb_vbmeta_size,
            report.avb_vbmeta_sha256,
            report.avb_vbmeta_header_valid,
        )
        if any(value is not None for value in values) or report.avb_structural_errors:
            raise PhysicalBootIdentityBindingError(f"{label} has inconsistent absent-AVB evidence")
        return {
            "footer_present": False,
            "footer_version_major": None,
            "footer_version_minor": None,
            "original_image_size": None,
            "vbmeta_offset": None,
            "vbmeta_size": None,
            "vbmeta_sha256": None,
        }

    if report.avb_structural_errors:
        raise PhysicalBootIdentityBindingError(
            f"{label} AVB layout is invalid: {'; '.join(report.avb_structural_errors)}"
        )
    if report.avb_vbmeta_header_valid is not True:
        raise PhysicalBootIdentityBindingError(f"{label} AVB vbmeta header is not structurally valid")
    return {
        "footer_present": True,
        "footer_version_major": _nonnegative(report.avb_footer_version_major, f"{label} AVB major version"),
        "footer_version_minor": _nonnegative(report.avb_footer_version_minor, f"{label} AVB minor version"),
        "original_image_size": _positive(report.avb_original_image_size, f"{label} AVB original image size"),
        "vbmeta_offset": _positive(report.avb_vbmeta_offset, f"{label} AVB vbmeta offset"),
        "vbmeta_size": _positive(report.avb_vbmeta_size, f"{label} AVB vbmeta size"),
        "vbmeta_sha256": _sha(report.avb_vbmeta_sha256, f"{label} AVB vbmeta SHA-256"),
    }


def _plan_input(plan: BootBuildPlan, name: str, *, required: bool):
    matches = [item for item in plan.inputs if item.name == name]
    if required and len(matches) != 1:
        raise PhysicalBootIdentityBindingError(f"boot plan must contain exactly one {name} input")
    if not required and len(matches) > 1:
        raise PhysicalBootIdentityBindingError(f"boot plan contains duplicate {name} inputs")
    return matches[0] if matches else None


def _require_plan_component(plan: BootBuildPlan, report: BootImageReport, name: str, label: str) -> tuple[str, int]:
    planned = _plan_input(plan, name, required=True)
    observed_sha, observed_size = _required_component(report, name, label)
    if planned.sha256 != observed_sha or planned.size != observed_size:
        raise PhysicalBootIdentityBindingError(f"{label} {name} bytes differ from exact boot plan input")
    return observed_sha, observed_size


def bind_physical_boot_identity(
    profile: DeviceProfile,
    physical: PhysicalBaselineBundleEvidence,
    gate: PhysicalCandidateGateEvidence,
    provenance: StockBootProvenance,
    boot_plan: BootBuildPlan,
    *,
    stock_boot: Path,
    candidate_boot: Path,
    candidate_dtbo: Path | None = None,
) -> PhysicalBootIdentityBindingEvidence:
    """Bind exact stock/candidate bytes to the reviewed physical candidate chain."""
    profile_id = getattr(profile, "profile_id", None)
    if not isinstance(profile_id, str) or not profile_id.strip():
        raise PhysicalBootIdentityBindingError("selected profile has invalid profile_id")

    if not isinstance(physical, PhysicalBaselineBundleEvidence) or physical.schema_version != 1:
        raise PhysicalBootIdentityBindingError("physical baseline bundle must be schema-v1 typed evidence")
    if physical.profile_id != profile_id:
        raise PhysicalBootIdentityBindingError("physical baseline bundle profile mismatch")
    if physical.ready_for_candidate_instantiation is not True or physical.baseline_matches_exact_stock_ota is not True:
        raise PhysicalBootIdentityBindingError("physical baseline bundle is not exact-stock ready")
    if physical.temporary_boot_authorized is not False:
        raise PhysicalBootIdentityBindingError("physical baseline bundle must not authorize temporary boot")
    if physical.hardware_verified is not False or physical.beta_gate_credit is not False:
        raise PhysicalBootIdentityBindingError("physical baseline bundle cannot claim hardware/Beta credit")

    if not isinstance(gate, PhysicalCandidateGateEvidence) or gate.schema_version != 1:
        raise PhysicalBootIdentityBindingError("physical candidate gate must be schema-v1 typed evidence")
    if gate.profile_id != profile_id or gate.device_serial != physical.device_serial:
        raise PhysicalBootIdentityBindingError("physical candidate gate identity mismatch")
    if gate.physical_baseline_bundle_sha256 != physical.evidence_sha256():
        raise PhysicalBootIdentityBindingError("physical candidate gate is detached from exact baseline bundle")
    if gate.ready_for_temporary_boot_offer is not True or gate.exact_physical_baseline_bound is not True:
        raise PhysicalBootIdentityBindingError("physical candidate gate is not ready/exact-baseline-bound")
    if gate.temporary_boot_executed is not False or gate.phone_storage_written is not False:
        raise PhysicalBootIdentityBindingError("physical candidate gate already records execution/write state")
    if gate.hardware_verified is not False or gate.beta_gate_credit is not False:
        raise PhysicalBootIdentityBindingError("physical candidate gate cannot claim hardware/Beta credit")

    if not isinstance(provenance, StockBootProvenance) or provenance.schema_version != 1:
        raise PhysicalBootIdentityBindingError("stock provenance must be schema-v1 typed evidence")
    provenance_sha = _sha(provenance.evidence_sha256(), "stock provenance SHA-256")
    if provenance.profile_id != profile_id:
        raise PhysicalBootIdentityBindingError("stock provenance profile mismatch")
    if physical.stock_provenance_sha256 != provenance_sha or gate.stock_provenance_sha256 != provenance_sha:
        raise PhysicalBootIdentityBindingError("stock provenance digest is detached from physical candidate chain")
    if physical.stock_boot_sha256 != provenance.boot_sha256 or gate.stock_boot_sha256 != provenance.boot_sha256:
        raise PhysicalBootIdentityBindingError("stock boot digest drifted across provenance/baseline/gate")
    if physical.stock_boot_size != provenance.boot_size:
        raise PhysicalBootIdentityBindingError("stock boot size drifted across provenance/baseline")
    if physical.stock_boot_header_version != provenance.boot_header_version:
        raise PhysicalBootIdentityBindingError("stock boot header version drifted across provenance/baseline")

    if not isinstance(boot_plan, BootBuildPlan) or boot_plan.schema_version != 1:
        raise PhysicalBootIdentityBindingError("boot plan must be schema-v1 typed evidence")
    contract = boot_build_contract(profile)
    plan_sha = _sha(boot_plan.plan_sha256(), "boot plan SHA-256")
    if boot_plan.profile_id != profile_id or gate.boot_plan_sha256 != plan_sha:
        raise PhysicalBootIdentityBindingError("boot plan is detached from selected profile/candidate gate")
    if boot_plan.stock_boot_sha256 != provenance.boot_sha256 or boot_plan.stock_ota_sha256 != provenance.ota_sha256:
        raise PhysicalBootIdentityBindingError("boot plan stock provenance drifted")
    if boot_plan.header_version != contract.header_version or boot_plan.page_size != contract.page_size:
        raise PhysicalBootIdentityBindingError("boot plan layout no longer matches selected profile")

    stock_report = _stable_boot_report(stock_boot, profile, "stock boot image")
    candidate_report = _stable_boot_report(candidate_boot, profile, "candidate boot image")
    try:
        require_stock_candidate_pair(stock_report, candidate_report, profile)
    except BootImageError as exc:
        raise PhysicalBootIdentityBindingError(str(exc)) from exc

    if stock_report.sha256 != provenance.boot_sha256 or stock_report.size != provenance.boot_size:
        raise PhysicalBootIdentityBindingError("exact stock boot bytes do not match immutable provenance")
    if stock_report.header_version != provenance.boot_header_version:
        raise PhysicalBootIdentityBindingError("exact stock boot header version does not match immutable provenance")
    if candidate_report.sha256 != gate.boot_image_sha256 or candidate_report.size != gate.boot_image_size:
        raise PhysicalBootIdentityBindingError("exact candidate boot bytes do not match physical candidate gate")

    stock_kernel_sha, stock_kernel_size = _required_component(stock_report, "kernel", "stock boot")
    stock_ramdisk_sha, stock_ramdisk_size = _required_component(stock_report, "ramdisk", "stock boot")
    stock_second_sha, stock_second_size = _optional_component(stock_report, "second", "stock boot")
    stock_recovery_sha, stock_recovery_size = _optional_component(stock_report, "recovery_dtbo", "stock boot")
    stock_dtb_sha, stock_dtb_size = _optional_dtb(stock_report, required=contract.include_dtb, label="stock boot")

    candidate_kernel_sha, candidate_kernel_size = _require_plan_component(
        boot_plan, candidate_report, "kernel", "candidate boot"
    )
    candidate_ramdisk_sha, candidate_ramdisk_size = _require_plan_component(
        boot_plan, candidate_report, "ramdisk", "candidate boot"
    )
    candidate_second_sha, candidate_second_size = _optional_component(candidate_report, "second", "candidate boot")
    candidate_recovery_sha, candidate_recovery_size = _optional_component(
        candidate_report, "recovery_dtbo", "candidate boot"
    )

    planned_dtb = _plan_input(boot_plan, "dtb", required=contract.include_dtb)
    candidate_dtb_sha, candidate_dtb_size = _optional_dtb(
        candidate_report, required=contract.include_dtb, label="candidate boot"
    )
    if contract.include_dtb:
        assert planned_dtb is not None
        if planned_dtb.sha256 != candidate_dtb_sha or planned_dtb.size != candidate_dtb_size:
            raise PhysicalBootIdentityBindingError("candidate boot DTB bytes differ from exact boot plan input")
        if gate.dtb_sha256 != candidate_dtb_sha:
            raise PhysicalBootIdentityBindingError("candidate embedded DTB differs from reviewed physical gate")
    elif gate.dtb_sha256 is not None:
        raise PhysicalBootIdentityBindingError("physical candidate gate unexpectedly carries an in-boot DTB")

    if gate.kernel_image_sha256 != candidate_kernel_sha:
        raise PhysicalBootIdentityBindingError("candidate embedded kernel differs from reviewed physical gate")

    planned_dtbo = _plan_input(boot_plan, "dtbo", required=contract.separate_dtbo)
    candidate_dtbo_sha: str | None = None
    candidate_dtbo_size: int | None = None
    if contract.separate_dtbo:
        if candidate_dtbo is None:
            raise PhysicalBootIdentityBindingError("selected profile requires the exact external candidate DTBO file")
        assert planned_dtbo is not None
        candidate_dtbo_sha, candidate_dtbo_size = _stable_file_identity(candidate_dtbo, "candidate DTBO")
        if planned_dtbo.sha256 != candidate_dtbo_sha or planned_dtbo.size != candidate_dtbo_size:
            raise PhysicalBootIdentityBindingError("exact candidate DTBO bytes differ from boot plan input")
        if gate.dtbo_image_sha256 != candidate_dtbo_sha:
            raise PhysicalBootIdentityBindingError("exact candidate DTBO differs from reviewed physical gate")
    else:
        if candidate_dtbo is not None:
            raise PhysicalBootIdentityBindingError("selected profile does not permit an external candidate DTBO")
        if gate.dtbo_image_sha256 is not None:
            raise PhysicalBootIdentityBindingError("physical candidate gate unexpectedly carries an external DTBO")

    stock_avb = _avb_identity(stock_report, "stock boot")
    candidate_avb = _avb_identity(candidate_report, "candidate boot")

    return PhysicalBootIdentityBindingEvidence(
        schema_version=1,
        profile_id=profile_id,
        device_serial=physical.device_serial,
        physical_baseline_bundle_sha256=physical.evidence_sha256(),
        physical_candidate_gate_sha256=gate.evidence_sha256(),
        stock_provenance_sha256=provenance_sha,
        boot_plan_sha256=plan_sha,
        stock_boot_sha256=stock_report.sha256,
        stock_boot_size=stock_report.size,
        stock_boot_header_version=_nonnegative(stock_report.header_version, "stock boot header version"),
        stock_kernel_sha256=stock_kernel_sha,
        stock_kernel_size=stock_kernel_size,
        stock_ramdisk_sha256=stock_ramdisk_sha,
        stock_ramdisk_size=stock_ramdisk_size,
        stock_second_sha256=stock_second_sha,
        stock_second_size=stock_second_size,
        stock_recovery_dtbo_sha256=stock_recovery_sha,
        stock_recovery_dtbo_size=stock_recovery_size,
        stock_dtb_sha256=stock_dtb_sha,
        stock_dtb_size=stock_dtb_size,
        stock_avb_footer_present=bool(stock_avb["footer_present"]),
        stock_avb_footer_version_major=stock_avb["footer_version_major"],
        stock_avb_footer_version_minor=stock_avb["footer_version_minor"],
        stock_avb_original_image_size=stock_avb["original_image_size"],
        stock_avb_vbmeta_offset=stock_avb["vbmeta_offset"],
        stock_avb_vbmeta_size=stock_avb["vbmeta_size"],
        stock_avb_vbmeta_sha256=stock_avb["vbmeta_sha256"],
        candidate_boot_sha256=candidate_report.sha256,
        candidate_boot_size=candidate_report.size,
        candidate_boot_header_version=_nonnegative(candidate_report.header_version, "candidate boot header version"),
        candidate_kernel_sha256=candidate_kernel_sha,
        candidate_kernel_size=candidate_kernel_size,
        candidate_ramdisk_sha256=candidate_ramdisk_sha,
        candidate_ramdisk_size=candidate_ramdisk_size,
        candidate_second_sha256=candidate_second_sha,
        candidate_second_size=candidate_second_size,
        candidate_recovery_dtbo_sha256=candidate_recovery_sha,
        candidate_recovery_dtbo_size=candidate_recovery_size,
        candidate_dtb_sha256=candidate_dtb_sha,
        candidate_dtb_size=candidate_dtb_size,
        candidate_external_dtbo_sha256=candidate_dtbo_sha,
        candidate_external_dtbo_size=candidate_dtbo_size,
        candidate_avb_footer_present=bool(candidate_avb["footer_present"]),
        candidate_avb_footer_version_major=candidate_avb["footer_version_major"],
        candidate_avb_footer_version_minor=candidate_avb["footer_version_minor"],
        candidate_avb_original_image_size=candidate_avb["original_image_size"],
        candidate_avb_vbmeta_offset=candidate_avb["vbmeta_offset"],
        candidate_avb_vbmeta_size=candidate_avb["vbmeta_size"],
        candidate_avb_vbmeta_sha256=candidate_avb["vbmeta_sha256"],
        stock_exact_bytes_verified=True,
        candidate_exact_bytes_verified=True,
        component_identity_bound=True,
        avb_layout_bound=True,
        temporary_boot_executed=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def verify_physical_boot_identity_binding(
    evidence: PhysicalBootIdentityBindingEvidence,
    profile: DeviceProfile,
    physical: PhysicalBaselineBundleEvidence,
    gate: PhysicalCandidateGateEvidence,
    provenance: StockBootProvenance,
    boot_plan: BootBuildPlan,
    *,
    stock_boot: Path,
    candidate_boot: Path,
    candidate_dtbo: Path | None = None,
) -> None:
    expected = bind_physical_boot_identity(
        profile,
        physical,
        gate,
        provenance,
        boot_plan,
        stock_boot=stock_boot,
        candidate_boot=candidate_boot,
        candidate_dtbo=candidate_dtbo,
    )
    if evidence != expected:
        raise PhysicalBootIdentityBindingError("physical boot identity binding does not match exact inputs")


def write_physical_boot_identity_binding(
    evidence: PhysicalBootIdentityBindingEvidence,
    destination: Path,
) -> str:
    if not isinstance(evidence, PhysicalBootIdentityBindingEvidence) or evidence.schema_version != 1:
        raise PhysicalBootIdentityBindingError("invalid physical boot identity binding evidence")
    if (
        evidence.stock_exact_bytes_verified is not True
        or evidence.candidate_exact_bytes_verified is not True
        or evidence.component_identity_bound is not True
        or evidence.avb_layout_bound is not True
    ):
        raise PhysicalBootIdentityBindingError("physical boot identity binding is incomplete")
    if evidence.temporary_boot_executed is not False or evidence.phone_storage_written is not False:
        raise PhysicalBootIdentityBindingError("host identity binding cannot record device execution/writes")
    if evidence.hardware_verified is not False or evidence.beta_gate_credit is not False:
        raise PhysicalBootIdentityBindingError("host identity binding cannot claim hardware/Beta credit")

    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise PhysicalBootIdentityBindingError(f"refusing to overwrite physical boot identity binding: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise PhysicalBootIdentityBindingError("refusing stale physical boot identity temporary path")
    try:
        temporary.write_bytes(evidence.canonical_json().encode("utf-8"))
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()
