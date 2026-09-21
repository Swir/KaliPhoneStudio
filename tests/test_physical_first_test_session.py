from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from kaliphonestudio import physical_first_test_session as session
from kaliphonestudio.physical_fastboot_capture import (
    PhysicalFastbootCaptureError,
    PhysicalFastbootCaptureResult,
)
from kaliphonestudio.profiles import get_profile


ROOT = Path(__file__).resolve().parents[1]
DEVICES = ROOT / "devices"
FIRMWARE_BUILD = "AC2003_11_F.22"
FIRMWARE_FINGERPRINT = "OnePlus/avicii/avicii:13/test/F.22:user/release-keys"
SERIAL = "SERIAL123"
CAPTURE_POLICY = "fastboot-version+devices+serial-getvar-all-v1"


def _profile():
    return get_profile(DEVICES, "oneplus/avicii")


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _result(
    destinations,
    *,
    persistent_write_authorized: bool = False,
    capture_policy: str = CAPTURE_POLICY,
):
    return PhysicalFastbootCaptureResult(
        profile_id="oneplus/avicii",
        product="avicii",
        serialno=SERIAL,
        current_slot="a",
        slot_count=2,
        unlocked=False,
        secure=True,
        firmware_build=FIRMWARE_BUILD,
        firmware_fingerprint=FIRMWARE_FINGERPRINT,
        transcript_sha256=_digest(destinations.transcript),
        baseline_evidence_sha256=_digest(destinations.baseline),
        fastboot_platform_tools_version="37.0.1",
        fastboot_executable_sha256="3" * 64,
        fastboot_tool_evidence_sha256=_digest(destinations.tool),
        fastboot_capture_bundle_sha256=_digest(destinations.capture),
        capture_policy=capture_policy,
        confirmation_token_verified=True,
        physical_interaction_performed=True,
        read_only=True,
        phone_storage_written=False,
        persistent_write_authorized=persistent_write_authorized,
        hardware_verified=False,
        beta_gate_credit=False,
        outputs={
            "transcript": str(destinations.transcript),
            "baseline_evidence": str(destinations.baseline),
            "fastboot_tool_evidence": str(destinations.tool),
            "capture_bundle": str(destinations.capture),
        },
    )


def _write_fake_capture(destinations) -> None:
    for path, label in destinations.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(label + "\n", encoding="utf-8")


def _install_success(monkeypatch, seen: list[dict[str, object]]):
    def fake_capture(
        profile,
        *,
        confirmation_token,
        serial,
        firmware_build,
        firmware_fingerprint,
        destinations,
        fastboot,
        fastboot_policy,
        tool_timeout_seconds,
        capture_timeout_seconds,
    ):
        seen.append(
            {
                "profile_id": profile.profile_id,
                "confirmation_token": confirmation_token,
                "serial": serial,
                "firmware_build": firmware_build,
                "firmware_fingerprint": firmware_fingerprint,
                "fastboot": str(fastboot),
                "fastboot_policy": str(fastboot_policy),
                "tool_timeout_seconds": tool_timeout_seconds,
                "capture_timeout_seconds": capture_timeout_seconds,
                "destinations": destinations,
            }
        )
        _write_fake_capture(destinations)
        return _result(destinations)

    monkeypatch.setattr(session, "capture_physical_fastboot_baseline", fake_capture)


