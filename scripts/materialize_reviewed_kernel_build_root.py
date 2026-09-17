#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.kernel_authority import load_kernel_authority
from kaliphonestudio.kernel_authority_materialization import (
    materialize_reviewed_kernel_build_root,
    write_reviewed_kernel_build_root_evidence,
)
from kaliphonestudio.kernel_contract import create_kernel_build_plan
from kaliphonestudio.kernel_toolchain import load_kernel_toolchain_lock
from kaliphonestudio.profiles import get_profile


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Rehydrate only the exact reviewed kernel .config around an already accepted "
            "Image; no kernel Image build and no device I/O are performed."
        )
    )
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--devices-dir", type=Path, default=Path("devices"))
    parser.add_argument("--toolchain-lock", type=Path, required=True)
    parser.add_argument("--kernel-authority", type=Path, required=True)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--toolchain-root", type=Path, required=True)
    parser.add_argument("--build-root", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    profile = get_profile(args.devices_dir, args.profile_id)
    plan = create_kernel_build_plan(profile)
    lock = load_kernel_toolchain_lock(args.toolchain_lock)
    authority = load_kernel_authority(args.kernel_authority)
    evidence = materialize_reviewed_kernel_build_root(
        plan,
        lock,
        authority,
        checkout=args.checkout,
        toolchain_root=args.toolchain_root,
        output_root=args.build_root,
        jobs=args.jobs,
    )
    digest = write_reviewed_kernel_build_root_evidence(evidence, args.out)
    print(evidence.canonical_json(), end="")
    print(f"reviewed kernel build-root evidence sha256={digest}")
    print("hardware/Beta credit: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
