import json
from hashlib import sha256
from pathlib import Path
import struct
from zipfile import ZipFile

import pytest

from kaliphonestudio.extractor import ExtractionError
from kaliphonestudio.stock_ota_pipeline import (
    StockOTAPipelineError,
    prepare_stock_from_ota,
)

ROOT = Path(__file__).resolve().parents[1]
DEVICES = ROOT / "devices"
EXACT_FINGERPRINT = "OnePlus/avicii/AC2003:13/RKQ1/test:user/release-keys"


def _payload() -> bytes:
    manifest = b"A"
    return struct.pack(">4sQQI", b"CrAU", 2, len(manifest), 0) + manifest + b"payload-data"


def _write_ota(path: Path) -> bytes:
    payload = _payload()
    with ZipFile(path, "w") as zf:
        zf.writestr("payload.bin", payload)
        zf.writestr(
            "META-INF/com/android/metadata",
            "pre-device=avicii\n"
            f"post-build={EXACT_FINGERPRINT}\n"
            "post-build-incremental=AC2003_TEST\n",
        )
    return payload


def _write_fake_extractor(path: Path) -> str:
    script = """#!/usr/bin/env python3
import pathlib
import struct
import sys

args = sys.argv[1:]
out = pathlib.Path(args[args.index("-o") + 1])
out.mkdir(parents=True, exist_ok=True)
page_size = 4096
kernel_size = 32
ramdisk_size = 24
dtb_size = 16
image = bytearray(page_size * 4)
image[:8] = b"ANDROID!"
struct.pack_into("<I", image, 8, kernel_size)
struct.pack_into("<I", image, 16, ramdisk_size)
struct.pack_into("<I", image, 24, 0)
struct.pack_into("<I", image, 36, page_size)
struct.pack_into("<I", image, 40, 2)
struct.pack_into("<I", image, 1632, 0)
struct.pack_into("<Q", image, 1636, 0)
struct.pack_into("<I", image, 1644, 1660)
struct.pack_into("<I", image, 1648, dtb_size)
struct.pack_into("<Q", image, 1652, 0x10000000)
image[page_size : page_size + kernel_size] = b"K" * kernel_size
image[page_size * 2 : page_size * 2 + ramdisk_size] = b"R" * ramdisk_size
image[page_size * 3 : page_size * 3 + dtb_size] = b"D" * dtb_size
(out / "boot.img").write_bytes(image)
"""
    path.write_text(script, encoding="utf-8", newline="\n")
    path.chmod(0o755)
    return sha256(path.read_bytes()).hexdigest()


def _write_manifest(path: Path, tool_sha: str) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "extractor": "payload-dumper-go",
                "source": {
                    "url": "https://github.com/example/payload-dumper-go",
                    "commit": "a" * 40,
                },
                "build": {
                    "toolchain": "go",
                    "toolchain_version": "1.27.0",
                    "command": ["go", "build", "-trimpath", "-o", "payload-dumper-go", "."],
                },
                "artifacts": {"test-amd64": {"sha256": tool_sha}},
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.skipif(__import__("os").name == "nt", reason="fake executable test uses a POSIX shebang")
def test_extracts_exact_ota_payload_boot_and_provenance_in_one_bundle(tmp_path: Path):
    ota = tmp_path / "oxygenos.zip"
    expected_payload = _write_ota(ota)
    tool = tmp_path / "payload-dumper-go"
    tool_sha = _write_fake_extractor(tool)
    manifest = tmp_path / "extractor-locks.json"
    _write_manifest(manifest, tool_sha)
    out = tmp_path / "stock-bundle"

    report, provenance = prepare_stock_from_ota(
        devices_root=DEVICES,
        profile_id="oneplus/avicii",
        ota_path=ota,
        extractor_path=tool,
        extractor_manifest_path=manifest,
        extractor_platform="test-amd64",
        output_dir=out,
        expected_firmware_fingerprint=EXACT_FINGERPRINT,
    )

    assert (out / "payload.bin").read_bytes() == expected_payload
    assert (out / "partitions" / "boot.img").is_file()
    assert (out / "stock-provenance.json").is_file()
    evidence = json.loads((out / "stock-extraction-report.json").read_text(encoding="utf-8"))
    assert evidence["schema_version"] == 2
    assert evidence["payload_sha256"] == sha256(expected_payload).hexdigest()
    assert evidence["boot_sha256"] == provenance.boot_sha256
    assert evidence["extractor_sha256"] == tool_sha
    assert evidence["extractor_manifest_sha256"] == sha256(manifest.read_bytes()).hexdigest()
    assert evidence["extractor_source_commit"] == "a" * 40
    assert evidence["extractor_source_url"] == "https://github.com/example/payload-dumper-go"
    assert evidence["stock_provenance_sha256"] == provenance.evidence_sha256()
    assert evidence["expected_firmware_fingerprint"] == EXACT_FINGERPRINT
    assert evidence["ota_post_build_fingerprint"] == EXACT_FINGERPRINT
    assert evidence["exact_firmware_fingerprint_match"] is True
    assert evidence["phone_queried"] is False
    assert evidence["phone_storage_written"] is False
    assert evidence["temporary_boot_authorized"] is False
    assert evidence["hardware_verified"] is False
    assert evidence["beta_gate_credit"] is False
    assert report.stock_provenance_sha256 == provenance.evidence_sha256()


