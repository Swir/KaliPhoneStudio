#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.physical_hardware_test_observation import load_physical_hardware_test_observation_evidence
from kaliphonestudio.physical_hardware_test_review import (
    PhysicalHardwareTestReviewError,
    make_rejected_physical_hardware_test_review_record,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a rejected-by-default review template for one exact physical functional-test observation"
    )
    parser.add_argument("--observation-evidence", type=Path, required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        observation = load_physical_hardware_test_observation_evidence(args.observation_evidence)
        record = make_rejected_physical_hardware_test_review_record(observation, args.reviewer)
        if args.out.exists() or args.out.is_symlink():
            raise PhysicalHardwareTestReviewError("refusing to overwrite existing functional test review template")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(record.canonical_json())
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print("Created rejected-by-default physical functional-test review template.")
    print("A reviewed result still cannot authorize project support or Beta release by itself.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
