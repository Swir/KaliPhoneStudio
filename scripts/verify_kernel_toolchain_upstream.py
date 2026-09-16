#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.kernel_toolchain import (
    capture_gitiles_source_evidence,
    load_kernel_toolchain_lock,
    write_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the exact source-locked Android Clang metadata through Gitiles."
    )
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    lock = load_kernel_toolchain_lock(args.lock)
    evidence = capture_gitiles_source_evidence(lock)
    digest = write_evidence(evidence, args.out)
    print(f"verified {lock.name}: {lock.source_commit}/{lock.tree_sha1}")
    print(f"evidence sha256: {digest}")
    print("hardware/Beta credit: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
