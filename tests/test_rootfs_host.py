from pathlib import Path

import pytest

from kaliphonestudio.rootfs import RootfsError, load_rootfs_source_lock
from kaliphonestudio import rootfs_host

ROOT = Path(__file__).parents[1]
LOCK_PATH = ROOT / "tools" / "rootfs-source-lock.json"


def test_parse_binfmt_status_requires_enabled_fixed_interpreter():
    status = rootfs_host.parse_binfmt_status(
        "enabled\ninterpreter /usr/libexec/qemu-binfmt/aarch64-binfmt-P\nflags: POCF\n"
    )
    assert status.enabled is True
    assert status.interpreter.endswith("aarch64-binfmt-P")
    assert "F" in status.flags


def test_parse_binfmt_status_rejects_handler_without_fix_binary_flag():
    with pytest.raises(RootfsError, match="F flag"):
        rootfs_host.parse_binfmt_status(
            "enabled\ninterpreter /usr/bin/qemu-aarch64\nflags: POC\n"
        )


def test_parse_binfmt_status_rejects_disabled_handler():
    with pytest.raises(RootfsError, match="not enabled"):
        rootfs_host.parse_binfmt_status(
            "disabled\ninterpreter /usr/bin/qemu-aarch64\nflags: POCF\n"
        )


def test_host_preflight_binds_locked_kali_key_and_commands(tmp_path, monkeypatch):
    lock = load_rootfs_source_lock(LOCK_PATH)
    binfmt = tmp_path / "qemu-aarch64"
    binfmt.write_text(
        "enabled\ninterpreter /usr/libexec/qemu-binfmt/aarch64-binfmt-P\nflags: POCF\n",
        encoding="utf-8",
    )
    keyring = tmp_path / "kali.gpg"
    keyring.write_bytes(b"keyring")
    monkeypatch.setattr(rootfs_host.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        rootfs_host,
        "_keyring_fingerprints",
        lambda path: {lock.archive_key_fingerprint},
    )
    status = rootfs_host.preflight_rootfs_host(
        lock, binfmt_path=binfmt, keyring_path=keyring
    )
    assert status.flags == "POCF"


def test_host_preflight_rejects_wrong_keyring_fingerprint(tmp_path, monkeypatch):
    lock = load_rootfs_source_lock(LOCK_PATH)
    binfmt = tmp_path / "qemu-aarch64"
    binfmt.write_text(
        "enabled\ninterpreter /usr/libexec/qemu-binfmt/aarch64-binfmt-P\nflags: POCF\n",
        encoding="utf-8",
    )
    keyring = tmp_path / "kali.gpg"
    keyring.write_bytes(b"keyring")
    monkeypatch.setattr(rootfs_host.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(rootfs_host, "_keyring_fingerprints", lambda path: {"A" * 40})
    with pytest.raises(RootfsError, match="locked fingerprint"):
        rootfs_host.preflight_rootfs_host(
            lock, binfmt_path=binfmt, keyring_path=keyring
        )
