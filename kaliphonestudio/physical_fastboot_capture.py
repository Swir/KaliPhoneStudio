"""Guarded physical Fastboot baseline capture orchestration.

This module is the single operator-facing implementation for capturing one exact
read-only physical Fastboot baseline. It verifies the profile-specific
confirmation token before any external command, verifies the reviewed Fastboot
binary, executes only ``fastboot --version``, ``fastboot devices`` and
``fastboot -s SERIAL getvar all``, then publishes an exact four-file evidence
set. It never boots, reboots, flashes, erases, changes slots or writes phone
storage. A successful capture is evidence input only and grants no hardware or
Beta credit.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
from typing import Sequence

from .fastboot_baseline import (
    FastbootBaselineError,
    capture_fastboot_baseline,
    write_fastboot_baseline_evidence,
)
from .fastboot_capture import (
    FastbootCaptureError,
    capture_fastboot_getvar_all,
    validate_capture_with_offline_parser,
    write_capture_once,
)
from .fastboot_capture_bundle import (
    FastbootCaptureBundleError,
    bind_fastboot_capture,
    write_fastboot_capture_bundle,
)
from .fastboot_tool import (
    FastbootToolError,
    inspect_fastboot_tool,
    write_fastboot_tool_evidence,
)
from .profiles import DeviceProfile, ProfileError, get_profile


DEFAULT_TRANSCRIPT_NAME = "fastboot-getvar-all.txt"
DEFAULT_BASELINE_NAME = "fastboot-baseline.json"
DEFAULT_TOOL_EVIDENCE_NAME = "fastboot-tool.json"
DEFAULT_CAPTURE_BUNDLE_NAME = "fastboot-capture-bundle.json"
DEFAULT_FASTBOOT_POLICY = Path(__file__).resolve().parents[1] / "tools" / "fastboot-tool-policy.json"


class PhysicalFastbootCaptureError(RuntimeError):
    """Raised when guarded physical baseline capture cannot proceed safely."""


@dataclass(frozen=True)
class PhysicalFastbootCaptureResult:
    profile_id: str
    product: str
    serialno: str
    current_slot: str
    slot_count: int
    unlocked: bool
    secure: bool
    firmware_build: str
    firmware_fingerprint: str
    transcript_sha256: str
    baseline_evidence_sha256: str
    fastboot_platform_tools_version: str
    fastboot_executable_sha256: str
    fastboot_tool_evidence_sha256: str
    fastboot_capture_bundle_sha256: str
    capture_policy: str
    confirmation_token_verified: bool
    physical_interaction_performed: bool
    read_only: bool
    phone_storage_written: bool
    persistent_write_authorized: bool
    hardware_verified: bool
    beta_gate_credit: bool
    outputs: dict[str, str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class FastbootCaptureDestinations:
    transcript: Path
    baseline: Path
    tool: Path
    capture: Path

    def items(self) -> tuple[tuple[Path, str], ...]:
        return (
            (self.transcript, "transcript"),
            (self.baseline, "baseline evidence"),
            (self.tool, "Fastboot tool evidence"),
            (self.capture, "Fastboot capture bundle"),
        )


def default_destinations(output_dir: Path) -> FastbootCaptureDestinations:
    root = Path(output_dir)
    return FastbootCaptureDestinations(
        transcript=root / DEFAULT_TRANSCRIPT_NAME,
        baseline=root / DEFAULT_BASELINE_NAME,
        tool=root / DEFAULT_TOOL_EVIDENCE_NAME,
        capture=root / DEFAULT_CAPTURE_BUNDLE_NAME,
    )


def _identity(path: Path) -> str:
    value = str(Path(path).expanduser().resolve(strict=False))
    return value.casefold() if os.name == "nt" else value


def _reject_symlink_ancestor(path: Path) -> None:
    current = Path(path).parent
    while True:
        if current.exists() and current.is_symlink():
            raise PhysicalFastbootCaptureError(
                f"refusing output below symlinked directory: {current}"
            )
        parent = current.parent
        if parent == current:
            break
        current = parent


def _staged(path: Path) -> Path:
    return path.with_name(path.name + ".capturing")


def _writer_tmp(path: Path) -> Path:
    return path.with_name(path.name + ".tmp")


def _validate_destinations(destinations: FastbootCaptureDestinations) -> None:
    finals = [path for path, _label in destinations.items()]
    staged = [_staged(path) for path in finals]
    writer_tmps = [_writer_tmp(path) for path in staged]
    identities = [_identity(path) for path in (*finals, *staged, *writer_tmps)]
    if len(set(identities)) != len(identities):
        raise PhysicalFastbootCaptureError(
            "capture destinations/staging paths must be distinct"
        )

    for path, label in destinations.items():
        _reject_symlink_ancestor(path)
        if path.exists() or path.is_symlink():
            raise PhysicalFastbootCaptureError(
                f"refusing to overwrite existing {label}: {path}"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        _reject_symlink_ancestor(path)

    for path in (*staged, *writer_tmps):
        if path.exists() or path.is_symlink():
            raise PhysicalFastbootCaptureError(
                f"refusing stale capture staging path: {path}"
            )


def capture_physical_fastboot_baseline(
    profile: DeviceProfile,
    *,
    confirmation_token: str,
    serial: str,
    firmware_build: str,
    firmware_fingerprint: str,
    destinations: FastbootCaptureDestinations,
    fastboot: str | Path = "fastboot",
    fastboot_policy: Path = DEFAULT_FASTBOOT_POLICY,
    tool_timeout_seconds: int = 15,
    capture_timeout_seconds: int = 30,
) -> PhysicalFastbootCaptureResult:
    """Capture and publish one exact read-only baseline evidence set.

    The profile confirmation token is checked before any Fastboot executable is
    inspected or run. All final and staging destinations are validated before
    device interaction. On any failure after publication begins, all newly
    published final files are removed and every staging file is cleaned up.
    """
    if not isinstance(profile, DeviceProfile):
        raise PhysicalFastbootCaptureError("a validated DeviceProfile is required")
    if confirmation_token != profile.confirmation_text:
        raise PhysicalFastbootCaptureError(
            "confirmation token does not match the selected device profile"
        )
    if not isinstance(serial, str) or not serial.strip():
        raise PhysicalFastbootCaptureError("exact fastboot serial is required")
    if not isinstance(firmware_build, str) or not firmware_build.strip():
        raise PhysicalFastbootCaptureError("exact firmware build is required")
    if not isinstance(firmware_fingerprint, str) or not firmware_fingerprint.strip():
        raise PhysicalFastbootCaptureError("exact firmware fingerprint is required")

    _validate_destinations(destinations)

    try:
        tool_evidence, resolved_fastboot = inspect_fastboot_tool(
            fastboot,
            policy_path=Path(fastboot_policy),
            timeout_seconds=tool_timeout_seconds,
        )
        payload = capture_fastboot_getvar_all(
            serial,
            fastboot=resolved_fastboot,
            timeout_seconds=capture_timeout_seconds,
        )
        validate_capture_with_offline_parser(payload)
    except (FastbootCaptureError, FastbootToolError) as exc:
        raise PhysicalFastbootCaptureError(str(exc)) from exc

    staged = FastbootCaptureDestinations(
        transcript=_staged(destinations.transcript),
        baseline=_staged(destinations.baseline),
        tool=_staged(destinations.tool),
        capture=_staged(destinations.capture),
    )
    published: list[Path] = []
    try:
        write_capture_once(payload, staged.transcript)
        evidence = capture_fastboot_baseline(
            profile,
            transcript=staged.transcript,
            firmware_build=firmware_build,
            firmware_fingerprint=firmware_fingerprint,
        )
        if evidence.serialno != serial.strip():
            raise PhysicalFastbootCaptureError(
                "captured getvar serialno does not match requested fastboot serial"
            )

        baseline_digest = write_fastboot_baseline_evidence(evidence, staged.baseline)
        tool_digest = write_fastboot_tool_evidence(tool_evidence, staged.tool)
        capture_bundle = bind_fastboot_capture(
            profile,
            evidence,
            tool_evidence,
            transcript=staged.transcript,
        )
        capture_digest = write_fastboot_capture_bundle(capture_bundle, staged.capture)

        if json.loads(staged.baseline.read_text(encoding="utf-8")) != json.loads(
            evidence.canonical_json()
        ):
            raise PhysicalFastbootCaptureError("Fastboot baseline evidence round-trip mismatch")
        if json.loads(staged.tool.read_text(encoding="utf-8")) != json.loads(
            tool_evidence.canonical_json()
        ):
            raise PhysicalFastbootCaptureError("Fastboot tool evidence round-trip mismatch")
        if json.loads(staged.capture.read_text(encoding="utf-8")) != json.loads(
            capture_bundle.canonical_json()
        ):
            raise PhysicalFastbootCaptureError("Fastboot capture bundle round-trip mismatch")
        if any(path.exists() or path.is_symlink() for path, _label in destinations.items()):
            raise PhysicalFastbootCaptureError("capture destination appeared during validation")

        for staged_path, final_path in (
            (staged.transcript, destinations.transcript),
            (staged.baseline, destinations.baseline),
            (staged.tool, destinations.tool),
            (staged.capture, destinations.capture),
        ):
            staged_path.replace(final_path)
            published.append(final_path)
    except (
        FastbootBaselineError,
        FastbootCaptureError,
        FastbootToolError,
        FastbootCaptureBundleError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
    ) as exc:
        for path in reversed(published):
            path.unlink(missing_ok=True)
        raise PhysicalFastbootCaptureError(str(exc)) from exc
    except BaseException:
        for path in reversed(published):
            path.unlink(missing_ok=True)
        raise
    finally:
        for path, _label in staged.items():
            path.unlink(missing_ok=True)
            _writer_tmp(path).unlink(missing_ok=True)

    return PhysicalFastbootCaptureResult(
        profile_id=evidence.profile_id,
        product=evidence.product,
        serialno=evidence.serialno,
        current_slot=evidence.current_slot,
        slot_count=evidence.slot_count,
        unlocked=evidence.unlocked,
        secure=evidence.secure,
        firmware_build=evidence.firmware_build,
        firmware_fingerprint=evidence.firmware_fingerprint,
        transcript_sha256=evidence.transcript_sha256,
        baseline_evidence_sha256=baseline_digest,
        fastboot_platform_tools_version=tool_evidence.observed_platform_tools_version,
        fastboot_executable_sha256=tool_evidence.executable_sha256,
        fastboot_tool_evidence_sha256=tool_digest,
        fastboot_capture_bundle_sha256=capture_digest,
        capture_policy=capture_bundle.capture_policy,
        confirmation_token_verified=True,
        physical_interaction_performed=True,
        read_only=True,
        phone_storage_written=False,
        persistent_write_authorized=False,
        hardware_verified=False,
        beta_gate_credit=False,
        outputs={
            "transcript": str(destinations.transcript),
            "baseline_evidence": str(destinations.baseline),
            "fastboot_tool_evidence": str(destinations.tool),
            "capture_bundle": str(destinations.capture),
        },
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="KaliPhoneStudio capture-fastboot-baseline",
        description=(
            "Capture one profile/serial-bound read-only Fastboot baseline evidence set. "
            "This queries a physical phone but never boots, flashes, erases, reboots, "
            "changes slots or writes phone storage."
        ),
    )
    parser.add_argument("--profile-id", required=True)
    parser.add_argument(
        "--devices-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "devices",
    )
    parser.add_argument("--serial", required=True, help="exact serial shown by fastboot devices")
    parser.add_argument("--firmware-build", required=True)
    parser.add_argument("--firmware-fingerprint", required=True)
    parser.add_argument(
        "--confirm-token",
        required=True,
        help="exact profile confirmation token; checked before any external command",
    )
    parser.add_argument("--fastboot", default="fastboot")
    parser.add_argument(
        "--fastboot-policy",
        type=Path,
        default=DEFAULT_FASTBOOT_POLICY,
        help="reviewed exact Platform-Tools policy",
    )
    parser.add_argument("--tool-timeout", type=int, default=15)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help=(
            "directory for the fixed four-file evidence set; mutually exclusive with "
            "the four explicit *-out options"
        ),
    )
    parser.add_argument("--transcript-out", type=Path)
    parser.add_argument("--evidence-out", type=Path)
    parser.add_argument("--tool-evidence-out", type=Path)
    parser.add_argument("--capture-evidence-out", type=Path)
    return parser


def _destinations_from_args(args: argparse.Namespace) -> FastbootCaptureDestinations:
    explicit = (
        args.transcript_out,
        args.evidence_out,
        args.tool_evidence_out,
        args.capture_evidence_out,
    )
    if args.output_dir is not None:
        if any(item is not None for item in explicit):
            raise PhysicalFastbootCaptureError(
                "--output-dir cannot be combined with explicit *-out paths"
            )
        return default_destinations(args.output_dir)
    if any(item is None for item in explicit):
        raise PhysicalFastbootCaptureError(
            "use --output-dir or provide all four explicit output paths"
        )
    return FastbootCaptureDestinations(
        transcript=args.transcript_out,
        baseline=args.evidence_out,
        tool=args.tool_evidence_out,
        capture=args.capture_evidence_out,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        profile = get_profile(args.devices_root, args.profile_id)
        result = capture_physical_fastboot_baseline(
            profile,
            confirmation_token=args.confirm_token,
            serial=args.serial,
            firmware_build=args.firmware_build,
            firmware_fingerprint=args.firmware_fingerprint,
            destinations=_destinations_from_args(args),
            fastboot=args.fastboot,
            fastboot_policy=args.fastboot_policy,
            tool_timeout_seconds=args.tool_timeout,
            capture_timeout_seconds=args.timeout,
        )
    except (ProfileError, PhysicalFastbootCaptureError) as exc:
        parser.exit(2, f"capture refused: {exc}\n")
    print(json.dumps(result.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
