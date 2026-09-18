#!/usr/bin/env python3
"""Prepare a rejected-by-default rootfs trial authorization review record."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

from kaliphonestudio.rootfs_handoff_trial_authorization import (
    RootfsHandoffTrialAuthorizationError,
    prepare_rootfs_handoff_trial_authorization_review_record,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare an offline rejected-by-default review for the exact accepted logical target binding and "
            "fresh-device revalidation. This never contacts a phone, binds a raw path, mounts, writes or executes a trial."
        )
    )
    parser.add_argument("--target-binding", type=Path, required=True)
    parser.add_argument("--fresh-revalidation", type=Path, required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--record-out", type=Path, required=True)
    parser.add_argument("--notes-out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def _write_pair(record_out: Path, record_text: str, notes_out: Path, notes_text: str) -> tuple[str, str]:
    if record_out == notes_out:
        raise RootfsHandoffTrialAuthorizationError("record and notes outputs must be different files")
    for destination in (record_out, notes_out):
        if destination.exists() or destination.is_symlink():
            raise RootfsHandoffTrialAuthorizationError(f"refusing to overwrite existing output: {destination}")
    created: list[Path] = []
    try:
        for destination, payload in ((record_out, record_text), (notes_out, notes_text)):
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
    return sha256(record_out.read_bytes()).hexdigest(), sha256(notes_out.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        record = prepare_rootfs_handoff_trial_authorization_review_record(
            args.target_binding,
            args.fresh_revalidation,
            args.reviewer,
        )
        notes = (
            "Rootfs handoff trial authorization review notes\n\n"
            "Review the exact target-binding and fresh-revalidation identities, logical target/filesystem/encryption/capacity, "
            "rootfs and recovery identities, staging subpath, rollback limitations and the requirement for a separate "
            "interactive executor with a live-device recheck and explicit operator confirmation.\n"
            "Do not add a raw /dev path, mount target, automatic execution or persistent-write authorization here.\n"
        )
        record_sha, notes_sha = _write_pair(args.record_out, record.canonical_json(), args.notes_out, notes)
    except (RootfsHandoffTrialAuthorizationError, OSError) as exc:
        print(f"Trial authorization preparation error: {exc}", file=sys.stderr)
        return 2

    result = {
        "record_path": str(args.record_out),
        "record_sha256": record_sha,
        "notes_path": str(args.notes_out),
        "notes_sha256": notes_sha,
        "profile_id": record.profile_id,
        "device_serial": record.device_serial,
        "decision": record.decision,
        "template_only": True,
        "trial_execution_allowed": False,
        "persistent_write_authorized": False,
        "hardware_verified": False,
        "beta_release_authorized": False,
    }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"trial authorization review template: {args.record_out}")
        print(f"record sha256: {record_sha}")
        print(f"notes sha256: {notes_sha}")
        print("decision: rejected (edit only after manual review)")
        print("device I/O / trial execution / write authorization: no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
