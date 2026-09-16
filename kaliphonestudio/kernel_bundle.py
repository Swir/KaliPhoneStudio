"""Fail-closed binding of kernel source/config/image evidence for first-boot candidates."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re

from .kernel_contract import (
    KernelBuildPlan,
    KernelCheckoutEvidence,
    KernelConfigEvidence,
    KernelContractError,
    KernelImageEvidence,
)


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_KERNEL_IMAGE_BYTES = 256 * 1024 * 1024


@dataclass(frozen=True)
class KernelCandidateEvidence:
    schema_version: int
    profile_id: str
    kernel_plan_sha256: str
    source_commit: str
    kernel_version: str
    checkout_evidence_sha256: str
    config_evidence_sha256: str
    image_evidence_sha256: str
    config_sha256: str
    image_sha256: str
    image_size: int
    arm64_magic_verified: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _hash_kernel_image(path: Path) -> tuple[str, int]:
    if not path.is_file() or path.is_symlink():
        raise KernelContractError("kernel image must be a regular non-symlink file")
    size = path.stat().st_size
    if size <= 0 or size > _MAX_KERNEL_IMAGE_BYTES:
        raise KernelContractError("kernel image size is outside the safety bound")
    digest = sha256()
    observed = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            observed += len(chunk)
            if observed > _MAX_KERNEL_IMAGE_BYTES:
                raise KernelContractError("kernel image changed beyond the safety bound")
            digest.update(chunk)
    if observed != size or path.stat().st_size != size:
        raise KernelContractError("kernel image changed while binding evidence")
    return digest.hexdigest(), size


def _require_sha256(value: str, label: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise KernelContractError(f"invalid {label}")


def bind_kernel_candidate_evidence(
    plan: KernelBuildPlan,
    checkout: KernelCheckoutEvidence,
    config: KernelConfigEvidence,
    image: KernelImageEvidence,
    *,
    kernel_image: Path,
) -> KernelCandidateEvidence:
    """Bind mutually-consistent host-side kernel evidence and re-hash the Image.

    This does not claim the kernel boots on hardware. It only prevents a first-boot
    candidate from silently mixing a different source commit, final .config or
    kernel Image after their individual checks completed.
    """
    if plan.schema_version != 1:
        raise KernelContractError("unsupported kernel plan schema")
    expected_plan_sha = plan.plan_sha256()
    evidence_items = (
        ("checkout", checkout),
        ("config", config),
        ("image", image),
    )
    for label, evidence in evidence_items:
        if evidence.schema_version != 1:
            raise KernelContractError(f"unsupported {label} evidence schema")
        if evidence.profile_id != plan.profile_id:
            raise KernelContractError(f"{label} evidence profile does not match kernel plan")
        if evidence.plan_sha256 != expected_plan_sha:
            raise KernelContractError(f"{label} evidence does not match kernel plan digest")

    if checkout.source_commit != plan.source_commit:
        raise KernelContractError("kernel checkout evidence source commit drifted")
    if checkout.kernel_version != plan.expected_kernel_version:
        raise KernelContractError("kernel checkout evidence version drifted")
    if config.required_config_count != len(plan.required_configs):
        raise KernelContractError("kernel config evidence requirement count drifted")
    if image.arm64_magic_verified is not True:
        raise KernelContractError("kernel image evidence lacks ARM64 header verification")

    for value, label in (
        (checkout.defconfig_sha256, "defconfig SHA-256"),
        (config.config_sha256, "kernel config SHA-256"),
        (image.image_sha256, "kernel image SHA-256"),
    ):
        _require_sha256(value, label)

    current_sha, current_size = _hash_kernel_image(kernel_image)
    if current_sha != image.image_sha256 or current_size != image.image_size:
        raise KernelContractError("kernel Image changed after verification")

    return KernelCandidateEvidence(
        schema_version=1,
        profile_id=plan.profile_id,
        kernel_plan_sha256=expected_plan_sha,
        source_commit=plan.source_commit,
        kernel_version=plan.expected_kernel_version,
        checkout_evidence_sha256=checkout.evidence_sha256(),
        config_evidence_sha256=config.evidence_sha256(),
        image_evidence_sha256=image.evidence_sha256(),
        config_sha256=config.config_sha256,
        image_sha256=image.image_sha256,
        image_size=image.image_size,
        arm64_magic_verified=True,
    )


def write_kernel_candidate_evidence(evidence: KernelCandidateEvidence, destination: Path) -> str:
    """Atomically write canonical kernel evidence and return its SHA-256."""
    if evidence.schema_version != 1:
        raise KernelContractError("unsupported kernel candidate evidence schema")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and (not destination.is_file() or destination.is_symlink()):
        raise KernelContractError("kernel evidence destination must be a regular file path")
    payload = evidence.canonical_json()
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists():
        raise KernelContractError("refusing to overwrite stale kernel evidence temporary file")
    try:
        temporary.write_text(payload, encoding="utf-8", newline="\n")
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return evidence.evidence_sha256()
