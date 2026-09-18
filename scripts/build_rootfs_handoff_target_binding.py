from __future__ import annotations

import argparse
from pathlib import Path
import sys

from kaliphonestudio.rootfs_handoff_target_binding import (
    RootfsHandoffTargetBindingError,
    bind_rootfs_handoff_target_binding_review,
    prepare_rootfs_handoff_target_binding_review_record,
    write_rootfs_handoff_target_binding_evidence,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Offline rootfs logical-target binding review. No phone I/O, raw device path, mount, "
            "persistent write, hardware verification or Beta authorization is performed."
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare", help="Create a rejected-by-default review record and notes template.")
    prepare.add_argument("--storage-discovery", type=Path, required=True)
    prepare.add_argument("--storage-report", type=Path, required=True)
    prepare.add_argument("--strategy-review", type=Path, required=True)
    prepare.add_argument("--reviewer", required=True)
    prepare.add_argument("--record-out", type=Path, required=True)
    prepare.add_argument("--notes-out", type=Path, required=True)

    bind = sub.add_parser("bind", help="Bind an edited review record to the exact physical evidence chain.")
    bind.add_argument("--storage-discovery", type=Path, required=True)
    bind.add_argument("--storage-report", type=Path, required=True)
    bind.add_argument("--strategy-review", type=Path, required=True)
    bind.add_argument("--review-record", type=Path, required=True)
    bind.add_argument("--review-notes", type=Path, required=True)
    bind.add_argument("--out", type=Path, required=True)
    return parser


def _write_new(path: Path, text: str) -> None:
    if path.exists() or path.is_symlink():
        raise RootfsHandoffTargetBindingError(f"refusing to overwrite existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    except OSError as exc:
        raise RootfsHandoffTargetBindingError(f"cannot write output {path}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "prepare":
            record = prepare_rootfs_handoff_target_binding_review_record(
                args.storage_discovery,
                args.storage_report,
                args.strategy_review,
                args.reviewer,
            )
            if args.record_out == args.notes_out:
                raise RootfsHandoffTargetBindingError("review record and notes outputs must differ")
            _write_new(args.record_out, record.canonical_json())
            try:
                _write_new(
                    args.notes_out,
                    "Rootfs handoff target-binding review notes\n\n"
                    "Review the exact logical partition identity, filesystem/encryption unlock state, capacity, "
                    "recovery plan and staging subpath. Do not record a /dev path, mount target or write authorization.\n",
                )
            except Exception:
                args.record_out.unlink(missing_ok=True)
                raise
            print("decision=rejected")
            print("logical_target_identity_bound=false")
            print("trial_execution_allowed=false")
            print("write_authorized=false")
            print("beta_release_authorized=false")
            return 0

        evidence = bind_rootfs_handoff_target_binding_review(
            args.storage_discovery,
            args.storage_report,
            args.strategy_review,
            args.review_record,
            args.review_notes,
        )
        digest = write_rootfs_handoff_target_binding_evidence(evidence, args.out)
        print(f"evidence_sha256={digest}")
        print(f"decision={evidence.decision}")
        print(f"logical_target_identity_bound={str(evidence.logical_target_identity_bound).lower()}")
        print("fresh_device_revalidation_required=true")
        print("trial_execution_allowed=false")
        print("write_authorized=false")
        print("beta_release_authorized=false")
        return 0
    except (RootfsHandoffTargetBindingError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
