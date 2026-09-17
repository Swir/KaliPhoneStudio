#!/usr/bin/env python3
"""Create a rejected-by-default manual review record for an exact physical test plan."""
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.physical_hardware_test_plan import load_physical_hardware_test_plan
from kaliphonestudio.physical_hardware_test_plan_review import (
    make_rejected_physical_hardware_test_plan_review_record,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare a fail-closed review template for one exact physical hardware test plan."
    )
    parser.add_argument("--test-plan", required=True, type=Path)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    plan = load_physical_hardware_test_plan(args.test_plan)
    record = make_rejected_physical_hardware_test_plan_review_record(plan, args.reviewer)
    if args.out.exists() or args.out.is_symlink():
        raise SystemExit(f"refusing to overwrite existing output: {args.out}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(record.canonical_json(), encoding="utf-8", newline="\n")
    print(f"prepared rejected-by-default review record for plan {plan.evidence_sha256()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
