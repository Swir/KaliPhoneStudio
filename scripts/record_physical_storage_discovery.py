#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.physical_rescue_diagnostics import load_physical_rescue_diagnostics_evidence
from kaliphonestudio.physical_rescue_functional_probes import load_physical_rescue_functional_probe_evidence
from kaliphonestudio.physical_storage_discovery import (
    load_rootfs_handoff_assessment,
    record_physical_storage_discovery,
    write_physical_storage_discovery_evidence,
)
from kaliphonestudio.profiles import get_profile


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Bind read-only physical storage observations to one exact rootfs-handoff assessment. "
            "This never selects a target or authorizes a storage write."
        )
    )
    parser.add_argument("--devices-root", type=Path, default=Path("devices"))
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--handoff-assessment", type=Path, required=True)
    parser.add_argument("--rescue-diagnostics", type=Path, required=True)
    parser.add_argument("--functional-probes", type=Path, required=True)
    parser.add_argument("--discovery-report", type=Path, required=True)
    parser.add_argument("--recovery-plan", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    profile = get_profile(args.devices_root, args.profile_id)
    assessment = load_rootfs_handoff_assessment(args.handoff_assessment)
    diagnostics = load_physical_rescue_diagnostics_evidence(args.rescue_diagnostics)
    functional = load_physical_rescue_functional_probe_evidence(args.functional_probes)
    evidence = record_physical_storage_discovery(
        profile,
        assessment,
        diagnostics,
        functional,
        args.discovery_report,
        args.recovery_plan,
    )
    digest = write_physical_storage_discovery_evidence(evidence, args.out)
    print(evidence.canonical_json(), end="")
    print(f"physical storage discovery evidence sha256={digest}")
    print("target selected: false")
    print("write authorized: false")
    print("hardware/Beta credit: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
