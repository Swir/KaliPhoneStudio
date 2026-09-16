import json
from pathlib import Path

import pytest

from kaliphonestudio.lz4_legacy import (
    AOSP_RAMDISK_POLICY_COMMIT,
    LEGACY_BLOCK_SIZE,
    LEGACY_MAGIC_BYTES,
    LZ4_REFERENCE_COMMIT,
    Lz4LegacyError,
    compress_legacy,
    decode_block,
    decompress_legacy,
    encode_literal_block,
)


@pytest.mark.parametrize("size", [0, 1, 14, 15, 270, 4096])
def test_literal_block_round_trip(size):
    payload = bytes((index * 31) % 251 for index in range(size))
    encoded = encode_literal_block(payload)
    assert decode_block(encoded) == payload


def test_decoder_handles_match_sequence_not_emitted_by_literal_encoder():
    # token: 1 literal, 4-byte match; literal 'a'; distance 1 -> b'aaaaa'
    assert decode_block(b"\x10a\x01\x00") == b"aaaaa"


def test_legacy_stream_is_deterministic_and_round_trips_multiple_blocks():
    payload = (b"KaliPhoneStudio-rescue\n" * 400_000) + b"tail"
    assert len(payload) > LEGACY_BLOCK_SIZE

    first = compress_legacy(payload)
    second = compress_legacy(payload)
    assert first == second
    assert first.startswith(LEGACY_MAGIC_BYTES)

    decoded, inspection = decompress_legacy(first, max_output_bytes=len(payload) + 1)
    assert decoded == payload
    assert inspection.block_count == 2
    assert inspection.compressed_size == len(first)
    assert inspection.uncompressed_size == len(payload)


def test_legacy_decoder_fails_closed_on_malformed_streams():
    with pytest.raises(Lz4LegacyError, match="magic"):
        decompress_legacy(b"BAD!")
    with pytest.raises(Lz4LegacyError, match="block header"):
        decompress_legacy(LEGACY_MAGIC_BYTES + b"\x01")
    with pytest.raises(Lz4LegacyError, match="truncated.*payload"):
        decompress_legacy(LEGACY_MAGIC_BYTES + (3).to_bytes(4, "little") + b"\x00")
    with pytest.raises(Lz4LegacyError, match="match offset"):
        decode_block(b"\x00\x01\x00")


def test_ramdisk_format_lock_matches_implementation_and_full_source_commits():
    lock_path = Path(__file__).resolve().parents[1] / "tools" / "ramdisk-format-locks.json"
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    lock = payload["lz4_legacy"]

    assert payload["schema_version"] == 1
    assert lock["legacy_magic_le_hex"] == LEGACY_MAGIC_BYTES.hex()
    assert lock["legacy_block_size"] == LEGACY_BLOCK_SIZE
    assert lock["artifact_compression"] == "lz4-legacy-literal-v1"
    assert lock["boot_policy"] == "lz4"
    assert lock["aosp"]["commit"] == AOSP_RAMDISK_POLICY_COMMIT
    assert lock["lz4_reference"]["commit"] == LZ4_REFERENCE_COMMIT
    assert len(lock["aosp"]["commit"]) == 40
    assert len(lock["lz4_reference"]["commit"]) == 40
    assert lock["aosp"]["reference_argv"] == ["lz4", "-l", "-12", "--favor-decSpeed"]
