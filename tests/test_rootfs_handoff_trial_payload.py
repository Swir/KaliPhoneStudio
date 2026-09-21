from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import io
from pathlib import Path
import tarfile

import pytest

from kaliphonestudio.rootfs_handoff_trial_execution_gate import RootfsHandoffTrialExecutionGateEvidence
from kaliphonestudio.rootfs_handoff_trial_payload import (
    RootfsHandoffTrialPayloadError,
    build_rootfs_handoff_trial_payload_manifest,
    load_rootfs_handoff_trial_payload_evidence,
    write_rootfs_handoff_trial_payload_evidence,
)


def _digest(label: str) -> str:
    return sha256(label.encode("utf-8")).hexdigest()


def _write_tar(path: Path, *, traversal: bool = False, special: bool = False) -> None:
    with tarfile.open(path, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        directory = tarfile.TarInfo("usr/bin")
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o755
        archive.addfile(directory)

        content = b"#!/bin/sh\necho kps\n"
        tool = tarfile.TarInfo("usr/bin/kps-tool")
        tool.size = len(content)
        tool.mode = 0o755
        archive.addfile(tool, io.BytesIO(content))

        symlink = tarfile.TarInfo("bin")
        symlink.type = tarfile.SYMTYPE
        symlink.linkname = "usr/bin"
        symlink.mode = 0o777
        archive.addfile(symlink)

        hardlink = tarfile.TarInfo("usr/bin/kps-tool-hard")
        hardlink.type = tarfile.LNKTYPE
        hardlink.linkname = "usr/bin/kps-tool"
        hardlink.mode = 0o755
        archive.addfile(hardlink)

        if traversal:
            bad = tarfile.TarInfo("../../escape")
            bad.size = 1
            archive.addfile(bad, io.BytesIO(b"x"))
        if special:
            bad = tarfile.TarInfo("dev/unsafe")
            bad.type = tarfile.CHRTYPE
            bad.devmajor = 1
            bad.devminor = 3
            archive.addfile(bad)


def _gate(archive: Path, *, required_free_bytes: int = 128 * 1024 * 1024) -> RootfsHandoffTrialExecutionGateEvidence:
    artifact = archive.read_bytes()
    return RootfsHandoffTrialExecutionGateEvidence(
        schema_version=1,
        execution_gate_policy="rootfs-handoff-interactive-execution-gate-v1",
        profile_id="oneplus/avicii",
        device_serial="SERIAL-TEST-001",
        firmware_build="OxygenOS-test",
        firmware_fingerprint="oneplus/avicii/test:user/release-keys",
        trial_plan_sha256=_digest("trial-plan"),
        trial_preflight_sha256=_digest("trial-preflight"),
        trial_authorization_sha256=_digest("trial-authorization"),
        target_binding_sha256=_digest("target-binding"),
        authorized_fresh_revalidation_sha256=_digest("authorized-revalidation"),
        execution_fresh_revalidation_sha256=_digest("execution-revalidation"),
        authorized_storage_discovery_sha256=_digest("authorized-discovery"),
        execution_storage_discovery_sha256=_digest("execution-discovery"),
        execution_storage_report_sha256=_digest("execution-report"),
        execution_storage_report_size=4096,
        candidate_partition_role="rootfs_candidate",
        observed_kernel_name="sda",
        observed_filesystem="ext4",
        observed_encryption_state="unencrypted",
        observed_free_bytes=256 * 1024 * 1024,
        required_free_bytes=required_free_bytes,
        staging_subpath="kaliphonestudio/rootfs-stage",
        rootfs_artifact_sha256=sha256(artifact).hexdigest(),
        rootfs_artifact_size=len(artifact),
        recovery_plan_sha256=_digest("recovery-plan"),
        exact_trial_plan_bound=True,
        exact_preflight_bound=True,
        authorized_revalidation_bound=True,
        distinct_execution_capture_bound=True,
        live_device_identity_revalidated=True,
        live_firmware_revalidated=True,
        live_target_identity_revalidated=True,
        live_filesystem_encryption_capacity_revalidated=True,
        local_rootfs_exact_bytes_verified=True,
        recovery_plan_identity_revalidated=True,
        execution_gate_passed=True,
        explicit_operator_confirmation_required=True,
        write_scope_confirmation_required=True,
        raw_device_path_resolution_required=True,
        interactive_writer_required=True,
        physical_gate_still_incomplete=True,
        physical_interaction_performed=False,
        external_device_command_executed=False,
        raw_device_path_bound=False,
        mount_target_bound=False,
        trial_execution_allowed=False,
        persistent_write_authorized=False,
        persistent_write_performed=False,
        phone_storage_written=False,
        storage_verified=False,
        recovery_verified=False,
        hardware_verified=False,
        beta_release_authorized=False,
        beta_gate_credit=False,
    )


def _write_gate(path: Path, gate: RootfsHandoffTrialExecutionGateEvidence) -> None:
    path.write_text(gate.canonical_json(), encoding="utf-8", newline="\n")


def test_build_manifest_binds_exact_gate_and_expanded_scope(tmp_path: Path) -> None:
    archive = tmp_path / "rootfs.tar.gz"
    _write_tar(archive)
    gate = _gate(archive)
    gate_path = tmp_path / "execution-gate.json"
    _write_gate(gate_path, gate)

    evidence = build_rootfs_handoff_trial_payload_manifest(gate_path, archive)

    assert evidence.execution_gate_sha256 == gate.evidence_sha256()
    assert evidence.rootfs_artifact_sha256 == gate.rootfs_artifact_sha256
    assert evidence.regular_file_count == 1
    assert evidence.directory_count == 1
    assert evidence.symlink_count == 1
    assert evidence.hardlink_count == 1
    assert evidence.regular_payload_bytes == len(b"#!/bin/sh\necho kps\n")
    assert evidence.minimum_required_free_bytes > evidence.regular_payload_bytes
    assert evidence.deterministic_write_scope_manifested is True
    assert evidence.persistent_write_authorized is False
    assert evidence.phone_storage_written is False
    assert [entry.path for entry in evidence.entries] == [
        "bin",
        "usr/bin",
        "usr/bin/kps-tool",
        "usr/bin/kps-tool-hard",
    ]
    tool = next(entry for entry in evidence.entries if entry.path == "usr/bin/kps-tool")
    assert tool.content_sha256 == sha256(b"#!/bin/sh\necho kps\n").hexdigest()


def test_manifest_roundtrip_is_canonical_and_create_only(tmp_path: Path) -> None:
    archive = tmp_path / "rootfs.tar.gz"
    _write_tar(archive)
    gate = _gate(archive)
    gate_path = tmp_path / "execution-gate.json"
    _write_gate(gate_path, gate)
    evidence = build_rootfs_handoff_trial_payload_manifest(gate_path, archive)
    out = tmp_path / "payload-manifest.json"

    digest = write_rootfs_handoff_trial_payload_evidence(evidence, out)
    loaded = load_rootfs_handoff_trial_payload_evidence(out)

    assert digest == evidence.evidence_sha256()
    assert loaded == evidence
    with pytest.raises(RootfsHandoffTrialPayloadError, match="refusing to overwrite"):
        write_rootfs_handoff_trial_payload_evidence(evidence, out)


def test_rejects_path_traversal_before_any_write_scope(tmp_path: Path) -> None:
    archive = tmp_path / "rootfs.tar.gz"
    _write_tar(archive, traversal=True)
    gate = _gate(archive)
    gate_path = tmp_path / "execution-gate.json"
    _write_gate(gate_path, gate)

    with pytest.raises(RootfsHandoffTrialPayloadError, match="normalized relative path|escapes|relative"):
        build_rootfs_handoff_trial_payload_manifest(gate_path, archive)


def test_rejects_special_tar_members(tmp_path: Path) -> None:
    archive = tmp_path / "rootfs.tar.gz"
    _write_tar(archive, special=True)
    gate = _gate(archive)
    gate_path = tmp_path / "execution-gate.json"
    _write_gate(gate_path, gate)

    with pytest.raises(RootfsHandoffTrialPayloadError, match="unsupported special tar member"):
        build_rootfs_handoff_trial_payload_manifest(gate_path, archive)


def test_rejects_capacity_review_that_only_covers_compressed_archive(tmp_path: Path) -> None:
    archive = tmp_path / "rootfs.tar.gz"
    _write_tar(archive)
    base = _gate(archive)
    gate = replace(base, required_free_bytes=max(base.rootfs_artifact_size, 1))
    gate_path = tmp_path / "execution-gate.json"
    _write_gate(gate_path, gate)

    with pytest.raises(RootfsHandoffTrialPayloadError, match="expanded payload plus deterministic safety margin"):
        build_rootfs_handoff_trial_payload_manifest(gate_path, archive)
