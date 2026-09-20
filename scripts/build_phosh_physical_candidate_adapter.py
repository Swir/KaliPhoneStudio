#!/usr/bin/env python3
"""Build one host-only Phosh successor-to-physical-candidate adapter record."""
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.phosh_physical_candidate_adapter import (
    PhoshPhysicalCandidateAdapterError,
    build_phosh_physical_candidate_adapter_from_paths,
    write_phosh_physical_candidate_adapter,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Host-only: bind one reviewed Phosh successor candidate to one exact "
            "physical-candidate gate for the same phone/firmware/boot chain. "
            "This does not stage rootfs, run Fastboot, authorize temporary boot, "
            "write phone storage, verify hardware, or grant Beta credit."
        )
    )
    parser.add_argument("--phosh-successor-candidate", type=Path, required=True)
    parser.add_argument("--physical-candidate-gate", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    try:
        evidence = build_phosh_physical_candidate_adapter_from_paths(
            args.phosh_successor_candidate,
            args.physical_candidate_gate,
        )
        digest = write_phosh_physical_candidate_adapter(evidence, args.out)
    except (PhoshPhysicalCandidateAdapterError, OSError) as exc:
        parser.error(str(exc))

    print(evidence.canonical_json(), end="")
    print(f"phosh physical-candidate adapter sha256={digest}")
    print("ready_for_physical_staging_review=true")
    print("staging_target_selected=false")
    print("rootfs_staged=false")
    print("temporary_boot_authorized=false")
    print("phone_storage_written=false")
    print("hardware/Beta credit=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
