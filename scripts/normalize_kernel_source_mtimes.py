#!/usr/bin/env python3
"""Normalize one exact kernel checkout's tracked mtimes without touching a phone."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kaliphonestudio.kernel_source_normalization import (  # noqa: E402
    DEFAULT_SOURCE_MTIME_EPOCH,
    normalize_kernel_checkout_mtimes,
    write_kernel_source_mtime_evidence,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize Git-tracked kernel source mtimes to a deterministic epoch after "
            "verifying the exact clean source commit. No ADB/Fastboot command is executed."
        )
    )
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--epoch", type=int, default=DEFAULT_SOURCE_MTIME_EPOCH)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    evidence = normalize_kernel_checkout_mtimes(
        args.checkout,
        args.expected_commit,
        epoch=args.epoch,
    )
    digest = write_kernel_source_mtime_evidence(evidence, args.out)
    print(evidence.canonical_json(), end="")
    print(f"kernel source mtime evidence sha256: {digest}")
    print("hardware/Beta gate credit: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
