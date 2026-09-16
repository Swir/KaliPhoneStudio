#!/usr/bin/env python3
"""Bind a profile-driven kernel checkout to the reviewed compiler source lock."""
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.kernel_contract import create_kernel_build_plan
from kaliphonestudio.kernel_toolchain import load_kernel_toolchain_lock
from kaliphonestudio.kernel_toolchain_binding import bind_kernel_plan_to_toolchain
from kaliphonestudio.profiles import get_profile


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify that an exact kernel checkout selects the locked compiler revision."
    )
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument(
        "--lock",
        type=Path,
        default=ROOT / "tools" / "kernel-toolchain-lock.json",
    )
    parser.add_argument("--build-config", default="build.config.common")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    if args.out.exists():
        parser.error(f"refusing to overwrite existing evidence: {args.out}")

    profile = get_profile(ROOT / "devices", args.profile_id)
    plan = create_kernel_build_plan(profile)
    lock = load_kernel_toolchain_lock(args.lock)
    evidence = bind_kernel_plan_to_toolchain(
        plan,
        lock,
        args.checkout,
        build_config_relative=args.build_config,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.out.with_name(args.out.name + ".tmp")
    if temporary.exists():
        parser.error(f"refusing stale temporary evidence: {temporary}")
    try:
        temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
        temporary.replace(args.out)
    finally:
        if temporary.exists():
            temporary.unlink()

    print(f"verified profile: {evidence.profile_id}")
    print(f"kernel plan sha256: {evidence.kernel_plan_sha256}")
    print(f"toolchain lock sha256: {evidence.toolchain_lock_sha256}")
    print(f"clang revision: {evidence.clang_revision}")
    print(f"evidence sha256: {evidence.evidence_sha256()}")
    print("hardware/Beta credit: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
