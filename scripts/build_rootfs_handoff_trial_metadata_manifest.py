from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from kaliphonestudio.rootfs_handoff_trial_metadata import (
    RootfsHandoffTrialMetadataError,
    build_rootfs_handoff_trial_metadata_manifest,
    write_rootfs_handoff_trial_metadata_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a create-only POSIX/PAX metadata manifest for one exact reviewed rootfs payload."
    )
    parser.add_argument("--payload-manifest", type=Path, required=True)
    parser.add_argument("--rootfs-artifact", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        evidence = build_rootfs_handoff_trial_metadata_manifest(args.payload_manifest, args.rootfs_artifact)
        digest = write_rootfs_handoff_trial_metadata_evidence(evidence, args.out)
    except (RootfsHandoffTrialMetadataError, OSError, ValueError) as exc:
        print(f"rootfs metadata manifest error: {exc}", file=sys.stderr)
        return 2
    result = {
        "path": str(args.out),
        "sha256": digest,
        "profile_id": evidence.profile_id,
        "device_serial": evidence.device_serial,
        "entry_count": evidence.entry_count,
        "pax_header_count": evidence.pax_header_count,
        "security_metadata_entry_count": evidence.security_metadata_entry_count,
        "posix_ownership_manifested": evidence.posix_ownership_manifested,
        "pax_metadata_manifested": evidence.pax_metadata_manifested,
        "interactive_writer_still_required": evidence.interactive_writer_still_required,
        "persistent_write_authorized": evidence.persistent_write_authorized,
        "hardware_verified": evidence.hardware_verified,
        "beta_gate_credit": evidence.beta_gate_credit,
    }
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(f"metadata manifest: {args.out}")
        print(f"sha256: {digest}")
        print(f"entries: {evidence.entry_count}; PAX headers: {evidence.pax_header_count}")
        print("phone I/O/write/hardware/Beta authority: no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
