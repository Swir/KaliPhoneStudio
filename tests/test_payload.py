from pathlib import Path
import struct

import pytest

from kaliphonestudio.payload import PayloadFormatError, inspect_payload


def _payload(path: Path, *, major: int = 2, manifest: bytes = b"manifest", signature: bytes = b"sig", data: bytes = b"data") -> Path:
    header = struct.pack(">4sQQ", b"CrAU", major, len(manifest))
    if major >= 2:
        header += struct.pack(">I", len(signature))
    path.write_bytes(header + manifest + (signature if major >= 2 else b"") + data)
    return path


def test_inspects_v2_payload_boundaries(tmp_path: Path):
    report = inspect_payload(_payload(tmp_path / "payload.bin"))
    assert report.major_version == 2
    assert report.header_size == 24
    assert report.manifest_size == 8
    assert report.metadata_signature_size == 3
    assert report.data_offset == 35


def test_inspects_v1_without_signature_field(tmp_path: Path):
    report = inspect_payload(_payload(tmp_path / "payload.bin", major=1))
    assert report.header_size == 20
    assert report.metadata_signature_size == 0


def test_rejects_wrong_magic(tmp_path: Path):
    path = _payload(tmp_path / "payload.bin")
    raw = bytearray(path.read_bytes())
    raw[:4] = b"NOPE"
    path.write_bytes(raw)
    with pytest.raises(PayloadFormatError, match="magic"):
        inspect_payload(path)


def test_rejects_unknown_major_version(tmp_path: Path):
    with pytest.raises(PayloadFormatError, match="unsupported"):
        inspect_payload(_payload(tmp_path / "payload.bin", major=3))


def test_rejects_declared_metadata_past_eof(tmp_path: Path):
    path = tmp_path / "payload.bin"
    path.write_bytes(struct.pack(">4sQQI", b"CrAU", 2, 4096, 0) + b"tiny")
    with pytest.raises(PayloadFormatError, match="exceeds file size"):
        inspect_payload(path)
