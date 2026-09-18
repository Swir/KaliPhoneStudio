"""Shared operator CLI for the reviewed physical candidate -> temporary-boot chain.

The module keeps candidate binding and temporary-boot preparation available from the
same packaged CLI used for baseline capture/stock provenance. Only the final
``execute-temporary-boot-once`` command performs device I/O, and it remains behind
both the profile-specific confirmation string and an explicit execution opt-in.
No persistent Fastboot write verb is exposed.
"""
from __future__ import annotations

import argparse
from dataclasses import fields
import json
from pathlib import Path
import tempfile
from typing import Any, Sequence, TypeVar

from .boot_authorization import TemporaryBootAuthorization
from .boot_builder import BootBuildPlan, BuildInput
from .candidate import FirstBootCandidateManifest
from .candidate_authority_bundle import FirstBootAuthorityBundleEvidence
from .fastboot_baseline import FastbootBaselineEvidence
from .fastboot_capture_bundle import FastbootCaptureBundleEvidence
from .fastboot_tool import FastbootToolEvidence
from .physical_baseline_bundle import PhysicalBaselineBundleEvidence
from .physical_boot_identity_binding import PhysicalBootIdentityBindingEvidence
from .physical_candidate_gate import (
    PhysicalCandidateGateError,
    PhysicalCandidateGateEvidence,
    bind_physical_candidate_gate,
    write_physical_candidate_gate,
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

MAX_EVIDENCE_BYTES = 2 * 1024 * 1024
T = TypeVar("T")


class PhysicalCandidateOperatorError(ValueError):
    """Raised when operator-supplied host evidence fails closed before device I/O."""


def _stable_json_object(path: Path, label: str) -> dict[str, Any]:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise PhysicalCandidateOperatorError(
            f"{label} must be a regular non-symlink JSON file"
        )
    before = candidate.stat()
    if before.st_size <= 0 or before.st_size > MAX_EVIDENCE_BYTES:
        raise PhysicalCandidateOperatorError(
            f"{label} size is outside the evidence safety bound"
        )
    raw = candidate.read_bytes()
    after = candidate.stat()
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if identity_before != identity_after:
        raise PhysicalCandidateOperatorError(f"{label} changed while being loaded")
    try:
        data = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalCandidateOperatorError(
            f"{label} is not strict UTF-8 JSON"
        ) from exc
    if not isinstance(data, dict):
        raise PhysicalCandidateOperatorError(f"{label} must contain one JSON object")
    return data


def _load_typed(cls: type[T], path: Path, label: str) -> T:
    data = _stable_json_object(path, label)
    expected = {field.name for field in fields(cls)}
    if set(data) != expected:
        missing = sorted(expected - set(data))
        extra = sorted(set(data) - expected)
        details: list[str] = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if extra:
            details.append("extra=" + ",".join(extra))
        detail = "; ".join(details) if details else "field mismatch"
        raise PhysicalCandidateOperatorError(
            f"{label} field set does not match the typed schema ({detail})"
        )
    try:
        return cls(**data)
    except TypeError as exc:
        raise PhysicalCandidateOperatorError(
            f"{label} cannot be materialized as typed evidence"
        ) from exc


def _load_boot_plan(path: Path) -> BootBuildPlan:
    data = _stable_json_object(path, "boot build plan")
    expected = {field.name for field in fields(BootBuildPlan)}
    if set(data) != expected:
        raise PhysicalCandidateOperatorError(
            "boot build plan field set does not match schema"
        )
    inputs = data.get("inputs")
    cmdline = data.get("kernel_cmdline")
    if not isinstance(inputs, list) or not isinstance(cmdline, list):
        raise PhysicalCandidateOperatorError(
            "boot build plan inputs/kernel_cmdline must be arrays"
        )
    typed_inputs: list[BuildInput] = []
    for item in inputs:
        if not isinstance(item, dict):
            raise PhysicalCandidateOperatorError(
                "boot build plan contains non-object input evidence"
            )
        try:
            typed_inputs.append(BuildInput(**item))
        except TypeError as exc:
            raise PhysicalCandidateOperatorError(
                "boot build plan contains malformed input evidence"
            ) from exc
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
            inputs=tuple(typed_inputs),
        )
    except (KeyError, TypeError) as exc:
        raise PhysicalCandidateOperatorError(
            "boot build plan cannot be materialized as typed evidence"
        ) from exc


def _require_fresh_output(path: Path, label: str) -> None:
    candidate = Path(path)
    if candidate.exists() or candidate.is_symlink():
        raise PhysicalCandidateOperatorError(f"refusing to overwrite {label}: {candidate}")
    temporary = candidate.with_name(candidate.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise PhysicalCandidateOperatorError(
            f"refusing stale {label} temporary path: {temporary}"
        )


def _preflight_execution_outputs(probe_out: Path, execution_out: Path) -> None:
    probe = Path(probe_out)
    execution = Path(execution_out)
    probe_tmp = probe.with_name(probe.name + ".tmp")
    execution_tmp = execution.with_name(execution.name + ".tmp")
    reserved_paths = {
        probe.absolute(),
        probe_tmp.absolute(),
        execution.absolute(),
        execution_tmp.absolute(),
    }
    if len(reserved_paths) != 4:
        raise PhysicalCandidateOperatorError(
            "runtime-probe/execution output and temporary paths must not overlap"
        )
    for path, label in (
        (probe, "temporary-boot runtime probe evidence"),
        (execution, "temporary-boot execution evidence"),
    ):
        _require_fresh_output(path, label)
        parent = path.parent
        parent.mkdir(parents=True, exist_ok=True)
        if parent.is_symlink() or not parent.is_dir():
            raise PhysicalCandidateOperatorError(
                f"{label} parent must be a regular directory"
            )
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=".kps-output-preflight-",
                dir=parent,
                delete=True,
            ) as handle:
                handle.write(b"KPS")
                handle.flush()
        except OSError as exc:
            raise PhysicalCandidateOperatorError(
                f"{label} parent is not writable before physical execution"
            ) from exc


