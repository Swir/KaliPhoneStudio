"""Create an operator-editable storage-discovery template from exact rescue evidence.

The template is deliberately incomplete: whole-block topology is prefilled from
already-bound read-only rescue diagnostics, while filesystem/encryption/free-space
fields remain explicitly unknown for the profile's partition role.  It contains no
device path, target choice, mount target, or write authorization.
"""
from __future__ import annotations

from pathlib import Path
import json

from .physical_rescue_diagnostics import (
    PhysicalRescueDiagnosticsEvidence,
    PhysicalRescueDiagnosticsError,
    validate_physical_rescue_diagnostics_evidence,
)
from .physical_rescue_functional_probes import (
    PhysicalRescueFunctionalProbeEvidence,
    PhysicalRescueFunctionalProbeError,
    validate_physical_rescue_functional_probe_evidence,
)
from .physical_storage_discovery import (
    PhysicalStorageDiscoveryReport,
    StorageBlockObservation,
    StorageEncryptionObservation,
    StorageFilesystemObservation,
    StorageFreeSpaceObservation,
    PhysicalStorageDiscoveryError,
    parse_physical_storage_discovery_report,
)
from .profiles import DeviceProfile
from .rootfs_handoff import RootfsHandoffAssessmentEvidence, rootfs_handoff_contract


class PhysicalStorageTemplateError(ValueError):
    pass


def create_physical_storage_discovery_template(
    profile: DeviceProfile,
    assessment: RootfsHandoffAssessmentEvidence,
    diagnostics: PhysicalRescueDiagnosticsEvidence,
    functional_probe: PhysicalRescueFunctionalProbeEvidence,
) -> PhysicalStorageDiscoveryReport:
    """Create a no-write template bound to the exact already-captured rescue chain."""
    if not isinstance(profile, DeviceProfile):
        raise PhysicalStorageTemplateError("profile must be typed DeviceProfile data")
    if not isinstance(assessment, RootfsHandoffAssessmentEvidence) or assessment.schema_version != 1:
        raise PhysicalStorageTemplateError("rootfs handoff assessment must be schema-v1 typed evidence")
    contract = rootfs_handoff_contract(profile)
    if assessment.profile_id != profile.profile_id:
        raise PhysicalStorageTemplateError("rootfs handoff assessment profile mismatch")
    if assessment.rootfs_handoff_contract_sha256 != contract.contract_sha256():
        raise PhysicalStorageTemplateError("rootfs handoff assessment is detached from current profile contract")
    if (
        assessment.target_selected
        or assessment.storage_path_bound
        or assessment.write_authorized
        or assessment.handoff_ready
        or assessment.hardware_verified
        or assessment.beta_gate_credit
        or assessment.manual_review_required is not True
    ):
        raise PhysicalStorageTemplateError("rootfs handoff assessment is not discovery-only")
    try:
        validate_physical_rescue_diagnostics_evidence(diagnostics)
    except PhysicalRescueDiagnosticsError as exc:
        raise PhysicalStorageTemplateError(str(exc)) from exc
    try:
        validate_physical_rescue_functional_probe_evidence(functional_probe)
    except PhysicalRescueFunctionalProbeError as exc:
        raise PhysicalStorageTemplateError(str(exc)) from exc
    if diagnostics.profile_id != profile.profile_id or diagnostics.device_serial != assessment.device_serial:
        raise PhysicalStorageTemplateError("rescue diagnostics do not match the handoff assessment")
    if functional_probe.profile_id != profile.profile_id or functional_probe.device_serial != assessment.device_serial:
        raise PhysicalStorageTemplateError("functional probe does not match the handoff assessment")
    if functional_probe.rescue_diagnostics_sha256 != diagnostics.evidence_sha256():
        raise PhysicalStorageTemplateError("functional probe is detached from rescue diagnostics")
    if (
        functional_probe.transcript_sha256 != diagnostics.transcript_sha256
        or functional_probe.rescue_probe_id != diagnostics.rescue_probe_id
    ):
        raise PhysicalStorageTemplateError("rescue transcript/probe identity drifted")
    if diagnostics.phone_storage_written or functional_probe.phone_storage_written:
        raise PhysicalStorageTemplateError("template creation requires a no-write rescue evidence chain")

    blocks: list[StorageBlockObservation] = []
    seen: set[str] = set()
    for record in diagnostics.records:
        if record.kind != "BLOCK":
            continue
        name, sectors, removable = record.values
        if not sectors.isdigit() or int(sectors) <= 0 or removable not in {"0", "1"}:
            continue
        if name in seen:
            raise PhysicalStorageTemplateError("rescue diagnostics contain duplicate block names")
        seen.add(name)
        blocks.append(StorageBlockObservation(name, int(sectors), removable == "1"))
    blocks.sort(key=lambda item: item.kernel_name)
    if not blocks:
        raise PhysicalStorageTemplateError("rescue diagnostics contain no usable whole-block topology")

    report = PhysicalStorageDiscoveryReport(
        schema_version=1,
        profile_id=profile.profile_id,
        device_serial=assessment.device_serial,
        collection_policy="operator-read-only-storage-discovery-v1",
        block_devices=tuple(blocks),
        filesystems=(
            StorageFilesystemObservation(
                partition_role=contract.partition_hint,
                kernel_name="unknown",
                filesystem="unknown",
                observed=False,
            ),
        ),
        encryption=(
            StorageEncryptionObservation(
                partition_role=contract.partition_hint,
                state="unknown",
                features=(),
                observed=False,
            ),
        ),
        free_space=(
            StorageFreeSpaceObservation(
                partition_role=contract.partition_hint,
                total_bytes=None,
                free_bytes=None,
                observed=False,
            ),
        ),
        phone_storage_written=False,
        target_selected=False,
        storage_path_bound=False,
    )
    try:
        parsed = parse_physical_storage_discovery_report(json.loads(report.canonical_json()))
    except (PhysicalStorageDiscoveryError, json.JSONDecodeError) as exc:
        raise PhysicalStorageTemplateError("generated physical storage template failed strict validation") from exc
    if parsed != report:
        raise PhysicalStorageTemplateError("generated physical storage template canonicalization drifted")
    return report


def _validated_payload(report: PhysicalStorageDiscoveryReport) -> str:
    if not isinstance(report, PhysicalStorageDiscoveryReport):
        raise PhysicalStorageTemplateError("physical storage discovery template must be typed report data")
    try:
        payload = report.canonical_json()
        parsed = parse_physical_storage_discovery_report(json.loads(payload))
    except (PhysicalStorageDiscoveryError, json.JSONDecodeError, TypeError) as exc:
        raise PhysicalStorageTemplateError("physical storage discovery template failed strict validation") from exc
    if parsed != report:
        raise PhysicalStorageTemplateError("physical storage discovery template canonicalization drifted")
    return payload


def write_physical_storage_discovery_template(
    report: PhysicalStorageDiscoveryReport,
    destination: Path,
) -> str:
    payload = _validated_payload(report)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise PhysicalStorageTemplateError("refusing to overwrite physical storage discovery template")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise PhysicalStorageTemplateError("refusing stale physical storage discovery template temporary path")
    try:
        temporary.write_text(payload, encoding="utf-8", newline="\n")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return report.report_sha256()
