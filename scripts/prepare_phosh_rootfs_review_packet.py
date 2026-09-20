#!/usr/bin/env python3
"""Create a review-ready packet from one exact real A/B Phosh rootfs candidate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kaliphonestudio.phosh_rootfs_authority import (  # noqa: E402
    build_phosh_rootfs_review_packet,
    write_phosh_rootfs_review_packet,
)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidate-artifact", type=Path, required=True)
    p.add_argument("--reproducibility-candidate", type=Path, required=True)
    p.add_argument("--build-evidence", type=Path, required=True)
    p.add_argument("--repository", required=True)
    p.add_argument("--source-run-id", type=int, required=True)
    p.add_argument("--source-run-attempt", type=int, required=True)
    p.add_argument("--source-commit", required=True)
    p.add_argument("--out", type=Path, required=True)
    return p


def main() -> int:
    args = parser().parse_args()
    packet = build_phosh_rootfs_review_packet(
        candidate_artifact_path=args.candidate_artifact,
        reproducibility_candidate_path=args.reproducibility_candidate,
        selected_build_evidence_path=args.build_evidence,
        repository=args.repository,
        source_run_id=args.source_run_id,
        source_run_attempt=args.source_run_attempt,
        source_commit=args.source_commit,
    )
    digest = write_phosh_rootfs_review_packet(packet, args.out)
    print(json.dumps({
        "review_packet_sha256": digest,
        "rootfs_artifact_sha256": packet.rootfs_artifact_sha256,
        "rootfs_artifact_size": packet.rootfs_artifact_size,
        "package_manifest_sha256": packet.package_manifest_sha256,
        "package_count": packet.package_count,
        "ready_for_authority_review": packet.ready_for_authority_review,
        "reviewed": packet.reviewed,
        "reproducibility_authority": packet.reproducibility_authority,
        "hardware_verified": packet.hardware_verified,
        "beta_gate_credit": packet.beta_gate_credit,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
