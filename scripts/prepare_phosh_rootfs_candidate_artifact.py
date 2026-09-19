#!/usr/bin/env python3
"""Verify and package one exact real Phosh rootfs payload for later first-boot assembly."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kaliphonestudio.phosh_candidate_artifact import (  # noqa: E402
    PhoshCandidateArtifactError,
    materialize_phosh_rootfs_candidate,
    write_phosh_rootfs_candidate_artifact_evidence,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Cross-check one exact Phosh ARM64 rootfs payload and package manifest against "
            "a selected build plus independent A/B equality evidence. This prepares a "
            "first-boot assembly candidate only; it creates no authority or Beta credit."
        )
    )
    result.add_argument("--rootfs", type=Path, required=True)
    result.add_argument("--package-manifest", type=Path, required=True)
    result.add_argument("--build-evidence", type=Path, required=True)
    result.add_argument("--reproducibility-candidate", type=Path, required=True)
    result.add_argument("--selected-origin", required=True)
    result.add_argument("--out", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    evidence = materialize_phosh_rootfs_candidate(
        rootfs_artifact_path=args.rootfs,
        package_manifest_path=args.package_manifest,
        build_evidence_path=args.build_evidence,
        reproducibility_candidate_path=args.reproducibility_candidate,
        selected_build_origin=args.selected_origin,
    )
    digest = write_phosh_rootfs_candidate_artifact_evidence(evidence, args.out)
    print(f"rootfs_artifact_sha256={evidence.rootfs_artifact_sha256}")
    print(f"rootfs_artifact_size={evidence.rootfs_artifact_size}")
    print(f"package_manifest_sha256={evidence.package_manifest_sha256}")
    print(f"package_count={evidence.package_count}")
    print("rootfs_payload_verified=true")
    print("package_manifest_verified=true")
    print("independent_ab_match_verified=true")
    print("ready_for_first_boot_candidate_assembly=true")
    print("reproducibility_authority=false")
    print("hardware_verified=false")
    print("beta_gate_credit=false")
    print(f"candidate_artifact_evidence_sha256={digest}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PhoshCandidateArtifactError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
