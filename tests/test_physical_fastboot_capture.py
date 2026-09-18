from __future__ import annotations

import json
from pathlib import Path

import pytest

from kaliphonestudio import physical_fastboot_capture as capture
from kaliphonestudio.fastboot_tool import FastbootToolEvidence
from kaliphonestudio.profiles import get_profile


ROOT = Path(__file__).resolve().parents[1]
DEVICES = ROOT / "devices"

TRANSCRIPT = (
    "(bootloader) product: avicii\n"
    "(bootloader) serialno: SERIAL123\n"
    "(bootloader) current-slot: a\n"
    "(bootloader) slot-count: 2\n"
    "(bootloader) unlocked: no\n"
    "(bootloader) secure: yes\n"
    "(bootloader) version-bootloader: avicii-test-1\n"
    "(bootloader) version-baseband: modem-test-1\n"
    "(bootloader) partition-size:boot: 0x6000000\n"
    "Finished. Total time: 0.003s\n"
).encode("utf-8")


def _profile():
    return get_profile(DEVICES, "oneplus/avicii")


def _tool_evidence(*, executable_sha256: str = "2" * 64) -> FastbootToolEvidence:
    return FastbootToolEvidence(
        schema_version=1,
        tool="fastboot",
        policy_sha256="1" * 64,
        required_platform_tools_version="37.0.1",
        observed_platform_tools_version="37.0.1",
        executable_filename="fastboot.exe",
        executable_sha256=executable_sha256,
        executable_size=123456,
        version_line="fastboot version 37.0.1",
        version_output_sha256="3" * 64,
    )


def _install_safe_mocks(monkeypatch, tmp_path: Path, calls: list[tuple]):
    resolved = tmp_path / "fastboot.exe"

    def inspect(fastboot, *, policy_path, timeout_seconds):
        calls.append(("inspect", str(fastboot), str(policy_path), timeout_seconds))
        return _tool_evidence(), resolved

    def read_only(serial, *, fastboot, timeout_seconds):
        calls.append(("capture", serial, str(fastboot), timeout_seconds))
        return TRANSCRIPT

    monkeypatch.setattr(capture, "inspect_fastboot_tool", inspect)
    monkeypatch.setattr(capture, "capture_fastboot_getvar_all", read_only)


def test_confirmation_token_is_checked_before_any_external_command(monkeypatch, tmp_path: Path):
    def unexpected(*args, **kwargs):
        raise AssertionError("external command path must not be reached")

    monkeypatch.setattr(capture, "inspect_fastboot_tool", unexpected)
    with pytest.raises(capture.PhysicalFastbootCaptureError, match="confirmation token"):
        capture.capture_physical_fastboot_baseline(
            _profile(),
            confirmation_token="WRONG",
            serial="SERIAL123",
            firmware_build="AC2003_11_F.22",
            firmware_fingerprint="OnePlus/avicii/avicii:13/test/F.22:user/release-keys",
            destinations=capture.default_destinations(tmp_path / "capture"),
        )
    assert not (tmp_path / "capture").exists()


def test_existing_output_refuses_before_external_command(monkeypatch, tmp_path: Path):
    output = tmp_path / "capture"
    output.mkdir()
    (output / capture.DEFAULT_BASELINE_NAME).write_text("existing", encoding="utf-8")

    def unexpected(*args, **kwargs):
        raise AssertionError("external command path must not be reached")

    monkeypatch.setattr(capture, "inspect_fastboot_tool", unexpected)
    with pytest.raises(capture.PhysicalFastbootCaptureError, match="refusing to overwrite"):
        capture.capture_physical_fastboot_baseline(
            _profile(),
            confirmation_token="AC2003",
            serial="SERIAL123",
            firmware_build="AC2003_11_F.22",
            firmware_fingerprint="OnePlus/avicii/avicii:13/test/F.22:user/release-keys",
            destinations=capture.default_destinations(output),
        )


def test_guarded_capture_publishes_exact_read_only_evidence_set(monkeypatch, tmp_path: Path):
    calls: list[tuple] = []
    _install_safe_mocks(monkeypatch, tmp_path, calls)
    output = tmp_path / "capture"

    result = capture.capture_physical_fastboot_baseline(
        _profile(),
        confirmation_token="AC2003",
        serial="SERIAL123",
        firmware_build="AC2003_11_F.22",
        firmware_fingerprint="OnePlus/avicii/avicii:13/test/F.22:user/release-keys",
        destinations=capture.default_destinations(output),
        fastboot="reviewed-fastboot",
        fastboot_policy=tmp_path / "policy.json",
        tool_timeout_seconds=11,
        capture_timeout_seconds=29,
    )

    assert [item[0] for item in calls] == ["inspect", "capture", "inspect"]
    assert calls[1][1:] == ("SERIAL123", str(tmp_path / "fastboot.exe"), 29)
    assert calls[2][1] == str(tmp_path / "fastboot.exe")
    assert result.profile_id == "oneplus/avicii"
    assert result.serialno == "SERIAL123"
    assert result.confirmation_token_verified is True
    assert result.physical_interaction_performed is True
    assert result.read_only is True
    assert result.phone_storage_written is False
    assert result.persistent_write_authorized is False
    assert result.hardware_verified is False
    assert result.beta_gate_credit is False
    assert set(output.iterdir()) == {
        output / capture.DEFAULT_TRANSCRIPT_NAME,
        output / capture.DEFAULT_BASELINE_NAME,
        output / capture.DEFAULT_TOOL_EVIDENCE_NAME,
        output / capture.DEFAULT_CAPTURE_BUNDLE_NAME,
    }
    assert (output / capture.DEFAULT_TRANSCRIPT_NAME).read_bytes() == TRANSCRIPT
    baseline = json.loads((output / capture.DEFAULT_BASELINE_NAME).read_text(encoding="utf-8"))
    bundle = json.loads((output / capture.DEFAULT_CAPTURE_BUNDLE_NAME).read_text(encoding="utf-8"))
    assert baseline["serialno"] == "SERIAL123"
    assert baseline["beta_gate_credit"] is False
    assert bundle["read_only"] is True
    assert bundle["phone_storage_written"] is False
    assert bundle["hardware_verified"] is False
    assert bundle["beta_gate_credit"] is False
    assert not list(output.glob("*.capturing"))
    assert not list(output.glob("*.tmp"))


