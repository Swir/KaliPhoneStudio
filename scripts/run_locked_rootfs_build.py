#!/usr/bin/env python3
"""Run the exact locked Kali ARM64 rootfs builder and publish one validated artifact."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess

from kaliphonestudio.rootfs import RootfsError, load_rootfs_source_lock, package_manifest_from_rootfs


def _git_output(checkout: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(checkout), *args],
            check=True,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise RootfsError(f"cannot inspect rootfs builder checkout: {exc}") from exc
    return result.stdout.strip()


def _find_rootfs_artifact(checkout: Path, architecture: str) -> Path:
    candidates = []
    for path in checkout.rglob("*.tar.xz"):
        if ".git" in path.parts or architecture not in path.name.lower():
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size >= 16 * 1024 * 1024:
            candidates.append(path)
    if len(candidates) != 1:
        details = ", ".join(str(path.relative_to(checkout)) for path in candidates) or "none"
        raise RootfsError(f"expected exactly one ARM64 rootfs tar.xz artifact, found: {details}")
    return candidates[0]


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Execute the pinned rootfs builder from an exact checkout without a shell."
    )
    result.add_argument("--lock", type=Path, required=True)
    result.add_argument("--checkout", type=Path, required=True)
    result.add_argument("--out", type=Path, required=True)
    result.add_argument("--sudo", action="store_true", help="prefix the locked builder argv with sudo --")
    result.add_argument("--timeout", type=int, default=5400)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.timeout <= 0:
        raise RootfsError("rootfs build timeout must be positive")
    lock = load_rootfs_source_lock(args.lock)
    checkout = args.checkout.resolve()
    if not checkout.is_dir():
        raise RootfsError("rootfs builder checkout directory does not exist")
    head = _git_output(checkout, "rev-parse", "HEAD")
    if head != lock.source_commit:
        raise RootfsError(f"rootfs builder checkout is not the locked commit: {head}")
    if not (checkout / "build-fs.sh").is_file():
        raise RootfsError("locked rootfs builder entrypoint is missing")

    argv = list(lock.command)
    if args.sudo:
        argv = ["sudo", "--", *argv]
    try:
        subprocess.run(
            argv,
            cwd=checkout,
            check=True,
            shell=False,
            timeout=args.timeout,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise RootfsError(f"locked rootfs builder failed: {exc}") from exc

    artifact = _find_rootfs_artifact(checkout, lock.architecture)
    _, package_count = package_manifest_from_rootfs(artifact)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists():
        raise RootfsError("refusing to overwrite an existing rootfs output artifact")
    shutil.copyfile(artifact, args.out)
    print(f"source_artifact={artifact}")
    print(f"package_count={package_count}")
    print(f"published_artifact={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
