"""Offline rootfs payload-manifest command for the unified evidence workspace.

This command inspects the exact reviewed rootfs archive after the interactive
execution gate has passed. It remains host-only and non-writing: no phone I/O,
raw-device resolution, mount, extraction, persistent write or Beta credit is
possible here.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from .rootfs_handoff_trial_payload import (
    RootfsHandoffTrialPayloadError,
    build_rootfs_handoff_trial_payload_manifest,
    write_rootfs_handoff_trial_payload_evidence,
)

PAYLOAD_EVIDENCE_COMMANDS = ("build-rootfs-handoff-trial-payload-manifest",)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="KaliPhoneStudio evidence",
        description=(
            "Offline rootfs payload-scope manifest workspace. It binds one exact execution gate to one exact "
            "rootfs archive, inventories the expanded archive scope and capacity requirement, and performs no "
            "phone I/O, raw path binding, mount, extraction, write authorization, hardware promotion or Beta credit."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable safety/result summary.")
    sub = parser.add_subparsers(dest="evidence_command", required=True)
    payload = sub.add_parser(
        "build-rootfs-handoff-trial-payload-manifest",
        help="Bind an exact execution gate to the deterministic expanded rootfs write scope.",
        description=(
            "Inspect the exact reviewed rootfs archive, reject unsafe tar scope and derive the expanded capacity "
            "requirement. Passing this command does not resolve a raw path, contact a phone, mount/extract/write "
            "storage or grant storage/recovery/hardware/Beta credit."
        ),
    )
    payload.add_argument("--execution-gate", type=Path, required=True)
    payload.add_argument("--rootfs-artifact", type=Path, required=True)
    payload.add_argument("--out", type=Path, required=True)
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.evidence_command != PAYLOAD_EVIDENCE_COMMANDS[0]:
        raise RootfsHandoffTrialPayloadError(f"unsupported payload evidence command: {args.evidence_command}")
    evidence = build_rootfs_handoff_trial_payload_manifest(args.execution_gate, args.rootfs_artifact)
    digest = write_rootfs_handoff_trial_payload_evidence(evidence, args.out)
    return {
        "command": args.evidence_command,
        "path": str(args.out),
        "sha256": digest,
        "profile_id": evidence.profile_id,
        "device_serial": evidence.device_serial,
        "execution_gate_sha256": evidence.execution_gate_sha256,
        "rootfs_artifact_sha256": evidence.rootfs_artifact_sha256,
        "entry_count": evidence.entry_count,
        "regular_payload_bytes": evidence.regular_payload_bytes,
        "minimum_required_free_bytes": evidence.minimum_required_free_bytes,
        "reviewed_required_free_bytes": evidence.reviewed_required_free_bytes,
        "observed_free_bytes": evidence.observed_free_bytes,
        "entries_sha256": evidence.entries_sha256,
        "exact_execution_gate_bound": evidence.exact_execution_gate_bound,
        "exact_rootfs_bytes_verified": evidence.exact_rootfs_bytes_verified,
        "deterministic_write_scope_manifested": evidence.deterministic_write_scope_manifested,
        "expanded_capacity_requirement_satisfied": evidence.expanded_capacity_requirement_satisfied,
        "interactive_writer_still_required": evidence.interactive_writer_still_required,
        "explicit_operator_confirmation_still_required": evidence.explicit_operator_confirmation_still_required,
        "write_scope_confirmation_still_required": evidence.write_scope_confirmation_still_required,
        "physical_interaction_performed": False,
        "external_device_command_executed": False,
        "raw_device_path_bound": False,
        "mount_target_bound": False,
        "trial_execution_allowed": False,
        "persistent_write_authorized": False,
        "persistent_write_performed": False,
        "phone_storage_written": False,
        "storage_verified": False,
        "recovery_verified": False,
        "hardware_verified": False,
        "beta_release_authorized": False,
        "beta_gate_credit": False,
    }


def _emit(result: dict[str, object], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    print(f"evidence workflow: {result['command']}")
    print(f"output: {result['path']}")
    print(f"sha256: {result['sha256']}")
    print(f"entries: {result['entry_count']}")
    print(f"expanded regular bytes: {result['regular_payload_bytes']}")
    print(f"minimum free bytes: {result['minimum_required_free_bytes']}")
    print("physical interaction/device command: no")
    print("raw target/mount/extraction/trial/write authorization: no")
    print("interactive writer still required: yes")
    print("hardware/Beta authorization: no")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        result = _run(args)
    except (RootfsHandoffTrialPayloadError, OSError, ValueError) as exc:
        print(f"Evidence workflow error: {exc}", file=sys.stderr)
        return 2
    _emit(result, as_json=args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