def bind_physical_candidate_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bind-physical-candidate-gate",
        description=(
            "Offline: cross-bind an exact physical stock baseline, schema-v8 candidate, "
            "reviewed authorities, temporary-boot authorization and boot plan. "
            "This command never invokes Fastboot and never writes phone storage."
        ),
    )
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--devices-root", type=Path, default=Path("devices"))
    parser.add_argument("--physical-baseline", type=Path, required=True)
    parser.add_argument("--first-boot-manifest", type=Path, required=True)
    parser.add_argument("--authority-bundle", type=Path, required=True)
    parser.add_argument("--boot-authorization", type=Path, required=True)
    parser.add_argument("--boot-plan", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        _require_fresh_output(args.out, "physical candidate gate evidence")
        profile = get_profile(args.devices_root, args.profile_id)
        physical = _load_typed(
            PhysicalBaselineBundleEvidence,
            args.physical_baseline,
            "physical baseline bundle",
        )
        manifest = _load_typed(
            FirstBootCandidateManifest,
            args.first_boot_manifest,
            "first-boot manifest",
        )
        authorities = _load_typed(
            FirstBootAuthorityBundleEvidence,
            args.authority_bundle,
            "first-boot authority bundle",
        )
        boot = _load_typed(
            TemporaryBootAuthorization,
            args.boot_authorization,
            "temporary-boot authorization",
        )
        plan = _load_boot_plan(args.boot_plan)
        evidence = bind_physical_candidate_gate(
            profile,
            physical,
            manifest,
            authorities,
            boot,
            plan,
        )
        digest = write_physical_candidate_gate(evidence, args.out)
    except (
        PhysicalCandidateOperatorError,
        PhysicalCandidateGateError,
        ValueError,
        OSError,
    ) as exc:
        parser.error(str(exc))

    print(evidence.canonical_json(), end="")
    print(f"physical candidate gate sha256={digest}")
    print("ready_for_temporary_boot_offer=true")
    print("temporary_boot_executed=false")
    print("phone_storage_written=false")
    print("hardware/Beta credit=false")
    return 0


def prepare_temporary_boot_offer_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="prepare-temporary-boot-offer",
        description=(
            "Offline: prepare the exact serial-bound Fastboot temporary-boot argv from "
            "reviewed evidence. This command performs no Fastboot operation and does not "
            "authorize execution."
        ),
    )
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--devices-root", type=Path, default=Path("devices"))
    parser.add_argument("--physical-candidate-gate", type=Path, required=True)
    parser.add_argument("--capture-bundle", type=Path, required=True)
    parser.add_argument("--fastboot-tool-evidence", type=Path, required=True)
    parser.add_argument("--fastboot-executable", type=Path, required=True)
    parser.add_argument("--boot-image", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        _require_fresh_output(args.out, "temporary-boot offer evidence")
        profile = get_profile(args.devices_root, args.profile_id)
        gate = _load_typed(
            PhysicalCandidateGateEvidence,
            args.physical_candidate_gate,
            "physical candidate gate",
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
            "Perform one serial-bound Fastboot temporary boot only after exact evidence/file "
            "revalidation including the exact stock/candidate boot identity binding, a fresh "
            "read-only device probe, the profile-specific confirmation text and explicit "
            "--execute-temporary-boot opt-in. No persistent write verb is available."
        ),
    )
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--devices-root", type=Path, default=Path("devices"))
    parser.add_argument("--physical-candidate-gate", type=Path, required=True)
    parser.add_argument("--boot-identity-binding", type=Path, required=True)
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
            "loading, Fastboot probing or command execution."
        ),
    )
    parser.add_argument("--probe-out", type=Path, required=True)
    parser.add_argument("--execution-out", type=Path, required=True)
    parser.add_argument("--probe-timeout", type=int, default=30)
    parser.add_argument("--boot-timeout", type=int, default=120)
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not args.execute_temporary_boot:
        parser.error(
            "refusing execution without explicit --execute-temporary-boot opt-in"
        )

    try:
        # Validate that evidence can be persisted before any physical command runs.
        # This prevents a successful one-shot boot from being followed by a trivial
        # local overwrite/path failure that would discard its audit record.
        _preflight_execution_outputs(args.probe_out, args.execution_out)
        profile = get_profile(args.devices_root, args.profile_id)
        gate = _load_typed(
            PhysicalCandidateGateEvidence,
            args.physical_candidate_gate,
            "physical candidate gate",
        )
        binding = _load_typed(
            PhysicalBootIdentityBindingEvidence,
            args.boot_identity_binding,
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
            binding,
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
