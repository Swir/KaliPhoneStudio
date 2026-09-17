"""Normalize exact kernel checkout timestamps for reproducibility experiments.

Git creates independent working trees with checkout-time mtimes.  A vendor kernel can
observe those mtimes through compiler builtins or host-side generators even when the
tracked bytes and commit are identical.  This module normalizes only Git-tracked
regular files and symlinks to one explicit epoch after proving the checkout is clean
and at the expected commit.  It never changes tracked file contents, `.git`, phone
state, or hardware.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
from typing import Any, Callable

from .kernel_contract import KernelContractError


DEFAULT_SOURCE_MTIME_EPOCH = 0
SOURCE_MTIME_POLICY = "git-tracked-source-date-epoch-v1"
_ALLOWED_GIT_MODES = {"100644", "100755", "120000"}
_HEX40 = set("0123456789abcdef")


@dataclass(frozen=True)
class KernelSourceMtimeEvidence:
    schema_version: int
    source_commit: str
    policy: str
    epoch: int
    tracked_manifest_sha256: str
    tracked_entry_count: int
    regular_file_count: int
    symlink_count: int
    checkout_clean_verified: bool
    normalized_verified: bool
    hardware_verified: bool = False
    beta_gate_credit: bool = False

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _validate_commit(value: str) -> str:
    if not isinstance(value, str):
        raise KernelContractError("expected kernel commit must be a string")
    commit = value.strip().lower()
    if len(commit) != 40 or any(ch not in _HEX40 for ch in commit):
        raise KernelContractError("expected kernel commit must be a full 40-hex SHA-1")
    return commit


def _validate_epoch(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise KernelContractError("kernel source mtime epoch must be a non-negative integer")
    # Keep the policy portable to filesystems whose timestamp range is narrower than Python's.
    if value > 4_102_444_800:  # 2100-01-01 UTC
        raise KernelContractError("kernel source mtime epoch is outside the supported policy range")
    return value


def _real_checkout(path: Path) -> Path:
    if not path.is_dir() or path.is_symlink():
        raise KernelContractError("kernel checkout must be a real directory")
    try:
        return path.resolve(strict=True)
    except OSError as exc:
        raise KernelContractError("cannot resolve kernel checkout") from exc


def _run_git(
    checkout: Path,
    args: list[str],
    *,
    runner: Callable[..., Any],
    text: bool = False,
) -> subprocess.CompletedProcess[Any]:
    try:
        return runner(
            ["git", "-C", str(checkout), *args],
            check=True,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=text,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise KernelContractError(f"kernel checkout git command failed: {' '.join(args)}") from exc


def _assert_clean_checkout(checkout: Path, *, runner: Callable[..., Any]) -> None:
    for args in (["diff", "--quiet", "--ignore-submodules", "--"], ["diff", "--cached", "--quiet", "--ignore-submodules", "--"]):
        try:
            runner(
                ["git", "-C", str(checkout), *args],
                check=True,
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except subprocess.CalledProcessError as exc:
            if exc.returncode == 1:
                raise KernelContractError("kernel checkout has modified tracked content") from exc
            raise KernelContractError("cannot verify clean kernel checkout") from exc
        except OSError as exc:
            raise KernelContractError("cannot verify clean kernel checkout") from exc


def _parse_tracked_entries(payload: bytes) -> list[tuple[str, str, str]]:
    entries: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for raw in payload.split(b"\0"):
        if not raw:
            continue
        try:
            header, path_bytes = raw.split(b"\t", 1)
            mode_b, blob_b, stage_b = header.split(b" ", 2)
            mode = mode_b.decode("ascii")
            blob = blob_b.decode("ascii").lower()
            stage = stage_b.decode("ascii")
            path_text = path_bytes.decode("utf-8", errors="strict")
        except (ValueError, UnicodeError) as exc:
            raise KernelContractError("malformed git ls-files metadata") from exc
        if stage != "0":
            raise KernelContractError("kernel checkout contains an unmerged tracked entry")
        if mode not in _ALLOWED_GIT_MODES:
            raise KernelContractError(f"unsupported tracked kernel entry mode: {mode}")
        if len(blob) != 40 or any(ch not in _HEX40 for ch in blob):
            raise KernelContractError("tracked kernel entry has malformed blob SHA-1")
        pure = PurePosixPath(path_text)
        if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
            raise KernelContractError("tracked kernel path is unsafe")
        normalized = pure.as_posix()
        if normalized in seen:
            raise KernelContractError("duplicate tracked kernel path")
        seen.add(normalized)
        entries.append((mode, blob, normalized))
    if not entries:
        raise KernelContractError("kernel checkout contains no tracked files")
    entries.sort(key=lambda item: item[2].encode("utf-8"))
    return entries


def _tracked_manifest_sha256(entries: list[tuple[str, str, str]]) -> str:
    digest = sha256()
    for mode, blob, path in entries:
        digest.update(mode.encode("ascii"))
        digest.update(b" ")
        digest.update(blob.encode("ascii"))
        digest.update(b"\t")
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _entry_path(checkout: Path, relative: str) -> Path:
    candidate = checkout.joinpath(*PurePosixPath(relative).parts)
    # Do not resolve the final component: a tracked symlink is a legitimate object whose own
    # mtime is normalized.  The parent must still stay inside the verified checkout.
    try:
        parent = candidate.parent.resolve(strict=True)
    except OSError as exc:
        raise KernelContractError(f"tracked kernel entry parent is missing: {relative}") from exc
    if parent != checkout and checkout not in parent.parents:
        raise KernelContractError(f"tracked kernel entry escapes checkout: {relative}")
    return candidate


def _normalize_entry(path: Path, mode: str, epoch: int) -> tuple[int, int]:
    try:
        before = path.lstat()
    except OSError as exc:
        raise KernelContractError(f"tracked kernel entry is missing: {path.name}") from exc

    if mode == "120000":
        if not stat.S_ISLNK(before.st_mode):
            raise KernelContractError("tracked kernel symlink mode does not match working tree")
        try:
            os.utime(path, (epoch, epoch), follow_symlinks=False)
            after = path.lstat()
        except (OSError, NotImplementedError) as exc:
            raise KernelContractError("cannot normalize tracked kernel symlink mtime") from exc
        if int(after.st_mtime) != epoch:
            raise KernelContractError("tracked kernel symlink mtime normalization did not stick")
        return 0, 1

    if path.is_symlink() or not stat.S_ISREG(before.st_mode):
        raise KernelContractError("tracked kernel regular-file mode does not match working tree")
    try:
        os.utime(path, (epoch, epoch), follow_symlinks=False)
        after = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise KernelContractError("cannot normalize tracked kernel file mtime") from exc
    if int(after.st_mtime) != epoch:
        raise KernelContractError("tracked kernel file mtime normalization did not stick")
    return 1, 0


def normalize_kernel_checkout_mtimes(
    checkout: Path,
    expected_commit: str,
    *,
    epoch: int = DEFAULT_SOURCE_MTIME_EPOCH,
    runner: Callable[..., Any] = subprocess.run,
) -> KernelSourceMtimeEvidence:
    """Normalize mtimes of the exact clean Git-tracked kernel tree and emit evidence.

    Untracked files and `.git` are never traversed or modified.  Git object identities are
    included in a canonical tracked-tree manifest digest, so two independent checkouts of
    the same commit produce identical evidence when the policy was applied successfully.
    """
    source = _real_checkout(checkout)
    commit = _validate_commit(expected_commit)
    normalized_epoch = _validate_epoch(epoch)

    head = _run_git(source, ["rev-parse", "HEAD"], runner=runner, text=True).stdout.strip().lower()
    if head != commit:
        raise KernelContractError("kernel checkout HEAD does not match the expected source commit")
    _assert_clean_checkout(source, runner=runner)

    listing = _run_git(source, ["ls-files", "-z", "--stage"], runner=runner).stdout
    if not isinstance(listing, (bytes, bytearray)):
        raise KernelContractError("git ls-files returned non-byte output")
    entries = _parse_tracked_entries(bytes(listing))

    regular = 0
    symlinks = 0
    for mode, _blob, relative in entries:
        reg_inc, link_inc = _normalize_entry(_entry_path(source, relative), mode, normalized_epoch)
        regular += reg_inc
        symlinks += link_inc

    # Metadata-only normalization must never make Git consider tracked content dirty.
    _assert_clean_checkout(source, runner=runner)
    return KernelSourceMtimeEvidence(
        schema_version=1,
        source_commit=commit,
        policy=SOURCE_MTIME_POLICY,
        epoch=normalized_epoch,
        tracked_manifest_sha256=_tracked_manifest_sha256(entries),
        tracked_entry_count=len(entries),
        regular_file_count=regular,
        symlink_count=symlinks,
        checkout_clean_verified=True,
        normalized_verified=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def write_kernel_source_mtime_evidence(evidence: KernelSourceMtimeEvidence, destination: Path) -> str:
    if evidence.schema_version != 1 or evidence.policy != SOURCE_MTIME_POLICY:
        raise KernelContractError("unsupported kernel source mtime evidence schema/policy")
    if evidence.checkout_clean_verified is not True or evidence.normalized_verified is not True:
        raise KernelContractError("refusing to persist unverified kernel source mtime evidence")
    if evidence.hardware_verified is not False or evidence.beta_gate_credit is not False:
        raise KernelContractError("host source-normalization evidence cannot claim hardware/Beta credit")
    if destination.exists():
        raise KernelContractError(f"refusing to overwrite existing evidence: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists():
        raise KernelContractError("refusing to overwrite stale source-normalization temporary file")
    try:
        temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return evidence.evidence_sha256()
