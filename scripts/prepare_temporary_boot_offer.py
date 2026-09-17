#!/usr/bin/env python3
"""Prepare and persist a temporary-boot offer; never execute Fastboot."""
from __future__ import annotations

import argparse
from dataclasses import fields
import json
from pathlib import Path
from typing import Any, TypeVar

from kaliphonestudio.fastboot_capture_bundle import FastbootCaptureBundleEvidence
from kaliphonestudio.fastboot_tool import FastbootToolEvidence
from kaliphonestudio.physical_candidate_gate import PhysicalCandidateGateEvidence
from kaliphonestudio.profiles import get_profile
from kaliphonestudio.temporary_boot_offer import (
    TemporaryBootOfferError,
    prepare_temporary_boot_offer,
    write_temporary_boot_offer,
)

MAX_EVIDENCE_BYTES = 2 * 1024 * 1024
T = TypeVar("T")


class OfferInputError(ValueError):
    pass


def _load_typed(cls: type[T], path: Path, label: str) -> T:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise OfferInputError(f"{label} must be a regular non-symlink JSON file")
    before = path.stat()
    if before.st_size <= 0 or before.st_size > MAX_EVIDENCE_BYTES:
        raise OfferInputError(f"{label} size is outside the evidence safety bound")
    raw = path.read_bytes()
    after = path.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise OfferInputError(f"{label} changed while being loaded")
    try:
        data: Any = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OfferInputError(f"{label} is not strict UTF-8 JSON") from exc
    if not isinstance(data, dict):
        raise OfferInputError(f"{label} must contain one JSON object")
    expected = {field.name for field in fields(cls)}
    if set(data) != expected:
        raise OfferInputError(f"{label} field set does not match the typed schema")
    try:
        return cls(**data)
    except TypeError as exc:
        raise OfferInputError(f"{label} cannot be materialized as typed evidence") from exc


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare the exact serial-bound temporary Fastboot boot argv from reviewed evidence. "
            "This command performs no Fastboot operation and does not authorize execution."
        )
    )
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--devices-root", type=Path, default=Path("devices"))
    parser.add_argument("--physical-candidate-gate", type=Path, required=True)
    parser.add_argument("--capture-bundle", type=Path, required=True)
    parser.add_argument("--fastboot-tool-evidence", type=Path, required=True)
    parser.add_argument("--fastboot-executable", type=Path, required=True)
    parser.add_argument("--boot-image", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    try:
        profile = get_profile(args.devices_root, args.profile_id)
        gate = _load_typed(
            PhysicalCandidateGateEvidence,
            args.physical_candidate_gate,
            "physical candidate gate",
        )
        capture = _load_typed(
            FastbootCaptureBundleEvidence,
            args.capture_bundle,
            "Fastboot capture bundle",
        )
        tool = _load_typed(
            FastbootToolEvidence,
            args.fastboot_tool_evidence,
            "Fastboot tool evidence",
        )
        offer = prepare_temporary_boot_offer(
            profile,
            gate,
            capture,
            tool,
            fastboot_executable=args.fastboot_executable,
            boot_image=args.boot_image,
        )
        digest = write_temporary_boot_offer(offer.evidence, args.out)
    except (OfferInputError, TemporaryBootOfferError, ValueError) as exc:
        parser.error(str(exc))

    print(offer.evidence.canonical_json(), end="")
    print(f"temporary boot offer sha256={digest}")
    print("argv preview (NOT EXECUTED):")
    print(json.dumps(list(offer.argv), ensure_ascii=False))
    print("persistent_write=false")
    print("temporary_boot_executed=false")
    print("phone_storage_written=false")
    print("hardware/Beta credit=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
