#!/usr/bin/env python3
"""Bind a raw physical-console capture to one exact temporary-boot execution."""
from __future__ import annotations

import argparse
from dataclasses import fields
import json
from pathlib import Path
from typing import Any, TypeVar

from kaliphonestudio.physical_boot_observation import (
    PhysicalBootObservationError,
    create_physical_boot_observation,
    load_rescue_observation_contract,
    write_physical_boot_observation,
)
from kaliphonestudio.temporary_boot_execution import TemporaryBootExecutionEvidence
from kaliphonestudio.temporary_boot_offer import TemporaryBootOfferEvidence

MAX_EVIDENCE_BYTES = 2 * 1024 * 1024
T = TypeVar("T")


class ObservationInputError(ValueError):
    pass


def _load_typed(cls: type[T], path: Path, label: str) -> T:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise ObservationInputError(f"{label} must be a regular non-symlink JSON file")
    before = candidate.stat()
    if before.st_size <= 0 or before.st_size > MAX_EVIDENCE_BYTES:
        raise ObservationInputError(f"{label} size is outside the evidence safety bound")
    raw = candidate.read_bytes()
    after = candidate.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise ObservationInputError(f"{label} changed while being loaded")
    try:
        data: Any = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ObservationInputError(f"{label} is not strict UTF-8 JSON") from exc
    if not isinstance(data, dict):
        raise ObservationInputError(f"{label} must contain one JSON object")
    expected = {field.name for field in fields(cls)}
    if set(data) != expected:
        raise ObservationInputError(f"{label} field set does not match the typed schema")
    try:
        return cls(**data)
    except TypeError as exc:
        raise ObservationInputError(f"{label} cannot be materialized as typed evidence") from exc


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Import a bounded physical console/UART/USB-serial log after an exact temporary-boot "
            "execution. Marker detection is evidence for later review only and never grants "
            "hardware or Beta credit automatically."
        )
    )
    parser.add_argument("--execution-evidence", type=Path, required=True)
    parser.add_argument("--offer-evidence", type=Path, required=True)
    parser.add_argument("--raw-capture", type=Path, required=True)
    parser.add_argument(
        "--source-kind",
        required=True,
        choices=("serial-console", "uart", "usb-serial", "operator-console-log"),
    )
    parser.add_argument("--rescue-lock", type=Path, default=Path("tools/rescue-payload-lock.json"))
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    try:
        execution = _load_typed(
            TemporaryBootExecutionEvidence, args.execution_evidence, "temporary-boot execution evidence"
        )
        offer = _load_typed(
            TemporaryBootOfferEvidence, args.offer_evidence, "temporary-boot offer evidence"
        )
        contract = load_rescue_observation_contract(args.rescue_lock, args.repository_root)
        observation = create_physical_boot_observation(
            execution,
            offer,
            contract,
            raw_capture=args.raw_capture,
            source_kind=args.source_kind,
        )
        digest = write_physical_boot_observation(observation, args.out)
    except (ObservationInputError, PhysicalBootObservationError, OSError, ValueError) as exc:
        parser.error(str(exc))

    print(f"physical boot observation sha256={digest}")
    print(f"kernel_banner_observed={str(observation.kernel_banner_observed).lower()}")
    print(f"rescue_init_marker_observed={str(observation.rescue_init_marker_observed).lower()}")
    print(f"rescue_shell_marker_observed={str(observation.rescue_shell_marker_observed).lower()}")
    print(f"panic_marker_observed={str(observation.panic_marker_observed).lower()}")
    print(f"observation_review_eligible={str(observation.observation_review_eligible).lower()}")
    print("review_required=true")
    print("hardware_verified=false")
    print("beta_gate_credit=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
