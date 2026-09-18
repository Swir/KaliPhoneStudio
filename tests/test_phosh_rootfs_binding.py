from __future__ import annotations

from dataclasses import asdict, replace
from hashlib import sha256
from pathlib import Path

import pytest

from kaliphonestudio.phosh import load_phosh_source_lock
from kaliphonestudio.phosh_rootfs_binding import (
    PhoshRootfsBindingError,
    build_phosh_rootfs_authority_binding,
    build_phosh_rootfs_authority_binding_from_paths,
    load_phosh_rootfs_authority_binding,
    validate_phosh_rootfs_authority_binding,
    write_phosh_rootfs_authority_binding,
)
from kaliphonestudio.rootfs_authority import authority_from_dict


LOCK_PATH = Path("tools/phosh-source-lock.json")


def _manifest() -> bytes:
    lock = load_phosh_source_lock(LOCK_PATH)
    lines = [
        f"{package}\t1.0-kps\t{'all' if package == 'webext-ublock-origin-firefox' else 'arm64'}"
        for package in lock.required_packages
    ]
    lines.append("base-files\t13.8+deb13u1\tarm64")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _authority(payload: bytes, *, artifact_sha: str = "a" * 64):
    return authority_from_dict(
        {
            "schema_version": 1,
            "authority_name": "kali-arm64-phosh-test",
            "authority_run_id": 101,
            "authority_commit": "b" * 40,
            "authority_artifact_id": 202,
            "release_tag": "kali-rolling-phosh-test",
            "architecture": "arm64",
            "variant": "full",
            "source_lock_sha256": "1" * 64,
            "repository_snapshot_sha256": "2" * 64,
            "inrelease_sha256": "3" * 64,
            "rootfs_evidence_sha256": "4" * 64,
            "canonicalization_binding_sha256": "5" * 64,
            "canonicalization_policy_sha256": "6" * 64,
            "canonicalization_a_evidence_sha256": "7" * 64,
            "canonicalization_b_evidence_sha256": "8" * 64,
            "raw_a_sha256": "9" * 64,
            "raw_a_size": 4096,
            "raw_b_sha256": "c" * 64,
            "raw_b_size": 4096,
            "artifact_sha256": artifact_sha,
            "artifact_size": 8192,
            "package_manifest_sha256": sha256(payload).hexdigest(),
            "package_count": len(payload.decode("utf-8").splitlines()),
            "strict_byte_identical": True,
            "reviewed": True,
            "hardware_verified": False,
            "beta_gate_credit": False,
        }
    )


def test_exact_phosh_manifest_binds_to_reviewed_rootfs_without_hardware_credit():
    lock = load_phosh_source_lock(LOCK_PATH)
    payload = _manifest()
    authority = _authority(payload)

    evidence = build_phosh_rootfs_authority_binding(lock, authority, payload)

    assert evidence.phosh_source_lock_sha256 == lock.lock_sha256()
    assert evidence.phosh_upstream_commit == lock.upstream_commit
    assert evidence.rootfs_authority_sha256 == authority.authority_sha256()
    assert evidence.rootfs_artifact_sha256 == authority.artifact_sha256
    assert evidence.package_manifest_sha256 == authority.package_manifest_sha256
    assert evidence.package_count == authority.package_count
    assert evidence.required_packages == lock.required_packages
    assert tuple(item[0] for item in evidence.installed_required_packages) == lock.required_packages
    assert evidence.host_userspace_package_contract_satisfied is True
    assert evidence.rootfs_authority_reviewed is True
    assert evidence.ready_for_physical_candidate_binding is True
    assert evidence.physical_validation_required is True
    assert evidence.display_verified is False
    assert evidence.touch_verified is False
    assert evidence.hardware_verified is False
    assert evidence.beta_release_authorized is False
    assert evidence.beta_gate_credit is False


def test_manifest_digest_drift_from_reviewed_authority_fails_closed():
    lock = load_phosh_source_lock(LOCK_PATH)
    payload = _manifest()
    authority = _authority(payload)
    drifted = payload + b"extra-test-package\t1.0\tarm64\n"

    with pytest.raises(PhoshRootfsBindingError, match="digest differs"):
        build_phosh_rootfs_authority_binding(lock, authority, drifted)


def test_package_count_drift_from_reviewed_authority_fails_closed():
    lock = load_phosh_source_lock(LOCK_PATH)
    payload = _manifest()
    raw = asdict(_authority(payload))
    raw["package_count"] += 1
    authority = authority_from_dict(raw)

    with pytest.raises(PhoshRootfsBindingError, match="package count differs"):
        build_phosh_rootfs_authority_binding(lock, authority, payload)


def test_missing_required_phosh_package_fails_closed_even_if_authority_matches_bytes():
    lock = load_phosh_source_lock(LOCK_PATH)
    payload = _manifest()
    text = payload.decode("utf-8")
    filtered = "\n".join(
        line for line in text.splitlines() if not line.startswith("mobian-phosh-phone\t")
    ).encode("utf-8") + b"\n"
    authority = _authority(filtered)

    with pytest.raises(PhoshRootfsBindingError, match="missing required Phosh packages"):
        build_phosh_rootfs_authority_binding(lock, authority, filtered)


def test_wrong_package_architecture_fails_closed():
    lock = load_phosh_source_lock(LOCK_PATH)
    payload = _manifest().replace(b"mobian-phosh\t1.0-kps\tarm64", b"mobian-phosh\t1.0-kps\tamd64")
    authority = _authority(payload)

    with pytest.raises(PhoshRootfsBindingError, match="unexpected architecture"):
        build_phosh_rootfs_authority_binding(lock, authority, payload)


def test_binding_validator_rejects_any_promotion():
    lock = load_phosh_source_lock(LOCK_PATH)
    payload = _manifest()
    evidence = build_phosh_rootfs_authority_binding(lock, _authority(payload), payload)

    for field in ("display_verified", "touch_verified", "hardware_verified", "beta_release_authorized", "beta_gate_credit"):
        with pytest.raises(PhoshRootfsBindingError, match="cannot promote"):
            validate_phosh_rootfs_authority_binding(replace(evidence, **{field: True}))


def test_binding_write_load_roundtrip_is_canonical_and_no_overwrite(tmp_path: Path):
    lock = load_phosh_source_lock(LOCK_PATH)
    payload = _manifest()
    evidence = build_phosh_rootfs_authority_binding(lock, _authority(payload), payload)
    target = tmp_path / "phosh-rootfs-binding.json"

    digest = write_phosh_rootfs_authority_binding(evidence, target)
    loaded = load_phosh_rootfs_authority_binding(target)

    assert digest == evidence.evidence_sha256()
    assert loaded == evidence
    assert target.read_bytes() == evidence.canonical_json().encode("utf-8")
    with pytest.raises(PhoshRootfsBindingError, match="refusing to overwrite"):
        write_phosh_rootfs_authority_binding(evidence, target)


def test_path_builder_rejects_symlinked_package_manifest(tmp_path: Path):
    payload = _manifest()
    authority = _authority(payload)
    authority_path = tmp_path / "authority.json"
    authority_path.write_text(authority.canonical_json(), encoding="utf-8")
    real_manifest = tmp_path / "manifest.txt"
    real_manifest.write_bytes(payload)
    linked_manifest = tmp_path / "manifest-link.txt"
    linked_manifest.symlink_to(real_manifest)

    with pytest.raises(PhoshRootfsBindingError, match="regular non-symlink"):
        build_phosh_rootfs_authority_binding_from_paths(
            LOCK_PATH,
            authority_path,
            linked_manifest,
        )
