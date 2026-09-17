from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from kaliphonestudio.kernel_build_binding import bind_kernel_reproducibility_to_build_runs
from kaliphonestudio.kernel_build_runner import KernelBuildRunEvidence
from kaliphonestudio.kernel_contract import create_kernel_build_plan
from kaliphonestudio.kernel_repro import KernelReproducibilityEvidence
from kaliphonestudio.kernel_toolchain import load_kernel_toolchain_lock
from kaliphonestudio.profiles import get_profile


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "review_kernel_authority.py"


def _chain(tmp_path: Path):
    plan = create_kernel_build_plan(get_profile(ROOT / "devices", "oneplus/avicii"))
    lock = load_kernel_toolchain_lock(ROOT / "tools" / "kernel-toolchain-lock.json")

    def run(config_evidence: str, image_evidence: str) -> KernelBuildRunEvidence:
        return KernelBuildRunEvidence(
            schema_version=1,
            profile_id=plan.profile_id,
            kernel_plan_sha256=plan.plan_sha256(),
            source_commit=plan.source_commit,
            toolchain_lock_sha256=lock.lock_sha256(),
            checkout_evidence_sha256="1" * 64,
            toolchain_binding_evidence_sha256="2" * 64,
            materialized_toolchain_evidence_sha256="3" * 64,
            build_recipe_sha256="4" * 64,
            reproducible_environment_sha256="5" * 64,
            config_evidence_sha256=config_evidence,
            config_sha256="8" * 64,
            config_size=2048,
            image_evidence_sha256=image_evidence,
            image_sha256="b" * 64,
            image_size=4096,
            arm64_magic_verified=True,
            beta_gate_credit=False,
        )

    build_a = run("6" * 64, "9" * 64)
    build_b = run("7" * 64, "a" * 64)
    reproducibility = KernelReproducibilityEvidence(
        schema_version=1,
        profile_id=plan.profile_id,
        kernel_plan_sha256=plan.plan_sha256(),
        source_commit=plan.source_commit,
        kernel_version=plan.expected_kernel_version,
        config_sha256="8" * 64,
        config_size=2048,
        image_sha256="b" * 64,
        image_size=4096,
        build_a_config_evidence_sha256=build_a.config_evidence_sha256,
        build_b_config_evidence_sha256=build_b.config_evidence_sha256,
        build_a_image_evidence_sha256=build_a.image_evidence_sha256,
        build_b_image_evidence_sha256=build_b.image_evidence_sha256,
        distinct_build_roots_verified=True,
        byte_identical=True,
        beta_gate_credit=False,
    )
    binding = bind_kernel_reproducibility_to_build_runs(
        plan, lock, reproducibility, build_a, build_b
    )

    paths = {
        "repro": tmp_path / "repro.json",
        "binding": tmp_path / "binding.json",
        "a": tmp_path / "build-a.json",
        "b": tmp_path / "build-b.json",
        "authority": tmp_path / "authority.json",
    }
    paths["repro"].write_text(reproducibility.canonical_json(), encoding="utf-8")
    paths["binding"].write_text(binding.canonical_json(), encoding="utf-8")
    paths["a"].write_text(build_a.canonical_json(), encoding="utf-8")
    paths["b"].write_text(build_b.canonical_json(), encoding="utf-8")
    return paths


def _argv(paths: dict[str, Path]) -> list[str]:
    return [
        sys.executable,
        str(SCRIPT),
        "--profile-id", "oneplus/avicii",
        "--repro-evidence", str(paths["repro"]),
        "--binding-evidence", str(paths["binding"]),
        "--build-evidence-a", str(paths["a"]),
        "--build-evidence-b", str(paths["b"]),
        "--authority-name", "oneplus-avicii-kernel-test",
        "--authority-run-id", "123456",
        "--authority-commit", "c" * 40,
        "--authority-artifact-id", "654321",
        "--out", str(paths["authority"]),
    ]


def _reviewed_argv(paths: dict[str, Path]) -> list[str]:
    return _argv(paths)[:-2] + ["--reviewed", "--out", str(paths["authority"])]


def test_review_cli_refuses_implicit_review(tmp_path: Path):
    paths = _chain(tmp_path)
    result = subprocess.run(_argv(paths), cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert "explicit --reviewed" in (result.stdout + result.stderr)
    assert not paths["authority"].exists()


def test_review_cli_refuses_stale_staging_file(tmp_path: Path):
    paths = _chain(tmp_path)
    staged = paths["authority"].with_name(paths["authority"].name + ".reviewing")
    staged.write_text("stale", encoding="utf-8")
    result = subprocess.run(
        _reviewed_argv(paths), cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert result.returncode != 0
    assert "stale kernel authority staging path" in (result.stdout + result.stderr)
    assert not paths["authority"].exists()
    assert staged.read_text(encoding="utf-8") == "stale"


def test_review_cli_creates_and_roundtrip_verifies_authority(tmp_path: Path):
    paths = _chain(tmp_path)
    result = subprocess.run(
        _reviewed_argv(paths),
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    output = json.loads(result.stdout.strip())
    assert output["authority_name"] == "oneplus-avicii-kernel-test"
    assert output["strict_byte_identical"] is True
    assert output["distinct_build_roots_verified"] is True
    assert output["reviewed"] is True
    assert output["hardware_verified"] is False
    assert output["beta_gate_credit"] is False
    saved = json.loads(paths["authority"].read_text(encoding="utf-8"))
    assert saved["authority_run_id"] == 123456
    assert saved["authority_artifact_id"] == 654321
    assert not paths["authority"].with_name(paths["authority"].name + ".reviewing").exists()
