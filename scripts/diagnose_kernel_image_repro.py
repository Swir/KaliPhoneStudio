#!/usr/bin/env python3
"""Diagnose two strict kernel Image candidates without relaxing acceptance."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kaliphonestudio.kernel_repro_diagnostics import (  # noqa: E402
    diagnose_kernel_image_divergence,
    write_kernel_image_divergence_evidence,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare two kernel Image files byte-for-byte and emit bounded non-release "
            "diagnostic evidence. This never grants reproducibility/Beta credit."
        )
    )
    parser.add_argument("--image-a", type=Path, required=True)
    parser.add_argument("--image-b", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-ranges", type=int, default=128)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    evidence = diagnose_kernel_image_divergence(
        args.image_a,
        args.image_b,
        max_ranges=args.max_ranges,
    )
    digest = write_kernel_image_divergence_evidence(evidence, args.out)
    print(evidence.canonical_json(), end="")
    print(f"kernel divergence diagnostic sha256: {digest}")
    print("hardware/Beta gate credit: false")
    # Diagnostics are informational. A mismatch is expected when this tool is used
    # after the strict verifier; do not turn the diagnostic step itself into a second
    # CI failure that could hide the original acceptance error.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
