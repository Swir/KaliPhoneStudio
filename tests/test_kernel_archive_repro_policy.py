from pathlib import Path

from kaliphonestudio.kernel_build_runner import create_kernel_build_recipe
from kaliphonestudio.kernel_contract import create_kernel_build_plan
from kaliphonestudio.kernel_toolchain import load_kernel_toolchain_lock
from kaliphonestudio.profiles import get_profile


ROOT = Path(__file__).resolve().parents[1]


def _plan():
    profile = get_profile(ROOT / "devices", "oneplus/avicii")
    return create_kernel_build_plan(profile)


def test_avicii_kernel_archive_repro_policy_is_profile_bound() -> None:
    plan = _plan()
    flags = dict(plan.make_flags)

    assert flags["TAR_OPTIONS"] == "--sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner"
    assert flags["XZ_OPT"] == "-T1"
    assert "TAR_OPTIONS" in plan.canonical_json()
    assert "XZ_OPT" in plan.canonical_json()


def test_archive_repro_policy_does_not_disable_kernel_headers() -> None:
    plan = _plan()
    required = dict(plan.required_configs)

    # The experiment makes upstream CONFIG_IKHEADERS generation deterministic;
    # it must not obtain reproducibility by silently removing the feature.
    assert required.get("CONFIG_IKHEADERS") != "n"


def test_compat_vdso_compiler_remap_is_profile_and_recipe_bound() -> None:
    plan = _plan()
    lock = load_kernel_toolchain_lock(ROOT / "tools" / "kernel-toolchain-lock.json")
    recipe = create_kernel_build_recipe(plan, lock, jobs=1)
    cc = dict(plan.make_flags)["CC"]

    assert cc.startswith("clang ")
    assert "$(KBUILD_SRC)" in cc
    assert "$(CURDIR)" in cc
    assert cc.count("-fdebug-prefix-map=") == 2
    assert cc.count("-fmacro-prefix-map=") == 2
    assert "/usr/src/kaliphonestudio-kernel" in cc
    assert "/usr/src/kaliphonestudio-kernel-build" in cc
    assert "/home/runner/" not in cc

    # This must be exact build-recipe evidence, not an unrecorded CI env tweak.
    assert ("CC", cc) in recipe.make_flags
    assert "$(KBUILD_SRC)" in recipe.canonical_json()
    assert "$(CURDIR)" in recipe.canonical_json()
