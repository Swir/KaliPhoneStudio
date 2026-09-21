from __future__ import annotations

import json
from pathlib import Path

import pytest

from kaliphonestudio import physical_candidate_preparation as preparation


def _write(path: Path, payload: bytes = b"fixture") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _session(tmp_path: Path, *, unsafe: bool = False) -> Path:
    session = tmp_path / "session"
    fastboot = session / "fastboot"
    fastboot.mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "profile_id": "oneplus/avicii",
        "device_serial": "SERIAL-001",
        "firmware_build": "AC2003_11.F.22",
        "firmware_fingerprint": "oneplus/avicii/avicii:12/test:user/release-keys",
        "fastboot_capture_bundle_sha256": "a" * 64,
        "fastboot_baseline_sha256": "b" * 64,
        "fastboot_tool_evidence_sha256": "c" * 64,
        "fastboot_transcript_sha256": "d" * 64,
        "fastboot_platform_tools_version": "36.0.0-13206524",
        "fastboot_executable_sha256": "e" * 64,
        "session_manifest_path": "physical-first-test-session.json",
        "fastboot_evidence_dir": "fastboot",
        "confirmation_token_verified": True,
        "physical_interaction_performed": True,
        "read_only_baseline_only": True,
        "temporary_boot_performed": unsafe,
        "persistent_write_authorized": False,
        "phone_storage_written": False,
        "hardware_verified": False,
        "beta_gate_credit": False,
    }
    _write(
        session / preparation.SESSION_MANIFEST_NAME,
        (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode(),
    )
    _write(fastboot / "fastboot-baseline.json", b"{}\n")
    _write(fastboot / "fastboot-capture-bundle.json", b"{}\n")
    _write(fastboot / "fastboot-tool.json", b"{}\n")
    return session


def _sources(tmp_path: Path) -> dict[str, Path]:
    return {
        "ota": _write(tmp_path / "oxygenos.zip", b"ota"),
        "extractor": _write(tmp_path / "payload-dumper-go.exe", b"extractor"),
        "first_boot_manifest": _write(tmp_path / "first-boot.json", b"{\"kind\":\"first\"}\n"),
        "authority_bundle": _write(tmp_path / "authority.json", b"{\"kind\":\"authority\"}\n"),
        "boot_authorization": _write(tmp_path / "boot-authorization.json", b"{\"kind\":\"authorization\"}\n"),
        "boot_plan": _write(tmp_path / "boot-plan.json", b"{\"kind\":\"plan\"}\n"),
        "candidate_boot": _write(tmp_path / "candidate-boot.img", b"candidate-boot"),
        "candidate_dtbo": _write(tmp_path / "candidate-dtbo.img", b"candidate-dtbo"),
        "fastboot_executable": _write(tmp_path / "fastboot.exe", b"fastboot"),
    }


def test_offline_preparation_composes_exact_stages_without_device_execution(tmp_path: Path, monkeypatch) -> None:
    session = _session(tmp_path)
    sources = _sources(tmp_path)
    calls: list[tuple[str, list[str]]] = []

    def stock(argv):
        args = list(argv or [])
        calls.append(("stock", args))
        out_dir = Path(args[args.index("--out-dir") + 1])
        _write(out_dir / "partitions" / "boot.img", b"stock-boot")
        _write(out_dir / "stock-provenance.json", b"{\"stock\":true}\n")
        return 0

    def output_stage(name: str):
        def run(argv):
            args = list(argv or [])
            calls.append((name, args))
            destination = Path(args[args.index("--out") + 1])
            _write(destination, (json.dumps({"stage": name}) + "\n").encode())
            return 0
        return run

    monkeypatch.setattr(preparation, "extract_stock_boot_from_ota_main", stock)
    monkeypatch.setattr(preparation, "bind_physical_stock_main", output_stage("physical-stock"))
    monkeypatch.setattr(preparation, "bind_physical_candidate_main", output_stage("physical-candidate"))
    monkeypatch.setattr(preparation, "bind_physical_boot_identity_main", output_stage("boot-identity"))
    monkeypatch.setattr(preparation, "prepare_temporary_boot_offer_main", output_stage("temporary-offer"))
    monkeypatch.setattr(preparation, "build_physical_recovery_readiness_main", output_stage("recovery-readiness"))

    evidence, digest = preparation.prepare_physical_candidate_offline(
        profile_id="oneplus/avicii",
        session_dir=session,
        devices_root=tmp_path / "devices",
        extractor_platform="windows-amd64",
        **sources,
    )

    assert [name for name, _ in calls] == [
        "stock",
        "physical-stock",
        "physical-candidate",
        "boot-identity",
        "temporary-offer",
        "recovery-readiness",
    ]
    assert "--candidate-dtbo" in calls[3][1]
    assert evidence.profile_id == "oneplus/avicii"
    assert evidence.device_serial == "SERIAL-001"
    assert evidence.host_pipeline_complete is True
    assert evidence.ready_for_temporary_boot_safety_review is True
    assert evidence.physical_interaction_performed_by_this_command is False
    assert evidence.external_device_command_executed is False
    assert evidence.temporary_boot_executed is False
    assert evidence.persistent_write_authorized is False
    assert evidence.phone_storage_written is False
    assert evidence.hardware_verified is False
    assert evidence.beta_release_authorized is False
    assert evidence.beta_gate_credit is False
    manifest = session / preparation.PREPARATION_MANIFEST_NAME
    assert manifest.is_file()
    assert len(digest) == 64
    assert json.loads(manifest.read_text(encoding="utf-8"))["ready_for_temporary_boot_safety_review"] is True


def test_unsafe_or_reused_session_refuses_before_any_stage(tmp_path: Path, monkeypatch) -> None:
    session = _session(tmp_path, unsafe=True)
    sources = _sources(tmp_path)
    called = False

    def forbidden(_argv):
        nonlocal called
        called = True
        raise AssertionError("stage must not run")

    monkeypatch.setattr(preparation, "extract_stock_boot_from_ota_main", forbidden)
    with pytest.raises(preparation.PhysicalCandidatePreparationError, match="temporary_boot_performed"):
        preparation.prepare_physical_candidate_offline(
            profile_id="oneplus/avicii",
            session_dir=session,
            devices_root=tmp_path / "devices",
            extractor_platform="windows-amd64",
            **sources,
        )
    assert called is False


def test_profile_mismatch_refuses_before_ota_or_candidate_work(tmp_path: Path, monkeypatch) -> None:
    session = _session(tmp_path)
    sources = _sources(tmp_path)
    called = False

    def forbidden(_argv):
        nonlocal called
        called = True
        raise AssertionError("stage must not run")

    monkeypatch.setattr(preparation, "extract_stock_boot_from_ota_main", forbidden)
    with pytest.raises(preparation.PhysicalCandidatePreparationError, match="selected profile"):
        preparation.prepare_physical_candidate_offline(
            profile_id="oneplus/other",
            session_dir=session,
            devices_root=tmp_path / "devices",
            extractor_platform="windows-amd64",
            **sources,
        )
    assert called is False


def test_stage_refusal_stops_following_pipeline(tmp_path: Path, monkeypatch) -> None:
    session = _session(tmp_path)
    sources = _sources(tmp_path)
    later_called = False

    def refused(_argv):
        return 2

    def later(_argv):
        nonlocal later_called
        later_called = True
        return 0

    monkeypatch.setattr(preparation, "extract_stock_boot_from_ota_main", refused)
    monkeypatch.setattr(preparation, "bind_physical_stock_main", later)
    with pytest.raises(preparation.PhysicalCandidatePreparationError, match="stock OTA extraction refused"):
        preparation.prepare_physical_candidate_offline(
            profile_id="oneplus/avicii",
            session_dir=session,
            devices_root=tmp_path / "devices",
            extractor_platform="windows-amd64",
            **sources,
        )
    assert later_called is False
    assert not (session / preparation.PREPARATION_MANIFEST_NAME).exists()
