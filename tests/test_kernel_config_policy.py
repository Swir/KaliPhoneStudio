from dataclasses import replace
from pathlib import Path

import pytest

from kaliphonestudio import kernel_build_runner as build_runner
from kaliphonestudio.kernel_contract import KernelContractError, create_kernel_build_plan
from kaliphonestudio.profiles import get_profile


ROOT = Path(__file__).resolve().parents[1]
PROFILE_ROOT = ROOT / "devices"


def _plan():
    return create_kernel_build_plan(get_profile(PROFILE_ROOT, "oneplus/avicii"))


def test_avicii_required_kernel_policy_matches_boot_ramdisk_and_deterministic_signing():
    profile = get_profile(PROFILE_ROOT, "oneplus/avicii")
    plan = create_kernel_build_plan(profile)
    required = dict(plan.required_configs)

    assert profile.data["boot"]["ramdisk_compression"] == "lz4"
    assert required["CONFIG_BLK_DEV_INITRD"] == "y"
    assert required["CONFIG_RD_LZ4"] == "y"
    assert required["CONFIG_MODULE_SIG"] == "n"
    assert required["CONFIG_MODULE_SIG_FORCE"] == "n"


def test_required_config_fragment_is_canonical_and_profile_bound():
    plan = _plan()
    first = build_runner._required_config_fragment_payload(plan)
    second = build_runner._required_config_fragment_payload(plan)

    assert first == second
    assert first.endswith("\n")
    assert "CONFIG_RD_LZ4=y\n" in first
    assert "# CONFIG_MODULE_SIG is not set\n" in first
    assert "# CONFIG_MODULE_SIG_FORCE is not set\n" in first
    assert "CONFIG_SCSI_UFS_QCOM=y\n" in first

    # The exact policy is already committed into the kernel-plan digest. A policy
    # change must therefore produce a different approved plan identity.
    changed = replace(
        plan,
        required_configs=tuple(
            (name, "n" if name == "CONFIG_RD_LZ4" else state)
            for name, state in plan.required_configs
        ),
    )
    assert changed.plan_sha256() != plan.plan_sha256()


def test_required_config_fragment_rejects_invalid_or_ambiguous_policy():
    plan = _plan()

    invalid_name = replace(plan, required_configs=(("RD_LZ4", "y"),))
    with pytest.raises(KernelContractError, match="invalid required CONFIG name"):
        build_runner._required_config_fragment_payload(invalid_name)

    invalid_state = replace(plan, required_configs=(("CONFIG_RD_LZ4", "auto"),))
    with pytest.raises(KernelContractError, match="unsupported required state"):
        build_runner._required_config_fragment_payload(invalid_state)

    duplicate = replace(
        plan,
        required_configs=(("CONFIG_RD_LZ4", "y"), ("CONFIG_RD_LZ4", "y")),
    )
    with pytest.raises(KernelContractError, match="duplicate required config"):
        build_runner._required_config_fragment_payload(duplicate)

    empty = replace(plan, required_configs=())
    with pytest.raises(KernelContractError, match="no required CONFIG policy"):
        build_runner._required_config_fragment_payload(empty)
