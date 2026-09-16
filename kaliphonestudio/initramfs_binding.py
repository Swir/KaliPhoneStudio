"""Bind deterministic rescue-initramfs evidence to an approved boot build plan."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re

from .boot_builder import BootBuildPlan
from .boot_image import BootImageError
from .initramfs import InitramfsEvidence, InitramfsError, verify_initramfs_artifact


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_INITRAMFS_COMPRESSION_TO_BOOT_POLICY = {
    "gzip-mtime0-level9": "gzip",
    "lz4-legacy-literal-v1": "lz4",
}


@dataclass(frozen=True)
class InitramfsBootBindingEvidence:
    schema_version: int
    profile_id: str
    boot_plan_sha256: str
    initramfs_evidence_sha256: str
    ramdisk_sha256: str
    ramdisk_size: int
    init_sha256: str
    ramdisk_compression: str
    verified: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _require_sha256(value: str, label: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise InitramfsError(f"{label} must be a lowercase SHA-256 digest")


def bind_initramfs_to_boot_plan(
    plan: BootBuildPlan,
    initramfs: InitramfsEvidence,
    *,
    artifact: Path,
) -> InitramfsBootBindingEvidence:
    """Prove that the verified initramfs bytes are exactly the plan's ramdisk input.

    This is a host-side evidence bridge only. It does not authorize a phone boot by
    itself and does not bypass the existing profile/provenance/round-trip gates.
    """
    if plan.schema_version != 1:
        raise BootImageError("unsupported boot build plan schema for initramfs binding")
    if not plan.profile_id:
        raise BootImageError("initramfs binding requires a profile-bound boot plan")

    ramdisks = [item for item in plan.inputs if item.name == "ramdisk"]
    if len(ramdisks) != 1:
        raise BootImageError("boot plan must contain exactly one ramdisk input")
    planned = ramdisks[0]
    if Path(planned.path).name != planned.path or planned.path in {"", ".", ".."}:
        raise BootImageError("boot plan contains an unsafe ramdisk path")
    _require_sha256(planned.sha256, "planned ramdisk")
    if not isinstance(planned.size, int) or isinstance(planned.size, bool) or planned.size <= 0:
        raise BootImageError("boot plan contains an invalid ramdisk size")

    _require_sha256(initramfs.artifact_sha256, "initramfs artifact")
    _require_sha256(initramfs.entry_manifest_sha256, "initramfs entry manifest")
    _require_sha256(initramfs.init_sha256, "initramfs /init")
    verify_initramfs_artifact(initramfs, artifact)

    compression = _INITRAMFS_COMPRESSION_TO_BOOT_POLICY.get(initramfs.compression)
    if compression is None:
        raise BootImageError("initramfs compression has no approved boot-policy mapping")
    if compression != plan.ramdisk_compression:
        raise BootImageError(
            "verified initramfs compression does not match the boot plan ramdisk policy"
        )
    if initramfs.artifact_sha256 != planned.sha256 or initramfs.artifact_size != planned.size:
        raise BootImageError("verified initramfs does not match the boot plan ramdisk input")

    return InitramfsBootBindingEvidence(
        schema_version=1,
        profile_id=plan.profile_id,
        boot_plan_sha256=plan.plan_sha256(),
        initramfs_evidence_sha256=initramfs.evidence_sha256(),
        ramdisk_sha256=planned.sha256,
        ramdisk_size=planned.size,
        init_sha256=initramfs.init_sha256,
        ramdisk_compression=compression,
        verified=True,
    )


def write_initramfs_boot_binding(
    evidence: InitramfsBootBindingEvidence,
    destination: Path,
) -> str:
    if evidence.schema_version != 1 or evidence.verified is not True:
        raise InitramfsError("cannot serialize an unverified initramfs/boot binding")
    for value, label in (
        (evidence.boot_plan_sha256, "boot plan"),
        (evidence.initramfs_evidence_sha256, "initramfs evidence"),
        (evidence.ramdisk_sha256, "ramdisk"),
        (evidence.init_sha256, "initramfs /init"),
    ):
        _require_sha256(value, label)
    if evidence.ramdisk_size <= 0:
        raise InitramfsError("initramfs/boot binding contains an invalid ramdisk size")
    if evidence.ramdisk_compression not in {"gzip", "lz4", "none"}:
        raise InitramfsError("initramfs/boot binding contains an invalid compression policy")

    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = evidence.canonical_json()
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8", newline="\n")
    temporary.replace(destination)
    return evidence.evidence_sha256()
