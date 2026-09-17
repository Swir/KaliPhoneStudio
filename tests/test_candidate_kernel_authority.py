from dataclasses import fields, replace

import pytest

from kaliphonestudio.candidate import FirstBootCandidateManifest
from kaliphonestudio.candidate_kernel_authority import (
    bind_first_boot_candidate_to_kernel_authority,
    write_first_boot_kernel_authority_evidence,
)
from kaliphonestudio.kernel_authority import KernelAuthorityRecord
from kaliphonestudio.kernel_contract import KernelContractError


PLAN_SHA = "1" * 64
LOCK_SHA = "2" * 64
RECIPE_SHA = "3" * 64
ENV_SHA = "4" * 64
BUILD_A_SHA = "5" * 64
BUILD_B_SHA = "6" * 64
REPRO_SHA = "7" * 64
BINDING_SHA = "8" * 64
CONFIG_SHA = "9" * 64
IMAGE_SHA = "a" * 64
IMAGE_SIZE = 43878416
SOURCE_COMMIT = "b" * 40


def manifest(**changes) -> FirstBootCandidateManifest:
    values = {}
    optional_names = {
        "dtb_sha256", "dtb_size", "dtb_tree_count",
        "dtbo_sha256", "dtbo_size", "dtbo_entry_count",
    }
    text_values = {
        "profile_id": "oneplus/avicii",
        "device_serial": "SERIAL123",
        "firmware_build": "AC2003_11_F.22",
        "firmware_fingerprint": "OnePlus/avicii/avicii:test",
        "kernel_source_commit": SOURCE_COMMIT,
        "kernel_version": "4.19.300",
        "kernel_clang_revision": "r416183b",
    }
    bool_names = {"kernel_reproducible", "kernel_distinct_build_roots_verified"}
    for field in fields(FirstBootCandidateManifest):
        name = field.name
        if name == "schema_version":
            values[name] = 8
        elif name in optional_names:
            values[name] = None
        elif name in text_values:
            values[name] = text_values[name]
        elif name in bool_names:
            values[name] = True
        elif name.endswith("_sha256"):
            values[name] = "c" * 64
        elif name.endswith("_size") or name.endswith("_count"):
            values[name] = 1
        else:
            raise AssertionError(f"unhandled manifest field: {name}")
    values.update({
        "kernel_plan_sha256": PLAN_SHA,
        "kernel_toolchain_lock_sha256": LOCK_SHA,
        "kernel_build_recipe_sha256": RECIPE_SHA,
        "kernel_reproducible_environment_sha256": ENV_SHA,
        "kernel_build_a_run_evidence_sha256": BUILD_A_SHA,
        "kernel_build_b_run_evidence_sha256": BUILD_B_SHA,
        "kernel_reproducibility_evidence_sha256": REPRO_SHA,
        "kernel_reproducibility_binding_evidence_sha256": BINDING_SHA,
        "kernel_config_sha256": CONFIG_SHA,
        "kernel_image_sha256": IMAGE_SHA,
        "kernel_image_size": IMAGE_SIZE,
    })
    values.update(changes)
    return FirstBootCandidateManifest(**values)


def authority(**changes) -> KernelAuthorityRecord:
    values = {
        "schema_version": 1,
        "authority_name": "oneplus-avicii-kernel-test",
        "authority_run_id": 35183670399,
        "authority_commit": "d" * 40,
        "authority_artifact_id": 12345,
        "profile_id": "oneplus/avicii",
        "source_commit": SOURCE_COMMIT,
        "kernel_plan_sha256": PLAN_SHA,
        "toolchain_lock_sha256": LOCK_SHA,
        "build_recipe_sha256": RECIPE_SHA,
        "reproducible_environment_sha256": ENV_SHA,
        "build_a_run_evidence_sha256": BUILD_A_SHA,
        "build_b_run_evidence_sha256": BUILD_B_SHA,
        "reproducibility_evidence_sha256": REPRO_SHA,
        "reproducibility_binding_sha256": BINDING_SHA,
        "config_sha256": CONFIG_SHA,
        "config_size": 166055,
        "image_sha256": IMAGE_SHA,
        "image_size": IMAGE_SIZE,
        "strict_byte_identical": True,
        "distinct_build_roots_verified": True,
        "reviewed": True,
        "hardware_verified": False,
        "beta_gate_credit": False,
    }
    values.update(changes)
    return KernelAuthorityRecord(**values)


def test_candidate_binds_exact_reviewed_kernel_authority(tmp_path):
    candidate = manifest()
    record = authority()
    evidence = bind_first_boot_candidate_to_kernel_authority(candidate, record)

    assert evidence.profile_id == candidate.profile_id
    assert evidence.first_boot_manifest_sha256 == candidate.manifest_sha256()
    assert evidence.kernel_authority_sha256 == record.authority_sha256()
    assert evidence.reproducibility_evidence_sha256 == REPRO_SHA
    assert evidence.reproducibility_binding_sha256 == BINDING_SHA
    assert evidence.image_sha256 == IMAGE_SHA
    assert evidence.image_size == IMAGE_SIZE
    assert evidence.strict_byte_identical is True
    assert evidence.reviewed is True
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False

    out = tmp_path / "kernel-authority-binding.json"
    digest = write_first_boot_kernel_authority_evidence(evidence, out)
    assert digest == evidence.evidence_sha256()
    assert out.read_text(encoding="utf-8") == evidence.canonical_json()


def test_candidate_binding_rejects_authority_identity_drift():
    with pytest.raises(KernelContractError, match="kernel Image"):
        bind_first_boot_candidate_to_kernel_authority(
            manifest(), authority(image_sha256="e" * 64)
        )
    with pytest.raises(KernelContractError, match="build A run evidence"):
        bind_first_boot_candidate_to_kernel_authority(
            manifest(), authority(build_a_run_evidence_sha256="f" * 64)
        )


def test_candidate_binding_rejects_non_reproducible_candidate():
    with pytest.raises(KernelContractError, match="not marked strictly"):
        bind_first_boot_candidate_to_kernel_authority(
            manifest(kernel_reproducible=False), authority()
        )
    with pytest.raises(KernelContractError, match="distinct kernel build-root"):
        bind_first_boot_candidate_to_kernel_authority(
            manifest(kernel_distinct_build_roots_verified=False), authority()
        )


def test_candidate_binding_rejects_unreviewed_or_credit_claiming_authority():
    with pytest.raises(KernelContractError, match="explicit completed review"):
        bind_first_boot_candidate_to_kernel_authority(manifest(), authority(reviewed=False))
    with pytest.raises(KernelContractError, match="hardware verification"):
        bind_first_boot_candidate_to_kernel_authority(
            manifest(), authority(hardware_verified=True)
        )
    with pytest.raises(KernelContractError, match="Beta-gate credit"):
        bind_first_boot_candidate_to_kernel_authority(
            manifest(), authority(beta_gate_credit=True)
        )


def test_candidate_kernel_authority_writer_refuses_overwrite(tmp_path):
    evidence = bind_first_boot_candidate_to_kernel_authority(manifest(), authority())
    out = tmp_path / "binding.json"
    write_first_boot_kernel_authority_evidence(evidence, out)
    with pytest.raises(KernelContractError, match="refusing to overwrite"):
        write_first_boot_kernel_authority_evidence(evidence, out)
