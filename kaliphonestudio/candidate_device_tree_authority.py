"""Bind a schema-v8 first-boot candidate to one reviewed DTB/DTBO authority.

The binding also consumes the candidate's reviewed kernel-authority link so a DT
authority cannot silently be detached from the exact kernel authority that built
it. This remains host-only provenance and grants no physical/Beta credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re

from .candidate import FirstBootCandidateManifest
from .candidate_kernel_authority import FirstBootKernelAuthorityEvidence
from .device_tree import DeviceTreeError
from .device_tree_authority import DeviceTreeAuthorityRecord, authority_from_dict
from .device_tree_build import DeviceTreeBuildPlan


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class FirstBootDeviceTreeAuthorityEvidence:
    schema_version: int
    profile_id: str
    first_boot_manifest_sha256: str
    device_tree_authority_sha256: str
    device_tree_plan_sha256: str
    kernel_authority_sha256: str
    authority_name: str
    authority_run_id: int
    authority_commit: str
    authority_artifact_id: int
    format_lock_sha256: str
    dtb_sha256: str
    dtb_size: int
    raw_dtbo: tuple[tuple[str, str, int], ...]
    dtbo_image_sha256: str
    dtbo_image_size: int
    dtbo_entry_count: int
    strict_byte_identical: bool
    distinct_build_roots_verified: bool
    reviewed: bool
    hardware_verified: bool = False
    beta_gate_credit: bool = False

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise DeviceTreeError(f"{label} must be a lowercase SHA-256 digest")
    return value


def bind_first_boot_candidate_to_device_tree_authority(
    manifest: FirstBootCandidateManifest,
    plan: DeviceTreeBuildPlan,
    authority: DeviceTreeAuthorityRecord,
    kernel_authority_binding: FirstBootKernelAuthorityEvidence,
) -> FirstBootDeviceTreeAuthorityEvidence:
    if not isinstance(manifest, FirstBootCandidateManifest) or manifest.schema_version != 8:
        raise DeviceTreeError("device-tree authority binding requires a schema-v8 first-boot manifest")
    if not isinstance(plan, DeviceTreeBuildPlan) or plan.schema_version != 1:
        raise DeviceTreeError("device-tree authority binding requires a schema-v1 DT build plan")
    authority = authority_from_dict(asdict(authority))
    if not isinstance(kernel_authority_binding, FirstBootKernelAuthorityEvidence) or kernel_authority_binding.schema_version != 1:
        raise DeviceTreeError("device-tree authority binding requires typed kernel-authority candidate evidence")

    manifest_digest = _digest(manifest.manifest_sha256(), "first-boot manifest")
    if authority.profile_id != manifest.profile_id or plan.profile_id != manifest.profile_id:
        raise DeviceTreeError("device-tree authority profile does not match first-boot candidate")
    if authority.device_tree_plan_sha256 != plan.plan_sha256():
        raise DeviceTreeError("device-tree authority is detached from supplied DT build plan")
    if authority.kernel_authority_sha256 != plan.kernel_authority_sha256:
        raise DeviceTreeError("device-tree authority is detached from DT plan kernel authority")

    if kernel_authority_binding.profile_id != manifest.profile_id:
        raise DeviceTreeError("kernel-authority candidate binding profile drifted")
    if kernel_authority_binding.first_boot_manifest_sha256 != manifest_digest:
        raise DeviceTreeError("kernel-authority candidate binding is detached from first-boot manifest")
    if kernel_authority_binding.kernel_authority_sha256 != authority.kernel_authority_sha256:
        raise DeviceTreeError("DT and candidate kernel authorities do not match")
    if kernel_authority_binding.reviewed is not True:
        raise DeviceTreeError("candidate kernel authority is not reviewed")
    if kernel_authority_binding.hardware_verified is not False or kernel_authority_binding.beta_gate_credit is not False:
        raise DeviceTreeError("host kernel-authority candidate evidence cannot claim hardware/Beta credit")

    if _digest(manifest.device_tree_format_lock_sha256, "candidate device-tree format lock") != plan.format_lock_sha256:
        raise DeviceTreeError("device-tree authority binding mismatch: format lock")
    if manifest.dtb_sha256 is None or manifest.dtb_size is None:
        raise DeviceTreeError("first-boot candidate has no DTB artifact")
    if manifest.dtbo_sha256 is None or manifest.dtbo_size is None or manifest.dtbo_entry_count is None:
        raise DeviceTreeError("first-boot candidate has no DTBO artifact")
    _digest(manifest.dtb_sha256, "candidate DTB")
    _digest(manifest.dtbo_sha256, "candidate DTBO")
    if manifest.dtb_sha256 != authority.dtb_sha256 or manifest.dtb_size != authority.dtb_size:
        raise DeviceTreeError("device-tree authority binding mismatch: DTB")
    if manifest.dtbo_sha256 != authority.dtbo_image_sha256 or manifest.dtbo_size != authority.dtbo_image_size:
        raise DeviceTreeError("device-tree authority binding mismatch: DTBO image")
    if manifest.dtbo_entry_count != authority.dtbo_entry_count:
        raise DeviceTreeError("device-tree authority binding mismatch: DTBO entry count")
    if authority.strict_byte_identical is not True or authority.distinct_build_roots_verified is not True or authority.reviewed is not True:
        raise DeviceTreeError("device-tree authority is not strict/reviewed")

    return FirstBootDeviceTreeAuthorityEvidence(
        schema_version=1,
        profile_id=manifest.profile_id,
        first_boot_manifest_sha256=manifest_digest,
        device_tree_authority_sha256=_digest(authority.authority_sha256(), "device-tree authority"),
        device_tree_plan_sha256=_digest(plan.plan_sha256(), "device-tree plan"),
        kernel_authority_sha256=_digest(authority.kernel_authority_sha256, "kernel authority"),
        authority_name=authority.authority_name,
        authority_run_id=authority.authority_run_id,
        authority_commit=authority.authority_commit,
        authority_artifact_id=authority.authority_artifact_id,
        format_lock_sha256=plan.format_lock_sha256,
        dtb_sha256=authority.dtb_sha256,
        dtb_size=authority.dtb_size,
        raw_dtbo=authority.raw_dtbo,
        dtbo_image_sha256=authority.dtbo_image_sha256,
        dtbo_image_size=authority.dtbo_image_size,
        dtbo_entry_count=authority.dtbo_entry_count,
        strict_byte_identical=True,
        distinct_build_roots_verified=True,
        reviewed=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def write_first_boot_device_tree_authority_evidence(
    evidence: FirstBootDeviceTreeAuthorityEvidence,
    destination: Path,
) -> str:
    if not isinstance(evidence, FirstBootDeviceTreeAuthorityEvidence) or evidence.schema_version != 1:
        raise DeviceTreeError("invalid first-boot device-tree authority evidence")
    if evidence.strict_byte_identical is not True or evidence.distinct_build_roots_verified is not True or evidence.reviewed is not True:
        raise DeviceTreeError("first-boot device-tree authority evidence is not strict/reviewed")
    if evidence.hardware_verified is not False or evidence.beta_gate_credit is not False:
        raise DeviceTreeError("first-boot device-tree authority evidence cannot claim hardware/Beta credit")
    path = Path(destination)
    if path.exists():
        raise DeviceTreeError("refusing to overwrite first-boot device-tree authority evidence")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists():
        raise DeviceTreeError("refusing stale first-boot device-tree authority temporary file")
    try:
        temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()
