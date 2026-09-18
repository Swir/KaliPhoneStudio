from __future__ import annotations

import json
from pathlib import Path

import pytest

import main as entrypoint
from kaliphonestudio.fastboot_tool import FastbootToolEvidence
from kaliphonestudio.physical_candidate_operator import (
    PhysicalCandidateOperatorError,
    _load_typed,
    _preflight_execution_outputs,
    execute_temporary_boot_once_main,
)


def test_shared_typed_loader_rejects_schema_drift(tmp_path: Path) -> None:
    path = tmp_path / "tool.json"
    path.write_text(json.dumps({"schema_version": 1, "unexpected": True}), encoding="utf-8")
    with pytest.raises(PhysicalCandidateOperatorError, match="field set"):
        _load_typed(FastbootToolEvidence, path, "Fastboot tool evidence")


def test_execution_output_preflight_rejects_same_path(tmp_path: Path) -> None:
    path = tmp_path / "physical.json"
    with pytest.raises(PhysicalCandidateOperatorError, match="must not overlap"):
        _preflight_execution_outputs(path, path)
    assert not path.exists()


def test_execution_output_preflight_rejects_cross_temp_collision(tmp_path: Path) -> None:
    execution = tmp_path / "execution.json"
    probe = tmp_path / "execution.json.tmp"
    with pytest.raises(PhysicalCandidateOperatorError, match="must not overlap"):
        _preflight_execution_outputs(probe, execution)
    assert not probe.exists()
    assert not execution.exists()


def test_execution_output_preflight_rejects_existing_output(tmp_path: Path) -> None:
    probe = tmp_path / "probe.json"
    execution = tmp_path / "execution.json"
    probe.write_text("occupied", encoding="utf-8")
    with pytest.raises(PhysicalCandidateOperatorError, match="refusing to overwrite"):
        _preflight_execution_outputs(probe, execution)
    assert not execution.exists()


def test_execution_output_preflight_checks_writable_parent_without_residue(
    tmp_path: Path,
) -> None:
    probe = tmp_path / "nested" / "probe.json"
    execution = tmp_path / "nested" / "execution.json"
    _preflight_execution_outputs(probe, execution)
    assert probe.parent.is_dir()
    assert not probe.exists()
    assert not execution.exists()
    assert list(probe.parent.glob(".kps-output-preflight-*")) == []


def test_execution_cli_refuses_before_evidence_or_device_io_without_opt_in(
    tmp_path: Path,
) -> None:
    probe = tmp_path / "probe.json"
    execution = tmp_path / "execution.json"
    argv = [
        "--profile-id",
        "oneplus/avicii",
        "--physical-candidate-gate",
        str(tmp_path / "missing-gate.json"),
        "--capture-bundle",
        str(tmp_path / "missing-capture.json"),
        "--baseline-evidence",
        str(tmp_path / "missing-baseline.json"),
        "--fastboot-tool-evidence",
        str(tmp_path / "missing-tool.json"),
        "--fastboot-executable",
        str(tmp_path / "missing-fastboot"),
        "--boot-image",
        str(tmp_path / "missing-boot.img"),
        "--confirmation",
        "WRONG-ON-PURPOSE",
        "--probe-out",
        str(probe),
        "--execution-out",
        str(execution),
    ]
    with pytest.raises(SystemExit) as exc:
        execute_temporary_boot_once_main(argv)
    assert exc.value.code == 2
    assert not probe.exists()
    assert not execution.exists()


@pytest.mark.parametrize(
    ("command", "attribute"),
    [
        ("bind-physical-candidate-gate", "bind_physical_candidate_main"),
        ("prepare-temporary-boot-offer", "prepare_temporary_boot_offer_main"),
        ("execute-temporary-boot-once", "execute_temporary_boot_once_main"),
    ],
)
def test_main_dispatches_shared_physical_candidate_commands(
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    attribute: str,
) -> None:
    observed: list[list[str]] = []

    def fake(argv):
        observed.append(list(argv))
        return 37

    monkeypatch.setattr(entrypoint, attribute, fake)
    assert entrypoint.main([command, "--sentinel", "value"]) == 37
    assert observed == [["--sentinel", "value"]]
