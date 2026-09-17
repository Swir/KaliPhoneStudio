from hashlib import sha256
from pathlib import Path

from kaliphonestudio.kernel_authority import load_and_verify_kernel_authority
from kaliphonestudio.kernel_contract import create_kernel_build_plan
from kaliphonestudio.kernel_toolchain import load_kernel_toolchain_lock
from kaliphonestudio.profiles import get_profile


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / "evidence" / "authorities" / "oneplus-avicii-kernel-4.19.300-2026-09-17.json"
CHAIN = ROOT / "evidence" / "authorities" / "kernel" / "oneplus-avicii-4.19.300-2026-09-17"


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def test_checked_avicii_kernel_authority_reconstructs_strict_chain():
    profile = get_profile(ROOT / "devices", "oneplus/avicii")
    plan = create_kernel_build_plan(profile)
    lock = load_kernel_toolchain_lock(ROOT / "tools" / "kernel-toolchain-lock.json")

    authority = load_and_verify_kernel_authority(
        AUTHORITY,
        plan,
        lock,
        CHAIN / "kernel-reproducibility.json",
        CHAIN / "kernel-reproducibility-binding.json",
        CHAIN / "kernel-build-a.json",
        CHAIN / "kernel-build-b.json",
    )

    assert authority.authority_sha256() == "0bdc44c4625e04214981eca428872642419fb8ad3c135a96d40f25e781a7d5f2"
    assert authority.authority_run_id == 35183670399
    assert authority.authority_commit == "e600a5de13fa91085464c7ce2d4a6327f39b96e8"
    assert authority.authority_artifact_id == 10482645697
    assert authority.profile_id == "oneplus/avicii"
    assert authority.source_commit == "fb4b4374d3b9ad0f10ba38d159585129f092fb3d"
    assert authority.image_sha256 == "be4440dc335d53c752270c484fe589a9bc1ef08f9100e885478b50df67cbe712"
    assert authority.image_size == 43878416
    assert authority.config_sha256 == "2ab588b240ed227101464f77465176f2c178ae09309a47e45f5ff56f14c3c7f3"
    assert authority.config_size == 166055
    assert authority.strict_byte_identical is True
    assert authority.distinct_build_roots_verified is True
    assert authority.reviewed is True
    assert authority.hardware_verified is False
    assert authority.beta_gate_credit is False

    assert _digest(CHAIN / "kernel-reproducibility.json") == authority.reproducibility_evidence_sha256
    assert _digest(CHAIN / "kernel-reproducibility-binding.json") == authority.reproducibility_binding_sha256
    assert _digest(CHAIN / "kernel-build-a.json") == authority.build_a_run_evidence_sha256
    assert _digest(CHAIN / "kernel-build-b.json") == authority.build_b_run_evidence_sha256
