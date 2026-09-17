"""Join reviewed kernel, rootfs and device-tree authority bindings for one candidate.

The three authority layers are intentionally created and reviewed independently. This
module adds the final host-side cross-binding needed before release-candidate assembly:
all three bindings must refer to the exact same schema-v8 first-boot manifest and the
DT authority must reference the same reviewed kernel authority as the kernel binding.

This is provenance only. It never performs device I/O and never grants physical/Beta
credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re

from .candidate import FirstBootCandidateManifest
from .candidate_device_tree_authority import FirstBootDeviceTreeAuthorityEvidence
from .candidate_kernel_authority import FirstBootKernelAuthorityEvidence
from .candidate_rootfs_authority import FirstBootRootfsAuthorityEvidence


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class CandidateAuthorityBundleError(ValueError):
    pass


@dataclass(frozen=True)
class FirstBootAuthorityBundleEvidence:
    schema_version: int
    profile_id: str
    first_boot_manifest_sha256: str
    kernel_binding_sha256: str
    rootfs_binding_sha256: str
    device_tree_binding_sha256: str
    kernel_authority_sha256: str
    rootfs_authority_sha256: str
    device_tree_authority_sha256: str
    kernel_authority_run_id: int
    kernel_authority_commit: str
    kernel_authority_artifact_id: int
    rootfs_authority_run_id: int
    rootfs_authority_commit: str
    rootfs_authority_artifact_id: int
    device_tree_authority_run_id: int
    device_tree_authority_commit: str
    device_tree_authority_artifact_id: int
    kernel_image_sha256: str
    rootfs_artifact_sha256: str
    dtb_sha256: str
    dtbo_image_sha256: str
    all_authorities_reviewed: bool
    all_required_artifacts_strict: bool
    hardware_verified: bool = False
    beta_gate_credit: bool = False

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise CandidateAuthorityBundleError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _commit(value: object, label: str) -> str:
    if not isinstance(value, str) or not _COMMIT_RE.fullmatch(value):
        raise CandidateAuthorityBundleError(f"{label} must be a full 40-hex commit")
    return value


def _positive(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise CandidateAuthorityBundleError(f"{label} must be a positive integer")
    return value


def _base_binding_checks(
    binding: object,
    *,
    expected_type: type,
    label: str,
    profile_id: str,
    manifest_sha256: str,
) -> None:
    if not isinstance(binding, expected_type):
        raise CandidateAuthorityBundleError(f"{label} must be typed authority-binding evidence")
    if binding.schema_version != 1:
        raise CandidateAuthorityBundleError(f"unsupported {label} schema")
    if binding.profile_id != profile_id:
        raise CandidateAuthorityBundleError(f"{label} profile does not match first-boot candidate")
    if _sha(binding.first_boot_manifest_sha256, f"{label} manifest") != manifest_sha256:
        raise CandidateAuthorityBundleError(f"{label} is detached from first-boot manifest")
    if binding.reviewed is not True:
        raise CandidateAuthorityBundleError(f"{label} is not reviewed")
    if binding.hardware_verified is not False or binding.beta_gate_credit is not False:
        raise CandidateAuthorityBundleError(f"{label} cannot claim hardware/Beta credit")


def bind_first_boot_authority_bundle(
    manifest: FirstBootCandidateManifest,
    kernel: FirstBootKernelAuthorityEvidence,
    rootfs: FirstBootRootfsAuthorityEvidence,
    device_tree: FirstBootDeviceTreeAuthorityEvidence,
) -> FirstBootAuthorityBundleEvidence:
    """Cross-bind all reviewed host authorities to one exact first-boot manifest."""
    if not isinstance(manifest, FirstBootCandidateManifest) or manifest.schema_version != 8:
        raise CandidateAuthorityBundleError("authority bundle requires a schema-v8 first-boot manifest")
    if not isinstance(manifest.profile_id, str) or not manifest.profile_id.strip():
        raise CandidateAuthorityBundleError("first-boot manifest has invalid profile_id")
    manifest_digest = _sha(manifest.manifest_sha256(), "first-boot manifest")

    _base_binding_checks(
        kernel,
        expected_type=FirstBootKernelAuthorityEvidence,
        label="kernel authority binding",
        profile_id=manifest.profile_id,
        manifest_sha256=manifest_digest,
    )
    _base_binding_checks(
        rootfs,
        expected_type=FirstBootRootfsAuthorityEvidence,
        label="rootfs authority binding",
        profile_id=manifest.profile_id,
        manifest_sha256=manifest_digest,
    )
    _base_binding_checks(
        device_tree,
        expected_type=FirstBootDeviceTreeAuthorityEvidence,
        label="device-tree authority binding",
        profile_id=manifest.profile_id,
        manifest_sha256=manifest_digest,
    )

    if kernel.strict_byte_identical is not True or kernel.distinct_build_roots_verified is not True:
        raise CandidateAuthorityBundleError("kernel authority binding is not strict/independent")
    if rootfs.strict_byte_identical is not True:
        raise CandidateAuthorityBundleError("rootfs authority binding is not strict")
    if device_tree.strict_byte_identical is not True or device_tree.distinct_build_roots_verified is not True:
        raise CandidateAuthorityBundleError("device-tree authority binding is not strict/independent")

    kernel_authority = _sha(kernel.kernel_authority_sha256, "kernel authority")
    if _sha(device_tree.kernel_authority_sha256, "device-tree kernel authority") != kernel_authority:
        raise CandidateAuthorityBundleError(
            "device-tree authority binding references a different reviewed kernel authority"
        )

    # Recheck the artifact identities exposed by the candidate. These comparisons make
    # the bundle useful as a compact pre-assembly gate even if individual binding
    # objects were deserialized elsewhere before reaching this function.
    if _sha(manifest.kernel_image_sha256, "candidate kernel Image") != _sha(kernel.image_sha256, "kernel authority Image"):
        raise CandidateAuthorityBundleError("candidate kernel Image differs from reviewed kernel authority")
    if _sha(manifest.rootfs_artifact_sha256, "candidate rootfs artifact") != _sha(rootfs.artifact_sha256, "rootfs authority artifact"):
        raise CandidateAuthorityBundleError("candidate rootfs differs from reviewed rootfs authority")
    if manifest.dtb_sha256 is None or _sha(manifest.dtb_sha256, "candidate DTB") != _sha(device_tree.dtb_sha256, "device-tree authority DTB"):
        raise CandidateAuthorityBundleError("candidate DTB differs from reviewed device-tree authority")
    if manifest.dtbo_sha256 is None or _sha(manifest.dtbo_sha256, "candidate DTBO") != _sha(device_tree.dtbo_image_sha256, "device-tree authority DTBO"):
        raise CandidateAuthorityBundleError("candidate DTBO differs from reviewed device-tree authority")

    return FirstBootAuthorityBundleEvidence(
        schema_version=1,
        profile_id=manifest.profile_id,
        first_boot_manifest_sha256=manifest_digest,
        kernel_binding_sha256=_sha(kernel.evidence_sha256(), "kernel authority binding"),
        rootfs_binding_sha256=_sha(rootfs.evidence_sha256(), "rootfs authority binding"),
        device_tree_binding_sha256=_sha(device_tree.evidence_sha256(), "device-tree authority binding"),
        kernel_authority_sha256=kernel_authority,
        rootfs_authority_sha256=_sha(rootfs.rootfs_authority_sha256, "rootfs authority"),
        device_tree_authority_sha256=_sha(device_tree.device_tree_authority_sha256, "device-tree authority"),
        kernel_authority_run_id=_positive(kernel.authority_run_id, "kernel authority run id"),
        kernel_authority_commit=_commit(kernel.authority_commit, "kernel authority commit"),
        kernel_authority_artifact_id=_positive(kernel.authority_artifact_id, "kernel authority artifact id"),
        rootfs_authority_run_id=_positive(rootfs.authority_run_id, "rootfs authority run id"),
        rootfs_authority_commit=_commit(rootfs.authority_commit, "rootfs authority commit"),
        rootfs_authority_artifact_id=_positive(rootfs.authority_artifact_id, "rootfs authority artifact id"),
        device_tree_authority_run_id=_positive(device_tree.authority_run_id, "device-tree authority run id"),
        device_tree_authority_commit=_commit(device_tree.authority_commit, "device-tree authority commit"),
        device_tree_authority_artifact_id=_positive(device_tree.authority_artifact_id, "device-tree authority artifact id"),
        kernel_image_sha256=kernel.image_sha256,
        rootfs_artifact_sha256=rootfs.artifact_sha256,
        dtb_sha256=device_tree.dtb_sha256,
        dtbo_image_sha256=device_tree.dtbo_image_sha256,
        all_authorities_reviewed=True,
        all_required_artifacts_strict=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def write_first_boot_authority_bundle(
    evidence: FirstBootAuthorityBundleEvidence,
    destination: Path,
) -> str:
    if not isinstance(evidence, FirstBootAuthorityBundleEvidence) or evidence.schema_version != 1:
        raise CandidateAuthorityBundleError("invalid first-boot authority bundle evidence")
    if evidence.all_authorities_reviewed is not True or evidence.all_required_artifacts_strict is not True:
        raise CandidateAuthorityBundleError("first-boot authority bundle is not reviewed/strict")
    if evidence.hardware_verified is not False or evidence.beta_gate_credit is not False:
        raise CandidateAuthorityBundleError("first-boot authority bundle cannot claim hardware/Beta credit")
    path = Path(destination)
    if path.exists():
        raise CandidateAuthorityBundleError("refusing to overwrite first-boot authority bundle evidence")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists():
        raise CandidateAuthorityBundleError("refusing stale first-boot authority bundle temporary file")
    try:
        temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()
