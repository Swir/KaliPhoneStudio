from pathlib import Path

import pytest

from kaliphonestudio.kernel_contract import KernelContractError, create_kernel_build_plan
from kaliphonestudio.kernel_repro import (
    verify_kernel_reproducibility,
    write_kernel_reproducibility_evidence,
)
from kaliphonestudio.profiles import get_profile


ROOT = Path(__file__).resolve().parents[1]
PROFILE_ROOT = ROOT / "devices"


def _plan():
    return create_kernel_build_plan(get_profile(PROFILE_ROOT, "oneplus/avicii"))


def _build_root(base: Path, name: str, *, extra_config: str = "", image_tail: bytes = b"") -> Path:
    plan = _plan()
    root = base / name
    image_dir = root / "arch" / plan.arch / "boot"
    image_dir.mkdir(parents=True)
    config = "".join(f"{key}={value}\n" for key, value in plan.required_configs) + extra_config
    (root / ".config").write_text(config, encoding="utf-8", newline="\n")
    payload = bytearray(4096)
    payload[0x38:0x3C] = b"ARM\x64"
    if image_tail:
        payload[-len(image_tail):] = image_tail
    (image_dir / plan.image_name).write_bytes(payload)
    return root


def test_kernel_reproducibility_requires_equal_artifacts_from_distinct_roots(tmp_path):
    plan = _plan()
    first = _build_root(tmp_path, "build-a")
    second = _build_root(tmp_path, "build-b")

    evidence = verify_kernel_reproducibility(plan, build_a=first, build_b=second)

    assert evidence.schema_version == 1
    assert evidence.profile_id == plan.profile_id
    assert evidence.kernel_plan_sha256 == plan.plan_sha256()
    assert evidence.source_commit == plan.source_commit
    assert evidence.kernel_version == plan.expected_kernel_version
    assert evidence.config_size > 0
    assert evidence.image_size == 4096
    assert evidence.distinct_build_roots_verified is True
    assert evidence.byte_identical is True
    assert evidence.beta_gate_credit is False
    assert len(evidence.evidence_sha256()) == 64

    destination = tmp_path / "evidence" / "kernel-repro.json"
    digest = write_kernel_reproducibility_evidence(evidence, destination)
    assert digest == evidence.evidence_sha256()
    assert destination.read_text(encoding="utf-8") == evidence.canonical_json()
    with pytest.raises(KernelContractError, match="refusing to overwrite"):
        write_kernel_reproducibility_evidence(evidence, destination)


def test_kernel_reproducibility_rejects_final_config_byte_drift(tmp_path):
    plan = _plan()
    first = _build_root(tmp_path, "build-a")
    second = _build_root(tmp_path, "build-b", extra_config="CONFIG_LOCALVERSION_AUTO=n\n")

    with pytest.raises(KernelContractError, match="different final \\.config bytes"):
        verify_kernel_reproducibility(plan, build_a=first, build_b=second)


def test_kernel_reproducibility_rejects_image_byte_drift(tmp_path):
    plan = _plan()
    first = _build_root(tmp_path, "build-a")
    second = _build_root(tmp_path, "build-b", image_tail=b"drift")

    with pytest.raises(KernelContractError, match="different Image bytes"):
        verify_kernel_reproducibility(plan, build_a=first, build_b=second)


def test_kernel_reproducibility_rejects_same_or_nested_build_roots(tmp_path):
    plan = _plan()
    first = _build_root(tmp_path, "build-a")

    with pytest.raises(KernelContractError, match="two distinct build roots"):
        verify_kernel_reproducibility(plan, build_a=first, build_b=first)

    nested = first / "nested"
    image_dir = nested / "arch" / plan.arch / "boot"
    image_dir.mkdir(parents=True)
    (nested / ".config").write_bytes((first / ".config").read_bytes())
    (image_dir / plan.image_name).write_bytes(
        (first / "arch" / plan.arch / "boot" / plan.image_name).read_bytes()
    )
    with pytest.raises(KernelContractError, match="must not be nested"):
        verify_kernel_reproducibility(plan, build_a=first, build_b=nested)


def test_kernel_reproducibility_revalidates_profile_required_config(tmp_path):
    plan = _plan()
    first = _build_root(tmp_path, "build-a")
    second = _build_root(tmp_path, "build-b")
    missing = plan.required_configs[0][0]
    for root in (first, second):
        lines = (root / ".config").read_text(encoding="utf-8").splitlines()
        (root / ".config").write_text(
            "\n".join(line for line in lines if not line.startswith(missing + "=")) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    with pytest.raises(KernelContractError, match=missing):
        verify_kernel_reproducibility(plan, build_a=first, build_b=second)
