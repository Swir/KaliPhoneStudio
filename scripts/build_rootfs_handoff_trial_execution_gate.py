#!/usr/bin/env python3
"""Build create-only rootfs interactive execution-gate evidence."""
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.rootfs_handoff_trial_execution_gate import (
    RootfsHandoffTrialExecutionGateError,
    build_rootfs_handoff_trial_execution_gate,
    write_rootfs_handoff_trial_execution_gate_evidence,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial-plan", type=Path, required=True)
    parser.add_argument("--trial-preflight", type=Path, required=True)
    parser.add_argument("--authorized-fresh-revalidation", type=Path, required=True)
    parser.add_argument("--execution-fresh-revalidation", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        evidence = build_rootfs_handoff_trial_execution_gate(
            args.trial_plan,
            args.trial_preflight,
            args.authorized_fresh_revalidation,
            args.execution_fresh_revalidation,
        )
        digest = write_rootfs_handoff_trial_execution_gate_evidence(evidence, args.out)
    except RootfsHandoffTrialExecutionGateError as exc:
        parser.error(str(exc))

    print(f"execution_gate_evidence={args.out}")
    print(f"execution_gate_sha256={digest}")
    print("execution_gate_passed=true")
    print("trial_execution_allowed=false")
    print("persistent_write_authorized=false")
    print("explicit_operator_confirmation_required=true")
    print("interactive_writer_required=true")
    print("beta_gate_credit=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
