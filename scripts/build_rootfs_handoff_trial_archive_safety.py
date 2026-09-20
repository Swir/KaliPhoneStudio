#!/usr/bin/env python3
"""Build create-only host evidence that a rootfs tar is extraction-safe by policy."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from kaliphonestudio.rootfs_handoff_trial_archive_safety import (
    RootfsHandoffTrialArchiveSafetyError,
    build_rootfs_handoff_trial_archive_safety_evidence,
    write_rootfs_handoff_trial_archive_safety_evidence,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build fail-closed rootfs archive extraction-safety evidence without extracting or writing a device."
    )
    parser.add_argument("--metadata-manifest", type=Path, required=True)
    parser.add_argument("--rootfs-artifact", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--json", action="store_true", help="print a machine-readable summary")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        evidence = build_rootfs_handoff_trial_archive_safety_evidence(
            args.metadata_manifest, args.rootfs_artifact
        )
        digest = write_rootfs_handoff_trial_archive_safety_evidence(evidence, args.out)
    except RootfsHandoffTrialArchiveSafetyError as exc:
        raise SystemExit(f"archive safety evidence blocked: {exc}") from exc

    summary = {
        "evidence_sha256": digest,
        "entry_count": evidence.entry_count,
        "symlink_count": evidence.symlink_count,
        "absolute_symlink_count": evidence.absolute_symlink_count,
        "hardlink_count": evidence.hardlink_count,
        "extraction_performed": evidence.extraction_performed,
        "persistent_write_authorized": evidence.persistent_write_authorized,
        "hardware_verified": evidence.hardware_verified,
        "beta_gate_credit": evidence.beta_gate_credit,
        "out": str(args.out),
    }
    if args.json:
        print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    else:
        print(
            "rootfs archive safety: PASS "
            f"entries={evidence.entry_count} symlinks={evidence.symlink_count} "
            f"hardlinks={evidence.hardlink_count} evidence_sha256={digest}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
