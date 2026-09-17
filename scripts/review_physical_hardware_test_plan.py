#!/usr/bin/env python3
"""Bind an exact physical functional-test plan to an independent manual review."""
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.physical_hardware_test_plan_review import (
    bind_physical_hardware_test_plan_review_from_files,
    write_physical_hardware_test_plan_review_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bind exact canonical test-plan bytes, review record and notes into immutable review evidence."
    )
    parser.add_argument("--test-plan", required=True, type=Path)
    parser.add_argument("--review-record", required=True, type=Path)
    parser.add_argument("--review-notes", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    evidence = bind_physical_hardware_test_plan_review_from_files(
        args.test_plan,
        args.review_record,
        args.review_notes,
    )
    digest = write_physical_hardware_test_plan_review_evidence(evidence, args.out)
    print(
        "physical test-plan review: "
        f"decision={evidence.decision} "
        f"accepted_for_physical_execution={str(evidence.accepted_for_physical_execution).lower()} "
        f"sha256={digest}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
