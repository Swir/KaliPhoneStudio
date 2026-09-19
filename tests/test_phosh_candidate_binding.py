from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from kaliphonestudio.candidate_authority_bundle import FirstBootAuthorityBundleEvidence
from kaliphonestudio.phosh_candidate_binding import (
    PhoshCandidateBindingError,
    bind_phosh_to_first_boot_candidate,
    build_phosh_candidate_binding_from_paths,
    load_phosh_candidate_binding,
    validate_phosh_candidate_binding,
    write_phosh_candidate_binding,
)
from kaliphonestudio.phosh_rootfs_binding import (
    PhoshRootfsAuthorityBindingEvidence,
    write_phosh_rootfs_authority_binding,
)


def _candidate(*, rootfs_authority: str = "6" * 64, rootfs_artifact: str = "7" * 64):
    return FirstBootAuthorityBundleEvidence(
        schema_version=1,
        profile_id="oneplus/avicii",
        first_boot_manifest_sha256="1" * 64,
        kernel_binding_sha256="2" * 64,
        rootfs_binding_sha256="3" * 64,
        device_tree_binding_sha256="4" * 64,
        kernel_authority_sha256="5" * 64,
        rootfs_authority_sha256=rootfs_authority,
        device_tree_authority_sha256="8" * 64,
        kernel_authority_run_id=101,
        kernel_authority_commit="a" * 40,
        kernel_authority_artifact_id=201,
        rootfs_authority_run_id=102,
        rootfs_authority_commit="b" * 40,
        rootfs_authority_artifact_id=202,
        device_tree_authority_run_id=103,
        device_tree_authority_commit="c" * 40,
        device_tree_authority_artifact_id=203,
        kernel_image_sha256="9" * 64,
        rootfs_artifact_sha256=rootfs_artifact,
        dtb_sha256="d" * 64,
        dtbo_image_sha256="e" * 64,
        all_authorities_reviewed=True,
        all_required_artifacts_strict=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def _phosh(*, rootfs_authority: str = "6" * 64, rootfs_artifact: str = "7" * 64):
    required = ("mobian-phosh", "mobian-phosh-phone", "squeekboard")
    return PhoshRootfsAuthorityBindingEvidence(
        schema_version=1,
        binding_policy="phosh-rootfs-authority-binding-v1",
        phosh_source_lock_sha256="f" * 64,
        phosh_upstream_commit="d" * 40,
        rootfs_authority_sha256=rootfs_authority,
        rootfs_authority_name="kali-arm64-phosh",
        rootfs_authority_commit="b" * 40,
        rootfs_release_tag="kali-rolling",
        rootfs_variant="full",
        rootfs_artifact_sha256=rootfs_artifact,
        rootfs_artifact_size=4_194_304,
        package_manifest_sha256="0" * 64,
        package_count=128,
        required_packages=required,
        installed_required_packages=tuple((name, "1.0-kps", "arm64") for name in required),
        host_userspace_package_contract_satisfied=True,
        rootfs_authority_reviewed=True,
        ready_for_physical_candidate_binding=True,
        physical_validation_required=True,
        display_verified=False,
        touch_verified=False,
        hardware_verified=False,
        beta_release_authorized=False,
        beta_gate_credit=False,
    )


def test_exact_candidate_and_phosh_rootfs_are_cross_bound_without_hardware_credit():
    candidate = _candidate()
    phosh = _phosh()

    evidence = bind_phosh_to_first_boot_candidate(candidate, phosh)

    assert evidence.profile_id == "oneplus/avicii"
    assert evidence.first_boot_manifest_sha256 == candidate.first_boot_manifest_sha256
    assert evidence.candidate_authority_bundle_sha256 == candidate.evidence_sha256()
    assert evidence.phosh_rootfs_binding_sha256 == phosh.evidence_sha256()
    assert evidence.rootfs_authority_sha256 == candidate.rootfs_authority_sha256
    assert evidence.rootfs_artifact_sha256 == candidate.rootfs_artifact_sha256
    assert evidence.required_packages == phosh.required_packages
    assert evidence.provenance_cross_bound is True
    assert evidence.ready_for_physical_phosh_validation is True
    assert evidence.physical_validation_required is True
    assert evidence.display_verified is False
    assert evidence.touch_verified is False
    assert evidence.hardware_verified is False
    assert evidence.beta_release_authorized is False
    assert evidence.beta_gate_credit is False


def test_rootfs_authority_drift_fails_closed():
    with pytest.raises(PhoshCandidateBindingError, match="different rootfs authorities"):
        bind_phosh_to_first_boot_candidate(_candidate(), _phosh(rootfs_authority="1" * 64))


def test_rootfs_artifact_drift_fails_closed():
    with pytest.raises(PhoshCandidateBindingError, match="different rootfs artifacts"):
        bind_phosh_to_first_boot_candidate(_candidate(), _phosh(rootfs_artifact="2" * 64))


def test_candidate_bundle_with_hardware_or_beta_credit_is_rejected():
    for field in ("hardware_verified", "beta_gate_credit"):
        with pytest.raises(PhoshCandidateBindingError, match="hardware/Beta credit"):
            bind_phosh_to_first_boot_candidate(replace(_candidate(), **{field: True}), _phosh())


def test_output_validator_rejects_any_host_side_promotion():
    evidence = bind_phosh_to_first_boot_candidate(_candidate(), _phosh())
    for field in (
        "display_verified",
        "touch_verified",
        "hardware_verified",
        "beta_release_authorized",
        "beta_gate_credit",
    ):
        with pytest.raises(PhoshCandidateBindingError, match="cannot promote"):
            validate_phosh_candidate_binding(replace(evidence, **{field: True}))


def test_write_load_roundtrip_is_canonical_and_create_only(tmp_path: Path):
    evidence = bind_phosh_to_first_boot_candidate(_candidate(), _phosh())
    target = tmp_path / "phosh-candidate-binding.json"

    digest = write_phosh_candidate_binding(evidence, target)
    loaded = load_phosh_candidate_binding(target)

    assert digest == evidence.evidence_sha256()
    assert loaded == evidence
    assert target.read_bytes() == evidence.canonical_json().encode("utf-8")
    with pytest.raises(PhoshCandidateBindingError, match="refusing to overwrite"):
        write_phosh_candidate_binding(evidence, target)


def test_path_builder_rejects_symlinked_candidate_bundle(tmp_path: Path):
    candidate = _candidate()
    candidate_file = tmp_path / "candidate.json"
    candidate_file.write_text(candidate.canonical_json(), encoding="utf-8", newline="\n")
    candidate_link = tmp_path / "candidate-link.json"
    candidate_link.symlink_to(candidate_file)
    phosh_file = tmp_path / "phosh.json"
    write_phosh_rootfs_authority_binding(_phosh(), phosh_file)

    with pytest.raises(PhoshCandidateBindingError, match="regular non-symlink"):
        build_phosh_candidate_binding_from_paths(candidate_link, phosh_file)


def test_path_builder_binds_two_exact_canonical_evidence_files(tmp_path: Path):
    candidate = _candidate()
    candidate_file = tmp_path / "candidate.json"
    candidate_file.write_text(candidate.canonical_json(), encoding="utf-8", newline="\n")
    phosh_file = tmp_path / "phosh.json"
    write_phosh_rootfs_authority_binding(_phosh(), phosh_file)

    evidence = build_phosh_candidate_binding_from_paths(candidate_file, phosh_file)

    assert evidence.candidate_authority_bundle_sha256 == candidate.evidence_sha256()
    assert evidence.phosh_rootfs_binding_sha256 == _phosh().evidence_sha256()
