#!/usr/bin/env python3
"""Build immutable host-only Phosh/candidate provenance evidence."""
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.phosh_candidate_binding import (
    PhoshCandidateBindingError,
    build_phosh_candidate_binding_from_paths,
    write_phosh_candidate_binding,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Cross-bind an exact reviewed first-boot authority bundle to an exact "
            "reviewed Phosh/rootfs package binding. This command performs no device I/O."
        )
    )
    parser.add_argument("--candidate-authority-bundle", required=True, type=Path)
    parser.add_argument("--phosh-rootfs-binding", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        evidence = build_phosh_candidate_binding_from_paths(
            args.candidate_authority_bundle,
            args.phosh_rootfs_binding,
        )
        digest = write_phosh_candidate_binding(evidence, args.output)
    except PhoshCandidateBindingError as exc:
        raise SystemExit(f"refused: {exc}") from exc
    print(f"phosh_candidate_binding_sha256={digest}")
    print("ready_for_physical_phosh_validation=true")
    print("hardware_verified=false")
    print("beta_release_authorized=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