def test_wrong_confirmation_token_refuses_before_workspace_or_capture(monkeypatch, tmp_path: Path):
    called = False

    def unexpected(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("capture must not be reached")

    monkeypatch.setattr(session, "capture_physical_fastboot_baseline", unexpected)
    target = tmp_path / "session-01"

    with pytest.raises(session.PhysicalFirstTestSessionError, match="confirmation token"):
        session.begin_physical_first_test_session(
            _profile(),
            confirmation_token="WRONG",
            serial=SERIAL,
            firmware_build=FIRMWARE_BUILD,
            firmware_fingerprint=FIRMWARE_FINGERPRINT,
            session_dir=target,
        )

    assert called is False
    assert not target.exists()


def test_existing_session_refuses_before_capture(monkeypatch, tmp_path: Path):
    target = tmp_path / "session-01"
    target.mkdir()
    (target / "old.txt").write_text("old", encoding="utf-8")

    monkeypatch.setattr(
        session,
        "capture_physical_fastboot_baseline",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("capture must not be reached")),
    )

    with pytest.raises(session.PhysicalFirstTestSessionError, match="refusing to reuse"):
        session.begin_physical_first_test_session(
            _profile(),
            confirmation_token="AC2003",
            serial=SERIAL,
            firmware_build=FIRMWARE_BUILD,
            firmware_fingerprint=FIRMWARE_FINGERPRINT,
            session_dir=target,
        )

    assert (target / "old.txt").read_text(encoding="utf-8") == "old"


def test_success_creates_exact_read_only_session_manifest(monkeypatch, tmp_path: Path):
    seen: list[dict[str, object]] = []
    _install_success(monkeypatch, seen)
    target = tmp_path / "session-01"

    evidence, digest, capture = session.begin_physical_first_test_session(
        _profile(),
        confirmation_token="AC2003",
        serial=f"  {SERIAL}  ",
        firmware_build=f"  {FIRMWARE_BUILD}  ",
        firmware_fingerprint=f"  {FIRMWARE_FINGERPRINT}  ",
        session_dir=target,
        fastboot="reviewed-fastboot.exe",
        fastboot_policy=tmp_path / "fastboot-policy.json",
        tool_timeout_seconds=12,
        capture_timeout_seconds=34,
    )

    assert len(seen) == 1
    call = seen[0]
    assert call["profile_id"] == "oneplus/avicii"
    assert call["serial"] == SERIAL
    assert call["firmware_build"] == FIRMWARE_BUILD
    assert call["firmware_fingerprint"] == FIRMWARE_FINGERPRINT
    assert call["tool_timeout_seconds"] == 12
    assert call["capture_timeout_seconds"] == 34
    assert capture.serialno == SERIAL
    assert capture.capture_policy == CAPTURE_POLICY

    manifest_path = target / session.SESSION_MANIFEST_NAME
    assert manifest_path.is_file()
    assert digest == evidence.sha256()
    assert evidence.session_manifest_path == session.SESSION_MANIFEST_NAME
    assert evidence.fastboot_evidence_dir == session.FASTBOOT_SUBDIR
    assert evidence.read_only_baseline_only is True
    assert evidence.temporary_boot_performed is False
    assert evidence.persistent_write_authorized is False
    assert evidence.phone_storage_written is False
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["profile_id"] == "oneplus/avicii"
    assert payload["device_serial"] == SERIAL
    assert payload["fastboot_capture_bundle_sha256"] == capture.fastboot_capture_bundle_sha256
    assert payload["fastboot_transcript_sha256"] == _digest(
        target / session.FASTBOOT_SUBDIR / "fastboot-getvar-all.txt"
    )
    assert payload["temporary_boot_performed"] is False
    assert payload["beta_gate_credit"] is False
    assert set((target / session.FASTBOOT_SUBDIR).iterdir()) == {
        target / session.FASTBOOT_SUBDIR / "fastboot-getvar-all.txt",
        target / session.FASTBOOT_SUBDIR / "fastboot-baseline.json",
        target / session.FASTBOOT_SUBDIR / "fastboot-tool.json",
        target / session.FASTBOOT_SUBDIR / "fastboot-capture-bundle.json",
    }


def test_capture_failure_cleans_only_empty_wrapper_directories(monkeypatch, tmp_path: Path):
    def refused(*args, **kwargs):
        destinations = kwargs["destinations"]
        destinations.transcript.parent.mkdir(parents=True, exist_ok=True)
        raise PhysicalFastbootCaptureError("device identity mismatch")

    monkeypatch.setattr(session, "capture_physical_fastboot_baseline", refused)
    target = tmp_path / "session-01"

    with pytest.raises(session.PhysicalFirstTestSessionError, match="device identity mismatch"):
        session.begin_physical_first_test_session(
            _profile(),
            confirmation_token="AC2003",
            serial=SERIAL,
            firmware_build=FIRMWARE_BUILD,
            firmware_fingerprint=FIRMWARE_FINGERPRINT,
            session_dir=target,
        )

    assert not target.exists()


