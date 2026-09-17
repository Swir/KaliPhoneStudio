from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from kaliphonestudio.physical_boot_observation import PhysicalBootObservationEvidence
from kaliphonestudio.physical_rescue_diagnostics import (
    PhysicalRescueDiagnosticsError,
    load_physical_boot_observation_for_diagnostics,
    load_physical_rescue_diagnostics_evidence,
    record_physical_rescue_diagnostics,
    validate_physical_rescue_diagnostics_evidence,
    write_physical_rescue_diagnostics_evidence,
)
from kaliphonestudio.profiles import DeviceProfile


def _digest(ch: str) -> str:
    return ch * 64


def _profile(tmp_path: Path, profile_id: str = "vendor/test") -> DeviceProfile:
    return DeviceProfile(path=tmp_path / "profile.json", data={"profile_id": profile_id})


def _transcript(path: Path, probe_id: str = _digest("a"), *, outside: bytes = b"") -> bytes:
    lines = [
        b"KPS_RESCUE_STAGE=init-reached-v1",
        b"KPS_RESCUE_PROBE_ID=" + probe_id.encode(),
        b"KPS_DIAG_BEGIN=readonly-sysfs-inventory-v1",
        b"KPS_DIAG_BLOCK=sda|122142720|0",
        b"KPS_DIAG_SCSI_HOST=host0|ufshcd",
        b"KPS_DIAG_POWER=battery|Battery|Charging|73|-|4012000|-325000|312",
        b"KPS_DIAG_INPUT=event2|goodix_ts",
        b"KPS_DIAG_GRAPHICS=fb0|msm_drm",
        b"KPS_DIAG_DRM=card0-DSI-1|connected",
        b"KPS_DIAG_END=readonly-sysfs-inventory-v1",
    ]
    if outside:
        lines.append(outside)
    payload = b"\r\n".join(lines) + b"\r\n"
    path.write_bytes(payload)
    return payload


