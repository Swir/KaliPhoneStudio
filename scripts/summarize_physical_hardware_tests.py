#!/usr/bin/env python3
"""Build a non-promoting status summary for reviewed physical functional tests."""
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.physical_hardware_test_summary import (
    build_physical_hardware_test_summary_from_files,
    write_physical_hardware_test_summary_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-plan", type=Path, required=True)
    parser.add_argument("--review-evidence", type=Path, action="append", default=[])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        summary = build_physical_hardware_test_summary_from_files(args.test_plan, args.review_evidence)
        digest = write_physical_hardware_test_summary_evidence(summary, args.out)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(f"functional test summary: {args.out}")
    print(f"sha256: {digest}")
    print(
        f"reviewed passes: {summary.reviewed_pass_count}/{summary.test_count}; "
        f"Beta-required reviewed passes: {summary.beta_required_reviewed_pass_count}/{summary.beta_required_test_count}"
    )
    print(f"all Beta-required tests reviewed pass: {str(summary.beta_required_tests_all_reviewed_pass).lower()}")
    print("project support/Beta credit: false; manual release-gate review remains required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
