from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from kaliphonestudio.phosh_candidate_artifact import PhoshRootfsCandidateArtifactEvidence
from kaliphonestudio.phosh_reproducibility import PhoshRootfsReproducibilityCandidate
from kaliphonestudio.phosh_rootfs_authority import (
    PhoshRootfsAuthorityError,
    build_phosh_rootfs_review_packet,
    build_reviewed_phosh_rootfs_authority,
    load_and_verify_phosh_rootfs_authority,
    load_phosh_rootfs_review_packet,
    write_phosh_rootfs_authority,
    write_phosh_rootfs_review_packet,
)


UPSTREAM = "1" * 40
HEAD = "2" * 40
SOURCE = "a" * 64
CONTRACT = "b" * 64
PLAN = "c" * 64
ARTIFACT = "d" * 64
MANIFEST = "e" * 64


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _write_chain(tmp_path: Path):
    build = {
        "schema_version": 1,
        "upstream_commit": UPSTREAM,
        "source_lock_sha256": SOURCE,
        "build_contract_sha256": CONTRACT,
        "build_plan_sha256": PLAN,
        "artifact_sha256": ARTIFACT,
        "artifact_size": 4096,
        "package_manifest_sha256": MANIFEST,
        "package_count": 42,
        "phosh_package_contract_satisfied": True,
        "reproducibility_authority": False,
        "physical_validation_required": True,
        "hardware_verified": False,
        "beta_gate_credit": False,
    }
    build_payload = _canonical(build)
    build_sha = sha256(build_payload).hexdigest()
    build_path = tmp_path / "build.json"
    build_path.write_bytes(build_payload)

    repro = PhoshRootfsReproducibilityCandidate(
        schema_version=1,
        upstream_commit=UPSTREAM,
        source_lock_sha256=SOURCE,
        build_contract_sha256=CONTRACT,
        build_plan_sha256=PLAN,
        build_a_origin="github-actions/Swir/KaliPhoneStudio/100/1/build-a",
        build_b_origin="github-actions/Swir/KaliPhoneStudio/100/1/build-b",
        build_a_evidence_sha256=build_sha,
        build_b_evidence_sha256="f" * 64,
        artifact_sha256=ARTIFACT,
        artifact_size=4096,
        package_manifest_sha256=MANIFEST,
        package_count=42,
        strict_byte_identical=True,
        package_manifest_identical=True,
        review_required=True,
        reproducibility_authority=False,
        physical_validation_required=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    repro_path = tmp_path / "repro.json"
    repro_path.write_text(repro.canonical_json(), encoding="utf-8", newline="\n")

    candidate = PhoshRootfsCandidateArtifactEvidence(
        schema_version=1,
        candidate_policy="phosh-rootfs-candidate-artifact-v1",
        selected_build_origin=repro.build_a_origin,
        selected_build_evidence_sha256=build_sha,
        reproducibility_candidate_sha256=repro.evidence_sha256(),
        upstream_commit=UPSTREAM,
        source_lock_sha256=SOURCE,
        build_contract_sha256=CONTRACT,
        build_plan_sha256=PLAN,
        rootfs_artifact_sha256=ARTIFACT,
        rootfs_artifact_size=4096,
        package_manifest_sha256=MANIFEST,
        package_count=42,
        rootfs_payload_verified=True,
        package_manifest_verified=True,
        independent_ab_match_verified=True,
        ready_for_first_boot_candidate_assembly=True,
        reproducibility_authority=False,
        physical_validation_required=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(candidate.canonical_json(), encoding="utf-8", newline="\n")
    return build_path, repro_path, candidate_path


def _packet(tmp_path: Path):
    build_path, repro_path, candidate_path = _write_chain(tmp_path)
    return build_phosh_rootfs_review_packet(
        candidate_artifact_path=candidate_path,
        reproducibility_candidate_path=repro_path,
        selected_build_evidence_path=build_path,
        repository="Swir/KaliPhoneStudio",
        source_run_id=100,
        source_run_attempt=1,
        source_commit=HEAD,
    )


def test_review_packet_binds_real_candidate_chain_without_authority_credit(tmp_path: Path):
    packet = _packet(tmp_path)
    assert packet.rootfs_artifact_sha256 == ARTIFACT
    assert packet.package_manifest_sha256 == MANIFEST
    assert packet.strict_byte_identical is True
    assert packet.ready_for_authority_review is True
    assert packet.reviewed is False
    assert packet.reproducibility_authority is False
    assert packet.hardware_verified is False
    assert packet.beta_gate_credit is False


def test_review_packet_rejects_detached_candidate(tmp_path: Path):
    build_path, repro_path, candidate_path = _write_chain(tmp_path)
    raw = json.loads(candidate_path.read_text(encoding="utf-8"))
    raw["reproducibility_candidate_sha256"] = "0" * 64
    candidate_path.write_bytes(_canonical(raw))
    with pytest.raises(PhoshRootfsAuthorityError, match="detached"):
        build_phosh_rootfs_review_packet(
            candidate_artifact_path=candidate_path,
            reproducibility_candidate_path=repro_path,
            selected_build_evidence_path=build_path,
            repository="Swir/KaliPhoneStudio",
            source_run_id=100,
            source_run_attempt=1,
            source_commit=HEAD,
        )


def test_authority_requires_explicit_review_and_exact_run_identity(tmp_path: Path):
    packet = _packet(tmp_path)
    with pytest.raises(PhoshRootfsAuthorityError, match="reviewed=true"):
        build_reviewed_phosh_rootfs_authority(
            review_packet=packet,
            authority_name="phosh-arm64-test",
            authority_run_id=100,
            authority_commit=HEAD,
            authority_artifact_id=77,
            reviewed=False,
        )
    with pytest.raises(PhoshRootfsAuthorityError, match="run id"):
        build_reviewed_phosh_rootfs_authority(
            review_packet=packet,
            authority_name="phosh-arm64-test",
            authority_run_id=101,
            authority_commit=HEAD,
            authority_artifact_id=77,
            reviewed=True,
        )


def test_reviewed_authority_round_trip_stays_host_only(tmp_path: Path):
    packet = _packet(tmp_path)
    packet_path = tmp_path / "packet.json"
    write_phosh_rootfs_review_packet(packet, packet_path)
    loaded_packet = load_phosh_rootfs_review_packet(packet_path)
    authority = build_reviewed_phosh_rootfs_authority(
        review_packet=loaded_packet,
        authority_name="phosh-arm64-test",
        authority_run_id=100,
        authority_commit=HEAD,
        authority_artifact_id=77,
        reviewed=True,
    )
    authority_path = tmp_path / "authority.json"
    digest = write_phosh_rootfs_authority(authority, authority_path)
    verified = load_and_verify_phosh_rootfs_authority(authority_path, packet_path)
    assert verified.authority_sha256() == digest
    assert verified.reviewed is True
    assert verified.reproducibility_authority is True
    assert verified.ready_for_first_boot_binding is True
    assert verified.physical_validation_required is True
    assert verified.hardware_verified is False
    assert verified.beta_gate_credit is False


def test_review_packet_refuses_noncanonical_input(tmp_path: Path):
    build_path, repro_path, candidate_path = _write_chain(tmp_path)
    raw = json.loads(repro_path.read_text(encoding="utf-8"))
    repro_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(PhoshRootfsAuthorityError, match="canonical JSON"):
        build_phosh_rootfs_review_packet(
            candidate_artifact_path=candidate_path,
            reproducibility_candidate_path=repro_path,
            selected_build_evidence_path=build_path,
            repository="Swir/KaliPhoneStudio",
            source_run_id=100,
            source_run_attempt=1,
            source_commit=HEAD,
        )
