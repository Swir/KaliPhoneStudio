#!/usr/bin/env python3
"""Bind manual review to one exact physical functional-test observation."""
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.physical_campaign_admission import load_current_physical_campaign_observation
from kaliphonestudio.physical_hardware_test_review import (
    bind_current_physical_hardware_test_review_from_files,
    write_physical_hardware_test_review_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boot-observation", type=Path, required=True)
    parser.add_argument("--observation-evidence", type=Path, required=True)
    parser.add_argument("--review-record", type=Path, required=True)
    parser.add_argument("--review-notes", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        boot_observation = load_current_physical_campaign_observation(args.boot_observation)
        evidence = bind_current_physical_hardware_test_review_from_files(
            boot_observation,
            args.observation_evidence,
            args.review_record,
            args.review_notes,
        )
        digest = write_physical_hardware_test_review_evidence(evidence, args.out)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(f"functional test review evidence: {args.out}")
    print(f"sha256: {digest}")
    print(f"test: {evidence.test_id}; reviewed result: {evidence.reviewed_result}")
    print("project support/Beta credit: false; manual release-gate review remains required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
