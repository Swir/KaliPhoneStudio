#!/usr/bin/env python3
"""Build exact offline physical recovery-readiness evidence without device I/O."""
from __future__ import annotations

import argparse
from dataclasses import fields
import json
from pathlib import Path
import sys
from typing import TypeVar

from kaliphonestudio.fastboot_baseline import FastbootBaselineEvidence
from kaliphonestudio.physical_baseline_bundle import PhysicalBaselineBundleEvidence
from kaliphonestudio.physical_boot_identity_binding import PhysicalBootIdentityBindingEvidence
from kaliphonestudio.physical_recovery_readiness import (
    PhysicalRecoveryReadinessError,
    build_physical_recovery_readiness,
    write_physical_recovery_readiness,
)
from kaliphonestudio.profiles import ProfileError, get_profile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEVICES_ROOT = ROOT / "devices"
T = TypeVar("T")


class PhysicalRecoveryReadinessCliError(ValueError):
    pass


def _stable_json(path: Path, label: str) -> dict[str, object]:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise PhysicalRecoveryReadinessCliError(f"{label} must be a regular non-symlink file: {candidate}")
    before = candidate.stat()
    try:
        raw = candidate.read_bytes()
        data = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalRecoveryReadinessCliError(f"cannot parse {label}: {candidate}") from exc
    after = candidate.stat()
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or before.st_ino != after.st_ino
    ):
        raise PhysicalRecoveryReadinessCliError(f"{label} changed while being read: {candidate}")
    if not isinstance(data, dict):
        raise PhysicalRecoveryReadinessCliError(f"{label} must contain a JSON object: {candidate}")
    return data


def _load_exact(path: Path, cls: type[T], label: str) -> T:
    data = _stable_json(path, label)
    expected = {field.name for field in fields(cls)}
    actual = set(data)
    if actual != expected:
        raise PhysicalRecoveryReadinessCliError(
            f"{label} schema mismatch: missing={sorted(expected - actual)} extra={sorted(actual - expected)}"
        )
    try:
        return cls(**data)
    except (TypeError, ValueError) as exc:
        raise PhysicalRecoveryReadinessCliError(f"{label} contains invalid typed fields") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Bind the captured slot context and exact local stock boot recovery material "
            "to one physical baseline and boot-identity chain. This command performs no "
            "ADB/Fastboot operation, changes no slot and authorizes no write."
        )
    )
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--devices-root", type=Path, default=DEFAULT_DEVICES_ROOT)
    parser.add_argument("--fastboot-baseline", type=Path, required=True)
    parser.add_argument("--physical-baseline", type=Path, required=True)
    parser.add_argument("--boot-identity-binding", type=Path, required=True)
    parser.add_argument("--stock-boot", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.out.exists() or args.out.is_symlink():
        print(f"refusing to overwrite output: {args.out}", file=sys.stderr)
        return 2
    try:
        profile = get_profile(args.devices_root, args.profile_id)
        baseline = _load_exact(args.fastboot_baseline, FastbootBaselineEvidence, "Fastboot baseline")
        physical = _load_exact(args.physical_baseline, PhysicalBaselineBundleEvidence, "physical baseline bundle")
        binding = _load_exact(args.boot_identity_binding, PhysicalBootIdentityBindingEvidence, "boot identity binding")
        evidence = build_physical_recovery_readiness(
            profile,
            baseline,
            physical,
            binding,
            stock_boot=args.stock_boot,
        )
        digest = write_physical_recovery_readiness(evidence, args.out)
    except (
        PhysicalRecoveryReadinessCliError,
        PhysicalRecoveryReadinessError,
        ProfileError,
        OSError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps({
        "profile_id": evidence.profile_id,
        "device_serial": evidence.device_serial,
        "physical_recovery_readiness_sha256": digest,
        "captured_active_slot": evidence.captured_active_slot,
        "expected_inactive_slot": evidence.expected_inactive_slot,
        "stock_boot_sha256": evidence.stock_boot_sha256,
        "stock_boot_material_present": evidence.stock_boot_material_present,
        "ready_for_temporary_boot_safety_review": evidence.ready_for_temporary_boot_safety_review,
        "slot_switch_authorized": evidence.slot_switch_authorized,
        "persistent_write_authorized": evidence.persistent_write_authorized,
        "rollback_exercised": evidence.rollback_exercised,
        "recovery_verified": evidence.recovery_verified,
        "hardware_verified": evidence.hardware_verified,
        "beta_gate_credit": evidence.beta_gate_credit,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
