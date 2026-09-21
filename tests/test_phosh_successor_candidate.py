from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from kaliphonestudio.candidate import FirstBootCandidateManifest
from kaliphonestudio.candidate_authority_bundle import FirstBootAuthorityBundleEvidence
from kaliphonestudio.phosh_first_boot_binding import PhoshFirstBootBindingEvidence
from kaliphonestudio.phosh_successor_candidate import (
    PhoshSuccessorCandidateError,
    build_phosh_successor_candidate,
    build_phosh_successor_candidate_from_paths,
    load_phosh_successor_candidate,
    validate_phosh_successor_candidate,
    write_phosh_successor_candidate,
)


def _h(label: str) -> str:
    return sha256(label.encode("utf-8")).hexdigest()


def _manifest() -> FirstBootCandidateManifest:
    return FirstBootCandidateManifest(
        schema_version=8,
        profile_id="oneplus/avicii",
        device_serial="ABC123",
        fastboot_baseline_sha256=_h("baseline"),
        firmware_build="AC2003_11.F.22",
        firmware_fingerprint="OnePlus/avicii/avicii:12/RKQ1/test:user/release-keys",
        boot_authorization_sha256=_h("boot-auth"),
        boot_plan_sha256=_h("boot-plan"),
        boot_image_sha256=_h("boot-image"),
        boot_image_size=60_000_000,
        kernel_evidence_sha256=_h("kernel-evidence"),
        kernel_plan_sha256=_h("kernel-plan"),
        kernel_source_commit="a" * 40,
        kernel_version="4.19.300",
        kernel_config_sha256=_h("kernel-config"),
        kernel_image_sha256=_h("kernel-image"),
        kernel_image_size=43_878_416,
        kernel_reproducibility_evidence_sha256=_h("kernel-repro"),
        kernel_reproducibility_binding_evidence_sha256=_h("kernel-repro-binding"),
        kernel_build_recipe_sha256=_h("kernel-recipe"),
        kernel_reproducible_environment_sha256=_h("kernel-env"),
        kernel_build_a_run_evidence_sha256=_h("kernel-a"),
        kernel_build_b_run_evidence_sha256=_h("kernel-b"),
        kernel_reproducible=True,
        kernel_distinct_build_roots_verified=True,
        kernel_toolchain_evidence_sha256=_h("toolchain-evidence"),
        kernel_toolchain_lock_sha256=_h("toolchain-lock"),
        kernel_toolchain_source_evidence_sha256=_h("toolchain-source"),
        kernel_toolchain_binding_evidence_sha256=_h("toolchain-binding"),
        kernel_toolchain_materialized_evidence_sha256=_h("toolchain-materialized"),
        kernel_clang_revision="clang-r416183b",
        kernel_clang_sha256=_h("clang"),
        kernel_clang_size=123_456,
        kernel_build_config_sha256=_h("build-config"),
        device_tree_evidence_sha256=_h("dt-evidence"),
        device_tree_format_lock_sha256=_h("dt-format-lock"),
        dtb_sha256=_h("dtb"),
        dtb_size=406_620,
        dtb_tree_count=1,
        dtbo_sha256=_h("dtbo"),
        dtbo_size=352_256,
        dtbo_entry_count=1,
        rootfs_evidence_sha256=_h("legacy-rootfs-evidence"),
        rootfs_artifact_sha256=_h("legacy-rootfs"),
        rootfs_artifact_size=137_460_600,
        rootfs_package_manifest_sha256=_h("legacy-packages"),
        rootfs_package_count=269,
        rootfs_source_lock_sha256=_h("legacy-rootfs-lock"),
        repository_snapshot_sha256=_h("repo-snapshot"),
    )


