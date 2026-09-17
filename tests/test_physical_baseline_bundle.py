from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from kaliphonestudio.fastboot_baseline import capture_fastboot_baseline
from kaliphonestudio.fastboot_capture_bundle import (
    FastbootCaptureBundleError,
    bind_fastboot_capture,
    verify_fastboot_capture_bundle,
    write_fastboot_capture_bundle,
)
from kaliphonestudio.fastboot_tool import FastbootToolEvidence
from kaliphonestudio.physical_baseline_bundle import (
    PhysicalBaselineBundleError,
    bind_physical_baseline_to_stock,
    verify_physical_baseline_bundle,
    write_physical_baseline_bundle,
)
from kaliphonestudio.profiles import get_profile
from kaliphonestudio.provenance import StockBootProvenance

ROOT = Path(__file__).resolve().parents[1]
DEVICES = ROOT / "devices"


def _profile():
    return get_profile(DEVICES, "oneplus/avicii")


def _transcript() -> bytes:
    return (
        "(bootloader) product: avicii\n"
        "(bootloader) serialno: SERIAL123\n"
        "(bootloader) current-slot: a\n"
        "(bootloader) slot-count: 2\n"
        "(bootloader) unlocked: no\n"
        "(bootloader) secure: yes\n"
        "(bootloader) version-bootloader: avicii-test-1\n"
        "(bootloader) version-baseband: modem-test-1\n"
        "Finished. Total time: 0.003s\n"
    ).encode()


def _baseline(tmp_path: Path):
    transcript = tmp_path / "fastboot.txt"
    transcript.write_bytes(_transcript())
    evidence = capture_fastboot_baseline(
        _profile(),
        transcript=transcript,
        firmware_build="AC2003_11_F.22",
        firmware_fingerprint="OnePlus/avicii/avicii:13/test/F.22:user/release-keys",
    )
    return evidence, transcript


def _tool() -> FastbootToolEvidence:
    return FastbootToolEvidence(
        schema_version=1,
        tool="fastboot",
        policy_sha256="1" * 64,
        required_platform_tools_version="37.0.1",
        observed_platform_tools_version="37.0.1",
        executable_filename="fastboot.exe",
        executable_sha256="2" * 64,
        executable_size=123456,
        version_line="fastboot version 37.0.1-13704100",
        version_output_sha256="3" * 64,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def _stock() -> StockBootProvenance:
    return StockBootProvenance(
        schema_version=1,
        profile_id="oneplus/avicii",
        ota_sha256="4" * 64,
        ota_size=4_000_000_000,
        payload_sha256="5" * 64,
        payload_metadata_sha256="6" * 64,
        payload_size=3_500_000_000,
        boot_sha256="7" * 64,
        boot_size=96 * 1024 * 1024,
        boot_header_version=2,
        firmware_metadata={
            "post-build": "OnePlus/avicii/avicii:13/test/F.22:user/release-keys",
            "post-build-incremental": "AC2003_11_F.22",
            "pre-device": "avicii",
        },
    )


def test_capture_bundle_binds_tool_baseline_and_raw_transcript(tmp_path: Path):
    baseline, transcript = _baseline(tmp_path)
    bundle = bind_fastboot_capture(_profile(), baseline, _tool(), transcript=transcript)
    assert bundle.profile_id == "oneplus/avicii"
    assert bundle.device_serial == "SERIAL123"
    assert bundle.transcript_sha256 == sha256(_transcript()).hexdigest()
    assert bundle.baseline_evidence_sha256 == baseline.evidence_sha256()
    assert bundle.fastboot_tool_evidence_sha256 == _tool().evidence_sha256()
    assert bundle.capture_policy == "fastboot-version+devices+serial-getvar-all-v1"
    assert bundle.read_only is True
    assert bundle.phone_storage_written is False
    assert bundle.hardware_verified is False
    assert bundle.beta_gate_credit is False
    verify_fastboot_capture_bundle(bundle, _profile(), baseline, _tool(), transcript=transcript)


def test_capture_bundle_rejects_transcript_or_tool_drift(tmp_path: Path):
    baseline, transcript = _baseline(tmp_path)
    transcript.write_bytes(_transcript() + b"noise\n")
    with pytest.raises(FastbootCaptureBundleError, match="does not match"):
        bind_fastboot_capture(_profile(), baseline, _tool(), transcript=transcript)

    transcript.write_bytes(_transcript())
    bad_tool = replace(_tool(), observed_platform_tools_version="36.0.2")
    with pytest.raises(FastbootCaptureBundleError, match="exact reviewed version"):
        bind_fastboot_capture(_profile(), baseline, bad_tool, transcript=transcript)


def test_capture_bundle_writer_is_immutable(tmp_path: Path):
    baseline, transcript = _baseline(tmp_path)
    bundle = bind_fastboot_capture(_profile(), baseline, _tool(), transcript=transcript)
    out = tmp_path / "capture.json"
    assert write_fastboot_capture_bundle(bundle, out) == bundle.evidence_sha256()
    with pytest.raises(FastbootCaptureBundleError, match="overwrite"):
        write_fastboot_capture_bundle(bundle, out)


def test_physical_bundle_binds_exact_ota_stock_boot_and_capture(tmp_path: Path):
    baseline, transcript = _baseline(tmp_path)
    capture = bind_fastboot_capture(_profile(), baseline, _tool(), transcript=transcript)
    stock = _stock()
    bundle = bind_physical_baseline_to_stock(_profile(), baseline, capture, stock)
    assert bundle.fastboot_capture_bundle_sha256 == capture.evidence_sha256()
    assert bundle.stock_provenance_sha256 == stock.evidence_sha256()
    assert bundle.stock_ota_sha256 == "4" * 64
    assert bundle.stock_boot_sha256 == "7" * 64
    assert bundle.baseline_matches_exact_stock_ota is True
    assert bundle.ready_for_candidate_instantiation is True
    assert bundle.temporary_boot_authorized is False
    assert bundle.hardware_verified is False
    assert bundle.beta_gate_credit is False
    verify_physical_baseline_bundle(bundle, _profile(), baseline, capture, stock)


def test_physical_bundle_rejects_firmware_or_capture_substitution(tmp_path: Path):
    baseline, transcript = _baseline(tmp_path)
    capture = bind_fastboot_capture(_profile(), baseline, _tool(), transcript=transcript)
    wrong_stock = replace(
        _stock(),
        firmware_metadata={
            "post-build": "OnePlus/avicii/avicii:13/other/F.23:user/release-keys",
            "post-build-incremental": "AC2003_11_F.23",
        },
    )
    with pytest.raises(PhysicalBaselineBundleError, match="fingerprint"):
        bind_physical_baseline_to_stock(_profile(), baseline, capture, wrong_stock)

    detached = replace(capture, baseline_evidence_sha256="8" * 64)
    with pytest.raises(PhysicalBaselineBundleError, match="detached"):
        bind_physical_baseline_to_stock(_profile(), baseline, detached, _stock())


def test_physical_bundle_writer_is_immutable(tmp_path: Path):
    baseline, transcript = _baseline(tmp_path)
    capture = bind_fastboot_capture(_profile(), baseline, _tool(), transcript=transcript)
    bundle = bind_physical_baseline_to_stock(_profile(), baseline, capture, _stock())
    out = tmp_path / "physical.json"
    assert write_physical_baseline_bundle(bundle, out) == bundle.evidence_sha256()
    with pytest.raises(PhysicalBaselineBundleError, match="overwrite"):
        write_physical_baseline_bundle(bundle, out)
