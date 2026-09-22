"""GUI bridge for the physical-phone bring-up workflow.

This module contains UI-independent helpers used by the PySide6 physical-test wizard.
It exposes only reviewed KaliPhoneStudio CLI boundaries: read-only baseline capture,
offline candidate preparation and one-shot temporary boot. There is no persistent
flash, erase or slot-change command builder here.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Callable, Sequence

from .fastboot_capture import FastbootCaptureError, list_fastboot_devices
from .fastboot_tool import FastbootToolError, inspect_fastboot_tool, load_fastboot_tool_policy


class PhysicalGuiBridgeError(RuntimeError):
    pass


@dataclass(frozen=True)
class FastbootDetection:
    serial: str
    platform_tools_version: str
    executable: Path
    executable_sha256: str


@dataclass(frozen=True)
class PhysicalSessionState:
    session_dir: Path
    baseline_ready: bool
    offline_candidate_ready: bool
    temporary_boot_recorded: bool


def runtime_candidate_root() -> Path:
    if getattr(sys, "frozen", False):
        executable_dir = Path(sys.executable).resolve().parent
        if executable_dir.name.lower() in {"kaliphonestudio", "kaliphonestudiocli"}:
            return executable_dir.parent
        return executable_dir
    return Path(__file__).resolve().parents[1]


def runtime_fastboot_policy(candidate_root: Path | None = None) -> Path:
    root = Path(candidate_root) if candidate_root is not None else runtime_candidate_root()
    for candidate in (
        root / "operator-pack" / "fastboot-tool-policy.json",
        root / "tools" / "fastboot-tool-policy.json",
    ):
        if candidate.is_file() and not candidate.is_symlink():
            return candidate
    raise PhysicalGuiBridgeError("reviewed Fastboot policy is missing from this candidate")


def runtime_cli_invocation(candidate_root: Path | None = None) -> tuple[str, tuple[str, ...]]:
    root = Path(candidate_root) if candidate_root is not None else runtime_candidate_root()
    frozen_cli = root / "KaliPhoneStudioCLI" / "KaliPhoneStudioCLI.exe"
    if frozen_cli.is_file() and not frozen_cli.is_symlink():
        return str(frozen_cli), ()
    source_main = root / "main.py"
    if source_main.is_file() and not source_main.is_symlink():
        return sys.executable, (str(source_main),)
    raise PhysicalGuiBridgeError("KaliPhoneStudio CLI entrypoint is missing")


def runtime_extractor(candidate_root: Path | None = None) -> Path | None:
    root = Path(candidate_root) if candidate_root is not None else runtime_candidate_root()
    candidate = root / "operator-tools" / "payload-dumper-go.exe"
    return candidate if candidate.is_file() and not candidate.is_symlink() else None


def runtime_reviewed_fastboot(candidate_root: Path | None = None) -> Path | None:
    """Return the candidate-local reviewed Fastboot when bootstrap has prepared it."""
    root = Path(candidate_root) if candidate_root is not None else runtime_candidate_root()
    try:
        policy_path = runtime_fastboot_policy(root)
        policy, _policy_sha256 = load_fastboot_tool_policy(policy_path)
    except (PhysicalGuiBridgeError, FastbootToolError):
        return None
    version = str(policy["platform_tools_version"])
    tool_root = root / "operator-runtime" / f"platform-tools-{version}" / "platform-tools"
    for filename in ("fastboot.exe", "fastboot"):
        candidate = tool_root / filename
        if candidate.is_file() and not candidate.is_symlink():
            return candidate.resolve()
    return None


def runtime_bootstrap_script(candidate_root: Path | None = None) -> Path | None:
    """Return the packaged download-only host bootstrap script, if available."""
    root = Path(candidate_root) if candidate_root is not None else runtime_candidate_root()
    candidate = root / "operator-pack" / "bootstrap-first-test.ps1"
    return candidate.resolve() if candidate.is_file() and not candidate.is_symlink() else None


def suggested_fastboot(
    candidate_root: Path | None = None,
    *,
    allow_path_fallback: bool = True,
) -> str:
    reviewed = runtime_reviewed_fastboot(candidate_root)
    if reviewed is not None:
        return str(reviewed)
    return (shutil.which("fastboot") or "") if allow_path_fallback else ""


def detect_single_fastboot_device(
    fastboot: str | Path,
    *,
    policy_path: Path | None = None,
    runner: Callable[..., Any] = subprocess.run,
) -> FastbootDetection:
    """Run only Fastboot version and device-list checks; never boot or write."""
    policy = Path(policy_path) if policy_path is not None else runtime_fastboot_policy()
    try:
        tool, resolved = inspect_fastboot_tool(fastboot, policy_path=policy, runner=runner)
        devices = list_fastboot_devices(fastboot=resolved, runner=runner)
    except (FastbootToolError, FastbootCaptureError) as exc:
        raise PhysicalGuiBridgeError(str(exc)) from exc
    if not devices:
        raise PhysicalGuiBridgeError("no Fastboot device detected")
    if len(devices) != 1:
        raise PhysicalGuiBridgeError(
            f"exactly one Fastboot device is required; detected {len(devices)}"
        )
    return FastbootDetection(
        serial=devices[0].serial,
        platform_tools_version=tool.observed_platform_tools_version,
        executable=resolved,
        executable_sha256=tool.executable_sha256,
    )


def _required_text(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise PhysicalGuiBridgeError(f"{label} is required")
    cleaned = value.strip()
    if not cleaned or any(ch in cleaned for ch in ("\x00", "\r", "\n")):
        raise PhysicalGuiBridgeError(f"{label} is missing or contains unsafe characters")
    return cleaned


def _required_file(path: str | Path, label: str) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_symlink() or not candidate.is_file():
        raise PhysicalGuiBridgeError(f"{label} must be an existing regular file")
    return candidate.resolve()


def _fresh_session_path(path: str | Path) -> Path:
    candidate = Path(path).expanduser().resolve(strict=False)
    if candidate.exists() or candidate.is_symlink():
        raise PhysicalGuiBridgeError("choose a fresh session path that does not exist yet")
    return candidate


def build_begin_session_args(
    *,
    profile_id: str,
    confirmation_token: str,
    serial: str,
    firmware_build: str,
    firmware_fingerprint: str,
    fastboot: str | Path,
    policy_path: str | Path,
    session_dir: str | Path,
) -> tuple[str, ...]:
    return (
        "begin-physical-test-session",
        "--profile-id", _required_text(profile_id, "profile id"),
        "--serial", _required_text(serial, "Fastboot serial"),
        "--firmware-build", _required_text(firmware_build, "firmware build"),
        "--firmware-fingerprint", _required_text(firmware_fingerprint, "firmware fingerprint"),
        "--confirm-token", _required_text(confirmation_token, "profile confirmation token"),
        "--fastboot", str(_required_file(fastboot, "Fastboot executable")),
        "--fastboot-policy", str(_required_file(policy_path, "Fastboot policy")),
        "--session-dir", str(_fresh_session_path(session_dir)),
    )


def build_prepare_candidate_args(
    *,
    profile_id: str,
    session_dir: str | Path,
    ota: str | Path,
    extractor: str | Path,
    first_boot_manifest: str | Path,
    authority_bundle: str | Path,
    boot_authorization: str | Path,
    boot_plan: str | Path,
    candidate_boot: str | Path,
    candidate_dtbo: str | Path,
    fastboot: str | Path,
) -> tuple[str, ...]:
    session = Path(session_dir).expanduser().resolve(strict=True)
    if not session.is_dir() or session.is_symlink():
        raise PhysicalGuiBridgeError("physical session directory is missing")
    return (
        "prepare-physical-candidate-offline",
        "--profile-id", _required_text(profile_id, "profile id"),
        "--session-dir", str(session),
        "--ota", str(_required_file(ota, "matching OxygenOS OTA")),
        "--extractor", str(_required_file(extractor, "OTA extractor")),
        "--extractor-platform", "windows-amd64",
        "--first-boot-manifest", str(_required_file(first_boot_manifest, "first-boot manifest")),
        "--authority-bundle", str(_required_file(authority_bundle, "authority bundle")),
        "--boot-authorization", str(_required_file(boot_authorization, "temporary-boot authorization")),
        "--boot-plan", str(_required_file(boot_plan, "boot plan")),
        "--candidate-boot", str(_required_file(candidate_boot, "candidate boot image")),
        "--candidate-dtbo", str(_required_file(candidate_dtbo, "candidate DTBO image")),
        "--fastboot-executable", str(_required_file(fastboot, "Fastboot executable")),
    )


def build_temporary_boot_args(
    *,
    profile_id: str,
    confirmation_token: str,
    session_dir: str | Path,
    fastboot: str | Path,
    boot_image: str | Path,
) -> tuple[str, ...]:
    session = Path(session_dir).expanduser().resolve(strict=True)
    if not session.is_dir() or session.is_symlink():
        raise PhysicalGuiBridgeError("physical session directory is missing")
    required = {
        "physical candidate gate": session / "physical-candidate-gate.json",
        "boot identity binding": session / "physical-boot-identity.json",
        "physical stock baseline": session / "physical-stock-baseline.json",
        "recovery readiness": session / "physical-recovery-readiness.json",
        "stock boot": session / "stock" / "partitions" / "boot.img",
        "Fastboot capture bundle": session / "fastboot" / "fastboot-capture-bundle.json",
        "Fastboot baseline": session / "fastboot" / "fastboot-baseline.json",
        "Fastboot tool evidence": session / "fastboot" / "fastboot-tool.json",
    }
    for label, path in required.items():
        _required_file(path, label)
    return (
        "execute-temporary-boot-once",
        "--profile-id", _required_text(profile_id, "profile id"),
        "--physical-candidate-gate", str(required["physical candidate gate"]),
        "--boot-identity-binding", str(required["boot identity binding"]),
        "--physical-baseline", str(required["physical stock baseline"]),
        "--recovery-readiness", str(required["recovery readiness"]),
        "--stock-boot", str(required["stock boot"]),
        "--capture-bundle", str(required["Fastboot capture bundle"]),
        "--baseline-evidence", str(required["Fastboot baseline"]),
        "--fastboot-tool-evidence", str(required["Fastboot tool evidence"]),
        "--fastboot-executable", str(_required_file(fastboot, "Fastboot executable")),
        "--boot-image", str(_required_file(boot_image, "candidate boot image")),
        "--confirmation", _required_text(confirmation_token, "temporary-boot confirmation"),
        "--execute-temporary-boot",
        "--probe-out", str(session / "temporary-boot-runtime-probe.json"),
        "--execution-out", str(session / "temporary-boot-execution.json"),
    )


def inspect_session_state(session_dir: str | Path) -> PhysicalSessionState:
    session = Path(session_dir).expanduser().resolve(strict=False)
    baseline_files = (
        session / "physical-first-test-session.json",
        session / "fastboot" / "fastboot-getvar-all.txt",
        session / "fastboot" / "fastboot-baseline.json",
        session / "fastboot" / "fastboot-tool.json",
        session / "fastboot" / "fastboot-capture-bundle.json",
    )
    candidate_files = (
        session / "physical-candidate-offline-preparation.json",
        session / "physical-candidate-gate.json",
        session / "physical-boot-identity.json",
        session / "physical-recovery-readiness.json",
        session / "stock" / "partitions" / "boot.img",
    )
    temporary_files = (
        session / "temporary-boot-runtime-probe.json",
        session / "temporary-boot-execution.json",
    )
    regular = lambda p: p.is_file() and not p.is_symlink()
    return PhysicalSessionState(
        session_dir=session,
        baseline_ready=all(regular(path) for path in baseline_files),
        offline_candidate_ready=all(regular(path) for path in candidate_files),
        temporary_boot_recorded=all(regular(path) for path in temporary_files),
    )


def ensure_no_persistent_write_verbs(args: Sequence[str]) -> None:
    forbidden = {"flash", "erase", "set_active", "flashing", "wipe"}
    tokens = {str(item).strip().lower() for item in args}
    overlap = forbidden & tokens
    if overlap:
        raise PhysicalGuiBridgeError(
            "persistent write verb unexpectedly entered the GUI command boundary: "
            + ", ".join(sorted(overlap))
        )
