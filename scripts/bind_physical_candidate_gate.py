#!/usr/bin/env python3
"""Create the host-only physical-candidate preflight gate.

The command performs no ADB/Fastboot operation.  It only cross-binds already
verified evidence and emits immutable JSON that can later make a temporary-boot
offer eligible for explicit user action.
"""
from __future__ import annotations

import argparse
from dataclasses import fields
import json
from pathlib import Path
from typing import Any, TypeVar

from kaliphonestudio.boot_authorization import TemporaryBootAuthorization
from kaliphonestudio.boot_builder import BootBuildPlan, BuildInput
from kaliphonestudio.candidate import FirstBootCandidateManifest
from kaliphonestudio.candidate_authority_bundle import FirstBootAuthorityBundleEvidence
from kaliphonestudio.physical_baseline_bundle import PhysicalBaselineBundleEvidence
from kaliphonestudio.physical_candidate_gate import (
    PhysicalCandidateGateError,
    bind_physical_candidate_gate,
    write_physical_candidate_gate,
)
from kaliphonestudio.profiles import get_profile

MAX_EVIDENCE_BYTES = 2 * 1024 * 1024
T = TypeVar("T")


class EvidenceLoadError(ValueError):
    pass


def _load_json(path: Path, label: str) -> dict[str, Any]:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise EvidenceLoadError(f"{label} must be a regular non-symlink JSON file")
    before = path.stat()
    if before.st_size <= 0 or before.st_size > MAX_EVIDENCE_BYTES:
        raise EvidenceLoadError(f"{label} size is outside the safe evidence limit")
    raw = path.read_bytes()
    after = path.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise EvidenceLoadError(f"{label} changed while being loaded")
    try:
        data = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceLoadError(f"{label} is not strict UTF-8 JSON") from exc
    if not isinstance(data, dict):
        raise EvidenceLoadError(f"{label} must contain one JSON object")
    return data


def _typed(cls: type[T], path: Path, label: str) -> T:
    data = _load_json(path, label)
    allowed = {field.name for field in fields(cls)}
    if set(data) != allowed:
        missing = sorted(allowed - set(data))
        extra = sorted(set(data) - allowed)
        detail = []
        if missing:
            detail.append(f"missing={','.join(missing)}")
        if extra:
            detail.append(f"extra={','.join(extra)}")
        raise EvidenceLoadError(f"{label} field set does not match schema ({'; '.join(detail)})")
    try:
        return cls(**data)
    except TypeError as exc:
        raise EvidenceLoadError(f"{label} cannot be materialized as typed evidence") from exc


def _boot_plan(path: Path) -> BootBuildPlan:
    data = _load_json(path, "boot build plan")
    allowed = {field.name for field in fields(BootBuildPlan)}
    if set(data) != allowed:
        raise EvidenceLoadError("boot build plan field set does not match schema")
    inputs = data.get("inputs")
    cmdline = data.get("kernel_cmdline")
    if not isinstance(inputs, list) or not isinstance(cmdline, list):
        raise EvidenceLoadError("boot build plan inputs/kernel_cmdline must be arrays")
    try:
        typed_inputs = tuple(BuildInput(**item) for item in inputs if isinstance(item, dict))
    except TypeError as exc:
        raise EvidenceLoadError("boot build plan contains malformed input evidence") from exc
    if len(typed_inputs) != len(inputs):
        raise EvidenceLoadError("boot build plan contains non-object input evidence")
    try:
        return BootBuildPlan(
            schema_version=data["schema_version"],
            profile_id=data["profile_id"],
            stock_boot_sha256=data["stock_boot_sha256"],
            stock_ota_sha256=data["stock_ota_sha256"],
            header_version=data["header_version"],
            page_size=data["page_size"],
            ramdisk_compression=data["ramdisk_compression"],
            kernel_cmdline=tuple(cmdline),
            inputs=typed_inputs,
        )
    except (KeyError, TypeError) as exc:
        raise EvidenceLoadError("boot build plan cannot be materialized as typed evidence") from exc


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Cross-bind an exact physical baseline, schema-v8 candidate, reviewed authority "
            "bundle, temporary-boot authorization and boot plan. This command never boots or "
            "writes the phone."
        )
    )
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--devices-root", type=Path, default=Path("devices"))
    parser.add_argument("--physical-baseline", type=Path, required=True)
    parser.add_argument("--first-boot-manifest", type=Path, required=True)
    parser.add_argument("--authority-bundle", type=Path, required=True)
    parser.add_argument("--boot-authorization", type=Path, required=True)
    parser.add_argument("--boot-plan", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    try:
        profile = get_profile(args.devices_root, args.profile_id)
        physical = _typed(
            PhysicalBaselineBundleEvidence,
            args.physical_baseline,
            "physical baseline bundle",
        )
        manifest = _typed(
            FirstBootCandidateManifest,
            args.first_boot_manifest,
            "first-boot manifest",
        )
        authorities = _typed(
            FirstBootAuthorityBundleEvidence,
            args.authority_bundle,
            "first-boot authority bundle",
        )
        boot = _typed(
            TemporaryBootAuthorization,
            args.boot_authorization,
            "temporary-boot authorization",
        )
        plan = _boot_plan(args.boot_plan)
        evidence = bind_physical_candidate_gate(
            profile,
            physical,
            manifest,
            authorities,
            boot,
            plan,
        )
        digest = write_physical_candidate_gate(evidence, args.out)
    except (EvidenceLoadError, PhysicalCandidateGateError, ValueError) as exc:
        parser.error(str(exc))

    print(evidence.canonical_json(), end="")
    print(f"physical candidate gate sha256={digest}")
    print("ready_for_temporary_boot_offer=true")
    print("temporary_boot_executed=false")
    print("phone_storage_written=false")
    print("hardware/Beta credit=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
