#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from kaliphonestudio.physical_storage_review import (
    PhysicalStorageReviewError,
    load_discovery_for_review,
)

_SAFE_REVIEWER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+-]{0,127}$")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create a fail-safe manual-review record template for one exact physical-storage "
            "discovery evidence file. The template defaults to rejected with every check false."
        )
    )
    parser.add_argument("--discovery-evidence", type=Path, required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    if not _SAFE_REVIEWER_RE.fullmatch(args.reviewer):
        parser.error("reviewer must be a safe identifier using letters, numbers, . _ @ + or -")
    discovery = load_discovery_for_review(args.discovery_evidence)
    destination = args.out
    if destination.exists() or destination.is_symlink():
        parser.error("refusing to overwrite review template")
    destination.parent.mkdir(parents=True, exist_ok=True)
    template = {
        "schema_version": 1,
        "profile_id": discovery.profile_id,
        "device_serial": discovery.device_serial,
        "review_policy": "manual-physical-storage-review-v1",
        "reviewer": args.reviewer,
        "decision": "rejected",
        "physical_context_reviewed": False,
        "topology_reviewed": False,
        "filesystem_reviewed": False,
        "encryption_reviewed": False,
        "free_space_reviewed": False,
        "recovery_plan_reviewed": False,
        "evidence_chain_reviewed": False,
        "target_selected": False,
        "storage_path_bound": False,
        "write_authorized": False,
    }
    try:
        destination.write_text(
            json.dumps(template, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    except OSError as exc:
        raise PhysicalStorageReviewError("could not write review template") from exc
    print(f"created safe review template: {destination}")
    print("default decision: rejected")
    print("target/write/hardware/Beta credit: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
