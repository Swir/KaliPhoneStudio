"""Small audited LZ4 legacy-frame codec for deterministic ramdisk artifacts.

Android's BOARD_RAMDISK_USE_LZ4 build path uses the LZ4 *legacy* framing
(`lz4 -l`), not the modern LZ4 frame format.  KaliPhoneStudio only needs a
safe deterministic encoder for rescue initramfs artifacts, so the encoder
intentionally emits literal-only LZ4 blocks.  This trades compression ratio
for a tiny, reviewable implementation while remaining a valid legacy stream
for the kernel LZ4 decompressor.

Format references pinned during implementation:
- AOSP platform/build core/Makefile @
  5db2b8fa45a8ba9e90f76f583bc46ffdcf6c3c57 (`lz4 -l -12 --favor-decSpeed`)
- lz4/lz4 v1.10.0 @ ebb370ca83af193212df4dcbadcc5d87bc0de2f0
"""
from __future__ import annotations

from dataclasses import dataclass


LEGACY_MAGIC = 0x184C2102
LEGACY_MAGIC_BYTES = LEGACY_MAGIC.to_bytes(4, "little")
LEGACY_BLOCK_SIZE = 8 * 1024 * 1024
_MAX_COMPRESSED_BLOCK = LEGACY_BLOCK_SIZE + (LEGACY_BLOCK_SIZE // 255) + 32

AOSP_RAMDISK_POLICY_COMMIT = "5db2b8fa45a8ba9e90f76f583bc46ffdcf6c3c57"
LZ4_REFERENCE_COMMIT = "ebb370ca83af193212df4dcbadcc5d87bc0de2f0"
LZ4_REFERENCE_VERSION = "1.10.0"


class Lz4LegacyError(ValueError):
    """Raised for malformed or resource-unsafe LZ4 legacy streams."""


@dataclass(frozen=True)
class Lz4LegacyInspection:
    block_count: int
    compressed_size: int
    uncompressed_size: int


def _write_length_extension(buffer: bytearray, value: int) -> None:
    if value < 0:
        raise Lz4LegacyError("negative LZ4 length extension")
    while value >= 255:
        buffer.append(255)
        value -= 255
    buffer.append(value)


def _read_length_extension(payload: bytes, cursor: int, base: int) -> tuple[int, int]:
    length = base
    if base != 15:
        return length, cursor
    while True:
        if cursor >= len(payload):
            raise Lz4LegacyError("truncated LZ4 length extension")
        extra = payload[cursor]
        cursor += 1
        length += extra
        if extra != 255:
            return length, cursor


def encode_literal_block(payload: bytes) -> bytes:
    """Encode one LZ4 block using only the final literal sequence.

    A literal-only final sequence is valid LZ4 block syntax and makes output
    completely deterministic without depending on a host compressor build.
    """
    if len(payload) > LEGACY_BLOCK_SIZE:
        raise Lz4LegacyError("legacy LZ4 block exceeds the 8 MiB format contract")
    literal_nibble = min(len(payload), 15)
    result = bytearray([literal_nibble << 4])
    if len(payload) >= 15:
        _write_length_extension(result, len(payload) - 15)
    result.extend(payload)
    if len(result) > _MAX_COMPRESSED_BLOCK:
        raise Lz4LegacyError("encoded LZ4 block exceeds the safety bound")
    return bytes(result)


def decode_block(payload: bytes, *, max_output: int = LEGACY_BLOCK_SIZE) -> bytes:
    """Decode standard LZ4 block sequences with an explicit output bound."""
    if max_output <= 0:
        raise Lz4LegacyError("LZ4 output limit must be positive")
    cursor = 0
    output = bytearray()
    while cursor < len(payload):
        token = payload[cursor]
        cursor += 1
        literal_length, cursor = _read_length_extension(payload, cursor, token >> 4)
        if literal_length > len(payload) - cursor:
            raise Lz4LegacyError("truncated LZ4 literal sequence")
        if len(output) + literal_length > max_output:
            raise Lz4LegacyError("LZ4 block exceeds the decompressed output limit")
        output.extend(payload[cursor : cursor + literal_length])
        cursor += literal_length

        # A block is allowed to end immediately after the final literals.
        if cursor == len(payload):
            break
        if cursor + 2 > len(payload):
            raise Lz4LegacyError("truncated LZ4 match offset")
        match_offset = int.from_bytes(payload[cursor : cursor + 2], "little")
        cursor += 2
        if match_offset <= 0 or match_offset > len(output):
            raise Lz4LegacyError("invalid LZ4 match offset")
        match_length, cursor = _read_length_extension(payload, cursor, token & 0x0F)
        match_length += 4
        if len(output) + match_length > max_output:
            raise Lz4LegacyError("LZ4 block exceeds the decompressed output limit")
        for _ in range(match_length):
            output.append(output[-match_offset])
    return bytes(output)


def compress_legacy(payload: bytes) -> bytes:
    """Create a deterministic Linux-kernel-compatible LZ4 legacy stream."""
    output = bytearray(LEGACY_MAGIC_BYTES)
    for start in range(0, len(payload), LEGACY_BLOCK_SIZE):
        block = encode_literal_block(payload[start : start + LEGACY_BLOCK_SIZE])
        output.extend(len(block).to_bytes(4, "little"))
        output.extend(block)
    return bytes(output)


def decompress_legacy(
    payload: bytes,
    *,
    max_output_bytes: int = 256 * 1024 * 1024,
) -> tuple[bytes, Lz4LegacyInspection]:
    """Decode and structurally inspect an LZ4 legacy stream.

    Legacy streams end at EOF (there is no required zero-sized end block), so
    every remaining byte must belong to a complete block header/payload pair.
    """
    if max_output_bytes <= 0:
        raise Lz4LegacyError("LZ4 frame output limit must be positive")
    if len(payload) < len(LEGACY_MAGIC_BYTES) or payload[:4] != LEGACY_MAGIC_BYTES:
        raise Lz4LegacyError("invalid LZ4 legacy magic")

    cursor = 4
    block_count = 0
    output = bytearray()
    while cursor < len(payload):
        if cursor + 4 > len(payload):
            raise Lz4LegacyError("truncated LZ4 legacy block header")
        compressed_size = int.from_bytes(payload[cursor : cursor + 4], "little")
        cursor += 4
        if compressed_size <= 0 or compressed_size > _MAX_COMPRESSED_BLOCK:
            raise Lz4LegacyError("invalid LZ4 legacy compressed block size")
        if cursor + compressed_size > len(payload):
            raise Lz4LegacyError("truncated LZ4 legacy block payload")
        block = payload[cursor : cursor + compressed_size]
        cursor += compressed_size
        remaining = max_output_bytes - len(output)
        if remaining <= 0:
            raise Lz4LegacyError("LZ4 legacy stream exceeds the output limit")
        decoded = decode_block(block, max_output=min(LEGACY_BLOCK_SIZE, remaining))
        output.extend(decoded)
        block_count += 1

    return bytes(output), Lz4LegacyInspection(
        block_count=block_count,
        compressed_size=len(payload),
        uncompressed_size=len(output),
    )
