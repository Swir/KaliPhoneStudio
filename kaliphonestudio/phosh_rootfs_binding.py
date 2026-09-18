"""Fail-closed binding between Phosh package evidence and reviewed rootfs authority.

This host-only layer freezes the exact Phosh package-manifest identity against one
reviewed reproducible Kali ARM64 rootfs authority. It performs no device I/O,
chooses no storage target and cannot grant display, touch, hardware or Beta credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .phosh import (
    PhoshError,
    PhoshSourceLock,
    evaluate_phosh_package_manifest,
    load_phosh_source_lock,
    validate_phosh_source_lock,
)
from .rootfs import RootfsError
from .rootfs_authority import RootfsAuthorityRecord, authority_from_dict, load_rootfs_authority

_POLICY = "phosh-rootfs-authority-binding-v1"
_MAX_MANIFEST_BYTES = 16 * 1024 * 1024
_MAX_EVIDENCE_BYTES = 4 * 1024 * 1024


class PhoshRootfsBindingError(ValueError):
    """Raised when Phosh/rootfs authority identities are incomplete or drifted."""


@dataclass(frozen=True)
class PhoshRootfsAuthorityBindingEvidence:
    schema_version: int
    binding_policy: str
    phosh_source_lock_sha256: str
    phosh_upstream_commit: str
    rootfs_authority_sha256: str
    rootfs_authority_name: str
    rootfs_authority_commit: str
    rootfs_release_tag: str
    rootfs_variant: str
    rootfs_artifact_sha256: str
    rootfs_artifact_size: int
    package_manifest_sha256: str
    package_count: int
    required_packages: tuple[str, ...]
    installed_required_packages: tuple[tuple[str, str, str], ...]
    host_userspace_package_contract_satisfied: bool
    rootfs_authority_reviewed: bool
    ready_for_physical_candidate_binding: bool
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


def _read_regular_file(path: Path, label: str, maximum: int) -> bytes:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhoshRootfsBindingError(f"{label} must be a regular non-symlink file")
    try:
        before = source.stat()
        if before.st_size <= 0 or before.st_size > maximum:
            raise PhoshRootfsBindingError(f"{label} size is outside the safety limit")
        payload = source.read_bytes()
        after = source.stat()
    except OSError as exc:
        raise PhoshRootfsBindingError(f"cannot read {label}: {exc}") from exc
    if len(payload) != before.st_size:
        raise PhoshRootfsBindingError(f"{label} size changed while being read")
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or getattr(before, "st_ino", None) != getattr(after, "st_ino", None)
    ):
        raise PhoshRootfsBindingError(f"{label} changed while being read")
    return payload


def _validated_authority(authority: RootfsAuthorityRecord) -> RootfsAuthorityRecord:
    try:
        return authority_from_dict(asdict(authority))
    except RootfsError as exc:
        raise PhoshRootfsBindingError(str(exc)) from exc


def validate_phosh_rootfs_authority_binding(
    evidence: PhoshRootfsAuthorityBindingEvidence,
) -> None:
    if not isinstance(evidence, PhoshRootfsAuthorityBindingEvidence) or evidence.schema_version != 1:
        raise PhoshRootfsBindingError("Phosh rootfs authority binding must be schema-v1 typed evidence")
    if evidence.binding_policy != _POLICY:
        raise PhoshRootfsBindingError("unsupported Phosh rootfs authority binding policy")
    for label, value in (
        ("Phosh source lock", evidence.phosh_source_lock_sha256),
        ("rootfs authority", evidence.rootfs_authority_sha256),
        ("rootfs artifact", evidence.rootfs_artifact_sha256),
        ("package manifest", evidence.package_manifest_sha256),
    ):
        if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
            raise PhoshRootfsBindingError(f"{label} must be a lowercase SHA-256")
    if not isinstance(evidence.phosh_upstream_commit, str) or len(evidence.phosh_upstream_commit) != 40 or any(
        ch not in "0123456789abcdef" for ch in evidence.phosh_upstream_commit
    ):
        raise PhoshRootfsBindingError("Phosh upstream commit must be an exact lowercase 40-hex commit")
    if not isinstance(evidence.rootfs_authority_commit, str) or len(evidence.rootfs_authority_commit) != 40 or any(
        ch not in "0123456789abcdef" for ch in evidence.rootfs_authority_commit
    ):
        raise PhoshRootfsBindingError("rootfs authority commit must be an exact lowercase 40-hex commit")
    for label, value in (
        ("rootfs authority name", evidence.rootfs_authority_name),
        ("rootfs release tag", evidence.rootfs_release_tag),
        ("rootfs variant", evidence.rootfs_variant),
    ):
        if not isinstance(value, str) or not value.strip() or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
            raise PhoshRootfsBindingError(f"{label} must be bounded printable text")
    if not isinstance(evidence.rootfs_artifact_size, int) or isinstance(evidence.rootfs_artifact_size, bool) or evidence.rootfs_artifact_size <= 0:
        raise PhoshRootfsBindingError("rootfs artifact size must be a positive integer")
    if not isinstance(evidence.package_count, int) or isinstance(evidence.package_count, bool) or evidence.package_count <= 0:
        raise PhoshRootfsBindingError("package count must be a positive integer")
    if not isinstance(evidence.required_packages, tuple) or not evidence.required_packages:
        raise PhoshRootfsBindingError("required Phosh package set must be non-empty")
    if len(evidence.required_packages) != len(set(evidence.required_packages)):
        raise PhoshRootfsBindingError("required Phosh packages must be unique")
    installed_names: list[str] = []
    for item in evidence.installed_required_packages:
        if not isinstance(item, tuple) or len(item) != 3:
            raise PhoshRootfsBindingError("installed Phosh package entries must be typed triples")
        package, version, architecture = item
        if package not in evidence.required_packages or not version or architecture not in {"arm64", "all"}:
            raise PhoshRootfsBindingError("installed Phosh package entry is invalid")
        installed_names.append(package)
    if len(installed_names) != len(set(installed_names)):
        raise PhoshRootfsBindingError("installed Phosh package entries must be unique")
    if tuple(installed_names) != evidence.required_packages:
        raise PhoshRootfsBindingError("installed Phosh package order/set drifted from required packages")
    if evidence.host_userspace_package_contract_satisfied is not True:
        raise PhoshRootfsBindingError("Phosh host userspace package contract is incomplete")
    if evidence.rootfs_authority_reviewed is not True:
        raise PhoshRootfsBindingError("rootfs authority must remain explicitly reviewed")
    if evidence.ready_for_physical_candidate_binding is not True:
        raise PhoshRootfsBindingError("complete host binding must be ready only for later physical candidate binding")
    if evidence.physical_validation_required is not True:
        raise PhoshRootfsBindingError("Phosh binding must require physical validation")
    for name in (
        "display_verified",
        "touch_verified",
        "hardware_verified",
        "beta_release_authorized",
        "beta_gate_credit",
    ):
        if getattr(evidence, name) is not False:
            raise PhoshRootfsBindingError(f"host Phosh binding cannot promote {name}")


def build_phosh_rootfs_authority_binding(
    lock: PhoshSourceLock,
    authority: RootfsAuthorityRecord,
    package_manifest: bytes,
) -> PhoshRootfsAuthorityBindingEvidence:
    """Bind exact Phosh package bytes to one reviewed rootfs authority, host-side only."""
    try:
        validate_phosh_source_lock(lock)
    except PhoshError as exc:
        raise PhoshRootfsBindingError(str(exc)) from exc
    authority = _validated_authority(authority)
    if authority.architecture != lock.architecture:
        raise PhoshRootfsBindingError("Phosh/rootfs architecture mismatch")
    if not isinstance(package_manifest, bytes):
        raise PhoshRootfsBindingError("package manifest must be exact bytes")
    try:
        package_evidence = evaluate_phosh_package_manifest(
            lock,
            package_manifest,
            rootfs_artifact_sha256=authority.artifact_sha256,
        )
    except PhoshError as exc:
        raise PhoshRootfsBindingError(str(exc)) from exc
    if package_evidence.package_manifest_sha256 != authority.package_manifest_sha256:
        raise PhoshRootfsBindingError("Phosh package manifest digest differs from reviewed rootfs authority")
    if package_evidence.package_count != authority.package_count:
        raise PhoshRootfsBindingError("Phosh package count differs from reviewed rootfs authority")
    if package_evidence.host_userspace_package_contract_satisfied is not True or package_evidence.missing_packages:
        missing = ", ".join(package_evidence.missing_packages) or "unknown"
        raise PhoshRootfsBindingError(f"reviewed rootfs is missing required Phosh packages: {missing}")
    if (
        package_evidence.physical_validation_required is not True
        or package_evidence.display_verified is not False
        or package_evidence.touch_verified is not False
        or package_evidence.hardware_verified is not False
        or package_evidence.beta_gate_credit is not False
    ):
        raise PhoshRootfsBindingError("Phosh package evidence contains forbidden hardware/Beta promotion")

    evidence = PhoshRootfsAuthorityBindingEvidence(
        schema_version=1,
        binding_policy=_POLICY,
        phosh_source_lock_sha256=lock.lock_sha256(),
        phosh_upstream_commit=lock.upstream_commit,
        rootfs_authority_sha256=authority.authority_sha256(),
        rootfs_authority_name=authority.authority_name,
        rootfs_authority_commit=authority.authority_commit,
        rootfs_release_tag=authority.release_tag,
        rootfs_variant=authority.variant,
        rootfs_artifact_sha256=authority.artifact_sha256,
        rootfs_artifact_size=authority.artifact_size,
        package_manifest_sha256=authority.package_manifest_sha256,
        package_count=authority.package_count,
        required_packages=lock.required_packages,
        installed_required_packages=package_evidence.installed_required_packages,
        host_userspace_package_contract_satisfied=True,
        rootfs_authority_reviewed=True,
        ready_for_physical_candidate_binding=True,
        physical_validation_required=True,
        display_verified=False,
        touch_verified=False,
        hardware_verified=False,
        beta_release_authorized=False,
        beta_gate_credit=False,
    )
    validate_phosh_rootfs_authority_binding(evidence)
    return evidence


def build_phosh_rootfs_authority_binding_from_paths(
    source_lock_path: Path,
    rootfs_authority_path: Path,
    package_manifest_path: Path,
) -> PhoshRootfsAuthorityBindingEvidence:
    try:
        lock = load_phosh_source_lock(Path(source_lock_path))
        authority = load_rootfs_authority(Path(rootfs_authority_path))
    except (PhoshError, RootfsError) as exc:
        raise PhoshRootfsBindingError(str(exc)) from exc
    payload = _read_regular_file(Path(package_manifest_path), "rootfs package manifest", _MAX_MANIFEST_BYTES)
    return build_phosh_rootfs_authority_binding(lock, authority, payload)


def write_phosh_rootfs_authority_binding(
    evidence: PhoshRootfsAuthorityBindingEvidence,
    destination: Path,
) -> str:
    validate_phosh_rootfs_authority_binding(evidence)
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise PhoshRootfsBindingError("refusing to overwrite Phosh rootfs authority binding")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise PhoshRootfsBindingError("refusing stale Phosh rootfs authority binding temporary path")
    try:
        temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
        temporary.replace(path)
    except OSError as exc:
        raise PhoshRootfsBindingError(f"cannot write Phosh rootfs authority binding: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()


def load_phosh_rootfs_authority_binding(path: Path) -> PhoshRootfsAuthorityBindingEvidence:
    raw = _read_regular_file(Path(path), "Phosh rootfs authority binding", _MAX_EVIDENCE_BYTES)
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhoshRootfsBindingError("Phosh rootfs authority binding is not valid UTF-8 JSON") from exc
    expected = {item.name for item in fields(PhoshRootfsAuthorityBindingEvidence)}
    if not isinstance(value, dict) or set(value) != expected:
        raise PhoshRootfsBindingError("Phosh rootfs authority binding fields do not match schema-v1")
    if not isinstance(value.get("required_packages"), list) or not isinstance(value.get("installed_required_packages"), list):
        raise PhoshRootfsBindingError("Phosh rootfs authority binding list fields are invalid")
    try:
        installed = tuple(tuple(item) for item in value["installed_required_packages"])
        evidence = PhoshRootfsAuthorityBindingEvidence(
            **{
                **value,
                "required_packages": tuple(value["required_packages"]),
                "installed_required_packages": installed,
            }
        )
    except (TypeError, ValueError) as exc:
        raise PhoshRootfsBindingError("Phosh rootfs authority binding field types are invalid") from exc
    validate_phosh_rootfs_authority_binding(evidence)
    if raw != evidence.canonical_json().encode("utf-8"):
        raise PhoshRootfsBindingError("Phosh rootfs authority binding is not canonical JSON")
    return evidence
