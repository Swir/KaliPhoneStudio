#!/usr/bin/env python3
"""Build one immutable cross-campaign physical release-gate audit packet."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from kaliphonestudio.physical_release_gate_audit import (
    PhysicalReleaseGateAuditError,
    build_physical_release_gate_audit_from_files,
    write_physical_release_gate_audit_evidence,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Cross-bind an exact physical bring-up dossier/review with the exact "
            "physical functional-result bundle for manual release-gate review. "
            "This command performs no phone I/O and never authorizes writes or Beta."
        )
    )
    parser.add_argument("--dossier", type=Path, required=True)
    parser.add_argument("--dossier-verification", type=Path, required=True)
    parser.add_argument("--dossier-review", type=Path, required=True)
    parser.add_argument("--functional-result-bundle", type=Path, required=True)
    parser.add_argument("--test-plan", type=Path, required=True)
    parser.add_argument("--test-plan-review", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        evidence = build_physical_release_gate_audit_from_files(
            args.dossier,
            args.dossier_verification,
            args.dossier_review,
            args.functional_result_bundle,
            args.test_plan,
            args.test_plan_review,
        )
        digest = write_physical_release_gate_audit_evidence(evidence, args.out)
    except PhysicalReleaseGateAuditError as exc:
        raise SystemExit(f"release-gate audit rejected: {exc}") from exc

    print(
        json.dumps(
            {
                "output": str(args.out),
                "sha256": digest,
                "profile_id": evidence.profile_id,
                "device_serial": evidence.device_serial,
                "cross_campaign_context_verified": evidence.cross_campaign_context_verified,
                "beta_required_tests_all_reviewed_pass": evidence.beta_required_tests_all_reviewed_pass,
                "kali_early_userspace_signal_present": evidence.kali_early_userspace_signal_present,
                "manual_release_gate_review_required": evidence.manual_release_gate_review_required,
                "physical_gate_still_incomplete": evidence.physical_gate_still_incomplete,
                "hardware_verified": evidence.hardware_verified,
                "beta_release_authorized": evidence.beta_release_authorized,
                "beta_gate_credit": evidence.beta_gate_credit,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
