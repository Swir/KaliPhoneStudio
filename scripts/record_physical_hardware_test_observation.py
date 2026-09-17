#!/usr/bin/env python3
"""Bind one actually executed physical functional-test observation to the exact plan."""
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.physical_hardware_test_observation import (
    bind_physical_hardware_test_observation_from_files,
    write_physical_hardware_test_observation_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-plan", type=Path, required=True)
    parser.add_argument("--test-id", required=True)
    parser.add_argument("--observation-record", type=Path, required=True)
    parser.add_argument("--observation-notes", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        evidence = bind_physical_hardware_test_observation_from_files(
            args.test_plan,
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
    print("hardware/Beta credit: false; persistent write: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
