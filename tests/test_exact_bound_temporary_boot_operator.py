from __future__ import annotations

from pathlib import Path

import pytest

from kaliphonestudio.exact_bound_temporary_boot_operator import (
    execute_temporary_boot_once_main,
    prepare_temporary_boot_offer_main,
)


def test_offer_cli_requires_exact_boot_identity_binding_before_evidence_load(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = tmp_path / "offer.json"
    argv = [
        "--profile-id", "oneplus/avicii",
        "--physical-candidate-gate", str(tmp_path / "missing-gate.json"),
        "--capture-bundle", str(tmp_path / "missing-capture.json"),
        "--fastboot-tool-evidence", str(tmp_path / "missing-tool.json"),
        "--fastboot-executable", str(tmp_path / "missing-fastboot.exe"),
        "--boot-image", str(tmp_path / "missing-boot.img"),
        "--out", str(out),
    ]
    with pytest.raises(SystemExit) as exc:
        prepare_temporary_boot_offer_main(argv)
    assert exc.value.code == 2
    assert "--physical-boot-identity-binding" in capsys.readouterr().err
    assert not out.exists()


def test_offer_cli_with_binding_path_still_fails_closed_on_missing_exact_evidence(
    tmp_path: Path,
) -> None:
    out = tmp_path / "offer.json"
    argv = [
        "--profile-id", "oneplus/avicii",
        "--physical-candidate-gate", str(tmp_path / "missing-gate.json"),
        "--physical-boot-identity-binding", str(tmp_path / "missing-binding.json"),
        "--capture-bundle", str(tmp_path / "missing-capture.json"),
        "--fastboot-tool-evidence", str(tmp_path / "missing-tool.json"),
        "--fastboot-executable", str(tmp_path / "missing-fastboot.exe"),
        "--boot-image", str(tmp_path / "missing-boot.img"),
        "--out", str(out),
    ]
    with pytest.raises(SystemExit) as exc:
        prepare_temporary_boot_offer_main(argv)
    assert exc.value.code == 2
    assert not out.exists()


def test_execution_opt_in_remains_first_gate_before_binding_or_device_io(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe = tmp_path / "probe.json"
    execution = tmp_path / "execution.json"
    argv = [
        "--profile-id", "oneplus/avicii",
        "--physical-candidate-gate", str(tmp_path / "missing-gate.json"),
        "--capture-bundle", str(tmp_path / "missing-capture.json"),
        "--baseline-evidence", str(tmp_path / "missing-baseline.json"),
        "--fastboot-tool-evidence", str(tmp_path / "missing-tool.json"),
        "--fastboot-executable", str(tmp_path / "missing-fastboot.exe"),
        "--boot-image", str(tmp_path / "missing-boot.img"),
        "--confirmation", "WRONG-ON-PURPOSE",
        "--probe-out", str(probe),
        "--execution-out", str(execution),
    ]
    with pytest.raises(SystemExit) as exc:
        execute_temporary_boot_once_main(argv)
    assert exc.value.code == 2
    error = capsys.readouterr().err
    assert "--execute-temporary-boot" in error
    assert "--physical-boot-identity-binding" not in error
    assert not probe.exists()
    assert not execution.exists()


def test_execution_with_opt_in_then_requires_exact_boot_identity_binding(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    probe = tmp_path / "probe.json"
    execution = tmp_path / "execution.json"
    argv = [
        "--profile-id", "oneplus/avicii",
        "--physical-candidate-gate", str(tmp_path / "missing-gate.json"),
        "--capture-bundle", str(tmp_path / "missing-capture.json"),
        "--baseline-evidence", str(tmp_path / "missing-baseline.json"),
        "--fastboot-tool-evidence", str(tmp_path / "missing-tool.json"),
        "--fastboot-executable", str(tmp_path / "missing-fastboot.exe"),
        "--boot-image", str(tmp_path / "missing-boot.img"),
        "--confirmation", "WRONG-ON-PURPOSE",
        "--execute-temporary-boot",
        "--probe-out", str(probe),
        "--execution-out", str(execution),
    ]
    with pytest.raises(SystemExit) as exc:
        execute_temporary_boot_once_main(argv)
    assert exc.value.code == 2
    assert "--physical-boot-identity-binding" in capsys.readouterr().err
    assert not probe.exists()
    assert not execution.exists()
