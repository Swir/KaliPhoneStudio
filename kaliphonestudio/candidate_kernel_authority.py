"""Bind a first-boot candidate manifest to a reviewed host kernel authority.

This is an offline provenance link only.  A reviewed reproducible kernel remains
unverified on physical hardware, so the resulting evidence always carries
``hardware_verified=false`` and ``beta_gate_credit=false``.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re

from .candidate import FirstBootCandidateManifest
from .kernel_authority import KernelAuthorityRecord, authority_from_dict
from .kernel_contract import KernelContractError


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class FirstBootKernelAuthorityEvidence:
    schema_version: int
    profile_id: str
    first_boot_manifest_sha256: str
    kernel_authority_sha256: str
    authority_name: str
    authority_run_id: int
    authority_commit: str
    authority_artifact_id: int
    source_commit: str
    kernel_plan_sha256: str
    toolchain_lock_sha256: str
    build_recipe_sha256: str
    reproducible_environment_sha256: str
    build_a_run_evidence_sha256: str
    build_b_run_evidence_sha256: str
    reproducibility_evidence_sha256: str
    reproducibility_binding_sha256: str
    config_sha256: str
    config_size: int
    image_sha256: str
    image_size: int
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
        raise KernelContractError(f"{label} must be a lowercase SHA-256 digest")
    return value


def bind_first_boot_candidate_to_kernel_authority(
    manifest: FirstBootCandidateManifest,
    authority: KernelAuthorityRecord,
) -> FirstBootKernelAuthorityEvidence:
    if not isinstance(manifest, FirstBootCandidateManifest) or manifest.schema_version != 8:
        raise KernelContractError("kernel authority binding requires a schema-v8 first-boot manifest")
    if manifest.kernel_reproducible is not True:
        raise KernelContractError("first-boot candidate is not marked strictly kernel-reproducible")
    if manifest.kernel_distinct_build_roots_verified is not True:
        raise KernelContractError("first-boot candidate lacks distinct kernel build-root proof")

    if not isinstance(authority, KernelAuthorityRecord):
        raise KernelContractError("kernel authority binding requires a typed authority record")
    authority = authority_from_dict(asdict(authority))
    if authority.profile_id != manifest.profile_id:
        raise KernelContractError("kernel authority profile does not match first-boot candidate")

    comparisons = (
        (manifest.kernel_source_commit, authority.source_commit, "source commit"),
        (manifest.kernel_plan_sha256, authority.kernel_plan_sha256, "kernel plan"),
        (manifest.kernel_toolchain_lock_sha256, authority.toolchain_lock_sha256, "toolchain lock"),
        (manifest.kernel_build_recipe_sha256, authority.build_recipe_sha256, "build recipe"),
        (manifest.kernel_reproducible_environment_sha256, authority.reproducible_environment_sha256, "reproducibility environment"),
        (manifest.kernel_build_a_run_evidence_sha256, authority.build_a_run_evidence_sha256, "build A run evidence"),
        (manifest.kernel_build_b_run_evidence_sha256, authority.build_b_run_evidence_sha256, "build B run evidence"),
        (manifest.kernel_reproducibility_evidence_sha256, authority.reproducibility_evidence_sha256, "reproducibility evidence"),
        (manifest.kernel_reproducibility_binding_evidence_sha256, authority.reproducibility_binding_sha256, "reproducibility binding"),
        (manifest.kernel_config_sha256, authority.config_sha256, "kernel config"),
        (manifest.kernel_image_sha256, authority.image_sha256, "kernel Image"),
    )
    for left, right, label in comparisons:
        if label != "source commit":
            _digest(left, f"candidate {label}")
            _digest(right, f"authority {label}")
        if left != right:
            raise KernelContractError(f"kernel authority binding mismatch: {label}")
    if manifest.kernel_image_size != authority.image_size:
        raise KernelContractError("kernel authority binding mismatch: Image size")

    return FirstBootKernelAuthorityEvidence(
        schema_version=1,
        profile_id=manifest.profile_id,
        first_boot_manifest_sha256=_digest(manifest.manifest_sha256(), "first-boot manifest"),
        kernel_authority_sha256=_digest(authority.authority_sha256(), "kernel authority"),
        authority_name=authority.authority_name,
        authority_run_id=authority.authority_run_id,
        authority_commit=authority.authority_commit,
        authority_artifact_id=authority.authority_artifact_id,
        source_commit=authority.source_commit,
        kernel_plan_sha256=authority.kernel_plan_sha256,
        toolchain_lock_sha256=authority.toolchain_lock_sha256,
        build_recipe_sha256=authority.build_recipe_sha256,
        reproducible_environment_sha256=authority.reproducible_environment_sha256,
        build_a_run_evidence_sha256=authority.build_a_run_evidence_sha256,
        build_b_run_evidence_sha256=authority.build_b_run_evidence_sha256,
        reproducibility_evidence_sha256=authority.reproducibility_evidence_sha256,
        reproducibility_binding_sha256=authority.reproducibility_binding_sha256,
        config_sha256=authority.config_sha256,
        config_size=authority.config_size,
        image_sha256=authority.image_sha256,
        image_size=authority.image_size,
        strict_byte_identical=True,
        distinct_build_roots_verified=True,
        reviewed=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def write_first_boot_kernel_authority_evidence(
    evidence: FirstBootKernelAuthorityEvidence,
    destination: Path,
) -> str:
    if not isinstance(evidence, FirstBootKernelAuthorityEvidence) or evidence.schema_version != 1:
        raise KernelContractError("invalid first-boot kernel authority evidence")
    if (
        evidence.strict_byte_identical is not True
        or evidence.distinct_build_roots_verified is not True
        or evidence.reviewed is not True
    ):
        raise KernelContractError("first-boot kernel authority evidence is not strict/reviewed")
    if evidence.hardware_verified is not False or evidence.beta_gate_credit is not False:
        raise KernelContractError("first-boot kernel authority evidence cannot claim hardware/Beta credit")
    path = Path(destination)
    if path.exists():
        raise KernelContractError("refusing to overwrite first-boot kernel authority evidence")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists():
        raise KernelContractError("refusing stale first-boot kernel authority temporary file")
    try:
        temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()
