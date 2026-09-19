"""Descriptor-bound hashing for safety-sensitive local artifacts.

The helper is intentionally host-only. It never performs device I/O and never
turns a verified local file into permission to boot, flash, mount, or write a
phone. Its job is narrower: bind the bytes read from one regular file descriptor
to the path identity observed before and after the read, failing closed on
symlinks, replacement, truncation, growth, or in-place metadata/content drift.

On Windows the descriptor is backed by a Win32 handle opened with read sharing
only (no write/delete sharing) and FILE_FLAG_OPEN_REPARSE_POINT, closing a race
that metadata-only checks cannot reliably close on every Windows filesystem.
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
    ctime_ns: int


def _same_object(left: os.stat_result, right: os.stat_result) -> bool:
    """Return whether two observations describe the same unchanged file state.

    Device, inode, size and mtime are portable path/descriptor invariants. POSIX
    additionally binds ctime: a writer can restore an older mtime after changing
    bytes, but ordinary file APIs cannot restore ctime. Windows ctime semantics
    differ across Python/filesystem generations, so ctime is recorded there but
    writer/delete exclusion is enforced by the Win32 handle share mode instead.
    """
    portable_match = (
        left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
        and left.st_size == right.st_size
        and left.st_mtime_ns == right.st_mtime_ns
    )
    if not portable_match:
        return False
    if os.name != "nt" and left.st_ctime_ns != right.st_ctime_ns:
        return False
    return True


def _open_readonly_descriptor(candidate: Path) -> int:
    """Open one read-only descriptor with the strongest local no-follow boundary.

    POSIX uses O_NOFOLLOW when available. Windows uses CreateFileW directly so
    the verification handle shares reads only: later write/delete opens and path
    replacement are denied while the exact bytes are being hashed. The final
    component is opened as the reparse point itself rather than followed.
    """
    flags = os.O_RDONLY
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)

    if os.name != "nt":
        return os.open(candidate, flags)

    # Imported lazily so non-Windows hosts do not depend on Win32-only modules.
    import ctypes
    from ctypes import wintypes
    import msvcrt

    generic_read = 0x80000000
    file_share_read = 0x00000001
    open_existing = 3
    file_attribute_normal = 0x00000080
    file_flag_open_reparse_point = 0x00200000
    file_flag_sequential_scan = 0x08000000

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE

    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL

    handle = create_file(
        os.fspath(candidate),
        generic_read,
        file_share_read,
        None,
        open_existing,
        file_attribute_normal | file_flag_open_reparse_point | file_flag_sequential_scan,
        None,
    )
    invalid_handle_value = wintypes.HANDLE(-1).value
    if handle == invalid_handle_value:
        error_code = ctypes.get_last_error()
        raise OSError(error_code, ctypes.FormatError(error_code), os.fspath(candidate))

    crt_flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    try:
        # open_osfhandle takes ownership of the Win32 handle on success.
        return msvcrt.open_osfhandle(handle, crt_flags)
    except Exception:
        close_handle(handle)
        raise


def hash_stable_regular_file(
    path: Path,
    *,
    max_bytes: int,
    expected_size: int | None = None,
    label: str = "artifact",
) -> StableFileIdentity:
    """Hash one exact regular file while defending the path/FD boundary.

    ``O_NOFOLLOW`` is used when the host exposes it. Windows instead opens a
    Win32 handle with read-only sharing and reparse-point protection. The initial
    ``lstat`` plus descriptor ``fstat`` identity comparison remains mandatory on
    every platform. A final ``lstat`` proves that the path still names the same
    file object after hashing. Size and mtime must remain unchanged everywhere;
    POSIX also requires unchanged ctime.
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

    descriptor: int | None = None
    try:
        descriptor = _open_readonly_descriptor(candidate)
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
            raise StableFileError(f"{label} path was replaced or changed while being hashed")

        return StableFileIdentity(
            path=candidate,
            size=fd_after.st_size,
            sha256=digest.hexdigest(),
            device=fd_after.st_dev,
            inode=fd_after.st_ino,
            mtime_ns=fd_after.st_mtime_ns,
            ctime_ns=fd_after.st_ctime_ns,
        )
    except StableFileError:
        raise
    except OSError as exc:
        raise StableFileError(f"cannot hash {label}: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
