from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import pytest

from kaliphonestudio.physical_boot_observation import (
    PhysicalBootObservationError,
    load_temporary_boot_execution_evidence,
    record_physical_boot_observation,
    write_physical_boot_observation_evidence,
)
from kaliphonestudio.profiles import DeviceProfile
from kaliphonestudio.rescue_candidate import (
    RescueCandidateEvidence,
    load_rescue_candidate_evidence,
    validate_rescue_candidate_evidence,
    write_rescue_candidate_evidence,
)
from kaliphonestudio.rescue_payload import RescuePayloadError
from kaliphonestudio.temporary_boot_execution import TemporaryBootExecutionEvidence


def _digest(char: str) -> str:
    return char * 64


def _rescue(profile_id: str = "vendor/test") -> RescueCandidateEvidence:
    repro = _digest("a")
    staging = _digest("b")
    init = _digest("c")
    policy = "profile+repro-payload+staging+init-v1"
    material = {
        "schema_version": 1,
        "profile_id": profile_id,
        "payload_repro_evidence_sha256": repro,
        "payload_staging_evidence_sha256": staging,
        "init_sha256": init,
        "policy": policy,
    }
    canonical = json.dumps(material, sort_keys=True, separators=(",", ":")) + "\n"
    probe_id = sha256(canonical.encode("utf-8")).hexdigest()
    probe_payload = (probe_id + "\n").encode("ascii")
    return RescueCandidateEvidence(
        schema_version=2,
        profile_id=profile_id,
        payload_repro_evidence_sha256=repro,
        payload_staging_evidence_sha256=staging,
        initramfs_evidence_sha256=_digest("d"),
        ramdisk_sha256=_digest("e"),
        ramdisk_size=4096,
        ramdisk_compression="lz4",
        init_sha256=init,
        rescue_probe_id=probe_id,
        rescue_probe_file_sha256=sha256(probe_payload).hexdigest(),
        rescue_probe_policy=policy,
        verified=True,
    )