def _observation(raw: bytes, profile_id: str = "vendor/test", probe_id: str = _digest("a")) -> PhysicalBootObservationEvidence:
    return PhysicalBootObservationEvidence(
        schema_version=1,
        profile_id=profile_id,
        device_serial="SERIAL-001",
        execution_evidence_sha256=_digest("1"),
        offer_sha256=_digest("2"),
        rescue_candidate_evidence_sha256=_digest("3"),
        rescue_ramdisk_sha256=_digest("4"),
        rescue_probe_id=probe_id,
        transcript_sha256=sha256(raw).hexdigest(),
        transcript_size=len(raw),
        stage_marker_count=1,
        probe_marker_count=1,
        observation_policy="exact-rescue-probe-console-binding-v1",
        physical_observation_recorded=True,
        temporary_boot_command_succeeded=True,
        rescue_init_observed=True,
        kali_early_userspace_verified=False,
        storage_verified=False,
        display_touch_verified=False,
        charging_battery_verified=False,
        recovery_verified=False,
        manual_review_required=True,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def test_physical_observation_loader_revalidates_schema(tmp_path: Path) -> None:
    transcript = tmp_path / "console.log"
    raw = _transcript(transcript)
    observation = _observation(raw)
    path = tmp_path / "observation.json"
    path.write_text(observation.canonical_json(), encoding="utf-8", newline="\n")
    assert load_physical_boot_observation_for_diagnostics(path) == observation


def test_readonly_inventory_is_bound_without_hardware_credit(tmp_path: Path) -> None:
    transcript = tmp_path / "console.log"
    raw = _transcript(transcript)
    observation = _observation(raw)
    evidence = record_physical_rescue_diagnostics(_profile(tmp_path), observation, transcript)
    assert evidence.physical_boot_observation_sha256 == observation.evidence_sha256()
    assert evidence.transcript_sha256 == observation.transcript_sha256
    assert evidence.diagnostic_record_count == 6
    assert evidence.block_record_count == 1
    assert evidence.scsi_host_record_count == 1
    assert evidence.power_record_count == 1
    assert evidence.input_record_count == 1
    assert evidence.graphics_record_count == 1
    assert evidence.drm_record_count == 1
    assert evidence.ufs_signal_observed is True
    assert evidence.battery_signal_observed is True
    assert evidence.input_signal_observed is True
    assert evidence.graphics_signal_observed is True
    assert evidence.storage_verified is False
    assert evidence.display_touch_verified is False
    assert evidence.charging_battery_verified is False
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False


def test_transcript_must_match_bound_observation(tmp_path: Path) -> None:
    transcript = tmp_path / "console.log"
    raw = _transcript(transcript)
    observation = _observation(raw)
    transcript.write_bytes(raw + b"extra\n")
    with pytest.raises(PhysicalRescueDiagnosticsError, match="not the transcript bound"):
        record_physical_rescue_diagnostics(_profile(tmp_path), observation, transcript)


def test_duplicate_diagnostic_block_is_rejected(tmp_path: Path) -> None:
    transcript = tmp_path / "console.log"
    raw = _transcript(transcript)
    duplicate = raw + b"KPS_DIAG_BEGIN=readonly-sysfs-inventory-v1\nKPS_DIAG_BLOCK=sdb|1|0\nKPS_DIAG_END=readonly-sysfs-inventory-v1\n"
    transcript.write_bytes(duplicate)
    with pytest.raises(PhysicalRescueDiagnosticsError, match="exactly one diagnostic block"):
        record_physical_rescue_diagnostics(_profile(tmp_path), _observation(duplicate), transcript)


def test_diagnostic_marker_outside_block_is_rejected(tmp_path: Path) -> None:
    transcript = tmp_path / "console.log"
    raw = _transcript(transcript, outside=b"KPS_DIAG_BLOCK=sdb|1|0")
    with pytest.raises(PhysicalRescueDiagnosticsError, match="outside the locked diagnostic block"):
        record_physical_rescue_diagnostics(_profile(tmp_path), _observation(raw), transcript)


def test_malformed_power_record_is_rejected(tmp_path: Path) -> None:
    transcript = tmp_path / "console.log"
    raw = _transcript(transcript).replace(
        b"KPS_DIAG_POWER=battery|Battery|Charging|73|-|4012000|-325000|312",
        b"KPS_DIAG_POWER=battery|Battery|Charging",
    )
    transcript.write_bytes(raw)
    with pytest.raises(PhysicalRescueDiagnosticsError, match="field count drifted"):
        record_physical_rescue_diagnostics(_profile(tmp_path), _observation(raw), transcript)


def test_profile_mismatch_is_rejected(tmp_path: Path) -> None:
    transcript = tmp_path / "console.log"
    raw = _transcript(transcript)
    with pytest.raises(PhysicalRescueDiagnosticsError, match="profile does not match"):
        record_physical_rescue_diagnostics(_profile(tmp_path, "vendor/other"), _observation(raw), transcript)


def test_claim_tampering_is_rejected(tmp_path: Path) -> None:
    transcript = tmp_path / "console.log"
    raw = _transcript(transcript)
    evidence = record_physical_rescue_diagnostics(_profile(tmp_path), _observation(raw), transcript)
    with pytest.raises(PhysicalRescueDiagnosticsError, match="unsupported hardware/Beta claim"):
        validate_physical_rescue_diagnostics_evidence(replace(evidence, storage_verified=True))


def test_evidence_round_trip_and_write_once(tmp_path: Path) -> None:
    transcript = tmp_path / "console.log"
    raw = _transcript(transcript)
    evidence = record_physical_rescue_diagnostics(_profile(tmp_path), _observation(raw), transcript)
    out = tmp_path / "diagnostics.json"
    digest = write_physical_rescue_diagnostics_evidence(evidence, out)
    assert digest == evidence.evidence_sha256()
    assert load_physical_rescue_diagnostics_evidence(out) == evidence
    with pytest.raises(PhysicalRescueDiagnosticsError, match="overwrite"):
        write_physical_rescue_diagnostics_evidence(evidence, out)


def test_unrelated_non_ascii_console_noise_is_ignored(tmp_path: Path) -> None:
    transcript = tmp_path / "console.log"
    raw = _transcript(transcript) + b"kernel-noise:\xff\xfe\n"
    transcript.write_bytes(raw)
    evidence = record_physical_rescue_diagnostics(_profile(tmp_path), _observation(raw), transcript)
    assert evidence.diagnostic_record_count == 6
