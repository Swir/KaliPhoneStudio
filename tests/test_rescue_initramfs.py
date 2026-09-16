from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import pytest

from kaliphonestudio.rescue_evidence import (
    evidence_from_dict,
    load_rescue_initramfs_evidence,
    verify_rescue_initramfs_artifact,
)
from kaliphonestudio.rescue_initramfs import (
    RescueInitramfsError,
    build_reproducible_rescue_initramfs,
)


def _make_tree(root: Path) -> None:
    (root / "bin").mkdir(parents=True)
    init = root / "init"
    init.write_text("#!/bin/sh\nexec /bin/rescue-shell\n", encoding="utf-8")
    init.chmod(0o755)
    shell = root / "bin" / "rescue-shell"
    shell.write_bytes(b"ELF-placeholder")
    shell.chmod(0o755)
    (root / "bin" / "sh").symlink_to("rescue-shell")


def _built_rescue(tmp_path: Path):
    source = tmp_path / "root"
    source.mkdir()
    _make_tree(source)
    out = tmp_path / "rescue.cpio"
    evidence_path = tmp_path / "rescue.json"
    evidence = build_reproducible_rescue_initramfs(source, out, evidence_path)
    return source, out, evidence_path, evidence


def test_reproducible_newc_and_evidence(tmp_path: Path) -> None:
    source = tmp_path / "root"
    source.mkdir()
    _make_tree(source)
    out = tmp_path / "artifacts" / "rescue.cpio"
    evidence_path = tmp_path / "evidence" / "rescue.json"

    evidence = build_reproducible_rescue_initramfs(
        source, out, evidence_path, source_date_epoch=1234
    )

    assert evidence.reproducible is True
    assert evidence.archive_format == "newc"
    assert evidence.compression == "none"
    assert evidence.entry_count == 4
    assert evidence.artifact_sha256 == sha256(out.read_bytes()).hexdigest()
    assert out.read_bytes().startswith(b"070701")
    assert b"TRAILER!!!\x00" in out.read_bytes()
    assert len(out.read_bytes()) % 512 == 0
    raw = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert raw["source_tree_sha256"] == evidence.source_tree_sha256
    assert raw["init_sha256"] == sha256((source / "init").read_bytes()).hexdigest()

    reloaded = load_rescue_initramfs_evidence(evidence_path)
    assert reloaded == evidence
    verify_rescue_initramfs_artifact(out, reloaded)


def test_same_tree_gives_same_artifact_across_separate_publications(tmp_path: Path) -> None:
    source = tmp_path / "root"
    source.mkdir()
    _make_tree(source)
    first = tmp_path / "first.cpio"
    first_evidence = tmp_path / "first.json"
    second = tmp_path / "second.cpio"
    second_evidence = tmp_path / "second.json"

    a = build_reproducible_rescue_initramfs(source, first, first_evidence)
    b = build_reproducible_rescue_initramfs(source, second, second_evidence)

    assert first.read_bytes() == second.read_bytes()
    assert a == b


def test_rejects_missing_or_non_executable_init(tmp_path: Path) -> None:
    source = tmp_path / "root"
    source.mkdir()
    (source / "bin").mkdir()
    (source / "bin" / "tool").write_text("x", encoding="utf-8")
    with pytest.raises(RescueInitramfsError, match="executable regular /init"):
        build_reproducible_rescue_initramfs(source, tmp_path / "a", tmp_path / "e")

    init = source / "init"
    init.write_text("#!/bin/sh\n", encoding="utf-8")
    init.chmod(0o644)
    with pytest.raises(RescueInitramfsError, match="/init must be executable"):
        build_reproducible_rescue_initramfs(source, tmp_path / "a", tmp_path / "e")


def test_rejects_symlink_escape_and_absolute_target(tmp_path: Path) -> None:
    source = tmp_path / "root"
    source.mkdir()
    init = source / "init"
    init.write_text("#!/bin/sh\n", encoding="utf-8")
    init.chmod(0o755)
    (source / "bad").symlink_to("../outside")
    with pytest.raises(RescueInitramfsError, match="escapes rescue root"):
        build_reproducible_rescue_initramfs(source, tmp_path / "a", tmp_path / "e")

    (source / "bad").unlink()
    (source / "bad").symlink_to("/etc/passwd")
    with pytest.raises(RescueInitramfsError, match="absolute symlink"):
        build_reproducible_rescue_initramfs(source, tmp_path / "a", tmp_path / "e")


def test_rejects_world_writable_regular_file(tmp_path: Path) -> None:
    source = tmp_path / "root"
    source.mkdir()
    init = source / "init"
    init.write_text("#!/bin/sh\n", encoding="utf-8")
    init.chmod(0o755)
    bad = source / "bad"
    bad.write_text("unsafe", encoding="utf-8")
    bad.chmod(0o666)
    with pytest.raises(RescueInitramfsError, match="world-writable"):
        build_reproducible_rescue_initramfs(source, tmp_path / "a", tmp_path / "e")


def test_tampered_artifact_fails_evidence_revalidation(tmp_path: Path) -> None:
    _, out, evidence_path, _ = _built_rescue(tmp_path)
    evidence = load_rescue_initramfs_evidence(evidence_path)

    data = bytearray(out.read_bytes())
    data[200] ^= 1
    out.write_bytes(data)
    with pytest.raises(RescueInitramfsError, match="SHA-256"):
        verify_rescue_initramfs_artifact(out, evidence)


def test_forged_hash_cannot_hide_noncanonical_newc_metadata(tmp_path: Path) -> None:
    _, out, _, evidence = _built_rescue(tmp_path)
    data = bytearray(out.read_bytes())
    # newc field 2 is uid: magic (6) + ino (8) + mode (8) = byte 22.
    data[22:30] = b"00000001"
    out.write_bytes(data)
    forged = replace(evidence, artifact_sha256=sha256(data).hexdigest())
    with pytest.raises(RescueInitramfsError, match="metadata is not canonical"):
        verify_rescue_initramfs_artifact(out, forged)


def test_forged_hash_cannot_hide_nonzero_bytes_after_trailer(tmp_path: Path) -> None:
    _, out, _, evidence = _built_rescue(tmp_path)
    data = bytearray(out.read_bytes())
    data[-1] = 1
    out.write_bytes(data)
    forged = replace(evidence, artifact_sha256=sha256(data).hexdigest())
    with pytest.raises(RescueInitramfsError, match="Non-zero|non-zero"):
        verify_rescue_initramfs_artifact(out, forged)


def test_init_digest_is_independently_rechecked(tmp_path: Path) -> None:
    _, out, _, evidence = _built_rescue(tmp_path)
    forged = replace(evidence, init_sha256="0" * 64)
    with pytest.raises(RescueInitramfsError, match="/init SHA-256"):
        verify_rescue_initramfs_artifact(out, forged)


def test_malformed_evidence_fails_closed() -> None:
    with pytest.raises(RescueInitramfsError, match="fields"):
        evidence_from_dict({"schema_version": 1})


def test_refuses_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "root"
    source.mkdir()
    _make_tree(source)
    out = tmp_path / "rescue.cpio"
    evidence_path = tmp_path / "rescue.json"
    out.write_bytes(b"existing")
    with pytest.raises(RescueInitramfsError, match="refusing to overwrite"):
        build_reproducible_rescue_initramfs(source, out, evidence_path)