@pytest.mark.skipif(__import__("os").name == "nt", reason="fake executable test uses a POSIX shebang")
def test_exact_physical_fingerprint_mismatch_refuses_before_output(tmp_path: Path):
    ota = tmp_path / "oxygenos.zip"
    _write_ota(ota)
    tool = tmp_path / "payload-dumper-go"
    tool_sha = _write_fake_extractor(tool)
    manifest = tmp_path / "extractor-locks.json"
    _write_manifest(manifest, tool_sha)
    out = tmp_path / "stock-bundle"

    with pytest.raises(StockOTAPipelineError, match="does not match"):
        prepare_stock_from_ota(
            devices_root=DEVICES,
            profile_id="oneplus/avicii",
            ota_path=ota,
            extractor_path=tool,
            extractor_manifest_path=manifest,
            extractor_platform="test-amd64",
            output_dir=out,
            expected_firmware_fingerprint="OnePlus/avicii/AC2003:13/RKQ1/other:user/release-keys",
        )
    assert not out.exists()


@pytest.mark.skipif(__import__("os").name == "nt", reason="fake executable test uses a POSIX shebang")
def test_pipeline_is_create_only_and_refuses_existing_output(tmp_path: Path):
    ota = tmp_path / "oxygenos.zip"
    _write_ota(ota)
    tool = tmp_path / "payload-dumper-go"
    tool_sha = _write_fake_extractor(tool)
    manifest = tmp_path / "extractor-locks.json"
    _write_manifest(manifest, tool_sha)
    out = tmp_path / "stock-bundle"
    out.mkdir()

    with pytest.raises(StockOTAPipelineError, match="existing output"):
        prepare_stock_from_ota(
            devices_root=DEVICES,
            profile_id="oneplus/avicii",
            ota_path=ota,
            extractor_path=tool,
            extractor_manifest_path=manifest,
            extractor_platform="test-amd64",
            output_dir=out,
        )


def test_pipeline_rejects_unknown_locked_extractor_platform_before_output(tmp_path: Path):
    ota = tmp_path / "oxygenos.zip"
    _write_ota(ota)
    tool = tmp_path / "payload-dumper-go"
    tool.write_bytes(b"not-reviewed")
    manifest = ROOT / "tools" / "extractor-locks.json"
    out = tmp_path / "stock-bundle"

    with pytest.raises(ExtractionError, match="not authorized"):
        prepare_stock_from_ota(
            devices_root=DEVICES,
            profile_id="oneplus/avicii",
            ota_path=ota,
            extractor_path=tool,
            extractor_manifest_path=manifest,
            extractor_platform="unknown-amd64",
            output_dir=out,
        )
    assert not out.exists()
