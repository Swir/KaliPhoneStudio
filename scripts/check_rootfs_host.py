#!/usr/bin/env python3
"""Validate the Linux host prerequisites for a pinned ARM64 rootfs build."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kaliphonestudio.rootfs import RootfsError, load_rootfs_source_lock  # noqa: E402
from kaliphonestudio.rootfs_host import preflight_rootfs_host  # noqa: E402


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Fail-closed ARM64 rootfs host preflight")
    result.add_argument("--lock", type=Path, required=True)
    result.add_argument(
        "--binfmt",
        type=Path,
        default=Path("/proc/sys/fs/binfmt_misc/qemu-aarch64"),
    )
    result.add_argument(
        "--keyring",
        type=Path,
        default=Path("/usr/share/keyrings/kali-archive-keyring.gpg"),
    )
    return result


def main() -> int:
    args = parser().parse_args()
    lock = load_rootfs_source_lock(args.lock)
    status = preflight_rootfs_host(lock, binfmt_path=args.binfmt, keyring_path=args.keyring)
    print(f"binfmt_interpreter={status.interpreter}")
    print(f"binfmt_flags={status.flags}")
    print(f"archive_key_fingerprint={lock.archive_key_fingerprint}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RootfsError as exc:
        print(f"rootfs host preflight failed: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
