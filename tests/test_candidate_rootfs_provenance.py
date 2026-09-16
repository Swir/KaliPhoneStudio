from dataclasses import fields, replace
from pathlib import Path

import pytest

from kaliphonestudio.candidate import FirstBootCandidateManifest
from kaliphonestudio.candidate_rootfs_provenance import (
    bind_first_boot_candidate_to_rootfs_provenance,
    write_first_boot_rootfs_provenance_evidence,
)
from kaliphonestudio.rootfs import RootfsError
from kaliphonestudio.rootfs_canonical import RootfsCanonicalizationEvidence
from kaliphonestudio.rootfs_canonical_binding import (
    RootfsCanonicalizationBindingEvidence,
    canonicalization_policy_sha256,
)


ROOTFS_EVIDENCE_SHA = "1" * 64
ARTIFACT_SHA = "2" * 64
PACKAGE_SHA = "3" * 64
SOURCE_LOCK_SHA = "4" * 64
SNAPSHOT_SHA = "5" * 64
RAW_A_SHA = "6" * 64
RAW_B_SHA = "7" * 64
ARTIFACT_SIZE = 123456
PACKAGE_COUNT = 269
RAW_A_SIZE = 234567
RAW_B_SIZE = 234890


def candidate_manifest(**changes) -> FirstBootCandidateManifest:
    values = {}
    optional_names = {
        "dtb_sha256",
        "dtb_size",
        "dtb_tree_count",
        "dtbo_sha256",
        "dtbo_size",
        "dtbo_entry_count",
    }
    text_values = {
        "profile_id": "oneplus/avicii",
        "device_serial": "SERIAL123",
        "firmware_build": "AC2003_11_F.22",
        "firmware_fingerprint": "OnePlus/avicii/avicii:test",
        "kernel_source_commit": "f" * 40,
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
            values[name] = "a" * 64
        elif name.endswith("_size") or name.endswith("_count"):
            values[name] = 1
        else:
            raise AssertionError(f"unhandled first-boot manifest field: {name}")
    values.update(
        {
            "rootfs_evidence_sha256": ROOTFS_EVIDENCE_SHA,
            "rootfs_artifact_sha256": ARTIFACT_SHA,
            "rootfs_artifact_size": ARTIFACT_SIZE,
            "rootfs_package_manifest_sha256": PACKAGE_SHA,
            "rootfs_package_count": PACKAGE_COUNT,
            "rootfs_source_lock_sha256": SOURCE_LOCK_SHA,
            "repository_snapshot_sha256": SNAPSHOT_SHA,
        }
    )
    values.update(changes)
    return FirstBootCandidateManifest(**values)


def canonical_record(input_sha, input_size, **changes):
    values = {
        "schema_version": 1,
        "input_sha256": input_sha,
        "input_size": input_size,
        "output_sha256": ARTIFACT_SHA,
        "output_size": ARTIFACT_SIZE,
        "member_count_input": 100,
        "member_count_output": 99,
        "normalized_mtime_count": 80,
        "zeroed_volatile_files": 3,
        "locked_password_entries": 1,
        "dropped_cache_entries": 1,
        "archive_prefix": "rootfs",
        "beta_gate_credit": False,
    }
    values.update(changes)
    return RootfsCanonicalizationEvidence(**values)


def evidence_set(**binding_changes):
    first = canonical_record(RAW_A_SHA, RAW_A_SIZE)
    second = canonical_record(RAW_B_SHA, RAW_B_SIZE)
    values = {
        "schema_version": 1,
        "rootfs_evidence_sha256": ROOTFS_EVIDENCE_SHA,
        "source_lock_sha256": SOURCE_LOCK_SHA,
        "repository_snapshot_sha256": SNAPSHOT_SHA,
        "canonicalization_policy_sha256": canonicalization_policy_sha256(),
        "canonicalization_a_evidence_sha256": first.evidence_sha256(),
        "canonicalization_b_evidence_sha256": second.evidence_sha256(),
        "raw_a_sha256": RAW_A_SHA,
        "raw_a_size": RAW_A_SIZE,
        "raw_b_sha256": RAW_B_SHA,
        "raw_b_size": RAW_B_SIZE,
        "artifact_sha256": ARTIFACT_SHA,
        "artifact_size": ARTIFACT_SIZE,
        "package_manifest_sha256": PACKAGE_SHA,
        "package_count": PACKAGE_COUNT,
        "strict_byte_identical": True,
        "beta_gate_credit": False,
    }
    values.update(binding_changes)
    return first, second, RootfsCanonicalizationBindingEvidence(**values)


def test_first_boot_candidate_is_bound_to_exact_rootfs_transformation_chain(tmp_path):
    manifest = candidate_manifest()
    first, second, binding = evidence_set()

    evidence = bind_first_boot_candidate_to_rootfs_provenance(
        manifest,
        binding,
        canonical_a=first,
        canonical_b=second,
    )

    assert evidence.schema_version == 1
    assert evidence.profile_id == "oneplus/avicii"
    assert evidence.first_boot_manifest_sha256 == manifest.manifest_sha256()
    assert evidence.rootfs_evidence_sha256 == ROOTFS_EVIDENCE_SHA
    assert evidence.rootfs_canonicalization_binding_sha256 == binding.evidence_sha256()
    assert evidence.canonicalization_a_evidence_sha256 == first.evidence_sha256()
    assert evidence.canonicalization_b_evidence_sha256 == second.evidence_sha256()
    assert evidence.raw_a_sha256 == RAW_A_SHA
    assert evidence.raw_b_sha256 == RAW_B_SHA
    assert evidence.artifact_sha256 == ARTIFACT_SHA
    assert evidence.strict_byte_identical is True
    assert evidence.beta_gate_credit is False
    assert evidence.hardware_verified is False

    destination = tmp_path / "evidence" / "first-boot-rootfs-provenance.json"
    digest = write_first_boot_rootfs_provenance_evidence(evidence, destination)
    assert digest == evidence.evidence_sha256()
    assert destination.read_text(encoding="utf-8") == evidence.canonical_json()


def test_binding_rejects_candidate_rootfs_artifact_substitution():
    first, second, binding = evidence_set()
    manifest = candidate_manifest(rootfs_artifact_sha256="8" * 64)
    with pytest.raises(RootfsError, match="rootfs artifact SHA-256 does not match"):
        bind_first_boot_candidate_to_rootfs_provenance(
            manifest, binding, canonical_a=first, canonical_b=second
        )


def test_binding_rejects_candidate_package_or_source_provenance_drift():
    first, second, binding = evidence_set()
    with pytest.raises(RootfsError, match="package count"):
        bind_first_boot_candidate_to_rootfs_provenance(
            candidate_manifest(rootfs_package_count=PACKAGE_COUNT + 1),
            binding,
            canonical_a=first,
            canonical_b=second,
        )
    with pytest.raises(RootfsError, match="source lock SHA-256"):
        bind_first_boot_candidate_to_rootfs_provenance(
            candidate_manifest(rootfs_source_lock_sha256="9" * 64),
            binding,
            canonical_a=first,
            canonical_b=second,
        )


def test_binding_rejects_detached_or_mutated_canonicalization_record():
    first, second, binding = evidence_set()
    changed_first = replace(first, input_sha256="8" * 64)
    with pytest.raises(RootfsError, match="canonicalization A evidence digest drifted"):
        bind_first_boot_candidate_to_rootfs_provenance(
            candidate_manifest(), binding, canonical_a=changed_first, canonical_b=second
        )


def test_binding_rejects_unknown_policy_or_non_strict_evidence():
    first, second, binding = evidence_set(canonicalization_policy_sha256="8" * 64)
    with pytest.raises(RootfsError, match="unknown policy"):
        bind_first_boot_candidate_to_rootfs_provenance(
            candidate_manifest(), binding, canonical_a=first, canonical_b=second
        )

    first, second, binding = evidence_set(strict_byte_identical=False)
    with pytest.raises(RootfsError, match="strict byte-identical"):
        bind_first_boot_candidate_to_rootfs_provenance(
            candidate_manifest(), binding, canonical_a=first, canonical_b=second
        )


def test_binding_rejects_host_evidence_claiming_beta_credit():
    first, second, binding = evidence_set(beta_gate_credit=True)
    with pytest.raises(RootfsError, match="cannot claim Beta credit"):
        bind_first_boot_candidate_to_rootfs_provenance(
            candidate_manifest(), binding, canonical_a=first, canonical_b=second
        )


def test_writer_refuses_overwrite(tmp_path):
    first, second, binding = evidence_set()
    evidence = bind_first_boot_candidate_to_rootfs_provenance(
        candidate_manifest(), binding, canonical_a=first, canonical_b=second
    )
    destination = tmp_path / "provenance.json"
    write_first_boot_rootfs_provenance_evidence(evidence, destination)
    with pytest.raises(RootfsError, match="refusing to overwrite"):
        write_first_boot_rootfs_provenance_evidence(evidence, destination)
