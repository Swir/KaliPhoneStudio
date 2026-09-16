from hashlib import sha256
from pathlib import Path

import pytest

from kaliphonestudio.boot_authorization import authorize_temporary_boot, write_temporary_boot_authorization
from kaliphonestudio.boot_builder import BootAssemblyEvidence, BootRoundTripEvidence, create_boot_build_plan
from kaliphonestudio.boot_image import BootImageError
from kaliphonestudio.fastboot_baseline import FastbootBaselineEvidence
from kaliphonestudio.profiles import get_profile
from kaliphonestudio.provenance import StockBootProvenance
from kaliphonestudio.safety import SafetyError, VerifiedDevice

ROOT = Path(__file__).parents[1]
PROFILE = get_profile(ROOT / "devices", "oneplus/avicii")
FINGERPRINT = "OnePlus/avicii/avicii:13/test/F.22:user/release-keys"
BUILD = "AC2003_11_F.22"


def provenance():
    return StockBootProvenance(
        schema_version=1,
        profile_id=PROFILE.profile_id,
        ota_sha256="a" * 64,
        ota_size=10,
        payload_sha256="b" * 64,
        payload_metadata_sha256="c" * 64,
        payload_size=9,
        boot_sha256="d" * 64,
        boot_size=4096,
        boot_header_version=2,
        firmware_metadata={
            "post-build": FINGERPRINT,
            "post-build-incremental": BUILD,
        },
    )


def baseline(**changes):
    values = {
        "schema_version": 1,
        "profile_id": PROFILE.profile_id,
        "transcript_sha256": "e" * 64,
        "transcript_size": 1024,
        "firmware_build": BUILD,
        "firmware_fingerprint": FINGERPRINT,
        "product": "avicii",
        "serialno": "SERIAL123",
        "current_slot": "a",
        "slot_count": 2,
        "unlocked": False,
        "secure": True,
        "bootloader_version": "bootloader-test",
        "baseband_version": "baseband-test",
        "variables": {"product": "avicii", "serialno": "SERIAL123"},
        "beta_gate_credit": False,
    }
    values.update(changes)
    return FastbootBaselineEvidence(**values)


def fixture_chain(tmp_path):
    paths = {}
    for name in ("kernel", "ramdisk", "dtb", "dtbo"):
        path = tmp_path / name
        path.write_bytes((name + "-bytes").encode())
        paths[name] = path
    prov = provenance()
    plan = create_boot_build_plan(
        PROFILE,
        prov,
        kernel=paths["kernel"],
        ramdisk=paths["ramdisk"],
        dtb=paths["dtb"],
        dtbo=paths["dtbo"],
    )
    image = tmp_path / "candidate.img"
    image.write_bytes(b"ANDROID!verified-candidate")
    digest = sha256(image.read_bytes()).hexdigest()
    assembly = BootAssemblyEvidence(
        1, PROFILE.profile_id, plan.plan_sha256(), digest, image.stat().st_size, True
    )
    round_trip = BootRoundTripEvidence(
        1,
        PROFILE.profile_id,
        plan.plan_sha256(),
        digest,
        sha256(paths["kernel"].read_bytes()).hexdigest(),
        sha256(paths["ramdisk"].read_bytes()).hexdigest(),
        sha256(paths["dtb"].read_bytes()).hexdigest(),
        True,
    )
    device = VerifiedDevice(PROFILE.profile_id, "SERIAL123", "a", True)
    return plan, prov, assembly, round_trip, baseline(), device, image


def authorize(chain, *, image=None):
    plan, prov, assembly, round_trip, base, device, default_image = chain
    return authorize_temporary_boot(
        plan,
        PROFILE,
        prov,
        assembly,
        round_trip,
        base,
        device,
        image=image or default_image,
    )


def test_authorization_binds_verified_chain_baseline_and_device(tmp_path):
    chain = fixture_chain(tmp_path)
    auth = authorize(chain)
    assert auth.schema_version == 2
    assert auth.device_serial == "SERIAL123"
    assert auth.fastboot_baseline_sha256 == chain[4].evidence_sha256()
    assert auth.firmware_build == BUILD
    assert auth.firmware_fingerprint == FINGERPRINT
    assert auth.reproducible and auth.structurally_verified
    destination = tmp_path / "evidence" / "temporary-boot-authorization.json"
    assert write_temporary_boot_authorization(auth, destination) == auth.authorization_sha256()
    assert destination.read_text() == auth.canonical_json()


def test_authorization_rejects_image_drift(tmp_path):
    chain = fixture_chain(tmp_path)
    chain[-1].write_bytes(b"ANDROID!tampered")
    with pytest.raises(BootImageError, match="changed after verification"):
        authorize(chain)


def test_authorization_rejects_unverified_round_trip(tmp_path):
    chain = fixture_chain(tmp_path)
    object.__setattr__(chain[3], "structurally_verified", False)
    with pytest.raises(BootImageError, match="structural round-trip"):
        authorize(chain)


def test_authorization_rejects_wrong_device_profile(tmp_path):
    chain = list(fixture_chain(tmp_path))
    chain[5] = VerifiedDevice("vendor/other", "SERIAL123", "a", True)
    with pytest.raises(SafetyError, match="different profile"):
        authorize(tuple(chain))


def test_authorization_rejects_locked_bootloader(tmp_path):
    chain = list(fixture_chain(tmp_path))
    chain[5] = VerifiedDevice(PROFILE.profile_id, "SERIAL123", "a", False)
    with pytest.raises(SafetyError, match="bootloader must be unlocked"):
        authorize(tuple(chain))


def test_authorization_rejects_baseline_serial_mismatch(tmp_path):
    chain = list(fixture_chain(tmp_path))
    chain[4] = baseline(serialno="OTHER")
    with pytest.raises(SafetyError, match="serial"):
        authorize(tuple(chain))


def test_authorization_rejects_firmware_fingerprint_or_build_mismatch(tmp_path):
    chain = list(fixture_chain(tmp_path))
    chain[4] = baseline(firmware_fingerprint="different/fingerprint")
    with pytest.raises(BootImageError, match="fingerprint"):
        authorize(tuple(chain))

    chain = list(fixture_chain(tmp_path))
    chain[4] = baseline(firmware_build="different-build")
    with pytest.raises(BootImageError, match="firmware build"):
        authorize(tuple(chain))
