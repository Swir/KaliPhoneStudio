#!/usr/bin/env python3
"""Execute one exact temporary Fastboot boot after explicit confirmation and revalidation."""
from __future__ import annotations

import argparse
from dataclasses import fields
import json
from pathlib import Path
from typing import Any, TypeVar

from kaliphonestudio.fastboot_baseline import FastbootBaselineEvidence
from kaliphonestudio.fastboot_capture_bundle import FastbootCaptureBundleEvidence
from kaliphonestudio.fastboot_tool import FastbootToolEvidence
from kaliphonestudio.physical_candidate_gate import PhysicalCandidateGateEvidence
from kaliphonestudio.profiles import get_profile
from kaliphonestudio.temporary_boot_execution import (
    TemporaryBootExecutionError,
    execute_temporary_boot_once,
    write_temporary_boot_execution,
    write_temporary_boot_runtime_probe,
)
from kaliphonestudio.temporary_boot_offer import (
    TemporaryBootOfferError,
    authorize_temporary_boot_offer,
    prepare_temporary_boot_offer,
)

MAX_EVIDENCE_BYTES = 2 * 1024 * 1024
T = TypeVar("T")


class ExecutionInputError(ValueError):
    pass


def _load_typed(cls: type[T], path: Path, label: str) -> T:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ExecutionInputError(f"{label} must be a regular non-symlink JSON file")
    before = path.stat()
    if before.st_size <= 0 or before.st_size > MAX_EVIDENCE_BYTES:
        raise ExecutionInputError(f"{label} size is outside the evidence safety bound")
    raw = path.read_bytes()
    after = path.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise ExecutionInputError(f"{label} changed while being loaded")
    try:
        data: Any = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExecutionInputError(f"{label} is not strict UTF-8 JSON") from exc
    if not isinstance(data, dict):
        raise ExecutionInputError(f"{label} must contain one JSON object")
    expected = {field.name for field in fields(cls)}
    if set(data) != expected:
        raise ExecutionInputError(f"{label} field set does not match the typed schema")
    try:
        return cls(**data)
    except TypeError as exc:
        raise ExecutionInputError(f"{label} cannot be materialized as typed evidence") from exc


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Perform one serial-bound Fastboot temporary boot only after exact evidence/file "
            "revalidation, a fresh read-only device probe and explicit profile confirmation. "
            "No persistent write verb is available."
        )
    )
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--devices-root", type=Path, default=Path("devices"))
    parser.add_argument("--physical-candidate-gate", type=Path, required=True)
    parser.add_argument("--capture-bundle", type=Path, required=True)
    parser.add_argument("--baseline-evidence", type=Path, required=True)
    parser.add_argument("--fastboot-tool-evidence", type=Path, required=True)
    parser.add_argument("--fastboot-executable", type=Path, required=True)
    parser.add_argument("--boot-image", type=Path, required=True)
    parser.add_argument("--confirmation", required=True)
    parser.add_argument(
        "--execute-temporary-boot",
        action="store_true",
        help="Required opt-in. Without this flag the script refuses to invoke Fastboot boot.",
    )
    parser.add_argument("--probe-out", type=Path, required=True)
    parser.add_argument("--execution-out", type=Path, required=True)
    parser.add_argument("--probe-timeout", type=int, default=30)
    parser.add_argument("--boot-timeout", type=int, default=120)
    args = parser.parse_args()

    if not args.execute_temporary_boot:
        parser.error("refusing execution without explicit --execute-temporary-boot opt-in")

    try:
        profile = get_profile(args.devices_root, args.profile_id)
        gate = _load_typed(PhysicalCandidateGateEvidence, args.physical_candidate_gate, "physical candidate gate")
        capture = _load_typed(FastbootCaptureBundleEvidence, args.capture_bundle, "Fastboot capture bundle")
        baseline = _load_typed(FastbootBaselineEvidence, args.baseline_evidence, "Fastboot baseline evidence")
        tool = _load_typed(FastbootToolEvidence, args.fastboot_tool_evidence, "Fastboot tool evidence")
        offer = prepare_temporary_boot_offer(
            profile,
            gate,
            capture,
            tool,
            fastboot_executable=args.fastboot_executable,
            boot_image=args.boot_image,
        )
        authorization = authorize_temporary_boot_offer(offer, profile, args.confirmation)
        probe, execution = execute_temporary_boot_once(
            profile,
            offer,
            authorization,
            gate,
            capture,
            tool,
            baseline,
            probe_timeout_seconds=args.probe_timeout,
            boot_timeout_seconds=args.boot_timeout,
        )
        probe_digest = write_temporary_boot_runtime_probe(probe, args.probe_out)
        execution_digest = write_temporary_boot_execution(execution, args.execution_out)
    except (ExecutionInputError, TemporaryBootOfferError, TemporaryBootExecutionError, ValueError) as exc:
        parser.error(str(exc))

    print(f"runtime probe sha256={probe_digest}")
    print(f"temporary boot execution sha256={execution_digest}")
    print(f"returncode={execution.returncode}")
    print(f"temporary_boot_command_succeeded={str(execution.temporary_boot_command_succeeded).lower()}")
    print("persistent_write=false")
    print("phone_storage_written=false")
    print("kali_userspace_verified=false")
    print("hardware/Beta credit=false")
    if not execution.temporary_boot_command_succeeded:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
