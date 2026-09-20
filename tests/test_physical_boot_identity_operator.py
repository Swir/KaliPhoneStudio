from __future__ import annotations

import ast
from pathlib import Path

import pytest

import main as entrypoint
from kaliphonestudio import physical_boot_identity_operator
from kaliphonestudio.boot_builder import BootBuildPlan
from kaliphonestudio.physical_baseline_bundle import PhysicalBaselineBundleEvidence
from kaliphonestudio.physical_candidate_gate import PhysicalCandidateGateEvidence
from kaliphonestudio.provenance import StockBootProvenance


def _argv(tmp_path: Path) -> list[str]:
    return [
        "--profile-id",
        "oneplus/avicii",
        "--physical-baseline",
        str(tmp_path / "physical.json"),
        "--physical-candidate-gate",
        str(tmp_path / "gate.json"),
        "--stock-provenance",
        str(tmp_path / "stock-provenance.json"),
        "--boot-plan",
        str(tmp_path / "boot-plan.json"),
        "--stock-boot",
        str(tmp_path / "stock-boot.img"),
        "--candidate-boot",
        str(tmp_path / "candidate-boot.img"),
        "--candidate-dtbo",
        str(tmp_path / "candidate-dtbo.img"),
        "--out",
        str(tmp_path / "boot-identity.json"),
    ]


def test_boot_identity_operator_fails_closed_on_missing_exact_inputs(tmp_path: Path) -> None:
    destination = tmp_path / "boot-identity.json"
    with pytest.raises(SystemExit) as exc:
        physical_boot_identity_operator.main(_argv(tmp_path))
    assert exc.value.code == 2
    assert not destination.exists()


def test_boot_identity_operator_refuses_existing_output_before_input_loading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "boot-identity.json"
    destination.write_text("occupied", encoding="utf-8")
    loaded = False

    def unexpected_load(*_args, **_kwargs):
        nonlocal loaded
        loaded = True
        raise AssertionError("input loading must not happen after output collision")

    monkeypatch.setattr(physical_boot_identity_operator, "_load_typed", unexpected_load)
    with pytest.raises(SystemExit) as exc:
        physical_boot_identity_operator.main(_argv(tmp_path))
    assert exc.value.code == 2
    assert loaded is False
    assert destination.read_text(encoding="utf-8") == "occupied"


def test_boot_identity_operator_binds_exact_host_files_without_device_io(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    profile = object()
    physical = object()
    gate = object()
    provenance = object()
    plan = object()
    observed: dict[str, object] = {}

    class Evidence:
        def canonical_json(self) -> str:
            return '{"schema_version":1}\n'

    evidence = Evidence()
    monkeypatch.setattr(physical_boot_identity_operator, "get_profile", lambda root, profile_id: profile)

    def fake_load(cls, path, label):
        observed[label] = Path(path)
        return {
            PhysicalBaselineBundleEvidence: physical,
            PhysicalCandidateGateEvidence: gate,
            StockBootProvenance: provenance,
        }[cls]

    monkeypatch.setattr(physical_boot_identity_operator, "_load_typed", fake_load)
    monkeypatch.setattr(physical_boot_identity_operator, "_load_boot_plan", lambda path: plan)

    def fake_bind(profile_arg, physical_arg, gate_arg, provenance_arg, plan_arg, **kwargs):
        assert profile_arg is profile
        assert physical_arg is physical
        assert gate_arg is gate
        assert provenance_arg is provenance
        assert plan_arg is plan
        assert Path(kwargs["stock_boot"]) == tmp_path / "stock-boot.img"
        assert Path(kwargs["candidate_boot"]) == tmp_path / "candidate-boot.img"
        assert Path(kwargs["candidate_dtbo"]) == tmp_path / "candidate-dtbo.img"
        return evidence

    monkeypatch.setattr(physical_boot_identity_operator, "bind_physical_boot_identity", fake_bind)
    monkeypatch.setattr(
        physical_boot_identity_operator,
        "write_physical_boot_identity_binding",
        lambda evidence_arg, destination: (
            "b" * 64
            if evidence_arg is evidence and Path(destination) == tmp_path / "boot-identity.json"
            else (_ for _ in ()).throw(AssertionError("unexpected identity write"))
        ),
    )

    assert physical_boot_identity_operator.main(_argv(tmp_path)) == 0
    output = capsys.readouterr().out
    assert "stock_exact_bytes_verified=true" in output
    assert "candidate_exact_bytes_verified=true" in output
    assert "temporary_boot_executed=false" in output
    assert "phone_storage_written=false" in output
    assert "hardware/Beta credit=false" in output
    assert set(observed) == {
        "physical baseline bundle",
        "physical candidate gate",
        "stock boot provenance",
    }


def test_main_dispatches_boot_identity_command(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: list[list[str]] = []

    def fake(argv):
        observed.append(list(argv))
        return 43

    monkeypatch.setattr(entrypoint, "physical_boot_identity_main", fake)
    assert entrypoint.main(["bind-physical-boot-identity", "--sentinel", "value"]) == 43
    assert observed == [["--sentinel", "value"]]


def test_boot_identity_operator_has_no_device_or_network_execution_imports() -> None:
    source = Path(physical_boot_identity_operator.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    forbidden = {"subprocess", "requests", "urllib", "httpx", "socket"}
    assert imported.isdisjoint(forbidden)
