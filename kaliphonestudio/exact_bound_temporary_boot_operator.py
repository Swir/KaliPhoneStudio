"""Shared CLI surface for exact-bound temporary-boot preparation/execution.

The older physical-candidate module still owns candidate-gate construction and common
strict JSON/output helpers.  This module owns the two temporary-boot commands so the
packaged CLI cannot prepare or execute a physical boot without a schema-v1 exact
stock/candidate boot identity binding.  The execution command preserves the stronger
rule that the explicit execution opt-in is checked before evidence loading or device
I/O.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .fastboot_baseline import FastbootBaselineEvidence
from .fastboot_capture_bundle import FastbootCaptureBundleEvidence
from .fastboot_tool import FastbootToolEvidence
from .physical_boot_identity_binding import PhysicalBootIdentityBindingEvidence
from .physical_candidate_gate import PhysicalCandidateGateEvidence
from .physical_candidate_operator import (
    PhysicalCandidateOperatorError,
    _load_typed,
    _preflight_execution_outputs,
    _require_fresh_output,
)
from .profiles import get_profile
from .temporary_boot_execution import (
    TemporaryBootExecutionError,
    execute_temporary_boot_once,
    write_temporary_boot_execution,
    write_temporary_boot_runtime_probe,
)
from .temporary_boot_offer import (
    TemporaryBootOfferError,
    authorize_temporary_boot_offer,
    prepare_temporary_boot_offer,
    write_temporary_boot_offer,
)


def _require_binding_argument(parser: argparse.ArgumentParser, value: Path | None) -> Path:
    if value is None:
        parser.error(
            "refusing temporary boot flow without --physical-boot-identity-binding; "
            "first bind exact stock/candidate boot bytes, components, AVB layout and DTBO"
        )
    return value


def prepare_temporary_boot_offer_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="prepare-temporary-boot-offer",
        description=(
            "Offline: prepare the exact serial-bound Fastboot temporary-boot argv from "
            "reviewed evidence plus the exact stock/candidate boot-identity binding. "
            "This command performs no Fastboot operation and does not authorize execution."
        ),
    )
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--devices-root", type=Path, default=Path("devices"))
    parser.add_argument("--physical-candidate-gate", type=Path, required=True)
    parser.add_argument(
        "--physical-boot-identity-binding",
        type=Path,
        help=(
            "Required schema-v1 exact-byte binding from bind_physical_boot_identity.py; "
            "kept non-required at argparse level so packaged fail-closed diagnostics remain stable."
        ),
    )
    parser.add_argument("--capture-bundle", type=Path, required=True)
    parser.add_argument("--fastboot-tool-evidence", type=Path, required=True)
    parser.add_argument("--fastboot-executable", type=Path, required=True)
    parser.add_argument("--boot-image", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)
    binding_path = _require_binding_argument(parser, args.physical_boot_identity_binding)

    try:
        _require_fresh_output(args.out, "temporary-boot offer evidence")
        profile = get_profile(args.devices_root, args.profile_id)
        gate = _load_typed(
            PhysicalCandidateGateEvidence,
            args.physical_candidate_gate,
            "physical candidate gate",
        )
        binding = _load_typed(
            PhysicalBootIdentityBindingEvidence,
            binding_path,
            "physical boot identity binding",
        )
        capture = _load_typed(
            FastbootCaptureBundleEvidence,
            args.capture_bundle,
            "Fastboot capture bundle",
        )
        tool = _load_typed(
            FastbootToolEvidence,
            args.fastboot_tool_evidence,
            "Fastboot tool evidence",
        )
        offer = prepare_temporary_boot_offer(
            profile,
            gate,
            capture,
            tool,
            boot_identity_binding=binding,
            fastboot_executable=args.fastboot_executable,
            boot_image=args.boot_image,
        )
        digest = write_temporary_boot_offer(offer.evidence, args.out)
    except (
        PhysicalCandidateOperatorError,
        TemporaryBootOfferError,
        ValueError,
        OSError,
    ) as exc:
        parser.error(str(exc))

    print(offer.evidence.canonical_json(), end="")
    print(f"temporary boot offer sha256={digest}")
    print(f"physical boot identity binding sha256={offer.evidence.physical_boot_identity_binding_sha256}")
    print("argv preview (NOT EXECUTED):")
    print(json.dumps(list(offer.argv), ensure_ascii=False))
    print("persistent_write=false")
    print("temporary_boot_executed=false")
    print("phone_storage_written=false")
    print("hardware/Beta credit=false")
    return 0


def execute_temporary_boot_once_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="execute-temporary-boot-once",
        description=(
            "Perform one serial-bound Fastboot temporary boot only after exact boot-identity "
            "binding/evidence/file revalidation, a fresh read-only device probe, the "
            "profile-specific confirmation text and explicit --execute-temporary-boot opt-in. "
            "No persistent write verb is available."
        ),
    )
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--devices-root", type=Path, default=Path("devices"))
    parser.add_argument("--physical-candidate-gate", type=Path, required=True)
    parser.add_argument(
        "--physical-boot-identity-binding",
        type=Path,
        help="Required exact-byte stock/candidate boot identity binding.",
    )
    parser.add_argument("--capture-bundle", type=Path, required=True)
    parser.add_argument("--baseline-evidence", type=Path, required=True)
    parser.add_argument("--fastboot-tool-evidence", type=Path, required=True)
    parser.add_argument("--fastboot-executable", type=Path, required=True)
    parser.add_argument("--boot-image", type=Path, required=True)
    parser.add_argument("--confirmation", required=True)
    parser.add_argument(
        "--execute-temporary-boot",
        action="store_true",
        help=(
            "Required opt-in. Without this flag KaliPhoneStudio refuses before evidence "
            "loading, exact-binding validation, Fastboot probing or command execution."
        ),
    )
    parser.add_argument("--probe-out", type=Path, required=True)
    parser.add_argument("--execution-out", type=Path, required=True)
    parser.add_argument("--probe-timeout", type=int, default=30)
    parser.add_argument("--boot-timeout", type=int, default=120)
    args = parser.parse_args(list(argv) if argv is not None else None)

    # Keep this *before* the binding requirement and every evidence read so a missing
    # opt-in is always the first hard stop on the one command that may invoke Fastboot.
    if not args.execute_temporary_boot:
        parser.error(
            "refusing execution without explicit --execute-temporary-boot opt-in"
        )
    binding_path = _require_binding_argument(parser, args.physical_boot_identity_binding)

    try:
        _preflight_execution_outputs(args.probe_out, args.execution_out)
        profile = get_profile(args.devices_root, args.profile_id)
        gate = _load_typed(
            PhysicalCandidateGateEvidence,
            args.physical_candidate_gate,
            "physical candidate gate",
        )
        binding = _load_typed(
            PhysicalBootIdentityBindingEvidence,
            binding_path,
            "physical boot identity binding",
        )
        capture = _load_typed(
            FastbootCaptureBundleEvidence,
            args.capture_bundle,
            "Fastboot capture bundle",
        )
        baseline = _load_typed(
            FastbootBaselineEvidence,
            args.baseline_evidence,
            "Fastboot baseline evidence",
        )
        tool = _load_typed(
            FastbootToolEvidence,
            args.fastboot_tool_evidence,
            "Fastboot tool evidence",
        )
        offer = prepare_temporary_boot_offer(
            profile,
            gate,
            capture,
            tool,
            boot_identity_binding=binding,
            fastboot_executable=args.fastboot_executable,
            boot_image=args.boot_image,
        )
        authorization = authorize_temporary_boot_offer(
            offer,
            profile,
            args.confirmation,
        )
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
        execution_digest = write_temporary_boot_execution(
            execution,
            args.execution_out,
        )
    except (
        PhysicalCandidateOperatorError,
        TemporaryBootOfferError,
        TemporaryBootExecutionError,
        ValueError,
        OSError,
    ) as exc:
        parser.error(str(exc))

    print(f"physical boot identity binding sha256={offer.evidence.physical_boot_identity_binding_sha256}")
    print(f"runtime probe sha256={probe_digest}")
    print(f"temporary boot execution sha256={execution_digest}")
    print(f"returncode={execution.returncode}")
    print(
        "temporary_boot_command_succeeded="
        f"{str(execution.temporary_boot_command_succeeded).lower()}"
    )
    print("persistent_write=false")
    print("phone_storage_written=false")
    print("kali_userspace_verified=false")
    print("hardware/Beta credit=false")
    return 0 if execution.temporary_boot_command_succeeded else 1
