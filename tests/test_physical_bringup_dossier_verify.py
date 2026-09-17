from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import pytest

from kaliphonestudio.physical_bringup_dossier import (
    DossierFileEvidence,
    PhysicalBringupDossierEvidence,
    PhysicalBringupDossierError,
    write_physical_bringup_dossier_evidence,
)
from kaliphonestudio.physical_bringup_dossier_verify import (
    validate_physical_bringup_dossier_verification_evidence,
    verify_physical_bringup_dossier_files,
    write_physical_bringup_dossier_verification_evidence,
)

_JSON_ROLES = {
    "physical_bringup_session",
    "physical_candidate_gate",
    "physical_boot_observation",
    "rescue_diagnostics",
    "rescue_functional_probe",
    "physical_storage_discovery",
    "physical_storage_review",
}
_RAW_ROLES = {
    "rescue_transcript",
    "storage_discovery_report",
    "recovery_plan",
    "storage_review_record",
    "storage_review_notes",
}


def _fixture(tmp_path: Path):
    role_files: dict[str, Path] = {}
    records: list[DossierFileEvidence] = []
    for role in sorted(_JSON_ROLES | _RAW_ROLES):
        path = tmp_path / "files" / role
        path.parent.mkdir(parents=True, exist_ok=True)
        if role in _JSON_ROLES:
            payload = (json.dumps({"role": role}, sort_keys=True, separators=(",", ":")) + "\n").encode()
            canonical = True
        else:
            payload = f"{role}\n".encode()
            canonical = False
        path.write_bytes(payload)
        role_files[role] = path
        records.append(DossierFileEvidence(role, sha256(payload).hexdigest(), len(payload), canonical))

    dossier = PhysicalBringupDossierEvidence(
        schema_version=1,
        dossier_policy="physical-bringup-exact-file-dossier-v1",
        profile_id="oneplus/avicii",
        device_serial="SERIAL123",
        firmware_build="OxygenOS-test",
        firmware_fingerprint="oneplus/avicii/test:user/release-keys",
        physical_bringup_session_sha256="1" * 64,
        rootfs_authority_sha256="2" * 64,
        rootfs_artifact_sha256="3" * 64,
        rootfs_artifact_size=137460600,
        rescue_probe_id="4" * 64,
        storage_review_accepted_for_strategy_design=True,
        kali_early_userspace_signal_present=False,
        required_file_count=12,
        supplied_file_count=12,
        exact_file_set_verified=True,
        rootfs_artifact_file_verified=False,
        files=tuple(records),
        manual_review_required=True,
        target_selected=False,
        storage_path_bound=False,
        write_authorized=False,
        handoff_ready=False,
        storage_verified=False,
        recovery_verified=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    dossier_file = tmp_path / "dossier.json"
    write_physical_bringup_dossier_evidence(dossier, dossier_file)
    return dossier, dossier_file, role_files


def test_reverify_exact_post_copy_set(tmp_path: Path) -> None:
    dossier, dossier_file, role_files = _fixture(tmp_path)
    evidence = verify_physical_bringup_dossier_files(
        dossier, dossier_file=dossier_file, role_files=role_files
    )
    assert evidence.exact_file_set_verified is True
    assert evidence.verified_role_count == 12
    assert evidence.canonical_json_role_count == 8
    assert evidence.write_authorized is False
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False


def test_reverify_rejects_missing_and_extra_roles(tmp_path: Path) -> None:
    dossier, dossier_file, role_files = _fixture(tmp_path)
    role_files.pop("recovery_plan")
    role_files["extra"] = dossier_file
    with pytest.raises(PhysicalBringupDossierError, match="verification file roles"):
        verify_physical_bringup_dossier_files(
            dossier, dossier_file=dossier_file, role_files=role_files
        )


def test_reverify_rejects_changed_member(tmp_path: Path) -> None:
    dossier, dossier_file, role_files = _fixture(tmp_path)
    role_files["storage_review_notes"].write_bytes(b"changed\n")
    with pytest.raises(PhysicalBringupDossierError, match="SHA-256"):
        verify_physical_bringup_dossier_files(
            dossier, dossier_file=dossier_file, role_files=role_files
        )


def test_reverify_requires_canonical_json_evidence(tmp_path: Path) -> None:
    dossier, dossier_file, role_files = _fixture(tmp_path)
    role = "physical_candidate_gate"
    payload = b'{ "role" : "physical_candidate_gate" }\n'
    role_files[role].write_bytes(payload)
    records = tuple(
        replace(item, sha256=sha256(payload).hexdigest(), size=len(payload)) if item.role == role else item
        for item in dossier.files
    )
    forged = replace(dossier, files=records)
    forged_file = tmp_path / "forged.json"
    write_physical_bringup_dossier_evidence(forged, forged_file)
    with pytest.raises(PhysicalBringupDossierError, match="not encoded as canonical JSON"):
        verify_physical_bringup_dossier_files(
            forged, dossier_file=forged_file, role_files=role_files
        )


def test_verification_evidence_is_immutable_and_non_promoting(tmp_path: Path) -> None:
    dossier, dossier_file, role_files = _fixture(tmp_path)
    evidence = verify_physical_bringup_dossier_files(
        dossier, dossier_file=dossier_file, role_files=role_files
    )
    out = tmp_path / "verification.json"
    digest = write_physical_bringup_dossier_verification_evidence(evidence, out)
    assert digest == evidence.evidence_sha256()
    with pytest.raises(PhysicalBringupDossierError, match="refusing to overwrite"):
        write_physical_bringup_dossier_verification_evidence(evidence, out)
    with pytest.raises(PhysicalBringupDossierError, match="unsupported"):
        validate_physical_bringup_dossier_verification_evidence(
            replace(evidence, hardware_verified=True)
        )
