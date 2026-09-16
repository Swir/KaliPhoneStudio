#!/usr/bin/env python3
"""Verify that the live Kali repository still matches one captured signed snapshot.

This is a pair-level start gate for reproducibility builds.  It intentionally runs
once immediately before both independent builders are launched together.  Each
builder then validates the exact captured InRelease bytes locally, avoiding the
false failure where a rolling repository advances during the first hour-long
build and prevents the second build from even starting.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kaliphonestudio.rootfs import (  # noqa: E402
    RootfsError,
    load_repository_snapshot,
    load_rootfs_source_lock,
    validate_repository_snapshot,
)


def verify_captured_inrelease(lock, snapshot_path: Path, inrelease_path: Path) -> str:
    """Validate the captured raw InRelease against canonical snapshot evidence."""
    snapshot = load_repository_snapshot(snapshot_path)
    validate_repository_snapshot(lock, snapshot)
    if not inrelease_path.is_file():
        raise RootfsError("captured Kali InRelease file is missing")
    payload = inrelease_path.read_bytes()
    if not payload or len(payload) > 16 * 1024 * 1024:
        raise RootfsError("captured Kali InRelease is empty or unreasonably large")
    digest = sha256(payload).hexdigest()
    if digest != snapshot.inrelease_sha256:
        raise RootfsError("captured Kali InRelease does not match repository snapshot evidence")
    return digest


def verify_live_snapshot(lock, snapshot_path: Path, inrelease_path: Path) -> str:
    """Require the live mirror to equal the already GPG-verified captured state."""
    expected = verify_captured_inrelease(lock, snapshot_path, inrelease_path)
    url = f"{lock.mirror.rstrip('/')}/dists/{lock.suite}/InRelease"
    try:
        result = subprocess.run(
            [
                "curl", "--fail", "--location", "--silent", "--show-error",
                "--proto", "=https", "--tlsv1.2", url,
            ],
            check=True,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise RootfsError(f"cannot revalidate locked Kali repository snapshot: {exc}") from exc
    actual = sha256(result.stdout).hexdigest()
    if actual != expected:
        raise RootfsError(
            "Kali repository InRelease changed after signed snapshot capture; "
            "refusing to start the reproducibility pair"
        )
    return actual


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Fail closed unless the live Kali InRelease equals captured signed evidence."
    )
    result.add_argument("--lock", type=Path, required=True)
    result.add_argument("--snapshot", type=Path, required=True)
    result.add_argument("--inrelease", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    lock = load_rootfs_source_lock(args.lock)
    digest = verify_live_snapshot(lock, args.snapshot, args.inrelease)
    print(f"pair_start_inrelease_sha256={digest}")
    print("pair_start_gate=verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
