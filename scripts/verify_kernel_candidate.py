#!/usr/bin/env python3
"""Verify and bind an offline kernel candidate against a device profile."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kaliphonestudio.kernel_bundle import (  # noqa: E402
    bind_kernel_candidate_evidence,
    write_kernel_candidate_evidence,
)
from kaliphonestudio.kernel_contract import (  # noqa: E402
    create_kernel_build_plan,
    verify_arm64_kernel_image,
    verify_generated_kernel_config,
    verify_kernel_checkout,
)
from kaliphonestudio.profiles import get_profile  # noqa: E402


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Verify an exact kernel checkout, final .config and ARM64 Image against "
            "a KaliPhoneStudio device profile, then emit canonical host-side evidence."
        )
    )
    result.add_argument("--profile-root", type=Path, default=ROOT / "devices")
    result.add_argument("--profile-id", required=True)
    result.add_argument("--checkout", type=Path, required=True)
    result.add_argument("--config", type=Path, required=True)
    result.add_argument("--image", type=Path, required=True)
    result.add_argument("--out", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    profile = get_profile(args.profile_root, args.profile_id)
    plan = create_kernel_build_plan(profile)
    checkout = verify_kernel_checkout(plan, args.checkout)
    config = verify_generated_kernel_config(plan, args.config)
    image = verify_arm64_kernel_image(plan, args.image)
    evidence = bind_kernel_candidate_evidence(
        plan,
        checkout,
        config,
        image,
        kernel_image=args.image,
    )
    evidence_digest = write_kernel_candidate_evidence(evidence, args.out)
    print(f"profile_id={evidence.profile_id}")
    print(f"kernel_plan_sha256={evidence.kernel_plan_sha256}")
    print(f"source_commit={evidence.source_commit}")
    print(f"kernel_version={evidence.kernel_version}")
    print(f"config_sha256={evidence.config_sha256}")
    print(f"image_sha256={evidence.image_sha256}")
    print(f"image_size={evidence.image_size}")
    print(f"evidence_sha256={evidence_digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
