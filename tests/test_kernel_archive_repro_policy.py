from pathlib import Path

from kaliphonestudio.kernel_contract import create_kernel_build_plan
from kaliphonestudio.profiles import get_profile


ROOT = Path(__file__).resolve().parents[1]


def test_avicii_kernel_archive_repro_policy_is_profile_bound() -> None:
    profile = get_profile(ROOT / "devices", "oneplus/avicii")
    plan = create_kernel_build_plan(profile)
    flags = dict(plan.make_flags)

    assert flags["TAR_OPTIONS"] == "--sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner"
    assert flags["XZ_OPT"] == "-T1"
    assert "TAR_OPTIONS" in plan.canonical_json()
    assert "XZ_OPT" in plan.canonical_json()


def test_archive_repro_policy_does_not_disable_kernel_headers() -> None:
    profile = get_profile(ROOT / "devices", "oneplus/avicii")
    plan = create_kernel_build_plan(profile)
    required = dict(plan.required_configs)

    # The experiment makes upstream CONFIG_IKHEADERS generation deterministic;
    # it must not obtain reproducibility by silently removing the feature.
    assert required.get("CONFIG_IKHEADERS") != "n"
