#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.physical_rescue_diagnostics import (
    load_physical_boot_observation_for_diagnostics,
    record_physical_rescue_diagnostics,
    write_physical_rescue_diagnostics_evidence,
)
from kaliphonestudio.profiles import get_profile


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Bind read-only rescue sysfs inventory to an already recorded exact physical "
            "boot observation. This performs no phone I/O and grants no hardware/Beta credit."
        )
    )
    parser.add_argument("--devices-root", type=Path, default=Path("devices"))
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--observation-evidence", type=Path, required=True)
    parser.add_argument("--console-transcript", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    profile = get_profile(args.devices_root, args.profile_id)
    observation = load_physical_boot_observation_for_diagnostics(args.observation_evidence)
    evidence = record_physical_rescue_diagnostics(profile, observation, args.console_transcript)
    digest = write_physical_rescue_diagnostics_evidence(evidence, args.out)
    print(evidence.canonical_json(), end="")
    print(f"physical rescue diagnostics evidence sha256={digest}")
    print(
        "signals: "
        f"ufs={str(evidence.ufs_signal_observed).lower()} "
        f"battery={str(evidence.battery_signal_observed).lower()} "
        f"input={str(evidence.input_signal_observed).lower()} "
        f"graphics={str(evidence.graphics_signal_observed).lower()}"
    )
    print("manual review required: true")
    print("storage/display/charging/hardware/Beta verified: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
