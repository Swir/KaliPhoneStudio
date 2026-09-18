#!/usr/bin/env python3
"""Create exact stock/candidate boot identity evidence without device I/O."""
from __future__ import annotations

import argparse
from dataclasses import fields
import json
from pathlib import Path
import sys
from typing import TypeVar

from kaliphonestudio.boot_builder import BootBuildPlan, BuildInput
from kaliphonestudio.physical_baseline_bundle import PhysicalBaselineBundleEvidence
from kaliphonestudio.physical_boot_identity_binding import (
    PhysicalBootIdentityBindingError,
    bind_physical_boot_identity,
    write_physical_boot_identity_binding,
)
from kaliphonestudio.physical_candidate_gate import PhysicalCandidateGateEvidence
from kaliphonestudio.profiles import ProfileError, get_profile
from kaliphonestudio.provenance import StockBootProvenance


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEVICES_ROOT = ROOT / "devices"
T = TypeVar("T")


class PhysicalBootIdentityCliError(ValueError):
    pass


def _regular_non_symlink(path: Path, label: str) -> Path:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise PhysicalBootIdentityCliError(f"{label} must be a regular non-symlink file: {candidate}")
    return candidate


def _stable_json(path: Path, label: str) -> dict[str, object]:
    candidate = _regular_non_symlink(path, label)
    before = candidate.stat()
    try:
        raw = candidate.read_bytes()
        data = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalBootIdentityCliError(f"cannot parse {label}: {candidate}") from exc
    after = candidate.stat()
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or before.st_ino != after.st_ino
    ):
        raise PhysicalBootIdentityCliError(f"{label} changed while being read: {candidate}")
    if not isinstance(data, dict):
        raise PhysicalBootIdentityCliError(f"{label} must contain a JSON object: {candidate}")
    return data


def _load_exact(path: Path, cls: type[T], label: str) -> T:
    data = _stable_json(path, label)
    expected = {field.name for field in fields(cls)}
    actual = set(data)
    if actual != expected:
        raise PhysicalBootIdentityCliError(
            f"{label} schema mismatch: missing={sorted(expected - actual)} extra={sorted(actual - expected)}"
        )
    try:
        return cls(**data)
    except (TypeError, ValueError) as exc:
        raise PhysicalBootIdentityCliError(f"{label} contains invalid typed fields") from exc


def _load_boot_plan(path: Path) -> BootBuildPlan:
    data = _stable_json(path, "boot plan")
    expected = {field.name for field in fields(BootBuildPlan)}
    if set(data) != expected:
        raise PhysicalBootIdentityCliError(
            f"boot plan schema mismatch: missing={sorted(expected - set(data))} extra={sorted(set(data) - expected)}"
        )
    raw_inputs = data.get("inputs")
    if not isinstance(raw_inputs, list):
        raise PhysicalBootIdentityCliError("boot plan inputs must be a JSON array")
    input_fields = {field.name for field in fields(BuildInput)}
    inputs: list[BuildInput] = []
    for index, raw in enumerate(raw_inputs):
        if not isinstance(raw, dict) or set(raw) != input_fields:
            raise PhysicalBootIdentityCliError(f"boot plan input {index} has an invalid schema")
        try:
            inputs.append(BuildInput(**raw))
        except (TypeError, ValueError) as exc:
            raise PhysicalBootIdentityCliError(f"boot plan input {index} has invalid fields") from exc
    cmdline = data.get("kernel_cmdline")
    if not isinstance(cmdline, list) or not all(isinstance(item, str) for item in cmdline):
        raise PhysicalBootIdentityCliError("boot plan kernel_cmdline must be an array of strings")
    normalized = dict(data)
    normalized["inputs"] = tuple(inputs)
    normalized["kernel_cmdline"] = tuple(cmdline)
    try:
        return BootBuildPlan(**normalized)
    except (TypeError, ValueError) as exc:
        raise PhysicalBootIdentityCliError("boot plan contains invalid typed fields") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Offline fail-closed binding of exact stock/candidate boot image bytes, "
            "per-component identities, optional AVB layout and external DTBO to one "
            "reviewed physical-candidate chain. No ADB/Fastboot command is executed."
        )
    )
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--devices-root", type=Path, default=DEFAULT_DEVICES_ROOT)
    parser.add_argument("--physical-baseline", type=Path, required=True)
    parser.add_argument("--candidate-gate", type=Path, required=True)
    parser.add_argument("--stock-provenance", type=Path, required=True)
    parser.add_argument("--boot-plan", type=Path, required=True)
    parser.add_argument("--stock-boot", type=Path, required=True)
    parser.add_argument("--candidate-boot", type=Path, required=True)
    parser.add_argument(
        "--candidate-dtbo",
        type=Path,
        help="Exact external candidate DTBO; required by profiles whose boot contract uses separate_dtbo.",
    )
    parser.add_argument("--out", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.out.exists() or args.out.is_symlink():
        print(f"refusing to overwrite output: {args.out}", file=sys.stderr)
        return 2
    try:
        profile = get_profile(args.devices_root, args.profile_id)
        physical = _load_exact(
            args.physical_baseline,
            PhysicalBaselineBundleEvidence,
            "physical baseline bundle",
        )
        gate = _load_exact(
            args.candidate_gate,
            PhysicalCandidateGateEvidence,
            "physical candidate gate",
        )
        provenance = _load_exact(
            args.stock_provenance,
            StockBootProvenance,
            "stock provenance",
        )
        plan = _load_boot_plan(args.boot_plan)
        evidence = bind_physical_boot_identity(
            profile,
            physical,
            gate,
            provenance,
            plan,
            stock_boot=args.stock_boot,
            candidate_boot=args.candidate_boot,
            candidate_dtbo=args.candidate_dtbo,
        )
        digest = write_physical_boot_identity_binding(evidence, args.out)
    except (
        PhysicalBootIdentityCliError,
        PhysicalBootIdentityBindingError,
        ProfileError,
        OSError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps({
        "profile_id": evidence.profile_id,
        "device_serial": evidence.device_serial,
        "physical_boot_identity_binding_sha256": digest,
        "stock_boot_sha256": evidence.stock_boot_sha256,
        "candidate_boot_sha256": evidence.candidate_boot_sha256,
        "stock_avb_footer_present": evidence.stock_avb_footer_present,
        "candidate_avb_footer_present": evidence.candidate_avb_footer_present,
        "component_identity_bound": evidence.component_identity_bound,
        "avb_layout_bound": evidence.avb_layout_bound,
        "temporary_boot_executed": evidence.temporary_boot_executed,
        "phone_storage_written": evidence.phone_storage_written,
        "hardware_verified": evidence.hardware_verified,
        "beta_gate_credit": evidence.beta_gate_credit,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
