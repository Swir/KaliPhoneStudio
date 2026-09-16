#!/usr/bin/env python3
"""Build a deterministic rescue initramfs without touching a phone."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kaliphonestudio.initramfs import (  # noqa: E402
    build_reproducible_initramfs,
    write_initramfs_evidence,
)
from kaliphonestudio.profiles import ProfileError, get_profile  # noqa: E402


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Build a deterministic newc rescue initramfs from a prepared staging tree. "
            "Compression can be selected explicitly or derived from a device profile."
        )
    )
    result.add_argument("--staging", type=Path, required=True)
    result.add_argument("--out", type=Path, required=True)
    result.add_argument("--evidence", type=Path, required=True)
    result.add_argument("--compression", choices=("gzip", "lz4"))
    result.add_argument("--profile-id", help="derive ramdisk compression from devices/<vendor>/<codename>/profile.json")
    result.add_argument("--profiles-root", type=Path, default=ROOT / "devices")
    return result


def _resolve_compression(args: argparse.Namespace) -> tuple[str, str | None]:
    if not args.profile_id:
        return args.compression or "gzip", None
    profile = get_profile(args.profiles_root, args.profile_id)
    value = profile.data.get("boot", {}).get("ramdisk_compression")
    if value not in {"gzip", "lz4"}:
        raise ProfileError(f"profile {profile.profile_id} uses unsupported rescue ramdisk compression: {value!r}")
    if args.compression is not None and args.compression != value:
        raise ProfileError(
            f"explicit compression {args.compression!r} conflicts with profile {profile.profile_id} policy {value!r}"
        )
    return value, profile.profile_id


def main() -> int:
    args = parser().parse_args()
    compression, profile_id = _resolve_compression(args)
    evidence = build_reproducible_initramfs(args.staging, args.out, compression=compression)
    evidence_digest = write_initramfs_evidence(evidence, args.evidence)
    if profile_id is not None:
        print(f"profile_id={profile_id}")
    print(f"compression={evidence.compression}")
    print(f"initramfs_sha256={evidence.artifact_sha256}")
    print(f"initramfs_size={evidence.artifact_size}")
    print(f"entry_count={evidence.entry_count}")
    print(f"evidence_sha256={evidence_digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
