"""Profile-driven kernel source/build evidence contracts.

This layer does not build or boot a kernel.  It creates deterministic plans from
an exact device profile, verifies a local exact-source checkout before a build,
validates the generated final ``.config`` against profile requirements and can
preflight a produced ARM64 Linux Image.  Hardware functionality is never inferred
from these host-side checks.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Any

from .profiles import DeviceProfile


_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_CONFIG_RE = re.compile(r"^CONFIG_[A-Z0-9_]+$")
_MAKE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_ARM64_IMAGE_MAGIC = b"ARM\x64"
_ARM64_IMAGE_MAGIC_OFFSET = 0x38
MAX_CONFIG_BYTES = 8 * 1024 * 1024
MAX_IMAGE_BYTES = 256 * 1024 * 1024


class KernelContractError(ValueError):
    pass


@dataclass(frozen=True)
class KernelBuildPlan:
    schema_version: int
    profile_id: str
    source_name: str
    source_url: str
    source_commit: str
    expected_kernel_version: str
    arch: str
    image_name: str
    defconfig: str
    config_fragments: tuple[str, ...]
    make_flags: tuple[tuple[str, str], ...]
    required_configs: tuple[tuple[str, str], ...]

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def plan_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class KernelCheckoutEvidence:
    schema_version: int
    profile_id: str
    plan_sha256: str
    source_commit: str
    kernel_version: str
    defconfig_sha256: str
    fragment_sha256: tuple[tuple[str, str], ...]

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class KernelConfigEvidence:
    schema_version: int
    profile_id: str
    plan_sha256: str
    config_sha256: str
    config_size: int
    required_config_count: int

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class KernelImageEvidence:
    schema_version: int
    profile_id: str
    plan_sha256: str
    image_sha256: str
    image_size: int
    arm64_magic_verified: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _safe_relative_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KernelContractError(f"{label} must be a non-empty relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise KernelContractError(f"{label} must be a safe relative POSIX path")
    if any(not part or "\\" in part or any(ord(ch) < 0x20 for ch in part) for part in path.parts):
        raise KernelContractError(f"{label} contains unsafe path data")
    return path.as_posix()


def _source_for_kernel(profile: DeviceProfile, source_name: str) -> dict[str, str]:
    matches = [s for s in profile.data["sources"] if s.get("name") == source_name]
    if len(matches) != 1:
        raise KernelContractError(
            f"kernel.source_name must resolve exactly one profile source; got {len(matches)}"
        )
    source = matches[0]
    commit = source["commit"].lower()
    if not _SHA_RE.fullmatch(commit):
        raise KernelContractError("kernel source commit is not a full git SHA")
    return {"name": source["name"], "url": source["url"], "commit": commit}


def create_kernel_build_plan(profile: DeviceProfile) -> KernelBuildPlan:
    contract = profile.data.get("kernel")
    if not isinstance(contract, dict):
        raise KernelContractError("profile has no validated kernel contract")
    source_name = contract.get("source_name")
    if not isinstance(source_name, str) or not source_name.strip():
        raise KernelContractError("kernel.source_name must be non-empty")
    source = _source_for_kernel(profile, source_name)

    version = contract.get("expected_version")
    if not isinstance(version, str) or not _VERSION_RE.fullmatch(version):
        raise KernelContractError("kernel.expected_version must be major.minor.patch")
    arch = contract.get("arch")
    if arch != profile.data.get("arch"):
        raise KernelContractError("kernel.arch must match profile arch")
    image_name = contract.get("image_name")
    if image_name != profile.data["boot"]["kernel_image"]:
        raise KernelContractError("kernel.image_name must match boot.kernel_image")

    defconfig = _safe_relative_path(contract.get("defconfig"), "kernel.defconfig")
    fragments_raw = contract.get("config_fragments")
    if not isinstance(fragments_raw, list) or any(not isinstance(x, str) for x in fragments_raw):
        raise KernelContractError("kernel.config_fragments must be a list of paths")
    fragments = tuple(_safe_relative_path(x, "kernel.config_fragments") for x in fragments_raw)
    if len(fragments) != len(set(fragments)):
        raise KernelContractError("kernel.config_fragments must not contain duplicates")

    flags = contract.get("make_flags")
    if not isinstance(flags, dict):
        raise KernelContractError("kernel.make_flags must be an object")
    normalized_flags: list[tuple[str, str]] = []
    for key, value in sorted(flags.items()):
        if not isinstance(key, str) or not _MAKE_KEY_RE.fullmatch(key):
            raise KernelContractError("kernel.make_flags contains an unsafe variable name")
        if not isinstance(value, str) or not value or any(ord(ch) < 0x20 for ch in value):
            raise KernelContractError(f"kernel.make_flags.{key} must be safe non-empty text")
        normalized_flags.append((key, value))

    required = contract.get("required_configs")
    if not isinstance(required, dict) or not required:
        raise KernelContractError("kernel.required_configs must be a non-empty object")
    normalized_required: list[tuple[str, str]] = []
    for name, state in sorted(required.items()):
        if not isinstance(name, str) or not _CONFIG_RE.fullmatch(name):
            raise KernelContractError("kernel.required_configs contains an invalid CONFIG_ name")
        if state not in {"y", "m", "n"}:
            raise KernelContractError(f"kernel.required_configs.{name} must be y, m or n")
        normalized_required.append((name, state))

    return KernelBuildPlan(
        schema_version=1,
        profile_id=profile.profile_id,
        source_name=source["name"],
        source_url=source["url"],
        source_commit=source["commit"],
        expected_kernel_version=version,
        arch=arch,
        image_name=image_name,
        defconfig=defconfig,
        config_fragments=fragments,
        make_flags=tuple(normalized_flags),
        required_configs=tuple(normalized_required),
    )


def _sha256_file(path: Path, *, maximum: int | None = None) -> tuple[str, int]:
    if not path.is_file() or path.is_symlink():
        raise KernelContractError(f"required regular file is missing or symlinked: {path}")
    size = path.stat().st_size
    if size <= 0:
        raise KernelContractError(f"required file is empty: {path}")
    if maximum is not None and size > maximum:
        raise KernelContractError(f"file exceeds safety size limit: {path}")
    digest = sha256()
    read = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            read += len(chunk)
            if maximum is not None and read > maximum:
                raise KernelContractError(f"file changed beyond safety size limit: {path}")
            digest.update(chunk)
    if read != size or path.stat().st_size != size:
        raise KernelContractError(f"file changed while hashing: {path}")
    return digest.hexdigest(), size


def _path_within(root: Path, relative: str) -> Path:
    root_resolved = root.resolve(strict=True)
    candidate = root_resolved.joinpath(*PurePosixPath(relative).parts)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise KernelContractError(f"kernel source material missing: {relative}") from exc
    if root_resolved != resolved and root_resolved not in resolved.parents:
        raise KernelContractError(f"kernel source material escapes checkout: {relative}")
    return resolved


def _kernel_version_from_makefile(path: Path) -> str:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="strict").splitlines()[:80]:
        if "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if key in {"VERSION", "PATCHLEVEL", "SUBLEVEL"} and value.isdigit():
            values[key] = value
    if set(values) != {"VERSION", "PATCHLEVEL", "SUBLEVEL"}:
        raise KernelContractError("kernel Makefile does not expose a complete numeric version")
    return f"{values['VERSION']}.{values['PATCHLEVEL']}.{values['SUBLEVEL']}"


def verify_kernel_checkout(
    plan: KernelBuildPlan,
    checkout: Path,
    *,
    git_binary: str = "git",
) -> KernelCheckoutEvidence:
    """Verify exact git HEAD, kernel version and profile-selected config material."""
    if plan.schema_version != 1:
        raise KernelContractError("unsupported kernel build plan schema")
    if not checkout.is_dir():
        raise KernelContractError(f"kernel checkout not found: {checkout}")
    try:
        result = subprocess.run(
            [git_binary, "-C", str(checkout), "rev-parse", "HEAD"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise KernelContractError("cannot verify kernel checkout git HEAD") from exc
    head = result.stdout.strip().lower()
    if head != plan.source_commit:
        raise KernelContractError(
            f"kernel checkout HEAD {head!r} does not match locked commit {plan.source_commit}"
        )

    makefile = _path_within(checkout, "Makefile")
    version = _kernel_version_from_makefile(makefile)
    if version != plan.expected_kernel_version:
        raise KernelContractError(
            f"kernel version {version} does not match locked {plan.expected_kernel_version}"
        )

    defconfig_path = _path_within(checkout, f"arch/{plan.arch}/configs/{plan.defconfig}")
    defconfig_sha, _ = _sha256_file(defconfig_path, maximum=MAX_CONFIG_BYTES)
    fragment_hashes: list[tuple[str, str]] = []
    for fragment in plan.config_fragments:
        path = _path_within(checkout, f"arch/{plan.arch}/configs/{fragment}")
        digest, _ = _sha256_file(path, maximum=MAX_CONFIG_BYTES)
        fragment_hashes.append((fragment, digest))

    return KernelCheckoutEvidence(
        schema_version=1,
        profile_id=plan.profile_id,
        plan_sha256=plan.plan_sha256(),
        source_commit=head,
        kernel_version=version,
        defconfig_sha256=defconfig_sha,
        fragment_sha256=tuple(fragment_hashes),
    )


def parse_generated_kernel_config(payload: bytes) -> dict[str, str]:
    if not payload or len(payload) > MAX_CONFIG_BYTES:
        raise KernelContractError("generated kernel config is empty or exceeds the safety limit")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise KernelContractError("generated kernel config must be UTF-8 text") from exc
    result: dict[str, str] = {}
    disabled_re = re.compile(r"^# (CONFIG_[A-Z0-9_]+) is not set$")
    enabled_re = re.compile(r"^(CONFIG_[A-Z0-9_]+)=(y|m|n|\".*\"|-?[0-9]+|0x[0-9A-Fa-f]+)$")
    for line in text.splitlines():
        disabled = disabled_re.fullmatch(line)
        if disabled:
            name, value = disabled.group(1), "n"
        else:
            enabled = enabled_re.fullmatch(line)
            if not enabled:
                continue
            name, value = enabled.group(1), enabled.group(2)
        previous = result.get(name)
        if previous is not None and previous != value:
            raise KernelContractError(f"generated kernel config has conflicting duplicate {name}")
        result[name] = value
    if not result:
        raise KernelContractError("generated kernel config contains no CONFIG_ assignments")
    return result


def verify_generated_kernel_config(
    plan: KernelBuildPlan,
    config_path: Path,
) -> KernelConfigEvidence:
    digest, size = _sha256_file(config_path, maximum=MAX_CONFIG_BYTES)
    values = parse_generated_kernel_config(config_path.read_bytes())
    mismatches = [
        f"{name}={values.get(name, '<missing>')} (required {state})"
        for name, state in plan.required_configs
        if values.get(name, "n") != state
    ]
    if mismatches:
        raise KernelContractError(
            "generated kernel config does not satisfy KaliPhoneStudio requirements: "
            + "; ".join(mismatches)
        )
    return KernelConfigEvidence(
        schema_version=1,
        profile_id=plan.profile_id,
        plan_sha256=plan.plan_sha256(),
        config_sha256=digest,
        config_size=size,
        required_config_count=len(plan.required_configs),
    )


def verify_arm64_kernel_image(
    plan: KernelBuildPlan,
    image_path: Path,
) -> KernelImageEvidence:
    if plan.arch != "arm64":
        raise KernelContractError("ARM64 Image verification requires an arm64 kernel plan")
    digest, size = _sha256_file(image_path, maximum=MAX_IMAGE_BYTES)
    if size < _ARM64_IMAGE_MAGIC_OFFSET + len(_ARM64_IMAGE_MAGIC):
        raise KernelContractError("kernel Image is too small for an ARM64 Image header")
    with image_path.open("rb") as handle:
        handle.seek(_ARM64_IMAGE_MAGIC_OFFSET)
        magic = handle.read(4)
    if magic != _ARM64_IMAGE_MAGIC:
        raise KernelContractError("kernel artifact is not an ARM64 Linux Image")
    return KernelImageEvidence(
        schema_version=1,
        profile_id=plan.profile_id,
        plan_sha256=plan.plan_sha256(),
        image_sha256=digest,
        image_size=size,
        arm64_magic_verified=True,
    )


def write_kernel_evidence(evidence: Any, destination: Path) -> str:
    if destination.exists():
        raise KernelContractError(f"refusing to overwrite existing evidence: {destination}")
    if not hasattr(evidence, "canonical_json") or not hasattr(evidence, "evidence_sha256"):
        raise KernelContractError("unsupported kernel evidence object")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.name + ".tmp")
    if temp.exists():
        temp.unlink()
    temp.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
    temp.replace(destination)
    return evidence.evidence_sha256()
