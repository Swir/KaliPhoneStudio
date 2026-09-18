"""Current physical-observation admission rules for new downstream campaign artifacts.

Historical physical boot observations remain readable for audit.  New campaign
artifacts must be rooted in the current schema-v2 observation, which carries the
exact runtime-probe, physical-baseline, boot-identity, recovery-readiness and
post-probe material-revalidation chain.

This module is deliberately offline and non-operational.  It performs no phone
I/O, does not choose storage, cannot authorize a write and grants no hardware or
Beta credit.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .physical_boot_observation import PhysicalBootObservationEvidence
from .physical_rescue_diagnostics import (
    PhysicalRescueDiagnosticsError,
    load_physical_boot_observation_for_diagnostics,
    require_current_physical_boot_observation_for_rescue,
)


class PhysicalCampaignAdmissionError(ValueError):
    pass


@dataclass(frozen=True)
class CurrentPhysicalObservationBinding:
    profile_id: str
    device_serial: str
    physical_boot_observation_sha256: str
    transcript_sha256: str
    rescue_probe_id: str
    runtime_probe_evidence_sha256: str
    physical_baseline_bundle_sha256: str
    boot_identity_binding_sha256: str
    recovery_readiness_sha256: str
    recovery_stock_boot_sha256: str
    fresh_fastboot_transcript_sha256: str


def require_current_physical_campaign_observation(
    observation: PhysicalBootObservationEvidence,
    *,
    expected_profile_id: str | None = None,
    expected_device_serial: str | None = None,
    expected_observation_sha256: str | None = None,
    expected_transcript_sha256: str | None = None,
    expected_rescue_probe_id: str | None = None,
) -> CurrentPhysicalObservationBinding:
    """Require current schema-v2 physical provenance and optional exact bindings."""
    try:
        require_current_physical_boot_observation_for_rescue(observation)
    except PhysicalRescueDiagnosticsError as exc:
        raise PhysicalCampaignAdmissionError(str(exc)) from exc

    observation_sha = observation.evidence_sha256()
    checks = (
        (expected_profile_id, observation.profile_id, "profile"),
        (expected_device_serial, observation.device_serial, "device serial"),
        (expected_observation_sha256, observation_sha, "physical boot observation"),
        (expected_transcript_sha256, observation.transcript_sha256, "rescue transcript"),
        (expected_rescue_probe_id, observation.rescue_probe_id, "rescue probe id"),
    )
    for expected, actual, label in checks:
        if expected is not None and expected != actual:
            raise PhysicalCampaignAdmissionError(
                f"downstream physical campaign {label} is detached from the current physical boot observation"
            )

    required = (
        ("runtime probe evidence", observation.runtime_probe_evidence_sha256),
        ("physical baseline bundle", observation.physical_baseline_bundle_sha256),
        ("boot identity binding", observation.boot_identity_binding_sha256),
        ("recovery readiness", observation.recovery_readiness_sha256),
        ("recovery stock boot", observation.recovery_stock_boot_sha256),
        ("fresh Fastboot transcript", observation.fresh_fastboot_transcript_sha256),
    )
    for label, value in required:
        if not isinstance(value, str) or len(value) != 64:
            raise PhysicalCampaignAdmissionError(
                f"current physical boot observation is missing exact {label} identity"
            )

    return CurrentPhysicalObservationBinding(
        profile_id=observation.profile_id,
        device_serial=observation.device_serial,
        physical_boot_observation_sha256=observation_sha,
        transcript_sha256=observation.transcript_sha256,
        rescue_probe_id=observation.rescue_probe_id,
        runtime_probe_evidence_sha256=observation.runtime_probe_evidence_sha256,
        physical_baseline_bundle_sha256=observation.physical_baseline_bundle_sha256,
        boot_identity_binding_sha256=observation.boot_identity_binding_sha256,
        recovery_readiness_sha256=observation.recovery_readiness_sha256,
        recovery_stock_boot_sha256=observation.recovery_stock_boot_sha256,
        fresh_fastboot_transcript_sha256=observation.fresh_fastboot_transcript_sha256,
    )


def load_current_physical_campaign_observation(path: Path) -> PhysicalBootObservationEvidence:
    """Load an observation and reject historical schemas for new campaign creation."""
    try:
        observation = load_physical_boot_observation_for_diagnostics(Path(path))
    except PhysicalRescueDiagnosticsError as exc:
        raise PhysicalCampaignAdmissionError(str(exc)) from exc
    require_current_physical_campaign_observation(observation)
    return observation
