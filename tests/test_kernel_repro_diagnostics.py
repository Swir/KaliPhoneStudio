from __future__ import annotations

from pathlib import Path

import pytest

from kaliphonestudio.kernel_repro_diagnostics import (
    KernelReproDiagnosticError,
    diagnose_kernel_image_divergence,
    write_kernel_image_divergence_evidence,
)


def _write(path: Path, payload: bytes) -> Path:
    path.write_bytes(payload)
    return path


def test_equal_independent_images_report_no_divergence(tmp_path: Path) -> None:
    a = _write(tmp_path / "a", b"A" * 8192)
    b = _write(tmp_path / "b", b"A" * 8192)
    evidence = diagnose_kernel_image_divergence(a, b, chunk_size=4096)
    assert evidence.equal is True
    assert evidence.differing_byte_count == 0
    assert evidence.differing_range_count == 0
    assert evidence.first_difference_offset is None
    assert evidence.last_difference_offset is None
    assert evidence.beta_gate_credit is False
    assert evidence.hardware_verified is False


def test_contiguous_and_separate_differences_are_counted_exactly(tmp_path: Path) -> None:
    left = bytearray(b"A" * 16384)
    right = bytearray(left)
    right[10:13] = b"BCD"
    right[4095:4097] = b"XY"  # crosses a diagnostic chunk boundary
    right[12000] = ord("Z")

    evidence = diagnose_kernel_image_divergence(
        _write(tmp_path / "a", bytes(left)),
        _write(tmp_path / "b", bytes(right)),
        chunk_size=4096,
    )
    assert evidence.equal is False
    assert evidence.differing_byte_count == 6
    assert evidence.differing_range_count == 3
    assert evidence.first_difference_offset == 10
    assert evidence.last_difference_offset == 12000
    assert [(r.start, r.end_exclusive, r.differing_bytes) for r in evidence.reported_ranges] == [
        (10, 13, 3),
        (4095, 4097, 2),
        (12000, 12001, 1),
    ]


def test_report_is_bounded_but_total_counts_remain_exact(tmp_path: Path) -> None:
    left = bytearray(b"A" * 8192)
    right = bytearray(left)
    for offset in (10, 20, 30, 40, 50):
        right[offset] = ord("B")
    evidence = diagnose_kernel_image_divergence(
        _write(tmp_path / "a", bytes(left)),
        _write(tmp_path / "b", bytes(right)),
        chunk_size=4096,
        max_ranges=2,
    )
    assert evidence.differing_byte_count == 5
    assert evidence.differing_range_count == 5
    assert evidence.reported_range_count == 2
    assert evidence.omitted_range_count == 3


def test_size_difference_becomes_trailing_range(tmp_path: Path) -> None:
    a = _write(tmp_path / "a", b"A" * 8192)
    b = _write(tmp_path / "b", b"A" * 8192 + b"TAIL")
    evidence = diagnose_kernel_image_divergence(a, b, chunk_size=4096)
    assert evidence.equal is False
    assert evidence.differing_byte_count == 4
    assert evidence.differing_range_count == 1
    assert evidence.first_difference_offset == 8192
    assert evidence.last_difference_offset == 8195
    trailing = evidence.reported_ranges[0]
    assert (trailing.start, trailing.end_exclusive, trailing.differing_bytes) == (8192, 8196, 4)


def test_evidence_write_is_canonical_and_hash_stable(tmp_path: Path) -> None:
    a = _write(tmp_path / "a", b"A" * 4096)
    b = _write(tmp_path / "b", b"B" + b"A" * 4095)
    evidence = diagnose_kernel_image_divergence(a, b, chunk_size=4096)
    out = tmp_path / "evidence" / "kernel-divergence.json"
    digest = write_kernel_image_divergence_evidence(evidence, out)
    assert len(digest) == 64
    assert digest == evidence.evidence_sha256()
    assert out.read_text(encoding="utf-8") == evidence.canonical_json()


def test_same_file_and_unsafe_inputs_fail_closed(tmp_path: Path) -> None:
    image = _write(tmp_path / "Image", b"A" * 4096)
    with pytest.raises(KernelReproDiagnosticError, match="independent"):
        diagnose_kernel_image_divergence(image, image, chunk_size=4096)

    missing = tmp_path / "missing"
    with pytest.raises(KernelReproDiagnosticError, match="regular"):
        diagnose_kernel_image_divergence(image, missing, chunk_size=4096)


def test_invalid_limits_fail_closed(tmp_path: Path) -> None:
    a = _write(tmp_path / "a", b"A" * 4096)
    b = _write(tmp_path / "b", b"B" * 4096)
    with pytest.raises(KernelReproDiagnosticError, match="chunk_size"):
        diagnose_kernel_image_divergence(a, b, chunk_size=1024)
    with pytest.raises(KernelReproDiagnosticError, match="max_ranges"):
        diagnose_kernel_image_divergence(a, b, max_ranges=0)