def _execution(profile_id: str = "vendor/test", serial: str = "SERIAL-001") -> TemporaryBootExecutionEvidence:
    return TemporaryBootExecutionEvidence(
        schema_version=1,
        profile_id=profile_id,
        device_serial=serial,
        offer_sha256=_digest("1"),
        authorization_sha256=_digest("2"),
        runtime_probe_sha256=_digest("3"),
        argv_sha256=_digest("4"),
        returncode=0,
        output_sha256=_digest("5"),
        output_size=37,
        execution_policy="single-serial-fastboot-boot-no-persistent-write-v1",
        command_invoked=True,
        temporary_boot_executed=True,
        temporary_boot_command_succeeded=True,
        persistent_write=False,
        phone_storage_written=False,
        kali_userspace_verified=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def _profile(tmp_path: Path, profile_id: str = "vendor/test") -> DeviceProfile:
    return DeviceProfile(path=tmp_path / "profile.json", data={"profile_id": profile_id})


def _transcript(path: Path, probe_id: str, *, crlf: bool = True) -> bytes:
    newline = b"\r\n" if crlf else b"\n"
    payload = newline.join(
        (
            b"bootloader: boot command accepted",
            b"KPS_RESCUE_STAGE=init-reached-v1",
            b"KPS_RESCUE_PROBE_ID=" + probe_id.encode("ascii"),
            b"KaliPhoneStudio rescue userspace",
            b"",
        )
    )
    path.write_bytes(payload)
    return payload


def test_exact_markers_bind_physical_observation_without_beta_credit(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    rescue = _rescue()
    execution = _execution()
    transcript = tmp_path / "console.log"
    raw = _transcript(transcript, rescue.rescue_probe_id)

    evidence = record_physical_boot_observation(profile, execution, rescue, transcript)

    assert evidence.execution_evidence_sha256 == execution.evidence_sha256()
    assert evidence.rescue_candidate_evidence_sha256 == rescue.evidence_sha256()
    assert evidence.rescue_probe_id == rescue.rescue_probe_id
    assert evidence.transcript_sha256 == sha256(raw).hexdigest()
    assert evidence.stage_marker_count == 1
    assert evidence.probe_marker_count == 1
    assert evidence.rescue_init_observed is True
    assert evidence.manual_review_required is True
    assert evidence.kali_early_userspace_verified is False
    assert evidence.storage_verified is False
    assert evidence.charging_battery_verified is False
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False


def test_wrong_probe_id_is_rejected(tmp_path: Path) -> None:
    rescue = _rescue()
    transcript = tmp_path / "console.log"
    _transcript(transcript, _digest("f"))
    with pytest.raises(PhysicalBootObservationError, match="conflicting rescue probe id"):
        record_physical_boot_observation(_profile(tmp_path), _execution(), rescue, transcript)


def test_missing_stage_marker_is_rejected(tmp_path: Path) -> None:
    rescue = _rescue()
    transcript = tmp_path / "console.log"
    transcript.write_bytes(b"KPS_RESCUE_PROBE_ID=" + rescue.rescue_probe_id.encode("ascii") + b"\n")
    with pytest.raises(PhysicalBootObservationError, match="exact rescue proof markers"):
        record_physical_boot_observation(_profile(tmp_path), _execution(), rescue, transcript)


def test_failed_fastboot_execution_cannot_be_promoted(tmp_path: Path) -> None:
    rescue = _rescue()
    transcript = tmp_path / "console.log"
    _transcript(transcript, rescue.rescue_probe_id)
    failed = replace(
        _execution(),
        returncode=1,
        temporary_boot_command_succeeded=False,
    )
    with pytest.raises(PhysicalBootObservationError, match="successful Fastboot boot command"):
        record_physical_boot_observation(_profile(tmp_path), failed, rescue, transcript)


def test_profile_mismatch_is_rejected(tmp_path: Path) -> None:
    rescue = _rescue("vendor/a")
    transcript = tmp_path / "console.log"
    _transcript(transcript, rescue.rescue_probe_id)
    with pytest.raises(PhysicalBootObservationError, match="do not match"):
        record_physical_boot_observation(
            _profile(tmp_path, "vendor/b"),
            _execution("vendor/b"),
            rescue,
            transcript,
        )


def test_rescue_probe_is_fail_closed_and_round_trips(tmp_path: Path) -> None:
    rescue = _rescue()
    validate_rescue_candidate_evidence(rescue)
    out = tmp_path / "rescue.json"
    digest = write_rescue_candidate_evidence(rescue, out)
    loaded = load_rescue_candidate_evidence(out)
    assert loaded == rescue
    assert digest == rescue.evidence_sha256()

    tampered = replace(rescue, rescue_probe_id=_digest("0"))
    with pytest.raises(RescuePayloadError, match="detached from candidate provenance"):
        validate_rescue_candidate_evidence(tampered)
    with pytest.raises(RescuePayloadError, match="overwrite"):
        write_rescue_candidate_evidence(rescue, out)


def test_execution_and_observation_writers_are_immutable(tmp_path: Path) -> None:
    execution = _execution()
    execution_path = tmp_path / "execution.json"
    execution_path.write_text(execution.canonical_json(), encoding="utf-8", newline="\n")
    assert load_temporary_boot_execution_evidence(execution_path) == execution

    rescue = _rescue()
    transcript = tmp_path / "console.log"
    _transcript(transcript, rescue.rescue_probe_id, crlf=False)
    observation = record_physical_boot_observation(_profile(tmp_path), execution, rescue, transcript)
    out = tmp_path / "observation.json"
    first = write_physical_boot_observation_evidence(observation, out)
    assert first == observation.evidence_sha256()
    with pytest.raises(PhysicalBootObservationError, match="overwrite"):
        write_physical_boot_observation_evidence(observation, out)
