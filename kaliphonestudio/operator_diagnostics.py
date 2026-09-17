"""Safe offline operator diagnostics and profile-driven recovery guidance.

This module deliberately performs no ADB/Fastboot/device I/O.  It inspects only
local repository state, validates device profiles, detects whether selected host
tools are present, and can export a deterministic redacted JSON bundle for
support/review.  Hardware support and Beta credit are never inferred here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import tempfile
from typing import Any, Callable, Iterable

from . import __version__
from .profiles import DeviceProfile, ProfileError, discover_profiles, get_profile


DIAGNOSTICS_SCHEMA_VERSION = 1
RECOVERY_GUIDE_SCHEMA_VERSION = 1
OPERATOR_BUNDLE_SCHEMA_VERSION = 1
_SUPPORTED_CHECK_STATUSES = frozenset({"pass", "warn", "fail"})


class OperatorDiagnosticsError(ValueError):
    """Raised when an operator diagnostics/recovery export cannot be trusted."""


@dataclass(frozen=True)
class DiagnosticCheck:
    check_id: str
    status: str
    summary: str
    detail: str

    def __post_init__(self) -> None:
        if self.status not in _SUPPORTED_CHECK_STATUSES:
            raise OperatorDiagnosticsError(f"unsupported diagnostic status: {self.status}")
        if not self.check_id or not self.summary:
            raise OperatorDiagnosticsError("diagnostic checks require a non-empty id and summary")


@dataclass(frozen=True)
class HostToolStatus:
    name: str
    available: bool
    purpose: str


@dataclass(frozen=True)
class OperatorDiagnosticReport:
    schema_version: int
    application: str
    application_version: str
    platform: str
    python_version: str
    repository_status_sha256: str
    beta_gate: str
    project_progress_percent: int | None
    profile_count: int
    selected_profile_id: str | None
    selected_profile_sha256: str | None
    host_tools: tuple[HostToolStatus, ...]
    checks: tuple[DiagnosticCheck, ...]
    pass_count: int
    warning_count: int
    failure_count: int
    offline_review_ready: bool
    physical_interaction_performed: bool
    hardware_verified: bool
    beta_gate_credit: bool
    beta_blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RecoveryGuide:
    schema_version: int
    profile_id: str
    display_name: str
    confirmation_token: str
    ab_device: bool
    preferred_boot_mode: str
    target_selection_allowed: bool
    persistent_write_authorized: bool
    forbidden_partitions: tuple[str, ...]
    required_physical_evidence: tuple[str, ...]
    steps: tuple[str, ...]
    profile_recovery_notes: tuple[str, ...]
    hardware_verified: bool
    beta_gate_credit: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json_object(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise OperatorDiagnosticsError(f"cannot read {label}: {path}: {exc}") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OperatorDiagnosticsError(f"{label} is not valid UTF-8 JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise OperatorDiagnosticsError(f"{label} must contain a JSON object: {path}")
    return payload, raw


def _python_minor(version_info: tuple[int, ...] | None = None) -> tuple[int, int]:
    source = tuple(version_info or tuple(sys.version_info[:3]))
    if len(source) < 2:
        raise OperatorDiagnosticsError("Python version information is incomplete")
    return int(source[0]), int(source[1])


def _profile_digest(profile: DeviceProfile) -> str:
    try:
        raw = profile.path.read_bytes()
    except OSError as exc:
        raise OperatorDiagnosticsError(
            f"cannot read selected profile bytes: {profile.path}: {exc}"
        ) from exc
    return _sha256(raw)


def _tool_status(
    name: str,
    purpose: str,
    executable_finder: Callable[[str], str | None],
) -> HostToolStatus:
    # Deliberately store only a boolean. Absolute tool paths can contain a user
    # name/home directory and therefore are not exported in support bundles.
    return HostToolStatus(name=name, available=bool(executable_finder(name)), purpose=purpose)


def _status_check(check_id: str, status: str, summary: str, detail: str) -> DiagnosticCheck:
    return DiagnosticCheck(check_id=check_id, status=status, summary=summary, detail=detail)


def build_diagnostic_report(
    *,
    repo_root: Path,
    devices_root: Path,
    profile_id: str | None = None,
    executable_finder: Callable[[str], str | None] = shutil.which,
    version_info: tuple[int, ...] | None = None,
    platform_name: str | None = None,
) -> OperatorDiagnosticReport:
    """Build a read-only host diagnostics report.

    The function never runs an external executable.  Tool discovery is limited to
    ``shutil.which``-style presence checks, and exported tool paths are redacted.
    """

    repo_root = Path(repo_root)
    devices_root = Path(devices_root)
    checks: list[DiagnosticCheck] = []

    build_status_path = repo_root / "BUILD_STATUS.json"
    status, status_bytes = _read_json_object(build_status_path, "BUILD_STATUS.json")

    ledger_version = status.get("version")
    if ledger_version == __version__:
        checks.append(
            _status_check(
                "version-sync",
                "pass",
                "Application and status-ledger versions match",
                f"Both report {__version__}.",
            )
        )
    else:
        checks.append(
            _status_check(
                "version-sync",
                "fail",
                "Application/status-ledger version mismatch",
                f"package={__version__!r}, BUILD_STATUS={ledger_version!r}",
            )
        )

    ci_versions_raw = status.get("python_ci", [])
    ci_versions = {
        item.strip() for item in ci_versions_raw if isinstance(item, str) and item.strip()
    } if isinstance(ci_versions_raw, list) else set()
    py_major, py_minor = _python_minor(version_info)
    py_label = f"{py_major}.{py_minor}"
    if py_major < 3 or (py_major == 3 and py_minor < 11):
        checks.append(
            _status_check(
                "python-runtime",
                "fail",
                "Python runtime is too old",
                f"Detected {py_label}; KaliPhoneStudio host tooling requires Python 3.11+.",
            )
        )
    elif py_label in ci_versions:
        checks.append(
            _status_check(
                "python-runtime",
                "pass",
                "Python runtime is covered by CI",
                f"Detected {py_label}; BUILD_STATUS lists it in python_ci.",
            )
        )
    else:
        checks.append(
            _status_check(
                "python-runtime",
                "warn",
                "Python runtime is outside the recorded CI matrix",
                f"Detected {py_label}; recorded CI versions: {', '.join(sorted(ci_versions)) or 'none'}.",
            )
        )

    progress = status.get("project_progress_percent")
    if isinstance(progress, int) and not isinstance(progress, bool) and 0 <= progress <= 100:
        progress_value: int | None = progress
        checks.append(
            _status_check(
                "progress-ledger",
                "pass",
                "Project progress ledger value is structurally valid",
                f"Current reviewed roadmap value: {progress}% (not Beta readiness).",
            )
        )
    else:
        progress_value = None
        checks.append(
            _status_check(
                "progress-ledger",
                "fail",
                "Project progress ledger value is invalid",
                "BUILD_STATUS.project_progress_percent must be an integer from 0 through 100.",
            )
        )

    beta_gate = status.get("beta_gate")
    if isinstance(beta_gate, str) and beta_gate.strip():
        beta_gate_value = beta_gate.strip()
        checks.append(
            _status_check(
                "beta-gate-ledger",
                "pass",
                "Beta gate state is explicit",
                f"BUILD_STATUS reports Beta gate: {beta_gate_value}.",
            )
        )
    else:
        beta_gate_value = "UNKNOWN"
        checks.append(
            _status_check(
                "beta-gate-ledger",
                "fail",
                "Beta gate state is missing",
                "BUILD_STATUS.beta_gate must be a non-empty string.",
            )
        )

    safety_files = (
        repo_root / "BETA_RELEASE_GATE.md",
        repo_root / "tools" / "fastboot-tool-policy.json",
        repo_root / "assets" / "readme" / "progress-card.svg",
        repo_root / "assets" / "readme" / "progress-mini.svg",
    )
    missing_safety_files = [str(path.relative_to(repo_root)) for path in safety_files if not path.is_file()]
    if missing_safety_files:
        checks.append(
            _status_check(
                "repository-safety-files",
                "fail",
                "Required repository safety/status files are missing",
                ", ".join(missing_safety_files),
            )
        )
    else:
        checks.append(
            _status_check(
                "repository-safety-files",
                "pass",
                "Required repository safety/status files are present",
                "Beta gate, Fastboot policy and SWIR progress assets are available.",
            )
        )

    try:
        profiles = discover_profiles(devices_root)
    except ProfileError as exc:
        profiles = []
        checks.append(
            _status_check(
                "profile-catalog",
                "fail",
                "Device profile catalog validation failed",
                str(exc),
            )
        )
    else:
        checks.append(
            _status_check(
                "profile-catalog",
                "pass" if profiles else "warn",
                "Device profile catalog validated" if profiles else "No device profiles were found",
                f"Validated profiles: {len(profiles)}.",
            )
        )

    selected: DeviceProfile | None = None
    selected_digest: str | None = None
    if profile_id:
        try:
            selected = get_profile(devices_root, profile_id)
            selected_digest = _profile_digest(selected)
        except (ProfileError, OperatorDiagnosticsError) as exc:
            checks.append(
                _status_check(
                    "selected-profile",
                    "fail",
                    "Selected profile could not be validated",
                    str(exc),
                )
            )
        else:
            checks.append(
                _status_check(
                    "selected-profile",
                    "pass",
                    "Selected profile validated",
                    f"Using {selected.profile_id}; exact profile bytes SHA-256={selected_digest}.",
                )
            )
            handoff = selected.data.get("rootfs_handoff")
            if isinstance(handoff, dict):
                target_allowed = handoff.get("target_selection_allowed")
                write_allowed = handoff.get("persistent_write_authorized")
                if target_allowed is False and write_allowed is False:
                    checks.append(
                        _status_check(
                            "profile-write-safety",
                            "pass",
                            "Profile rootfs handoff remains discovery-only",
                            "No target selection or persistent storage write is authorized by the profile.",
                        )
                    )
                else:
                    checks.append(
                        _status_check(
                            "profile-write-safety",
                            "fail",
                            "Selected profile does not satisfy the expected fail-closed handoff state",
                            f"target_selection_allowed={target_allowed!r}, persistent_write_authorized={write_allowed!r}",
                        )
                    )
            else:
                checks.append(
                    _status_check(
                        "profile-write-safety",
                        "warn",
                        "Selected profile has no rootfs_handoff contract",
                        "No write authorization is inferred; a dedicated reviewed strategy is still required.",
                    )
                )

    tools = (
        _tool_status(
            "fastboot",
            "physical baseline/temporary-boot workflows; diagnostics never execute it",
            executable_finder,
        ),
        _tool_status(
            "adb",
            "optional later Android-side diagnostics; not required by the offline profile browser",
            executable_finder,
        ),
        _tool_status("git", "source-lock/reproducibility workflows", executable_finder),
    )
    fastboot = next(item for item in tools if item.name == "fastboot")
    checks.append(
        _status_check(
            "fastboot-host-tool",
            "pass" if fastboot.available else "warn",
            "Fastboot host tool is discoverable" if fastboot.available else "Fastboot host tool was not found",
            "Presence only; no Fastboot command was executed and no phone state was inspected.",
        )
    )
    git_tool = next(item for item in tools if item.name == "git")
    checks.append(
        _status_check(
            "git-host-tool",
            "pass" if git_tool.available else "warn",
            "Git host tool is discoverable" if git_tool.available else "Git host tool was not found",
            "Git is used by source-lock/reproducibility workflows; no Git command was executed by doctor mode.",
        )
    )

    failures = sum(item.status == "fail" for item in checks)
    warnings = sum(item.status == "warn" for item in checks)
    passes = sum(item.status == "pass" for item in checks)
    blockers_raw = status.get("beta_blockers", [])
    beta_blockers = tuple(
        item.strip() for item in blockers_raw if isinstance(item, str) and item.strip()
    ) if isinstance(blockers_raw, list) else ()

    return OperatorDiagnosticReport(
        schema_version=DIAGNOSTICS_SCHEMA_VERSION,
        application="KaliPhoneStudio",
        application_version=__version__,
        platform=(platform_name or platform.system() or "unknown"),
        python_version=py_label,
        repository_status_sha256=_sha256(status_bytes),
        beta_gate=beta_gate_value,
        project_progress_percent=progress_value,
        profile_count=len(profiles),
        selected_profile_id=selected.profile_id if selected else None,
        selected_profile_sha256=selected_digest,
        host_tools=tools,
        checks=tuple(checks),
        pass_count=passes,
        warning_count=warnings,
        failure_count=failures,
        offline_review_ready=failures == 0,
        physical_interaction_performed=False,
        hardware_verified=False,
        beta_gate_credit=False,
        beta_blockers=beta_blockers,
    )


def build_recovery_guide(profile: DeviceProfile) -> RecoveryGuide:
    """Build profile-driven, non-executing recovery guidance for an operator."""

    data = profile.data
    handoff = data.get("rootfs_handoff")
    if isinstance(handoff, dict):
        target_selection_allowed = bool(handoff.get("target_selection_allowed", False))
        persistent_write_authorized = bool(handoff.get("persistent_write_authorized", False))
        forbidden_raw = handoff.get("forbidden_partitions", [])
        evidence_raw = handoff.get("required_physical_evidence", [])
        forbidden = tuple(str(item) for item in forbidden_raw if isinstance(item, str) and item)
        required_evidence = tuple(str(item) for item in evidence_raw if isinstance(item, str) and item)
    else:
        target_selection_allowed = False
        persistent_write_authorized = False
        forbidden = ()
        required_evidence = ()

    # This workflow is guidance only. If a future profile deliberately permits a
    # persistent strategy, that still must not become an implicit authorization
    # from the operator workspace.
    steps = (
        "Confirm the exact profile/device identity and firmware baseline before any device-side action.",
        "Capture and preserve the exact stock boot/recovery provenance and checksums for the physical baseline.",
        "Prefer a non-persistent temporary boot; this guide does not authorize persistent flashing or storage writes.",
        "Capture rescue markers/logs and bounded read-only diagnostics before considering any storage strategy.",
        "Collect and manually review the profile-required physical storage/recovery evidence; never infer a block-device target from a host-side hint.",
        "Stop on any profile, serial, firmware, candidate, transcript or recovery-path mismatch instead of attempting to repair it automatically.",
        "Exercise the documented rollback/recovery path on the exact physical baseline before granting any Beta credit.",
    )

    return RecoveryGuide(
        schema_version=RECOVERY_GUIDE_SCHEMA_VERSION,
        profile_id=profile.profile_id,
        display_name=str(data["display_name"]),
        confirmation_token=profile.confirmation_text,
        ab_device=bool(data["ab_device"]),
        preferred_boot_mode="temporary-fastboot-boot",
        target_selection_allowed=target_selection_allowed,
        persistent_write_authorized=False,
        forbidden_partitions=forbidden,
        required_physical_evidence=required_evidence,
        steps=steps,
        profile_recovery_notes=tuple(str(item) for item in data["recovery_notes"]),
        hardware_verified=False,
        beta_gate_credit=False,
    )


def format_diagnostic_report(report: OperatorDiagnosticReport) -> str:
    lines = [
        f"KaliPhoneStudio {report.application_version} — offline host doctor",
        f"Platform/Python: {report.platform} / {report.python_version}",
        f"Profiles validated: {report.profile_count}",
        f"Selected profile: {report.selected_profile_id or 'none'}",
        f"Project progress: {report.project_progress_percent if report.project_progress_percent is not None else 'N/A'}%" if report.project_progress_percent is not None else "Project progress: N/A",
        f"Beta gate: {report.beta_gate}",
        "",
    ]
    for item in report.checks:
        lines.append(f"[{item.status.upper():4}] {item.check_id}: {item.summary}")
        lines.append(f"       {item.detail}")
    lines.extend(
        [
            "",
            f"Summary: {report.pass_count} pass, {report.warning_count} warning, {report.failure_count} fail",
            f"Offline review ready: {'yes' if report.offline_review_ready else 'no'}",
            "Physical interaction performed: no",
            "Hardware verified: no",
            "Beta gate credit: no",
        ]
    )
    return "\n".join(lines)


def format_recovery_guide(guide: RecoveryGuide) -> str:
    lines = [
        f"Recovery guide — {guide.display_name} ({guide.profile_id})",
        f"Confirmation token: {guide.confirmation_token}",
        f"A/B device: {'yes' if guide.ab_device else 'no'}",
        f"Preferred boot mode: {guide.preferred_boot_mode}",
        f"Target selection allowed by current profile: {'yes' if guide.target_selection_allowed else 'no'}",
        "Persistent write authorized by this guide: no",
        "",
        "Safe operator sequence:",
    ]
    lines.extend(f"  {index}. {step}" for index, step in enumerate(guide.steps, start=1))
    if guide.required_physical_evidence:
        lines.append("")
        lines.append("Required physical evidence before storage strategy review:")
        lines.extend(f"  - {item}" for item in guide.required_physical_evidence)
    if guide.forbidden_partitions:
        lines.append("")
        lines.append("Partitions forbidden by the current handoff contract:")
        lines.append("  " + ", ".join(guide.forbidden_partitions))
    if guide.profile_recovery_notes:
        lines.append("")
        lines.append("Profile recovery notes:")
        lines.extend(f"  - {item}" for item in guide.profile_recovery_notes)
    lines.extend(["", "Hardware verified: no", "Beta gate credit: no"])
    return "\n".join(lines)


def build_operator_bundle(
    report: OperatorDiagnosticReport,
    recovery_guide: RecoveryGuide | None = None,
) -> dict[str, Any]:
    if recovery_guide and report.selected_profile_id != recovery_guide.profile_id:
        raise OperatorDiagnosticsError(
            "diagnostics report selected profile does not match the recovery guide"
        )
    return {
        "schema_version": OPERATOR_BUNDLE_SCHEMA_VERSION,
        "kind": "kaliphonestudio-offline-operator-bundle",
        "privacy": {
            "external_commands_executed": False,
            "device_queried": False,
            "absolute_tool_paths_exported": False,
        },
        "diagnostics": report.to_dict(),
        "recovery_guide": recovery_guide.to_dict() if recovery_guide else None,
        "hardware_verified": False,
        "beta_gate_credit": False,
    }


def write_operator_bundle(path: Path, bundle: dict[str, Any]) -> str:
    """Atomically write one deterministic operator bundle and return its SHA-256."""

    destination = Path(path)
    parent = destination.parent if destination.parent != Path("") else Path(".")
    if destination.exists() and destination.is_symlink():
        raise OperatorDiagnosticsError("refusing to replace a symlink diagnostics destination")
    if parent.exists() and parent.is_symlink():
        raise OperatorDiagnosticsError("refusing to write diagnostics through a symlink parent")
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OperatorDiagnosticsError(f"cannot create diagnostics directory: {parent}: {exc}") from exc
    if not parent.is_dir():
        raise OperatorDiagnosticsError(f"diagnostics parent is not a directory: {parent}")

    data = _canonical_json_bytes(bundle)
    tmp_name: str | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=parent)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, destination)
        tmp_name = None
    except OSError as exc:
        raise OperatorDiagnosticsError(f"cannot write diagnostics bundle: {destination}: {exc}") from exc
    finally:
        if tmp_name:
            try:
                Path(tmp_name).unlink(missing_ok=True)
            except OSError:
                pass
    return _sha256(data)


def validate_operator_bundle(bundle: dict[str, Any]) -> None:
    """Fail closed on the safety invariants of an exported operator bundle."""

    if bundle.get("schema_version") != OPERATOR_BUNDLE_SCHEMA_VERSION:
        raise OperatorDiagnosticsError("unsupported operator bundle schema")
    if bundle.get("kind") != "kaliphonestudio-offline-operator-bundle":
        raise OperatorDiagnosticsError("unexpected operator bundle kind")
    privacy = bundle.get("privacy")
    if not isinstance(privacy, dict):
        raise OperatorDiagnosticsError("operator bundle privacy section is missing")
    expected_privacy = {
        "external_commands_executed": False,
        "device_queried": False,
        "absolute_tool_paths_exported": False,
    }
    if privacy != expected_privacy:
        raise OperatorDiagnosticsError("operator bundle privacy invariants were changed")
    if bundle.get("hardware_verified") is not False or bundle.get("beta_gate_credit") is not False:
        raise OperatorDiagnosticsError("offline operator bundle cannot grant hardware/Beta credit")
    diagnostics = bundle.get("diagnostics")
    if not isinstance(diagnostics, dict):
        raise OperatorDiagnosticsError("operator bundle diagnostics section is missing")
    for field in ("physical_interaction_performed", "hardware_verified", "beta_gate_credit"):
        if diagnostics.get(field) is not False:
            raise OperatorDiagnosticsError(f"offline diagnostics must keep {field}=false")


def load_operator_bundle(path: Path) -> dict[str, Any]:
    payload, _ = _read_json_object(Path(path), "operator diagnostics bundle")
    validate_operator_bundle(payload)
    return payload
