"""Cross-bind host-reviewed Phosh userspace to one exact first-boot candidate.

This module closes the provenance gap between the reviewed first-boot authority
bundle and the reviewed Phosh/rootfs package binding. It is deliberately
host-only: no device I/O, storage target, mount, write, display/touch claim or
Beta authorization is possible here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from .candidate_authority_bundle import FirstBootAuthorityBundleEvidence
from .phosh_rootfs_binding import (
    PhoshRootfsAuthorityBindingEvidence,
    PhoshRootfsBindingError,
    load_phosh_rootfs_authority_binding,
    validate_phosh_rootfs_authority_binding,
)

_POLICY = "phosh-candidate-binding-v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_MAX_EVIDENCE_BYTES = 4 * 1024 * 1024


class PhoshCandidateBindingError(ValueError):
    """Raised when candidate/Phosh provenance is incomplete or drifted."""


@dataclass(frozen=True)
class PhoshCandidateBindingEvidence:
    schema_version: int
    binding_policy: str
    profile_id: str
    first_boot_manifest_sha256: str
    candidate_authority_bundle_sha256: str
    phosh_rootfs_binding_sha256: str
    phosh_source_lock_sha256: str
    phosh_upstream_commit: str
    rootfs_authority_sha256: str
    rootfs_artifact_sha256: str
    rootfs_artifact_size: int
    package_manifest_sha256: str
    package_count: int
    required_packages: tuple[str, ...]
    provenance_cross_bound: bool
    ready_for_physical_phosh_validation: bool
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
        raise PhoshCandidateBindingError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _commit(value: object, label: str) -> str:
    if not isinstance(value, str) or not _COMMIT_RE.fullmatch(value):
        raise PhoshCandidateBindingError(f"{label} must be a full lowercase 40-hex commit")
    return value


def _positive(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PhoshCandidateBindingError(f"{label} must be a positive integer")
    return value


def _read_regular_file(path: Path, label: str) -> bytes:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhoshCandidateBindingError(f"{label} must be a regular non-symlink file")
    try:
        before = source.stat()
        if before.st_size <= 0 or before.st_size > _MAX_EVIDENCE_BYTES:
            raise PhoshCandidateBindingError(f"{label} size is outside the safety limit")
        payload = source.read_bytes()
        after = source.stat()
    except OSError as exc:
        raise PhoshCandidateBindingError(f"cannot read {label}: {exc}") from exc
    if len(payload) != before.st_size:
        raise PhoshCandidateBindingError(f"{label} size changed while being read")
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or getattr(before, "st_ino", None) != getattr(after, "st_ino", None)
    ):
        raise PhoshCandidateBindingError(f"{label} changed while being read")
    return payload


def _validate_candidate_bundle(bundle: FirstBootAuthorityBundleEvidence) -> None:
    if not isinstance(bundle, FirstBootAuthorityBundleEvidence) or bundle.schema_version != 1:
        raise PhoshCandidateBindingError("first-boot authority bundle must be schema-v1 typed evidence")
    if not isinstance(bundle.profile_id, str) or not bundle.profile_id.strip():
        raise PhoshCandidateBindingError("candidate authority bundle profile_id is invalid")
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
        raise PhoshCandidateBindingError("candidate authority bundle must remain reviewed and strict")
    if bundle.hardware_verified is not False or bundle.beta_gate_credit is not False:
        raise PhoshCandidateBindingError("candidate authority bundle cannot carry hardware/Beta credit")


def _load_candidate_bundle(path: Path) -> FirstBootAuthorityBundleEvidence:
    raw = _read_regular_file(Path(path), "first-boot authority bundle")
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhoshCandidateBindingError("first-boot authority bundle is not valid UTF-8 JSON") from exc
    expected = {item.name for item in fields(FirstBootAuthorityBundleEvidence)}
    if not isinstance(value, dict) or set(value) != expected:
        raise PhoshCandidateBindingError("first-boot authority bundle fields do not match schema-v1")
    try:
        bundle = FirstBootAuthorityBundleEvidence(**value)
    except (TypeError, ValueError) as exc:
        raise PhoshCandidateBindingError("first-boot authority bundle field types are invalid") from exc
    _validate_candidate_bundle(bundle)
    if raw != bundle.canonical_json().encode("utf-8"):
        raise PhoshCandidateBindingError("first-boot authority bundle is not canonical JSON")
    return bundle


def validate_phosh_candidate_binding(evidence: PhoshCandidateBindingEvidence) -> None:
    if not isinstance(evidence, PhoshCandidateBindingEvidence) or evidence.schema_version != 1:
        raise PhoshCandidateBindingError("Phosh candidate binding must be schema-v1 typed evidence")
    if evidence.binding_policy != _POLICY:
        raise PhoshCandidateBindingError("unsupported Phosh candidate binding policy")
    if not isinstance(evidence.profile_id, str) or not evidence.profile_id.strip():
        raise PhoshCandidateBindingError("Phosh candidate binding profile_id is invalid")
    for label, value in (
        ("first-boot manifest", evidence.first_boot_manifest_sha256),
        ("candidate authority bundle", evidence.candidate_authority_bundle_sha256),
        ("Phosh rootfs binding", evidence.phosh_rootfs_binding_sha256),
        ("Phosh source lock", evidence.phosh_source_lock_sha256),
        ("rootfs authority", evidence.rootfs_authority_sha256),
        ("rootfs artifact", evidence.rootfs_artifact_sha256),
        ("package manifest", evidence.package_manifest_sha256),
    ):
        _sha(value, label)
    _commit(evidence.phosh_upstream_commit, "Phosh upstream commit")
    _positive(evidence.rootfs_artifact_size, "rootfs artifact size")
    _positive(evidence.package_count, "package count")
    if not isinstance(evidence.required_packages, tuple) or not evidence.required_packages:
        raise PhoshCandidateBindingError("required Phosh package set must be non-empty")
    if len(evidence.required_packages) != len(set(evidence.required_packages)):
        raise PhoshCandidateBindingError("required Phosh package set must be unique")
    if not all(isinstance(item, str) and item for item in evidence.required_packages):
        raise PhoshCandidateBindingError("required Phosh package names must be non-empty strings")
    if evidence.provenance_cross_bound is not True:
        raise PhoshCandidateBindingError("Phosh candidate provenance must remain cross-bound")
    if evidence.ready_for_physical_phosh_validation is not True:
        raise PhoshCandidateBindingError("host binding is only useful when ready for later physical Phosh validation")
    if evidence.physical_validation_required is not True:
        raise PhoshCandidateBindingError("physical Phosh validation must remain required")
    for name in (
        "display_verified",
        "touch_verified",
        "hardware_verified",
        "beta_release_authorized",
        "beta_gate_credit",
    ):
        if getattr(evidence, name) is not False:
            raise PhoshCandidateBindingError(f"host Phosh candidate binding cannot promote {name}")


def bind_phosh_to_first_boot_candidate(
    candidate_bundle: FirstBootAuthorityBundleEvidence,
    phosh_binding: PhoshRootfsAuthorityBindingEvidence,
) -> PhoshCandidateBindingEvidence:
    """Cross-bind exact reviewed Phosh/rootfs identity to one exact candidate bundle."""
    _validate_candidate_bundle(candidate_bundle)
    try:
        validate_phosh_rootfs_authority_binding(phosh_binding)
    except PhoshRootfsBindingError as exc:
        raise PhoshCandidateBindingError(str(exc)) from exc

    if candidate_bundle.rootfs_authority_sha256 != phosh_binding.rootfs_authority_sha256:
        raise PhoshCandidateBindingError("candidate and Phosh binding reference different rootfs authorities")
    if candidate_bundle.rootfs_artifact_sha256 != phosh_binding.rootfs_artifact_sha256:
        raise PhoshCandidateBindingError("candidate and Phosh binding reference different rootfs artifacts")
    if phosh_binding.host_userspace_package_contract_satisfied is not True:
        raise PhoshCandidateBindingError("Phosh package contract is not satisfied")
    if phosh_binding.rootfs_authority_reviewed is not True:
        raise PhoshCandidateBindingError("Phosh binding rootfs authority is not reviewed")
    if phosh_binding.ready_for_physical_candidate_binding is not True:
        raise PhoshCandidateBindingError("Phosh rootfs binding is not ready for candidate provenance binding")

    evidence = PhoshCandidateBindingEvidence(
        schema_version=1,
        binding_policy=_POLICY,
        profile_id=candidate_bundle.profile_id,
        first_boot_manifest_sha256=candidate_bundle.first_boot_manifest_sha256,
        candidate_authority_bundle_sha256=candidate_bundle.evidence_sha256(),
        phosh_rootfs_binding_sha256=phosh_binding.evidence_sha256(),
        phosh_source_lock_sha256=phosh_binding.phosh_source_lock_sha256,
        phosh_upstream_commit=phosh_binding.phosh_upstream_commit,
        rootfs_authority_sha256=phosh_binding.rootfs_authority_sha256,
        rootfs_artifact_sha256=phosh_binding.rootfs_artifact_sha256,
        rootfs_artifact_size=phosh_binding.rootfs_artifact_size,
        package_manifest_sha256=phosh_binding.package_manifest_sha256,
        package_count=phosh_binding.package_count,
        required_packages=phosh_binding.required_packages,
        provenance_cross_bound=True,
        ready_for_physical_phosh_validation=True,
        physical_validation_required=True,
        display_verified=False,
        touch_verified=False,
        hardware_verified=False,
        beta_release_authorized=False,
        beta_gate_credit=False,
    )
    validate_phosh_candidate_binding(evidence)
    return evidence


def build_phosh_candidate_binding_from_paths(
    candidate_authority_bundle_path: Path,
    phosh_rootfs_binding_path: Path,
) -> PhoshCandidateBindingEvidence:
    candidate = _load_candidate_bundle(Path(candidate_authority_bundle_path))
    try:
        phosh = load_phosh_rootfs_authority_binding(Path(phosh_rootfs_binding_path))
    except PhoshRootfsBindingError as exc:
        raise PhoshCandidateBindingError(str(exc)) from exc
    return bind_phosh_to_first_boot_candidate(candidate, phosh)


def write_phosh_candidate_binding(evidence: PhoshCandidateBindingEvidence, destination: Path) -> str:
    validate_phosh_candidate_binding(evidence)
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise PhoshCandidateBindingError("refusing to overwrite Phosh candidate binding")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise PhoshCandidateBindingError("refusing stale Phosh candidate binding temporary path")
    try:
        temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
        temporary.replace(path)
    except OSError as exc:
        raise PhoshCandidateBindingError(f"cannot write Phosh candidate binding: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()


def load_phosh_candidate_binding(path: Path) -> PhoshCandidateBindingEvidence:
    raw = _read_regular_file(Path(path), "Phosh candidate binding")
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhoshCandidateBindingError("Phosh candidate binding is not valid UTF-8 JSON") from exc
    expected = {item.name for item in fields(PhoshCandidateBindingEvidence)}
    if not isinstance(value, dict) or set(value) != expected:
        raise PhoshCandidateBindingError("Phosh candidate binding fields do not match schema-v1")
    if not isinstance(value.get("required_packages"), list):
        raise PhoshCandidateBindingError("Phosh candidate binding package list is invalid")
    try:
        evidence = PhoshCandidateBindingEvidence(
            **{**value, "required_packages": tuple(value["required_packages"])}
        )
    except (TypeError, ValueError) as exc:
        raise PhoshCandidateBindingError("Phosh candidate binding field types are invalid") from exc
    validate_phosh_candidate_binding(evidence)
    if raw != evidence.canonical_json().encode("utf-8"):
        raise PhoshCandidateBindingError("Phosh candidate binding is not canonical JSON")
    return evidence
