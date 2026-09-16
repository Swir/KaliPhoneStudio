from __future__ import annotations

from pathlib import Path

import pytest

from kaliphonestudio.kernel_contract import KernelContractError, create_kernel_build_plan
from kaliphonestudio.kernel_toolchain import load_kernel_toolchain_lock
from kaliphonestudio.kernel_toolchain_binding import bind_kernel_plan_to_toolchain
from kaliphonestudio.profiles import get_profile


ROOT = Path(__file__).resolve().parents[1]


def _plan():
    return create_kernel_build_plan(get_profile(ROOT / "devices", "oneplus/avicii"))


def _lock():
    return load_kernel_toolchain_lock(ROOT / "tools" / "kernel-toolchain-lock.json")


def test_avicii_exact_build_config_binds_to_locked_r416183b(tmp_path: Path):
    checkout = tmp_path / "kernel"
    checkout.mkdir()
    payload = (
        "BRANCH=android-4.19-stable\n"
        "LLVM=1\n"
        "CLANG_PREBUILT_BIN=prebuilts-master/clang/host/linux-x86/clang-r416183b/bin\n"
        "BUILDTOOLS_PREBUILT_BIN=build/build-tools/path/linux-x86\n"
    )
    (checkout / "build.config.common").write_text(payload, encoding="utf-8")

    evidence = bind_kernel_plan_to_toolchain(_plan(), _lock(), checkout)
    assert evidence.profile_id == "oneplus/avicii"
    assert evidence.clang_revision == "r416183b"
    assert evidence.llvm_mode == "1"
    assert evidence.clang_prebuilt_bin.endswith("clang-r416183b/bin")
    assert evidence.beta_gate_credit is False
    assert len(evidence.kernel_plan_sha256) == 64
    assert len(evidence.toolchain_lock_sha256) == 64
    assert len(evidence.build_config_sha256) == 64


def test_binding_rejects_different_clang_revision(tmp_path: Path):
    checkout = tmp_path / "kernel"
    checkout.mkdir()
    (checkout / "build.config.common").write_text(
        "LLVM=1\nCLANG_PREBUILT_BIN=prebuilts/clang-r999999/bin\n",
        encoding="utf-8",
    )
    with pytest.raises(KernelContractError, match="not locked"):
        bind_kernel_plan_to_toolchain(_plan(), _lock(), checkout)


def test_binding_rejects_non_llvm_kernel_build_config(tmp_path: Path):
    checkout = tmp_path / "kernel"
    checkout.mkdir()
    (checkout / "build.config.common").write_text(
        "LLVM=0\nCLANG_PREBUILT_BIN=prebuilts/clang-r416183b/bin\n",
        encoding="utf-8",
    )
    with pytest.raises(KernelContractError, match="declare LLVM=1"):
        bind_kernel_plan_to_toolchain(_plan(), _lock(), checkout)


def test_binding_rejects_conflicting_duplicate_toolchain_assignment(tmp_path: Path):
    checkout = tmp_path / "kernel"
    checkout.mkdir()
    (checkout / "build.config.common").write_text(
        "LLVM=1\n"
        "CLANG_PREBUILT_BIN=prebuilts/clang-r416183b/bin\n"
        "CLANG_PREBUILT_BIN=prebuilts/clang-r999999/bin\n",
        encoding="utf-8",
    )
    with pytest.raises(KernelContractError, match="conflicting duplicate CLANG_PREBUILT_BIN"):
        bind_kernel_plan_to_toolchain(_plan(), _lock(), checkout)


def test_binding_rejects_path_escape(tmp_path: Path):
    checkout = tmp_path / "kernel"
    checkout.mkdir()
    with pytest.raises(KernelContractError, match="safe relative POSIX"):
        bind_kernel_plan_to_toolchain(
            _plan(), _lock(), checkout, build_config_relative="../build.config.common"
        )
