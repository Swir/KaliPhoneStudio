#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.physical_rescue_diagnostics import (
    load_physical_boot_observation_for_diagnostics,
    load_physical_rescue_diagnostics_evidence,
)
from kaliphonestudio.physical_rescue_functional_probes import (
    PhysicalRescueFunctionalProbeError,
    record_physical_rescue_functional_probes,
    write_physical_rescue_functional_probe_evidence,
)
from kaliphonestudio.profiles import get_profile


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Bind an explicitly invoked read-only rescue probe transcript to exact prior "
            "physical observation/diagnostic evidence. This performs no phone I/O."
        )
    )
    parser.add_argument("--devices-root", type=Path, default=Path("devices"))
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--physical-observation", type=Path, required=True)
    parser.add_argument("--rescue-diagnostics", type=Path, required=True)
    parser.add_argument("--console-transcript", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    try:
        profile = get_profile(args.devices_root, args.profile_id)
        observation = load_physical_boot_observation_for_diagnostics(args.physical_observation)
        diagnostics = load_physical_rescue_diagnostics_evidence(args.rescue_diagnostics)
        evidence = record_physical_rescue_functional_probes(
            profile,
            observation,
            diagnostics,
            args.console_transcript,
        )
        digest = write_physical_rescue_functional_probe_evidence(evidence, args.out)
    except (ValueError, PhysicalRescueFunctionalProbeError) as exc:
        parser.error(str(exc))

    print(evidence.canonical_json(), end="")
    print(f"physical rescue functional probe evidence sha256={digest}")
    print("storage/charging/hardware/Beta credit: false; manual review required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
