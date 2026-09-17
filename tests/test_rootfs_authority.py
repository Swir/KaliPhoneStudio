from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path

import pytest

from kaliphonestudio.rootfs import RootfsArtifactEvidence, RootfsError, repository_snapshot_from_dict
from kaliphonestudio.rootfs_authority import (
    authority_from_dict,
    load_rootfs_authority,
    verify_rootfs_authority,
)

AUTHORITY_PATH = Path("evidence/authorities/kali-arm64-rootfs-2026.2-minimal.json")

SNAPSHOT = {
    "architecture": "arm64",
    "inrelease_sha256": "c5f9d9c614795d0c6f02b9d7e61c8748e9e49cdafe20c4be484d8fbb6e6322da",
    "mirror": "https://http.kali.org/kali",
    "package_indexes": [
        {"path": "contrib/binary-arm64/Packages", "sha256": "5f33e516d1323f36808a24da3b0cd387275650edfff29a7fdf26c284f686b53a", "size": 333745},
        {"path": "contrib/binary-arm64/Packages.gz", "sha256": "f3d41debccaba3570906fc7833e8b19ae98a9509f17d06ed1851ce84c8d7e3a2", "size": 100399},
        {"path": "main/binary-arm64/Packages", "sha256": "31f0662d2b7d1dd1a74cfaf371ac9ed6c5d4b85dce6ad2e4202fffcdc5cf33be", "size": 84060471},
        {"path": "main/binary-arm64/Packages.gz", "sha256": "48cc140302ae142c1dbd59c745c6c0be265bb32eb2c22e15f125bb2f1fb887d7", "size": 21397802},
        {"path": "non-free-firmware/binary-arm64/Packages", "sha256": "e129a38d1f15c9edd8a657021b292305b1cad74ae5d19bc357fe4d8a126195b8", "size": 70871},
        {"path": "non-free-firmware/binary-arm64/Packages.gz", "sha256": "e831fe31d152bc12b63abdace8dbe1b3627af0158ae14261ae7cdfb7b3fc40a3", "size": 15118},
        {"path": "non-free/binary-arm64/Packages", "sha256": "afc212b9b75684956ce635635e109071106881860b70edf6e9cce6f70fe23945", "size": 589117},
        {"path": "non-free/binary-arm64/Packages.gz", "sha256": "7ba245ad9a6f6acadd0909b2c652a3c9358c9067ff3f88a92cd40a988ad2d59f", "size": 142513},
    ],
    "schema_version": 2,
    "signing_key_fingerprint": "827C8569F2518CC677FECA1AED65462EC8D5E4C5",
    "suite": "kali-rolling",
}

BINDING = {
    "artifact_sha256": "133d5d806e09917c5a3e23293f8e3ad9d8daadab9a8c8d9f6d507179b06ddb1d",
    "artifact_size": 137460600,
    "beta_gate_credit": False,
    "canonicalization_a_evidence_sha256": "cc6352ab248cc22d9316adc1b2b3f2f110721a0a46059587dde2793ce03670ed",
    "canonicalization_b_evidence_sha256": "91919b1a8752bb267fe6e21ab2fc340d66b70bb0a4e559bb74647322bbe76116",
    "canonicalization_policy_sha256": "a39bb1d62cad430048c0458cea934ba925bf26d702b36ab78d7766a8339d5dd0",
    "package_count": 269,
    "package_manifest_sha256": "11a3609a23c263c43794414b7b2f2e587133fb247c2a146321c0bdef55db3fbd",
    "raw_a_sha256": "e8a1f72be757bcf115da395efc3f696cfe2a282caec6f4d743e2d7748ffd4062",
    "raw_a_size": 137478888,
    "raw_b_sha256": "37ce21e4fc258fbf2d577877fe7b354cd626927833401190b2c130cb28f0bba4",
    "raw_b_size": 137464640,
    "repository_snapshot_sha256": "323675aed3d35e9ce42e78417b28ccd43683bcde2c35bace37bbec29c6287908",
    "rootfs_evidence_sha256": "49694151e10234620e6135c59a9f895d895bffb66f01c9c26d53ae1a43b80ad5",
    "schema_version": 1,
    "source_lock_sha256": "80050ea91a797bf2779a0557ff53072940b9b2e17f9d710ca646a8e4d61bdaba",
    "strict_byte_identical": True,
}


def _rootfs_evidence() -> RootfsArtifactEvidence:
    return RootfsArtifactEvidence(
        schema_version=2,
        source_lock_sha256=BINDING["source_lock_sha256"],
        repository_snapshot_sha256=BINDING["repository_snapshot_sha256"],
        architecture="arm64",
        variant="minimal",
        artifact_sha256=BINDING["artifact_sha256"],
        artifact_size=BINDING["artifact_size"],
        package_manifest_sha256=BINDING["package_manifest_sha256"],
        package_count=BINDING["package_count"],
        reproducible=True,
    )


def test_checked_in_authority_verifies_complete_review_chain() -> None:
    authority = load_rootfs_authority(AUTHORITY_PATH)
    snapshot = repository_snapshot_from_dict(SNAPSHOT)
    verify_rootfs_authority(authority, _rootfs_evidence(), BINDING, snapshot)
    assert authority.authority_run_id == 35158577624
    assert authority.artifact_sha256 == BINDING["artifact_sha256"]
    assert authority.package_count == 269
    assert authority.strict_byte_identical is True
    assert authority.reviewed is True
    assert authority.hardware_verified is False
    assert authority.beta_gate_credit is False


def test_authority_rejects_beta_or_hardware_credit() -> None:
    authority = load_rootfs_authority(AUTHORITY_PATH)
    snapshot = repository_snapshot_from_dict(SNAPSHOT)
    with pytest.raises(RootfsError, match="Beta-gate credit"):
        verify_rootfs_authority(replace(authority, beta_gate_credit=True), _rootfs_evidence(), BINDING, snapshot)
    with pytest.raises(RootfsError, match="hardware verification"):
        verify_rootfs_authority(replace(authority, hardware_verified=True), _rootfs_evidence(), BINDING, snapshot)


def test_authority_rejects_tampered_binding() -> None:
    authority = load_rootfs_authority(AUTHORITY_PATH)
    snapshot = repository_snapshot_from_dict(SNAPSHOT)
    tampered = dict(BINDING)
    tampered["package_count"] = 268
    with pytest.raises(RootfsError, match="canonicalization-binding digest mismatch"):
        verify_rootfs_authority(authority, _rootfs_evidence(), tampered, snapshot)


def test_authority_rejects_tampered_rootfs_evidence() -> None:
    authority = load_rootfs_authority(AUTHORITY_PATH)
    snapshot = repository_snapshot_from_dict(SNAPSHOT)
    tampered = replace(_rootfs_evidence(), artifact_size=BINDING["artifact_size"] + 1)
    with pytest.raises(RootfsError, match="rootfs-evidence digest"):
        verify_rootfs_authority(authority, tampered, BINDING, snapshot)


def test_authority_schema_is_exact_and_fail_closed() -> None:
    authority = load_rootfs_authority(AUTHORITY_PATH)
    raw = asdict(authority)
    raw["unexpected"] = "field"
    with pytest.raises(RootfsError, match="authority record fields"):
        authority_from_dict(raw)
