#!/usr/bin/env python3
"""Build a deterministic rescue initramfs without touching a phone."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kaliphonestudio.initramfs import (  # noqa: E402
    build_reproducible_initramfs,
    write_initramfs_evidence,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Build a deterministic gzip/newc rescue initramfs from a prepared staging tree."
    )
    result.add_argument("--staging", type=Path, required=True)
    result.add_argument("--out", type=Path, required=True)
    result.add_argument("--evidence", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    evidence = build_reproducible_initramfs(args.staging, args.out)
    evidence_digest = write_initramfs_evidence(evidence, args.evidence)
    print(f"initramfs_sha256={evidence.artifact_sha256}")
    print(f"initramfs_size={evidence.artifact_size}")
    print(f"entry_count={evidence.entry_count}")
    print(f"evidence_sha256={evidence_digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
