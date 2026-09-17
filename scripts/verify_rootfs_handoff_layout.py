#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.profiles import get_profile
from kaliphonestudio.rootfs_handoff import (
    RootfsHandoffError,
    verify_rootfs_handoff_layout_checkout,
    write_rootfs_handoff_source_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the exact source-pinned rootfs handoff layout file for one device profile"
    )
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--devices-root", type=Path, default=Path("devices"))
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        profile = get_profile(args.devices_root, args.profile_id)
        evidence = verify_rootfs_handoff_layout_checkout(profile, args.checkout)
        digest = write_rootfs_handoff_source_evidence(evidence, args.out)
    except RootfsHandoffError as exc:
        parser.error(str(exc))
    print(evidence.canonical_json(), end="")
    print(f"rootfs handoff source evidence sha256={digest}")
    print("hardware/Beta credit: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
