#!/usr/bin/env python3
"""Build host-only binding for reviewed Phosh rootfs candidate regeneration."""
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.phosh_first_boot_binding import (
    PhoshFirstBootBindingError,
    build_phosh_first_boot_binding_from_paths,
    write_phosh_first_boot_binding,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Cross-bind one reviewed first-boot kernel/DT authority bundle with a "
            "reviewed Phosh rootfs authority. This produces host-only evidence that "
            "a successor candidate manifest must be regenerated; it never performs "
            "device I/O or grants hardware/Beta credit."
        )
    )
    parser.add_argument(
        "--candidate-authority-bundle",
        required=True,
        type=Path,
        help="canonical FirstBootAuthorityBundleEvidence JSON for the base candidate",
    )
    parser.add_argument(
        "--phosh-rootfs-authority",
        required=True,
        type=Path,
        help="canonical reviewed PhoshRootfsAuthorityRecord JSON",
    )
    parser.add_argument(
        "--phosh-review-packet",
        required=True,
        type=Path,
        help="canonical review packet bound to the reviewed Phosh authority",
    )
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="new canonical Phosh first-boot regeneration binding JSON",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        evidence = build_phosh_first_boot_binding_from_paths(
            args.candidate_authority_bundle,
            args.phosh_rootfs_authority,
            args.phosh_review_packet,
        )
        digest = write_phosh_first_boot_binding(evidence, args.out)
    except PhoshFirstBootBindingError as exc:
        raise SystemExit(f"phosh-first-boot-binding: {exc}") from exc

    print(f"phosh_first_boot_binding_sha256={digest}")
    print(f"profile_id={evidence.profile_id}")
    print(f"base_first_boot_manifest_sha256={evidence.base_first_boot_manifest_sha256}")
    print(f"phosh_rootfs_artifact_sha256={evidence.phosh_rootfs_artifact_sha256}")
    print("candidate_manifest_regeneration_required=true")
    print("hardware_verified=false")
    print("beta_gate_credit=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
