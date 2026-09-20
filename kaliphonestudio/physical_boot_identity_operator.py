"""Offline operator CLI for exact physical stock/candidate boot identity binding.

This command re-inspects exact local stock/candidate boot-chain bytes and binds them
to the already reviewed physical baseline/candidate/provenance/build-plan evidence.
It performs no ADB/Fastboot command, no slot change and no phone-storage write.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .physical_baseline_bundle import PhysicalBaselineBundleEvidence
from .physical_boot_identity_binding import (
    PhysicalBootIdentityBindingError,
    bind_physical_boot_identity,
    write_physical_boot_identity_binding,
)
from .physical_candidate_gate import PhysicalCandidateGateEvidence
from .physical_candidate_operator import (
    PhysicalCandidateOperatorError,
    _load_boot_plan,
    _load_typed,
    _require_fresh_output,
)
from .profiles import get_profile
from .provenance import StockBootProvenance


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bind-physical-boot-identity",
        description=(
            "Offline: re-inspect and bind exact stock/candidate boot-chain bytes to "
            "the reviewed physical baseline, candidate gate, immutable stock provenance "
            "and boot plan. No device I/O, temporary boot or persistent write occurs."
        ),
    )
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--devices-root", type=Path, default=Path("devices"))
    parser.add_argument("--physical-baseline", type=Path, required=True)
    parser.add_argument("--physical-candidate-gate", type=Path, required=True)
    parser.add_argument("--stock-provenance", type=Path, required=True)
    parser.add_argument("--boot-plan", type=Path, required=True)
    parser.add_argument("--stock-boot", type=Path, required=True)
    parser.add_argument("--candidate-boot", type=Path, required=True)
    parser.add_argument(
        "--candidate-dtbo",
        type=Path,
        help="Exact external candidate DTBO when required by the selected profile.",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        _require_fresh_output(args.out, "physical boot identity binding")
        profile = get_profile(args.devices_root, args.profile_id)
        physical = _load_typed(
            PhysicalBaselineBundleEvidence,
            args.physical_baseline,
            "physical baseline bundle",
        )
        gate = _load_typed(
            PhysicalCandidateGateEvidence,
            args.physical_candidate_gate,
            "physical candidate gate",
        )
        provenance = _load_typed(
            StockBootProvenance,
            args.stock_provenance,
            "stock boot provenance",
        )
        plan = _load_boot_plan(args.boot_plan)
        evidence = bind_physical_boot_identity(
            profile,
            physical,
            gate,
            provenance,
            plan,
            stock_boot=args.stock_boot,
            candidate_boot=args.candidate_boot,
            candidate_dtbo=args.candidate_dtbo,
        )
        digest = write_physical_boot_identity_binding(evidence, args.out)
    except (
        PhysicalCandidateOperatorError,
        PhysicalBootIdentityBindingError,
        ValueError,
        OSError,
    ) as exc:
        parser.error(str(exc))

    print(evidence.canonical_json(), end="")
    print(f"physical boot identity binding sha256={digest}")
    print("stock_exact_bytes_verified=true")
    print("candidate_exact_bytes_verified=true")
    print("component_identity_bound=true")
    print("avb_layout_bound=true")
    print("temporary_boot_executed=false")
    print("phone_storage_written=false")
    print("hardware/Beta credit=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
