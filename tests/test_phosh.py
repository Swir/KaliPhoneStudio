from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from kaliphonestudio.phosh import (
    PhoshError,
    evaluate_phosh_package_manifest,
    load_phosh_source_lock,
    parse_debos_package_recipe,
    parse_disabled_services,
    verify_phosh_source_bytes,
    verify_phosh_source_tree,
)


LOCK = Path("tools/phosh-source-lock.json")

ROOTFS = b'{{- $architecture := or .architecture "arm64" -}}\n{{- $username := or .username "kali" -}}\n{{- $password := or .password "1234" -}}\n{{- $hostname := or .hostname "kali" -}}\n{{- $environment := or .environment "phosh" -}}\n{{- $contrib := or .contrib "true" -}}\n{{- $nonfree := or .nonfree "false" -}}\n{{- $ssh := or .ssh "" -}}\n{{- $zram:= or .zram "false" -}}\n{{- $debian_suite := or .debian_suite "kali-rolling" -}}\n{{- $suite := or .suite $debian_suite -}}\n{{- $rootfs := or .rootfs "rootfs.tar.xz" }}\n{{- $mirror := or .mirror "http://kali.download/kali" -}}\n\narchitecture: {{ $architecture }}\n\nactions:\n  - action: debootstrap\n    suite: {{ $debian_suite }}\n    components:\n      - main\n{{ if eq $contrib "true" }}\n      - contrib\n{{ end }}\n{{ if eq $nonfree "true" }}\n      - non-free\n      - non-free-firmware\n{{ end }}\n    mirror: {{ $mirror }}\n    variant: minbase\n    keyring-file: kali-archive-keyring.gpg\n    keyring-package: kali-archive-keyring\n    #check-gpg: false\n\n  - action: apt\n    recommends: true\n    description: Install mobian-archive-keyring\n    packages:\n      - ca-certificates\n      - mobian-archive-keyring\n\n  - action: overlay\n    description: Enable resize of root partition\n    source: overlays/repart.d/\n    destination: /etc/repart.d/\n\n  - action: overlay\n    description: Disable Kali motd during boot\n    source: overlays/kali-motd/\n    destination: /etc/kali-motd/\n\n  - action: overlay\n    description: Add improved Squeekboard terminal layout\n    source: overlays/skel/\n    destination: /etc/skel/\n\n  - action: run\n    description: Setup Mobian repository\n    chroot: true\n    script: scripts/setup-apt.sh {{ $debian_suite }} {{ $suite }}\n\n{{ if eq $nonfree "true" }}\n  - action: run\n    description: Enable non-free-firmware repos\n    chroot: true\n    script: scripts/setup-apt-nonfree.sh true\n{{ end }}\n\n  - action: recipe\n    recipe: include/packages-base.yaml\n    variables:\n      ssh: {{ $ssh }}\n\n  - action: recipe\n    recipe: include/packages-{{ $environment }}.yaml\n\n  - action: run\n    description: Set up default user\n    chroot: true\n    script: scripts/setup-user.sh {{ $username }} {{ $password }}\n\n{{ if $ssh }}\n  - action: overlay\n    description: Set up sshd configuration\n    source: overlays/sshd_config.d/\n    destination: /etc/ssh/sshd_config.d/\n\n  - action: overlay\n    description: Set up user\'s ssh configuration\n    source: overlays/ssh/\n    destination: /home/{{ $username }}/.ssh/\n\n  - action: run\n    description: Set owner of .ssh\n    chroot: true\n    command: chown -R {{ $username }}:{{ $username }} /home/{{ $username }}/.ssh/\n{{ end }}\n\n{{ if eq $zram "true" }}\n  - action: overlay\n    description: setup zram devices\n    source: overlays/zram/\n    destination: /etc/\n{{ end }}\n\n  - action: run\n    description: Set up system\n    chroot: true\n    script: scripts/setup-system.sh {{ $hostname }}\n\n  - action: pack\n    file: {{ $rootfs }}\n    compression: xz\n'
COMMON = b'{{- $architecture := or .architecture "arm64" -}}\n\narchitecture: {{ $architecture }}\n\nactions:\n  - action: apt\n    recommends: false\n    description: Install Phosh packages\n    packages:\n      - mobian-phosh\n      # Additional software we don\'t want metapackages to depend on\n      - firefox-esr\n      - gnome-sound-recorder\n      - loupe\n      - powersupply-gtk\n      - webext-ublock-origin-firefox\n      - squeekboard\n      - nethunter\n      - hijacker\n      - kalitorify\n\n  - action: run\n    description: Disable getty in the Phosh environment\n    chroot: true\n    command: systemctl disable getty@.service\n'
QCOM = b'{{- $architecture := or .architecture "arm64" -}}\n{{- $device := or .device "sdm845" }}\n\narchitecture: {{ $architecture }}\n\nactions:\n  - action: apt\n    recommends: false\n    description: Install device-specific packages for Phosh\n    packages:\n      - gnome-snapshot\n      - firefox-esr-mobile-config\n      - mobian-phosh-phone\n'


