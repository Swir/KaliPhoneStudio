from pathlib import Path
from types import SimpleNamespace

import pytest

from kaliphonestudio import kernel_build_runner as build_runner
from kaliphonestudio.kernel_contract import KernelContractError, create_kernel_build_plan
from kaliphonestudio.kernel_toolchain import load_kernel_toolchain_lock
from kaliphonestudio.profiles import get_profile


ROOT = Path(__file__).resolve().parents[1]
PROFILE_ROOT = ROOT / "devices"
TOOLCHAIN_LOCK = ROOT / "tools" / "kernel-toolchain-lock.json"


def _plan_and_lock():
    profile = get_profile(PROFILE_ROOT, "oneplus/avicii")
    return create_kernel_build_plan(profile), load_kernel_toolchain_lock(TOOLCHAIN_LOCK)


def _sha(ch: str) -> str:
    return ch * 64


def _fake_evidence(digest: str, **attrs):
    return SimpleNamespace(evidence_sha256=lambda: digest, **attrs)


def _layout(tmp_path: Path):
    plan, lock = _plan_and_lock()
    checkout = tmp_path / "source"
    toolchain = tmp_path / "toolchain"
    output = tmp_path / "out"
    (checkout / "scripts" / "kconfig").mkdir(parents=True)
    (checkout / "scripts" / "kconfig" / "merge_config.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    for fragment in plan.config_fragments:
        path = checkout / "arch" / plan.arch / "configs" / fragment
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("CONFIG_DEBUG_FS=y\n", encoding="utf-8")
    (toolchain / "bin").mkdir(parents=True)
    return plan, lock, checkout, toolchain, output


def test_kernel_build_recipe_is_canonical_and_reproducible():
    plan, lock = _plan_and_lock()
    first = build_runner.create_kernel_build_recipe(plan, lock, jobs=2)
    second = build_runner.create_kernel_build_recipe(plan, lock, jobs=2)

    assert first == second
    assert first.schema_version == 1
    assert first.profile_id == plan.profile_id
    assert first.kernel_plan_sha256 == plan.plan_sha256()
    assert first.toolchain_lock_sha256 == lock.lock_sha256()
    env = dict(first.reproducible_environment)
    assert env["SOURCE_DATE_EPOCH"] == "0"
    assert env["KBUILD_BUILD_USER"] == "kaliphonestudio"
    assert env["KPS_CANONICAL_SOURCE_PREFIX"] == "/usr/src/kaliphonestudio-kernel"
    assert env["KPS_CANONICAL_OUTPUT_PREFIX"] == "/usr/src/kaliphonestudio-kernel-build"
    assert "prefix-map" in env["KPS_PATH_REMAP_POLICY"]
    assert len(first.recipe_sha256()) == 64
    assert len(first.environment_sha256()) == 64


@pytest.mark.parametrize("jobs", [0, -1, 17, True, 1.5])
def test_kernel_build_recipe_rejects_unsafe_job_counts(jobs):
    plan, lock = _plan_and_lock()
    with pytest.raises(KernelContractError, match="jobs"):
        build_runner.create_kernel_build_recipe(plan, lock, jobs=jobs)


def test_path_remap_flags_bind_distinct_host_roots_to_fixed_virtual_roots(tmp_path):
    source_a = (tmp_path / "kernel-a").resolve()
    source_b = (tmp_path / "kernel-b").resolve()
    out_a = (tmp_path / "build-a").resolve()
    out_b = (tmp_path / "build-b").resolve()

    flags_a = build_runner._path_remap_flags(source_a, out_a)
    flags_b = build_runner._path_remap_flags(source_b, out_b)

    assert str(source_a) in flags_a
    assert str(out_a) in flags_a
    assert str(source_b) in flags_b
    assert str(out_b) in flags_b
    assert flags_a != flags_b
    for flags in (flags_a, flags_b):
        assert build_runner._CANONICAL_SOURCE_PREFIX in flags
        assert build_runner._CANONICAL_OUTPUT_PREFIX in flags
        assert flags.count("-fdebug-prefix-map=") == 2
        assert flags.count("-fmacro-prefix-map=") == 2


def test_execute_kernel_build_uses_argv_only_locked_inputs_and_emits_evidence(tmp_path, monkeypatch):
    plan, lock, checkout, toolchain, output = _layout(tmp_path)
    calls = []

    monkeypatch.setattr(
        build_runner,
        "verify_kernel_checkout",
        lambda *args, **kwargs: _fake_evidence(_sha("1")),
    )
    monkeypatch.setattr(
        build_runner,
        "bind_kernel_plan_to_toolchain",
        lambda *args, **kwargs: _fake_evidence(_sha("2")),
    )
    monkeypatch.setattr(
        build_runner,
        "verify_materialized_toolchain",
        lambda *args, **kwargs: _fake_evidence(_sha("3")),
    )
    monkeypatch.setattr(
        build_runner,
        "verify_generated_kernel_config",
        lambda *args, **kwargs: _fake_evidence(
            _sha("4"), config_sha256=_sha("5"), config_size=2048
        ),
    )
    monkeypatch.setattr(
        build_runner,
        "verify_arm64_kernel_image",
        lambda *args, **kwargs: _fake_evidence(
            _sha("6"), image_sha256=_sha("7"), image_size=4096, arm64_magic_verified=True
        ),
    )

    def fake_runner(argv, **kwargs):
        calls.append((list(argv), dict(kwargs)))
        return SimpleNamespace(returncode=0)

    evidence = build_runner.execute_kernel_build(
        plan,
        lock,
        checkout=checkout,
        toolchain_root=toolchain,
        output_root=output,
        jobs=2,
        runner=fake_runner,
        base_env={"PATH": "/usr/bin"},
        step_timeout_seconds=60,
    )

    assert len(calls) == 4  # defconfig, merge fragment, olddefconfig, Image
    assert calls[0][0][0] == "make"
    assert calls[0][0][-1] == plan.defconfig
    assert calls[1][0][0] == "bash"
    assert calls[1][0][2:5] == ["-m", "-O", str(output.resolve())]
    assert calls[2][0][-1] == "olddefconfig"
    assert calls[3][0][-2:] == ["-j2", plan.image_name]

    for index in (0, 2, 3):
        argv = calls[index][0]
        assert "KBUILD_ABS_SRCTREE=0" in argv
        kcflags = next(item for item in argv if item.startswith("KCFLAGS="))
        kaflags = next(item for item in argv if item.startswith("KAFLAGS="))
        for value in (kcflags, kaflags):
            assert str(checkout.resolve()) in value
            assert str(output.resolve()) in value
            assert build_runner._CANONICAL_SOURCE_PREFIX in value
            assert build_runner._CANONICAL_OUTPUT_PREFIX in value

    for argv, kwargs in calls:
        assert isinstance(argv, list)
        assert kwargs["shell"] is False
        assert kwargs["check"] is True
        assert kwargs["timeout"] == 60
        assert kwargs["env"]["PATH"].split(":", 1)[0] == str((toolchain / "bin").resolve())
        assert kwargs["env"]["SOURCE_DATE_EPOCH"] == "0"
        assert kwargs["env"]["LC_ALL"] == "C"
        assert kwargs["env"]["KPS_CANONICAL_SOURCE_PREFIX"] == build_runner._CANONICAL_SOURCE_PREFIX

    assert evidence.profile_id == plan.profile_id
    assert evidence.kernel_plan_sha256 == plan.plan_sha256()
    assert evidence.toolchain_lock_sha256 == lock.lock_sha256()
    assert evidence.config_sha256 == _sha("5")
    assert evidence.image_sha256 == _sha("7")
    assert evidence.arm64_magic_verified is True
    assert evidence.beta_gate_credit is False

    destination = tmp_path / "evidence" / "kernel-build.json"
    digest = build_runner.write_kernel_build_run_evidence(evidence, destination)
    assert digest == evidence.evidence_sha256()
    assert destination.read_text(encoding="utf-8") == evidence.canonical_json()
    with pytest.raises(KernelContractError, match="refusing to overwrite"):
        build_runner.write_kernel_build_run_evidence(evidence, destination)


def test_execute_kernel_build_rejects_nonempty_or_nested_output(tmp_path, monkeypatch):
    plan, lock, checkout, toolchain, output = _layout(tmp_path)
    monkeypatch.setattr(build_runner, "verify_kernel_checkout", lambda *a, **k: _fake_evidence(_sha("1")))
    monkeypatch.setattr(build_runner, "bind_kernel_plan_to_toolchain", lambda *a, **k: _fake_evidence(_sha("2")))
    monkeypatch.setattr(build_runner, "verify_materialized_toolchain", lambda *a, **k: _fake_evidence(_sha("3")))

    output.mkdir()
    (output / "stale").write_text("x", encoding="utf-8")
    with pytest.raises(KernelContractError, match="must be empty"):
        build_runner.execute_kernel_build(
            plan,
            lock,
            checkout=checkout,
            toolchain_root=toolchain,
            output_root=output,
            step_timeout_seconds=60,
        )

    nested = checkout / "out"
    with pytest.raises(KernelContractError, match="independent of kernel checkout"):
        build_runner.execute_kernel_build(
            plan,
            lock,
            checkout=checkout,
            toolchain_root=toolchain,
            output_root=nested,
            step_timeout_seconds=60,
        )
