#!/usr/bin/env python3
"""Bind an exact rootfs strategy review to an exact physical evidence chain."""
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.physical_bringup_dossier import load_physical_bringup_dossier_evidence
from kaliphonestudio.physical_bringup_dossier_review import load_physical_bringup_dossier_review_evidence
from kaliphonestudio.physical_release_gate_audit import load_physical_release_gate_audit_evidence
from kaliphonestudio.physical_storage_discovery import load_physical_storage_discovery_evidence
from kaliphonestudio.physical_storage_review import load_physical_storage_review_evidence
from kaliphonestudio.rootfs_handoff_strategy_review import (
    bind_rootfs_handoff_strategy_review,
    load_rootfs_handoff_strategy_review_record,
    read_rootfs_handoff_strategy_review_notes,
    write_rootfs_handoff_strategy_review_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Bind a fail-closed reversible rootfs strategy review. No phone I/O or writes are performed.")
    parser.add_argument("--storage-discovery", type=Path, required=True)
    parser.add_argument("--storage-review", type=Path, required=True)
    parser.add_argument("--dossier", type=Path, required=True)
    parser.add_argument("--dossier-review", type=Path, required=True)
    parser.add_argument("--release-gate-audit", type=Path, required=True)
    parser.add_argument("--review-record", type=Path, required=True)
    parser.add_argument("--review-notes", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    record, record_sha, record_size = load_rootfs_handoff_strategy_review_record(args.review_record)
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
    print(f"strategy_design_accepted={str(evidence.strategy_design_accepted).lower()}")
    print("target_selected=false")
    print("trial_execution_allowed=false")
    print("write_authorized=false")
    print("hardware_verified=false")
    print("beta_release_authorized=false")
    print(f"sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
