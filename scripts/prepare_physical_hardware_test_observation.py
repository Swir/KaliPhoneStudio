#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.physical_hardware_test_observation import (
    PhysicalHardwareTestObservationError,
    make_inconclusive_physical_hardware_test_observation_record,
)
from kaliphonestudio.physical_hardware_test_plan import load_physical_hardware_test_plan


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create an inconclusive, not-executed-by-default physical functional-test observation template"
    )
    parser.add_argument("--test-plan", type=Path, required=True)
    parser.add_argument("--test-id", required=True)
    parser.add_argument("--operator", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        plan = load_physical_hardware_test_plan(args.test_plan)
        record = make_inconclusive_physical_hardware_test_observation_record(plan, args.test_id, args.operator)
        if args.out.exists() or args.out.is_symlink():
            raise PhysicalHardwareTestObservationError("refusing to overwrite existing observation template")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(record.canonical_json())
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print("Created not-executed-by-default physical functional-test observation template.")
    print("Edit only after the exact physical test is actually performed; this template grants no hardware/Beta credit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
