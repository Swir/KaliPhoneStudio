from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import io
import json
from pathlib import Path
import tarfile

import pytest

from kaliphonestudio import rootfs_member_manifest as member_manifest_module
from kaliphonestudio.phosh_repro_diagnostics import (
    PhoshReproDiagnosticError,
    diagnose_phosh_rootfs_builds,
    write_phosh_rootfs_reproducibility_diagnostic,
)
from kaliphonestudio.rootfs import RootfsError
from kaliphonestudio.rootfs_member_manifest import (
    build_rootfs_member_manifest,
    write_rootfs_member_manifest,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")


def _build(artifact: str, size: int = 100) -> dict[str, object]:
    return {
        "schema_version": 1, "upstream_commit": "8" * 40,
        "source_lock_sha256": "1" * 64, "build_contract_sha256": "2" * 64,
        "build_plan_sha256": "3" * 64, "artifact_sha256": artifact,
        "artifact_size": size, "package_manifest_sha256": "5" * 64,
        "package_count": 600, "phosh_package_contract_satisfied": True,
        "reproducibility_authority": False, "physical_validation_required": True,
        "hardware_verified": False, "beta_gate_credit": False,
    }


def _entry(index: int, path: str, content: str = "a") -> dict[str, object]:
    return {
        "index": index, "path": path, "type_hex": "30", "mode": 420,
        "uid": 0, "gid": 0, "uname": "root", "gname": "root", "linkname": "",
        "size": 1, "devmajor": 0, "devminor": 0, "pax_headers": [],
        "content_sha256": sha256(content.encode()).hexdigest(),
    }


def _manifest(artifact: str, entries: list[dict[str, object]], size: int = 100) -> dict[str, object]:
    return {
        "schema_version": 1, "artifact_sha256": artifact, "artifact_size": size,
        "member_count": len(entries), "entries": entries, "diagnostic_only": True,
        "reproducibility_authority": False, "hardware_verified": False,
        "beta_gate_credit": False,
    }


def _inputs(tmp_path: Path, *, artifact_a: str = "a" * 64, artifact_b: str = "b" * 64,
            entries_a: list[dict[str, object]] | None = None,
            entries_b: list[dict[str, object]] | None = None):
    entries_a = entries_a or [_entry(0, "root/a"), _entry(1, "root/b")]
    entries_b = entries_b or [_entry(0, "root/a"), _entry(1, "root/b")]
    paths = [tmp_path / name for name in ("a-build.json", "b-build.json", "a-members.json", "b-members.json")]
    _write_json(paths[0], _build(artifact_a)); _write_json(paths[1], _build(artifact_b))
    _write_json(paths[2], _manifest(artifact_a, entries_a)); _write_json(paths[3], _manifest(artifact_b, entries_b))
    return tuple(paths)


def _add_file(archive: tarfile.TarFile, name: str, data: bytes, *, mtime: int = 0) -> None:
    info = tarfile.TarInfo(name); info.size = len(data); info.mode = 0o644
    info.uid = info.gid = 0; info.uname = info.gname = "root"; info.mtime = mtime
    archive.addfile(info, io.BytesIO(data))


def test_member_manifest_records_order_content_and_create_only(tmp_path: Path):
    rootfs = tmp_path / "rootfs.tar.xz"
    with tarfile.open(rootfs, "w:xz", format=tarfile.PAX_FORMAT) as archive:
        _add_file(archive, "kali-arm64/var/lib/dpkg/status", b"Package: base-files\n")
        _add_file(archive, "kali-arm64/usr/bin/demo", b"payload\n")
    manifest = build_rootfs_member_manifest(rootfs)
    assert [entry.path for entry in manifest.entries] == ["kali-arm64/var/lib/dpkg/status", "kali-arm64/usr/bin/demo"]
    assert all(entry.content_sha256 for entry in manifest.entries)
    assert manifest.diagnostic_only is True and manifest.reproducibility_authority is False
    out = tmp_path / "members.json"; assert len(write_rootfs_member_manifest(manifest, out)) == 64
    with pytest.raises(RootfsError, match="overwrite"):
        write_rootfs_member_manifest(manifest, out)


def test_member_manifest_streams_xz_once_and_enforces_member_bound(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    rootfs = tmp_path / "stream.tar.xz"
    with tarfile.open(rootfs, "w:xz", format=tarfile.PAX_FORMAT) as archive:
        for index in range(3):
            _add_file(archive, f"kali-arm64/usr/share/demo-{index}", b"x")

    real_open = tarfile.open
    observed_modes: list[str | None] = []

    def tracking_open(*args, **kwargs):
        mode = kwargs.get("mode")
        if mode is None and len(args) > 1:
            mode = args[1]
        observed_modes.append(mode)
        return real_open(*args, **kwargs)

    monkeypatch.setattr(member_manifest_module.tarfile, "open", tracking_open)
    manifest = build_rootfs_member_manifest(rootfs)
    assert manifest.member_count == 3
    assert observed_modes == ["r|xz"]

    monkeypatch.setattr(member_manifest_module, "_MAX_MEMBERS", 2)
    with pytest.raises(RootfsError, match="too many members"):
        build_rootfs_member_manifest(rootfs)


def test_member_manifest_serialized_size_bound_is_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    rootfs = tmp_path / "bounded.tar.xz"
    with tarfile.open(rootfs, "w:xz", format=tarfile.PAX_FORMAT) as archive:
        _add_file(archive, "kali-arm64/usr/bin/demo", b"payload\n")
    manifest = build_rootfs_member_manifest(rootfs)
    monkeypatch.setattr(member_manifest_module, "_MAX_MANIFEST_BYTES", 16)
    with pytest.raises(RootfsError, match="unexpectedly large"):
        write_rootfs_member_manifest(manifest, tmp_path / "too-large.json")


def test_member_manifest_rejects_noncanonical_or_unsafe_input(tmp_path: Path):
    bad = tmp_path / "bad.tar.xz"
    with tarfile.open(bad, "w:xz") as archive:
        _add_file(archive, "kali-arm64/etc/bad\nname", b"x")
    with pytest.raises(RootfsError, match="invalid member name"):
        build_rootfs_member_manifest(bad)
    bad2 = tmp_path / "mtime.tar.xz"
    with tarfile.open(bad2, "w:xz") as archive:
        _add_file(archive, "kali-arm64/etc/demo", b"x", mtime=1)
    with pytest.raises(RootfsError, match="nonzero mtime"):
        build_rootfs_member_manifest(bad2)


def test_diagnostic_classifies_encoding_order_and_content_drift(tmp_path: Path):
    encoding = diagnose_phosh_rootfs_builds(*_inputs(tmp_path))
    assert encoding.archive_encoding_only_difference is True
    assert encoding.differing_member_count == 0

    order_dir = tmp_path / "order"; order_dir.mkdir()
    order = diagnose_phosh_rootfs_builds(*_inputs(order_dir, entries_a=[_entry(0, "root/a"), _entry(1, "root/b")], entries_b=[_entry(0, "root/b"), _entry(1, "root/a")]))
    assert order.ordering_only_difference is True and order.member_records_identical is True

    content_dir = tmp_path / "content"; content_dir.mkdir()
    content = diagnose_phosh_rootfs_builds(*_inputs(content_dir, entries_a=[_entry(0, "root/a")], entries_b=[_entry(0, "root/a", "z")]))
    assert content.differences[0].path == "root/a"
    assert content.differences[0].fields == ("content_sha256",)


def test_diagnostic_rejects_detached_unsafe_or_invalid_metadata(tmp_path: Path):
    a, b, ma, mb = _inputs(tmp_path)
    raw = json.loads(ma.read_text()); raw["artifact_sha256"] = "c" * 64; _write_json(ma, raw)
    with pytest.raises(PhoshReproDiagnosticError, match="detached"):
        diagnose_phosh_rootfs_builds(a, b, ma, mb)

    unsafe = tmp_path / "unsafe"; unsafe.mkdir()
    with pytest.raises(PhoshReproDiagnosticError, match="control characters"):
        diagnose_phosh_rootfs_builds(*_inputs(unsafe, entries_a=[_entry(0, "root/bad\npath")], entries_b=[_entry(0, "root/bad\npath")]))

    invalid = tmp_path / "invalid"; invalid.mkdir(); entry = _entry(0, "root/a"); entry["size"] = -1
    with pytest.raises(PhoshReproDiagnosticError, match="non-negative integer"):
        diagnose_phosh_rootfs_builds(*_inputs(invalid, entries_a=[entry], entries_b=[entry]))


def test_diagnostic_writer_is_create_only_and_non_promoting(tmp_path: Path):
    diagnostic = diagnose_phosh_rootfs_builds(*_inputs(tmp_path))
    out = tmp_path / "diag.json"; assert len(write_phosh_rootfs_reproducibility_diagnostic(diagnostic, out)) == 64
    with pytest.raises(PhoshReproDiagnosticError, match="overwrite"):
        write_phosh_rootfs_reproducibility_diagnostic(diagnostic, out)
    with pytest.raises(PhoshReproDiagnosticError, match="cannot promote"):
        write_phosh_rootfs_reproducibility_diagnostic(replace(diagnostic, beta_gate_credit=True), tmp_path / "bad.json")
