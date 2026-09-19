"""Descriptor-bound hashing for safety-sensitive local artifacts.

The helper is intentionally host-only. It never performs device I/O and never
turns a verified local file into permission to boot, flash, mount, or write a
phone. Its job is narrower: bind the bytes read from one regular file descriptor
to the path identity observed before and after the read, failing closed on
symlinks, replacement, truncation, size drift, or in-place metadata drift.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import stat


class StableFileError(ValueError):
    """Raised when an exact local-file identity cannot be established safely."""


@dataclass(frozen=True)
class StableFileIdentity:
    path: Path
    size: int
    sha256: str
    device: int
    inode: int
    mtime_ns: int


def _same_object(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
        and left.st_size == right.st_size
        and left.st_mtime_ns == right.st_mtime_ns
    )


def hash_stable_regular_file(
    path: Path,
    *,
    max_bytes: int,
    expected_size: int | None = None,
    label: str = "artifact",
) -> StableFileIdentity:
    """Hash one exact regular file while defending the path/FD boundary.

    ``O_NOFOLLOW`` is used when the host exposes it. On platforms without it,
    the initial ``lstat`` plus descriptor ``fstat`` identity comparison remains
    mandatory. A final ``lstat`` proves that the path still names the same file
    object after hashing.
    """
    candidate = Path(path)
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes <= 0:
        raise StableFileError("max_bytes must be a positive integer")
    if expected_size is not None and (
        not isinstance(expected_size, int)
        or isinstance(expected_size, bool)
        or expected_size <= 0
        or expected_size > max_bytes
    ):
        raise StableFileError(f"{label} expected size is outside the bounded safety limit")

    try:
        path_before = os.lstat(candidate)
    except OSError as exc:
        raise StableFileError(f"cannot inspect {label}: {exc}") from exc
    if stat.S_ISLNK(path_before.st_mode) or not stat.S_ISREG(path_before.st_mode):
        raise StableFileError(f"{label} must be a regular non-symlink file: {candidate}")

    flags = os.O_RDONLY
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)

    descriptor: int | None = None
    try:
        descriptor = os.open(candidate, flags)
        fd_before = os.fstat(descriptor)
        if not stat.S_ISREG(fd_before.st_mode):
            raise StableFileError(f"{label} descriptor is not a regular file")
        if not _same_object(path_before, fd_before):
            raise StableFileError(f"{label} path changed before the descriptor was secured")
        if fd_before.st_size <= 0 or fd_before.st_size > max_bytes:
            raise StableFileError(f"{label} size is outside the bounded safety limit")
        if expected_size is not None and fd_before.st_size != expected_size:
            raise StableFileError(f"{label} size differs from the expected exact size")

        digest = sha256()
        total = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > fd_before.st_size or total > max_bytes:
                raise StableFileError(f"{label} grew while being hashed")
            digest.update(chunk)

        fd_after = os.fstat(descriptor)
        if total != fd_before.st_size:
            raise StableFileError(f"{label} was truncated while being hashed")
        if not _same_object(fd_before, fd_after):
            raise StableFileError(f"{label} changed while being hashed")

        path_after = os.lstat(candidate)
        if stat.S_ISLNK(path_after.st_mode) or not stat.S_ISREG(path_after.st_mode):
            raise StableFileError(f"{label} path stopped naming a regular file during hashing")
        if not _same_object(fd_after, path_after):
            raise StableFileError(f"{label} path was replaced while being hashed")

        return StableFileIdentity(
            path=candidate,
            size=fd_after.st_size,
            sha256=digest.hexdigest(),
            device=fd_after.st_dev,
            inode=fd_after.st_ino,
            mtime_ns=fd_after.st_mtime_ns,
        )
    except StableFileError:
        raise
    except OSError as exc:
        raise StableFileError(f"cannot hash {label}: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
