from __future__ import annotations

import json
from pathlib import Path

import pytest

from kaliphonestudio import __version__
from kaliphonestudio.operator_diagnostics import (
    OperatorDiagnosticsError,
    build_diagnostic_report,
    build_operator_bundle,
    build_recovery_guide,
    load_operator_bundle,
    validate_operator_bundle,
    write_operator_bundle,
)
from kaliphonestudio.profiles import get_profile


ROOT = Path(__file__).resolve().parents[1]
DEVICES_ROOT = ROOT / "devices"


def _fake_tools(name: str) -> str | None:
    if name in {"fastboot", "git"}:
        return f"/redacted/tools/{name}"
    return None


def test_offline_doctor_validates_repo_without_device_interaction() -> None:
    report = build_diagnostic_report(
        repo_root=ROOT,
        devices_root=DEVICES_ROOT,
        profile_id="oneplus/avicii",
        executable_finder=_fake_tools,
        version_info=(3, 14, 0),
        platform_name="test-host",
    )
    assert report.application_version == __version__
    assert report.selected_profile_id == "oneplus/avicii"
    assert report.selected_profile_sha256
    assert report.profile_count >= 1
    assert report.offline_review_ready is True
    assert report.failure_count == 0
    assert report.physical_interaction_performed is False
    assert report.hardware_verified is False
    assert report.beta_gate_credit is False
    assert report.beta_gate == "BLOCKED"
    assert report.project_progress_percent == 58
    assert next(tool for tool in report.host_tools if tool.name == "fastboot").available is True
    exported = json.dumps(report.to_dict(), sort_keys=True)
    assert "/redacted/tools" not in exported


def test_missing_fastboot_warns_but_does_not_fake_device_failure() -> None:
    report = build_diagnostic_report(
        repo_root=ROOT,
        devices_root=DEVICES_ROOT,
        executable_finder=lambda _name: None,
        version_info=(3, 13, 1),
        platform_name="test-host",
    )
    fastboot_check = next(item for item in report.checks if item.check_id == "fastboot-host-tool")
    assert fastboot_check.status == "warn"
    assert report.warning_count >= 1
    assert report.offline_review_ready is True
    assert report.physical_interaction_performed is False


def test_outside_ci_python_is_warning_not_hardware_claim() -> None:
    report = build_diagnostic_report(
        repo_root=ROOT,
        devices_root=DEVICES_ROOT,
        executable_finder=_fake_tools,
        version_info=(3, 15, 0),
        platform_name="test-host",
    )
    runtime = next(item for item in report.checks if item.check_id == "python-runtime")
    assert runtime.status == "warn"
    assert report.offline_review_ready is True
    assert report.hardware_verified is False


def test_too_old_python_fails_offline_doctor() -> None:
    report = build_diagnostic_report(
        repo_root=ROOT,
        devices_root=DEVICES_ROOT,
        executable_finder=_fake_tools,
        version_info=(3, 10, 14),
        platform_name="test-host",
    )
    runtime = next(item for item in report.checks if item.check_id == "python-runtime")
    assert runtime.status == "fail"
    assert report.offline_review_ready is False


def test_profile_recovery_guide_is_profile_driven_and_fail_closed() -> None:
    profile = get_profile(DEVICES_ROOT, "oneplus/avicii")
    guide = build_recovery_guide(profile)
    handoff = profile.data["rootfs_handoff"]
    assert guide.profile_id == profile.profile_id
    assert guide.confirmation_token == profile.confirmation_text
    assert guide.ab_device is profile.data["ab_device"]
    assert guide.preferred_boot_mode == "temporary-fastboot-boot"
    assert guide.target_selection_allowed is handoff["target_selection_allowed"]
    assert guide.persistent_write_authorized is False
    assert guide.forbidden_partitions == tuple(handoff["forbidden_partitions"])
    assert guide.required_physical_evidence == tuple(handoff["required_physical_evidence"])
    assert guide.hardware_verified is False
    assert guide.beta_gate_credit is False
    assert any("rollback" in step.lower() for step in guide.steps)


def test_operator_bundle_is_deterministic_redacted_and_round_trips(tmp_path: Path) -> None:
    report = build_diagnostic_report(
        repo_root=ROOT,
        devices_root=DEVICES_ROOT,
        profile_id="oneplus/avicii",
        executable_finder=_fake_tools,
        version_info=(3, 14, 0),
        platform_name="test-host",
    )
    guide = build_recovery_guide(get_profile(DEVICES_ROOT, "oneplus/avicii"))
    bundle = build_operator_bundle(report, guide)
    validate_operator_bundle(bundle)

    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first_digest = write_operator_bundle(first, bundle)
    second_digest = write_operator_bundle(second, bundle)
    assert first.read_bytes() == second.read_bytes()
    assert first_digest == second_digest
    assert b"/redacted/tools" not in first.read_bytes()

    loaded = load_operator_bundle(first)
    assert loaded == bundle
    assert loaded["privacy"]["external_commands_executed"] is False
    assert loaded["privacy"]["device_queried"] is False
    assert loaded["hardware_verified"] is False
    assert loaded["beta_gate_credit"] is False


def test_operator_bundle_rejects_profile_mismatch() -> None:
    report = build_diagnostic_report(
        repo_root=ROOT,
        devices_root=DEVICES_ROOT,
        executable_finder=_fake_tools,
        version_info=(3, 14, 0),
        platform_name="test-host",
    )
    guide = build_recovery_guide(get_profile(DEVICES_ROOT, "oneplus/avicii"))
    with pytest.raises(OperatorDiagnosticsError, match="does not match"):
        build_operator_bundle(report, guide)


def test_operator_bundle_rejects_hardware_or_beta_promotion() -> None:
    report = build_diagnostic_report(
        repo_root=ROOT,
        devices_root=DEVICES_ROOT,
        executable_finder=_fake_tools,
        version_info=(3, 14, 0),
        platform_name="test-host",
    )
    bundle = build_operator_bundle(report)
    promoted = dict(bundle)
    promoted["hardware_verified"] = True
    with pytest.raises(OperatorDiagnosticsError, match="cannot grant"):
        validate_operator_bundle(promoted)


def test_write_refuses_symlink_destination(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    link = tmp_path / "link.json"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable on this test host")
    with pytest.raises(OperatorDiagnosticsError, match="symlink"):
        write_operator_bundle(link, {"schema_version": 1})
