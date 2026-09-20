from __future__ import annotations

from hashlib import sha256
import io
from pathlib import Path
import tarfile

import pytest

from kaliphonestudio.rootfs_member_manifest import (
    RootfsMemberManifestError,
    build_rootfs_member_manifest,
)


def _write_archive(path: Path, members: list[tuple[tarfile.TarInfo, bytes | None]]) -> None:
    with tarfile.open(path, mode="w:xz", format=tarfile.PAX_FORMAT) as archive:
        for info, payload in members:
            info.mtime = 0
            if payload is None:
                archive.addfile(info)
            else:
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))


def test_explicit_root_directory_marker_is_normalized_safely(tmp_path: Path) -> None:
    archive_path = tmp_path / "rootfs.tar.xz"
    root = tarfile.TarInfo("./")
    root.type = tarfile.DIRTYPE
    root.mode = 0o755
    root.uid = 0
    root.gid = 0

    payload = b"kali-phosh\n"
    file_info = tarfile.TarInfo("./etc/example")
    file_info.type = tarfile.REGTYPE
    file_info.mode = 0o644
    file_info.uid = 0
    file_info.gid = 0

    _write_archive(archive_path, [(root, None), (file_info, payload)])

    manifest = build_rootfs_member_manifest(archive_path)

    assert manifest.member_count == 2
    assert [entry.path for entry in manifest.entries] == [".", "etc/example"]
    assert manifest.entries[1].content_sha256 == sha256(payload).hexdigest()
    assert manifest.diagnostic_only is True
    assert manifest.reproducibility_authority is False
    assert manifest.hardware_verified is False
    assert manifest.beta_gate_credit is False


def test_binary_pax_value_is_losslessly_hex_encoded(tmp_path: Path) -> None:
    archive_path = tmp_path / "rootfs-pax.tar.xz"
    info = tarfile.TarInfo("./usr/bin/capable")
    info.type = tarfile.REGTYPE
    info.mode = 0o755
    info.uid = 0
    info.gid = 0
    info.pax_headers = {
        "SCHILY.xattr.security.capability": "\x01\x02cap",
        "comment": "plain-text",
    }

    _write_archive(archive_path, [(info, b"payload")])
    manifest = build_rootfs_member_manifest(archive_path)

    assert manifest.entries[0].pax_headers == (
        ("SCHILY.xattr.security.capability", "hex:0102636170"),
        ("comment", "hex:706c61696e2d74657874"),
    )
    assert all(
        all(ord(char) >= 32 and ord(char) != 127 for char in value)
        for _, value in manifest.entries[0].pax_headers
    )


def test_parent_traversal_is_still_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.tar.xz"
    info = tarfile.TarInfo("../escape")
    info.type = tarfile.REGTYPE
    info.mode = 0o644
    info.uid = 0
    info.gid = 0
    _write_archive(archive_path, [(info, b"nope")])

    with pytest.raises(RootfsMemberManifestError, match="path traversal"):
        build_rootfs_member_manifest(archive_path)


def test_root_marker_and_normalized_duplicate_fail_closed(tmp_path: Path) -> None:
    archive_path = tmp_path / "duplicate.tar.xz"
    first = tarfile.TarInfo("./etc/example")
    first.type = tarfile.REGTYPE
    first.mode = 0o644
    first.uid = 0
    first.gid = 0
    second = tarfile.TarInfo("etc/example")
    second.type = tarfile.REGTYPE
    second.mode = 0o644
    second.uid = 0
    second.gid = 0
    _write_archive(archive_path, [(first, b"a"), (second, b"b")])

    with pytest.raises(RootfsMemberManifestError, match="duplicate path"):
        build_rootfs_member_manifest(archive_path)
