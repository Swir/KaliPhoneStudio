"""Local Git-object verification for a source-locked kernel toolchain checkout.

The expensive kernel reproducibility workflow already fetches the exact locked
Android Clang commit and subtree.  This module verifies that local Git object
graph directly so the build does not need a second Gitiles HTTP metadata fetch
before it can start.  The resulting source evidence intentionally uses the same
canonical schema as the independent Gitiles verifier.

This is host-side provenance only.  It never grants hardware or Beta credit.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
from urllib.parse import urlparse

from .kernel_toolchain import (
    KernelToolchainError,
    KernelToolchainLock,
    KernelToolchainSourceEvidence,
    verify_android_version_capture,
)


MAX_GIT_OUTPUT_BYTES = 2 * 1024 * 1024
GIT_TIMEOUT_SECONDS = 30


def _run_git(repository: Path, *args: str, maximum: int = MAX_GIT_OUTPUT_BYTES) -> bytes:
    if not repository.is_dir() or repository.is_symlink():
        raise KernelToolchainError("toolchain checkout must be a real Git directory")
    try:
        result = subprocess.run(
            ["git", "-C", str(repository), *args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise KernelToolchainError(f"cannot execute git {' '.join(args)}") from exc
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        if len(stderr) > 400:
            stderr = stderr[:400] + "..."
        raise KernelToolchainError(
            f"git {' '.join(args)} failed with exit {result.returncode}: {stderr}"
        )
    if len(result.stdout) > maximum:
        raise KernelToolchainError(f"git {' '.join(args)} output exceeds safety limit")
    return result.stdout


def _git_text(repository: Path, *args: str) -> str:
    payload = _run_git(repository, *args)
    try:
        return payload.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise KernelToolchainError(f"git {' '.join(args)} returned non-UTF-8 text") from exc


def _canonical_https_remote(value: str) -> str:
    text = value.strip().rstrip("/")
    if text.endswith(".git"):
        text = text[:-4]
    parsed = urlparse(text)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise KernelToolchainError("toolchain Git remote must be credential-free HTTPS")
    return text


def _verify_object(
    repository: Path,
    *,
    spec: str,
    expected_sha1: str,
    expected_type: str,
    field: str,
) -> None:
    actual = _git_text(repository, "rev-parse", spec)
    if actual != expected_sha1:
        raise KernelToolchainError(
            f"local Git object mismatch for {field}: expected {expected_sha1}, got {actual}"
        )
    object_type = _git_text(repository, "cat-file", "-t", actual)
    if object_type != expected_type:
        raise KernelToolchainError(
            f"local Git object type mismatch for {field}: expected {expected_type}, got {object_type}"
        )


def capture_local_git_source_evidence(
    lock: KernelToolchainLock,
    repository: Path,
) -> KernelToolchainSourceEvidence:
    """Verify an exact fetched toolchain checkout without another network request.

    The repository must be the exact source repository from the lock, at the
    exact locked commit, using SHA-1 Git objects.  The locked subtree, bin tree,
    AndroidVersion blob and manifest blob are checked by object identity.  The
    AndroidVersion bytes are then read from the immutable commit object and
    validated against the lock.
    """
    if not repository.is_dir() or repository.is_symlink():
        raise KernelToolchainError("toolchain checkout must be a real directory")

    inside = _git_text(repository, "rev-parse", "--is-inside-work-tree")
    if inside != "true":
        raise KernelToolchainError("toolchain checkout is not a Git work tree")
    object_format = _git_text(repository, "rev-parse", "--show-object-format")
    if object_format != "sha1":
        raise KernelToolchainError("toolchain checkout must use SHA-1 Git objects")

    head = _git_text(repository, "rev-parse", "HEAD")
    if head != lock.source_commit:
        raise KernelToolchainError(
            f"toolchain checkout HEAD mismatch: expected {lock.source_commit}, got {head}"
        )
    head_type = _git_text(repository, "cat-file", "-t", head)
    if head_type != "commit":
        raise KernelToolchainError("locked toolchain HEAD is not a commit object")

    remote = _git_text(repository, "remote", "get-url", "origin")
    if _canonical_https_remote(remote) != _canonical_https_remote(lock.source_url):
        raise KernelToolchainError("toolchain checkout origin does not match the source lock")

    tracked_status = _git_text(repository, "status", "--porcelain=v1", "--untracked-files=no")
    if tracked_status:
        raise KernelToolchainError("toolchain checkout has modified tracked content")

    subtree_spec = f"{lock.source_commit}:{lock.subtree}"
    version_spec = f"{subtree_spec}/AndroidVersion.txt"
    manifest_spec = f"{subtree_spec}/manifest_{lock.build_id}.xml"
    bin_spec = f"{subtree_spec}/bin"

    _verify_object(
        repository,
        spec=subtree_spec,
        expected_sha1=lock.tree_sha1,
        expected_type="tree",
        field="toolchain subtree",
    )
    _verify_object(
        repository,
        spec=bin_spec,
        expected_sha1=lock.bin_tree_sha1,
        expected_type="tree",
        field="bin tree",
    )
    _verify_object(
        repository,
        spec=version_spec,
        expected_sha1=lock.android_version_blob_sha1,
        expected_type="blob",
        field="AndroidVersion.txt",
    )
    _verify_object(
        repository,
        spec=manifest_spec,
        expected_sha1=lock.manifest_blob_sha1,
        expected_type="blob",
        field=f"manifest_{lock.build_id}.xml",
    )

    version_payload = _run_git(repository, "show", version_spec, maximum=4096)
    verify_android_version_capture(lock, version_payload)

    return KernelToolchainSourceEvidence(
        schema_version=1,
        lock_sha256=lock.lock_sha256(),
        source_url=lock.source_url,
        source_commit=lock.source_commit,
        subtree=lock.subtree,
        tree_sha1=lock.tree_sha1,
        bin_tree_sha1=lock.bin_tree_sha1,
        android_version_blob_sha1=lock.android_version_blob_sha1,
        manifest_blob_sha1=lock.manifest_blob_sha1,
        android_version=lock.android_version,
        clang_revision=lock.clang_revision,
        build_id=lock.build_id,
        llvm_project_commit=lock.llvm_project_commit,
        beta_gate_credit=False,
    )
