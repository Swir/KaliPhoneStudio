#!/usr/bin/env python3
"""Bind an exact manual rootfs trial authorization review to reviewed evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from kaliphonestudio.rootfs_handoff_trial_authorization import (
    RootfsHandoffTrialAuthorizationError,
    bind_rootfs_handoff_trial_authorization_review,
    write_rootfs_handoff_trial_authorization_evidence,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Bind one exact manual authorization review to an accepted logical target and fresh-device revalidation. "
            "Acceptance only opens a later interactive execution boundary; this command performs no phone I/O, mount, trial or write."
        )
    )
    parser.add_argument("--target-binding", type=Path, required=True)
    parser.add_argument("--fresh-revalidation", type=Path, required=True)
    parser.add_argument("--review-record", type=Path, required=True)
    parser.add_argument("--review-notes", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        evidence = bind_rootfs_handoff_trial_authorization_review(
            args.target_binding,
            args.fresh_revalidation,
            args.review_record,
            args.review_notes,
        )
        digest = write_rootfs_handoff_trial_authorization_evidence(evidence, args.out)
    except (RootfsHandoffTrialAuthorizationError, OSError) as exc:
        print(f"Trial authorization binding error: {exc}", file=sys.stderr)
        return 2

    result = {
        "path": str(args.out),
        "sha256": digest,
        "profile_id": evidence.profile_id,
        "device_serial": evidence.device_serial,
        "decision": evidence.decision,
        "review_checks_complete": evidence.review_checks_complete,
        "manual_trial_authorization_accepted": evidence.manual_trial_authorization_accepted,
        "ready_for_interactive_trial_execution_boundary": evidence.ready_for_interactive_trial_execution_boundary,
        "live_device_recheck_required_at_execution": evidence.live_device_recheck_required_at_execution,
        "explicit_operator_confirmation_required_at_execution": evidence.explicit_operator_confirmation_required_at_execution,
        "trial_execution_allowed": evidence.trial_execution_allowed,
        "persistent_write_authorized": evidence.persistent_write_authorized,
        "hardware_verified": evidence.hardware_verified,
        "beta_release_authorized": evidence.beta_release_authorized,
        "beta_gate_credit": evidence.beta_gate_credit,
    }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"trial authorization evidence: {args.out}")
        print(f"sha256: {digest}")
        print(f"manual review decision: {evidence.decision}")
        print("trial executed / persistent write authorized: no")
        print("later live-device recheck + explicit operator confirmation required: yes")
        print("hardware/Beta authorization: no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
