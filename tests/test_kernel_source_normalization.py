import os
from pathlib import Path
import subprocess

import pytest

from kaliphonestudio.kernel_contract import KernelContractError
from kaliphonestudio.kernel_source_normalization import (
    SOURCE_MTIME_POLICY,
    normalize_kernel_checkout_mtimes,
    write_kernel_source_mtime_evidence,
)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "kernel"
    repo.mkdir(parents=True)
    _git(repo, "init", "--quiet")
    _git(repo, "config", "user.name", "KaliPhoneStudio Tests")
    _git(repo, "config", "user.email", "tests@example.invalid")

    source = repo / "kernel.c"
    source.write_text("int kernel_test(void) { return 7; }\n", encoding="utf-8")
    script = repo / "scripts" / "build.sh"
    script.parent.mkdir()
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)
    link = repo / "kernel-link.c"
    try:
        os.symlink("kernel.c", link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are required for this source-normalization contract test")

    _git(repo, "add", "kernel.c", "kernel-link.c", "scripts/build.sh")
    _git(repo, "commit", "--quiet", "-m", "fixture")
    return repo, _git(repo, "rev-parse", "HEAD").stdout.strip()


def test_normalization_is_path_independent_and_leaves_git_metadata_untouched(tmp_path):
    source, commit = _repo(tmp_path / "a")
    clone = tmp_path / "b" / "kernel"
    clone.parent.mkdir(parents=True)
    subprocess.run(
        ["git", "clone", "--quiet", "--no-hardlinks", str(source), str(clone)],
        check=True,
    )
    _git(clone, "checkout", "--quiet", "--detach", commit)

    # Deliberately give the two worktrees different checkout-like timestamps.
    for root, epoch in ((source, 1_700_000_001), (clone, 1_800_000_002)):
        os.utime(root / "kernel.c", (epoch, epoch))
        os.utime(root / "scripts" / "build.sh", (epoch, epoch))
        os.utime(root / "kernel-link.c", (epoch, epoch), follow_symlinks=False)

    git_head_mtime_a = (source / ".git" / "HEAD").stat().st_mtime_ns
    git_head_mtime_b = (clone / ".git" / "HEAD").stat().st_mtime_ns

    evidence_a = normalize_kernel_checkout_mtimes(source, commit)
    evidence_b = normalize_kernel_checkout_mtimes(clone, commit)

    assert evidence_a == evidence_b
    assert evidence_a.policy == SOURCE_MTIME_POLICY
    assert evidence_a.epoch == 0
    assert evidence_a.tracked_entry_count == 3
    assert evidence_a.regular_file_count == 2
    assert evidence_a.symlink_count == 1
    assert evidence_a.checkout_clean_verified is True
    assert evidence_a.normalized_verified is True
    assert evidence_a.hardware_verified is False
    assert evidence_a.beta_gate_credit is False
    assert len(evidence_a.tracked_manifest_sha256) == 64

    for root in (source, clone):
        assert int((root / "kernel.c").stat().st_mtime) == 0
        assert int((root / "scripts" / "build.sh").stat().st_mtime) == 0
        assert int((root / "kernel-link.c").lstat().st_mtime) == 0
        assert _git(root, "status", "--porcelain").stdout == ""

    assert (source / ".git" / "HEAD").stat().st_mtime_ns == git_head_mtime_a
    assert (clone / ".git" / "HEAD").stat().st_mtime_ns == git_head_mtime_b


def test_normalization_rejects_dirty_or_wrong_commit(tmp_path):
    repo, commit = _repo(tmp_path)
    (repo / "kernel.c").write_text("changed\n", encoding="utf-8")
    with pytest.raises(KernelContractError, match="modified tracked content"):
        normalize_kernel_checkout_mtimes(repo, commit)

    _git(repo, "checkout", "--", "kernel.c")
    with pytest.raises(KernelContractError, match="HEAD does not match"):
        normalize_kernel_checkout_mtimes(repo, "f" * 40)


@pytest.mark.parametrize("epoch", [-1, True, 4_102_444_801])
def test_normalization_rejects_unsafe_epoch(tmp_path, epoch):
    repo, commit = _repo(tmp_path)
    with pytest.raises(KernelContractError, match="epoch"):
        normalize_kernel_checkout_mtimes(repo, commit, epoch=epoch)


def test_normalization_evidence_is_atomic_and_non_overwriting(tmp_path):
    repo, commit = _repo(tmp_path)
    evidence = normalize_kernel_checkout_mtimes(repo, commit)
    destination = tmp_path / "evidence" / "kernel-source-mtime.json"

    digest = write_kernel_source_mtime_evidence(evidence, destination)
    assert digest == evidence.evidence_sha256()
    assert destination.read_text(encoding="utf-8") == evidence.canonical_json()
    with pytest.raises(KernelContractError, match="refusing to overwrite"):
        write_kernel_source_mtime_evidence(evidence, destination)
