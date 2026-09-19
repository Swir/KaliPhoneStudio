from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import pytest

from kaliphonestudio.phosh_candidate_artifact import (
    PhoshCandidateArtifactError,
    materialize_phosh_rootfs_candidate,
    validate_phosh_rootfs_candidate_artifact_evidence,
    write_phosh_rootfs_candidate_artifact_evidence,
)
from kaliphonestudio.phosh_reproducibility import PhoshRootfsReproducibilityCandidate


UPSTREAM = "1" * 40
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _canonical(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _fixture(tmp_path: Path, *, manifest: bytes = b"alpha\t1.0\tarm64\nbeta\t2.0\tall\n"):
    rootfs = tmp_path / "phosh-a.tar.xz"
    rootfs.write_bytes(b"real-rootfs-candidate-bytes")
    manifest_path = tmp_path / "phosh-packages.tsv"
    manifest_path.write_bytes(manifest)

    build = {
        "schema_version": 1,
        "upstream_commit": UPSTREAM,
        "source_lock_sha256": SHA_A,
        "build_contract_sha256": SHA_B,
        "build_plan_sha256": SHA_C,
        "artifact_sha256": sha256(rootfs.read_bytes()).hexdigest(),
        "artifact_size": rootfs.stat().st_size,
        "package_manifest_sha256": sha256(manifest).hexdigest(),
        "package_count": len(manifest.decode("utf-8").splitlines()),
        "phosh_package_contract_satisfied": True,
        "reproducibility_authority": False,
        "physical_validation_required": True,
        "hardware_verified": False,
        "beta_gate_credit": False,
    }
    build_path = tmp_path / "phosh-build.json"
    build_bytes = _canonical(build)
    build_path.write_bytes(build_bytes)
    build_sha = sha256(build_bytes).hexdigest()

    candidate = PhoshRootfsReproducibilityCandidate(
        schema_version=1,
        upstream_commit=UPSTREAM,
        source_lock_sha256=SHA_A,
        build_contract_sha256=SHA_B,
        build_plan_sha256=SHA_C,
        build_a_origin="github-actions/Swir/KaliPhoneStudio/123/1/build-a",
        build_b_origin="github-actions/Swir/KaliPhoneStudio/123/1/build-b",
        build_a_evidence_sha256=build_sha,
        build_b_evidence_sha256="d" * 64,
        artifact_sha256=build["artifact_sha256"],
        artifact_size=build["artifact_size"],
        package_manifest_sha256=build["package_manifest_sha256"],
        package_count=build["package_count"],
        strict_byte_identical=True,
        package_manifest_identical=True,
        review_required=True,
        reproducibility_authority=False,
        physical_validation_required=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    candidate_path = tmp_path / "phosh-repro.json"
    candidate_path.write_text(candidate.canonical_json(), encoding="utf-8", newline="\n")
    return rootfs, manifest_path, build_path, candidate_path, candidate


def test_materializes_exact_build_a_payload_for_first_boot_assembly(tmp_path: Path) -> None:
    rootfs, manifest, build, repro, candidate = _fixture(tmp_path)
    evidence = materialize_phosh_rootfs_candidate(
        rootfs_artifact_path=rootfs,
        package_manifest_path=manifest,
        build_evidence_path=build,
        reproducibility_candidate_path=repro,
        selected_build_origin=candidate.build_a_origin,
    )
    assert evidence.rootfs_payload_verified is True
    assert evidence.package_manifest_verified is True
    assert evidence.independent_ab_match_verified is True
    assert evidence.ready_for_first_boot_candidate_assembly is True
    assert evidence.reproducibility_authority is False
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False

    destination = tmp_path / "candidate-artifact.json"
    digest = write_phosh_rootfs_candidate_artifact_evidence(evidence, destination)
    assert digest == sha256(destination.read_bytes()).hexdigest()
    assert destination.read_bytes() == evidence.canonical_json().encode("utf-8")


def test_rejects_rootfs_payload_drift(tmp_path: Path) -> None:
    rootfs, manifest, build, repro, candidate = _fixture(tmp_path)
    rootfs.write_bytes(b"changed-rootfs")
    with pytest.raises(PhoshCandidateArtifactError, match="size differs|bytes do not match"):
        materialize_phosh_rootfs_candidate(
            rootfs_artifact_path=rootfs,
            package_manifest_path=manifest,
            build_evidence_path=build,
            reproducibility_candidate_path=repro,
            selected_build_origin=candidate.build_a_origin,
        )


def test_rejects_detached_build_origin(tmp_path: Path) -> None:
    rootfs, manifest, build, repro, _candidate = _fixture(tmp_path)
    with pytest.raises(PhoshCandidateArtifactError, match="not part of the A/B"):
        materialize_phosh_rootfs_candidate(
            rootfs_artifact_path=rootfs,
            package_manifest_path=manifest,
            build_evidence_path=build,
            reproducibility_candidate_path=repro,
            selected_build_origin="github-actions/Swir/KaliPhoneStudio/999/1/build-a",
        )


def test_rejects_malformed_package_manifest_even_when_hashes_match(tmp_path: Path) -> None:
    manifest = b"alpha\t1.0\tamd64\n"
    rootfs, manifest_path, build, repro, candidate = _fixture(tmp_path, manifest=manifest)
    with pytest.raises(PhoshCandidateArtifactError, match="non-ARM64"):
        materialize_phosh_rootfs_candidate(
            rootfs_artifact_path=rootfs,
            package_manifest_path=manifest_path,
            build_evidence_path=build,
            reproducibility_candidate_path=repro,
            selected_build_origin=candidate.build_a_origin,
        )


def test_candidate_evidence_cannot_promote_authority_hardware_or_beta(tmp_path: Path) -> None:
    rootfs, manifest, build, repro, candidate = _fixture(tmp_path)
    evidence = materialize_phosh_rootfs_candidate(
        rootfs_artifact_path=rootfs,
        package_manifest_path=manifest,
        build_evidence_path=build,
        reproducibility_candidate_path=repro,
        selected_build_origin=candidate.build_a_origin,
    )
    for field in ("reproducibility_authority", "hardware_verified", "beta_gate_credit"):
        with pytest.raises(PhoshCandidateArtifactError, match=field):
            validate_phosh_rootfs_candidate_artifact_evidence(replace(evidence, **{field: True}))
