from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import struct

import pytest

from kaliphonestudio.boot_builder import BootBuildPlan, BuildInput
from kaliphonestudio.boot_image import AVB_FOOTER_SIZE, inspect_boot_image
from kaliphonestudio.physical_baseline_bundle import PhysicalBaselineBundleEvidence
from kaliphonestudio.physical_boot_identity_binding import (
    PhysicalBootIdentityBindingError,
    bind_physical_boot_identity,
    verify_physical_boot_identity_binding,
    write_physical_boot_identity_binding,
)
from kaliphonestudio.physical_candidate_gate import PhysicalCandidateGateEvidence
from kaliphonestudio.profiles import get_profile
from kaliphonestudio.provenance import StockBootProvenance


ROOT = Path(__file__).parents[1]
PROFILE = get_profile(ROOT / "devices", "oneplus/avicii")


def _sha(label: str) -> str:
    return sha256(label.encode("utf-8")).hexdigest()


def _align(value: int, page_size: int) -> int:
    return 0 if value == 0 else ((value + page_size - 1) // page_size) * page_size


def _boot_image(
    tmp_path: Path,
    name: str,
    *,
    kernel_byte: int,
    ramdisk_byte: int,
    dtb_byte: int,
) -> Path:
    page_size = 4096
    kernel = bytes([kernel_byte]) * 32
    ramdisk = bytes([ramdisk_byte]) * 24
    dtb = bytes([dtb_byte]) * 16
    kernel_offset = page_size
    ramdisk_offset = kernel_offset + _align(len(kernel), page_size)
    dtb_offset = ramdisk_offset + _align(len(ramdisk), page_size)
    expected_end = dtb_offset + _align(len(dtb), page_size)

    data = bytearray(expected_end)
    data[:8] = b"ANDROID!"
    struct.pack_into("<I", data, 8, len(kernel))
    struct.pack_into("<I", data, 16, len(ramdisk))
    struct.pack_into("<I", data, 24, 0)
    struct.pack_into("<I", data, 36, page_size)
    struct.pack_into("<I", data, 40, 2)
    struct.pack_into("<I", data, 1632, 0)
    struct.pack_into("<Q", data, 1636, dtb_offset)
    struct.pack_into("<I", data, 1644, 1660)
    struct.pack_into("<I", data, 1648, len(dtb))
    struct.pack_into("<Q", data, 1652, 0x10000000)
    data[kernel_offset : kernel_offset + len(kernel)] = kernel
    data[ramdisk_offset : ramdisk_offset + len(ramdisk)] = ramdisk
    data[dtb_offset : dtb_offset + len(dtb)] = dtb

    path = tmp_path / name
    path.write_bytes(data)
    return path


def _append_avb(path: Path) -> tuple[str, int, int]:
    original = path.read_bytes()
    vbmeta = bytearray(256)
    struct.pack_into(">4sIIQQ", vbmeta, 0, b"AVB0", 1, 0, 0, 0)
    vbmeta_sha = sha256(vbmeta).hexdigest()
    footer = struct.pack(
        ">4sIIQQQ28x",
        b"AVBf",
        1,
        0,
        len(original),
        len(original),
        len(vbmeta),
    )
    assert len(footer) == AVB_FOOTER_SIZE
    path.write_bytes(original + vbmeta + footer)
    return vbmeta_sha, len(original), len(vbmeta)


def _fixture_chain(tmp_path: Path, *, stock_avb: bool = False):
    stock = _boot_image(
        tmp_path,
        "stock-boot.img",
        kernel_byte=0x11,
        ramdisk_byte=0x22,
        dtb_byte=0x33,
    )
    expected_stock_vbmeta = None
    expected_stock_original_size = None
    expected_stock_vbmeta_size = None
    if stock_avb:
        expected_stock_vbmeta, expected_stock_original_size, expected_stock_vbmeta_size = _append_avb(stock)

    candidate = _boot_image(
        tmp_path,
        "candidate-boot.img",
        kernel_byte=0x41,
        ramdisk_byte=0x52,
        dtb_byte=0x63,
    )
    dtbo = tmp_path / "dtbo.img"
    dtbo.write_bytes(bytes(range(64)))

    stock_report = inspect_boot_image(stock, PROFILE)
    candidate_report = inspect_boot_image(candidate, PROFILE)
    dtbo_bytes = dtbo.read_bytes()
    dtbo_sha = sha256(dtbo_bytes).hexdigest()

    provenance = StockBootProvenance(
        schema_version=1,
        profile_id=PROFILE.profile_id,
        ota_sha256=_sha("ota"),
        ota_size=8_000_000,
        payload_sha256=_sha("payload"),
        payload_metadata_sha256=_sha("payload-metadata"),
        payload_size=7_000_000,
        boot_sha256=stock_report.sha256,
        boot_size=stock_report.size,
        boot_header_version=2,
        firmware_metadata={
            "post-build": "AC2003_11_F.24",
            "post-build-incremental": "F.24",
        },
    )

    physical = PhysicalBaselineBundleEvidence(
        schema_version=1,
        profile_id=PROFILE.profile_id,
        device_serial="SERIAL-EXACT-01",
        product="avicii",
        firmware_build="AC2003_11_F.24",
        firmware_fingerprint="OnePlus/avicii/avicii:12/RKQ1/test:user/release-keys",
        fastboot_capture_bundle_sha256=_sha("capture"),
        fastboot_baseline_evidence_sha256=_sha("baseline"),
        fastboot_transcript_sha256=_sha("transcript"),
        stock_provenance_sha256=provenance.evidence_sha256(),
        stock_ota_sha256=provenance.ota_sha256,
        stock_ota_size=provenance.ota_size,
        stock_payload_sha256=provenance.payload_sha256,
        stock_payload_metadata_sha256=provenance.payload_metadata_sha256,
        stock_payload_size=provenance.payload_size,
        stock_boot_sha256=provenance.boot_sha256,
        stock_boot_size=provenance.boot_size,
        stock_boot_header_version=provenance.boot_header_version,
        firmware_metadata_sha256=_sha("firmware-metadata"),
        baseline_matches_exact_stock_ota=True,
        ready_for_candidate_instantiation=True,
        temporary_boot_authorized=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )

    plan = BootBuildPlan(
        schema_version=1,
        profile_id=PROFILE.profile_id,
        stock_boot_sha256=provenance.boot_sha256,
        stock_ota_sha256=provenance.ota_sha256,
        header_version=2,
        page_size=4096,
        ramdisk_compression="lz4",
        kernel_cmdline=tuple(PROFILE.data["kernel_cmdline"]),
        inputs=(
            BuildInput("kernel", "Image", candidate_report.kernel_size, candidate_report.kernel_sha256),
            BuildInput("ramdisk", "ramdisk.lz4", candidate_report.ramdisk_size, candidate_report.ramdisk_sha256),
            BuildInput("dtb", "dtb.img", candidate_report.dtb_size, candidate_report.dtb_sha256),
            BuildInput("dtbo", "dtbo.img", len(dtbo_bytes), dtbo_sha),
        ),
    )

    gate = PhysicalCandidateGateEvidence(
        schema_version=1,
        profile_id=PROFILE.profile_id,
        device_serial=physical.device_serial,
        firmware_build=physical.firmware_build,
        firmware_fingerprint=physical.firmware_fingerprint,
        physical_baseline_bundle_sha256=physical.evidence_sha256(),
        fastboot_capture_bundle_sha256=physical.fastboot_capture_bundle_sha256,
        fastboot_baseline_evidence_sha256=physical.fastboot_baseline_evidence_sha256,
        fastboot_transcript_sha256=physical.fastboot_transcript_sha256,
        stock_provenance_sha256=provenance.evidence_sha256(),
        stock_ota_sha256=provenance.ota_sha256,
        stock_boot_sha256=provenance.boot_sha256,
        first_boot_manifest_sha256=_sha("manifest"),
        first_boot_authority_bundle_sha256=_sha("authorities"),
        boot_authorization_sha256=_sha("boot-authorization"),
        boot_plan_sha256=plan.plan_sha256(),
        boot_image_sha256=candidate_report.sha256,
        boot_image_size=candidate_report.size,
        kernel_image_sha256=candidate_report.kernel_sha256,
        rootfs_artifact_sha256=_sha("rootfs"),
        dtb_sha256=candidate_report.dtb_sha256,
        dtbo_image_sha256=dtbo_sha,
        reviewed_authorities_bound=True,
        exact_physical_baseline_bound=True,
        ready_for_temporary_boot_offer=True,
        temporary_boot_executed=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    return {
        "stock": stock,
        "candidate": candidate,
        "dtbo": dtbo,
        "stock_report": stock_report,
        "candidate_report": candidate_report,
        "provenance": provenance,
        "physical": physical,
        "plan": plan,
        "gate": gate,
        "expected_stock_vbmeta": expected_stock_vbmeta,
        "expected_stock_original_size": expected_stock_original_size,
        "expected_stock_vbmeta_size": expected_stock_vbmeta_size,
    }


def _bind(chain):
    return bind_physical_boot_identity(
        PROFILE,
        chain["physical"],
        chain["gate"],
        chain["provenance"],
        chain["plan"],
        stock_boot=chain["stock"],
        candidate_boot=chain["candidate"],
        candidate_dtbo=chain["dtbo"],
    )


def test_binds_exact_stock_candidate_components_and_external_dtbo(tmp_path):
    chain = _fixture_chain(tmp_path)
    evidence = _bind(chain)

    assert evidence.schema_version == 1
    assert evidence.profile_id == "oneplus/avicii"
    assert evidence.stock_boot_sha256 == chain["provenance"].boot_sha256
    assert evidence.stock_kernel_sha256 == chain["stock_report"].kernel_sha256
    assert evidence.stock_ramdisk_sha256 == chain["stock_report"].ramdisk_sha256
    assert evidence.stock_dtb_sha256 == chain["stock_report"].dtb_sha256
    assert evidence.candidate_boot_sha256 == chain["gate"].boot_image_sha256
    assert evidence.candidate_kernel_sha256 == chain["candidate_report"].kernel_sha256
    assert evidence.candidate_ramdisk_sha256 == chain["candidate_report"].ramdisk_sha256
    assert evidence.candidate_dtb_sha256 == chain["candidate_report"].dtb_sha256
    assert evidence.candidate_external_dtbo_sha256 == chain["gate"].dtbo_image_sha256
    assert evidence.stock_avb_footer_present is False
    assert evidence.candidate_avb_footer_present is False
    assert evidence.stock_exact_bytes_verified is True
    assert evidence.candidate_exact_bytes_verified is True
    assert evidence.component_identity_bound is True
    assert evidence.avb_layout_bound is True
    assert evidence.temporary_boot_executed is False
    assert evidence.phone_storage_written is False
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False


def test_binds_structurally_valid_stock_avb_vbmeta_identity(tmp_path):
    chain = _fixture_chain(tmp_path, stock_avb=True)
    evidence = _bind(chain)

    assert evidence.stock_avb_footer_present is True
    assert evidence.stock_avb_vbmeta_sha256 == chain["expected_stock_vbmeta"]
    assert evidence.stock_avb_original_image_size == chain["expected_stock_original_size"]
    assert evidence.stock_avb_vbmeta_size == chain["expected_stock_vbmeta_size"]
    assert evidence.stock_avb_vbmeta_offset == chain["expected_stock_original_size"]
    assert evidence.candidate_avb_footer_present is False


def test_rejects_stock_boot_bytes_that_drift_from_immutable_provenance(tmp_path):
    chain = _fixture_chain(tmp_path)
    data = bytearray(chain["stock"].read_bytes())
    data[4096] ^= 0xFF
    chain["stock"].write_bytes(data)

    with pytest.raises(PhysicalBootIdentityBindingError, match="stock boot bytes do not match immutable provenance"):
        _bind(chain)


def test_rejects_candidate_component_drift_even_if_whole_gate_is_repointed(tmp_path):
    chain = _fixture_chain(tmp_path)
    data = bytearray(chain["candidate"].read_bytes())
    data[4096] ^= 0xFF
    chain["candidate"].write_bytes(data)
    drifted_report = inspect_boot_image(chain["candidate"], PROFILE)
    chain["gate"] = replace(
        chain["gate"],
        boot_image_sha256=drifted_report.sha256,
        boot_image_size=drifted_report.size,
        kernel_image_sha256=drifted_report.kernel_sha256,
    )

    with pytest.raises(PhysicalBootIdentityBindingError, match="kernel bytes differ from exact boot plan input"):
        _bind(chain)


def test_rejects_external_dtbo_drift(tmp_path):
    chain = _fixture_chain(tmp_path)
    chain["dtbo"].write_bytes(chain["dtbo"].read_bytes() + b"drift")

    with pytest.raises(PhysicalBootIdentityBindingError, match="candidate DTBO bytes differ from boot plan input"):
        _bind(chain)


def test_rejects_detached_stock_provenance_digest(tmp_path):
    chain = _fixture_chain(tmp_path)
    chain["gate"] = replace(chain["gate"], stock_provenance_sha256=_sha("other-provenance"))

    with pytest.raises(PhysicalBootIdentityBindingError, match="stock provenance digest is detached"):
        _bind(chain)


def test_rejects_symlink_exact_inputs(tmp_path):
    chain = _fixture_chain(tmp_path)
    link = tmp_path / "candidate-link.img"
    try:
        link.symlink_to(chain["candidate"])
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable on this platform")

    with pytest.raises(PhysicalBootIdentityBindingError, match="regular non-symlink"):
        bind_physical_boot_identity(
            PROFILE,
            chain["physical"],
            chain["gate"],
            chain["provenance"],
            chain["plan"],
            stock_boot=chain["stock"],
            candidate_boot=link,
            candidate_dtbo=chain["dtbo"],
        )


def test_verify_recomputes_exact_files_and_detects_post_binding_drift(tmp_path):
    chain = _fixture_chain(tmp_path)
    evidence = _bind(chain)
    data = bytearray(chain["candidate"].read_bytes())
    data[8192] ^= 0x7F
    chain["candidate"].write_bytes(data)

    with pytest.raises(PhysicalBootIdentityBindingError):
        verify_physical_boot_identity_binding(
            evidence,
            PROFILE,
            chain["physical"],
            chain["gate"],
            chain["provenance"],
            chain["plan"],
            stock_boot=chain["stock"],
            candidate_boot=chain["candidate"],
            candidate_dtbo=chain["dtbo"],
        )


def test_writer_is_immutable_canonical_and_refuses_promoted_flags(tmp_path):
    chain = _fixture_chain(tmp_path)
    evidence = _bind(chain)
    destination = tmp_path / "binding.json"

    digest = write_physical_boot_identity_binding(evidence, destination)
    assert digest == evidence.evidence_sha256()
    assert destination.read_bytes() == evidence.canonical_json().encode("utf-8")

    with pytest.raises(PhysicalBootIdentityBindingError, match="overwrite"):
        write_physical_boot_identity_binding(evidence, destination)

    promoted = replace(evidence, hardware_verified=True, beta_gate_credit=True)
    with pytest.raises(PhysicalBootIdentityBindingError, match="hardware/Beta credit"):
        write_physical_boot_identity_binding(promoted, tmp_path / "promoted.json")
