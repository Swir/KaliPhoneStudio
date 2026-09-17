from dataclasses import fields, replace

import pytest

from kaliphonestudio.candidate import FirstBootCandidateManifest
from kaliphonestudio.candidate_rootfs_authority import (
    bind_first_boot_candidate_to_rootfs_authority,
    write_first_boot_rootfs_authority_evidence,
)
from kaliphonestudio.candidate_rootfs_provenance import (
    bind_first_boot_candidate_to_rootfs_provenance,
)
from kaliphonestudio.rootfs import RootfsError
from kaliphonestudio.rootfs_authority import RootfsAuthorityRecord
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
INRELEASE_SHA = "8" * 64
ARTIFACT_SIZE = 123456
PACKAGE_COUNT = 269
RAW_A_SIZE = 234567
RAW_B_SIZE = 234890


def candidate_manifest(**changes) -> FirstBootCandidateManifest:
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
    values.update({
        "rootfs_evidence_sha256": ROOTFS_EVIDENCE_SHA,
        "rootfs_artifact_sha256": ARTIFACT_SHA,
        "rootfs_artifact_size": ARTIFACT_SIZE,
        "rootfs_package_manifest_sha256": PACKAGE_SHA,
        "rootfs_package_count": PACKAGE_COUNT,
        "rootfs_source_lock_sha256": SOURCE_LOCK_SHA,
        "repository_snapshot_sha256": SNAPSHOT_SHA,
    })
    values.update(changes)
    return FirstBootCandidateManifest(**values)


def canonical_record(input_sha, input_size):
    return RootfsCanonicalizationEvidence(
        schema_version=1,
        input_sha256=input_sha,
        input_size=input_size,
        output_sha256=ARTIFACT_SHA,
        output_size=ARTIFACT_SIZE,
        member_count_input=100,
        member_count_output=99,
        normalized_mtime_count=80,
        zeroed_volatile_files=3,
        locked_password_entries=1,
        dropped_cache_entries=1,
        archive_prefix="rootfs",
        beta_gate_credit=False,
    )


def evidence_set():
    first = canonical_record(RAW_A_SHA, RAW_A_SIZE)
    second = canonical_record(RAW_B_SHA, RAW_B_SIZE)
    binding = RootfsCanonicalizationBindingEvidence(
        schema_version=1,
        rootfs_evidence_sha256=ROOTFS_EVIDENCE_SHA,
        source_lock_sha256=SOURCE_LOCK_SHA,
        repository_snapshot_sha256=SNAPSHOT_SHA,
        canonicalization_policy_sha256=canonicalization_policy_sha256(),
        canonicalization_a_evidence_sha256=first.evidence_sha256(),
        canonicalization_b_evidence_sha256=second.evidence_sha256(),
        raw_a_sha256=RAW_A_SHA,
        raw_a_size=RAW_A_SIZE,
        raw_b_sha256=RAW_B_SHA,
        raw_b_size=RAW_B_SIZE,
        artifact_sha256=ARTIFACT_SHA,
        artifact_size=ARTIFACT_SIZE,
        package_manifest_sha256=PACKAGE_SHA,
        package_count=PACKAGE_COUNT,
        strict_byte_identical=True,
        beta_gate_credit=False,
    )
    manifest = candidate_manifest()
    provenance = bind_first_boot_candidate_to_rootfs_provenance(
        manifest, binding, canonical_a=first, canonical_b=second
    )
    return manifest, provenance, binding


def authority_for(provenance, **changes):
    values = {
        "schema_version": 1,
        "authority_name": "test-kali-arm64-rootfs",
        "authority_run_id": 35158577624,
        "authority_commit": "b" * 40,
        "authority_artifact_id": 10474870486,
        "release_tag": "2026.2",
        "architecture": "arm64",
        "variant": "minimal",
        "source_lock_sha256": provenance.source_lock_sha256,
        "repository_snapshot_sha256": provenance.repository_snapshot_sha256,
        "inrelease_sha256": INRELEASE_SHA,
        "rootfs_evidence_sha256": provenance.rootfs_evidence_sha256,
        "canonicalization_binding_sha256": provenance.rootfs_canonicalization_binding_sha256,
        "canonicalization_policy_sha256": provenance.canonicalization_policy_sha256,
        "canonicalization_a_evidence_sha256": provenance.canonicalization_a_evidence_sha256,
        "canonicalization_b_evidence_sha256": provenance.canonicalization_b_evidence_sha256,
        "raw_a_sha256": provenance.raw_a_sha256,
        "raw_a_size": provenance.raw_a_size,
        "raw_b_sha256": provenance.raw_b_sha256,
        "raw_b_size": provenance.raw_b_size,
        "artifact_sha256": provenance.artifact_sha256,
        "artifact_size": provenance.artifact_size,
        "package_manifest_sha256": provenance.package_manifest_sha256,
        "package_count": provenance.package_count,
        "strict_byte_identical": True,
        "reviewed": True,
        "hardware_verified": False,
        "beta_gate_credit": False,
    }
    values.update(changes)
    return RootfsAuthorityRecord(**values)


