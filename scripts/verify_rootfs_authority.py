#!/usr/bin/env python3
"""Verify a checked-in reviewed rootfs authority against downloaded CI evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kaliphonestudio.rootfs_authority import load_and_verify_rootfs_authority


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authority", type=Path, required=True)
    parser.add_argument("--rootfs-evidence", type=Path, required=True)
    parser.add_argument("--canonicalization-binding", type=Path, required=True)
    parser.add_argument("--repository-snapshot", type=Path, required=True)
    args = parser.parse_args()

    authority = load_and_verify_rootfs_authority(
        args.authority,
        args.rootfs_evidence,
        args.canonicalization_binding,
        args.repository_snapshot,
    )
    print(json.dumps({
        "authority_name": authority.authority_name,
        "authority_sha256": authority.authority_sha256(),
        "authority_run_id": authority.authority_run_id,
        "artifact_sha256": authority.artifact_sha256,
        "artifact_size": authority.artifact_size,
        "package_count": authority.package_count,
        "strict_byte_identical": authority.strict_byte_identical,
        "reviewed": authority.reviewed,
        "hardware_verified": authority.hardware_verified,
        "beta_gate_credit": authority.beta_gate_credit,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
