#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.kernel_toolchain import load_kernel_toolchain_lock, write_evidence
from kaliphonestudio.kernel_toolchain_checkout import capture_local_git_source_evidence


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify an already-fetched source-locked Android Clang checkout by local Git object identity."
    )
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    lock = load_kernel_toolchain_lock(args.lock)
    evidence = capture_local_git_source_evidence(lock, args.repository)
    digest = write_evidence(evidence, args.out)
    print(f"verified local Git checkout {lock.name}: {lock.source_commit}/{lock.tree_sha1}")
    print(f"evidence sha256: {digest}")
    print("hardware/Beta credit: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
