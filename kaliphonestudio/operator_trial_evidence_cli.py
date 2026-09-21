"""Offline rootfs trial-authorization and later-executor planning commands.

These commands are intentionally non-executing. They consume already reviewed
host evidence, create/bind manual authorization records, build an exact plan for
a future interactive executor, re-hash the exact local rootfs artifact, and can
bind a second distinct fresh-device capture into the final non-writing execution
gate. They never talk to a phone, resolve a raw storage path, mount/copy/write
storage, execute a rootfs trial, or grant storage/recovery/hardware/Beta credit.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Sequence

from .rootfs_handoff_trial_authorization import (
    RootfsHandoffTrialAuthorizationError,
    bind_rootfs_handoff_trial_authorization_review,
    prepare_rootfs_handoff_trial_authorization_review_record,
    write_rootfs_handoff_trial_authorization_evidence,
)
from .rootfs_handoff_trial_execution_gate import (
    RootfsHandoffTrialExecutionGateError,
    build_rootfs_handoff_trial_execution_gate,
    write_rootfs_handoff_trial_execution_gate_evidence,
)
from .rootfs_handoff_trial_plan import (
    RootfsHandoffTrialPlanError,
    build_rootfs_handoff_trial_plan,
    write_rootfs_handoff_trial_plan,
)
from .rootfs_handoff_trial_preflight import (
    RootfsHandoffTrialPreflightError,
    build_rootfs_handoff_trial_preflight,
    write_rootfs_handoff_trial_preflight_evidence,
)

TRIAL_EVIDENCE_COMMANDS = (
    "prepare-rootfs-handoff-trial-authorization-review",
    "bind-rootfs-handoff-trial-authorization-review",
    "build-rootfs-handoff-trial-plan",
    "build-rootfs-handoff-trial-preflight",
    "build-rootfs-handoff-trial-execution-gate",
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="KaliPhoneStudio evidence",
        description=(
            "Offline manual rootfs-trial authorization, planning, local-artifact preflight and execution-gate workspace. "
            "No phone I/O, raw path binding, mounting, trial execution, persistent write authorization, "
            "hardware promotion or Beta credit is possible here."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable safety/result summary.")
    sub = parser.add_subparsers(dest="evidence_command", required=True)

    prepare = sub.add_parser(
        "prepare-rootfs-handoff-trial-authorization-review",
        help="Create rejected-by-default trial authorization review record and notes templates.",
        description=(
            "Prepare one rejected-by-default manual review from an accepted target binding and exact fresh revalidation. "
            "The output is review material only and cannot execute or authorize a write."
        ),
    )
    prepare.add_argument("--target-binding", type=Path, required=True)
    prepare.add_argument("--fresh-revalidation", type=Path, required=True)
    prepare.add_argument("--reviewer", required=True)
    prepare.add_argument("--record-out", type=Path, required=True)
    prepare.add_argument("--notes-out", type=Path, required=True)

    bind = sub.add_parser(
        "bind-rootfs-handoff-trial-authorization-review",
        help="Bind an independently edited trial authorization review to the exact evidence chain.",
        description=(
            "Bind one exact manual review to an accepted target binding and fresh revalidation. Acceptance only opens "
            "a later interactive execution boundary and still performs no trial/write/device I/O."
        ),
    )
    bind.add_argument("--target-binding", type=Path, required=True)
    bind.add_argument("--fresh-revalidation", type=Path, required=True)
    bind.add_argument("--review-record", type=Path, required=True)
    bind.add_argument("--review-notes", type=Path, required=True)
    bind.add_argument("--out", type=Path, required=True)

    plan = sub.add_parser(
        "build-rootfs-handoff-trial-plan",
        help="Bind accepted trial authorization to an exact non-executing plan for a later interactive executor.",
        description=(
            "Build a deterministic execution plan from one accepted authorization plus the exact target binding and "
            "fresh revalidation. The plan requires live rechecks and explicit operator confirmation later; it performs "
            "no device I/O and contains no raw device path or mount target."
        ),
    )
    plan.add_argument("--trial-authorization", type=Path, required=True)
    plan.add_argument("--target-binding", type=Path, required=True)
    plan.add_argument("--fresh-revalidation", type=Path, required=True)
    plan.add_argument("--out", type=Path, required=True)

    preflight = sub.add_parser(
        "build-rootfs-handoff-trial-preflight",
        help="Re-hash the exact local rootfs artifact against one accepted non-executing trial plan.",
        description=(
            "Build deterministic local-artifact preflight evidence from one exact trial plan and local rootfs file. "
            "This re-hashes exact rootfs bytes only; live device/firmware/target/recovery rechecks and explicit operator "
            "confirmation remain mandatory at a later interactive executor. No device I/O, raw path, mount or write is performed."
        ),
    )
    preflight.add_argument("--trial-plan", type=Path, required=True)
    preflight.add_argument("--rootfs-artifact", type=Path, required=True)
    preflight.add_argument("--out", type=Path, required=True)

    execution_gate = sub.add_parser(
        "build-rootfs-handoff-trial-execution-gate",
        help="Bind a second distinct fresh storage revalidation immediately before a later interactive writer.",
        description=(
            "Build the final non-writing execution evidence gate from the exact trial plan/preflight, the fresh "
            "revalidation used for manual authorization and a second distinct execution-time fresh revalidation. "
            "Passing this gate still resolves no raw path, performs no phone I/O, authorizes no write and requires "
            "explicit operator confirmation plus a separate interactive writer."
        ),
    )
    execution_gate.add_argument("--trial-plan", type=Path, required=True)
    execution_gate.add_argument("--trial-preflight", type=Path, required=True)
    execution_gate.add_argument("--authorized-fresh-revalidation", type=Path, required=True)
    execution_gate.add_argument("--execution-fresh-revalidation", type=Path, required=True)
    execution_gate.add_argument("--out", type=Path, required=True)
    return parser


def _write_pair_exclusive(record_path: Path, record_text: str, notes_path: Path, notes_text: str) -> tuple[str, str]:
    record_path = Path(record_path)
    notes_path = Path(notes_path)
    if record_path == notes_path:
        raise RootfsHandoffTrialAuthorizationError("review record and notes outputs must be different files")
    for destination in (record_path, notes_path):
        if destination.exists() or destination.is_symlink():
            raise RootfsHandoffTrialAuthorizationError(f"refusing to overwrite existing output: {destination}")
    created: list[Path] = []
    try:
        for destination, payload in ((record_path, record_text), (notes_path, notes_text)):
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
            created.append(destination)
    except OSError:
        for destination in created:
            try:
                destination.unlink()
            except OSError:
                pass
        raise
    return sha256(record_path.read_bytes()).hexdigest(), sha256(notes_path.read_bytes()).hexdigest()


def _safe_result(command: str, path: Path, digest: str, **extra: object) -> dict[str, object]:
    result: dict[str, object] = {
        "command": command,
        "path": str(path),
        "sha256": digest,
        "physical_interaction_performed": False,
        "external_device_command_executed": False,
        "raw_device_path_bound": False,
        "mount_target_bound": False,
        "trial_execution_allowed": False,
        "persistent_write_authorized": False,
        "phone_storage_written": False,
        "storage_verified": False,
        "recovery_verified": False,
        "hardware_verified": False,
        "beta_release_authorized": False,
        "beta_gate_credit": False,
    }
    result.update(extra)
    return result


def _emit(result: dict[str, object], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    print(f"evidence workflow: {result['command']}")
    print(f"output: {result['path']}")
    print(f"sha256: {result['sha256']}")
    print("physical interaction/device command: no")
    print("raw target/mount/trial/write authorization: no")
    print("hardware/Beta authorization: no")


def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.evidence_command == "prepare-rootfs-handoff-trial-authorization-review":
        record = prepare_rootfs_handoff_trial_authorization_review_record(
            args.target_binding,
            args.fresh_revalidation,
            args.reviewer,
        )
        notes = (
            "Rootfs handoff trial authorization review notes\n\n"
            "Review the exact target binding and fresh revalidation, logical identity, filesystem/encryption/capacity, "
            "rootfs/recovery identities, staging subpath and rollback limitations. Confirm a later executor must perform "
            "a live-device recheck and require explicit operator confirmation. Do not record a raw /dev path, mount target, "
            "automatic execution or persistent-write authorization here.\n"
        )
        record_sha, notes_sha = _write_pair_exclusive(
            args.record_out,
            record.canonical_json(),
            args.notes_out,
            notes,
        )
        return _safe_result(
            args.evidence_command,
            args.record_out,
            record_sha,
            profile_id=record.profile_id,
            device_serial=record.device_serial,
            decision=record.decision,
            template_only=True,
            notes_path=str(args.notes_out),
            notes_sha256=notes_sha,
            ready_for_interactive_trial_execution_boundary=False,
        )

    if args.evidence_command == "bind-rootfs-handoff-trial-authorization-review":
        evidence = bind_rootfs_handoff_trial_authorization_review(
            args.target_binding,
            args.fresh_revalidation,
            args.review_record,
            args.review_notes,
        )
        digest = write_rootfs_handoff_trial_authorization_evidence(evidence, args.out)
        return _safe_result(
            args.evidence_command,
            args.out,
            digest,
            profile_id=evidence.profile_id,
            device_serial=evidence.device_serial,
            decision=evidence.decision,
            review_checks_complete=evidence.review_checks_complete,
            manual_trial_authorization_accepted=evidence.manual_trial_authorization_accepted,
            ready_for_interactive_trial_execution_boundary=evidence.ready_for_interactive_trial_execution_boundary,
            live_device_recheck_required_at_execution=evidence.live_device_recheck_required_at_execution,
            explicit_operator_confirmation_required_at_execution=evidence.explicit_operator_confirmation_required_at_execution,
            physical_gate_still_incomplete=evidence.physical_gate_still_incomplete,
        )

    if args.evidence_command == "build-rootfs-handoff-trial-plan":
        plan = build_rootfs_handoff_trial_plan(
            args.trial_authorization,
            args.target_binding,
            args.fresh_revalidation,
        )
        digest = write_rootfs_handoff_trial_plan(plan, args.out)
        return _safe_result(
            args.evidence_command,
            args.out,
            digest,
            profile_id=plan.profile_id,
            device_serial=plan.device_serial,
            exact_authorization_chain_bound=plan.exact_authorization_chain_bound,
            plan_ready_for_later_interactive_executor=plan.plan_ready_for_later_interactive_executor,
            live_device_identity_recheck_required=plan.live_device_identity_recheck_required,
            live_firmware_recheck_required=plan.live_firmware_recheck_required,
            live_target_identity_recheck_required=plan.live_target_identity_recheck_required,
            live_filesystem_encryption_capacity_recheck_required=plan.live_filesystem_encryption_capacity_recheck_required,
            rootfs_local_hash_recheck_required=plan.rootfs_local_hash_recheck_required,
            recovery_readiness_recheck_required=plan.recovery_readiness_recheck_required,
            explicit_operator_confirmation_required=plan.explicit_operator_confirmation_required,
            write_scope_confirmation_required=plan.write_scope_confirmation_required,
            physical_gate_still_incomplete=plan.physical_gate_still_incomplete,
        )

    if args.evidence_command == "build-rootfs-handoff-trial-preflight":
        evidence = build_rootfs_handoff_trial_preflight(args.trial_plan, args.rootfs_artifact)
        digest = write_rootfs_handoff_trial_preflight_evidence(evidence, args.out)
        return _safe_result(
            args.evidence_command,
            args.out,
            digest,
            profile_id=evidence.profile_id,
            device_serial=evidence.device_serial,
            exact_trial_plan_bound=evidence.exact_trial_plan_bound,
            local_rootfs_exact_bytes_verified=evidence.local_rootfs_exact_bytes_verified,
            rootfs_artifact_sha256=evidence.rootfs_artifact_sha256,
            rootfs_artifact_size=evidence.rootfs_artifact_size,
            live_device_identity_recheck_required=evidence.live_device_identity_recheck_required,
            live_firmware_recheck_required=evidence.live_firmware_recheck_required,
            live_target_identity_recheck_required=evidence.live_target_identity_recheck_required,
            live_filesystem_encryption_capacity_recheck_required=evidence.live_filesystem_encryption_capacity_recheck_required,
            recovery_readiness_recheck_required=evidence.recovery_readiness_recheck_required,
            explicit_operator_confirmation_required=evidence.explicit_operator_confirmation_required,
            write_scope_confirmation_required=evidence.write_scope_confirmation_required,
            interactive_executor_still_required=evidence.interactive_executor_still_required,
            physical_gate_still_incomplete=evidence.physical_gate_still_incomplete,
        )

    if args.evidence_command == "build-rootfs-handoff-trial-execution-gate":
        evidence = build_rootfs_handoff_trial_execution_gate(
            args.trial_plan,
            args.trial_preflight,
            args.authorized_fresh_revalidation,
            args.execution_fresh_revalidation,
        )
        digest = write_rootfs_handoff_trial_execution_gate_evidence(evidence, args.out)
        return _safe_result(
            args.evidence_command,
            args.out,
            digest,
            profile_id=evidence.profile_id,
            device_serial=evidence.device_serial,
            execution_gate_passed=evidence.execution_gate_passed,
            distinct_execution_capture_bound=evidence.distinct_execution_capture_bound,
            execution_storage_discovery_sha256=evidence.execution_storage_discovery_sha256,
            execution_storage_report_sha256=evidence.execution_storage_report_sha256,
            observed_free_bytes=evidence.observed_free_bytes,
            required_free_bytes=evidence.required_free_bytes,
            local_rootfs_exact_bytes_verified=evidence.local_rootfs_exact_bytes_verified,
            explicit_operator_confirmation_required=evidence.explicit_operator_confirmation_required,
            write_scope_confirmation_required=evidence.write_scope_confirmation_required,
            raw_device_path_resolution_required=evidence.raw_device_path_resolution_required,
            interactive_writer_required=evidence.interactive_writer_required,
            physical_gate_still_incomplete=evidence.physical_gate_still_incomplete,
        )

    raise RootfsHandoffTrialAuthorizationError(f"unsupported trial evidence command: {args.evidence_command}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        result = _run(args)
    except (
        RootfsHandoffTrialAuthorizationError,
        RootfsHandoffTrialPlanError,
        RootfsHandoffTrialPreflightError,
        RootfsHandoffTrialExecutionGateError,
        OSError,
        ValueError,
    ) as exc:
        print(f"Evidence workflow error: {exc}", file=sys.stderr)
        return 2
    _emit(result, as_json=args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
