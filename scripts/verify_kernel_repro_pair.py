#!/usr/bin/env python3
"""Verify two profile-driven kernel build roots without touching a phone."""
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.kernel_contract import create_kernel_build_plan
from kaliphonestudio.kernel_repro import (
    verify_kernel_reproducibility,
    write_kernel_reproducibility_evidence,
)
from kaliphonestudio.profiles import get_profile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare final .config and ARM64 Image bytes from two distinct build roots "
            "against one exact device profile/kernel plan. No ADB/Fastboot command is run."
        )
    )
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--profile-root", type=Path, default=Path("devices"))
    parser.add_argument("--build-a", type=Path, required=True)
    parser.add_argument("--build-b", type=Path, required=True)
    parser.add_argument("--config-relative", default=".config")
    parser.add_argument("--image-relative")
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    profile = get_profile(args.profile_root, args.profile_id)
    plan = create_kernel_build_plan(profile)
    evidence = verify_kernel_reproducibility(
        plan,
        build_a=args.build_a,
        build_b=args.build_b,
        config_relative=args.config_relative,
        image_relative=args.image_relative,
    )
    digest = write_kernel_reproducibility_evidence(evidence, args.out)
    print(evidence.canonical_json(), end="")
    print(f"kernel reproducibility evidence sha256: {digest}")
    print("hardware/Beta gate credit: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
