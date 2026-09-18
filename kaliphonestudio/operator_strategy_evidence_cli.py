"""Offline rootfs-strategy review commands for the shared operator workspace.

These commands consume already captured physical evidence only. They never invoke
ADB/Fastboot, never communicate with a phone, never select a raw storage path,
never authorize a persistent write and never grant hardware/Beta credit.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from typing import Sequence

from .physical_bringup_dossier import load_physical_bringup_dossier_evidence
from .physical_bringup_dossier_review import load_physical_bringup_dossier_review_evidence
from .physical_release_gate_audit import load_physical_release_gate_audit_evidence
from .physical_storage_discovery import load_physical_storage_discovery_evidence
from .physical_storage_review import load_physical_storage_review_evidence
from .rootfs_handoff_strategy_review import (
    RootfsHandoffStrategyReviewRecord,
    bind_rootfs_handoff_strategy_review,
    load_rootfs_handoff_strategy_review_record,
    read_rootfs_handoff_strategy_review_notes,
    write_rootfs_handoff_strategy_review_evidence,
)

_SAFE_REVIEWER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+-]{0,127}$")
STRATEGY_EVIDENCE_COMMANDS = (
    "prepare-rootfs-handoff-strategy-review",
    "bind-rootfs-handoff-strategy-review",
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="KaliPhoneStudio evidence",
        description=(
            "Offline reversible rootfs-strategy review workspace. No phone I/O, raw target selection, "
            "persistent write authorization, hardware promotion or Beta credit is possible here."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable safety/result summary.")
    sub = parser.add_subparsers(dest="evidence_command", required=True)

    prepare = sub.add_parser(
        "prepare-rootfs-handoff-strategy-review",
        help="Create rejected-by-default strategy review record and notes templates.",
    )
    prepare.add_argument("--storage-discovery", type=Path, required=True)
    prepare.add_argument("--storage-review", type=Path, required=True)
    prepare.add_argument("--reviewer", required=True)
    prepare.add_argument("--candidate-partition-role", required=True)
    prepare.add_argument("--staging-subpath", required=True)
    prepare.add_argument("--required-free-bytes", type=int, required=True)
    prepare.add_argument("--record-out", type=Path, required=True)
    prepare.add_argument("--notes-out", type=Path, required=True)

    bind = sub.add_parser(
        "bind-rootfs-handoff-strategy-review",
        help="Bind one exact strategy review to the exact accepted physical evidence chain.",
    )
    bind.add_argument("--storage-discovery", type=Path, required=True)
    bind.add_argument("--storage-review", type=Path, required=True)
    bind.add_argument("--dossier", type=Path, required=True)
    bind.add_argument("--dossier-review", type=Path, required=True)
    bind.add_argument("--release-gate-audit", type=Path, required=True)
    bind.add_argument("--review-record", type=Path, required=True)
    bind.add_argument("--review-notes", type=Path, required=True)
    bind.add_argument("--out", type=Path, required=True)
    return parser


def _write_pair_exclusive(record_path: Path, record_text: str, notes_path: Path, notes_text: str) -> tuple[str, str]:
    record_path = Path(record_path)
    notes_path = Path(notes_path)
    if record_path == notes_path:
        raise ValueError("strategy review record and notes outputs must be different files")
    for destination in (record_path, notes_path):
        if destination.exists() or destination.is_symlink():
            raise ValueError(f"refusing to overwrite existing output: {destination}")
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
        "storage_target_selected": False,
        "persistent_write_authorized": False,
        "phone_storage_written": False,
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
    print("storage target/persistent write: no")
    print("hardware/Beta authorization: no")


def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.evidence_command == "prepare-rootfs-handoff-strategy-review":
        if not _SAFE_REVIEWER_RE.fullmatch(args.reviewer):
            raise ValueError("reviewer must be a safe bounded identifier")
        discovery = load_physical_storage_discovery_evidence(args.storage_discovery)
        storage_review = load_physical_storage_review_evidence(args.storage_review)
        if storage_review.physical_storage_discovery_sha256 != discovery.evidence_sha256():
            raise ValueError("storage review is detached from supplied discovery")
        if storage_review.accepted_for_strategy_design is not True:
            raise ValueError("strategy template requires an accepted physical storage review")
        record = RootfsHandoffStrategyReviewRecord(
            schema_version=1,
            review_policy="reversible-rootfs-handoff-strategy-review-v1",
            profile_id=discovery.profile_id,
            device_serial=discovery.device_serial,
            reviewer=args.reviewer,
            decision="rejected",
            candidate_partition_role=args.candidate_partition_role,
            staging_subpath=args.staging_subpath,
            required_free_bytes=args.required_free_bytes,
            rootfs_artifact_sha256=storage_review.rootfs_artifact_sha256,
            recovery_plan_sha256=storage_review.recovery_plan_sha256,
            exact_physical_chain_reviewed=False,
            capacity_evidence_reviewed=False,
            filesystem_encryption_reviewed=False,
            rollback_plan_reviewed=False,
            forbidden_partition_policy_reviewed=False,
            no_raw_device_path_reviewed=False,
            no_write_authorization_reviewed=False,
            target_selected=False,
            storage_path_bound=False,
            trial_execution_allowed=False,
            write_authorized=False,
            phone_storage_written=False,
        )
        notes = (
            "Rootfs handoff strategy review notes\n\n"
            "Record the exact physical capacity/filesystem/encryption evidence, rollback reasoning, "
            "forbidden-partition review, and why no raw device path or write authorization is granted.\n"
        )
        record_digest, notes_digest = _write_pair_exclusive(
            args.record_out, record.canonical_json(), args.notes_out, notes
        )
        return _safe_result(
            args.evidence_command,
            args.record_out,
            record_digest,
            profile_id=record.profile_id,
            device_serial=record.device_serial,
            decision="rejected",
            template_only=True,
            notes_path=str(args.notes_out),
            notes_sha256=notes_digest,
        )

    if args.evidence_command == "bind-rootfs-handoff-strategy-review":
        record, record_sha, record_size = load_rootfs_handoff_strategy_review_record(args.review_record)
        # Recompute the identity from the parsed canonical record before binding. This makes
        # the shared operator path fail closed if a caller ever supplies detached metadata.
        canonical = record.canonical_json().encode("utf-8")
        if record_sha != sha256(canonical).hexdigest() or record_size != len(canonical):
            raise ValueError("strategy review record digest/size does not match canonical record bytes")
        notes_sha, notes_size = read_rootfs_handoff_strategy_review_notes(args.review_notes)
        evidence = bind_rootfs_handoff_strategy_review(
            load_physical_storage_discovery_evidence(args.storage_discovery),
            load_physical_storage_review_evidence(args.storage_review),
            load_physical_bringup_dossier_evidence(args.dossier),
            load_physical_bringup_dossier_review_evidence(args.dossier_review),
            load_physical_release_gate_audit_evidence(args.release_gate_audit),
            record,
            review_record_sha256=record_sha,
            review_record_size=record_size,
            review_notes_sha256=notes_sha,
            review_notes_size=notes_size,
        )
        digest = write_rootfs_handoff_strategy_review_evidence(evidence, args.out)
        return _safe_result(
            args.evidence_command,
            args.out,
            digest,
            profile_id=evidence.profile_id,
            device_serial=evidence.device_serial,
            decision=evidence.decision,
            strategy_design_accepted=evidence.strategy_design_accepted,
            manual_target_binding_required=evidence.manual_target_binding_required,
            physical_gate_still_incomplete=evidence.physical_gate_still_incomplete,
        )

    raise ValueError(f"unsupported strategy evidence command: {args.evidence_command}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        result = _run(args)
    except (ValueError, OSError) as exc:
        print(f"Evidence workflow error: {exc}", file=sys.stderr)
        return 2
    _emit(result, as_json=args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
