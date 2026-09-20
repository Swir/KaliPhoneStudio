from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import io
from pathlib import Path
from types import SimpleNamespace
import tarfile

import pytest

import kaliphonestudio.rootfs_handoff_trial_metadata as metadata
from kaliphonestudio.rootfs_handoff_trial_metadata import (
    RootfsHandoffTrialMetadataError,
    build_rootfs_handoff_trial_metadata_manifest,
    load_rootfs_handoff_trial_metadata_evidence,
    write_rootfs_handoff_trial_metadata_evidence,
)


def _write_rootfs(path: Path) -> None:
    with tarfile.open(path, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        directory = tarfile.TarInfo("usr/bin")
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o755
        directory.uid = 0
        directory.gid = 0
        directory.uname = "root"
        directory.gname = "root"
        archive.addfile(directory)

        content = b"#!/bin/sh\necho kps\n"
        tool = tarfile.TarInfo("usr/bin/kps-tool")
        tool.size = len(content)
        tool.mode = 0o755
        tool.uid = 1000
        tool.gid = 1001
        tool.uname = "kali"
        tool.gname = "kali"
        tool.pax_headers = {
            "SCHILY.xattr.security.capability": "cap_net_raw=ep",
            "KPS.review-note": "preserve-me",
            "mtime": "123.0",
        }
        archive.addfile(tool, io.BytesIO(content))


def _payload(archive: Path) -> SimpleNamespace:
    digest = sha256(archive.read_bytes()).hexdigest()
    entries = (
        SimpleNamespace(path="usr/bin", kind="dir", mode=0o755, size=0, link_target=None),
        SimpleNamespace(
            path="usr/bin/kps-tool", kind="file", mode=0o755,
            size=len(b"#!/bin/sh\necho kps\n"), link_target=None,
        ),
    )
    return SimpleNamespace(
        deterministic_write_scope_manifested=True,
        interactive_writer_still_required=True,
        persistent_write_authorized=False,
        persistent_write_performed=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_release_authorized=False,
        beta_gate_credit=False,
        rootfs_artifact_size=archive.stat().st_size,
        rootfs_artifact_sha256=digest,
        entries=entries,
        profile_id="oneplus/avicii",
        device_serial="SERIAL-TEST",
        execution_gate_sha256="1" * 64,
        evidence_sha256=lambda: "2" * 64,
    )


def _patch_payload(monkeypatch: pytest.MonkeyPatch, payload: SimpleNamespace) -> None:
    monkeypatch.setattr(metadata, "load_rootfs_handoff_trial_payload_evidence", lambda _path: payload)
    monkeypatch.setattr(metadata, "validate_rootfs_handoff_trial_payload_evidence", lambda _value: None)


def test_metadata_manifest_binds_ownership_and_non_structural_pax(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "rootfs.tar.gz"
    _write_rootfs(archive)
    payload = _payload(archive)
    _patch_payload(monkeypatch, payload)

    evidence = build_rootfs_handoff_trial_metadata_manifest(tmp_path / "payload.json", archive)

    assert evidence.entry_count == 2
    assert evidence.pax_header_count == 2
    assert evidence.security_metadata_entry_count == 1
    tool = next(item for item in evidence.entries if item.path == "usr/bin/kps-tool")
    assert (tool.uid, tool.gid, tool.uname, tool.gname) == (1000, 1001, "kali", "kali")
    assert ("SCHILY.xattr.security.capability", "cap_net_raw=ep") in tool.pax_headers
    assert ("KPS.review-note", "preserve-me") in tool.pax_headers
    assert all(key != "mtime" for key, _value in tool.pax_headers)
    assert evidence.posix_ownership_manifested is True
    assert evidence.pax_metadata_manifested is True
    assert evidence.interactive_writer_still_required is True
    assert evidence.persistent_write_authorized is False
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False


def test_metadata_manifest_roundtrip_is_canonical_and_create_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "rootfs.tar.gz"
    _write_rootfs(archive)
    payload = _payload(archive)
    _patch_payload(monkeypatch, payload)
    evidence = build_rootfs_handoff_trial_metadata_manifest(tmp_path / "payload.json", archive)
    out = tmp_path / "metadata.json"

    digest = write_rootfs_handoff_trial_metadata_evidence(evidence, out)
    assert digest == evidence.evidence_sha256()
    assert load_rootfs_handoff_trial_metadata_evidence(out) == evidence
    with pytest.raises(RootfsHandoffTrialMetadataError, match="refusing to overwrite"):
        write_rootfs_handoff_trial_metadata_evidence(evidence, out)


def test_metadata_manifest_rejects_member_scope_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "rootfs.tar.gz"
    _write_rootfs(archive)
    payload = _payload(archive)
    payload.entries = payload.entries[:1]
    _patch_payload(monkeypatch, payload)

    with pytest.raises(RootfsHandoffTrialMetadataError, match="absent from payload manifest"):
        build_rootfs_handoff_trial_metadata_manifest(tmp_path / "payload.json", archive)


def test_metadata_manifest_rejects_promotion_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "rootfs.tar.gz"
    _write_rootfs(archive)
    payload = _payload(archive)
    _patch_payload(monkeypatch, payload)
    evidence = build_rootfs_handoff_trial_metadata_manifest(tmp_path / "payload.json", archive)

    with pytest.raises(RootfsHandoffTrialMetadataError, match="safety flags"):
        metadata.validate_rootfs_handoff_trial_metadata_evidence(
            replace(evidence, beta_gate_credit=True)
        )
