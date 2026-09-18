from __future__ import annotations

from pathlib import Path

import pytest

from kaliphonestudio.physical_boot_observation import (
    PhysicalBootObservationEvidence,
    validate_physical_boot_observation_evidence,
)
from kaliphonestudio.physical_hardware_survey import (
    PhysicalHardwareSurveyError,
    record_physical_hardware_survey,
)
from kaliphonestudio.physical_rescue_diagnostics import (
    PhysicalRescueDiagnosticsError,
    record_physical_rescue_diagnostics,
    require_current_physical_boot_observation_for_rescue,
)
from kaliphonestudio.physical_rescue_functional_probes import (
    PhysicalRescueFunctionalProbeError,
    record_physical_rescue_functional_probes,
)


D = "0" * 64


def _legacy_observation() -> PhysicalBootObservationEvidence:
    return PhysicalBootObservationEvidence(
        schema_version=1,
        profile_id="oneplus/avicii",
        device_serial="LEGACY-SERIAL",
        execution_evidence_sha256=D,
        offer_sha256=D,
        rescue_candidate_evidence_sha256=D,
        rescue_ramdisk_sha256=D,
        rescue_probe_id=D,
        transcript_sha256=D,
        transcript_size=1,
        stage_marker_count=1,
        probe_marker_count=1,
        observation_policy="exact-rescue-probe-console-binding-v1",
        physical_observation_recorded=True,
        temporary_boot_command_succeeded=True,
        rescue_init_observed=True,
        kali_early_userspace_verified=False,
        storage_verified=False,
        display_touch_verified=False,
        charging_battery_verified=False,
        recovery_verified=False,
        manual_review_required=True,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def _current_observation() -> PhysicalBootObservationEvidence:
    return PhysicalBootObservationEvidence(
        schema_version=2,
        profile_id="oneplus/avicii",
        device_serial="CURRENT-SERIAL",
        execution_evidence_sha256=D,
        offer_sha256=D,
        rescue_candidate_evidence_sha256=D,
        rescue_ramdisk_sha256=D,
        rescue_probe_id=D,
        transcript_sha256=D,
        transcript_size=1,
        stage_marker_count=1,
        probe_marker_count=1,
        observation_policy="exact-rescue-probe+runtime-preexec-integrity-binding-v2",
        physical_observation_recorded=True,
        temporary_boot_command_succeeded=True,
        rescue_init_observed=True,
        kali_early_userspace_verified=False,
        storage_verified=False,
        display_touch_verified=False,
        charging_battery_verified=False,
        recovery_verified=False,
        manual_review_required=True,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
        runtime_probe_evidence_sha256=D,
        authorization_sha256=D,
        physical_baseline_bundle_sha256=D,
        boot_identity_binding_sha256=D,
        recovery_readiness_sha256=D,
        recovery_stock_boot_sha256=D,
        fresh_fastboot_transcript_sha256=D,
        captured_active_slot="a",
        expected_inactive_slot="b",
        post_probe_material_revalidation_required=True,
    )


def test_legacy_observation_remains_readable_for_historical_audit() -> None:
    legacy = _legacy_observation()
    validate_physical_boot_observation_evidence(legacy)


def test_legacy_observation_cannot_seed_new_rescue_evidence() -> None:
    legacy = _legacy_observation()
    with pytest.raises(PhysicalRescueDiagnosticsError, match="requires schema-v2 physical boot observation"):
        require_current_physical_boot_observation_for_rescue(legacy)


def test_recording_rejects_legacy_before_profile_or_transcript_access(tmp_path: Path) -> None:
    legacy = _legacy_observation()
    missing = tmp_path / "must-not-be-read.log"
    with pytest.raises(PhysicalRescueDiagnosticsError, match="requires schema-v2 physical boot observation"):
        record_physical_rescue_diagnostics(None, legacy, missing)  # type: ignore[arg-type]
    assert not missing.exists()


def test_functional_probe_recording_rejects_legacy_before_diagnostics_or_transcript_access(
    tmp_path: Path,
) -> None:
    legacy = _legacy_observation()
    missing = tmp_path / "functional-probe-must-not-be-read.log"
    with pytest.raises(
        PhysicalRescueFunctionalProbeError,
        match="requires schema-v2 physical boot observation",
    ):
        record_physical_rescue_functional_probes(
            None,  # type: ignore[arg-type]
            legacy,
            None,  # type: ignore[arg-type]
            missing,
        )
    assert not missing.exists()


def test_hardware_survey_recording_rejects_legacy_before_diagnostics_or_transcript_access(
    tmp_path: Path,
) -> None:
    legacy = _legacy_observation()
    missing = tmp_path / "hardware-survey-must-not-be-read.log"
    with pytest.raises(
        PhysicalHardwareSurveyError,
        match="requires schema-v2 physical boot observation",
    ):
        record_physical_hardware_survey(
            None,  # type: ignore[arg-type]
            legacy,
            None,  # type: ignore[arg-type]
            missing,
        )
    assert not missing.exists()


def test_current_observation_passes_campaign_admission_gate() -> None:
    current = _current_observation()
    validate_physical_boot_observation_evidence(current)
    require_current_physical_boot_observation_for_rescue(current)
