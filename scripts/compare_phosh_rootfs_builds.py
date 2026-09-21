#!/usr/bin/env python3
"""Compare two real Phosh rootfs build-evidence files without promoting them to authority."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kaliphonestudio.phosh_reproducibility import (  # noqa: E402
    PhoshReproducibilityError,
    compare_phosh_rootfs_builds,
    write_phosh_rootfs_reproducibility_candidate,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Compare two independently produced Phosh ARM64 rootfs build-evidence files. "
            "Success creates review-required reproducibility-candidate evidence only."
        )
    )
    result.add_argument("--build-a", type=Path, required=True)
    result.add_argument("--build-b", type=Path, required=True)
    result.add_argument("--origin-a", required=True)
    result.add_argument("--origin-b", required=True)
    result.add_argument("--out", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    evidence = compare_phosh_rootfs_builds(
        args.build_a,
        args.build_b,
        build_a_origin=args.origin_a,
        build_b_origin=args.origin_b,
    )
    digest = write_phosh_rootfs_reproducibility_candidate(evidence, args.out)
    print(f"artifact_sha256={evidence.artifact_sha256}")
    print(f"artifact_size={evidence.artifact_size}")
    print(f"package_manifest_sha256={evidence.package_manifest_sha256}")
    print(f"package_count={evidence.package_count}")
    print("strict_byte_identical=true")
    print("package_manifest_identical=true")
    print("review_required=true")
    print("reproducibility_authority=false")
    print("hardware_verified=false")
    print("beta_gate_credit=false")
    print(f"reproducibility_candidate_sha256={digest}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PhoshReproducibilityError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
