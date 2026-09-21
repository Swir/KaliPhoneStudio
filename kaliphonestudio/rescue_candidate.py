"""Build a profile-formatted rescue ramdisk from verified reproducible payload evidence."""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path
import re
import tempfile
from typing import Any

from .initramfs import InitramfsError, build_reproducible_initramfs
from .profiles import DeviceProfile
from .rescue_payload import RescuePayloadError
from .rescue_payload_repro import (
    RescuePayloadReproEvidence,
    stage_reproducible_payload,
)


_RESCUE_PROBE_POLICY = "profile+repro-payload+staging+init-v1"
_RESCUE_PROBE_PATH = Path("etc") / "kaliphonestudio" / "rescue-probe-id"
_ROOTFS_STAGE_HELPER_SOURCE = Path("rescue") / "kps-rootfs-stage-once"
_ROOTFS_STAGE_HELPER_DESTINATION = Path("sbin") / "kps-rootfs-stage-once"
_MAX_ROOTFS_STAGE_HELPER_BYTES = 64 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class RescueCandidateEvidence:
    schema_version: int
    profile_id: str
    payload_repro_evidence_sha256: str
    payload_staging_evidence_sha256: str
    initramfs_evidence_sha256: str
    ramdisk_sha256: str
    ramdisk_size: int
    ramdisk_compression: str
    init_sha256: str
    rescue_probe_id: str
    rescue_probe_file_sha256: str
    rescue_probe_policy: str
    verified: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise RescuePayloadError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _probe_material(
    *,
    profile_id: str,
    payload_repro_evidence_sha256: str,
    payload_staging_evidence_sha256: str,
    init_sha256: str,
) -> tuple[str, bytes]:
    material = {
        "schema_version": 1,
        "profile_id": profile_id,
        "payload_repro_evidence_sha256": payload_repro_evidence_sha256,
        "payload_staging_evidence_sha256": payload_staging_evidence_sha256,
        "init_sha256": init_sha256,
        "policy": _RESCUE_PROBE_POLICY,
    }
    canonical = json.dumps(material, sort_keys=True, separators=(",", ":")) + "\n"
    probe_id = sha256(canonical.encode("utf-8")).hexdigest()
    return probe_id, (probe_id + "\n").encode("ascii")


def _install_probe_file(staging_root: Path, payload: bytes) -> str:
    if len(payload) != 65 or payload[-1:] != b"\n" or not _SHA256_RE.fullmatch(payload[:-1].decode("ascii")):
        raise RescuePayloadError("rescue probe payload is not canonical")
    destination = staging_root / _RESCUE_PROBE_PATH
    parent = destination.parent
    if parent.exists() and (parent.is_symlink() or not parent.is_dir()):
        raise RescuePayloadError("rescue probe parent path is unsafe")
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise RescuePayloadError("refusing to overwrite staged rescue probe id")
    destination.write_bytes(payload)
    destination.chmod(0o444)
    if destination.read_bytes() != payload:
        raise RescuePayloadError("staged rescue probe bytes changed after write")
    return sha256(payload).hexdigest()


