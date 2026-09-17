from pathlib import Path

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
