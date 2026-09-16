#!/usr/bin/env python3
"""Run one exact profile-driven kernel build without touching a phone."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kaliphonestudio.kernel_build_runner import (  # noqa: E402
    execute_kernel_build,
    write_kernel_build_run_evidence,
)
from kaliphonestudio.kernel_contract import create_kernel_build_plan  # noqa: E402
from kaliphonestudio.kernel_toolchain import load_kernel_toolchain_lock  # noqa: E402
from kaliphonestudio.profiles import get_profile  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a source-locked kernel into an empty out-of-tree directory using the "
            "profile-selected exact compiler. No ADB/Fastboot command is executed."
        )
    )
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--profile-root", type=Path, default=ROOT / "devices")
    parser.add_argument(
        "--toolchain-lock",
        type=Path,
        default=ROOT / "tools" / "kernel-toolchain-lock.json",
    )
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--toolchain-root", type=Path, required=True)
    parser.add_argument("--build-root", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--build-config", default="build.config.common")
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    profile = get_profile(args.profile_root, args.profile_id)
    plan = create_kernel_build_plan(profile)
    lock = load_kernel_toolchain_lock(args.toolchain_lock)
    evidence = execute_kernel_build(
        plan,
        lock,
        checkout=args.checkout,
        toolchain_root=args.toolchain_root,
        output_root=args.build_root,
        jobs=args.jobs,
        build_config_relative=args.build_config,
    )
    digest = write_kernel_build_run_evidence(evidence, args.out)
    print(evidence.canonical_json(), end="")
    print(f"kernel build-run evidence sha256: {digest}")
    print("hardware/Beta gate credit: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
