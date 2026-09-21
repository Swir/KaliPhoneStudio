"""Host-only binding that prepares a reviewed Phosh rootfs for first-boot candidate regeneration.

This module deliberately does not mutate an existing first-boot manifest.  Instead it
cross-binds the already reviewed kernel/device-tree provenance from one exact candidate
authority bundle with one explicitly reviewed Phosh ARM64 rootfs authority and records
that the rootfs substitution requires a new candidate manifest.

No device I/O, storage selection, mounting, flashing, hardware verification or Beta
authorization is possible here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from .candidate_authority_bundle import FirstBootAuthorityBundleEvidence
from .phosh_rootfs_authority import (
    PhoshRootfsAuthorityError,
    PhoshRootfsAuthorityRecord,
    PhoshRootfsReviewPacketEvidence,
    load_and_verify_phosh_rootfs_authority,
    load_phosh_rootfs_review_packet,
    validate_phosh_rootfs_authority,
)
from .stable_file import StableFileError, read_stable_regular_file


_POLICY = "phosh-first-boot-regeneration-binding-v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_MAX_EVIDENCE_BYTES = 512 * 1024


class PhoshFirstBootBindingError(ValueError):
    """Raised when reviewed Phosh/rootfs provenance cannot be safely cross-bound."""


@dataclass(frozen=True)
class PhoshFirstBootBindingEvidence:
    schema_version: int
    binding_policy: str
    profile_id: str
    base_first_boot_manifest_sha256: str
    base_candidate_authority_bundle_sha256: str
    kernel_authority_sha256: str
    kernel_authority_run_id: int
    kernel_authority_commit: str
    kernel_authority_artifact_id: int
    kernel_image_sha256: str
    device_tree_authority_sha256: str
    device_tree_authority_run_id: int
    device_tree_authority_commit: str
    device_tree_authority_artifact_id: int
    dtb_sha256: str
    dtbo_image_sha256: str
    superseded_rootfs_authority_sha256: str
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
    phosh_rootfs_artifact_sha256: str
    phosh_rootfs_artifact_size: int
    phosh_package_manifest_sha256: str
    phosh_package_count: int
    kernel_device_tree_provenance_reused: bool
    rootfs_substitution_required: bool
    candidate_manifest_regeneration_required: bool
    ready_for_candidate_manifest_regeneration: bool
    physical_validation_required: bool
    display_verified: bool
    touch_verified: bool
    hardware_verified: bool
    beta_release_authorized: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise PhoshFirstBootBindingError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _commit(value: object, label: str) -> str:
    if not isinstance(value, str) or not _COMMIT_RE.fullmatch(value):
        raise PhoshFirstBootBindingError(f"{label} must be a full lowercase 40-hex commit")
    return value


def _positive(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PhoshFirstBootBindingError(f"{label} must be a positive integer")
    return value


def _validate_candidate_bundle(bundle: FirstBootAuthorityBundleEvidence) -> None:
    if not isinstance(bundle, FirstBootAuthorityBundleEvidence) or bundle.schema_version != 1:
        raise PhoshFirstBootBindingError("first-boot authority bundle must be schema-v1 typed evidence")
    if not isinstance(bundle.profile_id, str) or not bundle.profile_id.strip():
        raise PhoshFirstBootBindingError("first-boot authority bundle profile_id is invalid")
    for label, value in (
        ("first-boot manifest", bundle.first_boot_manifest_sha256),
        ("kernel binding", bundle.kernel_binding_sha256),
        ("rootfs binding", bundle.rootfs_binding_sha256),
        ("device-tree binding", bundle.device_tree_binding_sha256),
        ("kernel authority", bundle.kernel_authority_sha256),
        ("rootfs authority", bundle.rootfs_authority_sha256),
        ("device-tree authority", bundle.device_tree_authority_sha256),
        ("kernel image", bundle.kernel_image_sha256),
        ("rootfs artifact", bundle.rootfs_artifact_sha256),
        ("DTB", bundle.dtb_sha256),
        ("DTBO", bundle.dtbo_image_sha256),
    ):
        _sha(value, label)
    for label, value in (
        ("kernel authority commit", bundle.kernel_authority_commit),
        ("rootfs authority commit", bundle.rootfs_authority_commit),
        ("device-tree authority commit", bundle.device_tree_authority_commit),
    ):
        _commit(value, label)
    for label, value in (
        ("kernel authority run id", bundle.kernel_authority_run_id),
        ("kernel authority artifact id", bundle.kernel_authority_artifact_id),
        ("rootfs authority run id", bundle.rootfs_authority_run_id),
        ("rootfs authority artifact id", bundle.rootfs_authority_artifact_id),
        ("device-tree authority run id", bundle.device_tree_authority_run_id),
        ("device-tree authority artifact id", bundle.device_tree_authority_artifact_id),
    ):
        _positive(value, label)
    if bundle.all_authorities_reviewed is not True or bundle.all_required_artifacts_strict is not True:
        raise PhoshFirstBootBindingError("base first-boot authority bundle must remain reviewed and strict")
    if bundle.hardware_verified is not False or bundle.beta_gate_credit is not False:
        raise PhoshFirstBootBindingError("base first-boot authority bundle cannot carry hardware/Beta credit")


def _load_candidate_bundle(path: Path) -> FirstBootAuthorityBundleEvidence:
    try:
        payload, _identity = read_stable_regular_file(
            Path(path), max_bytes=_MAX_EVIDENCE_BYTES, label="first-boot authority bundle"
        )
    except StableFileError as exc:
        raise PhoshFirstBootBindingError(str(exc)) from exc
    try:
        raw: Any = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhoshFirstBootBindingError("first-boot authority bundle is not valid UTF-8 JSON") from exc
    expected = {item.name for item in fields(FirstBootAuthorityBundleEvidence)}
    if not isinstance(raw, dict) or set(raw) != expected:
        raise PhoshFirstBootBindingError("first-boot authority bundle fields do not match schema-v1")
    try:
        bundle = FirstBootAuthorityBundleEvidence(**raw)
    except (TypeError, ValueError) as exc:
        raise PhoshFirstBootBindingError("first-boot authority bundle field types are invalid") from exc
    _validate_candidate_bundle(bundle)
    if payload != bundle.canonical_json().encode("utf-8"):
        raise PhoshFirstBootBindingError("first-boot authority bundle is not canonical JSON")
    return bundle


def validate_phosh_first_boot_binding(evidence: PhoshFirstBootBindingEvidence) -> None:
    if not isinstance(evidence, PhoshFirstBootBindingEvidence) or evidence.schema_version != 1:
        raise PhoshFirstBootBindingError("Phosh first-boot binding must be schema-v1 typed evidence")
    if evidence.binding_policy != _POLICY:
        raise PhoshFirstBootBindingError("unsupported Phosh first-boot binding policy")
    if not isinstance(evidence.profile_id, str) or not evidence.profile_id.strip():
        raise PhoshFirstBootBindingError("Phosh first-boot binding profile_id is invalid")
    for label, value in (
        ("base first-boot manifest", evidence.base_first_boot_manifest_sha256),
        ("base candidate authority bundle", evidence.base_candidate_authority_bundle_sha256),
        ("kernel authority", evidence.kernel_authority_sha256),
        ("kernel image", evidence.kernel_image_sha256),
        ("device-tree authority", evidence.device_tree_authority_sha256),
        ("DTB", evidence.dtb_sha256),
        ("DTBO", evidence.dtbo_image_sha256),
        ("superseded rootfs authority", evidence.superseded_rootfs_authority_sha256),
        ("superseded rootfs artifact", evidence.superseded_rootfs_artifact_sha256),
        ("Phosh rootfs authority", evidence.phosh_rootfs_authority_sha256),
        ("Phosh review packet", evidence.phosh_review_packet_sha256),
        ("Phosh source lock", evidence.phosh_source_lock_sha256),
        ("Phosh rootfs artifact", evidence.phosh_rootfs_artifact_sha256),
        ("Phosh package manifest", evidence.phosh_package_manifest_sha256),
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
        ("kernel authority run id", evidence.kernel_authority_run_id),
        ("kernel authority artifact id", evidence.kernel_authority_artifact_id),
        ("device-tree authority run id", evidence.device_tree_authority_run_id),
        ("device-tree authority artifact id", evidence.device_tree_authority_artifact_id),
        ("Phosh rootfs authority run id", evidence.phosh_rootfs_authority_run_id),
        ("Phosh rootfs authority artifact id", evidence.phosh_rootfs_authority_artifact_id),
        ("Phosh rootfs artifact size", evidence.phosh_rootfs_artifact_size),
        ("Phosh package count", evidence.phosh_package_count),
    ):
        _positive(value, label)
    if not isinstance(evidence.phosh_rootfs_authority_name, str) or not evidence.phosh_rootfs_authority_name.strip():
        raise PhoshFirstBootBindingError("Phosh rootfs authority name is invalid")
    if evidence.superseded_rootfs_artifact_sha256 == evidence.phosh_rootfs_artifact_sha256:
        raise PhoshFirstBootBindingError(
            "Phosh rootfs equals the base candidate rootfs; use the existing direct Phosh candidate binding"
        )
    for name in (
        "kernel_device_tree_provenance_reused",
        "rootfs_substitution_required",
        "candidate_manifest_regeneration_required",
        "ready_for_candidate_manifest_regeneration",
        "physical_validation_required",
    ):
        if getattr(evidence, name) is not True:
            raise PhoshFirstBootBindingError(f"Phosh first-boot binding requires {name}=true")
    for name in (
        "display_verified",
        "touch_verified",
        "hardware_verified",
        "beta_release_authorized",
        "beta_gate_credit",
    ):
        if getattr(evidence, name) is not False:
            raise PhoshFirstBootBindingError(f"host Phosh first-boot binding cannot promote {name}")


def bind_reviewed_phosh_rootfs_for_candidate_regeneration(
    candidate_bundle: FirstBootAuthorityBundleEvidence,
    phosh_authority: PhoshRootfsAuthorityRecord,
    review_packet: PhoshRootfsReviewPacketEvidence,
) -> PhoshFirstBootBindingEvidence:
    """Prepare exact reviewed inputs for a successor first-boot candidate manifest."""
    _validate_candidate_bundle(candidate_bundle)
    try:
        validate_phosh_rootfs_authority(phosh_authority, review_packet)
    except PhoshRootfsAuthorityError as exc:
        raise PhoshFirstBootBindingError(str(exc)) from exc
    if phosh_authority.ready_for_first_boot_binding is not True:
        raise PhoshFirstBootBindingError("reviewed Phosh rootfs authority is not ready for first-boot binding")
    if phosh_authority.rootfs_artifact_sha256 == candidate_bundle.rootfs_artifact_sha256:
        raise PhoshFirstBootBindingError(
            "Phosh rootfs equals the base candidate rootfs; use the existing direct Phosh candidate binding"
        )

    evidence = PhoshFirstBootBindingEvidence(
        schema_version=1,
        binding_policy=_POLICY,
        profile_id=candidate_bundle.profile_id,
        base_first_boot_manifest_sha256=candidate_bundle.first_boot_manifest_sha256,
        base_candidate_authority_bundle_sha256=candidate_bundle.evidence_sha256(),
        kernel_authority_sha256=candidate_bundle.kernel_authority_sha256,
        kernel_authority_run_id=candidate_bundle.kernel_authority_run_id,
        kernel_authority_commit=candidate_bundle.kernel_authority_commit,
        kernel_authority_artifact_id=candidate_bundle.kernel_authority_artifact_id,
        kernel_image_sha256=candidate_bundle.kernel_image_sha256,
        device_tree_authority_sha256=candidate_bundle.device_tree_authority_sha256,
        device_tree_authority_run_id=candidate_bundle.device_tree_authority_run_id,
        device_tree_authority_commit=candidate_bundle.device_tree_authority_commit,
        device_tree_authority_artifact_id=candidate_bundle.device_tree_authority_artifact_id,
        dtb_sha256=candidate_bundle.dtb_sha256,
        dtbo_image_sha256=candidate_bundle.dtbo_image_sha256,
        superseded_rootfs_authority_sha256=candidate_bundle.rootfs_authority_sha256,
        superseded_rootfs_artifact_sha256=candidate_bundle.rootfs_artifact_sha256,
        phosh_rootfs_authority_sha256=phosh_authority.authority_sha256(),
        phosh_rootfs_authority_name=phosh_authority.authority_name,
        phosh_rootfs_authority_run_id=phosh_authority.authority_run_id,
        phosh_rootfs_authority_commit=phosh_authority.authority_commit,
        phosh_rootfs_authority_artifact_id=phosh_authority.authority_artifact_id,
        phosh_review_packet_sha256=phosh_authority.review_packet_sha256,
        phosh_source_commit=phosh_authority.source_commit,
        phosh_upstream_commit=phosh_authority.upstream_commit,
        phosh_source_lock_sha256=phosh_authority.source_lock_sha256,
        phosh_rootfs_artifact_sha256=phosh_authority.rootfs_artifact_sha256,
        phosh_rootfs_artifact_size=phosh_authority.rootfs_artifact_size,
        phosh_package_manifest_sha256=phosh_authority.package_manifest_sha256,
        phosh_package_count=phosh_authority.package_count,
        kernel_device_tree_provenance_reused=True,
        rootfs_substitution_required=True,
        candidate_manifest_regeneration_required=True,
        ready_for_candidate_manifest_regeneration=True,
        physical_validation_required=True,
        display_verified=False,
        touch_verified=False,
        hardware_verified=False,
        beta_release_authorized=False,
        beta_gate_credit=False,
    )
    validate_phosh_first_boot_binding(evidence)
    return evidence


def build_phosh_first_boot_binding_from_paths(
    candidate_authority_bundle_path: Path,
    phosh_rootfs_authority_path: Path,
    phosh_review_packet_path: Path,
) -> PhoshFirstBootBindingEvidence:
    candidate = _load_candidate_bundle(Path(candidate_authority_bundle_path))
    try:
        packet = load_phosh_rootfs_review_packet(Path(phosh_review_packet_path))
        authority = load_and_verify_phosh_rootfs_authority(
            Path(phosh_rootfs_authority_path), Path(phosh_review_packet_path)
        )
    except PhoshRootfsAuthorityError as exc:
        raise PhoshFirstBootBindingError(str(exc)) from exc
    return bind_reviewed_phosh_rootfs_for_candidate_regeneration(candidate, authority, packet)


def write_phosh_first_boot_binding(evidence: PhoshFirstBootBindingEvidence, destination: Path) -> str:
    validate_phosh_first_boot_binding(evidence)
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise PhoshFirstBootBindingError("refusing to overwrite Phosh first-boot binding")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise PhoshFirstBootBindingError("refusing stale Phosh first-boot binding temporary path")
    data = evidence.canonical_json().encode("utf-8")
    try:
        temporary.write_bytes(data)
        temporary.replace(path)
    except OSError as exc:
        raise PhoshFirstBootBindingError(f"cannot write Phosh first-boot binding: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return sha256(data).hexdigest()


def load_phosh_first_boot_binding(path: Path) -> PhoshFirstBootBindingEvidence:
    try:
        payload, _identity = read_stable_regular_file(
            Path(path), max_bytes=_MAX_EVIDENCE_BYTES, label="Phosh first-boot binding"
        )
    except StableFileError as exc:
        raise PhoshFirstBootBindingError(str(exc)) from exc
    try:
        raw: Any = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhoshFirstBootBindingError("Phosh first-boot binding is not valid UTF-8 JSON") from exc
    expected = {item.name for item in fields(PhoshFirstBootBindingEvidence)}
    if not isinstance(raw, dict) or set(raw) != expected:
        raise PhoshFirstBootBindingError("Phosh first-boot binding fields do not match schema-v1")
    try:
        evidence = PhoshFirstBootBindingEvidence(**raw)
    except (TypeError, ValueError) as exc:
        raise PhoshFirstBootBindingError("Phosh first-boot binding field types are invalid") from exc
    validate_phosh_first_boot_binding(evidence)
    if payload != evidence.canonical_json().encode("utf-8"):
        raise PhoshFirstBootBindingError("Phosh first-boot binding is not canonical JSON")
    return evidence
