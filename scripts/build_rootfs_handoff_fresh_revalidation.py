#!/usr/bin/env python3
"""Build non-executing fresh-device rootfs target revalidation evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from kaliphonestudio.rootfs_handoff_fresh_revalidation import (
    RootfsHandoffFreshRevalidationError,
    build_rootfs_handoff_fresh_revalidation,
    write_rootfs_handoff_fresh_revalidation_evidence,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Offline cross-check of an accepted logical rootfs target binding against a new read-only "
            "physical storage discovery. This does not bind a raw device path, mount, write or execute a trial."
        )
    )
    parser.add_argument("--target-binding", type=Path, required=True)
    parser.add_argument("--fresh-storage-discovery", type=Path, required=True)
    parser.add_argument("--fresh-storage-report", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        evidence = build_rootfs_handoff_fresh_revalidation(
            args.target_binding,
            args.fresh_storage_discovery,
            args.fresh_storage_report,
        )
        digest = write_rootfs_handoff_fresh_revalidation_evidence(evidence, args.out)
    except (RootfsHandoffFreshRevalidationError, OSError) as exc:
        print(f"Fresh target revalidation error: {exc}", file=sys.stderr)
        return 2

    result = {
        "path": str(args.out),
        "sha256": digest,
        "profile_id": evidence.profile_id,
        "device_serial": evidence.device_serial,
        "fresh_device_revalidated": evidence.fresh_device_revalidated,
        "ready_for_separate_manual_trial_authorization": evidence.ready_for_separate_manual_trial_authorization,
        "manual_trial_authorization_required": evidence.manual_trial_authorization_required,
        "raw_device_path_bound": evidence.raw_device_path_bound,
        "mount_target_bound": evidence.mount_target_bound,
        "trial_execution_allowed": evidence.trial_execution_allowed,
        "write_authorized": evidence.write_authorized,
        "hardware_verified": evidence.hardware_verified,
        "beta_release_authorized": evidence.beta_release_authorized,
        "beta_gate_credit": evidence.beta_gate_credit,
    }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"fresh target revalidation: {args.out}")
        print(f"sha256: {digest}")
        print("fresh logical target revalidated: yes")
        print("raw target/mount/trial/write authorization: no")
        print("hardware/Beta authorization: no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
