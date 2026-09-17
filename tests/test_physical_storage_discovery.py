from dataclasses import replace
from hashlib import sha256
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
from kaliphonestudio.physical_storage_discovery import (
    PhysicalStorageDiscoveryError,
    bind_physical_storage_discovery,
    load_physical_storage_discovery_evidence,
    load_physical_storage_discovery_report,
    parse_physical_storage_discovery_report,
    record_physical_storage_discovery,
    validate_physical_storage_discovery_evidence,
    write_physical_storage_discovery_evidence,
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


def _diagnostics() -> PhysicalRescueDiagnosticsEvidence:
    records = (
        RescueDiagnosticRecord("BLOCK", ("sda", "1000000", "0")),
        RescueDiagnosticRecord("SCSI_HOST", ("host0", "ufshcd")),
    )
    return PhysicalRescueDiagnosticsEvidence(
        schema_version=1,
        profile_id="oneplus/avicii",
        device_serial="SERIAL123",
        physical_boot_observation_sha256=S,
        transcript_sha256=T,
        rescue_probe_id=P,
        diagnostics_policy="readonly-sysfs-inventory-v1",
        normalized_diagnostics_sha256=diagnostics_digest(records),
        diagnostic_record_count=2,
        block_record_count=1,
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


def _report_dict() -> dict:
    return {
        "schema_version": 1,
        "profile_id": "oneplus/avicii",
        "device_serial": "SERIAL123",
        "collection_policy": "operator-read-only-storage-discovery-v1",
        "block_devices": [
            {"kernel_name": "sda", "size_sectors": 1000000, "removable": False}
        ],
        "filesystems": [
            {"partition_role": "userdata", "kernel_name": "sda18", "filesystem": "f2fs", "observed": True}
        ],
        "encryption": [
            {
                "partition_role": "userdata",
                "state": "encrypted",
                "features": ["fileencryption=ice", "wrappedkey"],
                "observed": True,
            }
        ],
        "free_space": [
            {"partition_role": "userdata", "total_bytes": 200000000000, "free_bytes": 150000000000, "observed": True}
        ],
        "phone_storage_written": False,
        "target_selected": False,
        "storage_path_bound": False,
    }


def _bind(report_dict: dict | None = None):
    profile = _profile()
    assessment = _assessment(profile)
    diag = _diagnostics()
    functional = _functional(diag)
    report = parse_physical_storage_discovery_report(_report_dict() if report_dict is None else report_dict)
    return bind_physical_storage_discovery(
        profile,
        assessment,
        diag,
        functional,
        report,
        discovery_report_sha256="ef" * 32,
        discovery_report_size=1234,
        recovery_plan_sha256="34" * 32,
        recovery_plan_size=512,
    )


def test_complete_observations_become_review_ready_but_never_a_target_or_hardware_pass():
    evidence = _bind()
    assert evidence.topology_bound_to_rescue_diagnostics is True
    assert evidence.storage_bus_signal_observed is True
    assert evidence.expected_filesystem_observed is True
    assert evidence.expected_encryption_features_observed is True
    assert evidence.free_space_observed is True
    assert evidence.all_required_categories_recorded is True
    assert evidence.discovery_ready_for_manual_review is True
    assert evidence.target_selected is False
    assert evidence.storage_path_bound is False
    assert evidence.write_authorized is False
    assert evidence.handoff_ready is False
    assert evidence.storage_verified is False
    assert evidence.recovery_verified is False
    assert evidence.phone_storage_written is False
    assert evidence.manual_review_required is True
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False


def test_topology_must_match_exact_rescue_sysfs_observation():
    raw = _report_dict()
    raw["block_devices"][0]["size_sectors"] += 1
    evidence = _bind(raw)
    assert evidence.topology_bound_to_rescue_diagnostics is False
    assert evidence.all_required_categories_recorded is False
    assert evidence.discovery_ready_for_manual_review is False


def test_expected_filesystem_and_encryption_are_checked_without_authorizing_userdata():
    raw = _report_dict()
    raw["filesystems"][0]["filesystem"] = "ext4"
    evidence = _bind(raw)
    assert evidence.filesystem_identity_observed is True
    assert evidence.expected_filesystem_observed is False
    assert evidence.discovery_ready_for_manual_review is False
    assert "metadata" in evidence.forbidden_partitions
    assert "super" in evidence.forbidden_partitions
    assert evidence.target_selected is False


def test_report_rejects_device_paths_write_claims_duplicates_and_inconsistent_unknowns():
    raw = _report_dict()
    raw["filesystems"][0]["kernel_name"] = "/dev/block/sda18"
    with pytest.raises(PhysicalStorageDiscoveryError, match="safe kernel/name"):
        parse_physical_storage_discovery_report(raw)

    raw = _report_dict()
    raw["phone_storage_written"] = True
    with pytest.raises(PhysicalStorageDiscoveryError, match="requires phone_storage_written=false"):
        parse_physical_storage_discovery_report(raw)

    raw = _report_dict()
    raw["filesystems"].append(dict(raw["filesystems"][0]))
    with pytest.raises(PhysicalStorageDiscoveryError, match="unique partition roles"):
        parse_physical_storage_discovery_report(raw)

    raw = _report_dict()
    raw["filesystems"][0]["observed"] = False
    with pytest.raises(PhysicalStorageDiscoveryError, match="filesystem=unknown"):
        parse_physical_storage_discovery_report(raw)


def test_binding_rejects_serial_and_rescue_chain_drift():
    raw = _report_dict()
    raw["device_serial"] = "OTHER"
    with pytest.raises(PhysicalStorageDiscoveryError, match="serial mismatch"):
        _bind(raw)

    profile = _profile()
    assessment = _assessment(profile)
    diag = _diagnostics()
    functional = replace(_functional(diag), rescue_diagnostics_sha256="56" * 32)
    report = parse_physical_storage_discovery_report(_report_dict())
    with pytest.raises(PhysicalStorageDiscoveryError, match="detached"):
        bind_physical_storage_discovery(
            profile,
            assessment,
            diag,
            functional,
            report,
            discovery_report_sha256="ef" * 32,
            discovery_report_size=100,
            recovery_plan_sha256="34" * 32,
            recovery_plan_size=100,
        )


def test_evidence_validator_rejects_promotion_to_handoff_or_beta():
    evidence = _bind()
    with pytest.raises(PhysicalStorageDiscoveryError, match="unsupported target/write/hardware claim"):
        validate_physical_storage_discovery_evidence(replace(evidence, handoff_ready=True))
    with pytest.raises(PhysicalStorageDiscoveryError, match="unsupported target/write/hardware claim"):
        validate_physical_storage_discovery_evidence(replace(evidence, beta_gate_credit=True))


def test_exact_report_bytes_and_recovery_plan_are_bound_and_output_is_immutable(tmp_path: Path):
    profile = _profile()
    assessment = _assessment(profile)
    diag = _diagnostics()
    functional = _functional(diag)
    report_path = tmp_path / "storage-report.json"
    raw = json.dumps(_report_dict(), indent=2, sort_keys=True).encode("utf-8") + b"\n"
    report_path.write_bytes(raw)
    recovery = tmp_path / "recovery-plan.txt"
    recovery_bytes = b"Recovery: exact OxygenOS package + documented rollback procedure.\n"
    recovery.write_bytes(recovery_bytes)

    evidence = record_physical_storage_discovery(
        profile, assessment, diag, functional, report_path, recovery
    )
    assert evidence.discovery_report_sha256 == sha256(raw).hexdigest()
    assert evidence.discovery_report_size == len(raw)
    assert evidence.recovery_plan_sha256 == sha256(recovery_bytes).hexdigest()
    assert evidence.recovery_plan_size == len(recovery_bytes)

    destination = tmp_path / "physical-storage-discovery.json"
    digest = write_physical_storage_discovery_evidence(evidence, destination)
    assert digest == evidence.evidence_sha256()
    loaded = load_physical_storage_discovery_evidence(destination)
    assert loaded == evidence
    with pytest.raises(PhysicalStorageDiscoveryError, match="overwrite"):
        write_physical_storage_discovery_evidence(evidence, destination)


def test_report_loader_rejects_symlink_and_preserves_exact_file_digest(tmp_path: Path):
    report = tmp_path / "report.json"
    raw = json.dumps(_report_dict(), separators=(",", ":")).encode() + b"\n"
    report.write_bytes(raw)
    loaded, digest, size = load_physical_storage_discovery_report(report)
    assert loaded.profile_id == "oneplus/avicii"
    assert digest == sha256(raw).hexdigest()
    assert size == len(raw)
    link = tmp_path / "report-link.json"
    link.symlink_to(report)
    with pytest.raises(PhysicalStorageDiscoveryError, match="non-symlink"):
        load_physical_storage_discovery_report(link)
