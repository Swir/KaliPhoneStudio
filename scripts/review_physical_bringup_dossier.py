#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.physical_bringup_dossier import load_physical_bringup_dossier_evidence
from kaliphonestudio.physical_bringup_dossier_review import (
    PhysicalBringupDossierReviewError,
    bind_physical_bringup_dossier_review,
    load_physical_bringup_dossier_review_record,
    load_physical_bringup_dossier_verification_for_review,
    read_physical_bringup_dossier_review_notes,
    write_physical_bringup_dossier_review_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Manually review one exact verified physical bring-up dossier for later strategy review. "
            "This command cannot select a target or authorize phone writes."
        )
    )
    parser.add_argument("--dossier", type=Path, required=True)
    parser.add_argument("--verification", type=Path, required=True)
    parser.add_argument("--review-record", type=Path, required=True)
    parser.add_argument("--review-notes", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    try:
        dossier = load_physical_bringup_dossier_evidence(args.dossier)
        verification = load_physical_bringup_dossier_verification_for_review(args.verification)
        review, record_sha256, record_size = load_physical_bringup_dossier_review_record(args.review_record)
        notes_sha256, notes_size = read_physical_bringup_dossier_review_notes(args.review_notes)
        evidence = bind_physical_bringup_dossier_review(
            dossier,
            verification,
            review,
            review_record_sha256=record_sha256,
            review_record_size=record_size,
            review_notes_sha256=notes_sha256,
            review_notes_size=notes_size,
        )
        digest = write_physical_bringup_dossier_review_evidence(evidence, args.out)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))

    print(evidence.canonical_json(), end="")
    print(f"physical dossier review evidence sha256={digest}")
    print("target/write/hardware/Beta credit: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
