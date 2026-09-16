from __future__ import annotations

import io
from pathlib import Path
import tarfile

import pytest

from kaliphonestudio.rootfs import RootfsError, package_manifest_from_rootfs


_STATUS = (
    b"Package: base-files\n"
    b"Status: install ok installed\n"
    b"Architecture: arm64\n"
    b"Version: 1.0\n\n"
)


def _archive(path: Path, names: list[str]) -> Path:
    with tarfile.open(path, "w:xz") as archive:
        for name in names:
            member = tarfile.TarInfo(name)
            member.size = len(_STATUS)
            member.mtime = 0
            archive.addfile(member, io.BytesIO(_STATUS))
    return path


def test_package_manifest_accepts_pinned_builder_top_level_directory(tmp_path: Path) -> None:
    artifact = _archive(
        tmp_path / "rootfs.tar.xz",
        ["kali-arm64/var/lib/dpkg/status"],
    )
    manifest, count = package_manifest_from_rootfs(artifact)
    assert count == 1
    assert manifest == b"base-files\t1.0\tarm64\n"


def test_package_manifest_still_accepts_archive_root_layout(tmp_path: Path) -> None:
    artifact = _archive(tmp_path / "rootfs.tar.xz", ["./var/lib/dpkg/status"])
    manifest, count = package_manifest_from_rootfs(artifact)
    assert count == 1
    assert manifest == b"base-files\t1.0\tarm64\n"


def test_package_manifest_rejects_ambiguous_root_and_prefixed_status(tmp_path: Path) -> None:
    artifact = _archive(
        tmp_path / "rootfs.tar.xz",
        ["var/lib/dpkg/status", "kali-arm64/var/lib/dpkg/status"],
    )
    with pytest.raises(RootfsError, match="exactly one"):
        package_manifest_from_rootfs(artifact)


def test_package_manifest_rejects_deep_suffix_match(tmp_path: Path) -> None:
    artifact = _archive(
        tmp_path / "rootfs.tar.xz",
        ["outer/kali-arm64/var/lib/dpkg/status"],
    )
    with pytest.raises(RootfsError, match="unsafe or unexpected"):
        package_manifest_from_rootfs(artifact)


def test_package_manifest_rejects_traversal_suffix_match(tmp_path: Path) -> None:
    artifact = _archive(
        tmp_path / "rootfs.tar.xz",
        ["../var/lib/dpkg/status"],
    )
    with pytest.raises(RootfsError, match="unsafe or unexpected"):
        package_manifest_from_rootfs(artifact)
