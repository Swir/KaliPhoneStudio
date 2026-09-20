"""One-command, read-only first-test session bootstrap for a physical phone.

This module wraps the existing guarded Fastboot baseline capture in a fresh,
create-only session directory and records one exact session manifest. It remains
profile-driven and performs no boot, reboot, flash, erase, slot change, mount or
phone-storage write. A successful session is evidence preparation only and grants
no hardware or Beta credit.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Sequence

from .physical_fastboot_capture import (
    DEFAULT_FASTBOOT_POLICY,
    PhysicalFastbootCaptureError,
    PhysicalFastbootCaptureResult,
    capture_physical_fastboot_baseline,
    default_destinations,
)
from .profiles import DeviceProfile, ProfileError, get_profile
from .stable_file import StableFileError, hash_stable_regular_file


SESSION_MANIFEST_NAME = "physical-first-test-session.json"
FASTBOOT_SUBDIR = "fastboot"
_CAPTURE_EVIDENCE_MAX_BYTES = 8 * 1024 * 1024
_EXPECTED_CAPTURE_POLICY = "read-only-fastboot-baseline-v1"


class PhysicalFirstTestSessionError(RuntimeError):
    """Raised when a first-test session cannot start or be recorded safely."""


@dataclass(frozen=True)
class PhysicalFirstTestSession:
    schema_version: int
    profile_id: str
    device_serial: str
    firmware_build: str
    firmware_fingerprint: str
    fastboot_capture_bundle_sha256: str
    fastboot_baseline_sha256: str
    fastboot_tool_evidence_sha256: str
    fastboot_transcript_sha256: str
    fastboot_platform_tools_version: str
    fastboot_executable_sha256: str
    session_manifest_path: str
    fastboot_evidence_dir: str
    confirmation_token_verified: bool
    physical_interaction_performed: bool
    read_only_baseline_only: bool
    temporary_boot_performed: bool
    persistent_write_authorized: bool
    phone_storage_written: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _reject_symlink_ancestor(path: Path) -> None:
    current = Path(path).parent
    while True:
        if current.is_symlink():
            raise PhysicalFirstTestSessionError(
                f"refusing session below symlinked directory: {current}"
            )
        parent = current.parent
        if parent == current:
            break
        current = parent


def _validate_fresh_session_dir(session_dir: Path) -> Path:
    session = Path(session_dir)
    _reject_symlink_ancestor(session)
    if session.exists() or session.is_symlink():
        raise PhysicalFirstTestSessionError(
            f"refusing to reuse existing physical test session: {session}"
        )
    try:
        session.parent.mkdir(parents=True, exist_ok=True)
        _reject_symlink_ancestor(session)
        session.mkdir()
    except OSError as exc:
        raise PhysicalFirstTestSessionError(
            f"cannot create fresh physical test session: {session}: {exc}"
        ) from exc
    if session.is_symlink() or not session.is_dir():
        raise PhysicalFirstTestSessionError(
            f"physical test session is not a regular directory: {session}"
        )
    return session


def _write_session_manifest(session: PhysicalFirstTestSession, destination: Path) -> str:
    payload = session.canonical_json().encode("utf-8")
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise PhysicalFirstTestSessionError(
            f"refusing to overwrite physical session manifest: {destination}"
        )
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise PhysicalFirstTestSessionError(
            f"refusing stale physical session manifest temporary file: {temporary}"
        )
    try:
        temporary.write_bytes(payload)
        temporary.replace(destination)
    except OSError as exc:
        raise PhysicalFirstTestSessionError(
            f"cannot publish physical session manifest: {destination}: {exc}"
        ) from exc
    finally:
        temporary.unlink(missing_ok=True)
    return sha256(payload).hexdigest()


def _verify_exact_capture_files(
    fastboot_dir: Path,
    capture_result: PhysicalFastbootCaptureResult,
) -> None:
    destinations = default_destinations(fastboot_dir)
    expected = (
        (destinations.transcript, "Fastboot transcript", capture_result.transcript_sha256),
        (destinations.baseline, "Fastboot baseline evidence", capture_result.baseline_evidence_sha256),
        (destinations.tool, "Fastboot tool evidence", capture_result.fastboot_tool_evidence_sha256),
        (destinations.capture, "Fastboot capture bundle", capture_result.fastboot_capture_bundle_sha256),
    )
    for path, label, expected_digest in expected:
        try:
            identity = hash_stable_regular_file(
                path,
                max_bytes=_CAPTURE_EVIDENCE_MAX_BYTES,
                label=label,
            )
        except StableFileError as exc:
            raise PhysicalFirstTestSessionError(str(exc)) from exc
        if identity.sha256 != expected_digest:
            raise PhysicalFirstTestSessionError(
                f"{label} digest drifted before first-test session binding"
            )


def begin_physical_first_test_session(
    profile: DeviceProfile,
    *,
    confirmation_token: str,
    serial: str,
    firmware_build: str,
    firmware_fingerprint: str,
    session_dir: Path,
    fastboot: str | Path = "fastboot",
    fastboot_policy: Path = DEFAULT_FASTBOOT_POLICY,
    tool_timeout_seconds: int = 15,
    capture_timeout_seconds: int = 30,
) -> tuple[PhysicalFirstTestSession, str, PhysicalFastbootCaptureResult]:
    """Create one fresh session and capture its exact read-only Fastboot baseline."""
    if not isinstance(profile, DeviceProfile):
        raise PhysicalFirstTestSessionError("a validated DeviceProfile is required")
    # Preserve the strongest existing safety property: reject the profile token
    # before creating a session directory or reaching any external Fastboot path.
    if confirmation_token != profile.confirmation_text:
        raise PhysicalFirstTestSessionError(
            "confirmation token does not match the selected device profile"
        )
    if not isinstance(serial, str) or not serial.strip():
        raise PhysicalFirstTestSessionError("exact fastboot serial is required")
    if not isinstance(firmware_build, str) or not firmware_build.strip():
        raise PhysicalFirstTestSessionError("exact firmware build is required")
    if not isinstance(firmware_fingerprint, str) or not firmware_fingerprint.strip():
        raise PhysicalFirstTestSessionError("exact firmware fingerprint is required")

    session_root = _validate_fresh_session_dir(session_dir)
    fastboot_dir = session_root / FASTBOOT_SUBDIR
    manifest_path = session_root / SESSION_MANIFEST_NAME

    try:
        capture_result = capture_physical_fastboot_baseline(
            profile,
            confirmation_token=confirmation_token,
            serial=serial.strip(),
            firmware_build=firmware_build.strip(),
            firmware_fingerprint=firmware_fingerprint.strip(),
            destinations=default_destinations(fastboot_dir),
            fastboot=fastboot,
            fastboot_policy=Path(fastboot_policy),
            tool_timeout_seconds=tool_timeout_seconds,
            capture_timeout_seconds=capture_timeout_seconds,
        )
    except PhysicalFastbootCaptureError as exc:
        # The underlying capture owns cleanup of staged/final evidence. Remove only
        # empty directories created by this wrapper; never recursively delete a
        # non-empty evidence directory after physical interaction.
        try:
            if fastboot_dir.is_dir() and not any(fastboot_dir.iterdir()):
                fastboot_dir.rmdir()
            if session_root.is_dir() and not any(session_root.iterdir()):
                session_root.rmdir()
        except OSError:
            pass
        raise PhysicalFirstTestSessionError(str(exc)) from exc

    if capture_result.profile_id != profile.profile_id:
        raise PhysicalFirstTestSessionError("captured profile identity drifted")
    if capture_result.serialno != serial.strip():
        raise PhysicalFirstTestSessionError("captured serial identity drifted")
    if capture_result.firmware_build != firmware_build.strip():
        raise PhysicalFirstTestSessionError("captured firmware build drifted")
    if capture_result.firmware_fingerprint != firmware_fingerprint.strip():
        raise PhysicalFirstTestSessionError("captured firmware fingerprint drifted")
    if (
        capture_result.capture_policy != _EXPECTED_CAPTURE_POLICY
        or capture_result.confirmation_token_verified is not True
        or capture_result.physical_interaction_performed is not True
        or capture_result.read_only is not True
        or capture_result.phone_storage_written is not False
        or capture_result.persistent_write_authorized is not False
        or capture_result.hardware_verified is not False
        or capture_result.beta_gate_credit is not False
    ):
        raise PhysicalFirstTestSessionError("physical baseline capture violated read-only policy")

    # Bind the session only after the exact four files emitted by the guarded capture
    # have been descriptor-stably re-hashed and still match the capture result.
    _verify_exact_capture_files(fastboot_dir, capture_result)

    session = PhysicalFirstTestSession(
        schema_version=1,
        profile_id=profile.profile_id,
        device_serial=capture_result.serialno,
        firmware_build=capture_result.firmware_build,
        firmware_fingerprint=capture_result.firmware_fingerprint,
        fastboot_capture_bundle_sha256=capture_result.fastboot_capture_bundle_sha256,
        fastboot_baseline_sha256=capture_result.baseline_evidence_sha256,
        fastboot_tool_evidence_sha256=capture_result.fastboot_tool_evidence_sha256,
        fastboot_transcript_sha256=capture_result.transcript_sha256,
        fastboot_platform_tools_version=capture_result.fastboot_platform_tools_version,
        fastboot_executable_sha256=capture_result.fastboot_executable_sha256,
        session_manifest_path=SESSION_MANIFEST_NAME,
        fastboot_evidence_dir=FASTBOOT_SUBDIR,
        confirmation_token_verified=True,
        physical_interaction_performed=True,
        read_only_baseline_only=True,
        temporary_boot_performed=False,
        persistent_write_authorized=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    manifest_digest = _write_session_manifest(session, manifest_path)
    return session, manifest_digest, capture_result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="KaliPhoneStudio begin-physical-test-session",
        description=(
            "Create one fresh profile-bound physical test session and capture only its "
            "read-only Fastboot baseline. No boot, flash, erase, slot change or phone-storage write occurs."
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
    parser.add_argument("--session-dir", type=Path, required=True)
    parser.add_argument("--fastboot", default="fastboot")
    parser.add_argument("--fastboot-policy", type=Path, default=DEFAULT_FASTBOOT_POLICY)
    parser.add_argument("--tool-timeout", type=int, default=15)
    parser.add_argument("--timeout", type=int, default=30)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        profile = get_profile(args.devices_root, args.profile_id)
        session, manifest_digest, capture_result = begin_physical_first_test_session(
            profile,
            confirmation_token=args.confirm_token,
            serial=args.serial,
            firmware_build=args.firmware_build,
            firmware_fingerprint=args.firmware_fingerprint,
            session_dir=args.session_dir,
            fastboot=args.fastboot,
            fastboot_policy=args.fastboot_policy,
            tool_timeout_seconds=args.tool_timeout,
            capture_timeout_seconds=args.timeout,
        )
    except (ProfileError, PhysicalFirstTestSessionError) as exc:
        parser.exit(2, f"session refused: {exc}\n")

    result = {
        "session": asdict(session),
        "session_manifest_sha256": manifest_digest,
        "capture_outputs": capture_result.outputs,
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
