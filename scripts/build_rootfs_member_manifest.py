#!/usr/bin/env python3
"""Create a diagnostic-only member manifest for one canonical rootfs archive."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kaliphonestudio.rootfs import RootfsError  # noqa: E402
from kaliphonestudio.rootfs_member_manifest import (  # noqa: E402
    build_rootfs_member_manifest,
    write_rootfs_member_manifest,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Create an exact member-level manifest from a canonical rootfs archive. "
            "Diagnostic-only; grants no authority, hardware or Beta credit."
        )
    )
    result.add_argument("--rootfs", type=Path, required=True)
    result.add_argument("--out", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    manifest = build_rootfs_member_manifest(args.rootfs)
    digest = write_rootfs_member_manifest(manifest, args.out)
    print(f"artifact_sha256={manifest.artifact_sha256}")
    print(f"artifact_size={manifest.artifact_size}")
    print(f"member_count={manifest.member_count}")
    print(f"member_manifest_sha256={digest}")
    print("diagnostic_only=true")
    print("reproducibility_authority=false")
    print("hardware_verified=false")
    print("beta_gate_credit=false")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RootfsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
