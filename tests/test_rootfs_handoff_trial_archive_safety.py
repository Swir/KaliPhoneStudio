from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import io
from pathlib import Path
from types import SimpleNamespace
import tarfile

import pytest

import kaliphonestudio.rootfs_handoff_trial_archive_safety as safety
from kaliphonestudio.rootfs_handoff_trial_archive_safety import (
    RootfsHandoffTrialArchiveSafetyError,
    build_rootfs_handoff_trial_archive_safety_evidence,
    load_rootfs_handoff_trial_archive_safety_evidence,
    validate_rootfs_handoff_trial_archive_safety_evidence,
    write_rootfs_handoff_trial_archive_safety_evidence,
)


def _add_file(archive: tarfile.TarFile, name: str, content: bytes = b"payload") -> None:
    item = tarfile.TarInfo(name)
    item.size = len(content)
    item.mode = 0o755
    archive.addfile(item, io.BytesIO(content))


def _metadata(archive: Path, entries: tuple[SimpleNamespace, ...]) -> SimpleNamespace:
    digest = sha256(archive.read_bytes()).hexdigest()
    return SimpleNamespace(
        profile_id="oneplus/avicii",
        device_serial="SERIAL-TEST",
        payload_manifest_sha256="2" * 64,
        rootfs_artifact_sha256=digest,
        rootfs_artifact_size=archive.stat().st_size,
        entries=entries,
        persistent_write_authorized=False,
        persistent_write_performed=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_release_authorized=False,
        beta_gate_credit=False,
        evidence_sha256=lambda: "3" * 64,
    )


def _patch_metadata(monkeypatch: pytest.MonkeyPatch, metadata: SimpleNamespace) -> None:
    monkeypatch.setattr(safety, "load_rootfs_handoff_trial_metadata_evidence", lambda _path: metadata)
    monkeypatch.setattr(safety, "validate_rootfs_handoff_trial_metadata_evidence", lambda _value: None)


def test_archive_safety_accepts_namespace_safe_links_and_binds_exact_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_path = tmp_path / "rootfs.tar"
    with tarfile.open(archive_path, "w", format=tarfile.PAX_FORMAT) as archive:
        directory = tarfile.TarInfo("usr/bin")
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o755
        archive.addfile(directory)
        _add_file(archive, "usr/bin/tool")
        relative = tarfile.TarInfo("usr/bin/tool-rel")
        relative.type = tarfile.SYMTYPE
        relative.linkname = "tool"
        relative.mode = 0o777
        archive.addfile(relative)
        absolute = tarfile.TarInfo("usr/bin/tool-abs")
        absolute.type = tarfile.SYMTYPE
        absolute.linkname = "/usr/bin/tool"
        absolute.mode = 0o777
        archive.addfile(absolute)
        hardlink = tarfile.TarInfo("usr/bin/tool-hard")
        hardlink.type = tarfile.LNKTYPE
        hardlink.linkname = "usr/bin/tool"
        hardlink.mode = 0o755
        archive.addfile(hardlink)

    entries = (
        SimpleNamespace(path="usr/bin", kind="dir"),
        SimpleNamespace(path="usr/bin/tool", kind="file"),
        SimpleNamespace(path="usr/bin/tool-rel", kind="symlink"),
        SimpleNamespace(path="usr/bin/tool-abs", kind="symlink"),
        SimpleNamespace(path="usr/bin/tool-hard", kind="hardlink"),
    )
    metadata = _metadata(archive_path, entries)
    _patch_metadata(monkeypatch, metadata)

    evidence = build_rootfs_handoff_trial_archive_safety_evidence(tmp_path / "metadata.json", archive_path)

    assert evidence.entry_count == 5
    assert evidence.symlink_count == 2
    assert evidence.absolute_symlink_count == 1
    assert evidence.relative_symlink_count == 1
    assert evidence.hardlink_count == 1
    assert evidence.no_link_ancestor_pivots is True
    assert evidence.hardlink_targets_resolved is True
    assert evidence.extraction_performed is False
    assert evidence.persistent_write_authorized is False
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False


