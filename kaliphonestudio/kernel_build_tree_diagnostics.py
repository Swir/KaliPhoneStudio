"""Bounded non-release diagnostics for divergent kernel build trees.

Strict kernel acceptance remains byte-for-byte equality of the final approved
outputs. This module is only used after that strict check fails. It compares a
selected, deterministic set of intermediate kernel build artifacts from two
independent output roots so a later iteration can identify where divergence
first becomes visible without weakening any release or Beta gate.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath


DIAGNOSTIC_SCHEMA_VERSION = 1
DEFAULT_CHUNK_SIZE = 1024 * 1024
DEFAULT_MAX_DIFFERENCES = 256
MAX_SELECTED_FILES = 100_000

_KEY_NAMES = frozenset({".config", "vmlinux", "System.map", "Module.symvers", "Image"})
_KEY_SUFFIXES = frozenset({".o", ".a"})
_EXACT_DIAGNOSTIC_PATHS = frozenset({"kernel/kheaders_data.tar.xz"})


class KernelBuildTreeDiagnosticError(ValueError):
    pass


@dataclass(frozen=True)
class BuildArtifactDifference:
    path: str
    category: str
    kind: str
    size_a: int | None
    size_b: int | None
    sha256_a: str | None
    sha256_b: str | None


@dataclass(frozen=True)
class KernelBuildTreeDivergenceEvidence:
    schema_version: int
    selected_path_count: int
    build_a_selected_count: int
    build_b_selected_count: int
    identical_path_count: int
    differing_path_count: int
    missing_from_a_count: int
    missing_from_b_count: int
    size_mismatch_count: int
    content_mismatch_count: int
    category_difference_counts: dict[str, int]
    reported_difference_count: int
    omitted_difference_count: int
    first_differing_path: str | None
    reported_differences: tuple[BuildArtifactDifference, ...]
    beta_gate_credit: bool = False
    hardware_verified: bool = False

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _safe_root(path: Path, label: str) -> Path:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_dir():
        raise KernelBuildTreeDiagnosticError(f"{label} must be a real directory")
    try:
        return candidate.resolve(strict=True)
    except OSError as exc:
        raise KernelBuildTreeDiagnosticError(f"cannot resolve {label}") from exc


def _safe_relative(root: Path, path: Path) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise KernelBuildTreeDiagnosticError("selected artifact escaped build root") from exc
    posix = PurePosixPath(*relative.parts)
    if posix.is_absolute() or not posix.parts or any(part in {"", ".", ".."} for part in posix.parts):
        raise KernelBuildTreeDiagnosticError("selected artifact has unsafe relative path")
    if any("\\" in part or any(ord(ch) < 0x20 for ch in part) for part in posix.parts):
        raise KernelBuildTreeDiagnosticError("selected artifact path contains unsafe data")
    return posix.as_posix()


def _selected(relative: str) -> bool:
    path = PurePosixPath(relative)
    name = path.name
    if relative in _EXACT_DIAGNOSTIC_PATHS:
        return True
    if relative == "arch/arm64/boot/Image":
        return True
    if name in _KEY_NAMES:
        return True
    return path.suffix in _KEY_SUFFIXES


def _category(relative: str) -> str:
    path = PurePosixPath(relative)
    if relative == "kernel/kheaders_data.tar.xz":
        return "kheaders_archive"
    if relative == "arch/arm64/boot/Image" or path.name == "Image":
        return "image"
    if path.name == "vmlinux":
        return "vmlinux"
    if path.name == "System.map":
        return "system_map"
    if path.name == ".config":
        return "config"
    if path.name == "Module.symvers":
        return "module_symvers"
    if path.suffix == ".o":
        return "object"
    if path.suffix == ".a":
        return "archive"
    return "other"


def _inventory(root: Path) -> dict[str, Path]:
    selected: dict[str, Path] = {}
    for candidate in root.rglob("*"):
        if candidate.is_symlink():
            try:
                rel = _safe_relative(root, candidate)
            except KernelBuildTreeDiagnosticError:
                continue
            if _selected(rel):
                raise KernelBuildTreeDiagnosticError(
                    f"selected build artifact must not be a symlink: {rel}"
                )
            continue
        if not candidate.is_file():
            continue
        rel = _safe_relative(root, candidate)
        if not _selected(rel):
            continue
        if rel in selected:
            raise KernelBuildTreeDiagnosticError(f"duplicate selected build path: {rel}")
        selected[rel] = candidate
        if len(selected) > MAX_SELECTED_FILES:
            raise KernelBuildTreeDiagnosticError("selected build artifact count exceeds safety limit")
    return selected


def _hash_regular(path: Path, *, chunk_size: int) -> tuple[str, int]:
    if path.is_symlink() or not path.is_file():
        raise KernelBuildTreeDiagnosticError("build artifact changed type while being diagnosed")
    before = path.stat()
    digest = sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    after = path.stat()
    if size != before.st_size or after.st_size != before.st_size or after.st_mtime_ns != before.st_mtime_ns:
        raise KernelBuildTreeDiagnosticError("build artifact changed while being diagnosed")
    return digest.hexdigest(), size


def _difference(
    relative: str,
    *,
    kind: str,
    size_a: int | None,
    size_b: int | None,
    sha_a: str | None,
    sha_b: str | None,
) -> BuildArtifactDifference:
    return BuildArtifactDifference(
        path=relative,
        category=_category(relative),
        kind=kind,
        size_a=size_a,
        size_b=size_b,
        sha256_a=sha_a,
        sha256_b=sha_b,
    )


def diagnose_kernel_build_tree(
    build_a: Path,
    build_b: Path,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    max_differences: int = DEFAULT_MAX_DIFFERENCES,
) -> KernelBuildTreeDivergenceEvidence:
    if not isinstance(chunk_size, int) or isinstance(chunk_size, bool) or chunk_size < 4096:
        raise KernelBuildTreeDiagnosticError("chunk_size must be an integer >= 4096")
    if not isinstance(max_differences, int) or isinstance(max_differences, bool) or max_differences < 1:
        raise KernelBuildTreeDiagnosticError("max_differences must be an integer >= 1")

    root_a = _safe_root(build_a, "build A")
    root_b = _safe_root(build_b, "build B")
    if root_a == root_b:
        raise KernelBuildTreeDiagnosticError("build A and build B must be independent directories")

    inventory_a = _inventory(root_a)
    inventory_b = _inventory(root_b)
    paths = sorted(set(inventory_a) | set(inventory_b))

    identical = 0
    missing_a = 0
    missing_b = 0
    size_mismatch = 0
    content_mismatch = 0
    category_counts: dict[str, int] = {}
    differences: list[BuildArtifactDifference] = []
    total_differences = 0
    first_differing_path: str | None = None

    def record(diff: BuildArtifactDifference) -> None:
        nonlocal total_differences, first_differing_path
        total_differences += 1
        if first_differing_path is None:
            first_differing_path = diff.path
        category_counts[diff.category] = category_counts.get(diff.category, 0) + 1
        if len(differences) < max_differences:
            differences.append(diff)

    for relative in paths:
        path_a = inventory_a.get(relative)
        path_b = inventory_b.get(relative)
        if path_a is None:
            missing_a += 1
            hash_b, bytes_b = _hash_regular(path_b, chunk_size=chunk_size)  # type: ignore[arg-type]
            record(_difference(relative, kind="missing_from_a", size_a=None, size_b=bytes_b, sha_a=None, sha_b=hash_b))
            continue
        if path_b is None:
            missing_b += 1
            hash_a, bytes_a = _hash_regular(path_a, chunk_size=chunk_size)
            record(_difference(relative, kind="missing_from_b", size_a=bytes_a, size_b=None, sha_a=hash_a, sha_b=None))
            continue

        stat_a = path_a.stat()
        stat_b = path_b.stat()
        hash_a, bytes_a = _hash_regular(path_a, chunk_size=chunk_size)
        hash_b, bytes_b = _hash_regular(path_b, chunk_size=chunk_size)
        if bytes_a != stat_a.st_size or bytes_b != stat_b.st_size:
            raise KernelBuildTreeDiagnosticError("build artifact size changed while being diagnosed")
        if bytes_a != bytes_b:
            size_mismatch += 1
            record(_difference(relative, kind="size_mismatch", size_a=bytes_a, size_b=bytes_b, sha_a=hash_a, sha_b=hash_b))
        elif hash_a != hash_b:
            content_mismatch += 1
            record(_difference(relative, kind="content_mismatch", size_a=bytes_a, size_b=bytes_b, sha_a=hash_a, sha_b=hash_b))
        else:
            identical += 1

    return KernelBuildTreeDivergenceEvidence(
        schema_version=DIAGNOSTIC_SCHEMA_VERSION,
        selected_path_count=len(paths),
        build_a_selected_count=len(inventory_a),
        build_b_selected_count=len(inventory_b),
        identical_path_count=identical,
        differing_path_count=total_differences,
        missing_from_a_count=missing_a,
        missing_from_b_count=missing_b,
        size_mismatch_count=size_mismatch,
        content_mismatch_count=content_mismatch,
        category_difference_counts=dict(sorted(category_counts.items())),
        reported_difference_count=len(differences),
        omitted_difference_count=max(0, total_differences - len(differences)),
        first_differing_path=first_differing_path,
        reported_differences=tuple(differences),
        beta_gate_credit=False,
        hardware_verified=False,
    )


def write_kernel_build_tree_evidence(evidence: KernelBuildTreeDivergenceEvidence, destination: Path) -> str:
    path = Path(destination)
    if path.exists():
        raise KernelBuildTreeDiagnosticError(f"refusing to overwrite evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = evidence.canonical_json()
    path.write_text(payload, encoding="utf-8", newline="\n")
    return sha256(payload.encode("utf-8")).hexdigest()
