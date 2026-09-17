"""Read-only Fastboot capture primitives for physical baseline collection.

This module deliberately exposes only ``fastboot devices`` and ``fastboot -s SERIAL
getvar all``. It never invokes boot, reboot, flash, erase, set_active, flashing or
any other state-changing verb. Captured bytes remain ordinary host-side evidence
and do not grant hardware or Beta credit by themselves.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Any, Callable

from .fastboot_baseline import MAX_TRANSCRIPT_BYTES, FastbootBaselineError


DEFAULT_TIMEOUT_SECONDS = 30
MAX_DEVICE_LIST_BYTES = 256 * 1024
MAX_SERIAL_LENGTH = 128


class FastbootCaptureError(RuntimeError):
    pass


@dataclass(frozen=True)
class FastbootConnectedDevice:
    serial: str
    state: str


def _safe_serial(value: str) -> str:
    if not isinstance(value, str):
        raise FastbootCaptureError("fastboot serial must be text")
    serial = value.strip()
    if not serial or len(serial) > MAX_SERIAL_LENGTH:
        raise FastbootCaptureError("fastboot serial is empty or exceeds the safety limit")
    if serial.startswith("-"):
        raise FastbootCaptureError("fastboot serial must not start with an option prefix")
    if any(ch.isspace() or ord(ch) < 0x21 or ord(ch) > 0x7E for ch in serial):
        raise FastbootCaptureError("fastboot serial contains unsafe characters")
    return serial


def _safe_executable(value: str | Path) -> str:
    raw = str(value)
    if not raw or "\x00" in raw or "\n" in raw or "\r" in raw:
        raise FastbootCaptureError("fastboot executable path is invalid")
    return raw


def _timeout(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1 or value > 300:
        raise FastbootCaptureError("fastboot timeout must be an integer between 1 and 300 seconds")
    return value


def _run_read_only(
    runner: Callable[..., Any],
    argv: list[str],
    *,
    timeout_seconds: int,
    maximum_bytes: int,
) -> bytes:
    """Run one fixed read-only argv and return its combined stdout/stderr bytes."""
    try:
        result = runner(
            argv,
            shell=False,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise FastbootCaptureError(f"fastboot read-only command failed to execute: {argv[-1]}") from exc
    returncode = getattr(result, "returncode", None)
    payload = getattr(result, "stdout", None)
    if not isinstance(returncode, int) or isinstance(returncode, bool):
        raise FastbootCaptureError("fastboot runner returned an invalid status")
    if not isinstance(payload, (bytes, bytearray)):
        raise FastbootCaptureError("fastboot runner did not return byte output")
    output = bytes(payload)
    if len(output) > maximum_bytes:
        raise FastbootCaptureError("fastboot output exceeds the safety size limit")
    if returncode != 0:
        raise FastbootCaptureError(f"fastboot read-only command exited with status {returncode}")
    return output


def parse_fastboot_devices(payload: bytes) -> tuple[FastbootConnectedDevice, ...]:
    if len(payload) > MAX_DEVICE_LIST_BYTES:
        raise FastbootCaptureError("fastboot device list exceeds the safety size limit")
    if b"\x00" in payload:
        raise FastbootCaptureError("fastboot device list contains NUL bytes")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FastbootCaptureError("fastboot device list must be UTF-8") from exc

    found: dict[str, FastbootConnectedDevice] = {}
    for original in text.splitlines():
        line = original.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            raise FastbootCaptureError("unexpected fastboot devices output")
        serial = _safe_serial(parts[0])
        state = parts[1].strip().lower()
        if state != "fastboot":
            raise FastbootCaptureError(f"device {serial} is not reported in fastboot state")
        if serial in found:
            raise FastbootCaptureError(f"duplicate fastboot device serial: {serial}")
        found[serial] = FastbootConnectedDevice(serial=serial, state=state)
    return tuple(found[key] for key in sorted(found))


def list_fastboot_devices(
    *,
    fastboot: str | Path = "fastboot",
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    runner: Callable[..., Any] = subprocess.run,
) -> tuple[FastbootConnectedDevice, ...]:
    executable = _safe_executable(fastboot)
    timeout = _timeout(timeout_seconds)
    payload = _run_read_only(
        runner,
        [executable, "devices"],
        timeout_seconds=timeout,
        maximum_bytes=MAX_DEVICE_LIST_BYTES,
    )
    return parse_fastboot_devices(payload)


def capture_fastboot_getvar_all(
    serial: str,
    *,
    fastboot: str | Path = "fastboot",
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    runner: Callable[..., Any] = subprocess.run,
) -> bytes:
    """Capture exact combined output from one serial-bound ``getvar all`` call."""
    executable = _safe_executable(fastboot)
    selected = _safe_serial(serial)
    timeout = _timeout(timeout_seconds)
    connected = list_fastboot_devices(
        fastboot=executable,
        timeout_seconds=timeout,
        runner=runner,
    )
    serials = {device.serial for device in connected}
    if selected not in serials:
        if not serials:
            raise FastbootCaptureError("no fastboot device is connected")
        raise FastbootCaptureError("requested fastboot serial is not present in the read-only device list")

    payload = _run_read_only(
        runner,
        [executable, "-s", selected, "getvar", "all"],
        timeout_seconds=timeout,
        maximum_bytes=MAX_TRANSCRIPT_BYTES,
    )
    if not payload:
        raise FastbootCaptureError("fastboot getvar all returned an empty transcript")
    return payload


def write_capture_once(payload: bytes, destination: Path) -> None:
    """Persist raw transcript bytes once without interpreting or rewriting them."""
    if not isinstance(payload, bytes) or not payload:
        raise FastbootCaptureError("captured transcript must be non-empty bytes")
    if len(payload) > MAX_TRANSCRIPT_BYTES:
        raise FastbootCaptureError("captured transcript exceeds the safety size limit")
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise FastbootCaptureError(f"refusing to overwrite fastboot transcript: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise FastbootCaptureError("refusing stale fastboot transcript temporary path")
    try:
        temporary.write_bytes(payload)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_capture_with_offline_parser(payload: bytes) -> None:
    """Reject explicit Fastboot failures before the transcript is accepted by a CLI."""
    from .fastboot_baseline import parse_fastboot_getvar_all

    try:
        parse_fastboot_getvar_all(payload)
    except FastbootBaselineError as exc:
        raise FastbootCaptureError(str(exc)) from exc
