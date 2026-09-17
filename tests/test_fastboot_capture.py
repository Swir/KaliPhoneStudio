from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from kaliphonestudio.fastboot_capture import (
    FastbootCaptureError,
    capture_fastboot_getvar_all,
    list_fastboot_devices,
    parse_fastboot_devices,
    validate_capture_with_offline_parser,
    write_capture_once,
)


TRANSCRIPT = b"""(bootloader) product: lito\n(bootloader) serialno: ABC123\n(bootloader) current-slot: a\n(bootloader) slot-count: 2\n(bootloader) unlocked: yes\n(bootloader) secure: yes\n(bootloader) version-bootloader: test-bl\n(bootloader) version-baseband: test-bb\nFinished. Total time: 0.001s\n"""


def _runner(calls: list[tuple[list[str], dict]], *, devices: bytes = b"ABC123\tfastboot\n", transcript: bytes = TRANSCRIPT, getvar_rc: int = 0):
    def run(argv, **kwargs):
        calls.append((list(argv), dict(kwargs)))
        if argv[-1] == "devices":
            return SimpleNamespace(returncode=0, stdout=devices)
        assert argv[-2:] == ["getvar", "all"]
        return SimpleNamespace(returncode=getvar_rc, stdout=transcript)
    return run


def test_device_list_parser_is_deterministic_and_strict():
    devices = parse_fastboot_devices(b"B\tfastboot\nA fastboot\n")
    assert [item.serial for item in devices] == ["A", "B"]
    assert all(item.state == "fastboot" for item in devices)
    with pytest.raises(FastbootCaptureError, match="not reported in fastboot state"):
        parse_fastboot_devices(b"A\tdevice\n")
    with pytest.raises(FastbootCaptureError, match="duplicate"):
        parse_fastboot_devices(b"A fastboot\nA fastboot\n")
    with pytest.raises(FastbootCaptureError, match="unexpected"):
        parse_fastboot_devices(b"too many columns here\n")


def test_list_devices_uses_only_read_only_argv():
    calls = []
    devices = list_fastboot_devices(fastboot="fastboot-custom", runner=_runner(calls))
    assert [item.serial for item in devices] == ["ABC123"]
    assert calls[0][0] == ["fastboot-custom", "devices"]
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["stdin"] is not None
    assert calls[0][1]["stderr"] is not None


def test_capture_is_serial_bound_and_only_runs_devices_plus_getvar_all():
    calls = []
    payload = capture_fastboot_getvar_all("ABC123", runner=_runner(calls))
    assert payload == TRANSCRIPT
    assert [item[0] for item in calls] == [
        ["fastboot", "devices"],
        ["fastboot", "-s", "ABC123", "getvar", "all"],
    ]
    flattened = " ".join(token for argv, _kwargs in calls for token in argv)
    for forbidden in (" flash ", " erase ", " reboot ", " boot ", " set_active ", " flashing "):
        assert forbidden not in f" {flattened} "


def test_capture_refuses_unknown_serial_before_getvar():
    calls = []
    with pytest.raises(FastbootCaptureError, match="requested fastboot serial is not present"):
        capture_fastboot_getvar_all("OTHER", runner=_runner(calls))
    assert [item[0] for item in calls] == [["fastboot", "devices"]]


def test_capture_refuses_serial_option_injection():
    calls = []
    with pytest.raises(FastbootCaptureError, match="must not start"):
        capture_fastboot_getvar_all("--serial=evil", runner=_runner(calls))
    assert calls == []


def test_capture_refuses_failed_getvar_and_invalid_parser_evidence():
    calls = []
    with pytest.raises(FastbootCaptureError, match="status 1"):
        capture_fastboot_getvar_all("ABC123", runner=_runner(calls, getvar_rc=1))
    with pytest.raises(FastbootCaptureError, match="failed command"):
        validate_capture_with_offline_parser(b"FAILED (remote: not allowed)\n")


def test_write_capture_once_preserves_exact_bytes_and_refuses_overwrite(tmp_path: Path):
    destination = tmp_path / "fastboot-getvar-all.txt"
    write_capture_once(TRANSCRIPT, destination)
    assert destination.read_bytes() == TRANSCRIPT
    with pytest.raises(FastbootCaptureError, match="refusing to overwrite"):
        write_capture_once(TRANSCRIPT, destination)


def test_timeout_and_runner_output_contract_fail_closed():
    calls = []
    with pytest.raises(FastbootCaptureError, match="between 1 and 300"):
        list_fastboot_devices(timeout_seconds=0, runner=_runner(calls))

    def text_runner(argv, **kwargs):
        return SimpleNamespace(returncode=0, stdout="not bytes")

    with pytest.raises(FastbootCaptureError, match="byte output"):
        list_fastboot_devices(runner=text_runner)
