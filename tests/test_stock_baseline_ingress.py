import json
from pathlib import Path
import struct
from zipfile import ZipFile

import pytest

from kaliphonestudio.boot_image import BootImageError
from kaliphonestudio.stock_baseline_ingress import (
    StockBaselineIngressError,
    prepare_stock_provenance,
    prepare_stock_provenance_main,
)

ROOT = Path(__file__).resolve().parents[1]
DEVICES = ROOT / "devices"


def _payload(marker: bytes = b"A") -> bytes:
    manifest = marker
    return struct.pack(">4sQQI", b"CrAU", 2, len(manifest), 0) + manifest + b"payload-data"


def _boot_v2() -> bytes:
    image = bytearray(4096)
    image[:8] = b"ANDROID!"
    struct.pack_into("<I", image, 40, 2)
    return bytes(image)


def _inputs(tmp_path: Path, *, ota_payload: bytes | None = None, external_payload: bytes | None = None):
    ota_payload = ota_payload or _payload()
    external_payload = external_payload or ota_payload
    ota = tmp_path / "oxygenos.zip"
    with ZipFile(ota, "w") as zf:
        zf.writestr("payload.bin", ota_payload)
        zf.writestr(
            "META-INF/com/android/metadata",
            "pre-device=avicii\n"
            "post-build=OnePlus/avicii/AC2003:13/RKQ1/test:user/release-keys\n"
            "post-build-incremental=AC2003_TEST\n",
        )
    payload = tmp_path / "payload.bin"
    payload.write_bytes(external_payload)
    boot = tmp_path / "boot.img"
    boot.write_bytes(_boot_v2())
    return ota, payload, boot


def test_prepare_stock_provenance_binds_exact_ota_payload_and_boot(tmp_path: Path):
    ota, payload, boot = _inputs(tmp_path)
    record, ota_sha, ota_size, boot_sha, boot_size = prepare_stock_provenance(
        devices_root=DEVICES,
        profile_id="oneplus/avicii",
        ota_path=ota,
        payload_path=payload,
        stock_boot_path=boot,
    )
    assert record.profile_id == "oneplus/avicii"
    assert record.ota_sha256 == ota_sha
    assert record.ota_size == ota_size
    assert record.payload_sha256
    assert record.boot_sha256 == boot_sha
    assert record.boot_size == boot_size
    assert record.boot_header_version == 2
    assert record.firmware_metadata["pre-device"] == "avicii"


def test_prepare_rejects_same_size_payload_from_different_ota(tmp_path: Path):
    good = _payload(b"A")
    different = _payload(b"B")
    assert len(good) == len(different)
    ota, payload, boot = _inputs(tmp_path, ota_payload=good, external_payload=different)
    with pytest.raises(StockBaselineIngressError, match="SHA-256"):
        prepare_stock_provenance(
            devices_root=DEVICES,
            profile_id="oneplus/avicii",
            ota_path=ota,
            payload_path=payload,
            stock_boot_path=boot,
        )


def test_prepare_rejects_stock_boot_with_wrong_header(tmp_path: Path):
    ota, payload, boot = _inputs(tmp_path)
    broken = bytearray(boot.read_bytes())
    struct.pack_into("<I", broken, 40, 3)
    boot.write_bytes(broken)
    with pytest.raises(BootImageError, match="boot header mismatch"):
        prepare_stock_provenance(
            devices_root=DEVICES,
            profile_id="oneplus/avicii",
            ota_path=ota,
            payload_path=payload,
            stock_boot_path=boot,
        )


def test_prepare_cli_writes_immutable_non_promoting_provenance(tmp_path: Path, capsys):
    ota, payload, boot = _inputs(tmp_path)
    out = tmp_path / "stock-provenance.json"
    rc = prepare_stock_provenance_main([
        "--devices-root", str(DEVICES),
        "--profile-id", "oneplus/avicii",
        "--ota", str(ota),
        "--payload", str(payload),
        "--stock-boot", str(boot),
        "--out", str(out),
    ])
    assert rc == 0
    result = json.loads(capsys.readouterr().out)
    assert out.is_file()
    evidence = json.loads(out.read_text(encoding="utf-8"))
    assert evidence["payload_sha256"] == result["payload_sha256"]
    assert result["phone_queried"] is False
    assert result["phone_storage_written"] is False
    assert result["temporary_boot_authorized"] is False
    assert result["hardware_verified"] is False
    assert result["beta_gate_credit"] is False

    rc = prepare_stock_provenance_main([
        "--devices-root", str(DEVICES),
        "--profile-id", "oneplus/avicii",
        "--ota", str(ota),
        "--payload", str(payload),
        "--stock-boot", str(boot),
        "--out", str(out),
    ])
    assert rc == 2
    assert "refusing to overwrite" in capsys.readouterr().err


def test_prepare_rejects_symlinked_payload(tmp_path: Path):
    ota, payload, boot = _inputs(tmp_path)
    link = tmp_path / "payload-link.bin"
    try:
        link.symlink_to(payload)
    except OSError:
        pytest.skip("symlinks unavailable on this host")
    with pytest.raises(StockBaselineIngressError, match="non-symlink"):
        prepare_stock_provenance(
            devices_root=DEVICES,
            profile_id="oneplus/avicii",
            ota_path=ota,
            payload_path=link,
            stock_boot_path=boot,
        )
