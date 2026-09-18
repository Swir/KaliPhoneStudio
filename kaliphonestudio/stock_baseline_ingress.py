"""Offline stock-firmware ingress for the physical KaliPhoneStudio gate.

This module bridges exact local OTA/stock bytes into the existing evidence chain.
It never executes ADB/Fastboot, never boots a phone and never writes phone storage.

Two explicit operator commands are exposed:
- ``prepare-stock-provenance``: verify profile hints, exact OTA payload bytes and
  stock boot structure, then write immutable StockBootProvenance.
- ``bind-physical-stock-baseline``: bind that provenance to one exact previously
  captured read-only Fastboot baseline/capture bundle.

Neither command grants temporary-boot authorization, hardware support or Beta
credit.
"""
from __future__ import annotations

import argparse
from dataclasses import fields
import json
from pathlib import Path
import sys
from typing import Sequence, TypeVar

from .boot_image import BootImageError, inspect_boot_image, require_candidate_compatible
from .fastboot_baseline import FastbootBaselineEvidence
from .fastboot_capture_bundle import FastbootCaptureBundleEvidence
from .ota_import import OTAImportError, inspect_ota_zip, require_firmware_hint
from .payload import PayloadFormatError, inspect_payload
from .physical_baseline_bundle import (
    PhysicalBaselineBundleError,
    bind_physical_baseline_to_stock,
    write_physical_baseline_bundle,
)
from .profiles import ProfileError, get_profile
from .provenance import (
    ProvenanceError,
    StockBootProvenance,
    build_stock_boot_provenance,
    write_immutable_provenance,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEVICES_ROOT = REPO_ROOT / "devices"
T = TypeVar("T")


class StockBaselineIngressError(ValueError):
    pass


def _regular_non_symlink(path: Path, label: str) -> Path:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise StockBaselineIngressError(f"{label} must be a regular non-symlink file: {candidate}")
    return candidate


def _stable_json_object(path: Path) -> dict[str, object]:
    candidate = _regular_non_symlink(path, "evidence file")
    before = candidate.stat()
    try:
        raw = candidate.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StockBaselineIngressError(f"cannot parse evidence JSON: {candidate}") from exc
    after = candidate.stat()
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or before.st_ino != after.st_ino
    ):
        raise StockBaselineIngressError(f"evidence file changed while being read: {candidate}")
    if not isinstance(data, dict):
        raise StockBaselineIngressError(f"evidence JSON must be an object: {candidate}")
    return data


def _load_exact(path: Path, cls: type[T]) -> T:
    data = _stable_json_object(path)
    expected = {field.name for field in fields(cls)}
    actual = set(data)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise StockBaselineIngressError(
            f"evidence schema mismatch for {path}: missing={missing} extra={extra}"
        )
    try:
        return cls(**data)
    except (TypeError, ValueError) as exc:
        raise StockBaselineIngressError(f"evidence fields are invalid for {path}") from exc


def prepare_stock_provenance(
    *,
    devices_root: Path,
    profile_id: str,
    ota_path: Path,
    payload_path: Path,
    stock_boot_path: Path,
) -> tuple[StockBootProvenance, str, int, str, int]:
    """Build exact stock provenance from already-local, non-symlink inputs.

    The external payload is deliberately required in addition to the OTA ZIP:
    later extractor/build tooling consumes that file, so we cryptographically
    prove it is byte-identical to the OTA's embedded payload.bin before binding
    any stock boot image to it.
    """
    profile = get_profile(Path(devices_root), profile_id)
    ota_file = _regular_non_symlink(ota_path, "OTA package")
    payload_file = _regular_non_symlink(payload_path, "extracted payload.bin")
    boot_file = _regular_non_symlink(stock_boot_path, "stock boot image")

    ota = inspect_ota_zip(ota_file)
    require_firmware_hint(ota, list(profile.data["firmware_hints"]))
    payload = inspect_payload(payload_file)
    if ota.payload_size != payload.file_size:
        raise StockBaselineIngressError("extracted payload size does not match exact OTA payload.bin")
    if ota.payload_sha256 != payload.payload_sha256:
        raise StockBaselineIngressError("extracted payload SHA-256 does not match exact OTA payload.bin")

    boot = inspect_boot_image(boot_file, profile)
    require_candidate_compatible(boot, profile)
    record = build_stock_boot_provenance(profile.profile_id, ota, payload, boot)
    return record, ota.sha256, ota.size, boot.sha256, boot.size


