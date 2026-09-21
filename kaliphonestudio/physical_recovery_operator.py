"""Offline operator CLI for exact physical recovery-readiness evidence.

This boundary binds already captured/read-only physical evidence to the exact local
stock ``boot.img`` required before any temporary-boot execution can be considered.
It performs no ADB/Fastboot command, selects no partition for writing, changes no
slot and grants no recovery, hardware or Beta credit.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .fastboot_baseline import FastbootBaselineEvidence
from .physical_baseline_bundle import PhysicalBaselineBundleEvidence
from .physical_boot_identity_binding import PhysicalBootIdentityBindingEvidence
from .physical_candidate_operator import (
    PhysicalCandidateOperatorError,
    _load_typed,
    _require_fresh_output,
)
from .physical_recovery_readiness import (
    PhysicalRecoveryReadinessError,
    build_physical_recovery_readiness,
    write_physical_recovery_readiness,
)
from .profiles import get_profile


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="build-physical-recovery-readiness",
        description=(
            "Offline: bind the exact captured Fastboot baseline, exact physical stock "
            "baseline, exact stock/candidate boot identity and the locally re-hashed "
            "matching stock boot.img into create-only recovery-readiness evidence. "
            "No device command, slot switch, flash/write or Beta promotion is performed."
        ),
    )
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--devices-root", type=Path, default=Path("devices"))
    parser.add_argument("--baseline-evidence", type=Path, required=True)
    parser.add_argument("--physical-baseline", type=Path, required=True)
    parser.add_argument("--boot-identity-binding", type=Path, required=True)
    parser.add_argument("--stock-boot", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        _require_fresh_output(args.out, "physical recovery-readiness evidence")
        profile = get_profile(args.devices_root, args.profile_id)
        baseline = _load_typed(
            FastbootBaselineEvidence,
            args.baseline_evidence,
            "Fastboot baseline evidence",
        )
        physical = _load_typed(
            PhysicalBaselineBundleEvidence,
            args.physical_baseline,
            "physical baseline bundle",
        )
        binding = _load_typed(
            PhysicalBootIdentityBindingEvidence,
            args.boot_identity_binding,
            "physical boot identity binding",
        )
        evidence = build_physical_recovery_readiness(
            profile,
            baseline,
            physical,
            binding,
            stock_boot=args.stock_boot,
        )
        digest = write_physical_recovery_readiness(evidence, args.out)
    except (
        PhysicalCandidateOperatorError,
        PhysicalRecoveryReadinessError,
        ValueError,
        OSError,
    ) as exc:
        parser.error(str(exc))

    print(evidence.canonical_json(), end="")
    print(f"physical recovery-readiness sha256={digest}")
    print("ready_for_temporary_boot_safety_review=true")
    print("slot_switch_authorized=false")
    print("inactive_slot_write_authorized=false")
    print("persistent_write_authorized=false")
    print("rollback_exercised=false")
    print("recovery_verified=false")
    print("hardware/Beta credit=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
