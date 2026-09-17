from dataclasses import replace
import json
from pathlib import Path

import pytest

from kaliphonestudio.physical_rescue_diagnostics import (
    PhysicalRescueDiagnosticsEvidence,
    RescueDiagnosticRecord,
    _normalized_digest as diagnostics_digest,
)
from kaliphonestudio.physical_rescue_functional_probes import (
    FunctionalProbeRecord,
    PhysicalRescueFunctionalProbeEvidence,
    _normalized_digest as functional_digest,
)
from kaliphonestudio.physical_storage_template import (
    PhysicalStorageTemplateError,
    create_physical_storage_discovery_template,
    write_physical_storage_discovery_template,
)
from kaliphonestudio.profiles import DeviceProfile
from kaliphonestudio.rootfs_handoff import RootfsHandoffAssessmentEvidence, rootfs_handoff_contract

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "devices" / "oneplus" / "avicii" / "profile.json"
S = "ab" * 32
T = "cd" * 32
P = "12" * 32


def _profile() -> DeviceProfile:
    return DeviceProfile(path=PROFILE_PATH, data=json.loads(PROFILE_PATH.read_text(encoding="utf-8")))


def _assessment(profile: DeviceProfile) -> RootfsHandoffAssessmentEvidence:
    contract = rootfs_handoff_contract(profile)
    return RootfsHandoffAssessmentEvidence(
        schema_version=1,
        profile_id=profile.profile_id,
        device_serial="SERIAL123",
        firmware_build="AC2003_11.F.17",
        firmware_fingerprint="OnePlus/avicii/avicii:12/RKQ1/build:user/release-keys",
        physical_candidate_gate_sha256=S,
        rootfs_handoff_contract_sha256=contract.contract_sha256(),
        rootfs_authority_sha256=T,
        rootfs_artifact_sha256="13" * 32,
        rootfs_artifact_size=137460600,
        layout_source_name=contract.layout_source_name,
        layout_source_commit=contract.layout_source_commit,
        layout_source_path=contract.layout_source_path,
        layout_source_blob_sha1=contract.layout_source_blob_sha1,
        storage_bus=contract.storage_bus,
        partition_hint=contract.partition_hint,
        expected_filesystems=contract.expected_filesystems,
        encryption_features=contract.encryption_features,
        metadata_partition=contract.metadata_partition,
        required_physical_evidence=contract.required_physical_evidence,
        forbidden_partitions=contract.forbidden_partitions,
        target_selected=False,
        storage_path_bound=False,
        write_authorized=False,
        handoff_ready=False,
        manual_review_required=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def _diagnostics(*, include_block: bool = True) -> PhysicalRescueDiagnosticsEvidence:
    records = []
    if include_block:
        records.append(RescueDiagnosticRecord("BLOCK", ("sda", "1000000", "0")))
    records.append(RescueDiagnosticRecord("SCSI_HOST", ("host0", "ufshcd")))
    records = tuple(records)
    return PhysicalRescueDiagnosticsEvidence(
        schema_version=1,
        profile_id="oneplus/avicii",
        device_serial="SERIAL123",
        physical_boot_observation_sha256=S,
        transcript_sha256=T,
        rescue_probe_id=P,
        diagnostics_policy="readonly-sysfs-inventory-v1",
        normalized_diagnostics_sha256=diagnostics_digest(records),
        diagnostic_record_count=len(records),
        block_record_count=sum(x.kind == "BLOCK" for x in records),
        scsi_host_record_count=1,
        power_record_count=0,
        input_record_count=0,
        graphics_record_count=0,
        drm_record_count=0,
        ufs_signal_observed=True,
        battery_signal_observed=False,
        input_signal_observed=False,
        graphics_signal_observed=False,
        records=records,
        physical_diagnostics_recorded=True,
        manual_review_required=True,
        storage_verified=False,
        display_touch_verified=False,
        charging_battery_verified=False,
        recovery_verified=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def _functional(diag: PhysicalRescueDiagnosticsEvidence) -> PhysicalRescueFunctionalProbeEvidence:
    records = (FunctionalProbeRecord("BLOCK_READ", ("sda", "4096", "ok")),)
    return PhysicalRescueFunctionalProbeEvidence(
        schema_version=1,
        profile_id="oneplus/avicii",
        device_serial="SERIAL123",
        physical_boot_observation_sha256=S,
        rescue_diagnostics_sha256=diag.evidence_sha256(),
        transcript_sha256=T,
        rescue_probe_id=P,
        probe_policy="readonly-functional-probes-v1",
        normalized_probe_sha256=functional_digest(records),
        probe_record_count=1,
        block_read_record_count=1,
        block_read_success_count=1,
        block_read_failure_count=0,
        block_read_missing_count=0,
        battery_sample_count=0,
        battery_pair_count=0,
        storage_read_signal_observed=True,
        battery_sampling_signal_observed=False,
        records=records,
        explicit_local_authorization_required=True,
        physical_functional_probe_recorded=True,
        manual_review_required=True,
        storage_verified=False,
        display_touch_verified=False,
        charging_battery_verified=False,
        recovery_verified=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def test_template_prefills_only_bound_topology_and_keeps_sensitive_observations_unknown():
    profile = _profile()
    assessment = _assessment(profile)
    diag = _diagnostics()
    report = create_physical_storage_discovery_template(profile, assessment, diag, _functional(diag))
    assert [(x.kernel_name, x.size_sectors, x.removable) for x in report.block_devices] == [("sda", 1000000, False)]
    assert report.filesystems[0].partition_role == "userdata"
    assert report.filesystems[0].kernel_name == "unknown"
    assert report.filesystems[0].filesystem == "unknown"
    assert report.filesystems[0].observed is False
    assert report.encryption[0].state == "unknown"
    assert report.encryption[0].features == ()
    assert report.encryption[0].observed is False
    assert report.free_space[0].total_bytes is None
    assert report.free_space[0].free_bytes is None
    assert report.free_space[0].observed is False
    assert report.phone_storage_written is False
    assert report.target_selected is False
    assert report.storage_path_bound is False
    assert "/dev/" not in report.canonical_json()


def test_template_refuses_detached_probe_chain_and_prior_write_claim():
    profile = _profile()
    assessment = _assessment(profile)
    diag = _diagnostics()
    detached = replace(_functional(diag), rescue_diagnostics_sha256="56" * 32)
    with pytest.raises(PhysicalStorageTemplateError, match="detached"):
        create_physical_storage_discovery_template(profile, assessment, diag, detached)

    written = replace(diag, phone_storage_written=True)
    with pytest.raises(PhysicalStorageTemplateError):
        create_physical_storage_discovery_template(profile, assessment, written, _functional(diag))


def test_template_requires_usable_whole_block_topology():
    profile = _profile()
    assessment = _assessment(profile)
    diag = _diagnostics(include_block=False)
    functional = _functional(diag)
    with pytest.raises(PhysicalStorageTemplateError, match="no usable whole-block topology"):
        create_physical_storage_discovery_template(profile, assessment, diag, functional)


def test_template_writer_is_immutable_and_digest_is_canonical(tmp_path: Path):
    profile = _profile()
    assessment = _assessment(profile)
    diag = _diagnostics()
    report = create_physical_storage_discovery_template(profile, assessment, diag, _functional(diag))
    destination = tmp_path / "storage-discovery-template.json"
    digest = write_physical_storage_discovery_template(report, destination)
    assert digest == report.report_sha256()
    assert destination.read_text(encoding="utf-8") == report.canonical_json()
    with pytest.raises(PhysicalStorageTemplateError, match="overwrite"):
        write_physical_storage_discovery_template(report, destination)
