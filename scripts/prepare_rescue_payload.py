#!/usr/bin/env python3
"""Verify a static ARM64 BusyBox and create deterministic rescue staging."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kaliphonestudio.rescue_payload import (  # noqa: E402
    load_rescue_payload_lock,
    prepare_rescue_staging,
    write_rescue_payload_evidence,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Validate a source-locked static ARM64 BusyBox plus independently captured "
            "applet list and stage KaliPhoneStudio's offline early-rescue userspace."
        )
    )
    result.add_argument("--lock", type=Path, default=ROOT / "tools" / "rescue-payload-lock.json")
    result.add_argument("--busybox", type=Path, required=True)
    result.add_argument("--applets", type=Path, required=True)
    result.add_argument("--init", dest="init_template", type=Path, default=ROOT / "rescue" / "init")
    result.add_argument("--staging", type=Path, required=True)
    result.add_argument("--evidence", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    lock = load_rescue_payload_lock(args.lock)
    evidence = prepare_rescue_staging(
        lock,
        busybox=args.busybox,
        applet_list=args.applets,
        init_template=args.init_template,
        destination=args.staging,
    )
    digest = write_rescue_payload_evidence(evidence, args.evidence)
    print(f"payload_id={evidence.payload_id}")
    print(f"architecture={evidence.architecture}")
    print(f"busybox_version={evidence.busybox_version}")
    print(f"busybox_sha256={evidence.busybox_sha256}")
    print(f"busybox_size={evidence.busybox_size}")
    print(f"applet_count={evidence.applet_count}")
    print(f"staging_manifest_sha256={evidence.staging_manifest_sha256}")
    print(f"evidence_sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
