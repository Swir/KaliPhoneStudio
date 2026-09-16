#!/usr/bin/env python3
"""Build a deterministic, non-secret first-boot provisioning overlay offline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from kaliphonestudio.provisioning import (
    build_first_boot_provisioning_bundle,
    create_first_boot_provisioning_plan,
    write_first_boot_provisioning_evidence,
)
from kaliphonestudio.rootfs import RootfsError
from kaliphonestudio.rootfs_canonical_binding import load_rootfs_artifact_evidence


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a deterministic first-boot policy overlay bound to strict ARM64 "
            "rootfs evidence. No credentials are accepted or embedded."
        )
    )
    parser.add_argument("--rootfs-evidence", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path, help="output deterministic tar bundle")
    parser.add_argument("--evidence", required=True, type=Path, help="output canonical bundle evidence JSON")
    parser.add_argument("--hostname", default="kali-phone")
    parser.add_argument("--locale", default="en_US.UTF-8")
    parser.add_argument("--timezone", default="UTC")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        rootfs_evidence = load_rootfs_artifact_evidence(args.rootfs_evidence)
        plan = create_first_boot_provisioning_plan(
            rootfs_evidence,
            hostname=args.hostname,
            locale=args.locale,
            timezone=args.timezone,
        )
        bundle_evidence = build_first_boot_provisioning_bundle(plan, args.out)
        evidence_sha = write_first_boot_provisioning_evidence(bundle_evidence, args.evidence)
    except RootfsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "schema_version": 1,
                "rootfs_evidence_sha256": plan.rootfs_evidence_sha256,
                "provisioning_plan_sha256": plan.plan_sha256(),
                "bundle_sha256": bundle_evidence.bundle_sha256,
                "bundle_size": bundle_evidence.bundle_size,
                "evidence_sha256": evidence_sha,
                "credentials_embedded": False,
                "remote_access_enabled": False,
                "hardware_verified": False,
                "beta_gate_credit": False,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
