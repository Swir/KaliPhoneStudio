from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from kaliphonestudio.phosh_physical_candidate_adapter import (
    PhoshPhysicalCandidateAdapterError,
    bind_phosh_successor_to_physical_gate,
    build_phosh_physical_candidate_adapter_from_paths,
    load_phosh_physical_candidate_adapter,
    validate_phosh_physical_candidate_adapter,
    write_phosh_physical_candidate_adapter,
)
from kaliphonestudio.phosh_successor_candidate import PhoshSuccessorCandidateManifest
from kaliphonestudio.physical_candidate_gate import PhysicalCandidateGateEvidence


def _h(label: str) -> str:
    return sha256(label.encode("utf-8")).hexdigest()


def _successor() -> PhoshSuccessorCandidateManifest:
    return PhoshSuccessorCandidateManifest(
        schema_version=1,
        candidate_policy="phosh-first-boot-successor-v1",
        profile_id="oneplus/avicii",
        device_serial="ABC123",
        fastboot_baseline_sha256=_h("baseline"),
        firmware_build="AC2003_11.F.22",
        firmware_fingerprint="OnePlus/avicii/avicii:12/RKQ1/test:user/release-keys",
        boot_authorization_sha256=_h("boot-auth"),
        boot_plan_sha256=_h("boot-plan"),
        boot_image_sha256=_h("boot-image"),
        boot_image_size=60_000_000,
        base_first_boot_manifest_sha256=_h("base-manifest"),
        base_candidate_authority_bundle_sha256=_h("base-authority-bundle"),
        phosh_first_boot_binding_sha256=_h("phosh-first-boot-binding"),
        kernel_authority_sha256=_h("kernel-authority"),
        kernel_authority_run_id=101,
        kernel_authority_commit="a" * 40,
        kernel_authority_artifact_id=201,
        kernel_image_sha256=_h("kernel-image"),
        kernel_image_size=43_878_416,
        device_tree_authority_sha256=_h("dt-authority"),
        device_tree_authority_run_id=102,
        device_tree_authority_commit="b" * 40,
        device_tree_authority_artifact_id=202,
        dtb_sha256=_h("dtb"),
        dtb_size=406_620,
        dtbo_image_sha256=_h("dtbo"),
        dtbo_size=352_256,
        superseded_rootfs_artifact_sha256=_h("legacy-rootfs"),
        phosh_rootfs_authority_sha256=_h("phosh-authority"),
        phosh_rootfs_authority_name="phosh-arm64-reviewed",
        phosh_rootfs_authority_run_id=9001,
        phosh_rootfs_authority_commit="c" * 40,
        phosh_rootfs_authority_artifact_id=777,
        phosh_review_packet_sha256=_h("phosh-review-packet"),
        phosh_source_commit="d" * 40,
        phosh_upstream_commit="e" * 40,
        phosh_source_lock_sha256=_h("phosh-source-lock"),
        rootfs_artifact_sha256=_h("phosh-rootfs"),
        rootfs_artifact_size=456_789_012,
        rootfs_package_manifest_sha256=_h("phosh-packages"),
        rootfs_package_count=521,
        kernel_device_tree_provenance_reused=True,
        reviewed_phosh_rootfs_bound=True,
        physical_validation_required=True,
        display_verified=False,
        touch_verified=False,
        hardware_verified=False,
        beta_release_authorized=False,
        beta_gate_credit=False,
    )


