#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.physical_storage_review import (
    load_discovery_for_review,
    record_physical_storage_review,
    write_physical_storage_review_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Bind a manual review to one exact physical-storage discovery record. "
            "This command is offline-only and cannot select a target or authorize storage writes."
        )
    )
    parser.add_argument("--discovery-evidence", type=Path, required=True)
    parser.add_argument("--review-record", type=Path, required=True)
    parser.add_argument("--review-notes", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    discovery = load_discovery_for_review(args.discovery_evidence)
    evidence = record_physical_storage_review(
        discovery,
        args.review_record,
        args.review_notes,
    )
    digest = write_physical_storage_review_evidence(evidence, args.out)
    print(evidence.canonical_json(), end="")
    print(f"physical storage review evidence sha256={digest}")
    print("target/write/hardware/Beta credit: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
