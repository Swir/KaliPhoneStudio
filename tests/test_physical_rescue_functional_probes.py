from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from kaliphonestudio.physical_boot_observation import PhysicalBootObservationEvidence
from kaliphonestudio.physical_rescue_diagnostics import record_physical_rescue_diagnostics
from kaliphonestudio.physical_rescue_functional_probes import (
    PhysicalRescueFunctionalProbeError,
    load_physical_rescue_functional_probe_evidence,
    record_physical_rescue_functional_probes,
    validate_physical_rescue_functional_probe_evidence,
    write_physical_rescue_functional_probe_evidence,
)
from kaliphonestudio.profiles import DeviceProfile


def _digest(ch: str) -> str:
    return ch * 64


def _profile(tmp_path: Path, profile_id: str = "vendor/test") -> DeviceProfile:
    return DeviceProfile(path=tmp_path / "profile.json", data={"profile_id": profile_id})


def _payload(probe_id: str = _digest("a"), *, extra: bytes = b"") -> bytes:
    lines = [
        b"KPS_RESCUE_STAGE=init-reached-v1",
        b"KPS_RESCUE_PROBE_ID=" + probe_id.encode(),
        b"KPS_DIAG_BEGIN=readonly-sysfs-inventory-v1",
        b"KPS_DIAG_BLOCK=sda|122142720|0",
        b"KPS_DIAG_SCSI_HOST=host0|ufshcd",
        b"KPS_DIAG_POWER=battery|Battery|Charging|73|-|4012000|-325000|312",
        b"KPS_DIAG_END=readonly-sysfs-inventory-v1",
        b"KPS_PROBE_BEGIN=readonly-functional-probes-v1",
        b"KPS_PROBE_BLOCK_READ=sda|4096|ok",
        b"KPS_PROBE_BATTERY_SAMPLE=battery|1|Charging|Good|73|4012000|-325000|312",
        b"KPS_PROBE_BATTERY_SAMPLE=battery|2|Charging|Good|73|4015000|-310000|313",
        b"KPS_PROBE_END=readonly-functional-probes-v1",
    ]
    if extra:
        lines.append(extra)
    return b"\r\n".join(lines) + b"\r\n"


def _write(path: Path, payload: bytes) -> None:
    path.write_bytes(payload)


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


def _bound(tmp_path: Path, raw: bytes):
    transcript = tmp_path / "console.log"
    _write(transcript, raw)
    profile = _profile(tmp_path)
    observation = _observation(raw)
    diagnostics = record_physical_rescue_diagnostics(profile, observation, transcript)
    return profile, observation, diagnostics, transcript


def test_explicit_read_only_probe_is_bound_without_hardware_credit(tmp_path: Path) -> None:
    profile, observation, diagnostics, transcript = _bound(tmp_path, _payload())
    evidence = record_physical_rescue_functional_probes(profile, observation, diagnostics, transcript)
    assert evidence.physical_boot_observation_sha256 == observation.evidence_sha256()
    assert evidence.rescue_diagnostics_sha256 == diagnostics.evidence_sha256()
    assert evidence.block_read_record_count == 1
    assert evidence.block_read_success_count == 1
    assert evidence.battery_sample_count == 2
    assert evidence.battery_pair_count == 1
    assert evidence.storage_read_signal_observed is True
    assert evidence.battery_sampling_signal_observed is True
    assert evidence.explicit_local_authorization_required is True
    assert evidence.storage_verified is False
    assert evidence.charging_battery_verified is False
    assert evidence.phone_storage_written is False
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False


def test_transcript_must_be_same_one_bound_by_observation(tmp_path: Path) -> None:
    raw = _payload()
    profile, observation, diagnostics, transcript = _bound(tmp_path, raw)
    transcript.write_bytes(raw + b"noise\n")
    with pytest.raises(PhysicalRescueFunctionalProbeError, match="not the transcript bound"):
        record_physical_rescue_functional_probes(profile, observation, diagnostics, transcript)


