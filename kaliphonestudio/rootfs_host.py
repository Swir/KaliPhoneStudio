"""Fail-closed host preflight for cross-architecture Kali ARM64 rootfs builds."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from typing import Iterable

from .rootfs import RootfsError, RootfsSourceLock, validate_rootfs_source_lock


@dataclass(frozen=True)
class BinfmtStatus:
    enabled: bool
    interpreter: str
    flags: str


def parse_binfmt_status(text: str) -> BinfmtStatus:
    """Parse one /proc/sys/fs/binfmt_misc entry without assuming field order."""
    if not isinstance(text, str) or not text.strip():
        raise RootfsError("qemu-aarch64 binfmt status is empty")
    enabled = False
    interpreter = ""
    flags = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line == "enabled":
            enabled = True
        elif line.startswith("interpreter "):
            interpreter = line.removeprefix("interpreter ").strip()
        elif line.startswith("flags: "):
            flags = line.removeprefix("flags: ").strip()
    if not enabled:
        raise RootfsError("qemu-aarch64 binfmt handler is not enabled")
    if not interpreter:
        raise RootfsError("qemu-aarch64 binfmt handler has no interpreter")
    # F (fix-binary) pins the interpreter at registration time. This is required
    # here because the second-stage debootstrap executes after crossing a chroot
    # boundary; a dynamic, non-F handler can disappear or resolve target libs.
    if "F" not in flags:
        raise RootfsError("qemu-aarch64 binfmt handler must use the F flag for chroot builds")
    return BinfmtStatus(True, interpreter, flags)


def _keyring_fingerprints(keyring: Path) -> set[str]:
    try:
        result = subprocess.run(
            [
                "gpg",
                "--batch",
                "--no-default-keyring",
                "--keyring",
                str(keyring),
                "--with-colons",
                "--fingerprint",
            ],
            check=True,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RootfsError(f"cannot inspect Kali archive keyring: {exc}") from exc
    fingerprints: set[str] = set()
    for line in result.stdout.splitlines():
        fields = line.split(":")
        if fields and fields[0] == "fpr" and len(fields) > 9 and fields[9]:
            fingerprints.add(fields[9].upper())
    return fingerprints


def _require_commands(names: Iterable[str]) -> None:
    missing = sorted(name for name in names if shutil.which(name) is None)
    if missing:
        raise RootfsError(f"rootfs host is missing required commands: {', '.join(missing)}")


def preflight_rootfs_host(
    lock: RootfsSourceLock,
    *,
    binfmt_path: Path = Path("/proc/sys/fs/binfmt_misc/qemu-aarch64"),
    keyring_path: Path = Path("/usr/share/keyrings/kali-archive-keyring.gpg"),
) -> BinfmtStatus:
    """Verify the host can safely enter an ARM64 chroot before the expensive build starts.

    Registration is backend-agnostic: the contract checks the kernel-visible
    handler actually used for foreign binaries. KaliPhoneStudio additionally
    requires the static QEMU binary because the locked NetHunter builder copies
    the host interpreter into the target rootfs for second-stage debootstrap.
    """
    validate_rootfs_source_lock(lock)
    _require_commands(
        (
            "curl",
            "debootstrap",
            "git",
            "gpg",
            "gpgv",
            "qemu-aarch64",
            "qemu-aarch64-static",
            "xz",
        )
    )
    try:
        state = binfmt_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RootfsError(f"cannot read qemu-aarch64 binfmt status: {exc}") from exc
    status = parse_binfmt_status(state)
    if not keyring_path.is_file() or keyring_path.stat().st_size <= 0:
        raise RootfsError("Kali archive keyring is missing from the host")
    fingerprints = _keyring_fingerprints(keyring_path)
    if lock.archive_key_fingerprint not in fingerprints:
        raise RootfsError("installed Kali archive keyring does not contain the locked fingerprint")
    return status
