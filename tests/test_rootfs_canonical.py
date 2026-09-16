import io
from pathlib import Path
import tarfile

import pytest

from kaliphonestudio.rootfs import RootfsError
from kaliphonestudio.rootfs_canonical import canonicalize_rootfs_archive


def _add_file(archive: tarfile.TarFile, name: str, data: bytes, mtime: int) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mode = 0o600 if name.endswith("/etc/shadow") else 0o644
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    info.mtime = mtime
    archive.addfile(info, io.BytesIO(data))


def _fixture(
    path: Path,
    *,
    mtime: int,
    machine_id: bytes,
    password_hash: bytes,
    cache: bytes,
    fake_clock: bytes,
) -> None:
    prefix = "kali-arm64"
    with tarfile.open(path, "w:xz", format=tarfile.PAX_FORMAT) as archive:
        _add_file(
            archive,
            f"{prefix}/var/lib/dpkg/status",
            b"Package: base-files\nStatus: install ok installed\nVersion: 1\nArchitecture: arm64\n\n",
            mtime,
        )
        _add_file(archive, f"{prefix}/etc/machine-id", machine_id, mtime + 1)
        _add_file(archive, f"{prefix}/var/lib/dbus/machine-id", machine_id, mtime + 2)
        _add_file(archive, f"{prefix}/etc/fake-hwclock.data", fake_clock, mtime + 3)
        _add_file(
            archive,
            f"{prefix}/etc/shadow",
            b"root:!:0:0:99999:7:::\nkali:" + password_hash + b":21000:0:99999:7:::\n",
            mtime + 4,
        )
        _add_file(archive, f"{prefix}/var/cache/ldconfig/aux-cache", cache, mtime + 5)
        _add_file(archive, f"{prefix}/usr/bin/unchanged", b"real package payload\n", mtime + 6)


def _member_bytes(path: Path, name: str) -> bytes:
    with tarfile.open(path, "r:xz") as archive:
        member = archive.getmember(name)
        handle = archive.extractfile(member)
        assert handle is not None
        return handle.read()


def test_canonicalization_removes_observed_builder_identity_and_mtime_drift(tmp_path):
    first = tmp_path / "first.tar.xz"
    second = tmp_path / "second.tar.xz"
    out_a = tmp_path / "canonical-a.tar.xz"
    out_b = tmp_path / "canonical-b.tar.xz"
    _fixture(
        first,
        mtime=100,
        machine_id=b"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n",
        password_hash=b"$y$random-salt-a$hash-a",
        cache=b"cache-a",
        fake_clock=b"2026-09-16 20:00:00\n",
    )
    _fixture(
        second,
        mtime=900,
        machine_id=b"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n",
        password_hash=b"$y$random-salt-b$hash-b",
        cache=b"cache-b",
        fake_clock=b"2026-09-16 20:01:00\n",
    )

    evidence_a = canonicalize_rootfs_archive(first, out_a)
    evidence_b = canonicalize_rootfs_archive(second, out_b)

    assert out_a.read_bytes() == out_b.read_bytes()
    assert evidence_a.output_sha256 == evidence_b.output_sha256
    assert evidence_a.beta_gate_credit is False
    assert evidence_a.zeroed_volatile_files == 3
    assert evidence_a.locked_password_entries == 2
    assert evidence_a.dropped_cache_entries == 1
    assert evidence_a.normalized_mtime_count == 6

    prefix = "kali-arm64"
    assert _member_bytes(out_a, f"{prefix}/etc/machine-id") == b""
    assert _member_bytes(out_a, f"{prefix}/var/lib/dbus/machine-id") == b""
    assert _member_bytes(out_a, f"{prefix}/etc/fake-hwclock.data") == b""
    assert _member_bytes(out_a, f"{prefix}/etc/shadow") == (
        b"root:!:0:0:99999:7:::\nkali:!:0:0:99999:7:::\n"
    )
    assert _member_bytes(out_a, f"{prefix}/usr/bin/unchanged") == b"real package payload\n"

    with tarfile.open(out_a, "r:xz") as archive:
        names = archive.getnames()
        assert f"{prefix}/var/cache/ldconfig/aux-cache" not in names
        assert all(member.mtime == 0 for member in archive.getmembers())


def test_canonicalization_rejects_ambiguous_dpkg_status_layout(tmp_path):
    source = tmp_path / "bad.tar.xz"
    destination = tmp_path / "out.tar.xz"
    with tarfile.open(source, "w:xz") as archive:
        _add_file(archive, "a/var/lib/dpkg/status", b"x", 1)
        _add_file(archive, "b/var/lib/dpkg/status", b"x", 1)

    with pytest.raises(RootfsError, match="exactly one"):
        canonicalize_rootfs_archive(source, destination)
    assert not destination.exists()


def test_canonicalization_rejects_path_traversal_and_cleans_partial_output(tmp_path):
    source = tmp_path / "bad.tar.xz"
    destination = tmp_path / "out.tar.xz"
    with tarfile.open(source, "w:xz") as archive:
        _add_file(archive, "kali-arm64/var/lib/dpkg/status", b"x", 1)
        _add_file(archive, "kali-arm64/../escape", b"x", 1)

    with pytest.raises(RootfsError, match="traversal"):
        canonicalize_rootfs_archive(source, destination)
    assert not destination.exists()
