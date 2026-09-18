"""Fail-closed host-side Phosh rootfs integration contracts.

This module validates an immutable NetHunter Pro Phosh source lock and can
evaluate a normalized dpkg package manifest.  It performs no device I/O,
selects no storage target and never claims display/touch or Beta readiness.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping


class PhoshError(ValueError):
    """Raised when Phosh source/package evidence is incomplete or ambiguous."""


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_PACKAGE_RE = re.compile(r"^[a-z0-9][a-z0-9+.-]*$")
_PACKAGE_LINE_RE = re.compile(r"^\s+-\s+([a-z0-9][a-z0-9+.-]*)\s*$")
_DISABLE_SERVICE_RE = re.compile(r"\bsystemctl\s+disable\s+([A-Za-z0-9@._-]+)\s*$")
_MAX_SOURCE_BYTES = 2 * 1024 * 1024
_MAX_MANIFEST_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class LockedPhoshRecipe:
    path: str
    sha256: str
    packages: tuple[str, ...]
    disabled_services: tuple[str, ...]


@dataclass(frozen=True)
class PhoshSourceLock:
    schema_version: int
    upstream_repository: str
    upstream_commit: str
    architecture: str
    environment: str
    family: str
    rootfs_template_path: str
    rootfs_template_sha256: str
    recipes: tuple[LockedPhoshRecipe, ...]
    physical_validation_required: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def lock_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()

    @property
    def required_packages(self) -> tuple[str, ...]:
        packages: list[str] = []
        for recipe in self.recipes:
            packages.extend(recipe.packages)
        return tuple(packages)

    @property
    def locked_paths(self) -> tuple[str, ...]:
        return (self.rootfs_template_path,) + tuple(recipe.path for recipe in self.recipes)


@dataclass(frozen=True)
class PhoshSourceVerification:
    schema_version: int
    source_lock_sha256: str
    upstream_commit: str
    architecture: str
    environment: str
    verified_files: tuple[tuple[str, str], ...]
    required_packages: tuple[str, ...]
    source_verified: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"


@dataclass(frozen=True)
class PhoshRootfsPackageEvidence:
    schema_version: int
    source_lock_sha256: str
    rootfs_artifact_sha256: str
    package_manifest_sha256: str
    package_count: int
    required_packages: tuple[str, ...]
    installed_required_packages: tuple[tuple[str, str, str], ...]
    missing_packages: tuple[str, ...]
    host_userspace_package_contract_satisfied: bool
    physical_validation_required: bool
    display_verified: bool
    touch_verified: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PhoshError(f"{label} must be a non-empty string")
    return value


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise PhoshError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _safe_relative_path(value: Any, label: str) -> str:
    text = _required_text(value, label)
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts or "." in path.parts or "\\" in text:
        raise PhoshError(f"{label} must be a safe repository-relative POSIX path")
    return text


def validate_phosh_source_lock(lock: PhoshSourceLock) -> None:
    if lock.schema_version != 1:
        raise PhoshError("unsupported Phosh source-lock schema")
    if not lock.upstream_repository.startswith("https://"):
        raise PhoshError("Phosh upstream repository must use HTTPS")
    if not _COMMIT_RE.fullmatch(lock.upstream_commit):
        raise PhoshError("Phosh upstream source must be pinned to a full 40-hex commit")
    if lock.architecture != "arm64":
        raise PhoshError("phone Phosh source lock must target arm64")
    if lock.environment != "phosh":
        raise PhoshError("mobile environment must be phosh")
    if not lock.family:
        raise PhoshError("Phosh source lock requires a target family")
    _safe_relative_path(lock.rootfs_template_path, "rootfs template path")
    _require_sha256(lock.rootfs_template_sha256, "rootfs template")
    if len(lock.recipes) < 2:
        raise PhoshError("Phosh source lock requires common and family recipe coverage")

    seen_paths: set[str] = {lock.rootfs_template_path}
    seen_packages: set[str] = set()
    for recipe in lock.recipes:
        path = _safe_relative_path(recipe.path, "recipe path")
        if path in seen_paths:
            raise PhoshError("duplicate path in Phosh source lock")
        seen_paths.add(path)
        _require_sha256(recipe.sha256, f"recipe {path}")
        if not recipe.packages:
            raise PhoshError(f"recipe {path} has no required packages")
        if len(recipe.packages) != len(set(recipe.packages)):
            raise PhoshError(f"recipe {path} contains duplicate packages")
        for package in recipe.packages:
            if not _PACKAGE_RE.fullmatch(package):
                raise PhoshError(f"invalid package name in {path}: {package!r}")
            if package in seen_packages:
                raise PhoshError(f"package is duplicated across Phosh recipes: {package}")
            seen_packages.add(package)
        if len(recipe.disabled_services) != len(set(recipe.disabled_services)):
            raise PhoshError(f"recipe {path} contains duplicate disabled services")
        if any(not service or "/" in service or "\\" in service for service in recipe.disabled_services):
            raise PhoshError(f"recipe {path} contains an unsafe service name")

    for package in ("mobian-phosh", "mobian-phosh-phone", "squeekboard"):
        if package not in seen_packages:
            raise PhoshError(f"Phosh source lock is missing required mobile package: {package}")

    if lock.physical_validation_required is not True:
        raise PhoshError("Phosh integration must require physical validation")
    if lock.hardware_verified is not False or lock.beta_gate_credit is not False:
        raise PhoshError("host-side Phosh source lock cannot grant hardware/Beta credit")


def load_phosh_source_lock(path: Path) -> PhoshSourceLock:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PhoshError(f"cannot read Phosh source lock: {exc}") from exc
    if not isinstance(raw, dict):
        raise PhoshError("Phosh source lock must be a JSON object")
    required_top = {"schema_version", "upstream", "target", "rootfs_template", "recipes", "policy"}
    if set(raw) != required_top:
        raise PhoshError("unexpected Phosh source-lock top-level fields")
    if raw["schema_version"] != 1:
        raise PhoshError("unsupported Phosh source-lock schema")

    upstream = raw["upstream"]
    target = raw["target"]
    template = raw["rootfs_template"]
    policy = raw["policy"]
    recipes_raw = raw["recipes"]

    if not isinstance(upstream, dict) or set(upstream) != {"repository", "commit"}:
        raise PhoshError("invalid Phosh upstream block")
    if not isinstance(target, dict) or set(target) != {"architecture", "environment", "family"}:
        raise PhoshError("invalid Phosh target block")
    if not isinstance(template, dict) or set(template) != {"path", "sha256"}:
        raise PhoshError("invalid Phosh rootfs-template block")
    if not isinstance(policy, dict) or set(policy) != {
        "physical_validation_required", "hardware_verified", "beta_gate_credit"
    }:
        raise PhoshError("invalid Phosh policy block")
    if not isinstance(recipes_raw, list):
        raise PhoshError("Phosh recipes must be a list")

    recipes: list[LockedPhoshRecipe] = []
    for item in recipes_raw:
        if not isinstance(item, dict) or set(item) != {"path", "sha256", "packages", "disabled_services"}:
            raise PhoshError("invalid locked Phosh recipe entry")
        packages = item["packages"]
        services = item["disabled_services"]
        if not isinstance(packages, list) or not all(isinstance(value, str) for value in packages):
            raise PhoshError("Phosh recipe packages must be strings")
        if not isinstance(services, list) or not all(isinstance(value, str) for value in services):
            raise PhoshError("Phosh disabled services must be strings")
        recipes.append(
            LockedPhoshRecipe(
                _safe_relative_path(item["path"], "recipe path"),
                _require_sha256(item["sha256"], "recipe"),
                tuple(packages),
                tuple(services),
            )
        )

    lock = PhoshSourceLock(
        schema_version=1,
        upstream_repository=_required_text(upstream["repository"], "Phosh upstream repository"),
        upstream_commit=_required_text(upstream["commit"], "Phosh upstream commit"),
        architecture=_required_text(target["architecture"], "Phosh architecture"),
        environment=_required_text(target["environment"], "Phosh environment"),
        family=_required_text(target["family"], "Phosh family"),
        rootfs_template_path=_safe_relative_path(template["path"], "rootfs template path"),
        rootfs_template_sha256=_require_sha256(template["sha256"], "rootfs template"),
        recipes=tuple(recipes),
        physical_validation_required=policy["physical_validation_required"],
        hardware_verified=policy["hardware_verified"],
        beta_gate_credit=policy["beta_gate_credit"],
    )
    validate_phosh_source_lock(lock)
    return lock


def _decode_source(data: bytes, label: str) -> str:
    if not data or len(data) > _MAX_SOURCE_BYTES:
        raise PhoshError(f"{label} is empty or unreasonably large")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PhoshError(f"{label} is not valid UTF-8") from exc


def parse_debos_package_recipe(data: bytes) -> tuple[str, ...]:
    text = _decode_source(data, "Phosh recipe")
    packages = tuple(
        match.group(1)
        for line in text.splitlines()
        if (match := _PACKAGE_LINE_RE.fullmatch(line))
    )
    if not packages:
        raise PhoshError("Phosh recipe contains no package entries")
    if len(packages) != len(set(packages)):
        raise PhoshError("Phosh recipe contains duplicate package entries")
    return packages


def parse_disabled_services(data: bytes) -> tuple[str, ...]:
    text = _decode_source(data, "Phosh recipe")
    services: list[str] = []
    for line in text.splitlines():
        match = _DISABLE_SERVICE_RE.search(line.strip())
        if match:
            services.append(match.group(1))
    if len(services) != len(set(services)):
        raise PhoshError("Phosh recipe contains duplicate disable-service commands")
    return tuple(services)


def _verify_rootfs_template(lock: PhoshSourceLock, data: bytes) -> str:
    digest = sha256(data).hexdigest()
    if digest != lock.rootfs_template_sha256:
        raise PhoshError("pinned NetHunter Pro rootfs template SHA-256 mismatch")
    text = _decode_source(data, "NetHunter Pro rootfs template")
    required_fragments = (
        'or .architecture "arm64"',
        'or .environment "phosh"',
        "recipe: include/packages-{{ $environment }}.yaml",
    )
    if any(fragment not in text for fragment in required_fragments):
        raise PhoshError("pinned rootfs template no longer expresses the locked ARM64 Phosh dispatch")
    return digest


def verify_phosh_source_bytes(
    lock: PhoshSourceLock,
    files: Mapping[str, bytes],
) -> PhoshSourceVerification:
    validate_phosh_source_lock(lock)
    if set(files) != set(lock.locked_paths):
        missing = sorted(set(lock.locked_paths) - set(files))
        extra = sorted(set(files) - set(lock.locked_paths))
        raise PhoshError(f"Phosh source set mismatch; missing={missing}, extra={extra}")

    verified: list[tuple[str, str]] = []
    template_data = files[lock.rootfs_template_path]
    verified.append((lock.rootfs_template_path, _verify_rootfs_template(lock, template_data)))

    recipes_by_path = {recipe.path: recipe for recipe in lock.recipes}
    for path in sorted(recipes_by_path):
        recipe = recipes_by_path[path]
        data = files[path]
        digest = sha256(data).hexdigest()
        if digest != recipe.sha256:
            raise PhoshError(f"pinned Phosh recipe SHA-256 mismatch: {path}")
        if parse_debos_package_recipe(data) != recipe.packages:
            raise PhoshError(f"pinned Phosh package contract drifted: {path}")
        if parse_disabled_services(data) != recipe.disabled_services:
            raise PhoshError(f"pinned Phosh service contract drifted: {path}")
        verified.append((path, digest))

    return PhoshSourceVerification(
        schema_version=1,
        source_lock_sha256=lock.lock_sha256(),
        upstream_commit=lock.upstream_commit,
        architecture=lock.architecture,
        environment=lock.environment,
        verified_files=tuple(sorted(verified)),
        required_packages=lock.required_packages,
        source_verified=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def verify_phosh_source_tree(lock: PhoshSourceLock, source_root: Path) -> PhoshSourceVerification:
    if source_root.is_symlink() or not source_root.is_dir():
        raise PhoshError("Phosh source root must be a real directory")
    root = source_root.resolve()
    files: dict[str, bytes] = {}
    for relative in lock.locked_paths:
        candidate = source_root / Path(relative)
        if candidate.is_symlink() or not candidate.is_file():
            raise PhoshError(f"locked Phosh source file is missing or unsafe: {relative}")
        resolved = candidate.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise PhoshError(f"locked Phosh source escapes source root: {relative}") from exc
        data = candidate.read_bytes()
        if len(data) > _MAX_SOURCE_BYTES:
            raise PhoshError(f"locked Phosh source file is unreasonably large: {relative}")
        files[relative] = data
    return verify_phosh_source_bytes(lock, files)


def _parse_package_manifest(payload: bytes) -> tuple[dict[str, tuple[str, str]], int]:
    if not payload or len(payload) > _MAX_MANIFEST_BYTES:
        raise PhoshError("rootfs package manifest is empty or unreasonably large")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PhoshError("rootfs package manifest is not valid UTF-8") from exc

    packages: dict[str, tuple[str, str]] = {}
    count = 0
    for line in text.splitlines():
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            raise PhoshError("rootfs package manifest must use package<TAB>version<TAB>architecture")
        package, version, architecture = parts
        if not _PACKAGE_RE.fullmatch(package) or not version or not architecture:
            raise PhoshError("rootfs package manifest contains an invalid record")
        if package in packages:
            raise PhoshError(f"rootfs package manifest contains duplicate package: {package}")
        packages[package] = (version, architecture)
        count += 1
    if count == 0:
        raise PhoshError("rootfs package manifest contains no package records")
    return packages, count


def evaluate_phosh_package_manifest(
    lock: PhoshSourceLock,
    package_manifest: bytes,
    *,
    rootfs_artifact_sha256: str,
) -> PhoshRootfsPackageEvidence:
    """Evaluate host-side package presence without making hardware claims."""
    validate_phosh_source_lock(lock)
    artifact_digest = _require_sha256(rootfs_artifact_sha256, "rootfs artifact")
    installed, package_count = _parse_package_manifest(package_manifest)

    present: list[tuple[str, str, str]] = []
    missing: list[str] = []
    for package in lock.required_packages:
        record = installed.get(package)
        if record is None:
            missing.append(package)
            continue
        version, architecture = record
        if architecture not in {lock.architecture, "all"}:
            raise PhoshError(
                f"required Phosh package {package} has unexpected architecture {architecture!r}"
            )
        present.append((package, version, architecture))

    return PhoshRootfsPackageEvidence(
        schema_version=1,
        source_lock_sha256=lock.lock_sha256(),
        rootfs_artifact_sha256=artifact_digest,
        package_manifest_sha256=sha256(package_manifest).hexdigest(),
        package_count=package_count,
        required_packages=lock.required_packages,
        installed_required_packages=tuple(present),
        missing_packages=tuple(missing),
        host_userspace_package_contract_satisfied=not missing,
        physical_validation_required=True,
        display_verified=False,
        touch_verified=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
