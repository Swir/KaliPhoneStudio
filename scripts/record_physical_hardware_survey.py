#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.physical_hardware_survey import (
    record_physical_hardware_survey,
    write_physical_hardware_survey_evidence,
)
from kaliphonestudio.physical_rescue_diagnostics import (
    load_physical_boot_observation_for_diagnostics,
    load_physical_rescue_diagnostics_evidence,
)
from kaliphonestudio.profiles import get_profile


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Bind bounded read-only hardware-presence markers to one exact rescue boot. "
            "This performs no phone I/O, does not activate hardware and grants no hardware/Beta credit."
        )
    )
    parser.add_argument("--devices-root", type=Path, default=Path("devices"))
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--observation-evidence", type=Path, required=True)
    parser.add_argument("--rescue-diagnostics-evidence", type=Path, required=True)
    parser.add_argument("--console-transcript", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    profile = get_profile(args.devices_root, args.profile_id)
    observation = load_physical_boot_observation_for_diagnostics(args.observation_evidence)
    diagnostics = load_physical_rescue_diagnostics_evidence(args.rescue_diagnostics_evidence)
    evidence = record_physical_hardware_survey(
        profile,
        observation,
        diagnostics,
        args.console_transcript,
    )
    digest = write_physical_hardware_survey_evidence(evidence, args.out)
    print(evidence.canonical_json(), end="")
    print(f"physical hardware survey evidence sha256={digest}")
    print(
        "observed-presence signals: "
        f"usb={str(evidence.usb_signal_observed).lower()} "
        f"network={str(evidence.network_signal_observed).lower()} "
        f"wifi={str(evidence.wifi_signal_observed).lower()} "
        f"bluetooth={str(evidence.bluetooth_signal_observed).lower()} "
        f"audio={str(evidence.audio_signal_observed).lower()} "
        f"thermal={str(evidence.thermal_signal_observed).lower()} "
        f"input={str(evidence.input_signal_observed).lower()} "
        f"display={str(evidence.display_signal_observed).lower()} "
        f"power={str(evidence.power_signal_observed).lower()}"
    )
    print("manual review required: true")
    print("presence does not prove functionality; all hardware/Beta verification flags remain false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
