#!/usr/bin/env python3
"""Build a non-executing physical functional-hardware test plan from reviewed evidence."""
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.physical_campaign_admission import load_current_physical_campaign_observation
from kaliphonestudio.physical_hardware_test_plan import (
    build_current_physical_hardware_test_plan_from_files,
    write_physical_hardware_test_plan,
)
from kaliphonestudio.profiles import get_profile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--devices-root", type=Path, default=Path("devices"))
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--boot-observation", type=Path, required=True)
    parser.add_argument("--hardware-review-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    profile = get_profile(args.devices_root, args.profile_id)
    observation = load_current_physical_campaign_observation(args.boot_observation)
    plan = build_current_physical_hardware_test_plan_from_files(
        profile, observation, args.hardware_review_evidence
    )
    digest = write_physical_hardware_test_plan(plan, args.output)
    blocked = [item["id"] for item in plan.tests if not item["context_signals_satisfied"]]
    print(f"physical hardware test plan: {args.output}")
    print(f"sha256: {digest}")
    print(f"tests: {plan.test_count}; Beta-required: {plan.beta_required_test_count}; all status=pending")
    print(f"Beta-required context ready: {str(plan.plan_ready_for_physical_execution).lower()}")
    if blocked:
        print("missing declared context signals for: " + ", ".join(blocked))
    print("hardware/Beta credit: false; phone storage written: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
