#!/usr/bin/env python3
"""Build one immutable Phosh successor first-boot candidate from reviewed host evidence."""
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.phosh_successor_candidate import (
    PhoshSuccessorCandidateError,
    build_phosh_successor_candidate_from_paths,
    write_phosh_successor_candidate,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Host-only: bind an exact schema-v8 base first-boot candidate and reviewed "
            "Phosh regeneration binding into an immutable successor candidate. "
            "No device I/O or Beta authorization is performed."
        )
    )
    parser.add_argument("--base-first-boot-manifest", type=Path, required=True)
    parser.add_argument("--base-authority-bundle", type=Path, required=True)
    parser.add_argument("--phosh-first-boot-binding", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    try:
        evidence = build_phosh_successor_candidate_from_paths(
            args.base_first_boot_manifest,
            args.base_authority_bundle,
            args.phosh_first_boot_binding,
        )
        digest = write_phosh_successor_candidate(evidence, args.out)
    except (PhoshSuccessorCandidateError, OSError) as exc:
        parser.error(str(exc))

    print(evidence.canonical_json(), end="")
    print(f"phosh successor first-boot candidate sha256={digest}")
    print("physical_validation_required=true")
    print("display_verified=false")
    print("touch_verified=false")
    print("hardware/Beta credit=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