def test_fastboot_tool_drift_after_capture_fails_before_publishing(monkeypatch, tmp_path: Path):
    resolved = tmp_path / "fastboot.exe"
    calls = 0

    def inspect(fastboot, *, policy_path, timeout_seconds):
        nonlocal calls
        calls += 1
        digest = "2" * 64 if calls == 1 else "4" * 64
        return _tool_evidence(executable_sha256=digest), resolved

    monkeypatch.setattr(capture, "inspect_fastboot_tool", inspect)
    monkeypatch.setattr(
        capture,
        "capture_fastboot_getvar_all",
        lambda serial, *, fastboot, timeout_seconds: TRANSCRIPT,
    )
    output = tmp_path / "capture"

    with pytest.raises(capture.PhysicalFastbootCaptureError, match="identity changed"):
        capture.capture_physical_fastboot_baseline(
            _profile(),
            confirmation_token="AC2003",
            serial="SERIAL123",
            firmware_build="AC2003_11_F.22",
            firmware_fingerprint="OnePlus/avicii/avicii:13/test/F.22:user/release-keys",
            destinations=capture.default_destinations(output),
        )

    assert output.is_dir()
    assert list(output.iterdir()) == []


def test_serial_drift_rolls_back_every_final_file(monkeypatch, tmp_path: Path):
    calls: list[tuple] = []
    _install_safe_mocks(monkeypatch, tmp_path, calls)
    output = tmp_path / "capture"

    with pytest.raises(capture.PhysicalFastbootCaptureError, match="serialno does not match"):
        capture.capture_physical_fastboot_baseline(
            _profile(),
            confirmation_token="AC2003",
            serial="DIFFERENT",
            firmware_build="AC2003_11_F.22",
            firmware_fingerprint="OnePlus/avicii/avicii:13/test/F.22:user/release-keys",
            destinations=capture.default_destinations(output),
        )

    assert output.is_dir()
    assert list(output.iterdir()) == []


def test_output_dir_and_explicit_paths_are_mutually_exclusive():
    parser = capture.build_parser()
    args = parser.parse_args(
        [
            "--profile-id", "oneplus/avicii",
            "--serial", "SERIAL123",
            "--firmware-build", "AC2003_11_F.22",
            "--firmware-fingerprint", "fp",
            "--confirm-token", "AC2003",
            "--output-dir", "out",
            "--transcript-out", "raw.txt",
        ]
    )
    with pytest.raises(capture.PhysicalFastbootCaptureError, match="cannot be combined"):
        capture._destinations_from_args(args)


def test_explicit_legacy_output_mode_requires_all_four_paths():
    parser = capture.build_parser()
    args = parser.parse_args(
        [
            "--profile-id", "oneplus/avicii",
            "--serial", "SERIAL123",
            "--firmware-build", "AC2003_11_F.22",
            "--firmware-fingerprint", "fp",
            "--confirm-token", "AC2003",
            "--transcript-out", "raw.txt",
        ]
    )
    with pytest.raises(capture.PhysicalFastbootCaptureError, match="all four"):
        capture._destinations_from_args(args)


def test_parser_help_describes_physical_read_only_boundary(capsys):
    with pytest.raises(SystemExit) as exc:
        capture.main(["--help"])
    assert exc.value.code == 0
    text = capsys.readouterr().out.lower()
    assert "read-only" in text
    assert "writes phone storage" in text
    assert "--confirm-token" in text


def test_host_entrypoint_routes_only_explicit_capture_subcommand(monkeypatch):
    import main as entrypoint

    seen = []
    monkeypatch.setattr(entrypoint, "physical_capture_main", lambda argv: seen.append(("physical", list(argv))) or 17)
    monkeypatch.setattr(entrypoint, "app_main", lambda argv: seen.append(("app", list(argv))) or 23)

    assert entrypoint.main(["capture-fastboot-baseline", "--help"]) == 17
    assert entrypoint.main(["--doctor"]) == 23
    assert seen == [
        ("physical", ["--help"]),
        ("app", ["--doctor"]),
    ]
