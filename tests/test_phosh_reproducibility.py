from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from kaliphonestudio.phosh_reproducibility import (
    PhoshReproducibilityError,
    compare_phosh_rootfs_builds,
    load_phosh_rootfs_build_evidence,
    write_phosh_rootfs_reproducibility_candidate,
)


def _build_payload(
    *,
    artifact_sha256: str = "4" * 64,
    artifact_size: int = 512 * 1024 * 1024,
    package_manifest_sha256: str = "5" * 64,
    package_count: int = 600,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "upstream_commit": "8" * 40,
        "source_lock_sha256": "1" * 64,
        "build_contract_sha256": "2" * 64,
        "build_plan_sha256": "3" * 64,
        "artifact_sha256": artifact_sha256,
        "artifact_size": artifact_size,
        "package_manifest_sha256": package_manifest_sha256,
        "package_count": package_count,
        "phosh_package_contract_satisfied": True,
        "reproducibility_authority": False,
        "physical_validation_required": True,
        "hardware_verified": False,
        "beta_gate_credit": False,
    }


def _write(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def test_identical_independent_builds_create_non_authoritative_candidate(tmp_path: Path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    _write(a, _build_payload())
    _write(b, _build_payload())

    evidence = compare_phosh_rootfs_builds(
        a,
        b,
        build_a_origin="github-actions/run-123/build-a",
        build_b_origin="github-actions/run-123/build-b",
    )

    assert evidence.strict_byte_identical is True
    assert evidence.package_manifest_identical is True
    assert evidence.review_required is True
    assert evidence.reproducibility_authority is False
    assert evidence.physical_validation_required is True
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False

    out = tmp_path / "candidate.json"
    digest = write_phosh_rootfs_reproducibility_candidate(evidence, out)
    assert len(digest) == 64
    assert out.read_text(encoding="utf-8") == evidence.canonical_json()


def test_duplicate_build_origin_fails_closed(tmp_path: Path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    _write(a, _build_payload())
    _write(b, _build_payload())
    with pytest.raises(PhoshReproducibilityError, match="distinct build origins"):
        compare_phosh_rootfs_builds(a, b, build_a_origin="run/a", build_b_origin="run/a")


def test_artifact_drift_fails_closed(tmp_path: Path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    _write(a, _build_payload())
    _write(b, _build_payload(artifact_sha256="9" * 64))
    with pytest.raises(PhoshReproducibilityError, match="not byte-identical"):
        compare_phosh_rootfs_builds(a, b, build_a_origin="run/a", build_b_origin="run/b")


def test_package_manifest_drift_fails_closed(tmp_path: Path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    _write(a, _build_payload())
    _write(b, _build_payload(package_manifest_sha256="9" * 64))
    with pytest.raises(PhoshReproducibilityError, match="package manifests"):
        compare_phosh_rootfs_builds(a, b, build_a_origin="run/a", build_b_origin="run/b")


def test_build_identity_drift_fails_closed(tmp_path: Path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    payload_b = _build_payload()
    payload_b["build_plan_sha256"] = "9" * 64
    _write(a, _build_payload())
    _write(b, payload_b)
    with pytest.raises(PhoshReproducibilityError, match="build identity mismatch"):
        compare_phosh_rootfs_builds(a, b, build_a_origin="run/a", build_b_origin="run/b")


def test_promoted_single_build_evidence_is_rejected(tmp_path: Path):
    path = tmp_path / "build.json"
    payload = _build_payload()
    payload["reproducibility_authority"] = True
    _write(path, payload)
    with pytest.raises(PhoshReproducibilityError, match="cannot already be authoritative"):
        load_phosh_rootfs_build_evidence(path)


def test_noncanonical_build_evidence_is_rejected(tmp_path: Path):
    path = tmp_path / "build.json"
    path.write_text(json.dumps(_build_payload(), indent=2) + "\n", encoding="utf-8")
    with pytest.raises(PhoshReproducibilityError, match="canonical JSON"):
        load_phosh_rootfs_build_evidence(path)


def test_candidate_cannot_be_promoted_by_dataclass_mutation(tmp_path: Path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    _write(a, _build_payload())
    _write(b, _build_payload())
    evidence = compare_phosh_rootfs_builds(a, b, build_a_origin="run/a", build_b_origin="run/b")
    with pytest.raises(PhoshReproducibilityError, match="cannot grant authority"):
        write_phosh_rootfs_reproducibility_candidate(
            replace(evidence, reproducibility_authority=True),
            tmp_path / "out.json",
        )
