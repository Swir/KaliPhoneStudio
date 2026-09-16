#!/usr/bin/env python3
"""Bind rootfs canonicalization A/B audit records to strict artifact evidence."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kaliphonestudio.rootfs import load_repository_snapshot, load_rootfs_source_lock  # noqa: E402
from kaliphonestudio.rootfs_canonical_binding import (  # noqa: E402
    create_rootfs_canonicalization_binding,
    load_canonicalization_evidence,
    load_rootfs_artifact_evidence,
    write_rootfs_canonicalization_binding,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Bind canonicalization provenance for two independently built rootfs artifacts."
    )
    result.add_argument("--lock", type=Path, required=True)
    result.add_argument("--snapshot", type=Path, required=True)
    result.add_argument("--rootfs-evidence", type=Path, required=True)
    result.add_argument("--artifact", type=Path, required=True)
    result.add_argument("--canonical-a", type=Path, required=True)
    result.add_argument("--canonical-b", type=Path, required=True)
    result.add_argument("--out", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    lock = load_rootfs_source_lock(args.lock)
    snapshot = load_repository_snapshot(args.snapshot)
    rootfs_evidence = load_rootfs_artifact_evidence(args.rootfs_evidence)
    canonical_a = load_canonicalization_evidence(args.canonical_a)
    canonical_b = load_canonicalization_evidence(args.canonical_b)
    binding = create_rootfs_canonicalization_binding(
        lock,
        snapshot,
        rootfs_evidence,
        artifact=args.artifact,
        canonical_a=canonical_a,
        canonical_b=canonical_b,
    )
    digest = write_rootfs_canonicalization_binding(binding, args.out)
    print(f"canonicalization_policy_sha256={binding.canonicalization_policy_sha256}")
    print(f"canonicalization_a_evidence_sha256={binding.canonicalization_a_evidence_sha256}")
    print(f"canonicalization_b_evidence_sha256={binding.canonicalization_b_evidence_sha256}")
    print(f"rootfs_evidence_sha256={binding.rootfs_evidence_sha256}")
    print(f"binding_evidence_sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
