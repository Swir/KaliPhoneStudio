#!/usr/bin/env python3
"""Run the exact locked Kali ARM64 rootfs builder and publish one validated artifact."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kaliphonestudio.rootfs import (  # noqa: E402
    RootfsError,
    load_rootfs_source_lock,
    package_manifest_from_rootfs,
)
from kaliphonestudio.rootfs_host import preflight_rootfs_host  # noqa: E402


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


def _assert_tracked_checkout_clean(checkout: Path) -> None:
    dirty = _git_output(checkout, "status", "--porcelain", "--untracked-files=no")
    if dirty:
        raise RootfsError("rootfs builder checkout has modified tracked files")


def _create_dependency_guard(checkout: Path, lock_sha256: str) -> Path:
    """Create the upstream dependency sentinel only after KPS preflight succeeded.

    The pinned 2026.2 builder checks for qemu-user/qemu-user-binfmt and would
    replace qemu-user-static on Ubuntu 24.04. Its ARM64 chroot path, however,
    needs a persistent static interpreter. We therefore skip *only* the upstream
    package mutator after KaliPhoneStudio independently verified the host.
    """
    marker = checkout / ".dep_check"
    if marker.exists() or marker.is_symlink():
        raise RootfsError("refusing prevalidated build: dependency guard already exists")
    marker.write_text(
        f"kaliphonestudio-prevalidated-static-qemu\nsource_lock_sha256={lock_sha256}\n",
        encoding="utf-8",
    )
    return marker


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Execute the pinned rootfs builder from an exact checkout without a shell."
    )
    result.add_argument("--lock", type=Path, required=True)
    result.add_argument("--checkout", type=Path, required=True)
    result.add_argument("--out", type=Path, required=True)
    result.add_argument("--sudo", action="store_true", help="prefix the locked builder argv with sudo --")
    result.add_argument(
        "--host-deps-prevalidated",
        action="store_true",
        help=(
            "after fail-closed static-QEMU/keyring/binfmt preflight, create the pinned "
            "builder's dependency sentinel so it cannot replace the verified QEMU runtime"
        ),
    )
    result.add_argument("--timeout", type=int, default=5400)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.timeout <= 0:
        raise RootfsError("rootfs build timeout must be positive")
    if args.host_deps_prevalidated and not args.sudo:
        raise RootfsError("prevalidated cross-architecture rootfs builds require --sudo")

    lock = load_rootfs_source_lock(args.lock)
    checkout = args.checkout.resolve()
    if not checkout.is_dir():
        raise RootfsError("rootfs builder checkout directory does not exist")
    head = _git_output(checkout, "rev-parse", "HEAD")
    if head != lock.source_commit:
        raise RootfsError(f"rootfs builder checkout is not the locked commit: {head}")
    if not (checkout / "build-fs.sh").is_file():
        raise RootfsError("locked rootfs builder entrypoint is missing")
    _assert_tracked_checkout_clean(checkout)

    dependency_guard: Path | None = None
    if args.host_deps_prevalidated:
        preflight_rootfs_host(lock)
        dependency_guard = _create_dependency_guard(checkout, lock.lock_sha256())

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
    finally:
        if dependency_guard is not None:
            try:
                dependency_guard.unlink(missing_ok=True)
            except OSError as exc:
                raise RootfsError(f"cannot remove rootfs dependency guard: {exc}") from exc

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
