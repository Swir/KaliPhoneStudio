#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.physical_hardware_review import (
    PhysicalHardwareReviewError,
    review_physical_hardware_survey_files,
    write_physical_hardware_review_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bind one exact manual review to one exact physical hardware-presence survey"
    )
    parser.add_argument("--survey-evidence", type=Path, required=True)
    parser.add_argument("--review-record", type=Path, required=True)
    parser.add_argument("--review-notes", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        evidence = review_physical_hardware_survey_files(
            args.survey_evidence,
            args.review_record,
            args.review_notes,
        )
        digest = write_physical_hardware_review_evidence(evidence, args.out)
    except PhysicalHardwareReviewError as exc:
        parser.error(str(exc))
    print(evidence.canonical_json(), end="")
    print(f"hardware review evidence sha256={digest}")
    print("functional hardware/Beta credit: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
