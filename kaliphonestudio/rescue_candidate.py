"""Build a profile-formatted rescue ramdisk from verified reproducible payload evidence."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import tempfile

from .initramfs import InitramfsError, build_reproducible_initramfs
from .profiles import DeviceProfile
from .rescue_payload import RescuePayloadError
from .rescue_payload_repro import (
    RescuePayloadReproEvidence,
    stage_reproducible_payload,
)


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
    verified: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


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
    """Create a deterministic profile-compressed rescue ramdisk.

    This is an offline host artifact only. It does not authorize temporary or
    persistent boot and it does not satisfy any hardware Beta gate.
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

    return RescueCandidateEvidence(
        schema_version=1,
        profile_id=profile.profile_id,
        payload_repro_evidence_sha256=repro.evidence_sha256(),
        payload_staging_evidence_sha256=staged.evidence_sha256(),
        initramfs_evidence_sha256=initramfs.evidence_sha256(),
        ramdisk_sha256=initramfs.artifact_sha256,
        ramdisk_size=initramfs.artifact_size,
        ramdisk_compression=compression,
        init_sha256=initramfs.init_sha256,
        verified=True,
    )


def write_rescue_candidate_evidence(
    evidence: RescueCandidateEvidence,
    destination: Path,
) -> str:
    if evidence.schema_version != 1 or evidence.verified is not True:
        raise RescuePayloadError("cannot serialize unverified rescue candidate evidence")
    if not evidence.profile_id or "/" not in evidence.profile_id:
        raise RescuePayloadError("rescue candidate evidence has invalid profile_id")
    for value, label in (
        (evidence.payload_repro_evidence_sha256, "payload reproducibility evidence"),
        (evidence.payload_staging_evidence_sha256, "payload staging evidence"),
        (evidence.initramfs_evidence_sha256, "initramfs evidence"),
        (evidence.ramdisk_sha256, "ramdisk"),
        (evidence.init_sha256, "init"),
    ):
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise RescuePayloadError(f"{label} must be a lowercase SHA-256 digest")
    if evidence.ramdisk_size <= 0 or evidence.ramdisk_compression not in {"gzip", "lz4"}:
        raise RescuePayloadError("rescue candidate evidence has invalid ramdisk metadata")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
    temporary.replace(destination)
    return evidence.evidence_sha256()
