#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.physical_hardware_review import (
    PhysicalHardwareReviewError,
    make_rejected_hardware_review_record,
)
from kaliphonestudio.physical_hardware_survey import load_physical_hardware_survey_evidence


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a safe rejected-by-default manual hardware-survey review template"
    )
    parser.add_argument("--survey-evidence", type=Path, required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        survey = load_physical_hardware_survey_evidence(args.survey_evidence)
        record = make_rejected_hardware_review_record(survey, args.reviewer)
        if args.out.exists() or args.out.is_symlink():
            raise PhysicalHardwareReviewError("refusing to overwrite existing review template")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(record.canonical_json())
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print("Created rejected-by-default hardware survey review template.")
    print("Presence remains contextual only; functional testing is still required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
