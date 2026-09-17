#!/usr/bin/env python3
"""Bind already-recorded physical bring-up evidence into one audit session.

This CLI performs no phone I/O.  It never invokes Fastboot/ADB and cannot select
or authorize a storage target.  All inputs must already exist as exact evidence
records created by the corresponding KaliPhoneStudio stages.
"""
from __future__ import annotations

import argparse
from dataclasses import fields
import json
from pathlib import Path
from typing import Any, TypeVar

from kaliphonestudio.physical_boot_observation import PhysicalBootObservationEvidence
from kaliphonestudio.physical_bringup_session import (
    PhysicalBringupSessionError,
    bind_physical_bringup_session,
    write_physical_bringup_session_evidence,
)
from kaliphonestudio.physical_candidate_gate import PhysicalCandidateGateEvidence
from kaliphonestudio.physical_kali_early_userspace import (
    PhysicalKaliEarlyUserspaceEvidence,
    validate_physical_kali_early_userspace_evidence,
)
from kaliphonestudio.physical_rescue_diagnostics import (
    load_physical_boot_observation_for_diagnostics,
    load_physical_rescue_diagnostics_evidence,
)
from kaliphonestudio.physical_rescue_functional_probes import (
    load_physical_rescue_functional_probe_evidence,
)
from kaliphonestudio.physical_storage_discovery import (
    load_physical_storage_discovery_evidence,
)
from kaliphonestudio.physical_storage_review import (
    load_physical_storage_review_evidence,
)

T = TypeVar("T")
_MAX_SIMPLE_EVIDENCE_BYTES = 4 * 1024 * 1024


def _load_simple_dataclass(path: Path, cls: type[T], label: str) -> T:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PhysicalBringupSessionError(f"{label} must be a regular non-symlink file")
    before = source.stat()
    raw = source.read_bytes()
    after = source.stat()
    if before.st_size <= 0 or before.st_size > _MAX_SIMPLE_EVIDENCE_BYTES or len(raw) != before.st_size:
        raise PhysicalBringupSessionError(f"{label} size is outside the safety limit")
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise PhysicalBringupSessionError(f"{label} changed while being read")
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalBringupSessionError(f"{label} is not valid UTF-8 JSON") from exc
    expected = {item.name for item in fields(cls)}
    if not isinstance(value, dict) or set(value) != expected:
        raise PhysicalBringupSessionError(f"{label} fields do not match expected schema")
    try:
        return cls(**value)
    except TypeError as exc:
        raise PhysicalBringupSessionError(f"{label} types are invalid") from exc


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Cross-bind exact physical candidate/rescue/storage-review evidence into one "
            "non-release audit session without phone I/O or storage authorization."
        )
    )
    parser.add_argument("--candidate-gate", type=Path, required=True)
    parser.add_argument("--boot-observation", type=Path, required=True)
    parser.add_argument("--rescue-diagnostics", type=Path, required=True)
    parser.add_argument("--functional-probes", type=Path, required=True)
    parser.add_argument("--storage-discovery", type=Path, required=True)
    parser.add_argument("--storage-review", type=Path, required=True)
    parser.add_argument(
        "--kali-early-userspace",
        type=Path,
        default=None,
        help="optional exact physical Kali early-userspace observation evidence",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    try:
        gate = _load_simple_dataclass(args.candidate_gate, PhysicalCandidateGateEvidence, "physical candidate gate")
        observation: PhysicalBootObservationEvidence = load_physical_boot_observation_for_diagnostics(args.boot_observation)
        diagnostics = load_physical_rescue_diagnostics_evidence(args.rescue_diagnostics)
        functional = load_physical_rescue_functional_probe_evidence(args.functional_probes)
        discovery = load_physical_storage_discovery_evidence(args.storage_discovery)
        review = load_physical_storage_review_evidence(args.storage_review)
        early = None
        if args.kali_early_userspace is not None:
            early = _load_simple_dataclass(
                args.kali_early_userspace,
                PhysicalKaliEarlyUserspaceEvidence,
                "physical Kali early-userspace evidence",
            )
            validate_physical_kali_early_userspace_evidence(early)
        evidence = bind_physical_bringup_session(
            gate,
            observation,
            diagnostics,
            functional,
            discovery,
            review,
            early_userspace=early,
        )
        digest = write_physical_bringup_session_evidence(evidence, args.out)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))

    print(evidence.canonical_json(), end="")
    print(f"physical bring-up session evidence sha256={digest}")
    print("storage target selected: false")
    print("write authorized: false")
    print("hardware/Beta credit: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
