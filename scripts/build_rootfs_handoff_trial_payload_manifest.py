"""Create a deterministic host-only rootfs trial payload manifest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from kaliphonestudio.rootfs_handoff_trial_payload import (
    RootfsHandoffTrialPayloadError,
    build_rootfs_handoff_trial_payload_manifest,
    write_rootfs_handoff_trial_payload_evidence,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect the exact reviewed rootfs archive, reject unsafe tar scope, and bind the expanded payload "
            "plus deterministic capacity requirement to an exact rootfs execution-gate file. This command "
            "performs no phone I/O, mount, extraction or write."
        )
    )
    parser.add_argument("--execution-gate", type=Path, required=True)
    parser.add_argument("--rootfs-artifact", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--json", action="store_true", help="Print a machine-readable summary.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        evidence = build_rootfs_handoff_trial_payload_manifest(args.execution_gate, args.rootfs_artifact)
        digest = write_rootfs_handoff_trial_payload_evidence(evidence, args.out)
    except (RootfsHandoffTrialPayloadError, OSError, ValueError) as exc:
        raise SystemExit(f"rootfs payload manifest blocked: {exc}") from exc

    result = {
        "status": "manifested-no-write",
        "output": str(args.out),
        "evidence_sha256": digest,
        "profile_id": evidence.profile_id,
        "device_serial": evidence.device_serial,
        "entry_count": evidence.entry_count,
        "regular_payload_bytes": evidence.regular_payload_bytes,
        "minimum_required_free_bytes": evidence.minimum_required_free_bytes,
        "reviewed_required_free_bytes": evidence.reviewed_required_free_bytes,
        "observed_free_bytes": evidence.observed_free_bytes,
        "interactive_writer_still_required": evidence.interactive_writer_still_required,
        "persistent_write_authorized": evidence.persistent_write_authorized,
        "phone_storage_written": evidence.phone_storage_written,
        "hardware_verified": evidence.hardware_verified,
        "beta_gate_credit": evidence.beta_gate_credit,
    }
    if args.json:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        print(f"payload manifest: {args.out}")
        print(f"evidence sha256: {digest}")
        print(f"entries: {evidence.entry_count}")
        print(f"expanded regular bytes: {evidence.regular_payload_bytes}")
        print(f"minimum free bytes: {evidence.minimum_required_free_bytes}")
        print("persistent write authorized: false")
        print("interactive writer still required: true")
        print("Beta gate credit: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
