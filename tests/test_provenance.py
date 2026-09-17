from pathlib import Path
from types import SimpleNamespace

import pytest

from kaliphonestudio.provenance import (
    ProvenanceError,
    build_stock_boot_provenance,
    write_immutable_provenance,
)

H = "a" * 64


def _evidence():
    ota = SimpleNamespace(sha256=H, size=2000, payload_size=1000, metadata={"post-build": "AC2003_11.F.22"})
    payload = SimpleNamespace(payload_sha256="b" * 64, metadata_sha256="c" * 64, file_size=1000)
    boot = SimpleNamespace(sha256="d" * 64, size=500, header_version=2)
    return ota, payload, boot


def test_binds_exact_ota_payload_boot_and_profile():
    ota, payload, boot = _evidence()
    record = build_stock_boot_provenance("oneplus/avicii", ota, payload, boot)
    assert record.schema_version == 1
    assert record.ota_sha256 == H
    assert record.payload_sha256 == "b" * 64
    assert record.boot_sha256 == "d" * 64
    assert record.firmware_metadata["post-build"] == "AC2003_11.F.22"
    assert len(record.evidence_sha256()) == 64
    assert record.canonical_json().endswith("\n")


def test_rejects_payload_not_from_reported_ota():
    ota, payload, boot = _evidence()
    payload.file_size = 999
    with pytest.raises(ProvenanceError, match="payload size"):
        build_stock_boot_provenance("oneplus/avicii", ota, payload, boot)


def test_requires_firmware_metadata():
    ota, payload, boot = _evidence()
    ota.metadata = {}
    with pytest.raises(ProvenanceError, match="firmware metadata"):
        build_stock_boot_provenance("oneplus/avicii", ota, payload, boot)


def test_provenance_is_immutable(tmp_path: Path):
    ota, payload, boot = _evidence()
    record = build_stock_boot_provenance("oneplus/avicii", ota, payload, boot)
    path = tmp_path / "stock.json"
    write_immutable_provenance(record, path)
    write_immutable_provenance(record, path)
    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ProvenanceError, match="different evidence"):
        write_immutable_provenance(record, path)


def test_provenance_writer_rejects_symlink(tmp_path: Path):
    ota, payload, boot = _evidence()
    record = build_stock_boot_provenance("oneplus/avicii", ota, payload, boot)
    target = tmp_path / "target.json"
    target.write_text(record.to_json(), encoding="utf-8")
    link = tmp_path / "stock.json"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable on this host")
    with pytest.raises(ProvenanceError, match="symlink"):
        write_immutable_provenance(record, link)
