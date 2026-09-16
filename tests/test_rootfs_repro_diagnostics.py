from __future__ import annotations

import io
import lzma
import tarfile
from pathlib import Path

import pytest

from kaliphonestudio.rootfs_repro_diagnostics import (
    RootfsReproDiagnosticError,
    build_rootfs_repro_diagnostics,
    write_rootfs_repro_diagnostics,
)


def _tar_bytes(entries, *, prefix="root", order=None):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w", format=tarfile.PAX_FORMAT) as archive:
        items = list(entries)
        if order is not None:
            by_name = {item[0]: item for item in items}
            items = [by_name[name] for name in order]
        root = tarfile.TarInfo(prefix)
        root.type = tarfile.DIRTYPE
        root.mode = 0o755
        root.uid = root.gid = 0
        root.mtime = 0
        archive.addfile(root)
        for name, data, metadata in items:
            info = tarfile.TarInfo(f"{prefix}/{name}")
            info.mode = metadata.get("mode", 0o644)
            info.uid = metadata.get("uid", 0)
            info.gid = metadata.get("gid", 0)
            info.uname = metadata.get("uname", "root")
            info.gname = metadata.get("gname", "root")
            info.mtime = metadata.get("mtime", 0)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return out.getvalue()


def _write_xz(path: Path, tar_bytes: bytes, preset=6):
    path.write_bytes(
        lzma.compress(tar_bytes, format=lzma.FORMAT_XZ, preset=preset)
    )


def _basic_entries(content=b"hello"):
    return [
        ("etc/config", content, {}),
        ("usr/bin/tool", b"tool", {"mode": 0o755}),
    ]


def test_identical_archive_is_strict_and_semantic(tmp_path):
    archive = tmp_path / "a.tar.xz"
    _write_xz(archive, _tar_bytes(_basic_entries()))
    copy = tmp_path / "b.tar.xz"
    copy.write_bytes(archive.read_bytes())

    report = build_rootfs_repro_diagnostics(archive, copy)
    assert report["schema_version"] == 2
    assert report["strict_reproducible"] is True
    assert report["semantic_equal"] is True
    assert report["container_only_difference"] is False
    assert report["summary"]["difference_count_total"] == 0
    assert report["beta_gate_credit"] is False


def test_different_xz_container_is_not_strict_but_semantically_equal(tmp_path):
    tar_bytes = _tar_bytes(_basic_entries())
    first = tmp_path / "a.tar.xz"
    second = tmp_path / "b.tar.xz"
    _write_xz(first, tar_bytes, preset=0)
    _write_xz(second, tar_bytes, preset=9)

    report = build_rootfs_repro_diagnostics(first, second)
    assert report["strict_reproducible"] is False
    assert report["semantic_equal"] is True
    assert report["container_only_difference"] is True


def test_content_change_is_reported(tmp_path):
    first = tmp_path / "a.tar.xz"
    second = tmp_path / "b.tar.xz"
    _write_xz(first, _tar_bytes(_basic_entries(b"one")))
    _write_xz(second, _tar_bytes(_basic_entries(b"two")))

    report = build_rootfs_repro_diagnostics(first, second)
    assert report["summary"]["content_changed"] == 1
    content = [d for d in report["differences"] if d["kind"] == "content"]
    assert content[0]["path"] == "etc/config"


def test_metadata_changes_are_field_specific(tmp_path):
    first = tmp_path / "a.tar.xz"
    second = tmp_path / "b.tar.xz"
    _write_xz(
        first,
        _tar_bytes(
            [
                (
                    "etc/config",
                    b"x",
                    {"mode": 0o600, "uid": 1, "gid": 2, "mtime": 3},
                )
            ]
        ),
    )
    _write_xz(
        second,
        _tar_bytes(
            [
                (
                    "etc/config",
                    b"x",
                    {"mode": 0o644, "uid": 4, "gid": 5, "mtime": 6},
                )
            ]
        ),
    )

    report = build_rootfs_repro_diagnostics(first, second)
    metadata = [
        d for d in report["differences"] if d["kind"] == "metadata"
    ][0]
    assert set(metadata["fields"]) >= {"mode", "uid", "gid", "mtime"}
    assert report["summary"]["metadata_changed"] == 1
    assert report["summary"]["metadata_mtime_only"] == 0
    assert report["summary"]["metadata_field_changes"] == {
        "mode": 1,
        "uid": 1,
        "gid": 1,
        "mtime": 1,
    }


