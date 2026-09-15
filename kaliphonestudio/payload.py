"""Fail-closed Android A/B OTA payload header inspection.

Host-side only: this module validates payload structure and metadata boundaries.
It never extracts partitions, boots, or flashes a device.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct

PAYLOAD_MAGIC = b"CrAU"
_HEADER_V1 = struct.Struct(">4sQQ")
_HEADER_V2 = struct.Struct(">4sQQI")
_MAX_MANIFEST_SIZE = 64 * 1024 * 1024
_MAX_METADATA_SIGNATURE_SIZE = 16 * 1024 * 1024


class PayloadFormatError(ValueError):
    pass


@dataclass(frozen=True)
class PayloadHeaderReport:
    path: Path
    file_size: int
    major_version: int
    manifest_size: int
    metadata_signature_size: int
    header_size: int
    metadata_size: int
    data_offset: int


def inspect_payload(path: Path) -> PayloadHeaderReport:
    """Validate the update_engine payload envelope without parsing protobuf data."""
    if not path.is_file():
        raise PayloadFormatError(f"payload does not exist: {path}")
    file_size = path.stat().st_size
    if file_size < _HEADER_V1.size:
        raise PayloadFormatError("payload is truncated before the v1 header")

    with path.open("rb") as fh:
        prefix = fh.read(_HEADER_V1.size)
        magic, major, manifest_size = _HEADER_V1.unpack(prefix)
        if magic != PAYLOAD_MAGIC:
            raise PayloadFormatError("invalid payload magic; expected CrAU")
        if major not in (1, 2):
            raise PayloadFormatError(f"unsupported payload major version: {major}")
        signature_size = 0
        header_size = _HEADER_V1.size
        if major >= 2:
            raw = fh.read(4)
            if len(raw) != 4:
                raise PayloadFormatError("payload is truncated before metadata signature size")
            signature_size = struct.unpack(">I", raw)[0]
            header_size = _HEADER_V2.size

    if manifest_size <= 0 or manifest_size > _MAX_MANIFEST_SIZE:
        raise PayloadFormatError("manifest size is outside the fail-closed host limit")
    if signature_size > _MAX_METADATA_SIGNATURE_SIZE:
        raise PayloadFormatError("metadata signature size is outside the fail-closed host limit")
    metadata_size = header_size + manifest_size + signature_size
    if metadata_size > file_size:
        raise PayloadFormatError("declared payload metadata exceeds file size")

    return PayloadHeaderReport(
        path=path,
        file_size=file_size,
        major_version=major,
        manifest_size=manifest_size,
        metadata_signature_size=signature_size,
        header_size=header_size,
        metadata_size=metadata_size,
        data_offset=metadata_size,
    )
