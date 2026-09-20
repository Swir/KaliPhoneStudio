from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import main as entrypoint
from kaliphonestudio import physical_recovery_operator
from kaliphonestudio.fastboot_baseline import FastbootBaselineEvidence
from kaliphonestudio.physical_baseline_bundle import PhysicalBaselineBundleEvidence
from kaliphonestudio.physical_boot_identity_binding import PhysicalBootIdentityBindingEvidence


def _argv(tmp_path: Path) -> list[str]:
    return [
        "--profile-id",
        "oneplus/avicii",
        "--baseline-evidence",
        str(tmp_path / "baseline.json"),
        "--physical-baseline",
        str(tmp_path / "physical.json"),
        "--boot-identity-binding",
        str(tmp_path / "binding.json"),
        "--stock-boot",
        str(tmp_path / "stock-boot.img"),
        "--out",
        str(tmp_path / "recovery-readiness.json"),
    ]


def test_recovery_operator_fails_closed_on_missing_exact_inputs(tmp_path: Path) -> None:
    destination = tmp_path / "recovery-readiness.json"
    with pytest.raises(SystemExit) as exc:
        physical_recovery_operator.main(_argv(tmp_path))
    assert exc.value.code == 2
    assert not destination.exists()


def test_recovery_operator_refuses_existing_output_before_input_loading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "recovery-readiness.json"
    destination.write_text("occupied", encoding="utf-8")
    loaded = False

    def unexpected_load(*_args, **_kwargs):
        nonlocal loaded
        loaded = True
        raise AssertionError("input loading must not happen after output collision")

    monkeypatch.setattr(physical_recovery_operator, "_load_typed", unexpected_load)
    with pytest.raises(SystemExit) as exc:
        physical_recovery_operator.main(_argv(tmp_path))
    assert exc.value.code == 2
    assert loaded is False
    assert destination.read_text(encoding="utf-8") == "occupied"


def test_recovery_operator_binds_typed_inputs_without_device_io(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    profile = object()
    baseline = object()
    physical = object()
    binding = object()
    observed: dict[str, object] = {}

    class Evidence:
        def canonical_json(self) -> str:
            return '{"schema_version":1}\n'

    evidence = Evidence()

    monkeypatch.setattr(physical_recovery_operator, "get_profile", lambda root, profile_id: profile)

    def fake_load(cls, path, label):
        observed[label] = Path(path)
        return {
            FastbootBaselineEvidence: baseline,
            PhysicalBaselineBundleEvidence: physical,
            PhysicalBootIdentityBindingEvidence: binding,
        }[cls]

    monkeypatch.setattr(physical_recovery_operator, "_load_typed", fake_load)

    def fake_build(profile_arg, baseline_arg, physical_arg, binding_arg, *, stock_boot):
        assert profile_arg is profile
        assert baseline_arg is baseline
        assert physical_arg is physical
        assert binding_arg is binding
        assert Path(stock_boot) == tmp_path / "stock-boot.img"
        return evidence

    monkeypatch.setattr(physical_recovery_operator, "build_physical_recovery_readiness", fake_build)
    monkeypatch.setattr(
        physical_recovery_operator,
        "write_physical_recovery_readiness",
        lambda evidence_arg, destination: (
            "a" * 64
            if evidence_arg is evidence and Path(destination) == tmp_path / "recovery-readiness.json"
            else (_ for _ in ()).throw(AssertionError("unexpected evidence write"))
        ),
    )

    assert physical_recovery_operator.main(_argv(tmp_path)) == 0
    output = capsys.readouterr().out
    assert "ready_for_temporary_boot_safety_review=true" in output
    assert "slot_switch_authorized=false" in output
    assert "persistent_write_authorized=false" in output
    assert "recovery_verified=false" in output
    assert "hardware/Beta credit=false" in output
    assert set(observed) == {
        "Fastboot baseline evidence",
        "physical baseline bundle",
        "physical boot identity binding",
    }


def test_main_dispatches_recovery_readiness_command(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: list[list[str]] = []

    def fake(argv):
        observed.append(list(argv))
        return 41

    monkeypatch.setattr(entrypoint, "physical_recovery_readiness_main", fake)
    assert entrypoint.main(["build-physical-recovery-readiness", "--sentinel", "value"]) == 41
    assert observed == [["--sentinel", "value"]]


def test_recovery_operator_source_has_no_device_or_network_execution_imports() -> None:
    source = Path(physical_recovery_operator.__file__).read_text(encoding="utf-8")
    forbidden = (
        "import subprocess",
        "from subprocess",
        "import requests",
        "from requests",
        "fastboot ",
        "adb ",
    )
    for needle in forbidden:
        assert needle not in source.lower()
