from dataclasses import replace
from pathlib import Path

import pytest

from kaliphonestudio.candidate_authority_bundle import FirstBootAuthorityBundleEvidence
from kaliphonestudio.phosh_first_boot_binding import (
    PhoshFirstBootBindingError,
    bind_reviewed_phosh_rootfs_for_candidate_regeneration,
    build_phosh_first_boot_binding_from_paths,
    load_phosh_first_boot_binding,
    write_phosh_first_boot_binding,
)
from kaliphonestudio.phosh_rootfs_authority import (
    PhoshRootfsReviewPacketEvidence,
    build_reviewed_phosh_rootfs_authority,
    write_phosh_rootfs_authority,
    write_phosh_rootfs_review_packet,
)


def _h(ch: str) -> str:
    return ch * 64


def _c(ch: str) -> str:
    return ch * 40


def _candidate() -> FirstBootAuthorityBundleEvidence:
    return FirstBootAuthorityBundleEvidence(
        schema_version=1,
        profile_id="oneplus/avicii",
        first_boot_manifest_sha256=_h("1"),
        kernel_binding_sha256=_h("2"),
        rootfs_binding_sha256=_h("3"),
        device_tree_binding_sha256=_h("4"),
        kernel_authority_sha256=_h("5"),
        rootfs_authority_sha256=_h("6"),
        device_tree_authority_sha256=_h("7"),
        kernel_authority_run_id=101,
        kernel_authority_commit=_c("a"),
        kernel_authority_artifact_id=201,
        rootfs_authority_run_id=102,
        rootfs_authority_commit=_c("b"),
        rootfs_authority_artifact_id=202,
        device_tree_authority_run_id=103,
        device_tree_authority_commit=_c("c"),
        device_tree_authority_artifact_id=203,
        kernel_image_sha256=_h("8"),
        rootfs_artifact_sha256=_h("9"),
        dtb_sha256=_h("a"),
        dtbo_image_sha256=_h("b"),
        all_authorities_reviewed=True,
        all_required_artifacts_strict=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def _packet(*, rootfs_sha256: str = _h("c")) -> PhoshRootfsReviewPacketEvidence:
    return PhoshRootfsReviewPacketEvidence(
        schema_version=1,
        review_policy="phosh-rootfs-review-packet-v1",
        repository="Swir/KaliPhoneStudio",
        source_run_id=9001,
        source_run_attempt=1,
        source_commit=_c("d"),
        candidate_artifact_evidence_sha256=_h("d"),
        reproducibility_candidate_sha256=_h("e"),
        selected_build_evidence_sha256=_h("f"),
        upstream_commit=_c("e"),
        source_lock_sha256=_h("0"),
        build_contract_sha256=_h("1"),
        build_plan_sha256=_h("2"),
        rootfs_artifact_sha256=rootfs_sha256,
        rootfs_artifact_size=123456,
        package_manifest_sha256=_h("3"),
        package_count=321,
        strict_byte_identical=True,
        package_manifest_identical=True,
        rootfs_payload_verified=True,
        package_manifest_verified=True,
        independent_ab_match_verified=True,
        ready_for_authority_review=True,
        reviewed=False,
        reproducibility_authority=False,
        physical_validation_required=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def _authority(packet: PhoshRootfsReviewPacketEvidence):
    return build_reviewed_phosh_rootfs_authority(
        review_packet=packet,
        authority_name="phosh-arm64-reviewed",
        authority_run_id=packet.source_run_id,
        authority_commit=packet.source_commit,
        authority_artifact_id=777,
        reviewed=True,
    )


def test_bind_reviewed_phosh_rootfs_prepares_successor_candidate_only() -> None:
    candidate = _candidate()
    packet = _packet()
    authority = _authority(packet)

    evidence = bind_reviewed_phosh_rootfs_for_candidate_regeneration(
        candidate, authority, packet
    )

    assert evidence.profile_id == candidate.profile_id
    assert evidence.base_first_boot_manifest_sha256 == candidate.first_boot_manifest_sha256
    assert evidence.kernel_authority_sha256 == candidate.kernel_authority_sha256
    assert evidence.device_tree_authority_sha256 == candidate.device_tree_authority_sha256
    assert evidence.superseded_rootfs_artifact_sha256 == candidate.rootfs_artifact_sha256
    assert evidence.phosh_rootfs_artifact_sha256 == packet.rootfs_artifact_sha256
    assert evidence.rootfs_substitution_required is True
    assert evidence.candidate_manifest_regeneration_required is True
    assert evidence.ready_for_candidate_manifest_regeneration is True
    assert evidence.physical_validation_required is True
    assert evidence.hardware_verified is False
    assert evidence.beta_release_authorized is False
    assert evidence.beta_gate_credit is False


def test_direct_same_rootfs_must_use_existing_candidate_binding() -> None:
    candidate = _candidate()
    packet = _packet(rootfs_sha256=candidate.rootfs_artifact_sha256)
    authority = _authority(packet)

    with pytest.raises(PhoshFirstBootBindingError, match="existing direct Phosh candidate binding"):
        bind_reviewed_phosh_rootfs_for_candidate_regeneration(candidate, authority, packet)


def test_binding_rejects_unreviewed_or_unsafe_base_candidate() -> None:
    packet = _packet()
    authority = _authority(packet)

    with pytest.raises(PhoshFirstBootBindingError, match="reviewed and strict"):
        bind_reviewed_phosh_rootfs_for_candidate_regeneration(
            replace(_candidate(), all_authorities_reviewed=False), authority, packet
        )

    with pytest.raises(PhoshFirstBootBindingError, match="hardware/Beta credit"):
        bind_reviewed_phosh_rootfs_for_candidate_regeneration(
            replace(_candidate(), beta_gate_credit=True), authority, packet
        )


def test_path_builder_and_canonical_round_trip(tmp_path: Path) -> None:
    candidate = _candidate()
    packet = _packet()
    authority = _authority(packet)

    candidate_path = tmp_path / "first-boot-authority-bundle.json"
    packet_path = tmp_path / "phosh-rootfs-review-packet.json"
    authority_path = tmp_path / "phosh-rootfs-authority.json"
    output_path = tmp_path / "phosh-first-boot-binding.json"

    candidate_path.write_text(candidate.canonical_json(), encoding="utf-8", newline="\n")
    write_phosh_rootfs_review_packet(packet, packet_path)
    write_phosh_rootfs_authority(authority, authority_path)

    evidence = build_phosh_first_boot_binding_from_paths(
        candidate_path, authority_path, packet_path
    )
    digest = write_phosh_first_boot_binding(evidence, output_path)

    loaded = load_phosh_first_boot_binding(output_path)
    assert loaded == evidence
    assert digest == evidence.evidence_sha256()

    with pytest.raises(PhoshFirstBootBindingError, match="overwrite"):
        write_phosh_first_boot_binding(evidence, output_path)


def test_path_builder_rejects_detached_authority_packet(tmp_path: Path) -> None:
    candidate = _candidate()
    packet = _packet()
    authority = _authority(packet)
    detached_packet = replace(packet, package_count=packet.package_count + 1)

    candidate_path = tmp_path / "first-boot-authority-bundle.json"
    packet_path = tmp_path / "phosh-rootfs-review-packet.json"
    authority_path = tmp_path / "phosh-rootfs-authority.json"

    candidate_path.write_text(candidate.canonical_json(), encoding="utf-8", newline="\n")
    write_phosh_rootfs_review_packet(detached_packet, packet_path)
    write_phosh_rootfs_authority(authority, authority_path)

    with pytest.raises(PhoshFirstBootBindingError, match="detached from the reviewed packet"):
        build_phosh_first_boot_binding_from_paths(
            candidate_path, authority_path, packet_path
        )
