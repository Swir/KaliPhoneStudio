from pathlib import Path

import pytest

from kaliphonestudio.kernel_bundle import (
    bind_kernel_candidate_evidence,
    write_kernel_candidate_evidence,
)
from kaliphonestudio.kernel_contract import (
    KernelCheckoutEvidence,
    KernelConfigEvidence,
    KernelContractError,
    KernelImageEvidence,
    create_kernel_build_plan,
)
from kaliphonestudio.profiles import get_profile


ROOT = Path(__file__).resolve().parents[1]


def _plan():
    return create_kernel_build_plan(get_profile(ROOT / "devices", "oneplus/avicii"))


def _kernel_image(path: Path) -> Path:
    payload = bytearray(4096)
    payload[0x38:0x3C] = b"ARM\x64"
    path.write_bytes(payload)
    return path


def _evidence(plan, image_path):
    import hashlib

    image_sha = hashlib.sha256(image_path.read_bytes()).hexdigest()
    checkout = KernelCheckoutEvidence(
        schema_version=1,
        profile_id=plan.profile_id,
        plan_sha256=plan.plan_sha256(),
        source_commit=plan.source_commit,
        kernel_version=plan.expected_kernel_version,
        defconfig_sha256="1" * 64,
        fragment_sha256=(("vendor/debugfs.config", "2" * 64),),
    )
    config = KernelConfigEvidence(
        schema_version=1,
        profile_id=plan.profile_id,
        plan_sha256=plan.plan_sha256(),
        config_sha256="3" * 64,
        config_size=4096,
        required_config_count=len(plan.required_configs),
    )
    image = KernelImageEvidence(
        schema_version=1,
        profile_id=plan.profile_id,
        plan_sha256=plan.plan_sha256(),
        image_sha256=image_sha,
        image_size=image_path.stat().st_size,
        arm64_magic_verified=True,
    )
    return checkout, config, image


def _bound(tmp_path):
    plan = _plan()
    image_path = _kernel_image(tmp_path / "Image")
    checkout, config, image = _evidence(plan, image_path)
    return bind_kernel_candidate_evidence(
        plan, checkout, config, image, kernel_image=image_path
    )


def test_kernel_candidate_evidence_binds_source_config_and_exact_image(tmp_path):
    plan = _plan()
    image_path = _kernel_image(tmp_path / "Image")
    checkout, config, image = _evidence(plan, image_path)
    bound = bind_kernel_candidate_evidence(
        plan, checkout, config, image, kernel_image=image_path
    )
    assert bound.profile_id == plan.profile_id
    assert bound.kernel_plan_sha256 == plan.plan_sha256()
    assert bound.source_commit == plan.source_commit
    assert bound.kernel_version == plan.expected_kernel_version
    assert bound.config_sha256 == config.config_sha256
    assert bound.image_sha256 == image.image_sha256
    assert bound.image_size == image.image_size
    assert bound.arm64_magic_verified is True
    assert len(bound.evidence_sha256()) == 64


def test_kernel_candidate_evidence_rejects_plan_or_profile_mixing(tmp_path):
    plan = _plan()
    image_path = _kernel_image(tmp_path / "Image")
    checkout, config, image = _evidence(plan, image_path)
    bad_config = KernelConfigEvidence(
        schema_version=1,
        profile_id="vendor/other",
        plan_sha256=plan.plan_sha256(),
        config_sha256=config.config_sha256,
        config_size=config.config_size,
        required_config_count=config.required_config_count,
    )
    with pytest.raises(KernelContractError, match="profile"):
        bind_kernel_candidate_evidence(
            plan, checkout, bad_config, image, kernel_image=image_path
        )


def test_kernel_candidate_evidence_rejects_image_drift(tmp_path):
    plan = _plan()
    image_path = _kernel_image(tmp_path / "Image")
    checkout, config, image = _evidence(plan, image_path)
    image_path.write_bytes(image_path.read_bytes() + b"tampered")
    with pytest.raises(KernelContractError, match="changed after verification"):
        bind_kernel_candidate_evidence(
            plan, checkout, config, image, kernel_image=image_path
        )


def test_kernel_candidate_evidence_rejects_unverified_arm64_header(tmp_path):
    plan = _plan()
    image_path = _kernel_image(tmp_path / "Image")
    checkout, config, image = _evidence(plan, image_path)
    bad_image = KernelImageEvidence(
        schema_version=1,
        profile_id=image.profile_id,
        plan_sha256=image.plan_sha256,
        image_sha256=image.image_sha256,
        image_size=image.image_size,
        arm64_magic_verified=False,
    )
    with pytest.raises(KernelContractError, match="lacks ARM64"):
        bind_kernel_candidate_evidence(
            plan, checkout, config, bad_image, kernel_image=image_path
        )


def test_kernel_candidate_evidence_writer_is_canonical_and_atomic(tmp_path):
    evidence = _bound(tmp_path)
    destination = tmp_path / "evidence" / "kernel.json"
    digest = write_kernel_candidate_evidence(evidence, destination)
    assert digest == evidence.evidence_sha256()
    assert destination.read_text(encoding="utf-8") == evidence.canonical_json()
    assert not destination.with_name(destination.name + ".tmp").exists()


def test_kernel_candidate_evidence_writer_rejects_stale_temp_file(tmp_path):
    evidence = _bound(tmp_path)
    destination = tmp_path / "evidence" / "kernel.json"
    destination.parent.mkdir(parents=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text("stale", encoding="utf-8")
    with pytest.raises(KernelContractError, match="stale"):
        write_kernel_candidate_evidence(evidence, destination)
    assert temporary.read_text(encoding="utf-8") == "stale"
    assert not destination.exists()
