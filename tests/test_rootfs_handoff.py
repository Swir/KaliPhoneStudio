from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import subprocess

import pytest

from kaliphonestudio.physical_candidate_gate import PhysicalCandidateGateEvidence
from kaliphonestudio.profiles import DeviceProfile, discover_profiles
from kaliphonestudio.rootfs_authority import RootfsAuthorityRecord
from kaliphonestudio.rootfs_handoff import (
    RootfsHandoffError,
    bind_rootfs_handoff_assessment,
    rootfs_handoff_contract,
    verify_rootfs_handoff_layout_checkout,
    verify_rootfs_handoff_assessment,
    write_rootfs_handoff_assessment,
)

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "devices" / "oneplus" / "avicii" / "profile.json"


def _data() -> dict:
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def _profile(data: dict | None = None) -> DeviceProfile:
    return DeviceProfile(path=PROFILE_PATH, data=_data() if data is None else data)


def _gate(rootfs_sha: str = "13" * 32) -> PhysicalCandidateGateEvidence:
    s = "ab" * 32
    return PhysicalCandidateGateEvidence(
        schema_version=1,
        profile_id="oneplus/avicii",
        device_serial="SERIAL123",
        firmware_build="AC2003_11.F.17",
        firmware_fingerprint="OnePlus/avicii/avicii:12/RKQ1/build:user/release-keys",
        physical_baseline_bundle_sha256=s,
        fastboot_capture_bundle_sha256=s,
        fastboot_baseline_evidence_sha256=s,
        fastboot_transcript_sha256=s,
        stock_provenance_sha256=s,
        stock_ota_sha256=s,
        stock_boot_sha256=s,
        first_boot_manifest_sha256=s,
        first_boot_authority_bundle_sha256=s,
        boot_authorization_sha256=s,
        boot_plan_sha256=s,
        boot_image_sha256=s,
        boot_image_size=64 * 1024 * 1024,
        kernel_image_sha256=s,
        rootfs_artifact_sha256=rootfs_sha,
        dtb_sha256=s,
        dtbo_image_sha256=s,
        reviewed_authorities_bound=True,
        exact_physical_baseline_bound=True,
        ready_for_temporary_boot_offer=True,
    )


