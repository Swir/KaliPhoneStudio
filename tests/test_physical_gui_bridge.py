from __future__ import annotations

from pathlib import Path
import subprocess

from kaliphonestudio.physical_gui_bridge import (
    build_begin_session_args,
    build_prepare_candidate_args,
    build_temporary_boot_args,
    detect_single_fastboot_device,
    ensure_no_persistent_write_verbs,
    inspect_session_state,
)


ROOT = Path(__file__).resolve().parents[1]


def _file(path: Path, data: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_gui_detects_one_exact_fastboot_device_with_readonly_commands(tmp_path: Path) -> None:
    fastboot = _file(tmp_path / "fastboot.exe", b"fake-fastboot-binary")

    calls: list[list[str]] = []

    def runner(argv, **kwargs):
        calls.append(list(argv))
        if argv[-1] == "--version":
            return subprocess.CompletedProcess(argv, 0, stdout=b"fastboot version 37.0.1\n")
        if argv[-1] == "devices":
            return subprocess.CompletedProcess(argv, 0, stdout=b"SERIAL123\tfastboot\n")
        raise AssertionError(f"unexpected command: {argv}")

    detection = detect_single_fastboot_device(
        fastboot,
        policy_path=ROOT / "tools" / "fastboot-tool-policy.json",
        runner=runner,
    )

    assert detection.serial == "SERIAL123"
    assert detection.platform_tools_version == "37.0.1"
    assert [call[-1] for call in calls] == ["--version", "devices"]
    joined = " ".join(token for call in calls for token in call).lower()
    for forbidden in (" flash ", " erase ", " set_active ", " flashing ", " boot "):
        assert forbidden not in f" {joined} "


def test_begin_session_gui_args_are_profile_bound_and_write_free(tmp_path: Path) -> None:
    fastboot = _file(tmp_path / "fastboot.exe")
    policy = _file(tmp_path / "policy.json", b"{}")
    args = build_begin_session_args(
        profile_id="oneplus/avicii",
        confirmation_token="AC2003",
        serial="SERIAL123",
        firmware_build="OOS-EXACT",
        firmware_fingerprint="oneplus/avicii/exact:fingerprint",
        fastboot=fastboot,
        policy_path=policy,
        session_dir=tmp_path / "fresh-session",
    )
    assert args[0] == "begin-physical-test-session"
    assert "--profile-id" in args and "oneplus/avicii" in args
    assert "--confirm-token" in args and "AC2003" in args
    ensure_no_persistent_write_verbs(args)


def test_offline_candidate_gui_args_bind_exact_inputs_without_phone_write(tmp_path: Path) -> None:
    session = tmp_path / "session"
    session.mkdir()
    inputs = {
        "ota": _file(tmp_path / "ota.zip"),
        "extractor": _file(tmp_path / "payload-dumper-go.exe"),
        "first_boot_manifest": _file(tmp_path / "first-boot.json"),
        "authority_bundle": _file(tmp_path / "authority.json"),
        "boot_authorization": _file(tmp_path / "authorization.json"),
        "boot_plan": _file(tmp_path / "boot-plan.json"),
        "candidate_boot": _file(tmp_path / "candidate-boot.img"),
        "candidate_dtbo": _file(tmp_path / "candidate-dtbo.img"),
        "fastboot": _file(tmp_path / "fastboot.exe"),
    }
    args = build_prepare_candidate_args(
        profile_id="oneplus/avicii",
        session_dir=session,
        **inputs,
    )
    assert args[0] == "prepare-physical-candidate-offline"
    assert "--ota" in args
    assert "--candidate-boot" in args
    assert "--candidate-dtbo" in args
    ensure_no_persistent_write_verbs(args)


def test_temporary_boot_gui_args_require_complete_recovery_chain(tmp_path: Path) -> None:
    session = tmp_path / "session"
    for relative in (
        "physical-candidate-gate.json",
        "physical-boot-identity.json",
        "physical-stock-baseline.json",
        "physical-recovery-readiness.json",
        "stock/partitions/boot.img",
        "fastboot/fastboot-capture-bundle.json",
        "fastboot/fastboot-baseline.json",
        "fastboot/fastboot-tool.json",
    ):
        _file(session / relative)
    fastboot = _file(tmp_path / "fastboot.exe")
    candidate = _file(tmp_path / "candidate-boot.img")

    args = build_temporary_boot_args(
        profile_id="oneplus/avicii",
        confirmation_token="AC2003",
        session_dir=session,
        fastboot=fastboot,
        boot_image=candidate,
    )

    assert args[0] == "execute-temporary-boot-once"
    assert "--execute-temporary-boot" in args
    assert "--recovery-readiness" in args
    assert "--confirmation" in args
    ensure_no_persistent_write_verbs(args)


def test_session_state_unlocks_only_after_exact_evidence_files_exist(tmp_path: Path) -> None:
    session = tmp_path / "session"
    assert inspect_session_state(session).baseline_ready is False

    for relative in (
        "physical-first-test-session.json",
        "fastboot/fastboot-getvar-all.txt",
        "fastboot/fastboot-baseline.json",
        "fastboot/fastboot-tool.json",
        "fastboot/fastboot-capture-bundle.json",
    ):
        _file(session / relative)
    state = inspect_session_state(session)
    assert state.baseline_ready is True
    assert state.offline_candidate_ready is False

    for relative in (
        "physical-candidate-offline-preparation.json",
        "physical-candidate-gate.json",
        "physical-boot-identity.json",
        "physical-recovery-readiness.json",
        "stock/partitions/boot.img",
    ):
        _file(session / relative)
    state = inspect_session_state(session)
    assert state.offline_candidate_ready is True
    assert state.temporary_boot_recorded is False

    _file(session / "temporary-boot-runtime-probe.json")
    _file(session / "temporary-boot-execution.json")
    assert inspect_session_state(session).temporary_boot_recorded is True


def test_gui_surface_exposes_gated_physical_flow_and_keeps_flash_locked() -> None:
    app = (ROOT / "kaliphonestudio" / "app.py").read_text(encoding="utf-8")
    wizard = (ROOT / "kaliphonestudio" / "physical_gui_wizard.py").read_text(encoding="utf-8")

    assert 'Physical phone test…' in app
    for label in (
        "Detect Fastboot phone",
        "Create read-only baseline",
        "Prepare exact offline candidate + recovery readiness",
        "Run one-shot TEMPORARY boot",
        "Persistent flash — LOCKED until physical Beta gate passes",
    ):
        assert label in wizard

    assert "QProcess" in wizard
    assert "begin-physical-test-session" not in wizard
    assert "prepare-physical-candidate-offline" not in wizard
    assert "execute-temporary-boot-once" not in wizard
