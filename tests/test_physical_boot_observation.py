from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import pytest

from kaliphonestudio.physical_boot_observation import (
    PhysicalBootObservationError,
    RESCUE_MARKER,
    RESCUE_SHELL_MARKER,
    create_physical_boot_observation,
    load_rescue_observation_contract,
    write_physical_boot_observation,
)
from kaliphonestudio.temporary_boot_execution import TemporaryBootExecutionEvidence
from kaliphonestudio.temporary_boot_offer import TemporaryBootOfferEvidence


def _h(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _init_payload() -> bytes:
    return (
        "#!/bin/sh\n"
        "KPS_RESCUE_MARKER=\"KPS_RESCUE_INIT_REACHED_V1\"\n"
        "echo \"$KPS_RESCUE_MARKER\"\n"
        "echo \"Entering local rescue shell. Persistent storage is not mounted automatically.\"\n"
    ).encode("utf-8")


def _repository(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    (root / "rescue").mkdir(parents=True)
    init = root / "rescue" / "init"
    init.write_bytes(_init_payload())
    (root / "rescue" / "busybox-minimal.config").write_text("CONFIG_STATIC=y\n", encoding="utf-8")
    lock = root / "tools" / "rescue-payload-lock.json"
    lock.parent.mkdir()
    payload = {
        "schema_version": 1,
        "payload_id": "busybox-arm64-rescue-v1",
        "architecture": "arm64",
        "busybox": {
            "version": "1.38.0",
            "source_url": "https://busybox.net/downloads/busybox-1.38.0.tar.bz2",
            "source_sha256": "a" * 64,
            "license": "GPL-2.0-only",
            "config_path": "rescue/busybox-minimal.config",
        },
        "binary_policy": {
            "elf_class": 64,
            "endianness": "little",
            "elf_machine": 183,
            "require_static": True,
            "max_binary_bytes": 8 * 1024 * 1024,
        },
        "required_applets": ["ash", "sh"],
        "forbidden_remote_access_applets": ["telnetd"],
        "init_template": "rescue/init",
        "network_default": "disabled",
        "ssh_default": "disabled",
        "materials": {
            "config_sha256": "b" * 64,
            "init_sha256": sha256(_init_payload()).hexdigest(),
        },
        "build": {
            "cross_compile": "aarch64-linux-gnu-",
            "kconfig_target": "allnoconfig",
            "make_target": "busybox",
            "ldflags": "--static",
            "source_date_epoch": 0,
            "independent_builds": 2,
        },
    }
    lock.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return root, lock


def _offer() -> TemporaryBootOfferEvidence:
    return TemporaryBootOfferEvidence(
        schema_version=1,
        profile_id="oneplus/avicii",
        device_serial="SERIAL123",
        physical_candidate_gate_sha256=_h("gate"),
        fastboot_capture_bundle_sha256=_h("capture"),
        fastboot_tool_evidence_sha256=_h("tool"),
        fastboot_tool_policy_sha256=_h("tool-policy"),
        fastboot_executable_sha256=_h("fastboot"),
        fastboot_executable_size=123456,
        platform_tools_version="37.0.1",
        boot_image_sha256=_h("boot-image"),
        boot_image_size=67108864,
        confirmation_text_sha256=_h("AC2003"),
        command_policy="fastboot-serial-temporary-boot-only-v1",
        persistent_write=False,
        phone_storage_written=False,
        temporary_boot_executed=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def _execution(offer: TemporaryBootOfferEvidence, *, succeeded: bool = True) -> TemporaryBootExecutionEvidence:
    return TemporaryBootExecutionEvidence(
        schema_version=1,
        profile_id=offer.profile_id,
        device_serial=offer.device_serial,
        offer_sha256=offer.evidence_sha256(),
        authorization_sha256=_h("authorization"),
        runtime_probe_sha256=_h("runtime-probe"),
        argv_sha256=_h("argv"),
        returncode=0 if succeeded else 1,
        output_sha256=_h("fastboot-output"),
        output_size=32,
        execution_policy="single-serial-fastboot-boot-no-persistent-write-v1",
        command_invoked=True,
        temporary_boot_executed=True,
        temporary_boot_command_succeeded=succeeded,
        persistent_write=False,
        phone_storage_written=False,
        kali_userspace_verified=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def _capture(tmp_path: Path, text: bytes) -> Path:
    path = tmp_path / "physical-console.log"
    path.write_bytes(text)
    return path


def test_contract_binds_exact_lock_and_init_bytes(tmp_path: Path) -> None:
    root, lock = _repository(tmp_path)
    contract = load_rescue_observation_contract(lock, root)
    assert contract.payload_id == "busybox-arm64-rescue-v1"
    assert contract.init_sha256 == sha256(_init_payload()).hexdigest()
    assert contract.marker == RESCUE_MARKER
    assert contract.network_default == "disabled"
    assert contract.ssh_default == "disabled"


def test_contract_rejects_init_drift(tmp_path: Path) -> None:
    root, lock = _repository(tmp_path)
    (root / "rescue" / "init").write_text("#!/bin/sh\necho changed\n", encoding="utf-8")
    with pytest.raises(PhysicalBootObservationError, match="do not match"):
        load_rescue_observation_contract(lock, root)


def test_rescue_marker_capture_is_review_eligible_but_not_hardware_verified(tmp_path: Path) -> None:
    root, lock = _repository(tmp_path)
    contract = load_rescue_observation_contract(lock, root)
    offer = _offer()
    execution = _execution(offer)
    capture = _capture(
        tmp_path,
        (
            b"[    0.000000] Linux version 4.19.300-kps\r\n"
            + RESCUE_MARKER.encode()
            + b"\r\n"
            + RESCUE_SHELL_MARKER.encode()
            + b"\r\n"
        ),
    )
    evidence = create_physical_boot_observation(
        execution, offer, contract, raw_capture=capture, source_kind="serial-console"
    )
    assert evidence.fastboot_command_succeeded is True
    assert evidence.kernel_banner_observed is True
    assert evidence.rescue_init_marker_observed is True
    assert evidence.rescue_shell_marker_observed is True
    assert evidence.panic_marker_observed is False
    assert evidence.observation_review_eligible is True
    assert evidence.review_required is True
    assert evidence.phone_storage_written_by_observer is False
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False


def test_panic_blocks_review_eligibility(tmp_path: Path) -> None:
    root, lock = _repository(tmp_path)
    contract = load_rescue_observation_contract(lock, root)
    offer = _offer()
    capture = _capture(
        tmp_path,
        RESCUE_MARKER.encode() + b"\n" + RESCUE_SHELL_MARKER.encode() + b"\nKernel panic - not syncing: test\n",
    )
    evidence = create_physical_boot_observation(
        _execution(offer), offer, contract, raw_capture=capture, source_kind="uart"
    )
    assert evidence.panic_marker_observed is True
    assert evidence.first_panic_marker == "Kernel panic - not syncing"
    assert evidence.observation_review_eligible is False
    assert evidence.hardware_verified is False


def test_failed_fastboot_command_never_becomes_review_eligible(tmp_path: Path) -> None:
    root, lock = _repository(tmp_path)
    contract = load_rescue_observation_contract(lock, root)
    offer = _offer()
    capture = _capture(
        tmp_path,
        RESCUE_MARKER.encode() + b"\n" + RESCUE_SHELL_MARKER.encode() + b"\n",
    )
    evidence = create_physical_boot_observation(
        _execution(offer, succeeded=False),
        offer,
        contract,
        raw_capture=capture,
        source_kind="usb-serial",
    )
    assert evidence.fastboot_command_succeeded is False
    assert evidence.rescue_init_marker_observed is True
    assert evidence.observation_review_eligible is False


def test_detached_execution_is_rejected(tmp_path: Path) -> None:
    root, lock = _repository(tmp_path)
    contract = load_rescue_observation_contract(lock, root)
    offer = _offer()
    execution = replace(_execution(offer), offer_sha256=_h("other-offer"))
    capture = _capture(tmp_path, b"some console bytes\n")
    with pytest.raises(PhysicalBootObservationError, match="detached"):
        create_physical_boot_observation(
            execution, offer, contract, raw_capture=capture, source_kind="serial-console"
        )


def test_invalid_source_kind_is_rejected(tmp_path: Path) -> None:
    root, lock = _repository(tmp_path)
    contract = load_rescue_observation_contract(lock, root)
    offer = _offer()
    capture = _capture(tmp_path, b"some console bytes\n")
    with pytest.raises(PhysicalBootObservationError, match="source_kind"):
        create_physical_boot_observation(
            _execution(offer), offer, contract, raw_capture=capture, source_kind="web-paste"
        )


def test_observation_preserves_raw_hash_and_normalizes_line_endings(tmp_path: Path) -> None:
    root, lock = _repository(tmp_path)
    contract = load_rescue_observation_contract(lock, root)
    offer = _offer()
    raw = b"one\r\ntwo\rthree\n"
    capture = _capture(tmp_path, raw)
    evidence = create_physical_boot_observation(
        _execution(offer), offer, contract, raw_capture=capture, source_kind="operator-console-log"
    )
    assert evidence.raw_capture_sha256 == sha256(raw).hexdigest()
    assert evidence.raw_capture_size == len(raw)
    normalized = b"one\ntwo\nthree\n"
    assert evidence.normalized_text_sha256 == sha256(normalized).hexdigest()
    assert evidence.normalized_text_size == len(normalized)


def test_writer_is_immutable(tmp_path: Path) -> None:
    root, lock = _repository(tmp_path)
    contract = load_rescue_observation_contract(lock, root)
    offer = _offer()
    capture = _capture(tmp_path, b"console data\n")
    evidence = create_physical_boot_observation(
        _execution(offer), offer, contract, raw_capture=capture, source_kind="serial-console"
    )
    destination = tmp_path / "observation.json"
    assert write_physical_boot_observation(evidence, destination) == evidence.evidence_sha256()
    with pytest.raises(PhysicalBootObservationError, match="overwrite"):
        write_physical_boot_observation(evidence, destination)
