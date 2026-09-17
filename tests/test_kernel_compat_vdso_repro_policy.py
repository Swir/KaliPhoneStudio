from pathlib import Path
import shutil
import subprocess

import pytest

from kaliphonestudio.kernel_build_runner import create_kernel_build_recipe
from kaliphonestudio.kernel_contract import create_kernel_build_plan
from kaliphonestudio.kernel_toolchain import load_kernel_toolchain_lock
from kaliphonestudio.profiles import get_profile


ROOT = Path(__file__).resolve().parents[1]


def _plan_and_recipe():
    profile = get_profile(ROOT / "devices", "oneplus/avicii")
    plan = create_kernel_build_plan(profile)
    lock = load_kernel_toolchain_lock(ROOT / "tools" / "kernel-toolchain-lock.json")
    return plan, create_kernel_build_recipe(plan, lock, jobs=1)


def test_compat_vdso_compiler_carries_recursive_canonical_path_maps() -> None:
    plan, recipe = _plan_and_recipe()
    flags = dict(plan.make_flags)
    cc = flags["CC"]

    assert cc.startswith("clang ")
    assert "$(KBUILD_SRC)" in cc
    assert "$(CURDIR)" in cc
    assert cc.count("-fdebug-prefix-map=") == 2
    assert cc.count("-fmacro-prefix-map=") == 2
    assert "/usr/src/kaliphonestudio-kernel" in cc
    assert "/usr/src/kaliphonestudio-kernel-build" in cc
    assert "/home/runner/" not in cc

    # The experiment must be cryptographically part of the exact build recipe,
    # not an unrecorded CI-only environment tweak.
    assert ("CC", cc) in recipe.make_flags
    assert "$(KBUILD_SRC)" in recipe.canonical_json()
    assert "$(CURDIR)" in recipe.canonical_json()


def test_compat_vdso_policy_keeps_locked_llvm_and_cross_compile_contract() -> None:
    plan, _recipe = _plan_and_recipe()
    flags = dict(plan.make_flags)

    assert flags["LLVM"] == "1"
    assert flags["LLVM_IAS"] == "1"
    assert flags["CROSS_COMPILE"] == "aarch64-linux-gnu-"
    assert flags["CROSS_COMPILE_COMPAT"] == "arm-linux-gnueabi-"
    assert flags["HOSTCC"] == "clang"
    assert flags["HOSTCXX"] == "clang++"


def test_pinned_vdso32_cc_compat_inherits_expanded_recursive_maps(tmp_path: Path) -> None:
    make = shutil.which("make")
    if make is None:
        pytest.skip("GNU make is not installed on this host")

    plan, _recipe = _plan_and_recipe()
    cc = dict(plan.make_flags)["CC"]
    source = (tmp_path / "kernel-source").resolve()
    output = (tmp_path / "kernel-output").resolve()
    source.mkdir()
    output.mkdir()
    makefile = output / "Makefile"
    makefile.write_text(
        f"KBUILD_SRC := {source}\n"
        "CC_COMPAT ?= $(CC)\n"
        "CC_COMPAT += --target=arm-linux-gnueabi\n"
        "all:\n"
        "\t@printf '%s\\n' '$(CC_COMPAT)'\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [make, "--no-print-directory", "-C", str(output), f"CC={cc}"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=20,
    )
    expanded = result.stdout.strip()

    assert "$(KBUILD_SRC)" not in expanded
    assert "$(CURDIR)" not in expanded
    assert expanded.startswith("clang ")
    assert expanded.endswith("--target=arm-linux-gnueabi")
    assert f"-fdebug-prefix-map={source}=/usr/src/kaliphonestudio-kernel" in expanded
    assert f"-fmacro-prefix-map={source}=/usr/src/kaliphonestudio-kernel" in expanded
    assert f"-fdebug-prefix-map={output}=/usr/src/kaliphonestudio-kernel-build" in expanded
    assert f"-fmacro-prefix-map={output}=/usr/src/kaliphonestudio-kernel-build" in expanded
