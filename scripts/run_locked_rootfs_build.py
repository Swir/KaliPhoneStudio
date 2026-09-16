#!/usr/bin/env python3
"""Run the exact locked Kali ARM64 rootfs builder and publish one validated artifact."""
from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kaliphonestudio.rootfs import (  # noqa: E402
    RootfsError,
    load_repository_snapshot,
    load_rootfs_source_lock,
    package_manifest_from_rootfs,
    validate_repository_snapshot,
)

_DEP_CHECK_MARKER = "KaliPhoneStudio: host dependencies preflighted; preserve qemu-user-static\n"
_REQUIRED_HOST_TOOLS = (
    "curl",
    "debootstrap",
    "git",
    "qemu-aarch64-static",
    "update-binfmts",
    "xz",
)


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


def _prepare_host_environment(checkout: Path) -> Path:
    """Fail closed unless the host has the static ARM64 emulation path we need.

    The pinned upstream builder performs a Debian-package-name dependency check. On
    Ubuntu 24.04 that check installs qemu-user/qemu-user-binfmt and removes
    qemu-user-static. Its copied ARM64 interpreter then becomes dynamically linked
    and the debootstrap second stage cannot enter chroot. We validate the actual
    executables ourselves and create upstream's untracked .dep_check sentinel so it
    cannot replace the already validated static emulator.
    """
    if _git_output(checkout, "status", "--porcelain", "--untracked-files=no"):
        raise RootfsError("rootfs builder checkout has tracked modifications before build")

    for tool in _REQUIRED_HOST_TOOLS:
        value = shutil.which(tool)
        if not value:
            raise RootfsError(f"required rootfs host tool is missing: {tool}")
        if not Path(value).resolve().is_file():
            raise RootfsError(f"rootfs host tool is not a regular file: {tool}")

    # A dynamic qemu-aarch64 can take precedence in the pinned upstream helper.
    # Refuse that ambiguous state instead of falling back from qemu-aarch64-static.
    dynamic_qemu = shutil.which("qemu-aarch64")
    if dynamic_qemu:
        raise RootfsError(
            "dynamic qemu-aarch64 is present; refusing host state that can replace qemu-aarch64-static"
        )

    sentinel = checkout / ".dep_check"
    if sentinel.exists():
        raise RootfsError("unexpected pre-existing upstream dependency sentinel")
    sentinel.write_text(_DEP_CHECK_MARKER, encoding="utf-8", newline="\n")
    return sentinel


def _verify_live_repository_snapshot(lock, snapshot_path: Path) -> None:
    """Require the live mirror InRelease to still equal the GPG-verified snapshot."""
    snapshot = load_repository_snapshot(snapshot_path)
    validate_repository_snapshot(lock, snapshot)
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
    digest = sha256(result.stdout).hexdigest()
    if digest != snapshot.inrelease_sha256:
        raise RootfsError(
            "Kali repository InRelease changed after signed snapshot capture; refusing rootfs build"
        )


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
    result.add_argument("--snapshot", type=Path, required=True)
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

    _verify_live_repository_snapshot(lock, args.snapshot)
    sentinel = _prepare_host_environment(checkout)
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
        try:
            if sentinel.is_file() and sentinel.read_text(encoding="utf-8") == _DEP_CHECK_MARKER:
                sentinel.unlink()
        except OSError:
            pass

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
