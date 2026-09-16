#!/usr/bin/env python3
"""Import a saved fastboot getvar-all transcript as profile-bound evidence.

The command is intentionally offline: it never invokes adb/fastboot and never
writes to a phone. Capture the transcript separately, then import it here.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kaliphonestudio.fastboot_baseline import (  # noqa: E402
    capture_fastboot_baseline,
    write_fastboot_baseline_evidence,
)
from kaliphonestudio.profiles import get_profile  # noqa: E402


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Validate an operator-captured fastboot getvar-all transcript against a "
            "device profile and exact firmware metadata. No phone command is run."
        )
    )
    result.add_argument("--profile-id", required=True)
    result.add_argument("--devices-root", type=Path, default=ROOT / "devices")
    result.add_argument("--transcript", type=Path, required=True)
    result.add_argument("--firmware-build", required=True)
    result.add_argument("--firmware-fingerprint", required=True)
    result.add_argument("--out", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.out.exists():
        raise SystemExit(f"refusing to overwrite existing evidence: {args.out}")
    profile = get_profile(args.devices_root, args.profile_id)
    evidence = capture_fastboot_baseline(
        profile,
        transcript=args.transcript,
        firmware_build=args.firmware_build,
        firmware_fingerprint=args.firmware_fingerprint,
    )
    digest = write_fastboot_baseline_evidence(evidence, args.out)
    print(f"profile_id={evidence.profile_id}")
    print(f"product={evidence.product}")
    print(f"serialno={evidence.serialno}")
    print(f"current_slot={evidence.current_slot or 'n/a'}")
    print(f"slot_count={evidence.slot_count if evidence.slot_count is not None else 'n/a'}")
    print(f"unlocked={'yes' if evidence.unlocked else 'no'}")
    print(f"secure={'yes' if evidence.secure else 'no'}")
    print(f"transcript_sha256={evidence.transcript_sha256}")
    print(f"evidence_sha256={digest}")
    print("beta_gate_credit=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
