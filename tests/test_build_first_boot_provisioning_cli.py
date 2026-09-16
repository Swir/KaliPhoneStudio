import json
from pathlib import Path
import subprocess
import sys

from kaliphonestudio.rootfs import RootfsArtifactEvidence


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "build_first_boot_provisioning.py"


def rootfs_evidence():
    return RootfsArtifactEvidence(
        schema_version=2,
        source_lock_sha256="1" * 64,
        repository_snapshot_sha256="2" * 64,
        architecture="arm64",
        variant="minimal",
        artifact_sha256="3" * 64,
        artifact_size=123456,
        package_manifest_sha256="4" * 64,
        package_count=269,
        reproducible=True,
    )


def test_cli_builds_bundle_and_machine_readable_safety_evidence(tmp_path):
    rootfs_path = tmp_path / "rootfs-evidence.json"
    rootfs_path.write_text(rootfs_evidence().canonical_json(), encoding="utf-8")
    bundle = tmp_path / "firstboot.tar"
    evidence = tmp_path / "firstboot-evidence.json"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--rootfs-evidence",
            str(rootfs_path),
            "--out",
            str(bundle),
            "--evidence",
            str(evidence),
            "--hostname",
            "kali-phone",
            "--locale",
            "pl_PL.UTF-8",
            "--timezone",
            "Europe/Oslo",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["schema_version"] == 1
    assert output["credentials_embedded"] is False
    assert output["remote_access_enabled"] is False
    assert output["hardware_verified"] is False
    assert output["beta_gate_credit"] is False
    assert len(output["bundle_sha256"]) == 64
    assert len(output["evidence_sha256"]) == 64
    assert bundle.is_file()
    assert evidence.is_file()


def test_cli_fails_closed_on_non_reproducible_rootfs_evidence(tmp_path):
    rootfs = rootfs_evidence()
    raw = json.loads(rootfs.canonical_json())
    raw["reproducible"] = False
    rootfs_path = tmp_path / "rootfs-evidence.json"
    rootfs_path.write_text(json.dumps(raw), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--rootfs-evidence",
            str(rootfs_path),
            "--out",
            str(tmp_path / "firstboot.tar"),
            "--evidence",
            str(tmp_path / "firstboot-evidence.json"),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "not reproducible" in result.stderr.lower() or "reproducible" in result.stderr.lower()
    assert not (tmp_path / "firstboot.tar").exists()
    assert not (tmp_path / "firstboot-evidence.json").exists()
