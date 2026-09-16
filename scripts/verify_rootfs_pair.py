#!/usr/bin/env python3
"""Emit KaliPhoneStudio rootfs reproducibility evidence for two completed builds."""
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.rootfs import (
    create_reproducible_rootfs_evidence,
    load_repository_snapshot,
    load_rootfs_source_lock,
    write_rootfs_artifact_evidence,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Verify two rootfs artifacts are byte-identical and bind them to locked source/repository evidence."
    )
    result.add_argument("--lock", type=Path, required=True, help="rootfs source-lock JSON")
    result.add_argument("--snapshot", type=Path, required=True, help="repository snapshot evidence JSON")
    result.add_argument("--first", type=Path, required=True, help="first independently built rootfs artifact")
    result.add_argument("--second", type=Path, required=True, help="second independently built rootfs artifact")
    result.add_argument("--out", type=Path, required=True, help="destination evidence JSON")
    return result


def main() -> int:
    args = parser().parse_args()
    lock = load_rootfs_source_lock(args.lock)
    snapshot = load_repository_snapshot(args.snapshot)
    evidence = create_reproducible_rootfs_evidence(
        lock,
        snapshot,
        first_artifact=args.first,
        second_artifact=args.second,
    )
    evidence_digest = write_rootfs_artifact_evidence(evidence, args.out)
    print(f"rootfs_sha256={evidence.artifact_sha256}")
    print(f"rootfs_size={evidence.artifact_size}")
    print(f"evidence_sha256={evidence_digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
