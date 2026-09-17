from __future__ import annotations

from pathlib import Path

import pytest

from kaliphonestudio.kernel_build_tree_diagnostics import (
    KernelBuildTreeDiagnosticError,
    diagnose_kernel_build_tree,
    write_kernel_build_tree_evidence,
)


def _write(root: Path, relative: str, payload: bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_identical_selected_build_trees_are_path_independent(tmp_path: Path):
    build_a = tmp_path / "left" / "out"
    build_b = tmp_path / "right" / "out"
    build_a.mkdir(parents=True)
    build_b.mkdir(parents=True)
    files = {
        ".config": b"CONFIG_TEST=y\n",
        "vmlinux": b"elf-like-vmlinux",
        "System.map": b"map\n",
        "arch/arm64/boot/Image": b"image\x00bytes",
        "drivers/test/example.o": b"object-bytes",
        "built-in.a": b"archive-bytes",
        "kernel/kheaders_data.tar.xz": b"deterministic-kheaders",
        "ignored.log": b"different host path noise",
    }
    for relative, payload in files.items():
        _write(build_a, relative, payload)
        _write(build_b, relative, payload if relative != "ignored.log" else b"other noise")

    evidence = diagnose_kernel_build_tree(build_a, build_b)

    assert evidence.selected_path_count == 7
    assert evidence.identical_path_count == 7
    assert evidence.differing_path_count == 0
    assert evidence.reported_differences == ()
    assert evidence.first_differing_path is None
    assert evidence.beta_gate_credit is False
    assert evidence.hardware_verified is False
    assert str(build_a) not in evidence.canonical_json()
    assert str(build_b) not in evidence.canonical_json()


def test_reports_content_size_and_missing_differences_with_categories(tmp_path: Path):
    build_a = tmp_path / "a"
    build_b = tmp_path / "b"
    build_a.mkdir()
    build_b.mkdir()

    _write(build_a, ".config", b"same\n")
    _write(build_b, ".config", b"same\n")
    _write(build_a, "drivers/a.o", b"AAAA")
    _write(build_b, "drivers/a.o", b"BBBB")
    _write(build_a, "drivers/b.o", b"short")
    _write(build_b, "drivers/b.o", b"longer")
    _write(build_a, "lib/only-a.a", b"a")
    _write(build_b, "lib/only-b.a", b"b")

    evidence = diagnose_kernel_build_tree(build_a, build_b, max_differences=10)
    by_path = {item.path: item for item in evidence.reported_differences}

    assert evidence.selected_path_count == 5
    assert evidence.identical_path_count == 1
    assert evidence.differing_path_count == 4
    assert evidence.content_mismatch_count == 1
    assert evidence.size_mismatch_count == 1
    assert evidence.missing_from_a_count == 1
    assert evidence.missing_from_b_count == 1
    assert evidence.category_difference_counts == {"archive": 2, "object": 2}
    assert by_path["drivers/a.o"].kind == "content_mismatch"
    assert by_path["drivers/a.o"].sha256_a != by_path["drivers/a.o"].sha256_b
    assert by_path["drivers/b.o"].kind == "size_mismatch"
    assert by_path["lib/only-a.a"].kind == "missing_from_b"
    assert by_path["lib/only-b.a"].kind == "missing_from_a"


def test_kheaders_archive_is_selected_and_classified_directly(tmp_path: Path):
    build_a = tmp_path / "a"
    build_b = tmp_path / "b"
    build_a.mkdir()
    build_b.mkdir()
    _write(build_a, "kernel/kheaders_data.tar.xz", b"archive-a")
    _write(build_b, "kernel/kheaders_data.tar.xz", b"archive-b")

    evidence = diagnose_kernel_build_tree(build_a, build_b)

    assert evidence.selected_path_count == 1
    assert evidence.differing_path_count == 1
    assert evidence.category_difference_counts == {"kheaders_archive": 1}
    difference = evidence.reported_differences[0]
    assert difference.path == "kernel/kheaders_data.tar.xz"
    assert difference.category == "kheaders_archive"
    assert difference.kind == "content_mismatch"
    assert difference.sha256_a != difference.sha256_b


def test_difference_output_is_bounded_but_totals_remain_exact(tmp_path: Path):
    build_a = tmp_path / "a"
    build_b = tmp_path / "b"
    build_a.mkdir()
    build_b.mkdir()
    for index in range(10):
        _write(build_a, f"obj/{index:02d}.o", f"A{index}".encode())
        _write(build_b, f"obj/{index:02d}.o", f"B{index}".encode())

    evidence = diagnose_kernel_build_tree(build_a, build_b, max_differences=3)

    assert evidence.differing_path_count == 10
    assert evidence.reported_difference_count == 3
    assert evidence.omitted_difference_count == 7
    assert evidence.first_differing_path == "obj/00.o"
    assert [item.path for item in evidence.reported_differences] == [
        "obj/00.o",
        "obj/01.o",
        "obj/02.o",
    ]


def test_rejects_same_root_and_selected_symlink(tmp_path: Path):
    build_a = tmp_path / "a"
    build_b = tmp_path / "b"
    build_a.mkdir()
    build_b.mkdir()
    _write(build_a, "real.o", b"x")
    try:
        (build_a / "linked.o").symlink_to(build_a / "real.o")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable on this platform")

    with pytest.raises(KernelBuildTreeDiagnosticError, match="independent directories"):
        diagnose_kernel_build_tree(build_b, build_b)
    with pytest.raises(KernelBuildTreeDiagnosticError, match="must not be a symlink"):
        diagnose_kernel_build_tree(build_a, build_b)


def test_writer_refuses_overwrite(tmp_path: Path):
    build_a = tmp_path / "a"
    build_b = tmp_path / "b"
    build_a.mkdir()
    build_b.mkdir()
    _write(build_a, "vmlinux", b"a")
    _write(build_b, "vmlinux", b"b")
    evidence = diagnose_kernel_build_tree(build_a, build_b)
    destination = tmp_path / "evidence.json"

    digest = write_kernel_build_tree_evidence(evidence, destination)
    assert len(digest) == 64
    assert destination.read_text(encoding="utf-8") == evidence.canonical_json()
    with pytest.raises(KernelBuildTreeDiagnosticError, match="refusing to overwrite"):
        write_kernel_build_tree_evidence(evidence, destination)
