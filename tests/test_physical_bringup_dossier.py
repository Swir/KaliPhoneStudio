from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from kaliphonestudio.physical_bringup_dossier import (
    PhysicalBringupDossierError,
    build_physical_bringup_dossier,
    load_physical_bringup_dossier_evidence,
    validate_physical_bringup_dossier_evidence,
    write_physical_bringup_dossier_evidence,
)
from kaliphonestudio.physical_bringup_session import PhysicalBringupSessionEvidence


def _write(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return sha256(payload).hexdigest()


def _fixture(tmp_path: Path, *, early: bool = False, with_rootfs: bool = False):
    evidence_payloads = {
        "physical_candidate_gate": b'{"gate":1}\n',
        "physical_boot_observation": b'{"boot":1}\n',
        "rescue_diagnostics": b'{"diag":1}\n',
        "rescue_functional_probe": b'{"probe":1}\n',
        "physical_storage_discovery": b'{"discovery":1}\n',
        "physical_storage_review": b'{"review":1}\n',
    }
    raw_payloads = {
        "rescue_transcript": b"KPS_RESCUE_STAGE=init-reached-v1\n",
        "storage_discovery_report": b'{"storage":"observed"}\n',
        "recovery_plan": b"restore exact stock baseline\n",
        "storage_review_record": b'{"decision":"accepted"}\n',
        "storage_review_notes": b"manual review notes\n",
    }
    if early:
        evidence_payloads["kali_early_userspace_evidence"] = b'{"early":1}\n'
        raw_payloads["kali_early_userspace_transcript"] = b"KPS_KALI_STAGE=rootfs-systemd-early-v1\n"

    evidence_paths = {}
    raw_paths = {}
    evidence_digests = {}
    raw_digests = {}
    for role, payload in evidence_payloads.items():
        path = tmp_path / "evidence-files" / f"{role}.json"
        evidence_paths[role] = path
        evidence_digests[role] = _write(path, payload)
    for role, payload in raw_payloads.items():
        path = tmp_path / "raw" / f"{role}.bin"
        raw_paths[role] = path
        raw_digests[role] = _write(path, payload)

    rootfs_payload = b"rootfs-bytes" if with_rootfs else None
    rootfs_path = tmp_path / "rootfs.tar.xz"
    rootfs_sha = sha256(rootfs_payload or b"expected-rootfs-identity").hexdigest()
    rootfs_size = len(rootfs_payload) if with_rootfs else 137460600
    if with_rootfs:
        _write(rootfs_path, rootfs_payload)

    session = PhysicalBringupSessionEvidence(
        schema_version=1,
        session_policy="physical-bringup-evidence-chain-v1",
        profile_id="oneplus/avicii",
        device_serial="SERIAL123",
        firmware_build="OxygenOS-test-build",
        firmware_fingerprint="oneplus/avicii/test:user/release-keys",
        physical_candidate_gate_sha256=evidence_digests["physical_candidate_gate"],
        physical_boot_observation_sha256=evidence_digests["physical_boot_observation"],
        rescue_diagnostics_sha256=evidence_digests["rescue_diagnostics"],
        rescue_functional_probe_sha256=evidence_digests["rescue_functional_probe"],
        physical_storage_discovery_sha256=evidence_digests["physical_storage_discovery"],
        physical_storage_review_sha256=evidence_digests["physical_storage_review"],
        rootfs_handoff_assessment_sha256="c" * 64,
        rootfs_handoff_contract_sha256="d" * 64,
        rootfs_authority_sha256="a" * 64,
        rootfs_artifact_sha256=rootfs_sha,
        rootfs_artifact_size=rootfs_size,
        rescue_transcript_sha256=raw_digests["rescue_transcript"],
        rescue_probe_id="b" * 64,
        discovery_report_sha256=raw_digests["storage_discovery_report"],
        recovery_plan_sha256=raw_digests["recovery_plan"],
        storage_review_record_sha256=raw_digests["storage_review_record"],
        storage_review_notes_sha256=raw_digests["storage_review_notes"],
        kali_early_userspace_evidence_sha256=evidence_digests.get("kali_early_userspace_evidence"),
        kali_early_userspace_transcript_sha256=raw_digests.get("kali_early_userspace_transcript"),
        kali_early_userspace_probe_id=("e" * 64 if early else None),
        rescue_chain_complete=True,
        storage_discovery_chain_complete=True,
        storage_review_recorded=True,
        storage_review_accepted_for_strategy_design=True,
        kali_early_userspace_signal_present=early,
        manual_review_required=True,
        target_selected=False,
        storage_path_bound=False,
        write_authorized=False,
        handoff_ready=False,
        storage_verified=False,
        charging_battery_verified=False,
        display_touch_verified=False,
        recovery_verified=False,
        kali_early_userspace_verified=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    session_file = tmp_path / "physical-bringup-session.json"
    session_file.write_text(session.canonical_json(), encoding="utf-8", newline="\n")
    return session, session_file, evidence_paths, raw_paths, (rootfs_path if with_rootfs else None)


def test_exact_file_dossier_binds_full_session_without_promotion(tmp_path: Path) -> None:
    session, session_file, evidence, raw, _ = _fixture(tmp_path)
    dossier = build_physical_bringup_dossier(
        session, session_file=session_file, evidence_files=evidence, raw_files=raw
    )
    assert dossier.exact_file_set_verified is True
    assert dossier.required_file_count == 12
    assert dossier.supplied_file_count == 12
    assert dossier.rootfs_artifact_file_verified is False
    assert dossier.storage_review_accepted_for_strategy_design is True
    assert dossier.target_selected is False
    assert dossier.write_authorized is False
    assert dossier.storage_verified is False
    assert dossier.recovery_verified is False
    assert dossier.hardware_verified is False
    assert dossier.beta_gate_credit is False
    assert [item.role for item in dossier.files] == sorted(item.role for item in dossier.files)
    validate_physical_bringup_dossier_evidence(dossier)


def test_kali_early_userspace_requires_both_exact_files(tmp_path: Path) -> None:
    session, session_file, evidence, raw, _ = _fixture(tmp_path, early=True)
    evidence.pop("kali_early_userspace_evidence")
    with pytest.raises(PhysicalBringupDossierError, match="evidence file roles"):
        build_physical_bringup_dossier(
            session, session_file=session_file, evidence_files=evidence, raw_files=raw
        )


def test_unexpected_early_userspace_files_are_rejected(tmp_path: Path) -> None:
    session, session_file, evidence, raw, _ = _fixture(tmp_path)
    path = tmp_path / "extra.json"
    _write(path, b"extra")
    evidence["kali_early_userspace_evidence"] = path
    with pytest.raises(PhysicalBringupDossierError, match="evidence file roles"):
        build_physical_bringup_dossier(
            session, session_file=session_file, evidence_files=evidence, raw_files=raw
        )


def test_modified_raw_artifact_is_rejected(tmp_path: Path) -> None:
    session, session_file, evidence, raw, _ = _fixture(tmp_path)
    raw["recovery_plan"].write_bytes(b"substituted plan")
    with pytest.raises(PhysicalBringupDossierError, match="recovery_plan SHA-256"):
        build_physical_bringup_dossier(
            session, session_file=session_file, evidence_files=evidence, raw_files=raw
        )


def test_noncanonical_session_file_is_rejected(tmp_path: Path) -> None:
    session, session_file, evidence, raw, _ = _fixture(tmp_path)
    session_file.write_text("  " + session.canonical_json(), encoding="utf-8")
    with pytest.raises(PhysicalBringupDossierError, match="physical_bringup_session SHA-256"):
        build_physical_bringup_dossier(
            session, session_file=session_file, evidence_files=evidence, raw_files=raw
        )


def test_optional_rootfs_artifact_is_verified_by_hash_and_size(tmp_path: Path) -> None:
    session, session_file, evidence, raw, rootfs = _fixture(tmp_path, with_rootfs=True)
    dossier = build_physical_bringup_dossier(
        session,
        session_file=session_file,
        evidence_files=evidence,
        raw_files=raw,
        rootfs_artifact=rootfs,
    )
    assert dossier.rootfs_artifact_file_verified is True
    assert dossier.supplied_file_count == dossier.required_file_count + 1
    rootfs.write_bytes(b"wrong")
    with pytest.raises(PhysicalBringupDossierError, match="rootfs_artifact SHA-256"):
        build_physical_bringup_dossier(
            session,
            session_file=session_file,
            evidence_files=evidence,
            raw_files=raw,
            rootfs_artifact=rootfs,
        )


def test_symlink_raw_file_is_rejected(tmp_path: Path) -> None:
    session, session_file, evidence, raw, _ = _fixture(tmp_path)
    target = raw["storage_review_notes"]
    link = tmp_path / "notes-link"
    link.symlink_to(target)
    raw["storage_review_notes"] = link
    with pytest.raises(PhysicalBringupDossierError, match="regular non-symlink"):
        build_physical_bringup_dossier(
            session, session_file=session_file, evidence_files=evidence, raw_files=raw
        )


def test_validator_rejects_hardware_or_write_promotion(tmp_path: Path) -> None:
    session, session_file, evidence, raw, _ = _fixture(tmp_path)
    dossier = build_physical_bringup_dossier(
        session, session_file=session_file, evidence_files=evidence, raw_files=raw
    )
    for field in (
        "target_selected",
        "write_authorized",
        "storage_verified",
        "recovery_verified",
        "hardware_verified",
        "beta_gate_credit",
    ):
        with pytest.raises(PhysicalBringupDossierError, match="unsupported"):
            validate_physical_bringup_dossier_evidence(replace(dossier, **{field: True}))


def test_write_load_round_trip_and_refuse_overwrite(tmp_path: Path) -> None:
    session, session_file, evidence, raw, _ = _fixture(tmp_path)
    dossier = build_physical_bringup_dossier(
        session, session_file=session_file, evidence_files=evidence, raw_files=raw
    )
    out = tmp_path / "dossier.json"
    digest = write_physical_bringup_dossier_evidence(dossier, out)
    assert digest == dossier.evidence_sha256()
    assert load_physical_bringup_dossier_evidence(out) == dossier
    with pytest.raises(PhysicalBringupDossierError, match="refusing to overwrite"):
        write_physical_bringup_dossier_evidence(dossier, out)
