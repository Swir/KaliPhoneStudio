#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.kernel_build_tree_diagnostics import (
    diagnose_kernel_build_tree,
    write_kernel_build_tree_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare selected intermediate artifacts from two independent kernel build roots. "
            "Diagnostics never relax strict kernel reproducibility acceptance."
        )
    )
    parser.add_argument("--build-a", type=Path, required=True)
    parser.add_argument("--build-b", type=Path, required=True)
    parser.add_argument("--max-differences", type=int, default=256)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    evidence = diagnose_kernel_build_tree(
        args.build_a,
        args.build_b,
        max_differences=args.max_differences,
    )
    digest = write_kernel_build_tree_evidence(evidence, args.out)
    print(
        f"selected={evidence.selected_path_count} "
        f"identical={evidence.identical_path_count} "
        f"different={evidence.differing_path_count} "
        f"reported={evidence.reported_difference_count} "
        f"omitted={evidence.omitted_difference_count}"
    )
    print(f"evidence sha256: {digest}")
    print("hardware/Beta credit: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