def _prepare_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="KaliPhoneStudio prepare-stock-provenance",
        description=(
            "Offline: bind an exact OTA, its byte-identical extracted payload.bin "
            "and a structurally compatible stock boot.img into immutable provenance. "
            "No phone is queried or written."
        ),
    )
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--devices-root", type=Path, default=DEFAULT_DEVICES_ROOT)
    parser.add_argument("--ota", type=Path, required=True, help="Exact local OTA ZIP.")
    parser.add_argument("--payload", type=Path, required=True, help="payload.bin extracted from that exact OTA.")
    parser.add_argument("--stock-boot", type=Path, required=True, help="boot.img extracted from that exact payload.")
    parser.add_argument("--out", type=Path, required=True, help="New immutable stock-provenance JSON path.")
    return parser


def prepare_stock_provenance_main(argv: Sequence[str] | None = None) -> int:
    args = _prepare_parser().parse_args(list(argv) if argv is not None else None)
    if args.out.exists() or args.out.is_symlink():
        print(f"refusing to overwrite output: {args.out}", file=sys.stderr)
        return 2
    try:
        record, ota_sha, ota_size, boot_sha, boot_size = prepare_stock_provenance(
            devices_root=args.devices_root,
            profile_id=args.profile_id,
            ota_path=args.ota,
            payload_path=args.payload,
            stock_boot_path=args.stock_boot,
        )
        write_immutable_provenance(record, args.out)
    except (
        StockBaselineIngressError,
        ProfileError,
        OTAImportError,
        PayloadFormatError,
        BootImageError,
        ProvenanceError,
        OSError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps({
        "profile_id": record.profile_id,
        "ota_sha256": ota_sha,
        "ota_size": ota_size,
        "payload_sha256": record.payload_sha256,
        "payload_size": record.payload_size,
        "stock_boot_sha256": boot_sha,
        "stock_boot_size": boot_size,
        "stock_provenance_sha256": record.evidence_sha256(),
        "phone_queried": False,
        "phone_storage_written": False,
        "temporary_boot_authorized": False,
        "hardware_verified": False,
        "beta_gate_credit": False,
    }, sort_keys=True))
    return 0


def _bind_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="KaliPhoneStudio bind-physical-stock-baseline",
        description=(
            "Offline: bind one exact read-only physical Fastboot capture to matching "
            "stock OTA/boot provenance. This does not authorize temporary boot."
        ),
    )
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--devices-root", type=Path, default=DEFAULT_DEVICES_ROOT)
    parser.add_argument("--baseline-evidence", type=Path, required=True)
    parser.add_argument("--capture-evidence", type=Path, required=True)
    parser.add_argument("--stock-provenance", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def bind_physical_stock_main(argv: Sequence[str] | None = None) -> int:
    args = _bind_parser().parse_args(list(argv) if argv is not None else None)
    if args.out.exists() or args.out.is_symlink():
        print(f"refusing to overwrite output: {args.out}", file=sys.stderr)
        return 2
    try:
        profile = get_profile(args.devices_root, args.profile_id)
        baseline = _load_exact(args.baseline_evidence, FastbootBaselineEvidence)
        capture = _load_exact(args.capture_evidence, FastbootCaptureBundleEvidence)
        provenance = _load_exact(args.stock_provenance, StockBootProvenance)
        bundle = bind_physical_baseline_to_stock(profile, baseline, capture, provenance)
        digest = write_physical_baseline_bundle(bundle, args.out)
    except (
        StockBaselineIngressError,
        ProfileError,
        PhysicalBaselineBundleError,
        OSError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps({
        "profile_id": bundle.profile_id,
        "device_serial": bundle.device_serial,
        "firmware_build": bundle.firmware_build,
        "firmware_fingerprint": bundle.firmware_fingerprint,
        "stock_ota_sha256": bundle.stock_ota_sha256,
        "stock_boot_sha256": bundle.stock_boot_sha256,
        "physical_baseline_bundle_sha256": digest,
        "ready_for_candidate_instantiation": True,
        "phone_queried": False,
        "phone_storage_written": False,
        "temporary_boot_authorized": False,
        "hardware_verified": False,
        "beta_gate_credit": False,
    }, sort_keys=True))
    return 0