def _authority(artifact_sha: str = "13" * 32) -> RootfsAuthorityRecord:
    s = "cd" * 32
    return RootfsAuthorityRecord(
        schema_version=1,
        authority_name="kali-arm64-rootfs-test",
        authority_run_id=1,
        authority_commit="12" * 20,
        authority_artifact_id=2,
        release_tag="2026.2",
        architecture="arm64",
        variant="minimal",
        source_lock_sha256=s,
        repository_snapshot_sha256=s,
        inrelease_sha256=s,
        rootfs_evidence_sha256=s,
        canonicalization_binding_sha256=s,
        canonicalization_policy_sha256=s,
        canonicalization_a_evidence_sha256=s,
        canonicalization_b_evidence_sha256=s,
        raw_a_sha256=s,
        raw_a_size=100,
        raw_b_sha256=s,
        raw_b_size=100,
        artifact_sha256=artifact_sha,
        artifact_size=137460600,
        package_manifest_sha256=s,
        package_count=269,
        strict_byte_identical=True,
        reviewed=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def test_all_repository_profiles_have_valid_discovery_only_handoff_contract():
    profiles = discover_profiles(ROOT / "devices")
    assert profiles
    for profile in profiles:
        contract = rootfs_handoff_contract(profile)
        assert contract.profile_id == profile.profile_id
        assert contract.state == "discovery-only"
        assert contract.target_selection_allowed is False
        assert contract.persistent_write_authorized is False
        assert not contract.layout_source_path.startswith("/")


def test_avicii_contract_binds_pinned_layout_source_and_forbids_system_containers():
    contract = rootfs_handoff_contract(_profile())
    assert contract.layout_source_commit == "3f1270c2871e9893332073eb0f8f5f9499abbf13"
    assert contract.layout_source_path == "init/fstab.qcom"
    assert contract.layout_source_blob_sha1 == "20873c3a84e1e6e8d2483e313f561ad35ded7355"
    assert contract.storage_bus == "ufs"
    assert contract.partition_hint == "userdata"
    assert contract.expected_filesystems == ("f2fs",)
    assert "fileencryption=ice" in contract.encryption_features
    assert "wrappedkey" in contract.encryption_features
    assert "metadata" in contract.forbidden_partitions
    assert "super" in contract.forbidden_partitions
    for name in _data()["ab_partitions"]:
        assert name in contract.forbidden_partitions


def test_contract_rejects_paths_target_selection_and_missing_required_evidence():
    data = deepcopy(_data())
    data["rootfs_handoff"]["layout_source_path"] = "/dev/block/by-name/userdata"
    with pytest.raises(RootfsHandoffError, match="relative POSIX"):
        rootfs_handoff_contract(_profile(data))

    data = deepcopy(_data())
    data["rootfs_handoff"]["target_selection_allowed"] = True
    with pytest.raises(RootfsHandoffError, match="must not select"):
        rootfs_handoff_contract(_profile(data))

    data = deepcopy(_data())
    data["rootfs_handoff"]["persistent_write_authorized"] = True
    with pytest.raises(RootfsHandoffError, match="cannot authorize"):
        rootfs_handoff_contract(_profile(data))

    data = deepcopy(_data())
    data["rootfs_handoff"]["required_physical_evidence"].remove("encryption-state")
    with pytest.raises(RootfsHandoffError, match="missing mandatory"):
        rootfs_handoff_contract(_profile(data))


def test_contract_rejects_detached_source_and_missing_forbidden_ab_partition():
    data = deepcopy(_data())
    data["rootfs_handoff"]["layout_source_name"] = "unlocked source"
    with pytest.raises(RootfsHandoffError, match="resolve exactly one"):
        rootfs_handoff_contract(_profile(data))

    data = deepcopy(_data())
    data["rootfs_handoff"]["forbidden_partitions"].remove("boot")
    with pytest.raises(RootfsHandoffError, match="forbid all system/A-B"):
        rootfs_handoff_contract(_profile(data))


def test_assessment_binds_exact_gate_authority_and_never_authorizes_storage():
    profile = _profile()
    gate = _gate()
    authority = _authority()
    evidence = bind_rootfs_handoff_assessment(profile, gate, authority)
    assert evidence.profile_id == profile.profile_id
    assert evidence.physical_candidate_gate_sha256 == gate.evidence_sha256()
    assert evidence.rootfs_authority_sha256 == authority.authority_sha256()
    assert evidence.rootfs_artifact_sha256 == authority.artifact_sha256
    assert evidence.rootfs_artifact_size == authority.artifact_size
    assert evidence.target_selected is False
    assert evidence.storage_path_bound is False
    assert evidence.write_authorized is False
    assert evidence.handoff_ready is False
    assert evidence.manual_review_required is True
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False
    verify_rootfs_handoff_assessment(evidence, profile, gate, authority)


def test_assessment_fails_closed_on_rootfs_drift_or_prior_device_action():
    profile = _profile()
    with pytest.raises(RootfsHandoffError, match="detached"):
        bind_rootfs_handoff_assessment(profile, _gate("14" * 32), _authority("13" * 32))

    gate = replace(_gate(), temporary_boot_executed=True)
    with pytest.raises(RootfsHandoffError, match="precede execution"):
        bind_rootfs_handoff_assessment(profile, gate, _authority())

    gate = replace(_gate(), phone_storage_written=True)
    with pytest.raises(RootfsHandoffError, match="storage writes"):
        bind_rootfs_handoff_assessment(profile, gate, _authority())


def test_assessment_write_is_immutable_and_rejects_promoted_claims(tmp_path: Path):
    profile = _profile()
    evidence = bind_rootfs_handoff_assessment(profile, _gate(), _authority())
    destination = tmp_path / "handoff.json"
    digest = write_rootfs_handoff_assessment(evidence, destination)
    assert digest == evidence.evidence_sha256()
    assert destination.read_text(encoding="utf-8") == evidence.canonical_json()
    with pytest.raises(RootfsHandoffError, match="overwrite"):
        write_rootfs_handoff_assessment(evidence, destination)

    promoted = replace(evidence, handoff_ready=True)
    with pytest.raises(RootfsHandoffError, match="cannot select/authorize"):
        write_rootfs_handoff_assessment(promoted, tmp_path / "promoted.json")


def _run_git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def test_layout_checkout_verifier_binds_exact_commit_blob_and_clean_tree(tmp_path: Path):
    repo = tmp_path / "device-source"
    repo.mkdir()
    _run_git(repo, "init", "-q")
    _run_git(repo, "config", "user.email", "ci@example.invalid")
    _run_git(repo, "config", "user.name", "CI")
    _run_git(repo, "remote", "add", "origin", "https://github.com/LineageOS/android_device_oneplus_avicii")
    source = repo / "init" / "fstab.qcom"
    source.parent.mkdir()
    source.write_text("userdata /data f2fs defaults fileencryption=ice,wrappedkey\n", encoding="utf-8")
    _run_git(repo, "add", "init/fstab.qcom")
    _run_git(repo, "commit", "-q", "-m", "fixture")
    commit = _run_git(repo, "rev-parse", "HEAD")
    blob = _run_git(repo, "rev-parse", "HEAD:init/fstab.qcom")

    data = deepcopy(_data())
    data["sources"][0]["commit"] = commit
    data["rootfs_handoff"]["layout_source_blob_sha1"] = blob
    profile = _profile(data)
    evidence = verify_rootfs_handoff_layout_checkout(profile, repo)
    assert evidence.checkout_head == commit
    assert evidence.source_blob_sha1 == blob
    assert evidence.tracked_tree_clean is True
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False

    source.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(RootfsHandoffError, match="tracked modifications"):
        verify_rootfs_handoff_layout_checkout(profile, repo)
