from pathlib import Path
from types import SimpleNamespace

import pytest

from kaliphonestudio.kernel_contract import (
    KernelContractError,
    create_kernel_build_plan,
    parse_generated_kernel_config,
    verify_arm64_kernel_image,
    verify_generated_kernel_config,
    verify_kernel_checkout,
)
from kaliphonestudio.profiles import get_profile


ROOT = Path(__file__).resolve().parents[1]
PROFILE_ROOT = ROOT / "devices"


def _plan():
    profile = get_profile(PROFILE_ROOT, "oneplus/avicii")
    return create_kernel_build_plan(profile)


def test_avicii_kernel_plan_is_profile_driven_and_exact_source_locked():
    plan = _plan()
    assert plan.profile_id == "oneplus/avicii"
    assert plan.source_url == "https://github.com/LineageOS/android_kernel_oneplus_sm7250"
    assert plan.source_commit == "fb4b4374d3b9ad0f10ba38d159585129f092fb3d"
    assert plan.expected_kernel_version == "4.19.300"
    assert plan.arch == "arm64"
    assert plan.image_name == "Image"
    assert plan.defconfig == "vendor/lito-perf_defconfig"
    assert plan.config_fragments == ("vendor/debugfs.config",)
    assert ("CONFIG_SCSI_UFS_QCOM", "y") in plan.required_configs
    assert ("CONFIG_SECCOMP", "y") in plan.required_configs
    assert len(plan.plan_sha256()) == 64


def test_kernel_checkout_evidence_binds_commit_version_and_config_material(tmp_path, monkeypatch):
    plan = _plan()
    checkout = tmp_path / "kernel"
    config_dir = checkout / "arch" / "arm64" / "configs" / "vendor"
    config_dir.mkdir(parents=True)
    (checkout / "Makefile").write_text(
        "VERSION = 4\nPATCHLEVEL = 19\nSUBLEVEL = 300\n",
        encoding="utf-8",
    )
    (config_dir / "lito-perf_defconfig").write_text("CONFIG_ARCH_LITO=y\n", encoding="utf-8")
    (config_dir / "debugfs.config").write_text("CONFIG_DEBUG_FS=n\n", encoding="utf-8")

    def fake_run(argv, **kwargs):
        assert argv[:3] == ["git", "-C", str(checkout)]
        return SimpleNamespace(stdout=plan.source_commit + "\n", stderr="", returncode=0)

    monkeypatch.setattr("kaliphonestudio.kernel_contract.subprocess.run", fake_run)
    evidence = verify_kernel_checkout(plan, checkout)
    assert evidence.profile_id == plan.profile_id
    assert evidence.plan_sha256 == plan.plan_sha256()
    assert evidence.source_commit == plan.source_commit
    assert evidence.kernel_version == "4.19.300"
    assert len(evidence.defconfig_sha256) == 64
    assert evidence.fragment_sha256[0][0] == "vendor/debugfs.config"


def test_kernel_checkout_rejects_wrong_source_commit(tmp_path, monkeypatch):
    plan = _plan()
    checkout = tmp_path / "kernel"
    checkout.mkdir()

    monkeypatch.setattr(
        "kaliphonestudio.kernel_contract.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(stdout="0" * 40 + "\n", stderr="", returncode=0),
    )
    with pytest.raises(KernelContractError, match="does not match locked commit"):
        verify_kernel_checkout(plan, checkout)


def test_generated_kernel_config_must_satisfy_profile_requirements(tmp_path):
    plan = _plan()
    config = tmp_path / ".config"
    payload = "".join(f"{name}={state}\n" for name, state in plan.required_configs)
    config.write_text(payload, encoding="utf-8")
    evidence = verify_generated_kernel_config(plan, config)
    assert evidence.plan_sha256 == plan.plan_sha256()
    assert evidence.required_config_count == len(plan.required_configs)
    assert evidence.config_size == len(payload.encode())

    missing_name = plan.required_configs[0][0]
    bad_payload = "".join(
        f"{name}={state}\n" for name, state in plan.required_configs if name != missing_name
    )
    config.write_text(bad_payload, encoding="utf-8")
    with pytest.raises(KernelContractError, match=missing_name):
        verify_generated_kernel_config(plan, config)


def test_generated_config_parser_rejects_conflicting_duplicates():
    with pytest.raises(KernelContractError, match="conflicting duplicate"):
        parse_generated_kernel_config(b"CONFIG_SECCOMP=y\n# CONFIG_SECCOMP is not set\n")


def test_arm64_kernel_image_preflight_checks_magic_and_hash(tmp_path):
    plan = _plan()
    image = tmp_path / "Image"
    payload = bytearray(4096)
    payload[0x38:0x3C] = b"ARM\x64"
    image.write_bytes(payload)
    evidence = verify_arm64_kernel_image(plan, image)
    assert evidence.profile_id == plan.profile_id
    assert evidence.plan_sha256 == plan.plan_sha256()
    assert evidence.image_size == 4096
    assert evidence.arm64_magic_verified is True
    assert len(evidence.image_sha256) == 64

    payload[0x38:0x3C] = b"NOPE"
    image.write_bytes(payload)
    with pytest.raises(KernelContractError, match="not an ARM64 Linux Image"):
        verify_arm64_kernel_image(plan, image)
