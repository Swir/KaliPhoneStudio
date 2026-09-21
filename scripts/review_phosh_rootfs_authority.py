#!/usr/bin/env python3
"""Explicitly promote a reviewed Phosh A/B rootfs packet to host authority."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kaliphonestudio.phosh_rootfs_authority import (  # noqa: E402
    build_reviewed_phosh_rootfs_authority,
    load_and_verify_phosh_rootfs_authority,
    load_phosh_rootfs_review_packet,
    write_phosh_rootfs_authority,
)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--review-packet", type=Path, required=True)
    p.add_argument("--authority-name", required=True)
    p.add_argument("--authority-run-id", type=int, required=True)
    p.add_argument("--authority-commit", required=True)
    p.add_argument("--authority-artifact-id", type=int, required=True)
    p.add_argument("--reviewed", action="store_true", help="explicitly confirm completed evidence review")
    p.add_argument("--out", type=Path, required=True)
    return p


def main() -> int:
    args = parser().parse_args()
    if not args.reviewed:
        raise SystemExit("refusing Phosh rootfs authority creation without explicit --reviewed")
    if args.out.exists() or args.out.is_symlink():
        raise SystemExit(f"refusing to overwrite existing authority: {args.out}")
    staged = args.out.with_name(args.out.name + ".reviewing")
    if staged.exists() or staged.is_symlink():
        raise SystemExit(f"refusing stale Phosh authority staging path: {staged}")

    packet = load_phosh_rootfs_review_packet(args.review_packet)
    authority = build_reviewed_phosh_rootfs_authority(
        review_packet=packet,
        authority_name=args.authority_name,
        authority_run_id=args.authority_run_id,
        authority_commit=args.authority_commit,
        authority_artifact_id=args.authority_artifact_id,
        reviewed=True,
    )
    try:
        digest = write_phosh_rootfs_authority(authority, staged)
        verified = load_and_verify_phosh_rootfs_authority(staged, args.review_packet)
        if verified.authority_sha256() != digest:
            raise SystemExit("Phosh rootfs authority round-trip digest mismatch")
        if args.out.exists() or args.out.is_symlink():
            raise SystemExit(f"authority destination appeared during review: {args.out}")
        staged.replace(args.out)
    finally:
        staged.unlink(missing_ok=True)

    print(json.dumps({
        "authority_name": verified.authority_name,
        "authority_sha256": digest,
        "authority_run_id": verified.authority_run_id,
        "authority_commit": verified.authority_commit,
        "authority_artifact_id": verified.authority_artifact_id,
        "rootfs_artifact_sha256": verified.rootfs_artifact_sha256,
        "package_manifest_sha256": verified.package_manifest_sha256,
        "reviewed": verified.reviewed,
        "reproducibility_authority": verified.reproducibility_authority,
        "ready_for_first_boot_binding": verified.ready_for_first_boot_binding,
        "hardware_verified": verified.hardware_verified,
        "beta_gate_credit": verified.beta_gate_credit,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
