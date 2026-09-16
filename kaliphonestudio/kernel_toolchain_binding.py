"""Bind an exact kernel plan to the source-locked compiler it declares.

The common kernel contract intentionally stays device-independent.  This module
bridges that plan to a separately reviewed Android Clang source lock by checking
the exact kernel checkout's build configuration.  The result is provenance
evidence only: it does not compile, boot, flash, or claim hardware success.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any

from .kernel_contract import KernelBuildPlan, KernelContractError
from .kernel_toolchain import KernelToolchainLock


_ASSIGN_RE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")
MAX_BUILD_CONFIG_BYTES = 1024 * 1024


@dataclass(frozen=True)
class KernelToolchainBindingEvidence:
    schema_version: int
    profile_id: str
    kernel_plan_sha256: str
    kernel_source_commit: str
    toolchain_lock_sha256: str
    clang_revision: str
    build_config_path: str
    build_config_sha256: str
    llvm_mode: str
    clang_prebuilt_bin: str
    beta_gate_credit: bool = False

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _safe_relative(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KernelContractError(f"{field} must be a non-empty relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or "." in path.parts or ".." in path.parts:
        raise KernelContractError(f"{field} must be a safe relative POSIX path")
    if any(not part or "\\" in part or any(ord(ch) < 0x20 for ch in part) for part in path.parts):
        raise KernelContractError(f"{field} contains unsafe path data")
    return path.as_posix()


def _parse_simple_assignments(payload: bytes) -> dict[str, str]:
    if not payload or len(payload) > MAX_BUILD_CONFIG_BYTES:
        raise KernelContractError("kernel build config is empty or exceeds the safety limit")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise KernelContractError("kernel build config must be UTF-8") from exc

    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _ASSIGN_RE.fullmatch(line)
        if not match:
            continue
        key, value = match.groups()
        if key in values and values[key] != value:
            raise KernelContractError(f"kernel build config has conflicting duplicate {key}")
        values[key] = value
    return values


def bind_kernel_plan_to_toolchain(
    plan: KernelBuildPlan,
    lock: KernelToolchainLock,
    kernel_checkout: Path,
    *,
    build_config_relative: str = "build.config.common",
) -> KernelToolchainBindingEvidence:
    """Require the exact kernel build config to select the locked Clang revision."""
    if plan.schema_version != 1:
        raise KernelContractError("unsupported kernel build plan schema for toolchain binding")
    flags = dict(plan.make_flags)
    if flags.get("LLVM") != "1":
        raise KernelContractError("kernel plan must explicitly require LLVM=1")
    if lock.beta_gate_credit is not False:
        raise KernelContractError("kernel toolchain lock cannot grant Beta hardware credit")

    relative = _safe_relative(build_config_relative, "build_config_relative")
    if not kernel_checkout.is_dir() or kernel_checkout.is_symlink():
        raise KernelContractError("kernel checkout must be a real directory")
    root = kernel_checkout.resolve(strict=True)
    candidate = root.joinpath(*PurePosixPath(relative).parts)
    if candidate.is_symlink():
        raise KernelContractError("kernel build config must not be a symlink")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise KernelContractError("kernel build config is missing") from exc
    if root != resolved and root not in resolved.parents:
        raise KernelContractError("kernel build config escapes checkout")
    if not resolved.is_file():
        raise KernelContractError("kernel build config must be a regular file")

    size_before = resolved.stat().st_size
    if size_before <= 0 or size_before > MAX_BUILD_CONFIG_BYTES:
        raise KernelContractError("kernel build config is empty or exceeds the safety limit")
    payload = resolved.read_bytes()
    if len(payload) != size_before or resolved.stat().st_size != size_before:
        raise KernelContractError("kernel build config changed while reading")
    values = _parse_simple_assignments(payload)

    if values.get("LLVM") != "1":
        raise KernelContractError("kernel build config must declare LLVM=1")
    declared = values.get("CLANG_PREBUILT_BIN")
    if not declared:
        raise KernelContractError("kernel build config does not declare CLANG_PREBUILT_BIN")
    normalized = PurePosixPath(declared)
    if normalized.is_absolute() or ".." in normalized.parts or "." in normalized.parts:
        raise KernelContractError("CLANG_PREBUILT_BIN must be a safe relative path")
    if any(
        not part or "\\" in part or any(ord(ch) < 0x20 for ch in part)
        for part in normalized.parts
    ):
        raise KernelContractError("CLANG_PREBUILT_BIN contains unsafe path data")
    expected_suffix = PurePosixPath(lock.subtree) / "bin"
    if tuple(normalized.parts[-len(expected_suffix.parts):]) != expected_suffix.parts:
        raise KernelContractError(
            f"kernel build config selects {declared!r}, not locked {lock.clang_revision}"
        )

    return KernelToolchainBindingEvidence(
        schema_version=1,
        profile_id=plan.profile_id,
        kernel_plan_sha256=plan.plan_sha256(),
        kernel_source_commit=plan.source_commit,
        toolchain_lock_sha256=lock.lock_sha256(),
        clang_revision=lock.clang_revision,
        build_config_path=relative,
        build_config_sha256=sha256(payload).hexdigest(),
        llvm_mode="1",
        clang_prebuilt_bin=normalized.as_posix(),
        beta_gate_credit=False,
    )