def _install_rootfs_stage_helper(*, repository_root: Path, staging_root: Path) -> str:
    """Install the explicit local-console rootfs writer into the rescue ramdisk.

    The helper is never invoked automatically. Its exact bytes are included in
    the deterministic initramfs manifest/ramdisk hash, while the helper itself
    still requires a passed execution-gate file, live mount revalidation and a
    fresh exact operator confirmation before any persistent staging write.
    """

    try:
        root = repository_root.resolve(strict=True)
    except OSError as exc:
        raise RescuePayloadError(f"cannot resolve repository root for rootfs stage helper: {exc}") from exc
    source = root / _ROOTFS_STAGE_HELPER_SOURCE
    if source.is_symlink() or not source.is_file():
        raise RescuePayloadError("rootfs stage helper must be a regular non-symlink repository file")
    try:
        resolved = source.resolve(strict=True)
        resolved.relative_to(root)
        payload = source.read_bytes()
    except (OSError, ValueError) as exc:
        raise RescuePayloadError(f"cannot load rootfs stage helper safely: {exc}") from exc
    if not payload.startswith(b"#!/bin/sh\n") or not (1 <= len(payload) <= _MAX_ROOTFS_STAGE_HELPER_BYTES):
        raise RescuePayloadError("rootfs stage helper has invalid script bytes or size")
    for marker in (
        b'KPS_POLICY="interactive-rootfs-stage-v1"',
        b'"execution_gate_passed":true',
        b'"explicit_operator_confirmation_required":true',
        b"KPS_ROOTFS_STAGE_BETA_CREDIT=false",
    ):
        if marker not in payload:
            raise RescuePayloadError("rootfs stage helper is missing a required fail-closed contract marker")

    destination = staging_root / _ROOTFS_STAGE_HELPER_DESTINATION
    if destination.exists() or destination.is_symlink():
        raise RescuePayloadError("refusing to overwrite staged rootfs stage helper")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    destination.chmod(0o700)
    if destination.read_bytes() != payload:
        raise RescuePayloadError("staged rootfs stage helper bytes changed after write")
    return sha256(payload).hexdigest()


def validate_rescue_candidate_evidence(evidence: RescueCandidateEvidence) -> None:
    if not isinstance(evidence, RescueCandidateEvidence) or evidence.schema_version != 2:
        raise RescuePayloadError("rescue candidate evidence must be schema-v2 typed evidence")
    if evidence.verified is not True:
        raise RescuePayloadError("cannot use unverified rescue candidate evidence")
    if not isinstance(evidence.profile_id, str) or "/" not in evidence.profile_id:
        raise RescuePayloadError("rescue candidate evidence has invalid profile_id")
    for value, label in (
        (evidence.payload_repro_evidence_sha256, "payload reproducibility evidence"),
        (evidence.payload_staging_evidence_sha256, "payload staging evidence"),
        (evidence.initramfs_evidence_sha256, "initramfs evidence"),
        (evidence.ramdisk_sha256, "ramdisk"),
        (evidence.init_sha256, "init"),
        (evidence.rescue_probe_id, "rescue probe id"),
        (evidence.rescue_probe_file_sha256, "rescue probe file"),
    ):
        _require_sha256(value, label)
    if evidence.ramdisk_size <= 0 or evidence.ramdisk_compression not in {"gzip", "lz4"}:
        raise RescuePayloadError("rescue candidate evidence has invalid ramdisk metadata")
    if evidence.rescue_probe_policy != _RESCUE_PROBE_POLICY:
        raise RescuePayloadError("rescue candidate evidence has an unsupported rescue probe policy")
    expected_probe_id, expected_probe_payload = _probe_material(
        profile_id=evidence.profile_id,
        payload_repro_evidence_sha256=evidence.payload_repro_evidence_sha256,
        payload_staging_evidence_sha256=evidence.payload_staging_evidence_sha256,
        init_sha256=evidence.init_sha256,
    )
    if evidence.rescue_probe_id != expected_probe_id:
        raise RescuePayloadError("rescue probe id is detached from candidate provenance")
    if evidence.rescue_probe_file_sha256 != sha256(expected_probe_payload).hexdigest():
        raise RescuePayloadError("rescue probe file digest is detached from the probe id")


