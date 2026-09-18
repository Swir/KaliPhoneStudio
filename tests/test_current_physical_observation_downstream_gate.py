from __future__ import annotations

from pathlib import Path

import pytest

from kaliphonestudio.physical_boot_observation import PhysicalBootObservationEvidence
from kaliphonestudio.physical_bringup_session import (
    PhysicalBringupSessionError,
    bind_physical_bringup_session,
)
from kaliphonestudio.physical_campaign_admission import (
    PhysicalCampaignAdmissionError,
    require_current_physical_campaign_observation,
)
from kaliphonestudio.physical_hardware_review import (
    PhysicalHardwareReviewError,
    review_current_physical_hardware_survey_files,
)
from kaliphonestudio.physical_hardware_test_plan import (
    PhysicalHardwareTestPlanError,
    build_current_physical_hardware_test_plan_from_files,
)
from kaliphonestudio.physical_hardware_test_plan_review import (
    PhysicalHardwareTestPlanReviewError,
    bind_current_physical_hardware_test_plan_review_from_files,
)
from kaliphonestudio.physical_hardware_test_observation import (
    PhysicalHardwareTestObservationError,
    bind_current_physical_hardware_test_observation_from_files,
    make_current_inconclusive_physical_hardware_test_observation_record,
)
from kaliphonestudio.physical_storage_discovery import (
    PhysicalStorageDiscoveryError,
    record_current_physical_storage_discovery,
)


D = "0" * 64


def _legacy() -> PhysicalBootObservationEvidence:
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


def _current() -> PhysicalBootObservationEvidence:
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


def test_current_campaign_helper_rejects_legacy_but_accepts_current() -> None:
    with pytest.raises(PhysicalCampaignAdmissionError, match="requires schema-v2"):
        require_current_physical_campaign_observation(_legacy())
    binding = require_current_physical_campaign_observation(_current())
    assert binding.profile_id == "oneplus/avicii"
    assert binding.device_serial == "CURRENT-SERIAL"
    assert binding.physical_boot_observation_sha256 == _current().evidence_sha256()


def test_hardware_review_rejects_legacy_before_reading_review_files(tmp_path: Path) -> None:
    missing = tmp_path / "must-not-be-read.json"
    with pytest.raises(PhysicalHardwareReviewError, match="requires schema-v2"):
        review_current_physical_hardware_survey_files(
            _legacy(), missing, missing, missing
        )
    assert not missing.exists()


def test_test_plan_rejects_legacy_before_reading_review_file(tmp_path: Path) -> None:
    missing = tmp_path / "must-not-be-read.json"
    with pytest.raises(PhysicalHardwareTestPlanError, match="requires schema-v2"):
        build_current_physical_hardware_test_plan_from_files(
            None,  # type: ignore[arg-type]
            _legacy(),
            missing,
        )
    assert not missing.exists()


def test_plan_review_rejects_legacy_before_reading_plan_or_review_files(tmp_path: Path) -> None:
    missing = tmp_path / "must-not-be-read.json"
    with pytest.raises(PhysicalHardwareTestPlanReviewError, match="requires schema-v2"):
        bind_current_physical_hardware_test_plan_review_from_files(
            _legacy(), missing, missing, missing
        )
    assert not missing.exists()


def test_observation_template_rejects_legacy_before_plan_validation() -> None:
    with pytest.raises(PhysicalHardwareTestObservationError, match="requires schema-v2"):
        make_current_inconclusive_physical_hardware_test_observation_record(
            _legacy(),
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            "display",
            "operator-ci",
        )


def test_observation_binding_rejects_legacy_before_reading_campaign_files(tmp_path: Path) -> None:
    missing = tmp_path / "must-not-be-read.json"
    with pytest.raises(PhysicalHardwareTestObservationError, match="requires schema-v2"):
        bind_current_physical_hardware_test_observation_from_files(
            _legacy(), missing, missing, "display", missing, missing
        )
    assert not missing.exists()


def test_storage_discovery_rejects_legacy_before_reading_operator_reports(tmp_path: Path) -> None:
    missing = tmp_path / "must-not-be-read.json"
    with pytest.raises(PhysicalStorageDiscoveryError, match="requires schema-v2"):
        record_current_physical_storage_discovery(
            None,  # type: ignore[arg-type]
            _legacy(),
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            missing,
            missing,
        )
    assert not missing.exists()


def test_bringup_session_rejects_legacy_before_candidate_or_downstream_validation() -> None:
    with pytest.raises(PhysicalBringupSessionError, match="requires schema-v2"):
        bind_physical_bringup_session(
            None,  # type: ignore[arg-type]
            _legacy(),
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
        )


def test_current_helper_detects_downstream_identity_drift() -> None:
    current = _current()
    with pytest.raises(PhysicalCampaignAdmissionError, match="device serial is detached"):
        require_current_physical_campaign_observation(
            current,
            expected_device_serial="OTHER",
        )
    with pytest.raises(PhysicalCampaignAdmissionError, match="rescue transcript is detached"):
        require_current_physical_campaign_observation(
            current,
            expected_transcript_sha256="1" * 64,
        )
