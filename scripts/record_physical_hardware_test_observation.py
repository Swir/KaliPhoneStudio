#!/usr/bin/env python3
"""Bind one actually executed physical functional-test observation to an accepted exact plan review."""
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.physical_campaign_admission import load_current_physical_campaign_observation
from kaliphonestudio.physical_hardware_test_observation import (
    bind_current_physical_hardware_test_observation_from_files,
    write_physical_hardware_test_observation_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boot-observation", type=Path, required=True)
    parser.add_argument("--test-plan", type=Path, required=True)
    parser.add_argument("--test-plan-review-evidence", type=Path, required=True)
    parser.add_argument("--test-id", required=True)
    parser.add_argument("--observation-record", type=Path, required=True)
    parser.add_argument("--observation-notes", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        observation = load_current_physical_campaign_observation(args.boot_observation)
        evidence = bind_current_physical_hardware_test_observation_from_files(
            observation,
            args.test_plan,
            args.test_plan_review_evidence,
            args.test_id,
            args.observation_record,
            args.observation_notes,
        )
        digest = write_physical_hardware_test_observation_evidence(evidence, args.out)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(f"functional observation evidence: {args.out}")
    print(f"sha256: {digest}")
    print(f"test: {evidence.test_id}; outcome: {evidence.outcome}; manual review required: true")
    print(f"accepted exact plan review: {evidence.physical_hardware_test_plan_review_sha256}")
    print("hardware/Beta credit: false; persistent write: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
