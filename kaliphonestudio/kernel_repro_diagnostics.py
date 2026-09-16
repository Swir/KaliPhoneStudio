"""Bounded, non-release diagnostics for strict kernel Image divergence.

The reproducibility acceptance rule remains byte-for-byte equality.  This module only
helps explain a failed A/B comparison and can never create release/Beta evidence.
It compares files in a streaming fashion so full kernel Images do not need to be
loaded into memory.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import BinaryIO


DIAGNOSTIC_SCHEMA_VERSION = 1
DEFAULT_CHUNK_SIZE = 1024 * 1024
DEFAULT_MAX_RANGES = 128


class KernelReproDiagnosticError(ValueError):
    pass


@dataclass(frozen=True)
class ByteRangeDifference:
    start: int
    end_exclusive: int
    differing_bytes: int

    @property
    def span_bytes(self) -> int:
        return self.end_exclusive - self.start


@dataclass(frozen=True)
class KernelImageDivergenceEvidence:
    schema_version: int
    image_a_sha256: str
    image_b_sha256: str
    image_a_size: int
    image_b_size: int
    overlap_size: int
    equal: bool
    differing_byte_count: int
    differing_range_count: int
    reported_range_count: int
    omitted_range_count: int
    first_difference_offset: int | None
    last_difference_offset: int | None
    reported_ranges: tuple[ByteRangeDifference, ...]
    beta_gate_credit: bool = False
    hardware_verified: bool = False

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _safe_regular_file(path: Path, label: str) -> Path:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise KernelReproDiagnosticError(f"{label} must be a regular non-symlink file")
    try:
        return candidate.resolve(strict=True)
    except OSError as exc:
        raise KernelReproDiagnosticError(f"cannot resolve {label}") from exc


def _hash_file(path: Path, chunk_size: int) -> tuple[str, int]:
    digest = sha256()
    total = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
    return digest.hexdigest(), total


def _record_range(
    ranges: list[ByteRangeDifference],
    start: int,
    end_exclusive: int,
    differing_bytes: int,
    *,
    max_ranges: int,
) -> None:
    if len(ranges) < max_ranges:
        ranges.append(
            ByteRangeDifference(
                start=start,
                end_exclusive=end_exclusive,
                differing_bytes=differing_bytes,
            )
        )


def diagnose_kernel_image_divergence(
    image_a: Path,
    image_b: Path,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    max_ranges: int = DEFAULT_MAX_RANGES,
) -> KernelImageDivergenceEvidence:
    """Compare two kernel Images and emit bounded location/count evidence.

    A range is a maximal contiguous run of byte offsets whose values differ.  If file
    sizes differ, the trailing bytes are represented as one additional differing
    range.  The total count/range count remains exact even if ``reported_ranges`` is
    capped.
    """
    if not isinstance(chunk_size, int) or isinstance(chunk_size, bool) or chunk_size < 4096:
        raise KernelReproDiagnosticError("chunk_size must be an integer >= 4096")
    if not isinstance(max_ranges, int) or isinstance(max_ranges, bool) or max_ranges < 1:
        raise KernelReproDiagnosticError("max_ranges must be an integer >= 1")

    a = _safe_regular_file(image_a, "image A")
    b = _safe_regular_file(image_b, "image B")
    if a == b:
        raise KernelReproDiagnosticError("image A and image B must be independent files")

    hash_a, size_a = _hash_file(a, chunk_size)
    hash_b, size_b = _hash_file(b, chunk_size)
    overlap = min(size_a, size_b)

    differing_bytes = 0
    differing_range_count = 0
    first_difference: int | None = None
    last_difference: int | None = None
    reported: list[ByteRangeDifference] = []

    active_start: int | None = None
    active_count = 0
    absolute = 0

    with a.open("rb") as left, b.open("rb") as right:
        remaining = overlap
        while remaining:
            amount = min(chunk_size, remaining)
            chunk_a = left.read(amount)
            chunk_b = right.read(amount)
            if len(chunk_a) != amount or len(chunk_b) != amount:
                raise KernelReproDiagnosticError("kernel Image changed while being diagnosed")

            for index, (byte_a, byte_b) in enumerate(zip(chunk_a, chunk_b)):
                offset = absolute + index
                if byte_a != byte_b:
                    differing_bytes += 1
                    if first_difference is None:
                        first_difference = offset
                    last_difference = offset
                    if active_start is None:
                        active_start = offset
                        active_count = 1
                    else:
                        active_count += 1
                elif active_start is not None:
                    differing_range_count += 1
                    _record_range(
                        reported,
                        active_start,
                        offset,
                        active_count,
                        max_ranges=max_ranges,
                    )
                    active_start = None
                    active_count = 0
            absolute += amount
            remaining -= amount

    if active_start is not None:
        differing_range_count += 1
        _record_range(
            reported,
            active_start,
            overlap,
            active_count,
            max_ranges=max_ranges,
        )
        active_start = None

    if size_a != size_b:
        trailing = abs(size_a - size_b)
        differing_bytes += trailing
        differing_range_count += 1
        if first_difference is None:
            first_difference = overlap
        last_difference = max(size_a, size_b) - 1
        _record_range(
            reported,
            overlap,
            max(size_a, size_b),
            trailing,
            max_ranges=max_ranges,
        )

    equal = size_a == size_b and differing_bytes == 0
    if equal != (hash_a == hash_b):
        raise KernelReproDiagnosticError("byte comparison and SHA-256 result disagree")

    return KernelImageDivergenceEvidence(
        schema_version=DIAGNOSTIC_SCHEMA_VERSION,
        image_a_sha256=hash_a,
        image_b_sha256=hash_b,
        image_a_size=size_a,
        image_b_size=size_b,
        overlap_size=overlap,
        equal=equal,
        differing_byte_count=differing_bytes,
        differing_range_count=differing_range_count,
        reported_range_count=len(reported),
        omitted_range_count=max(0, differing_range_count - len(reported)),
        first_difference_offset=first_difference,
        last_difference_offset=last_difference,
        reported_ranges=tuple(reported),
        beta_gate_credit=False,
        hardware_verified=False,
    )


def write_kernel_image_divergence_evidence(
    evidence: KernelImageDivergenceEvidence,
    destination: Path,
) -> str:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = evidence.canonical_json()
    path.write_text(payload, encoding="utf-8", newline="\n")
    return sha256(payload.encode("utf-8")).hexdigest()
