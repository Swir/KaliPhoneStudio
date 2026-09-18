from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import kaliphonestudio.temporary_boot_execution as module
from kaliphonestudio.temporary_boot_execution import (
    TemporaryBootExecutionError,
    execute_temporary_boot_once,
)
from kaliphonestudio.temporary_boot_offer import TemporaryBootOfferError


class _DigestEvidence:
    def __init__(self, device_serial: str = "SERIAL123") -> None:
        self.device_serial = device_serial

    def evidence_sha256(self) -> str:
        return "1" * 64


class _Authorization:
    def evidence_sha256(self) -> str:
        return "2" * 64


class _Probe:
    def evidence_sha256(self) -> str:
        return "3" * 64


class _Result:
    returncode = 0
    stdout = b"OKAY temporary boot\n"


def _arguments():
    fastboot = Path("/reviewed/fastboot")
    image = Path("/reviewed/candidate-boot.img")
    offer = SimpleNamespace(
        fastboot_executable=fastboot,
        boot_image=image,
        evidence=_DigestEvidence(),
        argv=(str(fastboot), "-s", "SERIAL123", "boot", str(image)),
    )
    profile = SimpleNamespace(profile_id="acme/demo")
    authorization = _Authorization()
    opaque = SimpleNamespace()
    return (
        profile,
        offer,
        authorization,
        opaque,
        opaque,
        opaque,
        opaque,
        opaque,
        opaque,
        opaque,
    )


def _patch_probe_and_validators(monkeypatch, order: list[str]) -> None:
    def fake_probe(*args, **kwargs):
        order.append("probe")
        return _Probe()

    monkeypatch.setattr(module, "probe_temporary_boot_runtime", fake_probe)
    monkeypatch.setattr(
        module,
        "_validate_boot_identity_binding",
        lambda *args, **kwargs: order.append("binding"),
    )
    monkeypatch.setattr(
        module,
        "_validate_authorization",
        lambda *args, **kwargs: order.append("authorization"),
    )
    monkeypatch.setattr(
        module,
        "_validate_baseline_binding",
        lambda *args, **kwargs: order.append("baseline"),
    )
    monkeypatch.setattr(
        module,
        "_validate_recovery_readiness",
        lambda *args, **kwargs: order.append("recovery"),
    )


def test_post_probe_exact_material_revalidation_precedes_boot(monkeypatch) -> None:
    order: list[str] = []
    _patch_probe_and_validators(monkeypatch, order)

    def fake_verify(*args, **kwargs):
        order.append("offer-rehash")

    def runner(argv, **kwargs):
        order.append("boot")
        return _Result()

    monkeypatch.setattr(module, "verify_temporary_boot_offer", fake_verify)
    args = _arguments()
    probe, execution = execute_temporary_boot_once(
        *args,
        stock_boot=Path("/reviewed/stock-boot.img"),
        runner=runner,
    )

    assert probe.evidence_sha256() == "3" * 64
    assert order == [
        "probe",
        "offer-rehash",
        "binding",
        "authorization",
        "baseline",
        "recovery",
        "boot",
    ]
    assert "post-probe-exact-material-revalidation" in execution.execution_policy
    assert execution.persistent_write is False
    assert execution.phone_storage_written is False
    assert execution.hardware_verified is False
    assert execution.beta_gate_credit is False


def test_post_probe_offer_drift_fails_before_boot(monkeypatch) -> None:
    order: list[str] = []
    _patch_probe_and_validators(monkeypatch, order)

    def fail_verify(*args, **kwargs):
        order.append("offer-rehash")
        raise TemporaryBootOfferError("candidate boot image bytes changed")

    boot_calls: list[tuple[str, ...]] = []

    def runner(argv, **kwargs):
        boot_calls.append(tuple(argv))
        return _Result()

    monkeypatch.setattr(module, "verify_temporary_boot_offer", fail_verify)
    args = _arguments()
    with pytest.raises(TemporaryBootExecutionError, match="pre-execution offer revalidation failed"):
        execute_temporary_boot_once(
            *args,
            stock_boot=Path("/reviewed/stock-boot.img"),
            runner=runner,
        )

    assert order == ["probe", "offer-rehash"]
    assert boot_calls == []


def test_post_probe_recovery_drift_fails_before_boot(monkeypatch) -> None:
    order: list[str] = []

    def fake_probe(*args, **kwargs):
        order.append("probe")
        return _Probe()

    monkeypatch.setattr(module, "probe_temporary_boot_runtime", fake_probe)
    monkeypatch.setattr(
        module,
        "verify_temporary_boot_offer",
        lambda *args, **kwargs: order.append("offer-rehash"),
    )
    monkeypatch.setattr(
        module,
        "_validate_boot_identity_binding",
        lambda *args, **kwargs: order.append("binding"),
    )
    monkeypatch.setattr(
        module,
        "_validate_authorization",
        lambda *args, **kwargs: order.append("authorization"),
    )
    monkeypatch.setattr(
        module,
        "_validate_baseline_binding",
        lambda *args, **kwargs: order.append("baseline"),
    )

    def fail_recovery(*args, **kwargs):
        order.append("recovery")
        raise TemporaryBootExecutionError("stock boot bytes drifted")

    monkeypatch.setattr(module, "_validate_recovery_readiness", fail_recovery)
    boot_calls: list[tuple[str, ...]] = []

    def runner(argv, **kwargs):
        boot_calls.append(tuple(argv))
        return _Result()

    args = _arguments()
    with pytest.raises(TemporaryBootExecutionError, match="pre-execution recovery revalidation failed"):
        execute_temporary_boot_once(
            *args,
            stock_boot=Path("/reviewed/stock-boot.img"),
            runner=runner,
        )

    assert order == [
        "probe",
        "offer-rehash",
        "binding",
        "authorization",
        "baseline",
        "recovery",
    ]
    assert boot_calls == []
