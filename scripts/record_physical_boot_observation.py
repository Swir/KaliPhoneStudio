#!/usr/bin/env python3
"""Bind an operator-captured physical console transcript to exact boot/rescue evidence.

This command is intentionally offline: it never invokes adb/fastboot and never opens
serial/USB devices. The operator captures the raw console/log transcript separately.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kaliphonestudio.physical_boot_observation import (  # noqa: E402
    load_temporary_boot_execution_evidence,
    load_temporary_boot_runtime_probe_evidence,
    record_physical_boot_observation,
    write_physical_boot_observation_evidence,
)
from kaliphonestudio.profiles import get_profile  # noqa: E402
from kaliphonestudio.rescue_candidate import load_rescue_candidate_evidence  # noqa: E402


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Verify that a raw physical console/log transcript contains the exact "
            "deterministic rescue markers for one successful temporary-boot execution "
            "and bind it to the exact fresh runtime-probe/recovery chain. This does not "
            "connect to a phone and does not grant hardware/Beta credit."
        )
    )
    result.add_argument("--profile-id", required=True)
    result.add_argument("--devices-root", type=Path, default=ROOT / "devices")
    result.add_argument("--execution-evidence", type=Path, required=True)
    result.add_argument("--runtime-probe-evidence", type=Path, required=True)
    result.add_argument("--rescue-evidence", type=Path, required=True)
    result.add_argument("--console-transcript", type=Path, required=True)
    result.add_argument("--out", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.out.exists() or args.out.is_symlink():
        raise SystemExit(f"refusing to overwrite existing output: {args.out}")

    profile = get_profile(args.devices_root, args.profile_id)
    execution = load_temporary_boot_execution_evidence(args.execution_evidence)
    runtime_probe = load_temporary_boot_runtime_probe_evidence(args.runtime_probe_evidence)
    rescue = load_rescue_candidate_evidence(args.rescue_evidence)
    observation = record_physical_boot_observation(
        profile,
        execution,
        runtime_probe,
        rescue,
        args.console_transcript,
    )
    digest = write_physical_boot_observation_evidence(observation, args.out)

    print(f"profile_id={observation.profile_id}")
    print(f"device_serial={observation.device_serial}")
    print(f"runtime_probe_evidence_sha256={observation.runtime_probe_evidence_sha256}")
    print(f"boot_identity_binding_sha256={observation.boot_identity_binding_sha256}")
    print(f"recovery_readiness_sha256={observation.recovery_readiness_sha256}")
    print(f"rescue_probe_id={observation.rescue_probe_id}")
    print(f"transcript_sha256={observation.transcript_sha256}")
    print(f"rescue_init_observed={str(observation.rescue_init_observed).lower()}")
    print(
        "post_probe_material_revalidation_required="
        f"{str(observation.post_probe_material_revalidation_required).lower()}"
    )
    print(f"manual_review_required={str(observation.manual_review_required).lower()}")
    print(f"kali_early_userspace_verified={str(observation.kali_early_userspace_verified).lower()}")
    print(f"hardware_verified={str(observation.hardware_verified).lower()}")
    print(f"beta_gate_credit={str(observation.beta_gate_credit).lower()}")
    print(f"evidence_sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
