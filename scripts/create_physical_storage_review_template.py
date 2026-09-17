#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from kaliphonestudio.physical_storage_review import (
    PhysicalStorageReviewError,
    load_discovery_for_review,
)

_ATTESTATION = (
    "I reviewed the exact physical storage discovery evidence and recovery plan; "
    "this decision does not select a storage target or authorize a write."
)


def build_template(discovery_path: Path) -> dict[str, object]:
    discovery = load_discovery_for_review(discovery_path)
    return {
        "schema_version": 1,
        "profile_id": discovery.profile_id,
        "device_serial": discovery.device_serial,
        "review_policy": "human-storage-discovery-review-v1",
        "review_scope": "discovery-evidence-only-no-target-v1",
        "reviewer_id": "REPLACE_WITH_REVIEWER_ID",
        "decision": "REPLACE_WITH_DECISION",
        "physical_storage_discovery_sha256": discovery.evidence_sha256(),
        "discovery_report_sha256": discovery.discovery_report_sha256,
        "recovery_plan_sha256": discovery.recovery_plan_sha256,
        "target_selected": False,
        "storage_path_bound": False,
        "write_authorized": False,
        "phone_storage_written": False,
        "attestation": _ATTESTATION,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create a non-valid review template pre-bound to exact physical-storage discovery evidence. "
            "The reviewer must replace reviewer_id and decision manually before the review recorder can accept it."
        )
    )
    parser.add_argument("--discovery-evidence", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    try:
        template = build_template(args.discovery_evidence)
        if args.out.exists() or args.out.is_symlink():
            raise PhysicalStorageReviewError("refusing to overwrite physical storage review template")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(template, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    except PhysicalStorageReviewError as exc:
        parser.error(str(exc))

    print(f"review template written: {args.out}")
    print("replace reviewer_id and decision manually; template itself is not review evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