def files():
    return {
        "rootfs.yaml": ROOTFS,
        "include/packages-phosh.yaml": COMMON,
        "devices/qcom/packages-phosh.yaml": QCOM,
    }


def test_lock_is_pinned_fail_closed_and_non_promoting():
    lock = load_phosh_source_lock(LOCK)
    assert len(lock.upstream_commit) == 40
    assert lock.architecture == "arm64"
    assert lock.environment == "phosh"
    assert lock.family == "qcom"
    assert lock.physical_validation_required is True
    assert lock.hardware_verified is False
    assert lock.beta_gate_credit is False
    assert "mobian-phosh" in lock.required_packages
    assert "mobian-phosh-phone" in lock.required_packages
    assert "squeekboard" in lock.required_packages


def test_locked_upstream_bytes_verify_exactly():
    lock = load_phosh_source_lock(LOCK)
    evidence = verify_phosh_source_bytes(lock, files())
    assert evidence.source_verified is True
    assert evidence.upstream_commit == lock.upstream_commit
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False
    assert dict(evidence.verified_files)["rootfs.yaml"] == sha256(ROOTFS).hexdigest()


def test_recipe_parsing_matches_locked_upstream_contract():
    assert parse_debos_package_recipe(COMMON)[0] == "mobian-phosh"
    assert "squeekboard" in parse_debos_package_recipe(COMMON)
    assert parse_disabled_services(COMMON) == ("getty@.service",)
    assert parse_debos_package_recipe(QCOM) == (
        "gnome-snapshot",
        "firefox-esr-mobile-config",
        "mobian-phosh-phone",
    )
    assert parse_disabled_services(QCOM) == ()


def test_upstream_content_drift_fails_closed():
    lock = load_phosh_source_lock(LOCK)
    changed = files()
    changed["include/packages-phosh.yaml"] = COMMON + b"\n# drift\n"
    with pytest.raises(PhoshError, match="SHA-256 mismatch"):
        verify_phosh_source_bytes(lock, changed)


def test_missing_or_extra_source_file_fails_closed():
    lock = load_phosh_source_lock(LOCK)
    missing = files()
    missing.pop("rootfs.yaml")
    with pytest.raises(PhoshError, match="source set mismatch"):
        verify_phosh_source_bytes(lock, missing)
    extra = files()
    extra["README.md"] = b"not locked"
    with pytest.raises(PhoshError, match="source set mismatch"):
        verify_phosh_source_bytes(lock, extra)


def test_symlinked_source_is_rejected(tmp_path: Path):
    lock = load_phosh_source_lock(LOCK)
    real_root = tmp_path / "real"
    source_root = tmp_path / "src"
    real_root.mkdir()
    source_root.mkdir()
    for path, data in files().items():
        target = real_root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        link = source_root / path
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(target)
    with pytest.raises(PhoshError, match="missing or unsafe"):
        verify_phosh_source_tree(lock, source_root)


def test_manifest_evidence_reports_complete_host_package_contract_without_hardware_credit():
    lock = load_phosh_source_lock(LOCK)
    lines = [
        f"{package}\t1.0-test\t{'all' if package == 'webext-ublock-origin-firefox' else 'arm64'}"
        for package in lock.required_packages
    ]
    lines.append("base-files\t13.8+deb13u1\tarm64")
    payload = ("\n".join(sorted(lines)) + "\n").encode()
    evidence = evaluate_phosh_package_manifest(
        lock, payload, rootfs_artifact_sha256="1" * 64
    )
    assert evidence.host_userspace_package_contract_satisfied is True
    assert evidence.missing_packages == ()
    assert len(evidence.installed_required_packages) == len(lock.required_packages)
    assert evidence.physical_validation_required is True
    assert evidence.display_verified is False
    assert evidence.touch_verified is False
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False


def test_manifest_missing_mobile_package_is_not_complete():
    lock = load_phosh_source_lock(LOCK)
    packages = [package for package in lock.required_packages if package != "mobian-phosh-phone"]
    payload = ("\n".join(f"{package}\t1.0\tarm64" for package in packages) + "\n").encode()
    evidence = evaluate_phosh_package_manifest(
        lock, payload, rootfs_artifact_sha256="2" * 64
    )
    assert evidence.host_userspace_package_contract_satisfied is False
    assert evidence.missing_packages == ("mobian-phosh-phone",)
    assert evidence.hardware_verified is False


def test_manifest_wrong_architecture_fails_closed():
    lock = load_phosh_source_lock(LOCK)
    lines = [
        f"{package}\t1.0\t{'amd64' if package == 'mobian-phosh' else 'arm64'}"
        for package in lock.required_packages
    ]
    with pytest.raises(PhoshError, match="unexpected architecture"):
        evaluate_phosh_package_manifest(
            lock,
            ("\n".join(lines) + "\n").encode(),
            rootfs_artifact_sha256="3" * 64,
        )


def test_lock_cannot_promote_hardware_or_beta(tmp_path: Path):
    raw = json.loads(LOCK.read_text(encoding="utf-8"))
    raw["policy"]["hardware_verified"] = True
    path = tmp_path / "bad-lock.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(PhoshError, match="cannot grant hardware/Beta credit"):
        load_phosh_source_lock(path)