def test_archive_safety_rejects_symlink_target_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_path = tmp_path / "rootfs.tar"
    with tarfile.open(archive_path, "w") as archive:
        bad = tarfile.TarInfo("usr/bin/bad")
        bad.type = tarfile.SYMTYPE
        bad.linkname = "../../../host"
        archive.addfile(bad)
    metadata = _metadata(archive_path, (SimpleNamespace(path="usr/bin/bad", kind="symlink"),))
    _patch_metadata(monkeypatch, metadata)

    with pytest.raises(RootfsHandoffTrialArchiveSafetyError, match="symlink target escapes"):
        build_rootfs_handoff_trial_archive_safety_evidence(tmp_path / "metadata.json", archive_path)


def test_archive_safety_rejects_link_ancestor_pivot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_path = tmp_path / "rootfs.tar"
    with tarfile.open(archive_path, "w") as archive:
        pivot = tarfile.TarInfo("usr/current")
        pivot.type = tarfile.SYMTYPE
        pivot.linkname = "lib"
        archive.addfile(pivot)
        _add_file(archive, "usr/current/payload")
    entries = (
        SimpleNamespace(path="usr/current", kind="symlink"),
        SimpleNamespace(path="usr/current/payload", kind="file"),
    )
    metadata = _metadata(archive_path, entries)
    _patch_metadata(monkeypatch, metadata)

    with pytest.raises(RootfsHandoffTrialArchiveSafetyError, match="nested below link pivot"):
        build_rootfs_handoff_trial_archive_safety_evidence(tmp_path / "metadata.json", archive_path)


def test_archive_safety_rejects_unresolved_hardlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_path = tmp_path / "rootfs.tar"
    with tarfile.open(archive_path, "w") as archive:
        hardlink = tarfile.TarInfo("usr/bin/missing-hard")
        hardlink.type = tarfile.LNKTYPE
        hardlink.linkname = "usr/bin/missing"
        archive.addfile(hardlink)
    metadata = _metadata(
        archive_path,
        (SimpleNamespace(path="usr/bin/missing-hard", kind="hardlink"),),
    )
    _patch_metadata(monkeypatch, metadata)

    with pytest.raises(RootfsHandoffTrialArchiveSafetyError, match="missing or not a regular file"):
        build_rootfs_handoff_trial_archive_safety_evidence(tmp_path / "metadata.json", archive_path)


def test_archive_safety_evidence_roundtrip_is_canonical_and_create_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_path = tmp_path / "rootfs.tar"
    with tarfile.open(archive_path, "w") as archive:
        _add_file(archive, "usr/bin/tool")
    metadata = _metadata(archive_path, (SimpleNamespace(path="usr/bin/tool", kind="file"),))
    _patch_metadata(monkeypatch, metadata)
    evidence = build_rootfs_handoff_trial_archive_safety_evidence(
        tmp_path / "metadata.json", archive_path
    )
    out = tmp_path / "archive-safety.json"

    digest = write_rootfs_handoff_trial_archive_safety_evidence(evidence, out)
    assert digest == evidence.evidence_sha256()
    assert load_rootfs_handoff_trial_archive_safety_evidence(out) == evidence
    with pytest.raises(RootfsHandoffTrialArchiveSafetyError, match="refusing to overwrite"):
        write_rootfs_handoff_trial_archive_safety_evidence(evidence, out)


def test_archive_safety_rejects_special_member_and_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_path = tmp_path / "rootfs.tar"
    with tarfile.open(archive_path, "w") as archive:
        fifo = tarfile.TarInfo("run/unsafe-fifo")
        fifo.type = tarfile.FIFOTYPE
        archive.addfile(fifo)
    metadata = _metadata(archive_path, (SimpleNamespace(path="run/unsafe-fifo", kind="fifo"),))
    _patch_metadata(monkeypatch, metadata)

    with pytest.raises(RootfsHandoffTrialArchiveSafetyError, match="special archive member"):
        build_rootfs_handoff_trial_archive_safety_evidence(tmp_path / "metadata.json", archive_path)

    safe = safety.RootfsHandoffTrialArchiveSafetyEvidence(
        1,
        "exact-rootfs-archive-extraction-safety-v1",
        "oneplus/avicii",
        "SERIAL-TEST",
        "1" * 64,
        "2" * 64,
        "3" * 64,
        1,
        1,
        0,
        0,
        0,
        0,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
    )
    with pytest.raises(RootfsHandoffTrialArchiveSafetyError, match="safety flags"):
        validate_rootfs_handoff_trial_archive_safety_evidence(replace(safe, beta_gate_credit=True))
