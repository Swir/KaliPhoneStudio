from copy import deepcopy
import json
from pathlib import Path

import pytest

from kaliphonestudio.fastboot_baseline import (
    FastbootBaselineError,
    capture_fastboot_baseline,
    parse_fastboot_getvar_all,
    require_device_matches_baseline,
    write_fastboot_baseline_evidence,
)
from kaliphonestudio.profiles import ProfileError, get_profile, validate_profile
from kaliphonestudio.safety import SafetyError, VerifiedDevice


ROOT = Path(__file__).resolve().parents[1]
DEVICES = ROOT / "devices"
PROFILE_PATH = DEVICES / "oneplus" / "avicii" / "profile.json"


def _profile():
    return get_profile(DEVICES, "oneplus/avicii")


def _transcript(*, product="avicii", serial="SERIAL123", slot="a", count="2", unlocked="no") -> bytes:
    return (
        f"(bootloader) product: {product}\n"
        f"(bootloader) serialno: {serial}\n"
        f"(bootloader) current-slot: {slot}\n"
        f"(bootloader) slot-count: {count}\n"
        f"(bootloader) unlocked: {unlocked}\n"
        "(bootloader) secure: yes\n"
        "(bootloader) version-bootloader: avicii-test-1\n"
        "(bootloader) version-baseband: modem-test-1\n"
        "(bootloader) partition-size:boot: 0x6000000\n"
        "Finished. Total time: 0.003s\n"
    ).encode("utf-8")


def _capture(tmp_path: Path, payload: bytes | None = None):
    transcript = tmp_path / "fastboot.txt"
    transcript.write_bytes(payload if payload is not None else _transcript())
    return capture_fastboot_baseline(
        _profile(),
        transcript=transcript,
        firmware_build="AC2003_11_F.22",
        firmware_fingerprint="OnePlus/avicii/avicii:13/test/F.22:user/release-keys",
    )


def test_capture_binds_exact_profile_firmware_and_transcript(tmp_path):
    evidence = _capture(tmp_path)
    assert evidence.schema_version == 1
    assert evidence.profile_id == "oneplus/avicii"
    assert evidence.product == "avicii"
    assert evidence.serialno == "SERIAL123"
    assert evidence.current_slot == "a"
    assert evidence.slot_count == 2
    assert evidence.unlocked is False
    assert evidence.secure is True
    assert evidence.bootloader_version == "avicii-test-1"
    assert evidence.baseband_version == "modem-test-1"
    assert evidence.variables["partition-size:boot"] == "0x6000000"
    assert len(evidence.transcript_sha256) == 64
    assert evidence.beta_gate_credit is False


def test_conflicting_duplicate_and_failed_command_are_rejected():
    with pytest.raises(FastbootBaselineError, match="conflicting duplicate"):
        parse_fastboot_getvar_all(
            _transcript() + b"(bootloader) serialno: DIFFERENT\n"
        )
    with pytest.raises(FastbootBaselineError, match="failed command"):
        parse_fastboot_getvar_all(b"FAILED (remote: command not allowed)\n")


def test_required_vars_wrong_identity_and_ab_invariants_fail_closed(tmp_path):
    missing = _transcript().replace(b"(bootloader) secure: yes\n", b"")
    with pytest.raises(FastbootBaselineError, match="missing required"):
        _capture(tmp_path, missing)

    (tmp_path / "fastboot.txt").unlink()
    with pytest.raises(FastbootBaselineError, match="does not identify profile"):
        _capture(tmp_path, _transcript(product="other-device"))

    (tmp_path / "fastboot.txt").unlink()
    with pytest.raises(FastbootBaselineError, match="current-slot"):
        _capture(tmp_path, _transcript(slot="c"))

    (tmp_path / "fastboot.txt").unlink()
    with pytest.raises(FastbootBaselineError, match="profile expectation"):
        _capture(tmp_path, _transcript(count="3"))


def test_yes_no_and_serial_contracts_are_strict(tmp_path):
    with pytest.raises(FastbootBaselineError, match="yes or no"):
        _capture(tmp_path, _transcript(unlocked="true"))

    (tmp_path / "fastboot.txt").unlink()
    with pytest.raises(FastbootBaselineError, match="whitespace"):
        _capture(tmp_path, _transcript(serial="BAD SERIAL"))


def test_evidence_is_canonical_refuses_overwrite_and_binds_serial(tmp_path):
    evidence = _capture(tmp_path)
    out = tmp_path / "baseline.json"
    digest = write_fastboot_baseline_evidence(evidence, out)
    assert digest == evidence.evidence_sha256()
    parsed = json.loads(out.read_text(encoding="utf-8"))
    assert parsed["profile_id"] == "oneplus/avicii"
    assert parsed["beta_gate_credit"] is False
    with pytest.raises(FastbootBaselineError, match="overwrite"):
        write_fastboot_baseline_evidence(evidence, out)

    require_device_matches_baseline(
        _profile(), evidence, VerifiedDevice("oneplus/avicii", "SERIAL123", "b", True)
    )
    with pytest.raises(SafetyError, match="serial"):
        require_device_matches_baseline(
            _profile(), evidence, VerifiedDevice("oneplus/avicii", "OTHER", "a", True)
        )


def test_profile_schema_v2_requires_complete_fastboot_probe_contract():
    data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    assert data["schema_version"] == 2

    broken = deepcopy(data)
    del broken["fastboot_probe"]
    with pytest.raises(ProfileError, match="fastboot_probe"):
        validate_profile(broken)

    broken = deepcopy(data)
    broken["fastboot_probe"]["identity_var"] = "not-required"
    with pytest.raises(ProfileError, match="required_vars"):
        validate_profile(broken)

    broken = deepcopy(data)
    broken["fastboot_probe"]["required_vars"].append("../unsafe")
    with pytest.raises(ProfileError, match="unsafe"):
        validate_profile(broken)

    broken = deepcopy(data)
    broken["fastboot_probe"]["expected_slot_count"] = 1
    with pytest.raises(ProfileError, match="expected_slot_count"):
        validate_profile(broken)
