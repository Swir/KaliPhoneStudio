from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from kaliphonestudio.profile_hooks import (
    HookResult,
    ProfileHookError,
    ProfileHookRegistry,
    declared_profile_hooks,
    execute_profile_hooks,
    validate_profile_hooks_contract,
)
from kaliphonestudio.profiles import DeviceProfile, ProfileError, get_profile


ROOT = Path(__file__).resolve().parents[1]
DEVICES_ROOT = ROOT / "devices"


def _profile_with_hooks(tmp_path: Path, hooks: dict[str, list[str]]) -> DeviceProfile:
    base = get_profile(DEVICES_ROOT, "oneplus/avicii")
    data = dict(base.data)
    data["hooks"] = hooks
    return DeviceProfile(path=tmp_path / "profile.json", data=data)


def test_optional_hooks_contract_accepts_missing_or_ordered_safe_ids() -> None:
    validate_profile_hooks_contract(None)
    validate_profile_hooks_contract(
        {
            "build": ["vendor/prepare-kernel", "common/post-build"],
            "verify": ["common/verify-image"],
            "recovery": [],
        }
    )


def test_hooks_contract_rejects_unknown_stage_duplicates_and_unsafe_ids() -> None:
    with pytest.raises(ProfileError):
        validate_profile_hooks_contract({"flash": ["x"]})
    with pytest.raises(ProfileError):
        validate_profile_hooks_contract({"build": ["common/x", "common/x"]})
    with pytest.raises(ProfileError):
        validate_profile_hooks_contract({"build": ["../../evil"]})


def test_undeclared_profile_has_no_hooks() -> None:
    profile = get_profile(DEVICES_ROOT, "oneplus/avicii")
    assert declared_profile_hooks(profile, "build") == ()
    assert declared_profile_hooks(profile, "verify") == ()


def test_build_hooks_execute_in_declared_order_and_emit_non_beta_evidence(tmp_path: Path) -> None:
    profile = _profile_with_hooks(tmp_path, {"build": ["common/first", "common/second"]})
    registry = ProfileHookRegistry()
    calls: list[str] = []

    def first(ctx):
        calls.append("first")
        assert ctx.profile_id == "oneplus/avicii"
        assert ctx.stage == "build"
        assert ctx.metadata["candidate"] == "offline"
        return HookResult("common/first", "build", True, "first ok", {"step": 1})

    def second(ctx):
        calls.append("second")
        return HookResult("common/second", "build", True, "second ok", {"step": 2})

    registry.register("common/first", "build", first)
    registry.register("common/second", "build", second)
    results, evidence = execute_profile_hooks(
        profile,
        "build",
        registry,
        workspace=tmp_path,
        metadata={"candidate": "offline"},
    )

    assert calls == ["first", "second"]
    assert [item.hook_id for item in results] == ["common/first", "common/second"]
    assert evidence.declared_hook_ids == ("common/first", "common/second")
    assert len(evidence.result_digests) == 2
    assert evidence.all_ok is True
    assert evidence.beta_gate_credit is False
    assert evidence.hardware_verified is False
    assert len(evidence.evidence_sha256()) == 64


def test_unregistered_or_wrong_stage_hook_fails_closed(tmp_path: Path) -> None:
    profile = _profile_with_hooks(tmp_path, {"verify": ["common/check"]})
    registry = ProfileHookRegistry()
    with pytest.raises(ProfileHookError, match="unregistered"):
        execute_profile_hooks(profile, "verify", registry, workspace=tmp_path)

    registry.register(
        "common/check",
        "build",
        lambda ctx: HookResult("common/check", "build", True, "ok", {}),
    )
    with pytest.raises(ProfileHookError, match="registered for build"):
        execute_profile_hooks(profile, "verify", registry, workspace=tmp_path)


def test_duplicate_registration_fails_closed() -> None:
    registry = ProfileHookRegistry()
    callback = lambda ctx: HookResult("common/x", "build", True, "ok", {})
    registry.register("common/x", "build", callback)
    with pytest.raises(ProfileHookError, match="duplicate"):
        registry.register("common/x", "build", callback)


def test_failed_or_malformed_hook_cannot_produce_accepted_evidence(tmp_path: Path) -> None:
    profile = _profile_with_hooks(tmp_path, {"verify": ["common/check"]})
    registry = ProfileHookRegistry()
    registry.register(
        "common/check",
        "verify",
        lambda ctx: HookResult("common/check", "verify", False, "verification failed", {}),
    )
    with pytest.raises(ProfileHookError, match="verification failed"):
        execute_profile_hooks(profile, "verify", registry, workspace=tmp_path)


def test_recovery_hooks_require_explicit_authorization(tmp_path: Path) -> None:
    profile = _profile_with_hooks(tmp_path, {"recovery": ["common/recovery-check"]})
    registry = ProfileHookRegistry()
    registry.register(
        "common/recovery-check",
        "recovery",
        lambda ctx: HookResult(
            "common/recovery-check", "recovery", True, "offline recovery check ok", {}
        ),
    )

    with pytest.raises(ProfileHookError, match="explicit"):
        execute_profile_hooks(profile, "recovery", registry, workspace=tmp_path)

    _, evidence = execute_profile_hooks(
        profile,
        "recovery",
        registry,
        workspace=tmp_path,
        allow_recovery=True,
    )
    assert evidence.recovery_explicitly_authorized is True
    assert evidence.beta_gate_credit is False
    assert evidence.hardware_verified is False


def test_workspace_must_exist(tmp_path: Path) -> None:
    profile = _profile_with_hooks(tmp_path, {})
    registry = ProfileHookRegistry()
    with pytest.raises(ProfileHookError, match="existing directory"):
        execute_profile_hooks(profile, "build", registry, workspace=tmp_path / "missing")
