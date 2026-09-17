from pathlib import Path
from types import SimpleNamespace

import pytest

import kaliphonestudio.kernel_authority_materialization as materialization
from kaliphonestudio.kernel_contract import KernelContractError


SHA = "a" * 64
CONFIG_SHA = "b" * 64
IMAGE_SHA = "c" * 64
AUTH_SHA = "d" * 64
SOURCE = "e" * 40


class DigestEvidence:
    def __init__(self, digest):
        self.digest = digest

    def evidence_sha256(self):
        return self.digest


class FakePlan:
    schema_version = 1
    profile_id = "oneplus/avicii"
    source_commit = SOURCE
    arch = "arm64"
    image_name = "Image"
    defconfig = "vendor/lito-perf_defconfig"
    config_fragments = ("vendor/debugfs.config",)

    def plan_sha256(self):
        return SHA


class FakeLock:
    schema_version = 1

    def lock_sha256(self):
        return "1" * 64


class FakeAuthority:
    schema_version = 1
    reviewed = True
    strict_byte_identical = True
    distinct_build_roots_verified = True
    hardware_verified = False
    beta_gate_credit = False
    profile_id = "oneplus/avicii"
    source_commit = SOURCE
    kernel_plan_sha256 = SHA
    toolchain_lock_sha256 = "1" * 64
    build_recipe_sha256 = "2" * 64
    reproducible_environment_sha256 = "3" * 64
    config_sha256 = CONFIG_SHA
    config_size = 166055
    image_sha256 = IMAGE_SHA
    image_size = 43878416

    def authority_sha256(self):
        return AUTH_SHA


class FakeRecipe:
    defconfig = FakePlan.defconfig
    config_fragments = FakePlan.config_fragments

    def recipe_sha256(self):
        return "2" * 64

    def environment_sha256(self):
        return "3" * 64


def patch_dependencies(monkeypatch, calls):
    monkeypatch.setattr(materialization, "verify_kernel_checkout", lambda *_: DigestEvidence("4" * 64))
    monkeypatch.setattr(materialization, "bind_kernel_plan_to_toolchain", lambda *_: DigestEvidence("5" * 64))
    monkeypatch.setattr(materialization, "verify_materialized_toolchain", lambda *_: DigestEvidence("6" * 64))
    monkeypatch.setattr(materialization, "create_kernel_build_recipe", lambda *_args, **_kwargs: FakeRecipe())
    monkeypatch.setattr(materialization, "_execution_env", lambda *_: {"PATH": "/tool"})
    monkeypatch.setattr(
        materialization,
        "_make_argv",
        lambda _source, _output, _recipe, target, **_kwargs: ["make", target],
    )
    monkeypatch.setattr(materialization, "_merge_script", lambda source: source / "merge_config.sh")
    monkeypatch.setattr(
        materialization,
        "_fragment_path",
        lambda source, _plan, fragment: source / fragment,
    )
    monkeypatch.setattr(
        materialization,
        "_write_required_config_fragment",
        lambda _plan, output: output / ".kaliphonestudio-required.config",
    )
    monkeypatch.setattr(
        materialization,
        "_run_checked",
        lambda _runner, argv, **_kwargs: calls.append(tuple(argv)),
    )
    monkeypatch.setattr(
        materialization,
        "verify_generated_kernel_config",
        lambda *_: SimpleNamespace(config_sha256=CONFIG_SHA, config_size=166055),
    )
    monkeypatch.setattr(
        materialization,
        "verify_arm64_kernel_image",
        lambda *_: SimpleNamespace(image_sha256=IMAGE_SHA, image_size=43878416),
    )


def roots(tmp_path: Path):
    source = tmp_path / "source"
    toolchain = tmp_path / "toolchain"
    output = tmp_path / "output"
    source.mkdir(); toolchain.mkdir(); output.mkdir()
    return source, toolchain, output


def test_missing_config_replays_only_config_sequence(monkeypatch, tmp_path):
    calls = []
    patch_dependencies(monkeypatch, calls)
    source, toolchain, output = roots(tmp_path)
    evidence = materialization.materialize_reviewed_kernel_build_root(
        FakePlan(), FakeLock(), FakeAuthority(),
        checkout=source, toolchain_root=toolchain, output_root=output,
    )
    assert evidence.config_rehydrated is True
    assert [call[-1] for call in calls] == [
        "vendor/lito-perf_defconfig",
        str(output / ".kaliphonestudio-required.config"),
        "olddefconfig",
    ]
    assert all("Image" not in call for call in calls)
    assert evidence.config_sha256 == CONFIG_SHA
    assert evidence.image_sha256 == IMAGE_SHA
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False


def test_existing_config_is_verified_without_make(monkeypatch, tmp_path):
    calls = []
    patch_dependencies(monkeypatch, calls)
    source, toolchain, output = roots(tmp_path)
    (output / ".config").write_text("existing\n", encoding="utf-8")
    evidence = materialization.materialize_reviewed_kernel_build_root(
        FakePlan(), FakeLock(), FakeAuthority(),
        checkout=source, toolchain_root=toolchain, output_root=output,
    )
    assert evidence.config_rehydrated is False
    assert calls == []


def test_authority_recipe_drift_fails_before_materialization(monkeypatch, tmp_path):
    calls = []
    patch_dependencies(monkeypatch, calls)
    source, toolchain, output = roots(tmp_path)
    authority = FakeAuthority()
    authority.build_recipe_sha256 = "f" * 64
    with pytest.raises(KernelContractError, match="build recipe"):
        materialization.materialize_reviewed_kernel_build_root(
            FakePlan(), FakeLock(), authority,
            checkout=source, toolchain_root=toolchain, output_root=output,
        )
    assert calls == []


def test_materialized_config_or_image_mismatch_fails_closed(monkeypatch, tmp_path):
    calls = []
    patch_dependencies(monkeypatch, calls)
    source, toolchain, output = roots(tmp_path)
    (output / ".config").write_text("existing\n", encoding="utf-8")
    monkeypatch.setattr(
        materialization,
        "verify_generated_kernel_config",
        lambda *_: SimpleNamespace(config_sha256="0" * 64, config_size=166055),
    )
    with pytest.raises(KernelContractError, match="config does not match"):
        materialization.materialize_reviewed_kernel_build_root(
            FakePlan(), FakeLock(), FakeAuthority(),
            checkout=source, toolchain_root=toolchain, output_root=output,
        )
