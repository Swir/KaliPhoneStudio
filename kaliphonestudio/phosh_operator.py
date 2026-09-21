"""Frozen host-only Phosh handoff commands for the physical AC2003 campaign."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .phosh_first_boot_binding import (
    PhoshFirstBootBindingError,
    build_phosh_first_boot_binding_from_paths,
    write_phosh_first_boot_binding,
)
from .phosh_physical_candidate_adapter import (
    PhoshPhysicalCandidateAdapterError,
    build_phosh_physical_candidate_adapter_from_paths,
    write_phosh_physical_candidate_adapter,
)
from .phosh_successor_candidate import (
    PhoshSuccessorCandidateError,
    build_phosh_successor_candidate_from_paths,
    write_phosh_successor_candidate,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Host-only reviewed Phosh handoff. These commands bind evidence only; "
            "they do not run Fastboot, stage rootfs bytes, write phone storage, "
            "verify hardware, or grant Beta credit."
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)

    binding = sub.add_parser(
        "build-first-boot-binding",
        help="bind reviewed Phosh rootfs authority to the reviewed base authority bundle",
    )
    binding.add_argument("--candidate-authority-bundle", type=Path, required=True)
    binding.add_argument("--phosh-rootfs-authority", type=Path, required=True)
    binding.add_argument("--phosh-review-packet", type=Path, required=True)
    binding.add_argument("--out", type=Path, required=True)

    successor = sub.add_parser(
        "build-successor-candidate",
        help="build an immutable Phosh successor first-boot candidate",
    )
    successor.add_argument("--base-first-boot-manifest", type=Path, required=True)
    successor.add_argument("--base-authority-bundle", type=Path, required=True)
    successor.add_argument("--phosh-first-boot-binding", type=Path, required=True)
    successor.add_argument("--out", type=Path, required=True)

    adapter = sub.add_parser(
        "bind-physical-candidate",
        help="cross-bind the reviewed Phosh successor to the exact physical candidate gate",
    )
    adapter.add_argument("--phosh-successor-candidate", type=Path, required=True)
    adapter.add_argument("--physical-candidate-gate", type=Path, required=True)
    adapter.add_argument("--out", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        if args.command == "build-first-boot-binding":
            evidence = build_phosh_first_boot_binding_from_paths(
                args.candidate_authority_bundle,
                args.phosh_rootfs_authority,
                args.phosh_review_packet,
            )
            digest = write_phosh_first_boot_binding(evidence, args.out)
            print(f"phosh_first_boot_binding_sha256={digest}")
            print(f"profile_id={evidence.profile_id}")
            print("candidate_manifest_regeneration_required=true")
        elif args.command == "build-successor-candidate":
            evidence = build_phosh_successor_candidate_from_paths(
                args.base_first_boot_manifest,
                args.base_authority_bundle,
                args.phosh_first_boot_binding,
            )
            digest = write_phosh_successor_candidate(evidence, args.out)
            print(f"phosh_successor_candidate_sha256={digest}")
            print(f"profile_id={evidence.profile_id}")
            print("physical_validation_required=true")
        else:
            evidence = build_phosh_physical_candidate_adapter_from_paths(
                args.phosh_successor_candidate,
                args.physical_candidate_gate,
            )
            digest = write_phosh_physical_candidate_adapter(evidence, args.out)
            print(f"phosh_physical_candidate_adapter_sha256={digest}")
            print(f"profile_id={evidence.profile_id}")
            print("ready_for_physical_staging_review=true")
    except (
        PhoshFirstBootBindingError,
        PhoshSuccessorCandidateError,
        PhoshPhysicalCandidateAdapterError,
        OSError,
    ) as exc:
        parser.error(str(exc))

    print("phone_storage_written=false")
    print("hardware_verified=false")
    print("beta_gate_credit=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
