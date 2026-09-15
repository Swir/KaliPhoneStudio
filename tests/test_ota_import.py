from pathlib import Path
from zipfile import ZipFile

import pytest

from kaliphonestudio.ota_import import OTAImportError, inspect_ota_zip, require_firmware_hint


def _ota(path: Path, *, metadata: str = "pre-device=avicii\npost-build=OnePlus/avicii/AC2003\n") -> Path:
    with ZipFile(path, "w") as zf:
        zf.writestr("payload.bin", b"CrAU" + b"x" * 64)
        zf.writestr("META-INF/com/android/metadata", metadata)
    return path


def test_inspect_ota_finds_payload_and_metadata(tmp_path: Path):
    report = inspect_ota_zip(_ota(tmp_path / "ota.zip"))
    assert report.payload_member == "payload.bin"
    assert report.payload_size == 68
    assert report.metadata["pre-device"] == "avicii"
    assert len(report.sha256) == 64


def test_rejects_missing_payload(tmp_path: Path):
    path = tmp_path / "bad.zip"
    with ZipFile(path, "w") as zf:
        zf.writestr("metadata", "pre-device=avicii")
    with pytest.raises(OTAImportError):
        inspect_ota_zip(path)


def test_rejects_unsafe_zip_member(tmp_path: Path):
    path = tmp_path / "bad.zip"
    with ZipFile(path, "w") as zf:
        zf.writestr("payload.bin", b"x")
        zf.writestr("../escape", b"x")
    with pytest.raises(OTAImportError):
        inspect_ota_zip(path)


def test_profile_firmware_hints_are_required(tmp_path: Path):
    report = inspect_ota_zip(_ota(tmp_path / "ota.zip"))
    require_firmware_hint(report, ["avicii", "AC2003"])
    with pytest.raises(OTAImportError):
        require_firmware_hint(report, ["different-device"])
