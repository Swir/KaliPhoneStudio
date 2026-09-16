#!/usr/bin/env python3
"""Bind strict two-build kernel equality to exact executed build evidence."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kaliphonestudio.kernel_build_binding import (  # noqa: E402
    bind_kernel_reproducibility_to_build_runs,
    load_kernel_build_run_evidence,
    load_kernel_reproducibility_evidence,
    write_kernel_reproducibility_binding_evidence,
)
from kaliphonestudio.kernel_contract import create_kernel_build_plan  # noqa: E402
from kaliphonestudio.kernel_toolchain import load_kernel_toolchain_lock  # noqa: E402
from kaliphonestudio.profiles import get_profile  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--profile-root", type=Path, default=ROOT / "devices")
    parser.add_argument("--toolchain-lock", type=Path, default=ROOT / "tools" / "kernel-toolchain-lock.json")
    parser.add_argument("--repro-evidence", type=Path, required=True)
    parser.add_argument("--build-evidence-a", type=Path, required=True)
    parser.add_argument("--build-evidence-b", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    if args.out.exists():
        parser.error(f"refusing to overwrite existing evidence: {args.out}")
    plan = create_kernel_build_plan(get_profile(args.profile_root, args.profile_id))
    lock = load_kernel_toolchain_lock(args.toolchain_lock)
    reproducibility = load_kernel_reproducibility_evidence(args.repro_evidence)
    build_a = load_kernel_build_run_evidence(args.build_evidence_a)
    build_b = load_kernel_build_run_evidence(args.build_evidence_b)
    evidence = bind_kernel_reproducibility_to_build_runs(plan, lock, reproducibility, build_a, build_b)
    digest = write_kernel_reproducibility_binding_evidence(evidence, args.out)
    print(evidence.canonical_json(), end="")
    print(f"kernel reproducibility binding evidence sha256: {digest}")
    print("hardware/Beta gate credit: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
