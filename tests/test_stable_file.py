from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path

import pytest

import kaliphonestudio.stable_file as stable_file
from kaliphonestudio.stable_file import StableFileError, hash_stable_regular_file


def test_hash_stable_regular_file_binds_exact_bytes(tmp_path: Path) -> None:
    artifact = tmp_path / "stock-boot.img"
    payload = b"exact local stock boot material\n" * 8
    artifact.write_bytes(payload)

    identity = hash_stable_regular_file(
        artifact,
        max_bytes=1024 * 1024,
        expected_size=len(payload),
        label="stock boot recovery material",
    )

    assert identity.path == artifact
    assert identity.size == len(payload)
    assert identity.sha256 == sha256(payload).hexdigest()
    assert isinstance(identity.device, int)
    assert isinstance(identity.inode, int)
    assert identity.mtime_ns > 0


def test_hash_stable_regular_file_rejects_expected_size_drift(tmp_path: Path) -> None:
    artifact = tmp_path / "rootfs.img"
    artifact.write_bytes(b"rootfs")

    with pytest.raises(StableFileError, match="size differs from the expected exact size"):
        hash_stable_regular_file(
            artifact,
            max_bytes=1024,
            expected_size=artifact.stat().st_size + 1,
            label="rootfs artifact",
        )


def test_hash_stable_regular_file_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "real.img"
    target.write_bytes(b"real")
    link = tmp_path / "link.img"
    try:
        link.symlink_to(target.name)
    except (OSError, NotImplementedError):
        pytest.skip("host cannot create test symlink")

    with pytest.raises(StableFileError, match="regular non-symlink"):
        hash_stable_regular_file(link, max_bytes=1024, label="artifact")


@pytest.mark.skipif(
    os.name == "nt",
    reason="Windows may deny renaming a file while the read descriptor is open",
)
def test_hash_stable_regular_file_rejects_path_swap_during_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "artifact.bin"
    displaced = tmp_path / "artifact.original"
    payload = b"A" * (2 * 1024 * 1024)
    artifact.write_bytes(payload)

    original_read = os.read
    swapped = False

    def adversarial_read(fd: int, count: int) -> bytes:
        nonlocal swapped
        chunk = original_read(fd, count)
        if chunk and not swapped:
            artifact.replace(displaced)
            artifact.write_bytes(b"B" * len(payload))
            swapped = True
        return chunk

    monkeypatch.setattr(stable_file.os, "read", adversarial_read)

    with pytest.raises(StableFileError, match="path was replaced while being hashed"):
        hash_stable_regular_file(
            artifact,
            max_bytes=4 * 1024 * 1024,
            expected_size=len(payload),
            label="stock boot recovery material",
        )


def test_hash_stable_regular_file_rejects_non_positive_or_oversized_contract(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"x")

    with pytest.raises(StableFileError, match="max_bytes must be a positive integer"):
        hash_stable_regular_file(artifact, max_bytes=0)

    with pytest.raises(StableFileError, match="expected size is outside the bounded safety limit"):
        hash_stable_regular_file(artifact, max_bytes=1, expected_size=2)