def build_verified_rescue_candidate(
    *,
    profile: DeviceProfile,
    repro: RescuePayloadReproEvidence,
    lock_manifest_path: Path,
    repository_root: Path,
    busybox: Path,
    applet_list: Path,
    destination: Path,
) -> RescueCandidateEvidence:
    """Create a deterministic profile-compressed rescue ramdisk with a provenance probe id.

    The probe id is deterministic and bound to the exact profile, reproducible
    payload, staged payload evidence and reviewed /init bytes. The locked /init
    prints this id when the physical rescue userspace is actually reached. This
    remains host-only evidence and never authorizes or performs a phone boot.
    """

    if profile.data.get("arch") not in {"arm64", "aarch64"}:
        raise RescuePayloadError("rescue candidate requires an ARM64 device profile")
    boot = profile.data.get("boot")
    if not isinstance(boot, dict):
        raise RescuePayloadError("device profile has no boot contract")
    compression = boot.get("ramdisk_compression")
    if compression not in {"gzip", "lz4"}:
        raise RescuePayloadError(
            "verified rescue candidate currently requires gzip or lz4 ramdisk compression"
        )
    if destination.exists():
        raise RescuePayloadError("refusing to overwrite an existing rescue candidate")

    with tempfile.TemporaryDirectory(prefix="kaliphonestudio-rescue-") as temporary:
        staging_root = Path(temporary) / "staging"
        staged = stage_reproducible_payload(
            repro=repro,
            lock_manifest_path=lock_manifest_path,
            repository_root=repository_root,
            busybox=busybox,
            applet_list=applet_list,
            destination=staging_root,
        )
        probe_id, probe_payload = _probe_material(
            profile_id=profile.profile_id,
            payload_repro_evidence_sha256=repro.evidence_sha256(),
            payload_staging_evidence_sha256=staged.evidence_sha256(),
            init_sha256=staged.init_sha256,
        )
        probe_file_sha256 = _install_probe_file(staging_root, probe_payload)
        _install_rootfs_stage_helper(repository_root=repository_root, staging_root=staging_root)
        initramfs = build_reproducible_initramfs(
            staging_root,
            destination,
            compression=compression,
        )

    if initramfs.init_sha256 != staged.init_sha256:
        destination.unlink(missing_ok=True)
        raise InitramfsError("rescue candidate /init digest diverges from verified payload staging")
    if initramfs.artifact_size <= 0 or not initramfs.reproducible:
        destination.unlink(missing_ok=True)
        raise InitramfsError("rescue candidate lacks reproducible initramfs evidence")

    evidence = RescueCandidateEvidence(
        schema_version=2,
        profile_id=profile.profile_id,
        payload_repro_evidence_sha256=repro.evidence_sha256(),
        payload_staging_evidence_sha256=staged.evidence_sha256(),
        initramfs_evidence_sha256=initramfs.evidence_sha256(),
        ramdisk_sha256=initramfs.artifact_sha256,
        ramdisk_size=initramfs.artifact_size,
        ramdisk_compression=compression,
        init_sha256=initramfs.init_sha256,
        rescue_probe_id=probe_id,
        rescue_probe_file_sha256=probe_file_sha256,
        rescue_probe_policy=_RESCUE_PROBE_POLICY,
        verified=True,
    )
    validate_rescue_candidate_evidence(evidence)
    return evidence


def load_rescue_candidate_evidence(path: Path) -> RescueCandidateEvidence:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise RescuePayloadError("rescue candidate evidence must be a regular non-symlink file")
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RescuePayloadError(f"cannot load rescue candidate evidence: {exc}") from exc
    if not isinstance(raw, dict):
        raise RescuePayloadError("rescue candidate evidence must be a JSON object")
    expected = {item.name for item in fields(RescueCandidateEvidence)}
    if set(raw) != expected:
        raise RescuePayloadError("rescue candidate evidence fields do not match schema-v2")
    try:
        evidence = RescueCandidateEvidence(**raw)
    except TypeError as exc:
        raise RescuePayloadError("rescue candidate evidence types are invalid") from exc
    validate_rescue_candidate_evidence(evidence)
    return evidence


def write_rescue_candidate_evidence(
    evidence: RescueCandidateEvidence,
    destination: Path,
) -> str:
    validate_rescue_candidate_evidence(evidence)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise RescuePayloadError("refusing to overwrite existing rescue candidate evidence")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise RescuePayloadError("refusing to overwrite rescue candidate evidence temporary path")
    temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
    temporary.replace(destination)
    return evidence.evidence_sha256()
