"""Executable, device-independent build contract for the KaliPhoneStudio Phosh rootfs.

The existing minimal Kali rootfs remains the reviewed reproducibility authority. This
module defines a separate candidate path for a Phosh-capable ARM64 userspace based on
the pinned NetHunter Pro source lock. It deliberately does not grant hardware, device
support, reproducibility-authority or Beta credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path, PurePath
import re
from typing import Any

from .phosh import PhoshSourceLock, validate_phosh_source_lock


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SIZE_RE = re.compile(r"^[1-9][0-9]*[KMG]$")
_SAFE_ARTIFACT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*\.tar\.xz$")


class PhoshBuildError(ValueError):
    """Raised when the executable Phosh rootfs build contract is unsafe or ambiguous."""


@dataclass(frozen=True)
class PhoshRootfsBuildContract:
    schema_version: int
    phosh_source_lock_sha256: str
    architecture: str
    environment: str
    family: str
    debian_suite: str
    mobian_suite: str
    mirror: str
    contrib: bool
    nonfree: bool
    scratch_size: str
    generic_artifact: str
    staged_artifact: str
    double_build_required: bool
    canonicalization_required: bool
    physical_validation_required: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def contract_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PhoshRootfsBuildPlan:
    schema_version: int
    upstream_commit: str
    source_lock_sha256: str
    build_contract_sha256: str
    base_argv: tuple[str, ...]
    stage_argv: tuple[str, ...]
    stage_recipe_sha256: str
    generic_artifact: str
    staged_artifact: str
    physical_validation_required: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"


@dataclass(frozen=True)
class PhoshRootfsBuildEvidence:
    schema_version: int
    upstream_commit: str
    source_lock_sha256: str
    build_contract_sha256: str
    build_plan_sha256: str
    artifact_sha256: str
    artifact_size: int
    package_manifest_sha256: str
    package_count: int
    phosh_package_contract_satisfied: bool
    reproducibility_authority: bool
    physical_validation_required: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PhoshBuildError(f"{label} must be a non-empty string")
    return value


def _safe_artifact(value: Any, label: str) -> str:
    name = _text(value, label)
    if PurePath(name).name != name or not _SAFE_ARTIFACT_RE.fullmatch(name):
        raise PhoshBuildError(f"{label} must be a safe tar.xz basename")
    return name


def validate_phosh_rootfs_build_contract(source_lock: PhoshSourceLock, contract: PhoshRootfsBuildContract) -> None:
    validate_phosh_source_lock(source_lock)
    if contract.schema_version != 1:
        raise PhoshBuildError("unsupported Phosh rootfs build-contract schema")
    if not _SHA256_RE.fullmatch(contract.phosh_source_lock_sha256):
        raise PhoshBuildError("Phosh source-lock binding must be a lowercase SHA-256 digest")
    if contract.phosh_source_lock_sha256 != source_lock.lock_sha256():
        raise PhoshBuildError("Phosh rootfs build contract is not bound to the current source lock")
    if (contract.architecture != source_lock.architecture or contract.environment != source_lock.environment or contract.family != source_lock.family):
        raise PhoshBuildError("Phosh rootfs build target does not match the source lock")
    if contract.debian_suite != "kali-rolling":
        raise PhoshBuildError("Phosh rootfs build must explicitly use kali-rolling")
    if contract.mobian_suite != "forky":
        raise PhoshBuildError("Phosh rootfs build must explicitly pin the reviewed Mobian suite")
    if not contract.mirror.startswith("https://"):
        raise PhoshBuildError("Phosh rootfs mirror must use HTTPS")
    if contract.contrib is not True or contract.nonfree is not True:
        raise PhoshBuildError("QCOM Phosh rootfs requires explicit contrib and non-free repositories")
    if not _SIZE_RE.fullmatch(contract.scratch_size):
        raise PhoshBuildError("Phosh rootfs scratch size must be an explicit K/M/G quantity")
    _safe_artifact(contract.generic_artifact, "generic Phosh rootfs artifact")
    _safe_artifact(contract.staged_artifact, "staged Phosh rootfs artifact")
    if contract.generic_artifact == contract.staged_artifact:
        raise PhoshBuildError("generic and staged Phosh rootfs artifacts must be distinct")
    if contract.double_build_required is not True or contract.canonicalization_required is not True:
        raise PhoshBuildError("Phosh rootfs candidate must require canonicalization and independent double build")
    if contract.physical_validation_required is not True:
        raise PhoshBuildError("Phosh rootfs candidate must require physical validation")
    if contract.hardware_verified is not False or contract.beta_gate_credit is not False:
        raise PhoshBuildError("host-side Phosh rootfs build contract cannot grant hardware/Beta credit")


def load_phosh_rootfs_build_contract(path: Path, source_lock: PhoshSourceLock) -> PhoshRootfsBuildContract:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PhoshBuildError(f"cannot read Phosh rootfs build contract: {exc}") from exc
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "phosh_source_lock_sha256", "build", "policy"}:
        raise PhoshBuildError("unexpected Phosh rootfs build-contract top-level fields")
    build = raw["build"]
    policy = raw["policy"]
    required_build = {"architecture", "environment", "family", "debian_suite", "mobian_suite", "mirror", "contrib", "nonfree", "scratch_size", "generic_artifact", "staged_artifact", "double_build_required", "canonicalization_required"}
    if not isinstance(build, dict) or set(build) != required_build:
        raise PhoshBuildError("unexpected Phosh rootfs build fields")
    if not isinstance(policy, dict) or set(policy) != {"physical_validation_required", "hardware_verified", "beta_gate_credit"}:
        raise PhoshBuildError("unexpected Phosh rootfs build policy fields")
    contract = PhoshRootfsBuildContract(
        schema_version=raw["schema_version"],
        phosh_source_lock_sha256=_text(raw["phosh_source_lock_sha256"], "Phosh source-lock SHA-256"),
        architecture=_text(build["architecture"], "Phosh architecture"),
        environment=_text(build["environment"], "Phosh environment"),
        family=_text(build["family"], "Phosh family"),
        debian_suite=_text(build["debian_suite"], "Debian suite"),
        mobian_suite=_text(build["mobian_suite"], "Mobian suite"),
        mirror=_text(build["mirror"], "Kali mirror"),
        contrib=build["contrib"], nonfree=build["nonfree"],
        scratch_size=_text(build["scratch_size"], "scratch size"),
        generic_artifact=_safe_artifact(build["generic_artifact"], "generic Phosh rootfs artifact"),
        staged_artifact=_safe_artifact(build["staged_artifact"], "staged Phosh rootfs artifact"),
        double_build_required=build["double_build_required"],
        canonicalization_required=build["canonicalization_required"],
        physical_validation_required=policy["physical_validation_required"],
        hardware_verified=policy["hardware_verified"], beta_gate_credit=policy["beta_gate_credit"],
    )
    validate_phosh_rootfs_build_contract(source_lock, contract)
    return contract


def _qcom_supplement_packages(source_lock: PhoshSourceLock) -> tuple[str, ...]:
    expected = f"devices/{source_lock.family}/packages-{source_lock.environment}.yaml"
    matches = [recipe for recipe in source_lock.recipes if recipe.path == expected]
    if len(matches) != 1:
        raise PhoshBuildError(f"Phosh source lock must contain exactly one family supplement: {expected}")
    recipe = matches[0]
    if recipe.disabled_services:
        raise PhoshBuildError("family Phosh supplement contains service actions; explicit stage handling is required")
    return recipe.packages


def render_family_supplement_recipe(source_lock: PhoshSourceLock, contract: PhoshRootfsBuildContract) -> bytes:
    validate_phosh_rootfs_build_contract(source_lock, contract)
    packages = _qcom_supplement_packages(source_lock)
    package_lines = "\n".join(f"      - {package}" for package in packages)
    text = (
        '{{- $architecture := or .architecture "arm64" -}}\n'
        f'{{{{- $input := or .input "{contract.generic_artifact}" -}}}}\n'
        f'{{{{- $output := or .output "{contract.staged_artifact}" -}}}}\n'
        "architecture: {{ $architecture }}\n\n"
        "actions:\n"
        "  - action: unpack\n"
        "    file: {{ $input }}\n\n"
        "  - action: apt\n"
        "    recommends: false\n"
        "    description: Install locked KaliPhoneStudio QCOM Phosh userspace supplement\n"
        "    packages:\n"
        f"{package_lines}\n\n"
        "  - action: pack\n"
        "    file: {{ $output }}\n"
        "    compression: xz\n"
    )
    return text.encode("utf-8")


def create_phosh_rootfs_build_plan(source_lock: PhoshSourceLock, contract: PhoshRootfsBuildContract, *, debos_command: str = "debos", stage_recipe_name: str = ".kaliphonestudio-phosh-qcom-stage.yaml") -> PhoshRootfsBuildPlan:
    validate_phosh_rootfs_build_contract(source_lock, contract)
    if not debos_command or "/" in debos_command or "\\" in debos_command:
        raise PhoshBuildError("debos command must be a bare executable name")
    if PurePath(stage_recipe_name).name != stage_recipe_name or not stage_recipe_name.endswith(".yaml"):
        raise PhoshBuildError("Phosh stage recipe name must be a safe YAML basename")
    base_argv = (
        debos_command, f"--scratchsize={contract.scratch_size}",
        "-t", f"architecture:{contract.architecture}", "-t", f"environment:{contract.environment}",
        "-t", f"contrib:{str(contract.contrib).lower()}", "-t", f"nonfree:{str(contract.nonfree).lower()}",
        "-t", f"debian_suite:{contract.debian_suite}", "-t", f"suite:{contract.mobian_suite}",
        "-t", f"mirror:{contract.mirror}", "-t", f"rootfs:{contract.generic_artifact}",
        source_lock.rootfs_template_path,
    )
    stage_argv = (
        debos_command, f"--scratchsize={contract.scratch_size}",
        "-t", f"architecture:{contract.architecture}", "-t", f"input:{contract.generic_artifact}",
        "-t", f"output:{contract.staged_artifact}", stage_recipe_name,
    )
    recipe = render_family_supplement_recipe(source_lock, contract)
    return PhoshRootfsBuildPlan(
        schema_version=1, upstream_commit=source_lock.upstream_commit,
        source_lock_sha256=source_lock.lock_sha256(), build_contract_sha256=contract.contract_sha256(),
        base_argv=base_argv, stage_argv=stage_argv, stage_recipe_sha256=sha256(recipe).hexdigest(),
        generic_artifact=contract.generic_artifact, staged_artifact=contract.staged_artifact,
        physical_validation_required=True, hardware_verified=False, beta_gate_credit=False,
    )


def create_phosh_rootfs_build_evidence(plan: PhoshRootfsBuildPlan, *, artifact_sha256: str, artifact_size: int, package_manifest_sha256: str, package_count: int, phosh_package_contract_satisfied: bool) -> PhoshRootfsBuildEvidence:
    if not _SHA256_RE.fullmatch(artifact_sha256):
        raise PhoshBuildError("Phosh rootfs artifact SHA-256 is invalid")
    if not _SHA256_RE.fullmatch(package_manifest_sha256):
        raise PhoshBuildError("Phosh rootfs package-manifest SHA-256 is invalid")
    if artifact_size <= 0 or package_count <= 0:
        raise PhoshBuildError("Phosh rootfs evidence has invalid size/package count")
    if phosh_package_contract_satisfied is not True:
        raise PhoshBuildError("Phosh package contract is not satisfied")
    return PhoshRootfsBuildEvidence(
        schema_version=1, upstream_commit=plan.upstream_commit, source_lock_sha256=plan.source_lock_sha256,
        build_contract_sha256=plan.build_contract_sha256,
        build_plan_sha256=sha256(plan.canonical_json().encode("utf-8")).hexdigest(),
        artifact_sha256=artifact_sha256, artifact_size=artifact_size,
        package_manifest_sha256=package_manifest_sha256, package_count=package_count,
        phosh_package_contract_satisfied=True, reproducibility_authority=False,
        physical_validation_required=True, hardware_verified=False, beta_gate_credit=False,
    )


def write_phosh_rootfs_build_evidence(evidence: PhoshRootfsBuildEvidence, destination: Path) -> str:
    if evidence.reproducibility_authority is not False or evidence.hardware_verified is not False or evidence.beta_gate_credit is not False:
        raise PhoshBuildError("single-build Phosh evidence cannot be authoritative, hardware-verified or grant Beta credit")
    path = Path(destination)
    if path.exists():
        raise PhoshBuildError("refusing to overwrite Phosh rootfs build evidence")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
    return evidence.evidence_sha256()