def test_non_read_only_capture_result_never_gets_session_manifest(monkeypatch, tmp_path: Path):
    def unsafe_capture(*args, **kwargs):
        destinations = kwargs["destinations"]
        _write_fake_capture(destinations)
        return _result(destinations, persistent_write_authorized=True)

    monkeypatch.setattr(session, "capture_physical_fastboot_baseline", unsafe_capture)
    target = tmp_path / "session-01"

    with pytest.raises(session.PhysicalFirstTestSessionError, match="read-only policy"):
        session.begin_physical_first_test_session(
            _profile(),
            confirmation_token="AC2003",
            serial=SERIAL,
            firmware_build=FIRMWARE_BUILD,
            firmware_fingerprint=FIRMWARE_FINGERPRINT,
            session_dir=target,
        )

    assert not (target / session.SESSION_MANIFEST_NAME).exists()
    assert (target / session.FASTBOOT_SUBDIR / "fastboot-capture-bundle.json").is_file()


def test_unreviewed_capture_policy_never_gets_session_manifest(monkeypatch, tmp_path: Path):
    def wrong_policy_capture(*args, **kwargs):
        destinations = kwargs["destinations"]
        _write_fake_capture(destinations)
        return _result(destinations, capture_policy="different-fastboot-policy")

    monkeypatch.setattr(session, "capture_physical_fastboot_baseline", wrong_policy_capture)
    target = tmp_path / "session-01"

    with pytest.raises(session.PhysicalFirstTestSessionError, match="read-only policy"):
        session.begin_physical_first_test_session(
            _profile(),
            confirmation_token="AC2003",
            serial=SERIAL,
            firmware_build=FIRMWARE_BUILD,
            firmware_fingerprint=FIRMWARE_FINGERPRINT,
            session_dir=target,
        )

    assert not (target / session.SESSION_MANIFEST_NAME).exists()


def test_tampered_capture_file_fails_before_session_manifest(monkeypatch, tmp_path: Path):
    def tampered_capture(*args, **kwargs):
        destinations = kwargs["destinations"]
        _write_fake_capture(destinations)
        result = _result(destinations)
        destinations.baseline.write_text("tampered after capture\n", encoding="utf-8")
        return result

    monkeypatch.setattr(session, "capture_physical_fastboot_baseline", tampered_capture)
    target = tmp_path / "session-01"

    with pytest.raises(session.PhysicalFirstTestSessionError, match="digest drifted"):
        session.begin_physical_first_test_session(
            _profile(),
            confirmation_token="AC2003",
            serial=SERIAL,
            firmware_build=FIRMWARE_BUILD,
            firmware_fingerprint=FIRMWARE_FINGERPRINT,
            session_dir=target,
        )

    assert not (target / session.SESSION_MANIFEST_NAME).exists()


def test_help_and_host_entrypoint_expose_only_explicit_session_command(monkeypatch, capsys):
    with pytest.raises(SystemExit) as exc:
        session.main(["--help"])
    assert exc.value.code == 0
    help_text = capsys.readouterr().out.lower()
    assert "read-only fastboot baseline" in help_text
    assert "no boot, flash, erase, slot change" in help_text

    import main as entrypoint

    seen = []
    monkeypatch.setattr(
        entrypoint,
        "physical_first_test_session_main",
        lambda argv: seen.append(("session", list(argv))) or 31,
    )
    monkeypatch.setattr(entrypoint, "app_main", lambda argv: seen.append(("app", list(argv))) or 23)

    assert entrypoint.main(["begin-physical-test-session", "--help"]) == 31
    assert entrypoint.main(["--doctor"]) == 23
    assert seen == [("session", ["--help"]), ("app", ["--doctor"])]