def test_mtime_only_metadata_is_counted_separately(tmp_path):
    first = tmp_path / "a.tar.xz"
    second = tmp_path / "b.tar.xz"
    _write_xz(first, _tar_bytes([("etc/config", b"x", {"mtime": 10})]))
    _write_xz(second, _tar_bytes([("etc/config", b"x", {"mtime": 20})]))

    report = build_rootfs_repro_diagnostics(first, second)
    assert report["summary"]["metadata_changed"] == 1
    assert report["summary"]["metadata_mtime_only"] == 1
    assert report["summary"]["metadata_field_changes"] == {"mtime": 1}


def test_added_removed_and_order_are_reported(tmp_path):
    first = tmp_path / "a.tar.xz"
    second = tmp_path / "b.tar.xz"
    _write_xz(
        first,
        _tar_bytes(
            [("a", b"a", {}), ("b", b"b", {})],
            order=["a", "b"],
        ),
    )
    _write_xz(
        second,
        _tar_bytes(
            [("b", b"b", {}), ("c", b"c", {})],
            order=["c", "b"],
        ),
    )

    report = build_rootfs_repro_diagnostics(first, second)
    assert report["summary"]["added"] == 1
    assert report["summary"]["removed"] == 1
    assert report["summary"]["order_changed"] is True


def test_different_top_level_prefix_is_normalized(tmp_path):
    first = tmp_path / "a.tar.xz"
    second = tmp_path / "b.tar.xz"
    _write_xz(first, _tar_bytes(_basic_entries(), prefix="build-a"))
    _write_xz(second, _tar_bytes(_basic_entries(), prefix="build-b"))

    report = build_rootfs_repro_diagnostics(first, second)
    assert report["semantic_equal"] is True
    assert report["left"]["stripped_prefix"] == "build-a"
    assert report["right"]["stripped_prefix"] == "build-b"


def test_traversal_is_rejected(tmp_path):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w") as archive:
        info = tarfile.TarInfo("../escape")
        info.size = 1
        archive.addfile(info, io.BytesIO(b"x"))
    first = tmp_path / "a.tar.xz"
    _write_xz(first, out.getvalue())

    with pytest.raises(RootfsReproDiagnosticError, match="traversal"):
        build_rootfs_repro_diagnostics(first, first)


def test_duplicate_normalized_path_is_rejected(tmp_path):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w") as archive:
        for name in ("root/a", "root/./a"):
            info = tarfile.TarInfo(name)
            info.size = 1
            archive.addfile(info, io.BytesIO(b"x"))
    first = tmp_path / "a.tar.xz"
    _write_xz(first, out.getvalue())

    with pytest.raises(RootfsReproDiagnosticError, match="duplicate"):
        build_rootfs_repro_diagnostics(first, first)


def test_truncation_prioritizes_payload_changes_over_mtime_noise(tmp_path):
    first = tmp_path / "a.tar.xz"
    second = tmp_path / "b.tar.xz"
    left_entries = [
        (f"a{i}", b"same", {"mtime": 10}) for i in range(5)
    ] + [("z-content", b"before", {"mtime": 10})]
    right_entries = [
        (f"a{i}", b"same", {"mtime": 20}) for i in range(5)
    ] + [("z-content", b"after!", {"mtime": 20})]
    _write_xz(first, _tar_bytes(left_entries))
    _write_xz(second, _tar_bytes(right_entries))

    report = build_rootfs_repro_diagnostics(first, second, max_differences=2)
    assert report["summary"]["content_changed"] == 1
    assert report["summary"]["metadata_changed"] == 6
    assert report["summary"]["metadata_mtime_only"] == 6
    assert report["differences_truncated"] is True
    assert report["differences"][0]["kind"] == "content"
    assert report["differences"][0]["path"] == "z-content"
    assert report["reporting"]["reported_by_kind"]["content"] == 1
    assert report["reporting"]["omitted_by_kind"]["metadata"] == 5


def test_difference_output_is_bounded_and_file_is_canonical(tmp_path):
    first = tmp_path / "a.tar.xz"
    second = tmp_path / "b.tar.xz"
    _write_xz(
        first,
        _tar_bytes([(f"f{i}", b"a", {}) for i in range(5)]),
    )
    _write_xz(
        second,
        _tar_bytes([(f"f{i}", b"b", {}) for i in range(5)]),
    )
    out = tmp_path / "diagnostic.json"

    report = write_rootfs_repro_diagnostics(
        first,
        second,
        out,
        max_differences=2,
    )
    assert report["summary"]["difference_count_total"] == 5
    assert report["differences_truncated"] is True
    assert len(report["differences"]) == 2
    assert report["reporting"]["reported_by_kind"]["content"] == 2
    assert report["reporting"]["omitted_by_kind"]["content"] == 3
    text = out.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert '"beta_gate_credit":false' in text
