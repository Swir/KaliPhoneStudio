"""Offline rootfs payload evidence commands for the unified evidence workspace.

These commands progressively bind an exact reviewed rootfs archive to its
expanded write scope, POSIX/PAX metadata, and extraction-safety policy. They
remain host-only and non-writing: no phone I/O, raw-device resolution, mount,
extraction, persistent write or Beta credit is possible here.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from .rootfs_handoff_trial_archive_safety import (
    build_rootfs_handoff_trial_archive_safety_evidence,
    write_rootfs_handoff_trial_archive_safety_evidence,
)
from .rootfs_handoff_trial_metadata import (
    build_rootfs_handoff_trial_metadata_manifest,
    write_rootfs_handoff_trial_metadata_evidence,
)
from .rootfs_handoff_trial_payload import (
    RootfsHandoffTrialPayloadError,
    build_rootfs_handoff_trial_payload_manifest,
    write_rootfs_handoff_trial_payload_evidence,
)

PAYLOAD_EVIDENCE_COMMANDS = (
    "build-rootfs-handoff-trial-payload-manifest",
    "build-rootfs-handoff-trial-metadata-manifest",
    "build-rootfs-handoff-trial-archive-safety",
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="KaliPhoneStudio evidence",
        description=(
            "Offline rootfs payload evidence workspace. It binds exact reviewed host evidence while performing no "
            "phone I/O, raw path binding, mount, extraction, write authorization, hardware promotion or Beta credit."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable safety/result summary.")
    sub = parser.add_subparsers(dest="evidence_command", required=True)

    payload = sub.add_parser(
        PAYLOAD_EVIDENCE_COMMANDS[0],
        help="Bind an exact execution gate to the deterministic expanded rootfs write scope.",
    )
    payload.add_argument("--execution-gate", type=Path, required=True)
    payload.add_argument("--rootfs-artifact", type=Path, required=True)
    payload.add_argument("--out", type=Path, required=True)

    metadata = sub.add_parser(
        PAYLOAD_EVIDENCE_COMMANDS[1],
        help="Bind exact POSIX ownership/mode and non-structural PAX metadata to a reviewed payload manifest.",
    )
    metadata.add_argument("--payload-manifest", type=Path, required=True)
    metadata.add_argument("--rootfs-artifact", type=Path, required=True)
    metadata.add_argument("--out", type=Path, required=True)

    archive = sub.add_parser(
        PAYLOAD_EVIDENCE_COMMANDS[2],
        help="Build host-only extraction-safety evidence for the exact reviewed rootfs archive.",
    )
    archive.add_argument("--metadata-manifest", type=Path, required=True)
    archive.add_argument("--rootfs-artifact", type=Path, required=True)
    archive.add_argument("--out", type=Path, required=True)
    return parser


def _common_result(command: str, out: Path | str, digest: str, evidence: object) -> dict[str, object]:
    return {
        "command": command,
        "path": str(out),
        "sha256": digest,
        "profile_id": getattr(evidence, "profile_id"),
        "device_serial": getattr(evidence, "device_serial"),
        "rootfs_artifact_sha256": getattr(evidence, "rootfs_artifact_sha256"),
        "entry_count": getattr(evidence, "entry_count"),
        "physical_interaction_performed": False,
        "external_device_command_executed": False,
        "raw_device_path_bound": False,
        "mount_target_bound": False,
        "extraction_performed": False,
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


def _run(args: argparse.Namespace) -> dict[str, object]:
    command = args.evidence_command
    if command == PAYLOAD_EVIDENCE_COMMANDS[0]:
        evidence = build_rootfs_handoff_trial_payload_manifest(args.execution_gate, args.rootfs_artifact)
        digest = write_rootfs_handoff_trial_payload_evidence(evidence, args.out)
        result = _common_result(command, args.out, digest, evidence)
        result.update(
            execution_gate_sha256=evidence.execution_gate_sha256,
            regular_payload_bytes=evidence.regular_payload_bytes,
            minimum_required_free_bytes=evidence.minimum_required_free_bytes,
            reviewed_required_free_bytes=evidence.reviewed_required_free_bytes,
            observed_free_bytes=evidence.observed_free_bytes,
            entries_sha256=evidence.entries_sha256,
            exact_execution_gate_bound=evidence.exact_execution_gate_bound,
            exact_rootfs_bytes_verified=evidence.exact_rootfs_bytes_verified,
            deterministic_write_scope_manifested=evidence.deterministic_write_scope_manifested,
            expanded_capacity_requirement_satisfied=evidence.expanded_capacity_requirement_satisfied,
            interactive_writer_still_required=evidence.interactive_writer_still_required,
            explicit_operator_confirmation_still_required=evidence.explicit_operator_confirmation_still_required,
            write_scope_confirmation_still_required=evidence.write_scope_confirmation_still_required,
        )
        return result

    if command == PAYLOAD_EVIDENCE_COMMANDS[1]:
        evidence = build_rootfs_handoff_trial_metadata_manifest(args.payload_manifest, args.rootfs_artifact)
        digest = write_rootfs_handoff_trial_metadata_evidence(evidence, args.out)
        result = _common_result(command, args.out, digest, evidence)
        result.update(
            payload_manifest_sha256=evidence.payload_manifest_sha256,
            execution_gate_sha256=evidence.execution_gate_sha256,
            metadata_entries_sha256=evidence.metadata_entries_sha256,
            pax_header_count=evidence.pax_header_count,
            security_metadata_entry_count=evidence.security_metadata_entry_count,
            exact_payload_manifest_bound=evidence.exact_payload_manifest_bound,
            exact_rootfs_bytes_verified=evidence.exact_rootfs_bytes_verified,
            posix_ownership_manifested=evidence.posix_ownership_manifested,
            pax_metadata_manifested=evidence.pax_metadata_manifested,
            interactive_writer_still_required=evidence.interactive_writer_still_required,
            explicit_operator_confirmation_still_required=evidence.explicit_operator_confirmation_still_required,
            write_scope_confirmation_still_required=evidence.write_scope_confirmation_still_required,
        )
        return result

    if command == PAYLOAD_EVIDENCE_COMMANDS[2]:
        evidence = build_rootfs_handoff_trial_archive_safety_evidence(
            args.metadata_manifest, args.rootfs_artifact
        )
        digest = write_rootfs_handoff_trial_archive_safety_evidence(evidence, args.out)
        result = _common_result(command, args.out, digest, evidence)
        result.update(
            metadata_manifest_sha256=evidence.metadata_manifest_sha256,
            payload_manifest_sha256=evidence.payload_manifest_sha256,
            symlink_count=evidence.symlink_count,
            absolute_symlink_count=evidence.absolute_symlink_count,
            relative_symlink_count=evidence.relative_symlink_count,
            hardlink_count=evidence.hardlink_count,
            exact_metadata_manifest_bound=evidence.exact_metadata_manifest_bound,
            exact_rootfs_bytes_verified=evidence.exact_rootfs_bytes_verified,
            normalized_paths_unique=evidence.normalized_paths_unique,
            path_namespace_safe=evidence.path_namespace_safe,
            link_targets_namespace_safe=evidence.link_targets_namespace_safe,
            no_link_ancestor_pivots=evidence.no_link_ancestor_pivots,
            hardlink_targets_resolved=evidence.hardlink_targets_resolved,
            special_members_rejected=evidence.special_members_rejected,
        )
        return result

    raise RootfsHandoffTrialPayloadError(f"unsupported payload evidence command: {command}")


def _emit(result: dict[str, object], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    print(f"evidence workflow: {result['command']}")
    print(f"output: {result['path']}")
    print(f"sha256: {result['sha256']}")
    print(f"entries: {result['entry_count']}")
    if "regular_payload_bytes" in result:
        print(f"expanded regular bytes: {result['regular_payload_bytes']}")
        print(f"minimum free bytes: {result['minimum_required_free_bytes']}")
    if "pax_header_count" in result:
        print(f"PAX records: {result['pax_header_count']}")
    if "symlink_count" in result:
        print(f"symlinks/hardlinks: {result['symlink_count']}/{result['hardlink_count']}")
    print("physical interaction/device command: no")
    print("raw target/mount/extraction/trial/write authorization: no")
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
