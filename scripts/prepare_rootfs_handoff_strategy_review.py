#!/usr/bin/env python3
"""Prepare a rejected-by-default reversible rootfs strategy review record."""
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.physical_storage_discovery import load_physical_storage_discovery_evidence
from kaliphonestudio.physical_storage_review import load_physical_storage_review_evidence
from kaliphonestudio.rootfs_handoff_strategy_review import RootfsHandoffStrategyReviewRecord


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a fail-closed rootfs handoff strategy review template. No phone I/O is performed.")
    parser.add_argument("--storage-discovery", type=Path, required=True)
    parser.add_argument("--storage-review", type=Path, required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--candidate-partition-role", required=True)
    parser.add_argument("--staging-subpath", required=True)
    parser.add_argument("--required-free-bytes", type=int, required=True)
    parser.add_argument("--record-out", type=Path, required=True)
    parser.add_argument("--notes-out", type=Path, required=True)
    args = parser.parse_args()

    discovery = load_physical_storage_discovery_evidence(args.storage_discovery)
    review = load_physical_storage_review_evidence(args.storage_review)
    if review.physical_storage_discovery_sha256 != discovery.evidence_sha256():
        raise SystemExit("storage review is detached from supplied discovery")
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
        rootfs_artifact_sha256=review.rootfs_artifact_sha256,
        recovery_plan_sha256=review.recovery_plan_sha256,
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
    for path in (args.record_out, args.notes_out):
        if path.exists() or path.is_symlink():
            raise SystemExit(f"refusing to overwrite existing output: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
    args.record_out.write_text(record.canonical_json(), encoding="utf-8", newline="\n")
    args.notes_out.write_text(
        "Rootfs handoff strategy review notes\n\n"
        "Record the exact physical capacity/filesystem/encryption evidence, rollback reasoning, forbidden-partition review, and why no raw device path or write authorization is being granted.\n",
        encoding="utf-8",
        newline="\n",
    )
    print(args.record_out)
    print(args.notes_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
