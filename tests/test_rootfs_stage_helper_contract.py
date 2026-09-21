from __future__ import annotations

import json
from pathlib import Path

from kaliphonestudio.rescue_candidate import _install_rootfs_stage_helper


def test_repository_rootfs_stage_helper_is_explicit_fail_closed_and_not_auto_run(tmp_path: Path) -> None:
    helper = Path("rescue/kps-rootfs-stage-once").read_text(encoding="utf-8")
    init = Path("rescue/init").read_text(encoding="utf-8")

    assert 'KPS_POLICY="interactive-rootfs-stage-v1"' in helper
    assert '"execution_gate_passed":true' in helper
    assert '"explicit_operator_confirmation_required":true' in helper
    assert '"write_scope_confirmation_required":true' in helper
    assert '"interactive_writer_required":true' in helper
    assert '"physical_gate_still_incomplete":true' in helper
    assert '"persistent_write_authorized":false' in helper
    assert '"raw_device_path_bound":false' in helper
    assert '"mount_target_bound":false' in helper
    assert 'mountpoint -q "$target_mount"' in helper
    assert 'case "$target_mount" in\n    /mnt/kps-*)' in helper
    assert 'sha256sum "$gate_file"' in helper
    assert 'sha256sum "$archive"' in helper
    assert 'tar -tf "$archive"' in helper
    assert 'tar -xpf "$archive" -C "$temporary_path"' in helper
    assert 'IFS= read -r answer' in helper
    assert '[ "$answer" = "$confirmation" ]' in helper
    executable_lines = [line.strip().lower() for line in helper.splitlines()]
    assert not any(line.startswith("mkfs") for line in executable_lines)
    assert not any(line.startswith("fastboot") for line in executable_lines)
    assert not any(line.startswith("set_active") for line in executable_lines)
    assert not any(line.startswith("reboot") for line in executable_lines)
    assert "/sbin/kps-rootfs-stage-once" not in init


def test_repository_busybox_contract_contains_only_needed_local_stage_applets() -> None:
    config = Path("rescue/busybox-minimal.config").read_text(encoding="utf-8")
    lock = json.loads(Path("tools/rescue-payload-lock.json").read_text(encoding="utf-8"))
    required = set(lock["required_applets"])

    for symbol in ("CONFIG_DF=y", "CONFIG_MOUNTPOINT=y", "CONFIG_TAR=y"):
        assert symbol in config
    for applet in ("df", "mountpoint", "tar"):
        assert applet in required

    forbidden = set(lock["forbidden_remote_access_applets"])
    assert not (required & forbidden)


def test_rootfs_stage_helper_installer_is_create_only_and_hashes_exact_bytes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    rescue = repo / "rescue"
    rescue.mkdir(parents=True)
    source = rescue / "kps-rootfs-stage-once"
    source.write_text(
        "#!/bin/sh\n"
        'KPS_POLICY="interactive-rootfs-stage-v1"\n'
        "# \"execution_gate_passed\":true\n"
        "# \"explicit_operator_confirmation_required\":true\n"
        "echo KPS_ROOTFS_STAGE_BETA_CREDIT=false\n",
        encoding="utf-8",
        newline="\n",
    )
    staging = tmp_path / "staging"
    (staging / "sbin").mkdir(parents=True)

    digest = _install_rootfs_stage_helper(repository_root=repo, staging_root=staging)
    installed = staging / "sbin" / "kps-rootfs-stage-once"
    assert installed.read_bytes() == source.read_bytes()
    assert len(digest) == 64
    assert installed.stat().st_mode & 0o777 == 0o700
