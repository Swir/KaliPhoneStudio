#!/usr/bin/env python3
"""Build a deterministic uncompressed rescue initramfs and canonical evidence."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kaliphonestudio.rescue_initramfs import (  # noqa: E402
    RescueInitramfsError,
    build_reproducible_rescue_initramfs,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Build the same rescue newc archive from two independent source-tree reads, "
            "require byte equality and publish canonical evidence."
        )
    )
    result.add_argument("--source", type=Path, required=True, help="rescue root directory")
    result.add_argument("--out", type=Path, required=True, help="output uncompressed .cpio path")
    result.add_argument("--evidence", type=Path, required=True, help="output canonical JSON evidence")
    result.add_argument(
        "--source-date-epoch",
        type=int,
        default=0,
        help="fixed newc mtime (default: 0)",
    )
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        evidence = build_reproducible_rescue_initramfs(
            args.source,
            args.out,
            args.evidence,
            source_date_epoch=args.source_date_epoch,
        )
    except RescueInitramfsError as exc:
        print(f"rescue initramfs build rejected: {exc}", file=sys.stderr)
        return 2
    print(f"artifact_sha256={evidence.artifact_sha256}")
    print(f"artifact_size={evidence.artifact_size}")
    print(f"source_tree_sha256={evidence.source_tree_sha256}")
    print(f"entry_count={evidence.entry_count}")
    print(f"evidence_sha256={evidence.evidence_sha256()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
