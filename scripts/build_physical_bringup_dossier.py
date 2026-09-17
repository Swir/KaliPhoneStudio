#!/usr/bin/env python3
"""Build an exact-file audit dossier for one already-bound physical session.

This command performs no phone I/O. It verifies that the supplied evidence and
raw capture files are exactly the bytes named by PhysicalBringupSessionEvidence,
then writes one immutable non-release manifest for manual audit/archive use.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.physical_bringup_dossier import (
    PhysicalBringupDossierError,
    build_physical_bringup_dossier,
    write_physical_bringup_dossier_evidence,
)
from kaliphonestudio.physical_bringup_session import (
    load_physical_bringup_session_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify and bind the exact on-disk byte set for one physical bring-up "
            "session without phone I/O, target selection or write authorization."
        )
    )
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--candidate-gate", type=Path, required=True)
    parser.add_argument("--boot-observation", type=Path, required=True)
    parser.add_argument("--rescue-diagnostics", type=Path, required=True)
    parser.add_argument("--functional-probes", type=Path, required=True)
    parser.add_argument("--storage-discovery", type=Path, required=True)
    parser.add_argument("--storage-review", type=Path, required=True)
    parser.add_argument("--rescue-transcript", type=Path, required=True)
    parser.add_argument("--storage-discovery-report", type=Path, required=True)
    parser.add_argument("--recovery-plan", type=Path, required=True)
    parser.add_argument("--storage-review-record", type=Path, required=True)
    parser.add_argument("--storage-review-notes", type=Path, required=True)
    parser.add_argument("--kali-early-userspace-evidence", type=Path, default=None)
    parser.add_argument("--kali-early-userspace-transcript", type=Path, default=None)
    parser.add_argument(
        "--rootfs-artifact",
        type=Path,
        default=None,
        help="optional exact rootfs file; when supplied its SHA-256 and size are verified",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    if (args.kali_early_userspace_evidence is None) != (
        args.kali_early_userspace_transcript is None
    ):
        parser.error(
            "Kali early-userspace evidence and transcript must be supplied together"
        )

    evidence_files = {
        "physical_candidate_gate": args.candidate_gate,
        "physical_boot_observation": args.boot_observation,
        "rescue_diagnostics": args.rescue_diagnostics,
        "rescue_functional_probe": args.functional_probes,
        "physical_storage_discovery": args.storage_discovery,
        "physical_storage_review": args.storage_review,
    }
    raw_files = {
        "rescue_transcript": args.rescue_transcript,
        "storage_discovery_report": args.storage_discovery_report,
        "recovery_plan": args.recovery_plan,
        "storage_review_record": args.storage_review_record,
        "storage_review_notes": args.storage_review_notes,
    }
    if args.kali_early_userspace_evidence is not None:
        evidence_files["kali_early_userspace_evidence"] = (
            args.kali_early_userspace_evidence
        )
        raw_files["kali_early_userspace_transcript"] = (
            args.kali_early_userspace_transcript
        )

    try:
        session = load_physical_bringup_session_evidence(args.session)
        dossier = build_physical_bringup_dossier(
            session,
            session_file=args.session,
            evidence_files=evidence_files,
            raw_files=raw_files,
            rootfs_artifact=args.rootfs_artifact,
        )
        digest = write_physical_bringup_dossier_evidence(dossier, args.out)
    except (PhysicalBringupDossierError, ValueError, OSError) as exc:
        parser.error(str(exc))

    print(dossier.canonical_json(), end="")
    print(f"physical bring-up dossier evidence sha256={digest}")
    print(f"exact files verified={dossier.supplied_file_count}")
    print(f"rootfs artifact file verified={str(dossier.rootfs_artifact_file_verified).lower()}")
    print("target selected: false")
    print("write authorized: false")
    print("hardware/Beta credit: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
