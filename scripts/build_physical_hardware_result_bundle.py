#!/usr/bin/env python3
"""Build an exact-file, non-promoting physical functional-result audit bundle."""
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.physical_hardware_result_bundle import (
    build_physical_hardware_result_bundle_from_files,
    write_physical_hardware_result_bundle_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-plan", type=Path, required=True)
    parser.add_argument("--test-plan-review-evidence", type=Path, required=True)
    parser.add_argument("--observation-evidence", type=Path, action="append", default=[])
    parser.add_argument("--review-evidence", type=Path, action="append", default=[])
    parser.add_argument("--summary-evidence", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        bundle = build_physical_hardware_result_bundle_from_files(
            args.test_plan,
            args.test_plan_review_evidence,
            args.observation_evidence,
            args.review_evidence,
            args.summary_evidence,
        )
        digest = write_physical_hardware_result_bundle_evidence(bundle, args.out)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(f"physical functional result bundle: {args.out}")
    print(f"sha256: {digest}")
    print(
        f"exact observations/reviews: {bundle.observation_count}/{bundle.result_review_count}; "
        f"Beta-required reviewed passes: "
        f"{bundle.beta_required_reviewed_pass_count}/{bundle.beta_required_test_count}"
    )
    print(
        "all Beta-required functional tests reviewed pass in this exact bundle: "
        f"{str(bundle.beta_required_tests_all_reviewed_pass).lower()}"
    )
    print("hardware/Beta credit: false; complete manual release-gate review remains required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
