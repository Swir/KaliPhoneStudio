from dataclasses import replace
import tarfile

import pytest

from kaliphonestudio.provisioning import (
    FirstBootProvisioningPlan,
    build_first_boot_provisioning_bundle,
    create_first_boot_provisioning_plan,
    validate_first_boot_provisioning_plan,
    verify_first_boot_provisioning_bundle,
    write_first_boot_provisioning_evidence,
)
from kaliphonestudio.rootfs import RootfsArtifactEvidence, RootfsError


def rootfs_evidence(**changes):
    values = {
        "schema_version": 2,
        "source_lock_sha256": "1" * 64,
        "repository_snapshot_sha256": "2" * 64,
        "architecture": "arm64",
        "variant": "minimal",
        "artifact_sha256": "3" * 64,
        "artifact_size": 123456,
        "package_manifest_sha256": "4" * 64,
        "package_count": 269,
        "reproducible": True,
    }
    values.update(changes)
    return RootfsArtifactEvidence(**values)


def test_first_boot_bundle_is_deterministic_non_secret_and_rootfs_bound(tmp_path):
    rootfs = rootfs_evidence()
    plan = create_first_boot_provisioning_plan(
        rootfs,
        hostname="kali-phone",
        locale="pl_PL.UTF-8",
        timezone="Europe/Oslo",
    )

    first_path = tmp_path / "first.tar"
    second_path = tmp_path / "second.tar"
    first = build_first_boot_provisioning_bundle(plan, first_path)
    second = build_first_boot_provisioning_bundle(plan, second_path)

    assert first.bundle_sha256 == second.bundle_sha256
    assert first.bundle_size == second.bundle_size
    assert first.rootfs_evidence_sha256 == rootfs.evidence_sha256()
    assert first.provisioning_plan_sha256 == plan.plan_sha256()
    assert first.credentials_embedded is False
    assert first.remote_access_enabled is False
    assert first.hardware_verified is False
    assert first.beta_gate_credit is False
    assert first_path.read_bytes() == second_path.read_bytes()

    with tarfile.open(first_path, "r:") as archive:
        members = archive.getmembers()
        assert [item.name for item in members] == sorted(
            [
                "etc/hostname",
                "etc/locale.conf",
                "etc/systemd/system-preset/90-kaliphonestudio-firstboot.preset",
                "etc/timezone",
                "usr/share/kaliphonestudio/first-boot-provisioning.json",
            ]
        )
        for item in members:
            assert item.isfile()
            assert item.uid == 0
            assert item.gid == 0
            assert item.uname == "root"
            assert item.gname == "root"
            assert item.mtime == 0
            assert item.mode == 0o644
        assert archive.extractfile("etc/hostname").read() == b"kali-phone\n"
        assert archive.extractfile("etc/locale.conf").read() == b"LANG=pl_PL.UTF-8\n"
        assert archive.extractfile("etc/timezone").read() == b"Europe/Oslo\n"
        preset = archive.extractfile(
            "etc/systemd/system-preset/90-kaliphonestudio-firstboot.preset"
        ).read().decode()
        assert preset == "disable dropbear.service\ndisable ssh.service\ndisable sshd.service\n"
        manifest = archive.extractfile(
            "usr/share/kaliphonestudio/first-boot-provisioning.json"
        ).read().decode()
        assert manifest == plan.canonical_json()
        assert '"root_password_locked":true' in manifest
        assert "password_hash" not in manifest.lower()
        assert "password_plaintext" not in manifest.lower()
        assert "private_key" not in manifest.lower()


def test_plan_requires_reproducible_arm64_rootfs():
    with pytest.raises(RootfsError, match="reproducible rootfs evidence"):
        create_first_boot_provisioning_plan(rootfs_evidence(reproducible=False))
    with pytest.raises(RootfsError, match="ARM64"):
        create_first_boot_provisioning_plan(rootfs_evidence(architecture="amd64"))


def test_plan_rejects_malformed_rootfs_evidence_fields():
    for changes, match in (
        ({"source_lock_sha256": "bad"}, "rootfs source lock"),
        ({"repository_snapshot_sha256": "bad"}, "rootfs repository snapshot"),
        ({"artifact_sha256": "bad"}, "rootfs artifact"),
        ({"package_manifest_sha256": "bad"}, "rootfs package manifest"),
        ({"artifact_size": 0}, "artifact size"),
        ({"package_count": 0}, "package count"),
        ({"variant": ""}, "rootfs variant"),
    ):
        with pytest.raises(RootfsError, match=match):
            create_first_boot_provisioning_plan(rootfs_evidence(**changes))