def test_candidate_is_bound_to_exact_reviewed_rootfs_authority(tmp_path):
    manifest, provenance, _ = evidence_set()
    authority = authority_for(provenance)
    evidence = bind_first_boot_candidate_to_rootfs_authority(manifest, provenance, authority)

    assert evidence.schema_version == 1
    assert evidence.profile_id == manifest.profile_id
    assert evidence.first_boot_manifest_sha256 == manifest.manifest_sha256()
    assert evidence.first_boot_rootfs_provenance_sha256 == provenance.evidence_sha256()
    assert evidence.rootfs_authority_sha256 == authority.authority_sha256()
    assert evidence.authority_run_id == authority.authority_run_id
    assert evidence.artifact_sha256 == ARTIFACT_SHA
    assert evidence.package_count == PACKAGE_COUNT
    assert evidence.strict_byte_identical is True
    assert evidence.reviewed is True
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False

    out = tmp_path / "first-boot-rootfs-authority.json"
    digest = write_first_boot_rootfs_authority_evidence(evidence, out)
    assert digest == evidence.evidence_sha256()
    assert out.read_text(encoding="utf-8") == evidence.canonical_json()


def test_authority_binding_rejects_detached_first_boot_provenance():
    manifest, provenance, _ = evidence_set()
    detached = replace(provenance, first_boot_manifest_sha256="9" * 64)
    with pytest.raises(RootfsError, match="detached"):
        bind_first_boot_candidate_to_rootfs_authority(
            manifest, detached, authority_for(provenance)
        )


def test_authority_binding_rejects_artifact_or_raw_ab_substitution():
    manifest, provenance, _ = evidence_set()
    with pytest.raises(RootfsError, match="provenance/authority artifact"):
        bind_first_boot_candidate_to_rootfs_authority(
            manifest,
            provenance,
            authority_for(provenance, artifact_sha256="9" * 64),
        )
    with pytest.raises(RootfsError, match="raw rootfs A"):
        bind_first_boot_candidate_to_rootfs_authority(
            manifest,
            provenance,
            authority_for(provenance, raw_a_sha256="9" * 64),
        )


def test_authority_binding_rejects_unreviewed_or_credit_claims():
    manifest, provenance, _ = evidence_set()
    with pytest.raises(RootfsError, match="explicit completed review"):
        bind_first_boot_candidate_to_rootfs_authority(
            manifest, provenance, authority_for(provenance, reviewed=False)
        )
    with pytest.raises(RootfsError, match="hardware verification"):
        bind_first_boot_candidate_to_rootfs_authority(
            manifest, provenance, authority_for(provenance, hardware_verified=True)
        )
    with pytest.raises(RootfsError, match="Beta-gate credit"):
        bind_first_boot_candidate_to_rootfs_authority(
            manifest, provenance, authority_for(provenance, beta_gate_credit=True)
        )


def test_authority_binding_rejects_candidate_artifact_drift():
    manifest, provenance, _ = evidence_set()
    # Keep the manifest digest intact so this regression reaches the candidate-to-
    # provenance identity layer rather than being correctly rejected earlier as a
    # detached provenance record.
    changed_provenance = replace(provenance, artifact_size=ARTIFACT_SIZE + 1)
    with pytest.raises(RootfsError, match="candidate/rootfs-provenance artifact size"):
        bind_first_boot_candidate_to_rootfs_authority(
            manifest, changed_provenance, authority_for(provenance)
        )


def test_authority_writer_refuses_overwrite(tmp_path):
    manifest, provenance, _ = evidence_set()
    evidence = bind_first_boot_candidate_to_rootfs_authority(
        manifest, provenance, authority_for(provenance)
    )
    out = tmp_path / "authority.json"
    write_first_boot_rootfs_authority_evidence(evidence, out)
    with pytest.raises(RootfsError, match="refusing to overwrite"):
        write_first_boot_rootfs_authority_evidence(evidence, out)
