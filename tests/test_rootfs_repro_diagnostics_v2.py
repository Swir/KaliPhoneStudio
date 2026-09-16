from __future__ import annotations

import io
import lzma
import tarfile
from pathlib import Path

from kaliphonestudio.rootfs_repro_diagnostics import build_rootfs_repro_diagnostics


def _status(version: str) -> bytes:
    return (
        "Package: base-files\n"
        "Status: install ok installed\n"
        "Architecture: arm64\n"
        f"Version: {version}\n\n"
    ).encode("utf-8")


def _write_rootfs(path: Path, *, version: str, marker: bytes) -> None:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as archive:
        root = tarfile.TarInfo("kali-arm64")
        root.type = tarfile.DIRTYPE
        root.mode = 0o755
        root.mtime = 0
        archive.addfile(root)

        status = _status(version)
        member = tarfile.TarInfo("kali-arm64/var/lib/dpkg/status")
        member.size = len(status)
        member.mode = 0o644
        member.mtime = 0
        archive.addfile(member, io.BytesIO(status))

        marker_member = tarfile.TarInfo("kali-arm64/etc/build-marker")
        marker_member.size = len(marker)
        marker_member.mode = 0o644
        marker_member.mtime = 0
        archive.addfile(marker_member, io.BytesIO(marker))

    path.write_bytes(lzma.compress(raw.getvalue(), format=lzma.FORMAT_XZ, preset=6))


def test_diagnostics_separate_package_equality_from_other_payload_drift(tmp_path):
    first = tmp_path / "a.tar.xz"
    second = tmp_path / "b.tar.xz"
    _write_rootfs(first, version="1.0", marker=b"build-a")
    _write_rootfs(second, version="1.0", marker=b"build-b")

    report = build_rootfs_repro_diagnostics(first, second)

    packages = report["package_manifest"]
    assert packages["equal"] is True
    assert packages["left"]["available"] is True
    assert packages["right"]["available"] is True
    assert packages["left"]["package_count"] == 1
    assert packages["left"]["sha256"] == packages["right"]["sha256"]
    assert report["summary"]["content_changed"] == 1
    assert report["beta_gate_credit"] is False


def test_diagnostics_expose_installed_package_drift_without_granting_credit(tmp_path):
    first = tmp_path / "a.tar.xz"
    second = tmp_path / "b.tar.xz"
    _write_rootfs(first, version="1.0", marker=b"same")
    _write_rootfs(second, version="1.1", marker=b"same")

    report = build_rootfs_repro_diagnostics(first, second)

    packages = report["package_manifest"]
    assert packages["equal"] is False
    assert packages["left"]["sha256"] != packages["right"]["sha256"]
    assert report["strict_reproducible"] is False
    assert report["beta_gate_credit"] is False
