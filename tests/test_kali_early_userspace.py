from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import tarfile

import pytest

from kaliphonestudio.candidate_authority_bundle import FirstBootAuthorityBundleEvidence
from kaliphonestudio.candidate_rootfs_authority import FirstBootRootfsAuthorityEvidence
from kaliphonestudio.kali_early_userspace import (
    KaliEarlyUserspaceError,
    build_kali_early_userspace_probe_bundle,
    create_kali_early_userspace_probe_plan,
    load_kali_early_userspace_bundle_evidence,
    verify_kali_early_userspace_probe_bundle,
    write_kali_early_userspace_bundle_evidence,
    write_kali_early_userspace_plan,
)
from kaliphonestudio.physical_candidate_gate import PhysicalCandidateGateEvidence
from kaliphonestudio.physical_kali_early_userspace import (
    PhysicalKaliEarlyUserspaceError,
    record_physical_kali_early_userspace_observation,
    write_physical_kali_early_userspace_evidence,
)
from kaliphonestudio.profiles import DeviceProfile
from kaliphonestudio.temporary_boot_execution import TemporaryBootExecutionEvidence


def _d(char: str) -> str:
    return char * 64


def _rootfs(profile_id: str = "vendor/test") -> FirstBootRootfsAuthorityEvidence:
    return FirstBootRootfsAuthorityEvidence(
        schema_version=1,
        profile_id=profile_id,
        first_boot_manifest_sha256=_d("1"),
        first_boot_rootfs_provenance_sha256=_d("2"),
        rootfs_authority_sha256=_d("3"),
        authority_name="kali-arm64-test",
        authority_run_id=123,
        authority_commit="a" * 40,
        authority_artifact_id=456,
        release_tag="2026.2",
        architecture="arm64",
        variant="minimal",
        rootfs_evidence_sha256=_d("4"),
        rootfs_canonicalization_binding_sha256=_d("5"),
        canonicalization_policy_sha256=_d("6"),
        artifact_sha256=_d("7"),
        artifact_size=137_460_600,
        package_manifest_sha256=_d("8"),
        package_count=269,
        source_lock_sha256=_d("9"),
        repository_snapshot_sha256=_d("a"),
        inrelease_sha256=_d("b"),
        strict_byte_identical=True,
        reviewed=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def _authorities(rootfs: FirstBootRootfsAuthorityEvidence, profile_id: str = "vendor/test") -> FirstBootAuthorityBundleEvidence:
    return FirstBootAuthorityBundleEvidence(
        schema_version=1,
        profile_id=profile_id,
        first_boot_manifest_sha256=rootfs.first_boot_manifest_sha256,
        kernel_binding_sha256=_d("c"),
        rootfs_binding_sha256=rootfs.evidence_sha256(),
        device_tree_binding_sha256=_d("d"),
        kernel_authority_sha256=_d("e"),
        rootfs_authority_sha256=rootfs.rootfs_authority_sha256,
        device_tree_authority_sha256=_d("f"),
        kernel_authority_run_id=11,
        kernel_authority_commit="b" * 40,
        kernel_authority_artifact_id=12,
        rootfs_authority_run_id=rootfs.authority_run_id,
        rootfs_authority_commit=rootfs.authority_commit,
        rootfs_authority_artifact_id=rootfs.authority_artifact_id,
        device_tree_authority_run_id=13,
        device_tree_authority_commit="c" * 40,
        device_tree_authority_artifact_id=14,
        kernel_image_sha256=_d("0"),
        rootfs_artifact_sha256=rootfs.artifact_sha256,
        dtb_sha256=_d("1"),
        dtbo_image_sha256=_d("2"),
        all_authorities_reviewed=True,
        all_required_artifacts_strict=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def _execution(profile_id: str = "vendor/test", serial: str = "SERIAL-001", authorization: str = _d("a")) -> TemporaryBootExecutionEvidence:
    return TemporaryBootExecutionEvidence(
        schema_version=1,
        profile_id=profile_id,
        device_serial=serial,
        offer_sha256=_d("b"),
        authorization_sha256=authorization,
        runtime_probe_sha256=_d("c"),
        argv_sha256=_d("d"),
        returncode=0,
        output_sha256=_d("e"),
        output_size=42,
        execution_policy="single-serial-fastboot-boot-no-persistent-write-v1",
        command_invoked=True,
        temporary_boot_executed=True,
        temporary_boot_command_succeeded=True,
        persistent_write=False,
        phone_storage_written=False,
        kali_userspace_verified=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def _gate(authorities, serial: str = "SERIAL-001", authorization: str = _d("a")) -> PhysicalCandidateGateEvidence:
    return PhysicalCandidateGateEvidence(
        schema_version=1,
        profile_id=authorities.profile_id,
        device_serial=serial,
        firmware_build="OOS-TEST",
        firmware_fingerprint="oneplus/test/fingerprint",
        physical_baseline_bundle_sha256=_d("3"),
        fastboot_capture_bundle_sha256=_d("4"),
        fastboot_baseline_evidence_sha256=_d("5"),
        fastboot_transcript_sha256=_d("6"),
        stock_provenance_sha256=_d("7"),
        stock_ota_sha256=_d("8"),
        stock_boot_sha256=_d("9"),
        first_boot_manifest_sha256=authorities.first_boot_manifest_sha256,
        first_boot_authority_bundle_sha256=authorities.evidence_sha256(),
        boot_authorization_sha256=authorization,
        boot_plan_sha256=_d("b"),
        boot_image_sha256=_d("c"),
        boot_image_size=50_000_000,
        kernel_image_sha256=authorities.kernel_image_sha256,
        rootfs_artifact_sha256=authorities.rootfs_artifact_sha256,
        dtb_sha256=authorities.dtb_sha256,
        dtbo_image_sha256=authorities.dtbo_image_sha256,
        reviewed_authorities_bound=True,
        exact_physical_baseline_bound=True,
        ready_for_temporary_boot_offer=True,
        temporary_boot_executed=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def _profile(tmp_path: Path) -> DeviceProfile:
    return DeviceProfile(path=tmp_path / "profile.json", data={"profile_id": "vendor/test"})


def _transcript(path: Path, bundle, *, probe_id: str | None = None, conflict: bool = False) -> bytes:
    lines = [
        b"kernel: reached userspace",
        b"KPS_KALI_STAGE=rootfs-systemd-early-v1",
        b"KPS_KALI_PROBE_ID=" + (probe_id or bundle.probe_id).encode("ascii"),
        b"KPS_KALI_MANIFEST_SHA256=" + bundle.first_boot_manifest_sha256.encode("ascii"),
        b"KPS_KALI_ROOTFS_AUTHORITY_SHA256=" + bundle.rootfs_authority_sha256.encode("ascii"),
        b"KPS_KALI_ROOTFS_ARTIFACT_SHA256=" + bundle.rootfs_artifact_sha256.encode("ascii"),
    ]
    if conflict:
        lines.append(b"KPS_KALI_ROOTFS_ARTIFACT_SHA256=" + _d("f").encode("ascii"))
    raw = b"\r\n".join(lines) + b"\r\n"
    path.write_bytes(raw)
    return raw


def test_probe_plan_is_exactly_bound_to_reviewed_rootfs_authority() -> None:
    rootfs = _rootfs()
    authorities = _authorities(rootfs)
    plan = create_kali_early_userspace_probe_plan(authorities, rootfs)
    assert plan.first_boot_manifest_sha256 == authorities.first_boot_manifest_sha256
    assert plan.first_boot_authority_bundle_sha256 == authorities.evidence_sha256()
    assert plan.rootfs_authority_binding_sha256 == rootfs.evidence_sha256()
    assert plan.rootfs_authority_sha256 == rootfs.rootfs_authority_sha256
    assert plan.rootfs_artifact_sha256 == rootfs.artifact_sha256
    assert plan.probe_policy == "kali-rootfs-systemd-early-v1"
    assert len(plan.probe_id) == 64
    assert plan.hardware_verified is False
    assert plan.beta_gate_credit is False


def test_probe_plan_rejects_detached_rootfs_binding() -> None:
    rootfs = _rootfs()
    authorities = replace(_authorities(rootfs), rootfs_binding_sha256=_d("f"))
    with pytest.raises(KaliEarlyUserspaceError, match="digest does not match"):
        create_kali_early_userspace_probe_plan(authorities, rootfs)


def test_probe_bundle_is_deterministic_and_contains_only_exact_members(tmp_path: Path) -> None:
    rootfs = _rootfs()
    plan = create_kali_early_userspace_probe_plan(_authorities(rootfs), rootfs)
    a, b = tmp_path / "a.tar", tmp_path / "b.tar"
    evidence_a = build_kali_early_userspace_probe_bundle(plan, a)
    evidence_b = build_kali_early_userspace_probe_bundle(plan, b)
    assert a.read_bytes() == b.read_bytes()
    assert evidence_a.bundle_sha256 == evidence_b.bundle_sha256
    assert evidence_a.member_count == 5
    assert evidence_a.systemd_activation_bound is True
    assert evidence_a.credentials_embedded is False
    assert evidence_a.remote_access_enabled is False
    assert evidence_a.phone_storage_written is False

    with tarfile.open(a, "r:") as archive:
        names = [m.name for m in archive.getmembers()]
        assert names == sorted(names)
        link = archive.getmember("etc/systemd/system/basic.target.wants/kaliphonestudio-early-userspace-proof.service")
        assert link.issym()
        assert link.linkname == "../../../../usr/lib/systemd/system/kaliphonestudio-early-userspace-proof.service"
        script_file = archive.extractfile("usr/libexec/kaliphonestudio/emit-early-userspace-proof")
        assert script_file is not None
        script = script_file.read().decode()
        assert "KPS_KALI_STAGE=rootfs-systemd-early-v1" in script
        assert plan.probe_id in script
        assert "fastboot" not in script.lower()
        assert "ssh" not in script.lower()


def test_bundle_verifier_rejects_changed_bytes(tmp_path: Path) -> None:
    rootfs = _rootfs()
    plan = create_kali_early_userspace_probe_plan(_authorities(rootfs), rootfs)
    bundle = tmp_path / "probe.tar"
    evidence = build_kali_early_userspace_probe_bundle(plan, bundle)
    bundle.write_bytes(bundle.read_bytes() + b"x")
    with pytest.raises(KaliEarlyUserspaceError, match="bytes do not match"):
        verify_kali_early_userspace_probe_bundle(plan, evidence, bundle)


def test_plan_and_evidence_writers_are_immutable_and_round_trip(tmp_path: Path) -> None:
    rootfs = _rootfs()
    plan = create_kali_early_userspace_probe_plan(_authorities(rootfs), rootfs)
    bundle = tmp_path / "probe.tar"
    evidence = build_kali_early_userspace_probe_bundle(plan, bundle)
    plan_path = tmp_path / "plan.json"
    evidence_path = tmp_path / "evidence.json"
    assert write_kali_early_userspace_plan(plan, plan_path) == plan.plan_sha256()
    assert write_kali_early_userspace_bundle_evidence(evidence, evidence_path) == evidence.evidence_sha256()
    assert load_kali_early_userspace_bundle_evidence(evidence_path) == evidence
    with pytest.raises(KaliEarlyUserspaceError, match="overwrite"):
        write_kali_early_userspace_bundle_evidence(evidence, evidence_path)


def test_exact_physical_markers_create_observation_without_automatic_verification(tmp_path: Path) -> None:
    rootfs = _rootfs()
    authorities = _authorities(rootfs)
    plan = create_kali_early_userspace_probe_plan(authorities, rootfs)
    bundle = build_kali_early_userspace_probe_bundle(plan, tmp_path / "probe.tar")
    gate = _gate(authorities)
    execution = _execution()
    transcript = tmp_path / "console.log"
    raw = _transcript(transcript, bundle)

    evidence = record_physical_kali_early_userspace_observation(
        _profile(tmp_path), execution, gate, bundle, transcript
    )
    assert evidence.transcript_sha256 == sha256(raw).hexdigest()
    assert evidence.exact_candidate_identity_bound is True
    assert evidence.exact_rootfs_identity_bound is True
    assert evidence.kali_systemd_early_signal_observed is True
    assert evidence.kali_rootfs_signal_observed is True
    assert evidence.kali_early_userspace_verified is False
    assert evidence.manual_review_required is True
    assert evidence.phone_storage_written is False
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False


def test_wrong_probe_or_conflicting_rootfs_marker_is_rejected(tmp_path: Path) -> None:
    rootfs = _rootfs()
    authorities = _authorities(rootfs)
    plan = create_kali_early_userspace_probe_plan(authorities, rootfs)
    bundle = build_kali_early_userspace_probe_bundle(plan, tmp_path / "probe.tar")
    transcript = tmp_path / "console.log"
    _transcript(transcript, bundle, probe_id=_d("f"))
    with pytest.raises(PhysicalKaliEarlyUserspaceError, match="conflicting probe id"):
        record_physical_kali_early_userspace_observation(_profile(tmp_path), _execution(), _gate(authorities), bundle, transcript)
    _transcript(transcript, bundle, conflict=True)
    with pytest.raises(PhysicalKaliEarlyUserspaceError, match="conflicting rootfs artifact"):
        record_physical_kali_early_userspace_observation(_profile(tmp_path), _execution(), _gate(authorities), bundle, transcript)


def test_detached_candidate_gate_and_failed_execution_are_rejected(tmp_path: Path) -> None:
    rootfs = _rootfs()
    authorities = _authorities(rootfs)
    plan = create_kali_early_userspace_probe_plan(authorities, rootfs)
    bundle = build_kali_early_userspace_probe_bundle(plan, tmp_path / "probe.tar")
    transcript = tmp_path / "console.log"
    _transcript(transcript, bundle)

    bad_gate = replace(_gate(authorities), first_boot_manifest_sha256=_d("f"))
    with pytest.raises(PhysicalKaliEarlyUserspaceError, match="detached from physical candidate manifest"):
        record_physical_kali_early_userspace_observation(_profile(tmp_path), _execution(), bad_gate, bundle, transcript)

    failed = replace(_execution(), returncode=1, temporary_boot_command_succeeded=False)
    with pytest.raises(PhysicalKaliEarlyUserspaceError, match="successful Fastboot boot command"):
        record_physical_kali_early_userspace_observation(_profile(tmp_path), failed, _gate(authorities), bundle, transcript)


def test_physical_evidence_writer_is_immutable(tmp_path: Path) -> None:
    rootfs = _rootfs()
    authorities = _authorities(rootfs)
    plan = create_kali_early_userspace_probe_plan(authorities, rootfs)
    bundle = build_kali_early_userspace_probe_bundle(plan, tmp_path / "probe.tar")
    transcript = tmp_path / "console.log"
    _transcript(transcript, bundle)
    evidence = record_physical_kali_early_userspace_observation(_profile(tmp_path), _execution(), _gate(authorities), bundle, transcript)
    out = tmp_path / "physical.json"
    assert write_physical_kali_early_userspace_evidence(evidence, out) == evidence.evidence_sha256()
    with pytest.raises(PhysicalKaliEarlyUserspaceError, match="overwrite"):
        write_physical_kali_early_userspace_evidence(evidence, out)
