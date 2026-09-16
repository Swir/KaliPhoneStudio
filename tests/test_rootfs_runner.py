from pathlib import Path

import pytest

from kaliphonestudio.rootfs import RootfsError
from scripts.run_locked_rootfs_build import _create_dependency_guard


def test_dependency_guard_is_explicit_and_lock_bound(tmp_path: Path):
    digest = "a" * 64
    marker = _create_dependency_guard(tmp_path, digest)
    assert marker == tmp_path / ".dep_check"
    text = marker.read_text(encoding="utf-8")
    assert "kaliphonestudio-prevalidated-static-qemu" in text
    assert f"source_lock_sha256={digest}" in text


def test_dependency_guard_refuses_preexisting_marker(tmp_path: Path):
    marker = tmp_path / ".dep_check"
    marker.write_text("unknown provenance\n", encoding="utf-8")
    with pytest.raises(RootfsError, match="already exists"):
        _create_dependency_guard(tmp_path, "b" * 64)


def test_dependency_guard_refuses_symlink(tmp_path: Path):
    target = tmp_path / "target"
    target.write_text("x", encoding="utf-8")
    marker = tmp_path / ".dep_check"
    marker.symlink_to(target)
    with pytest.raises(RootfsError, match="already exists"):
        _create_dependency_guard(tmp_path, "c" * 64)
