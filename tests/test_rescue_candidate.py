from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import struct

import pytest

from kaliphonestudio.profiles import DeviceProfile
from kaliphonestudio.rescue_candidate import (
    build_verified_rescue_candidate,
    write_rescue_candidate_evidence,
)
from kaliphonestudio.rescue_payload import RescuePayloadError
from kaliphonestudio.rescue_payload_repro import verify_reproducible_payload_pair


def _arm64_elf() -> bytes:
    payload = bytearray(64 + 56 + 4)
    payload[:4] = b"\x7fELF"
    payload[4:7] = bytes((2, 1, 1))
    struct.pack_into("<HHI", payload, 16, 2, 183, 1)
    struct.pack_into("<Q", payload, 32, 64)
    struct.pack_into("<HHHHHH", payload, 52, 64, 56, 1, 0, 0, 0)
    struct.pack_into("<I", payload, 64, 1)
    payload[120:] = b"KPS!"
    return bytes(payload)


def _fixture(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / "rescue").mkdir(parents=True)
    config = repo / "rescue" / "busybox-minimal.config"
    init = repo / "rescue" / "init"
    helper = repo / "rescue" / "kps-rootfs-stage-once"
    config.write_text("CONFIG_STATIC=y\nCONFIG_ASH=y\n", encoding="utf-8", newline="\n")
    init.write_text(
        "#!/bin/sh\necho 'network=disabled ssh=disabled'\nexec sh\n",
        encoding="utf-8", newline="\n",
    )
    init.chmod(0o755)
    helper.write_text(
        "#!/bin/sh\n"
        'KPS_POLICY="interactive-rootfs-stage-v1"\n'
        "# fixture only: runtime helper contract markers\n"
        "# \"execution_gate_passed\":true\n"
        "# \"explicit_operator_confirmation_required\":true\n"
        "echo KPS_ROOTFS_STAGE_BETA_CREDIT=false\n",
        encoding="utf-8",
        newline="\n",
    )
    helper.chmod(0o700)
    source = tmp_path / "busybox.tar.bz2"
    source.write_bytes(b"busybox-source")
    lock = {
        "schema_version": 1,
        "payload_id": "fixture-arm64-rescue-v1",
        "architecture": "arm64",
        "busybox": {
            "version": "1.38.0",
            "source_url": "https://busybox.net/downloads/busybox-1.38.0.tar.bz2",
            "source_sha256": sha256(source.read_bytes()).hexdigest(),
            "license": "GPL-2.0-only",
            "config_path": "rescue/busybox-minimal.config",
        },
        "binary_policy": {
            "elf_class": 64, "endianness": "little", "elf_machine": 183,
            "require_static": True, "max_binary_bytes": 8 * 1024 * 1024,
        },
        "required_applets": ["cat", "mount", "sh"],
        "forbidden_remote_access_applets": ["nc"],
        "init_template": "rescue/init",
        "network_default": "disabled",
        "ssh_default": "disabled",
        "materials": {
            "config_sha256": sha256(config.read_bytes()).hexdigest(),
            "init_sha256": sha256(init.read_bytes()).hexdigest(),
        },
        "build": {
            "cross_compile": "aarch64-linux-gnu-", "kconfig_target": "allnoconfig",
            "make_target": "busybox", "ldflags": "--static", "source_date_epoch": 0,
            "independent_builds": 2,
        },
    }
    lock_path = tmp_path / "lock.json"
    lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8", newline="\n")
    binary_a = tmp_path / "busybox-a"
    binary_b = tmp_path / "busybox-b"
    binary_a.write_bytes(_arm64_elf())
    binary_b.write_bytes(_arm64_elf())
    applets_a = tmp_path / "applets-a"
    applets_b = tmp_path / "applets-b"
    applets_a.write_text("cat\nmount\nsh\n", encoding="utf-8", newline="\n")
    applets_b.write_text("mount\nsh\ncat\n", encoding="utf-8", newline="\n")
    repro = verify_reproducible_payload_pair(
        lock_manifest_path=lock_path, repository_root=repo, source_archive=source,
        first_binary=binary_a, second_binary=binary_b,
        first_applet_list=applets_a, second_applet_list=applets_b,
        compiler_id="aarch64-linux-gnu-gcc fixture 13.2.0", target_machine="aarch64-linux-gnu",
    )
    return repo, lock_path, binary_a, applets_a, repro


def test_build_verified_candidate_uses_profile_lz4_and_binds_evidence(tmp_path: Path) -> None:
    repo, lock_path, binary, applets, repro = _fixture(tmp_path)
    profile = DeviceProfile(
        path=tmp_path / "devices" / "vendor" / "test" / "profile.json",
        data={"profile_id": "vendor/test", "arch": "arm64", "boot": {"ramdisk_compression": "lz4"}},
    )
    artifact = tmp_path / "rescue.cpio.lz4"
    evidence = build_verified_rescue_candidate(
        profile=profile, repro=repro, lock_manifest_path=lock_path,
        repository_root=repo, busybox=binary, applet_list=applets, destination=artifact,
    )
    assert evidence.verified is True
    assert evidence.profile_id == "vendor/test"
    assert evidence.ramdisk_compression == "lz4"
    assert evidence.payload_repro_evidence_sha256 == repro.evidence_sha256()
    assert evidence.ramdisk_sha256 == sha256(artifact.read_bytes()).hexdigest()
    assert artifact.read_bytes().startswith(bytes.fromhex("02214c18"))
    out = tmp_path / "candidate.json"
    digest = write_rescue_candidate_evidence(evidence, out)
    assert digest == evidence.evidence_sha256()


def test_candidate_rejects_profile_without_supported_compression(tmp_path: Path) -> None:
    repo, lock_path, binary, applets, repro = _fixture(tmp_path)
    profile = DeviceProfile(
        path=tmp_path / "profile.json",
        data={"profile_id": "vendor/test", "arch": "arm64", "boot": {"ramdisk_compression": "none"}},
    )
    with pytest.raises(RescuePayloadError, match="gzip or lz4"):
        build_verified_rescue_candidate(
            profile=profile, repro=repro, lock_manifest_path=lock_path,
            repository_root=repo, busybox=binary, applet_list=applets,
            destination=tmp_path / "candidate",
        )


def test_candidate_refuses_overwrite(tmp_path: Path) -> None:
    repo, lock_path, binary, applets, repro = _fixture(tmp_path)
    profile = DeviceProfile(
        path=tmp_path / "profile.json",
        data={"profile_id": "vendor/test", "arch": "arm64", "boot": {"ramdisk_compression": "gzip"}},
    )
    artifact = tmp_path / "existing.img"
    artifact.write_bytes(b"do-not-touch")
    with pytest.raises(RescuePayloadError, match="overwrite"):
        build_verified_rescue_candidate(
            profile=profile, repro=repro, lock_manifest_path=lock_path,
            repository_root=repo, busybox=binary, applet_list=applets, destination=artifact,
        )
    assert artifact.read_bytes() == b"do-not-touch"