def test_diagnostics_must_bind_same_observation(tmp_path: Path) -> None:
    profile, observation, diagnostics, transcript = _bound(tmp_path, _payload())
    forged = replace(diagnostics, physical_boot_observation_sha256=_digest("f"))
    with pytest.raises(PhysicalRescueFunctionalProbeError, match="not bound to the supplied"):
        record_physical_rescue_functional_probes(profile, observation, forged, transcript)


def test_duplicate_probe_block_is_rejected(tmp_path: Path) -> None:
    raw = _payload() + (
        b"KPS_PROBE_BEGIN=readonly-functional-probes-v1\n"
        b"KPS_PROBE_BLOCK_READ=sda|4096|ok\n"
        b"KPS_PROBE_END=readonly-functional-probes-v1\n"
    )
    profile, observation, diagnostics, transcript = _bound(tmp_path, raw)
    with pytest.raises(PhysicalRescueFunctionalProbeError, match="exactly one probe block"):
        record_physical_rescue_functional_probes(profile, observation, diagnostics, transcript)


def test_probe_marker_outside_block_is_rejected(tmp_path: Path) -> None:
    raw = _payload(extra=b"KPS_PROBE_BLOCK_READ=sdb|4096|ok")
    profile, observation, diagnostics, transcript = _bound(tmp_path, raw)
    with pytest.raises(PhysicalRescueFunctionalProbeError, match="outside the locked probe block"):
        record_physical_rescue_functional_probes(profile, observation, diagnostics, transcript)


def test_block_read_size_and_outcome_are_locked(tmp_path: Path) -> None:
    for bad in (b"sda|8192|ok", b"sda|4096|written"):
        raw = _payload().replace(b"sda|4096|ok", bad)
        profile, observation, diagnostics, transcript = _bound(tmp_path, raw)
        with pytest.raises(PhysicalRescueFunctionalProbeError):
            record_physical_rescue_functional_probes(profile, observation, diagnostics, transcript)


def test_single_battery_sample_does_not_claim_sampling_pair(tmp_path: Path) -> None:
    raw = _payload().replace(
        b"KPS_PROBE_BATTERY_SAMPLE=battery|2|Charging|Good|73|4015000|-310000|313\r\n",
        b"",
    )
    profile, observation, diagnostics, transcript = _bound(tmp_path, raw)
    evidence = record_physical_rescue_functional_probes(profile, observation, diagnostics, transcript)
    assert evidence.battery_sample_count == 1
    assert evidence.battery_pair_count == 0
    assert evidence.battery_sampling_signal_observed is False


def test_claim_tampering_is_rejected(tmp_path: Path) -> None:
    profile, observation, diagnostics, transcript = _bound(tmp_path, _payload())
    evidence = record_physical_rescue_functional_probes(profile, observation, diagnostics, transcript)
    with pytest.raises(PhysicalRescueFunctionalProbeError, match="unsupported hardware/Beta claim"):
        validate_physical_rescue_functional_probe_evidence(replace(evidence, storage_verified=True))


def test_round_trip_is_write_once(tmp_path: Path) -> None:
    profile, observation, diagnostics, transcript = _bound(tmp_path, _payload())
    evidence = record_physical_rescue_functional_probes(profile, observation, diagnostics, transcript)
    out = tmp_path / "functional.json"
    digest = write_physical_rescue_functional_probe_evidence(evidence, out)
    assert digest == evidence.evidence_sha256()
    assert load_physical_rescue_functional_probe_evidence(out) == evidence
    with pytest.raises(PhysicalRescueFunctionalProbeError, match="overwrite"):
        write_physical_rescue_functional_probe_evidence(evidence, out)


def test_unrelated_non_ascii_console_noise_is_ignored(tmp_path: Path) -> None:
    raw = _payload() + b"kernel-noise:\xff\xfe\n"
    profile, observation, diagnostics, transcript = _bound(tmp_path, raw)
    evidence = record_physical_rescue_functional_probes(profile, observation, diagnostics, transcript)
    assert evidence.probe_record_count == 3
