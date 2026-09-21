"""Create an immutable Phosh successor first-boot candidate without rewriting legacy rootfs provenance.

The legacy :class:`FirstBootCandidateManifest` schema v8 binds one exact rootfs evidence
chain. Replacing only its rootfs digest would make that manifest internally dishonest.
This module therefore creates a small successor manifest that keeps the exact reviewed
boot/kernel/device-tree identity from the base schema-v8 candidate and overlays one
reviewed Phosh rootfs through ``PhoshFirstBootBindingEvidence``.

This is host-only evidence. It performs no device I/O, selects no storage target and
cannot claim display/touch/hardware/Beta success.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, TypeVar

from .candidate import FirstBootCandidateManifest
from .candidate_authority_bundle import FirstBootAuthorityBundleEvidence
from .phosh_first_boot_binding import (
    PhoshFirstBootBindingError,
    PhoshFirstBootBindingEvidence,
    validate_phosh_first_boot_binding,
)
from .stable_file import StableFileError, read_stable_regular_file

_POLICY = "phosh-first-boot-successor-v1"
_MAX_EVIDENCE_BYTES = 2 * 1024 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
T = TypeVar("T")


class PhoshSuccessorCandidateError(ValueError):
    """Raised when exact first-boot/Phosh provenance cannot be joined safely."""


@dataclass(frozen=True)
class PhoshSuccessorCandidateManifest:
    schema_version: int
    candidate_policy: str
    profile_id: str
    device_serial: str
    fastboot_baseline_sha256: str
    firmware_build: str
    firmware_fingerprint: str
    boot_authorization_sha256: str
    boot_plan_sha256: str
    boot_image_sha256: str
    boot_image_size: int
    base_first_boot_manifest_sha256: str
    base_candidate_authority_bundle_sha256: str
    phosh_first_boot_binding_sha256: str
    kernel_authority_sha256: str
    kernel_authority_run_id: int
    kernel_authority_commit: str
    kernel_authority_artifact_id: int
    kernel_image_sha256: str
    kernel_image_size: int
    device_tree_authority_sha256: str
    device_tree_authority_run_id: int
    device_tree_authority_commit: str
    device_tree_authority_artifact_id: int
    dtb_sha256: str | None
    dtb_size: int | None
    dtbo_image_sha256: str | None
    dtbo_size: int | None
    superseded_rootfs_artifact_sha256: str
    phosh_rootfs_authority_sha256: str
    phosh_rootfs_authority_name: str
    phosh_rootfs_authority_run_id: int
    phosh_rootfs_authority_commit: str
    phosh_rootfs_authority_artifact_id: int
    phosh_review_packet_sha256: str
    phosh_source_commit: str
    phosh_upstream_commit: str
    phosh_source_lock_sha256: str
    rootfs_artifact_sha256: str
    rootfs_artifact_size: int
    rootfs_package_manifest_sha256: str
    rootfs_package_count: int
    kernel_device_tree_provenance_reused: bool
    reviewed_phosh_rootfs_bound: bool
    physical_validation_required: bool
    display_verified: bool
    touch_verified: bool
    hardware_verified: bool
    beta_release_authorized: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def manifest_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise PhoshSuccessorCandidateError(f"{label} must be a lowercase SHA-256")
    return value


def _commit(value: object, label: str) -> str:
    if not isinstance(value, str) or not _COMMIT_RE.fullmatch(value):
        raise PhoshSuccessorCandidateError(f"{label} must be a full lowercase 40-hex commit")
    return value


def _positive(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PhoshSuccessorCandidateError(f"{label} must be a positive integer")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PhoshSuccessorCandidateError(f"{label} must be a non-empty string")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise PhoshSuccessorCandidateError(f"{label} contains control data")
    return value


def _optional_artifact(digest: object, size: object, label: str) -> None:
    if digest is None:
        if size is not None:
            raise PhoshSuccessorCandidateError(f"{label} size must be null when digest is null")
        return
    _sha(digest, f"{label} SHA-256")
    _positive(size, f"{label} size")


def _validate_base_manifest(manifest: FirstBootCandidateManifest) -> None:
    if not isinstance(manifest, FirstBootCandidateManifest) or manifest.schema_version != 8:
        raise PhoshSuccessorCandidateError("base first-boot candidate must be schema-v8 typed evidence")
    _text(manifest.profile_id, "profile_id")
    _text(manifest.device_serial, "device_serial")
    _text(manifest.firmware_build, "firmware_build")
    _text(manifest.firmware_fingerprint, "firmware_fingerprint")
    for label, value in (
        ("Fastboot baseline", manifest.fastboot_baseline_sha256),
        ("boot authorization", manifest.boot_authorization_sha256),
        ("boot plan", manifest.boot_plan_sha256),
        ("boot image", manifest.boot_image_sha256),
        ("kernel image", manifest.kernel_image_sha256),
        ("rootfs artifact", manifest.rootfs_artifact_sha256),
    ):
        _sha(value, label)
    _positive(manifest.boot_image_size, "boot image size")
    _positive(manifest.kernel_image_size, "kernel image size")
    _positive(manifest.rootfs_artifact_size, "rootfs artifact size")
    _optional_artifact(manifest.dtb_sha256, manifest.dtb_size, "DTB")
    _optional_artifact(manifest.dtbo_sha256, manifest.dtbo_size, "DTBO")


def _validate_base_authorities(
    manifest: FirstBootCandidateManifest, bundle: FirstBootAuthorityBundleEvidence
) -> None:
    if not isinstance(bundle, FirstBootAuthorityBundleEvidence) or bundle.schema_version != 1:
        raise PhoshSuccessorCandidateError("base authority bundle must be schema-v1 typed evidence")
    if bundle.profile_id != manifest.profile_id:
        raise PhoshSuccessorCandidateError("base authority bundle profile mismatch")
    if bundle.first_boot_manifest_sha256 != manifest.manifest_sha256():
        raise PhoshSuccessorCandidateError("base authority bundle is detached from exact schema-v8 manifest")
    if bundle.all_authorities_reviewed is not True or bundle.all_required_artifacts_strict is not True:
        raise PhoshSuccessorCandidateError("base authority bundle must remain reviewed and strict")
    if bundle.hardware_verified is not False or bundle.beta_gate_credit is not False:
        raise PhoshSuccessorCandidateError("base authority bundle cannot claim hardware/Beta credit")
    for observed, expected, label in (
        (bundle.kernel_image_sha256, manifest.kernel_image_sha256, "kernel Image"),
        (bundle.rootfs_artifact_sha256, manifest.rootfs_artifact_sha256, "legacy rootfs"),
        (bundle.dtb_sha256, manifest.dtb_sha256, "DTB"),
        (bundle.dtbo_image_sha256, manifest.dtbo_sha256, "DTBO"),
    ):
        if observed != expected:
            raise PhoshSuccessorCandidateError(f"base authority bundle {label} differs from manifest")


def validate_phosh_successor_candidate(evidence: PhoshSuccessorCandidateManifest) -> None:
    if not isinstance(evidence, PhoshSuccessorCandidateManifest) or evidence.schema_version != 1:
        raise PhoshSuccessorCandidateError("Phosh successor candidate must be schema-v1 typed evidence")
    if evidence.candidate_policy != _POLICY:
        raise PhoshSuccessorCandidateError("unsupported Phosh successor candidate policy")
    for label, value in (
        ("profile_id", evidence.profile_id),
        ("device_serial", evidence.device_serial),
        ("firmware_build", evidence.firmware_build),
        ("firmware_fingerprint", evidence.firmware_fingerprint),
        ("Phosh rootfs authority name", evidence.phosh_rootfs_authority_name),
    ):
        _text(value, label)
    for label, value in (
        ("Fastboot baseline", evidence.fastboot_baseline_sha256),
        ("boot authorization", evidence.boot_authorization_sha256),
        ("boot plan", evidence.boot_plan_sha256),
        ("boot image", evidence.boot_image_sha256),
        ("base first-boot manifest", evidence.base_first_boot_manifest_sha256),
        ("base candidate authority bundle", evidence.base_candidate_authority_bundle_sha256),
        ("Phosh first-boot binding", evidence.phosh_first_boot_binding_sha256),
        ("kernel authority", evidence.kernel_authority_sha256),
        ("kernel image", evidence.kernel_image_sha256),
        ("device-tree authority", evidence.device_tree_authority_sha256),
        ("superseded rootfs", evidence.superseded_rootfs_artifact_sha256),
        ("Phosh rootfs authority", evidence.phosh_rootfs_authority_sha256),
        ("Phosh review packet", evidence.phosh_review_packet_sha256),
        ("Phosh source lock", evidence.phosh_source_lock_sha256),
        ("Phosh rootfs artifact", evidence.rootfs_artifact_sha256),
        ("Phosh package manifest", evidence.rootfs_package_manifest_sha256),
    ):
        _sha(value, label)
    for label, value in (
        ("kernel authority commit", evidence.kernel_authority_commit),
        ("device-tree authority commit", evidence.device_tree_authority_commit),
        ("Phosh rootfs authority commit", evidence.phosh_rootfs_authority_commit),
        ("Phosh source commit", evidence.phosh_source_commit),
        ("Phosh upstream commit", evidence.phosh_upstream_commit),
    ):
        _commit(value, label)
    for label, value in (
        ("boot image size", evidence.boot_image_size),
        ("kernel image size", evidence.kernel_image_size),
        ("kernel authority run id", evidence.kernel_authority_run_id),
        ("kernel authority artifact id", evidence.kernel_authority_artifact_id),
        ("device-tree authority run id", evidence.device_tree_authority_run_id),
        ("device-tree authority artifact id", evidence.device_tree_authority_artifact_id),
        ("Phosh rootfs authority run id", evidence.phosh_rootfs_authority_run_id),
        ("Phosh rootfs authority artifact id", evidence.phosh_rootfs_authority_artifact_id),
        ("Phosh rootfs artifact size", evidence.rootfs_artifact_size),
        ("Phosh package count", evidence.rootfs_package_count),
    ):
        _positive(value, label)
    _optional_artifact(evidence.dtb_sha256, evidence.dtb_size, "DTB")
    _optional_artifact(evidence.dtbo_image_sha256, evidence.dtbo_size, "DTBO")
    if evidence.superseded_rootfs_artifact_sha256 == evidence.rootfs_artifact_sha256:
        raise PhoshSuccessorCandidateError("successor rootfs must differ from the superseded rootfs")
    for name in (
        "kernel_device_tree_provenance_reused",
        "reviewed_phosh_rootfs_bound",
        "physical_validation_required",
    ):
        if getattr(evidence, name) is not True:
            raise PhoshSuccessorCandidateError(f"Phosh successor candidate requires {name}=true")
    for name in (
        "display_verified",
        "touch_verified",
        "hardware_verified",
        "beta_release_authorized",
        "beta_gate_credit",
    ):
        if getattr(evidence, name) is not False:
            raise PhoshSuccessorCandidateError(f"host successor candidate cannot promote {name}")


def build_phosh_successor_candidate(
    base_manifest: FirstBootCandidateManifest,
    base_authorities: FirstBootAuthorityBundleEvidence,
    binding: PhoshFirstBootBindingEvidence,
) -> PhoshSuccessorCandidateManifest:
    """Bind exact boot/kernel/DT identity to one reviewed replacement Phosh rootfs."""
    _validate_base_manifest(base_manifest)
    _validate_base_authorities(base_manifest, base_authorities)
    try:
        validate_phosh_first_boot_binding(binding)
    except PhoshFirstBootBindingError as exc:
        raise PhoshSuccessorCandidateError(str(exc)) from exc

    manifest_sha = base_manifest.manifest_sha256()
    bundle_sha = base_authorities.evidence_sha256()
    if binding.profile_id != base_manifest.profile_id:
        raise PhoshSuccessorCandidateError("Phosh binding profile mismatch")
    if binding.base_first_boot_manifest_sha256 != manifest_sha:
        raise PhoshSuccessorCandidateError("Phosh binding is detached from exact base manifest")
    if binding.base_candidate_authority_bundle_sha256 != bundle_sha:
        raise PhoshSuccessorCandidateError("Phosh binding is detached from exact base authority bundle")
    for observed, expected, label in (
        (binding.kernel_authority_sha256, base_authorities.kernel_authority_sha256, "kernel authority"),
        (binding.kernel_image_sha256, base_manifest.kernel_image_sha256, "kernel Image"),
        (binding.device_tree_authority_sha256, base_authorities.device_tree_authority_sha256, "device-tree authority"),
        (binding.dtb_sha256, base_manifest.dtb_sha256, "DTB"),
        (binding.dtbo_image_sha256, base_manifest.dtbo_sha256, "DTBO"),
        (binding.superseded_rootfs_artifact_sha256, base_manifest.rootfs_artifact_sha256, "superseded rootfs"),
    ):
        if observed != expected:
            raise PhoshSuccessorCandidateError(f"Phosh binding {label} differs from exact base candidate")

    evidence = PhoshSuccessorCandidateManifest(
        schema_version=1,
        candidate_policy=_POLICY,
        profile_id=base_manifest.profile_id,
        device_serial=base_manifest.device_serial,
        fastboot_baseline_sha256=base_manifest.fastboot_baseline_sha256,
        firmware_build=base_manifest.firmware_build,
        firmware_fingerprint=base_manifest.firmware_fingerprint,
        boot_authorization_sha256=base_manifest.boot_authorization_sha256,
        boot_plan_sha256=base_manifest.boot_plan_sha256,
        boot_image_sha256=base_manifest.boot_image_sha256,
        boot_image_size=base_manifest.boot_image_size,
        base_first_boot_manifest_sha256=manifest_sha,
        base_candidate_authority_bundle_sha256=bundle_sha,
        phosh_first_boot_binding_sha256=binding.evidence_sha256(),
        kernel_authority_sha256=binding.kernel_authority_sha256,
        kernel_authority_run_id=binding.kernel_authority_run_id,
        kernel_authority_commit=binding.kernel_authority_commit,
        kernel_authority_artifact_id=binding.kernel_authority_artifact_id,
        kernel_image_sha256=binding.kernel_image_sha256,
        kernel_image_size=base_manifest.kernel_image_size,
        device_tree_authority_sha256=binding.device_tree_authority_sha256,
        device_tree_authority_run_id=binding.device_tree_authority_run_id,
        device_tree_authority_commit=binding.device_tree_authority_commit,
        device_tree_authority_artifact_id=binding.device_tree_authority_artifact_id,
        dtb_sha256=base_manifest.dtb_sha256,
        dtb_size=base_manifest.dtb_size,
        dtbo_image_sha256=base_manifest.dtbo_sha256,
        dtbo_size=base_manifest.dtbo_size,
        superseded_rootfs_artifact_sha256=binding.superseded_rootfs_artifact_sha256,
        phosh_rootfs_authority_sha256=binding.phosh_rootfs_authority_sha256,
        phosh_rootfs_authority_name=binding.phosh_rootfs_authority_name,
        phosh_rootfs_authority_run_id=binding.phosh_rootfs_authority_run_id,
        phosh_rootfs_authority_commit=binding.phosh_rootfs_authority_commit,
        phosh_rootfs_authority_artifact_id=binding.phosh_rootfs_authority_artifact_id,
        phosh_review_packet_sha256=binding.phosh_review_packet_sha256,
        phosh_source_commit=binding.phosh_source_commit,
        phosh_upstream_commit=binding.phosh_upstream_commit,
        phosh_source_lock_sha256=binding.phosh_source_lock_sha256,
        rootfs_artifact_sha256=binding.phosh_rootfs_artifact_sha256,
        rootfs_artifact_size=binding.phosh_rootfs_artifact_size,
        rootfs_package_manifest_sha256=binding.phosh_package_manifest_sha256,
        rootfs_package_count=binding.phosh_package_count,
        kernel_device_tree_provenance_reused=True,
        reviewed_phosh_rootfs_bound=True,
        physical_validation_required=True,
        display_verified=False,
        touch_verified=False,
        hardware_verified=False,
        beta_release_authorized=False,
        beta_gate_credit=False,
    )
    validate_phosh_successor_candidate(evidence)
    return evidence


def _load_typed_canonical(cls: type[T], path: Path, label: str) -> T:
    try:
        payload, _identity = read_stable_regular_file(
            Path(path), max_bytes=_MAX_EVIDENCE_BYTES, label=label
        )
    except StableFileError as exc:
        raise PhoshSuccessorCandidateError(str(exc)) from exc
    try:
        raw: Any = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhoshSuccessorCandidateError(f"{label} is not valid UTF-8 JSON") from exc
    expected = {item.name for item in fields(cls)}
    if not isinstance(raw, dict) or set(raw) != expected:
        raise PhoshSuccessorCandidateError(f"{label} fields do not match typed schema")
    try:
        evidence = cls(**raw)
    except (TypeError, ValueError) as exc:
        raise PhoshSuccessorCandidateError(f"{label} field types are invalid") from exc
    canonical = getattr(evidence, "canonical_json", None)
    if not callable(canonical) or payload != canonical().encode("utf-8"):
        raise PhoshSuccessorCandidateError(f"{label} is not canonical JSON")
    return evidence


def build_phosh_successor_candidate_from_paths(
    base_manifest_path: Path,
    base_authority_bundle_path: Path,
    phosh_first_boot_binding_path: Path,
) -> PhoshSuccessorCandidateManifest:
    base_manifest = _load_typed_canonical(
        FirstBootCandidateManifest, base_manifest_path, "base first-boot manifest"
    )
    base_authorities = _load_typed_canonical(
        FirstBootAuthorityBundleEvidence, base_authority_bundle_path, "base authority bundle"
    )
    binding = _load_typed_canonical(
        PhoshFirstBootBindingEvidence, phosh_first_boot_binding_path, "Phosh first-boot binding"
    )
    return build_phosh_successor_candidate(base_manifest, base_authorities, binding)


def load_phosh_successor_candidate(path: Path) -> PhoshSuccessorCandidateManifest:
    evidence = _load_typed_canonical(
        PhoshSuccessorCandidateManifest, Path(path), "Phosh successor candidate"
    )
    validate_phosh_successor_candidate(evidence)
    return evidence


def write_phosh_successor_candidate(
    evidence: PhoshSuccessorCandidateManifest, destination: Path
) -> str:
    validate_phosh_successor_candidate(evidence)
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise PhoshSuccessorCandidateError(f"refusing to overwrite Phosh successor candidate: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise PhoshSuccessorCandidateError("refusing stale Phosh successor candidate temporary path")
    try:
        temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.manifest_sha256()
