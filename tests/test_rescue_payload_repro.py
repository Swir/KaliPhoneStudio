from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import struct

import pytest

from kaliphonestudio.rescue_payload import RescuePayloadError
from kaliphonestudio.rescue_payload_repro import (
    load_repro_contract,
    stage_reproducible_payload,
    verify_reproducible_payload_pair,
    write_repro_evidence,
)


def _arm64_elf(*, interpreter: bool = False, marker: bytes = b"A") -> bytes:
    payload = bytearray(64 + 56 + len(marker))
    payload[:4] = b"\x7fELF"
    payload[4] = 2
    payload[5] = 1
    payload[6] = 1
    struct.pack_into("<HHI", payload, 16, 2, 183, 1)
    struct.pack_into("<Q", payload, 24, 0)
    struct.pack_into("<Q", payload, 32, 64)
    struct.pack_into("<Q", payload, 40, 0)
    struct.pack_into("<I", payload, 48, 0)
    struct.pack_into("<HHHHHH", payload, 52, 64, 56, 1, 0, 0, 0)
    struct.pack_into("<I", payload, 64, 3 if interpreter else 1)
    payload[120:] = marker
    return bytes(payload)


def _write_contract(tmp_path: Path) -> dict[str, Path]:
    repo = tmp_path / "repo"
    (repo / "rescue").mkdir(parents=True)
    config = repo / "rescue" / "busybox-minimal.config"
    init = repo / "rescue" / "init"
    config.write_text("CONFIG_STATIC=y\nCONFIG_ASH=y\n", encoding="utf-8", newline="\n")
    init.write_text(
        "#!/bin/sh\n"
        "echo 'network=disabled ssh=disabled'\n"
        "exec sh\n",
        encoding="utf-8",
        newline="\n",
    )
    init.chmod(0o755)

    source = tmp_path / "busybox.tar.bz2"
    source.write_bytes(b"busybox-source-fixture")
    source_sha = sha256(source.read_bytes()).hexdigest()
    lock = {
        "schema_version": 1,
        "payload_id": "fixture-arm64-rescue-v1",
        "architecture": "arm64",
        "busybox": {
            "version": "1.38.0",
            "source_url": "https://busybox.net/downloads/busybox-1.38.0.tar.bz2",
            "source_sha256": source_sha,
            "license": "GPL-2.0-only",
            "config_path": "rescue/busybox-minimal.config",
        },
        "binary_policy": {
            "elf_class": 64,
            "endianness": "little",
            "elf_machine": 183,
            "require_static": True,
            "max_binary_bytes": 8 * 1024 * 1024,
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
            "cross_compile": "aarch64-linux-gnu-",
            "kconfig_target": "allnoconfig",
            "make_target": "busybox",
            "ldflags": "--static",
            "source_date_epoch": 0,
            "independent_builds": 2,
        },
    }
    lock_path = tmp_path / "rescue-payload-lock.json"
    lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8", newline="\n")
    first = tmp_path / "busybox-a"
    second = tmp_path / "busybox-b"
    first.write_bytes(_arm64_elf())
    second.write_bytes(_arm64_elf())
    applets_a = tmp_path / "applets-a.txt"
    applets_b = tmp_path / "applets-b.txt"
    applets_a.write_text("sh\nmount\ncat\n", encoding="utf-8", newline="\n")
    applets_b.write_text("cat\nsh\nmount\n", encoding="utf-8", newline="\n")
    return {
        "repo": repo, "config": config, "init": init, "source": source, "lock": lock_path,
        "first": first, "second": second, "applets_a": applets_a, "applets_b": applets_b,
    }


def _verify(paths: dict[str, Path]):
    return verify_reproducible_payload_pair(
        lock_manifest_path=paths["lock"], repository_root=paths["repo"],
        source_archive=paths["source"], first_binary=paths["first"], second_binary=paths["second"],
        first_applet_list=paths["applets_a"], second_applet_list=paths["applets_b"],
        compiler_id="aarch64-linux-gnu-gcc fixture 13.2.0", target_machine="aarch64-linux-gnu",
    )


