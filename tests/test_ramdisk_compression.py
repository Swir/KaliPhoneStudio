from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from kaliphonestudio.profiles import DeviceProfile, load_profile
from kaliphonestudio.ramdisk_compression import (
    RamdiskCompressionError,
    authorize_compressor_binary,
    compress_rescue_ramdisk_reproducibly,
    load_ramdisk_compressor_lock,
)
from kaliphonestudio.rescue_initramfs import build_reproducible_rescue_initramfs


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "devices" / "oneplus" / "avicii" / "profile.json"
LOCK_PATH = ROOT / "tools" / "ramdisk-compressor-locks.json"


def _make_rescue(tmp_path: Path):
    source = tmp_path / "root"
    source.mkdir()
    init = source / "init"
    init.write_text("#!/bin/sh\nexec /bin/rescue\n", encoding="utf-8")
    init.chmod(0o755)
    (source / "bin").mkdir()
    tool = source / "bin" / "rescue"
    tool.write_bytes(b"ELF-placeholder")
    tool.chmod(0o755)
    cpio = tmp_path / "rescue.cpio"
    evidence_path = tmp_path / "rescue.json"
    evidence = build_reproducible_rescue_initramfs(source, cpio, evidence_path)
    return cpio, evidence


def _authorized_lock(tmp_path: Path, binary: Path) -> Path:
    data = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    data["compressors"]["lz4"]["artifacts"] = {
        "test-amd64": sha256(binary.read_bytes()).hexdigest()
    }
    path = tmp_path / "lock.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_repository_lz4_lock_is_exact_source_and_fail_closed_by_default():
    lock = load_ramdisk_compressor_lock(LOCK_PATH)
    assert lock.source_tag == "v1.10.0"
    assert lock.source_commit == "ebb370ca83af193212df4dcbadcc5d87bc0de2f0"
    assert lock.invocation == ("-l", "-12", "--favor-decSpeed")
    assert lock.format == "lz4-legacy"
    assert lock.legacy_magic_hex == "02214c18"
    assert lock.artifacts == {}


def test_rejects_moving_source_or_non_android_invocation(tmp_path: Path):
    data = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    data["compressors"]["lz4"]["source"]["commit"] = "main"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(RamdiskCompressionError, match="full lowercase git SHA"):
        load_ramdisk_compressor_lock(path)

    data = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    data["compressors"]["lz4"]["invocation"] = ["-12"]
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(RamdiskCompressionError, match="Android legacy"):
        load_ramdisk_compressor_lock(path)


def test_unauthorized_platform_and_wrong_binary_hash_fail_closed(tmp_path: Path):
    lock = load_ramdisk_compressor_lock(LOCK_PATH)
    binary = tmp_path / "lz4"
    binary.write_bytes(b"fake")
    with pytest.raises(RamdiskCompressionError, match="no reviewed compressor artifact"):
        authorize_compressor_binary(lock, "linux-amd64", binary)

    locked_path = _authorized_lock(tmp_path, binary)
    authorized = load_ramdisk_compressor_lock(locked_path)
    binary.write_bytes(b"tampered")
    with pytest.raises(RamdiskCompressionError, match="SHA-256"):
        authorize_compressor_binary(authorized, "test-amd64", binary)


def test_profile_driven_compression_double_build_and_evidence(tmp_path: Path, monkeypatch):
    profile = load_profile(PROFILE_PATH)
    cpio, source_evidence = _make_rescue(tmp_path)
    binary = tmp_path / "lz4"
    binary.write_bytes(b"reviewed-lz4-binary")
    lock = load_ramdisk_compressor_lock(_authorized_lock(tmp_path, binary))

    def fake_run(argv, *, stdin, stdout, stderr, shell, check, timeout):
        assert tuple(argv[1:]) == ("-l", "-12", "--favor-decSpeed")
        assert shell is False and check is False and timeout == 120
        stdout.write(bytes.fromhex("02214c18") + stdin.read())
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr("kaliphonestudio.ramdisk_compression.subprocess.run", fake_run)
    output = tmp_path / "out" / "ramdisk.lz4"
    evidence_path = tmp_path / "out" / "ramdisk.json"
    evidence = compress_rescue_ramdisk_reproducibly(
        profile,
        cpio,
        source_evidence,
        binary,
        lock,
        "test-amd64",
        output,
        evidence_path,
    )

    assert output.read_bytes().startswith(bytes.fromhex("02214c18"))
    assert evidence.profile_id == "oneplus/avicii"
    assert evidence.output_sha256 == sha256(output.read_bytes()).hexdigest()
    assert evidence.input_sha256 == source_evidence.artifact_sha256
    assert evidence.invocation == ("-l", "-12", "--favor-decSpeed")
    assert json.loads(evidence_path.read_text(encoding="utf-8"))["reproducible"] is True


def test_independent_compression_must_be_byte_identical(tmp_path: Path, monkeypatch):
    profile = load_profile(PROFILE_PATH)
    cpio, source_evidence = _make_rescue(tmp_path)
    binary = tmp_path / "lz4"
    binary.write_bytes(b"reviewed-lz4-binary")
    lock = load_ramdisk_compressor_lock(_authorized_lock(tmp_path, binary))
    calls = 0

    def fake_run(argv, *, stdin, stdout, stderr, shell, check, timeout):
        nonlocal calls
        calls += 1
        stdout.write(bytes.fromhex("02214c18") + bytes([calls]) + stdin.read())
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr("kaliphonestudio.ramdisk_compression.subprocess.run", fake_run)
    with pytest.raises(RamdiskCompressionError, match="not byte-identical"):
        compress_rescue_ramdisk_reproducibly(
            profile,
            cpio,
            source_evidence,
            binary,
            lock,
            "test-amd64",
            tmp_path / "ramdisk.lz4",
            tmp_path / "ramdisk.json",
        )


def test_profile_compression_policy_is_mandatory(tmp_path: Path, monkeypatch):
    profile = load_profile(PROFILE_PATH)
    data = deepcopy(profile.data)
    data["boot"]["ramdisk_compression"] = "gzip"
    wrong_profile = DeviceProfile(path=profile.path, data=data)
    cpio, source_evidence = _make_rescue(tmp_path)
    binary = tmp_path / "lz4"
    binary.write_bytes(b"reviewed-lz4-binary")
    lock = load_ramdisk_compressor_lock(_authorized_lock(tmp_path, binary))

    with pytest.raises(RamdiskCompressionError, match="does not require lz4"):
        compress_rescue_ramdisk_reproducibly(
            wrong_profile,
            cpio,
            source_evidence,
            binary,
            lock,
            "test-amd64",
            tmp_path / "ramdisk.lz4",
            tmp_path / "ramdisk.json",
        )