def _gate(successor: PhoshSuccessorCandidateManifest) -> PhysicalCandidateGateEvidence:
    return PhysicalCandidateGateEvidence(
        schema_version=1,
        profile_id=successor.profile_id,
        device_serial=successor.device_serial,
        firmware_build=successor.firmware_build,
        firmware_fingerprint=successor.firmware_fingerprint,
        physical_baseline_bundle_sha256=_h("physical-baseline-bundle"),
        fastboot_capture_bundle_sha256=_h("fastboot-capture-bundle"),
        fastboot_baseline_evidence_sha256=successor.fastboot_baseline_sha256,
        fastboot_transcript_sha256=_h("fastboot-transcript"),
        stock_provenance_sha256=_h("stock-provenance"),
        stock_ota_sha256=_h("stock-ota"),
        stock_boot_sha256=_h("stock-boot"),
        first_boot_manifest_sha256=successor.base_first_boot_manifest_sha256,
        first_boot_authority_bundle_sha256=successor.base_candidate_authority_bundle_sha256,
        boot_authorization_sha256=successor.boot_authorization_sha256,
        boot_plan_sha256=successor.boot_plan_sha256,
        boot_image_sha256=successor.boot_image_sha256,
        boot_image_size=successor.boot_image_size,
        kernel_image_sha256=successor.kernel_image_sha256,
        rootfs_artifact_sha256=successor.superseded_rootfs_artifact_sha256,
        dtb_sha256=successor.dtb_sha256,
        dtbo_image_sha256=successor.dtbo_image_sha256,
        reviewed_authorities_bound=True,
        exact_physical_baseline_bound=True,
        ready_for_temporary_boot_offer=True,
        temporary_boot_executed=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def _objects():
    successor = _successor()
    return successor, _gate(successor)


def test_adapter_cross_binds_successor_to_exact_physical_campaign() -> None:
    successor, gate = _objects()

    evidence = bind_phosh_successor_to_physical_gate(successor, gate)

    assert evidence.profile_id == successor.profile_id == gate.profile_id
    assert evidence.device_serial == successor.device_serial == gate.device_serial
    assert evidence.physical_candidate_gate_sha256 == gate.evidence_sha256()
    assert evidence.physical_baseline_bundle_sha256 == gate.physical_baseline_bundle_sha256
    assert evidence.phosh_successor_candidate_sha256 == successor.manifest_sha256()
    assert evidence.rootfs_artifact_sha256 == successor.rootfs_artifact_sha256
    assert evidence.superseded_rootfs_artifact_sha256 == gate.rootfs_artifact_sha256
    assert evidence.exact_physical_gate_bound is True
    assert evidence.reviewed_phosh_successor_bound is True
    assert evidence.ready_for_physical_staging_review is True
    assert evidence.physical_validation_required is True
    assert evidence.staging_target_selected is False
    assert evidence.rootfs_staged is False
    assert evidence.temporary_boot_authorized is False
    assert evidence.temporary_boot_executed is False
    assert evidence.phone_storage_written is False
    assert evidence.hardware_verified is False
    assert evidence.beta_release_authorized is False
    assert evidence.beta_gate_credit is False


@pytest.mark.parametrize(
    ("field", "replacement", "match"),
    [
        ("device_serial", "OTHER", "device serial"),
        ("firmware_build", "OTHER_BUILD", "firmware build"),
        ("fastboot_baseline_evidence_sha256", _h("other-baseline"), "Fastboot baseline"),
        ("first_boot_manifest_sha256", _h("other-manifest"), "base first-boot manifest"),
        ("boot_image_sha256", _h("other-boot"), "boot image"),
        ("kernel_image_sha256", _h("other-kernel"), "kernel image"),
        ("rootfs_artifact_sha256", _h("other-legacy-rootfs"), "superseded rootfs"),
    ],
)
def test_adapter_rejects_physical_gate_identity_drift(
    field: str, replacement: object, match: str
) -> None:
    successor, gate = _objects()
    changed = replace(gate, **{field: replacement})
    with pytest.raises(PhoshPhysicalCandidateAdapterError, match=match):
        bind_phosh_successor_to_physical_gate(successor, changed)


def test_adapter_rejects_physical_gate_with_promoted_execution_or_beta() -> None:
    successor, gate = _objects()

    with pytest.raises(PhoshPhysicalCandidateAdapterError, match="temporary_boot_executed"):
        bind_phosh_successor_to_physical_gate(
            successor, replace(gate, temporary_boot_executed=True)
        )
    with pytest.raises(PhoshPhysicalCandidateAdapterError, match="beta_gate_credit"):
        bind_phosh_successor_to_physical_gate(
            successor, replace(gate, beta_gate_credit=True)
        )


def test_adapter_evidence_cannot_promote_staging_write_boot_or_hardware() -> None:
    evidence = bind_phosh_successor_to_physical_gate(*_objects())

    for field in (
        "staging_target_selected",
        "rootfs_staged",
        "temporary_boot_authorized",
        "temporary_boot_executed",
        "phone_storage_written",
        "hardware_verified",
        "beta_release_authorized",
        "beta_gate_credit",
    ):
        with pytest.raises(PhoshPhysicalCandidateAdapterError, match=field):
            validate_phosh_physical_candidate_adapter(
                replace(evidence, **{field: True})
            )


def test_path_builder_round_trip_and_create_only_writer(tmp_path: Path) -> None:
    successor, gate = _objects()
    successor_path = tmp_path / "phosh-successor-first-boot-candidate.json"
    gate_path = tmp_path / "physical-candidate-gate.json"
    output_path = tmp_path / "phosh-physical-candidate-adapter.json"

    successor_path.write_text(successor.canonical_json(), encoding="utf-8", newline="\n")
    gate_path.write_text(gate.canonical_json(), encoding="utf-8", newline="\n")

    evidence = build_phosh_physical_candidate_adapter_from_paths(
        successor_path, gate_path
    )
    digest = write_phosh_physical_candidate_adapter(evidence, output_path)

    assert digest == evidence.evidence_sha256()
    assert output_path.read_text(encoding="utf-8") == evidence.canonical_json()
    assert load_phosh_physical_candidate_adapter(output_path) == evidence

    with pytest.raises(PhoshPhysicalCandidateAdapterError, match="overwrite"):
        write_phosh_physical_candidate_adapter(evidence, output_path)