def test_pair_verification_binds_source_materials_and_two_builds(tmp_path: Path) -> None:
    paths = _write_contract(tmp_path)
    evidence = _verify(paths)
    assert evidence.reproducible is True
    assert evidence.independent_builds == 2
    assert evidence.architecture == "arm64"
    assert evidence.elf_machine == 183
    assert evidence.busybox_sha256 == sha256(paths["first"].read_bytes()).hexdigest()
    assert evidence.source_archive_sha256 == sha256(paths["source"].read_bytes()).hexdigest()
    assert evidence.config_sha256 == sha256(paths["config"].read_bytes()).hexdigest()
    assert evidence.init_sha256 == sha256(paths["init"].read_bytes()).hexdigest()
    assert evidence.applet_count == 3
    out = tmp_path / "evidence" / "rescue-repro.json"
    digest = write_repro_evidence(evidence, out)
    assert digest == evidence.evidence_sha256()
    assert json.loads(out.read_text(encoding="utf-8"))["busybox_sha256"] == evidence.busybox_sha256


def test_pair_verification_rejects_binary_divergence(tmp_path: Path) -> None:
    paths = _write_contract(tmp_path)
    paths["second"].write_bytes(_arm64_elf(marker=b"B"))
    with pytest.raises(RescuePayloadError, match="not byte-identical"):
        _verify(paths)


def test_pair_verification_rejects_dynamic_interpreter(tmp_path: Path) -> None:
    paths = _write_contract(tmp_path)
    dynamic = _arm64_elf(interpreter=True)
    paths["first"].write_bytes(dynamic)
    paths["second"].write_bytes(dynamic)
    with pytest.raises(RescuePayloadError, match="PT_INTERP"):
        _verify(paths)


def test_pair_verification_rejects_source_archive_drift(tmp_path: Path) -> None:
    paths = _write_contract(tmp_path)
    paths["source"].write_bytes(b"tampered-source")
    with pytest.raises(RescuePayloadError, match="source archive SHA-256"):
        _verify(paths)


def test_contract_rejects_repository_material_drift(tmp_path: Path) -> None:
    paths = _write_contract(tmp_path)
    paths["init"].write_text(
        "#!/bin/sh\necho 'network=disabled ssh=disabled'\necho drift\nexec sh\n",
        encoding="utf-8", newline="\n",
    )
    with pytest.raises(RescuePayloadError, match="init SHA-256"):
        load_repro_contract(paths["lock"], repository_root=paths["repo"])


def test_pair_verification_rejects_forbidden_applet(tmp_path: Path) -> None:
    paths = _write_contract(tmp_path)
    paths["applets_a"].write_text("cat\nmount\nnc\nsh\n", encoding="utf-8", newline="\n")
    paths["applets_b"].write_text("cat\nmount\nnc\nsh\n", encoding="utf-8", newline="\n")
    with pytest.raises(RescuePayloadError, match="forbidden remote-access"):
        _verify(paths)


def test_staging_requires_matching_reproducibility_evidence(tmp_path: Path) -> None:
    paths = _write_contract(tmp_path)
    evidence = _verify(paths)
    staging = tmp_path / "staging"
    staged = stage_reproducible_payload(
        repro=evidence, lock_manifest_path=paths["lock"], repository_root=paths["repo"],
        busybox=paths["first"], applet_list=paths["applets_a"], destination=staging,
    )
    assert staged.busybox_sha256 == evidence.busybox_sha256
    assert staged.init_sha256 == evidence.init_sha256
    assert (staging / "bin" / "sh").is_symlink()
    assert (staging / "sbin" / "mount").is_symlink()
    tampered = replace(evidence, busybox_sha256="0" * 64)
    with pytest.raises(RescuePayloadError, match="BusyBox bytes"):
        stage_reproducible_payload(
            repro=tampered, lock_manifest_path=paths["lock"], repository_root=paths["repo"],
            busybox=paths["first"], applet_list=paths["applets_a"], destination=tmp_path / "tampered-staging",
        )


def test_staging_rejects_lock_change_after_pair_verification(tmp_path: Path) -> None:
    paths = _write_contract(tmp_path)
    evidence = _verify(paths)
    raw = json.loads(paths["lock"].read_text(encoding="utf-8"))
    raw["build"]["source_date_epoch"] = 1
    paths["lock"].write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8", newline="\n")
    with pytest.raises(RescuePayloadError):
        stage_reproducible_payload(
            repro=evidence, lock_manifest_path=paths["lock"], repository_root=paths["repo"],
            busybox=paths["first"], applet_list=paths["applets_a"], destination=tmp_path / "drifted",
        )