def _bundle(manifest: FirstBootCandidateManifest) -> FirstBootAuthorityBundleEvidence:
    return FirstBootAuthorityBundleEvidence(
        schema_version=1,
        profile_id=manifest.profile_id,
        first_boot_manifest_sha256=manifest.manifest_sha256(),
        kernel_binding_sha256=_h("kernel-binding"),
        rootfs_binding_sha256=_h("rootfs-binding"),
        device_tree_binding_sha256=_h("dt-binding"),
        kernel_authority_sha256=_h("kernel-authority"),
        rootfs_authority_sha256=_h("legacy-rootfs-authority"),
        device_tree_authority_sha256=_h("dt-authority"),
        kernel_authority_run_id=101,
        kernel_authority_commit="b" * 40,
        kernel_authority_artifact_id=201,
        rootfs_authority_run_id=102,
        rootfs_authority_commit="c" * 40,
        rootfs_authority_artifact_id=202,
        device_tree_authority_run_id=103,
        device_tree_authority_commit="d" * 40,
        device_tree_authority_artifact_id=203,
        kernel_image_sha256=manifest.kernel_image_sha256,
        rootfs_artifact_sha256=manifest.rootfs_artifact_sha256,
        dtb_sha256=manifest.dtb_sha256,
        dtbo_image_sha256=manifest.dtbo_sha256,
        all_authorities_reviewed=True,
        all_required_artifacts_strict=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def _binding(
    manifest: FirstBootCandidateManifest,
    bundle: FirstBootAuthorityBundleEvidence,
) -> PhoshFirstBootBindingEvidence:
    return PhoshFirstBootBindingEvidence(
        schema_version=1,
        binding_policy="phosh-first-boot-regeneration-binding-v1",
        profile_id=manifest.profile_id,
        base_first_boot_manifest_sha256=manifest.manifest_sha256(),
        base_candidate_authority_bundle_sha256=bundle.evidence_sha256(),
        kernel_authority_sha256=bundle.kernel_authority_sha256,
        kernel_authority_run_id=bundle.kernel_authority_run_id,
        kernel_authority_commit=bundle.kernel_authority_commit,
        kernel_authority_artifact_id=bundle.kernel_authority_artifact_id,
        kernel_image_sha256=manifest.kernel_image_sha256,
        device_tree_authority_sha256=bundle.device_tree_authority_sha256,
        device_tree_authority_run_id=bundle.device_tree_authority_run_id,
        device_tree_authority_commit=bundle.device_tree_authority_commit,
        device_tree_authority_artifact_id=bundle.device_tree_authority_artifact_id,
        dtb_sha256=manifest.dtb_sha256,
        dtbo_image_sha256=manifest.dtbo_sha256,
        superseded_rootfs_authority_sha256=bundle.rootfs_authority_sha256,
        superseded_rootfs_artifact_sha256=manifest.rootfs_artifact_sha256,
        phosh_rootfs_authority_sha256=_h("phosh-authority"),
        phosh_rootfs_authority_name="phosh-arm64-reviewed",
        phosh_rootfs_authority_run_id=9001,
        phosh_rootfs_authority_commit="e" * 40,
        phosh_rootfs_authority_artifact_id=777,
        phosh_review_packet_sha256=_h("phosh-review-packet"),
        phosh_source_commit="f" * 40,
        phosh_upstream_commit="1" * 40,
        phosh_source_lock_sha256=_h("phosh-source-lock"),
        phosh_rootfs_artifact_sha256=_h("phosh-rootfs"),
        phosh_rootfs_artifact_size=456_789_012,
        phosh_package_manifest_sha256=_h("phosh-packages"),
        phosh_package_count=521,
        kernel_device_tree_provenance_reused=True,
        rootfs_substitution_required=True,
        candidate_manifest_regeneration_required=True,
        ready_for_candidate_manifest_regeneration=True,
        physical_validation_required=True,
        display_verified=False,
        touch_verified=False,
        hardware_verified=False,
        beta_release_authorized=False,
        beta_gate_credit=False,
    )


def _objects():
    manifest = _manifest()
    bundle = _bundle(manifest)
    binding = _binding(manifest, bundle)
    return manifest, bundle, binding


def test_build_successor_reuses_boot_kernel_dt_and_replaces_only_rootfs_identity() -> None:
    manifest, bundle, binding = _objects()

    successor = build_phosh_successor_candidate(manifest, bundle, binding)

    assert successor.profile_id == manifest.profile_id
    assert successor.device_serial == manifest.device_serial
    assert successor.boot_image_sha256 == manifest.boot_image_sha256
    assert successor.kernel_image_sha256 == manifest.kernel_image_sha256
    assert successor.dtb_sha256 == manifest.dtb_sha256
    assert successor.dtbo_image_sha256 == manifest.dtbo_sha256
    assert successor.base_first_boot_manifest_sha256 == manifest.manifest_sha256()
    assert successor.base_candidate_authority_bundle_sha256 == bundle.evidence_sha256()
    assert successor.phosh_first_boot_binding_sha256 == binding.evidence_sha256()
    assert successor.superseded_rootfs_artifact_sha256 == manifest.rootfs_artifact_sha256
    assert successor.rootfs_artifact_sha256 == binding.phosh_rootfs_artifact_sha256
    assert successor.rootfs_artifact_sha256 != manifest.rootfs_artifact_sha256
    assert successor.reviewed_phosh_rootfs_bound is True
    assert successor.physical_validation_required is True
    assert successor.display_verified is False
    assert successor.touch_verified is False
    assert successor.hardware_verified is False
    assert successor.beta_release_authorized is False
    assert successor.beta_gate_credit is False


def test_rejects_binding_detached_from_base_manifest_or_bundle() -> None:
    manifest, bundle, binding = _objects()

    with pytest.raises(PhoshSuccessorCandidateError, match="exact base manifest"):
        build_phosh_successor_candidate(
            manifest,
            bundle,
            replace(binding, base_first_boot_manifest_sha256=_h("detached-manifest")),
        )

    with pytest.raises(PhoshSuccessorCandidateError, match="exact base authority bundle"):
        build_phosh_successor_candidate(
            manifest,
            bundle,
            replace(binding, base_candidate_authority_bundle_sha256=_h("detached-bundle")),
        )


def test_rejects_kernel_or_superseded_rootfs_identity_drift() -> None:
    manifest, bundle, binding = _objects()

    with pytest.raises(PhoshSuccessorCandidateError, match="kernel Image"):
        build_phosh_successor_candidate(
            manifest, bundle, replace(binding, kernel_image_sha256=_h("wrong-kernel"))
        )

    with pytest.raises(PhoshSuccessorCandidateError, match="superseded rootfs"):
        build_phosh_successor_candidate(
            manifest,
            bundle,
            replace(binding, superseded_rootfs_artifact_sha256=_h("wrong-old-rootfs")),
        )


def test_rejects_unsafe_or_unreviewed_base_authority_bundle() -> None:
    manifest, bundle, binding = _objects()

    with pytest.raises(PhoshSuccessorCandidateError, match="reviewed and strict"):
        build_phosh_successor_candidate(
            manifest, replace(bundle, all_authorities_reviewed=False), binding
        )

    with pytest.raises(PhoshSuccessorCandidateError, match="hardware/Beta credit"):
        build_phosh_successor_candidate(
            manifest, replace(bundle, beta_gate_credit=True), binding
        )


def test_successor_host_claims_are_fail_closed() -> None:
    successor = build_phosh_successor_candidate(*_objects())

    with pytest.raises(PhoshSuccessorCandidateError, match="cannot promote display_verified"):
        validate_phosh_successor_candidate(replace(successor, display_verified=True))

    with pytest.raises(PhoshSuccessorCandidateError, match="cannot promote beta_gate_credit"):
        validate_phosh_successor_candidate(replace(successor, beta_gate_credit=True))


def test_path_builder_canonical_round_trip_and_create_only_writer(tmp_path: Path) -> None:
    manifest, bundle, binding = _objects()
    manifest_path = tmp_path / "first-boot-manifest.json"
    bundle_path = tmp_path / "first-boot-authority-bundle.json"
    binding_path = tmp_path / "phosh-first-boot-binding.json"
    output_path = tmp_path / "phosh-successor-first-boot-candidate.json"

    manifest_path.write_text(manifest.canonical_json(), encoding="utf-8", newline="\n")
    bundle_path.write_text(bundle.canonical_json(), encoding="utf-8", newline="\n")
    binding_path.write_text(binding.canonical_json(), encoding="utf-8", newline="\n")

    successor = build_phosh_successor_candidate_from_paths(
        manifest_path, bundle_path, binding_path
    )
    digest = write_phosh_successor_candidate(successor, output_path)

    assert digest == successor.manifest_sha256()
    assert output_path.read_text(encoding="utf-8") == successor.canonical_json()
    assert load_phosh_successor_candidate(output_path) == successor

    with pytest.raises(PhoshSuccessorCandidateError, match="overwrite"):
        write_phosh_successor_candidate(successor, output_path)
