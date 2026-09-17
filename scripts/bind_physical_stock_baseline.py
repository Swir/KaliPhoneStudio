#!/usr/bin/env python3
"""Bind captured physical Fastboot evidence to exact OTA/stock-boot provenance.

This command is offline: it performs no ADB/Fastboot calls and no phone I/O. The
result is only an ingress record for later first-boot candidate preparation; it
does not authorize temporary boot and grants no hardware/Beta credit.
"""
from __future__ import annotations

import argparse
from dataclasses import fields
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kaliphonestudio.fastboot_baseline import FastbootBaselineEvidence
from kaliphonestudio.fastboot_capture_bundle import FastbootCaptureBundleEvidence
from kaliphonestudio.physical_baseline_bundle import (
    PhysicalBaselineBundleError,
    bind_physical_baseline_to_stock,
    write_physical_baseline_bundle,
)
from kaliphonestudio.profiles import get_profile
from kaliphonestudio.provenance import StockBootProvenance


def _load_exact(path: Path, cls):
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise SystemExit(f"evidence file must be a regular non-symlink file: {candidate}")
    try:
        data = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"cannot parse evidence JSON: {candidate}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"evidence JSON must be an object: {candidate}")
    expected = {field.name for field in fields(cls)}
    if set(data) != expected:
        missing = sorted(expected - set(data))
        extra = sorted(set(data) - expected)
        raise SystemExit(f"evidence schema mismatch for {candidate}: missing={missing} extra={extra}")
    try:
        return cls(**data)
    except TypeError as exc:
        raise SystemExit(f"evidence fields are invalid for {candidate}") from exc


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--profile-id", required=True)
    p.add_argument("--devices-root", type=Path, default=ROOT / "devices")
    p.add_argument("--baseline-evidence", type=Path, required=True)
    p.add_argument("--capture-evidence", type=Path, required=True)
    p.add_argument("--stock-provenance", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    return p


def main() -> int:
    args = parser().parse_args()
    if args.out.exists() or args.out.is_symlink():
        raise SystemExit(f"refusing to overwrite output: {args.out}")
    profile = get_profile(args.devices_root, args.profile_id)
    baseline = _load_exact(args.baseline_evidence, FastbootBaselineEvidence)
    capture = _load_exact(args.capture_evidence, FastbootCaptureBundleEvidence)
    provenance = _load_exact(args.stock_provenance, StockBootProvenance)
    try:
        bundle = bind_physical_baseline_to_stock(profile, baseline, capture, provenance)
        digest = write_physical_baseline_bundle(bundle, args.out)
    except PhysicalBaselineBundleError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps({
        "profile_id": bundle.profile_id,
        "device_serial": bundle.device_serial,
        "firmware_build": bundle.firmware_build,
        "firmware_fingerprint": bundle.firmware_fingerprint,
        "stock_ota_sha256": bundle.stock_ota_sha256,
        "stock_boot_sha256": bundle.stock_boot_sha256,
        "physical_baseline_bundle_sha256": digest,
        "ready_for_candidate_instantiation": True,
        "temporary_boot_authorized": False,
        "hardware_verified": False,
        "beta_gate_credit": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