def test_plan_rejects_unsafe_hostname_locale_and_timezone():
    rootfs = rootfs_evidence()
    for hostname in ("KaliPhone", "-bad", "bad_thing", "a" * 64):
        with pytest.raises(RootfsError, match="hostname"):
            create_first_boot_provisioning_plan(rootfs, hostname=hostname)

    for locale in ("pl", "pl_PL.UTF-8;evil", "../pl_PL.UTF-8"):
        with pytest.raises(RootfsError, match="locale"):
            create_first_boot_provisioning_plan(rootfs, locale=locale)

    for timezone in ("/etc/passwd", "Europe/../Oslo", "Europe//Oslo", "Europe/Oslo/", "Europe/Oslo;rm"):
        with pytest.raises(RootfsError, match="timezone"):
            create_first_boot_provisioning_plan(rootfs, timezone=timezone)


def test_plan_fails_closed_if_security_defaults_are_weakened():
    plan = create_first_boot_provisioning_plan(rootfs_evidence())
    with pytest.raises(RootfsError, match="interactive user setup"):
        validate_first_boot_provisioning_plan(
            replace(plan, interactive_user_setup_required=False)
        )
    with pytest.raises(RootfsError, match="root password locked"):
        validate_first_boot_provisioning_plan(replace(plan, root_password_locked=False))
    with pytest.raises(RootfsError, match="remote access"):
        validate_first_boot_provisioning_plan(replace(plan, remote_access_enabled=True))
    with pytest.raises(RootfsError, match="denylist drifted"):
        validate_first_boot_provisioning_plan(replace(plan, disabled_remote_units=()))
    with pytest.raises(RootfsError, match="cannot claim Beta credit"):
        validate_first_boot_provisioning_plan(replace(plan, beta_gate_credit=True))


def test_bundle_verifier_detects_plan_or_byte_substitution(tmp_path):
    plan = create_first_boot_provisioning_plan(rootfs_evidence(), hostname="kali-phone")
    bundle_path = tmp_path / "provisioning.tar"
    evidence = build_first_boot_provisioning_bundle(plan, bundle_path)

    changed_plan = replace(plan, hostname="kali-test")
    with pytest.raises(RootfsError, match="plan digest drifted"):
        verify_first_boot_provisioning_bundle(changed_plan, evidence, bundle_path)

    data = bytearray(bundle_path.read_bytes())
    data[0] ^= 0x01
    bundle_path.write_bytes(data)
    with pytest.raises(RootfsError, match="bytes do not match evidence"):
        verify_first_boot_provisioning_bundle(plan, evidence, bundle_path)


def test_bundle_verifier_rejects_malformed_evidence_fields(tmp_path):
    plan = create_first_boot_provisioning_plan(rootfs_evidence())
    bundle_path = tmp_path / "provisioning.tar"
    evidence = build_first_boot_provisioning_bundle(plan, bundle_path)

    with pytest.raises(RootfsError, match="bundle.*SHA-256"):
        verify_first_boot_provisioning_bundle(
            plan, replace(evidence, bundle_sha256="bad"), bundle_path
        )
    with pytest.raises(RootfsError, match="bundle size"):
        verify_first_boot_provisioning_bundle(
            plan, replace(evidence, bundle_size=0), bundle_path
        )
    with pytest.raises(RootfsError, match="member count"):
        verify_first_boot_provisioning_bundle(
            plan, replace(evidence, member_count=0), bundle_path
        )


def test_bundle_builder_and_evidence_writer_refuse_overwrite(tmp_path):
    plan = create_first_boot_provisioning_plan(rootfs_evidence())
    bundle = tmp_path / "provisioning.tar"
    evidence = build_first_boot_provisioning_bundle(plan, bundle)
    with pytest.raises(RootfsError, match="refusing to overwrite"):
        build_first_boot_provisioning_bundle(plan, bundle)

    evidence_path = tmp_path / "provisioning-evidence.json"
    assert write_first_boot_provisioning_evidence(evidence, evidence_path) == evidence.evidence_sha256()
    assert evidence_path.read_text(encoding="utf-8") == evidence.canonical_json()
    with pytest.raises(RootfsError, match="refusing to overwrite"):
        write_first_boot_provisioning_evidence(evidence, evidence_path)


def test_manual_plan_with_bad_rootfs_digest_is_rejected():
    plan = FirstBootProvisioningPlan(
        schema_version=1,
        rootfs_evidence_sha256="not-a-hash",
        architecture="arm64",
        hostname="kali-phone",
        locale="en_US.UTF-8",
        timezone="UTC",
        interactive_user_setup_required=True,
        root_password_locked=True,
        remote_access_enabled=False,
        disabled_remote_units=("dropbear.service", "ssh.service", "sshd.service"),
        beta_gate_credit=False,
    )
    with pytest.raises(RootfsError, match="rootfs evidence"):
        validate_first_boot_provisioning_plan(plan)
