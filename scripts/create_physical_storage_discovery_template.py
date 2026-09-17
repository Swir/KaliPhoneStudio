#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.physical_rescue_diagnostics import load_physical_rescue_diagnostics_evidence
from kaliphonestudio.physical_rescue_functional_probes import load_physical_rescue_functional_probe_evidence
from kaliphonestudio.physical_storage_discovery import load_rootfs_handoff_assessment
from kaliphonestudio.physical_storage_template import (
    create_physical_storage_discovery_template,
    write_physical_storage_discovery_template,
)
from kaliphonestudio.profiles import get_profile


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create an operator-editable no-write storage-discovery template from exact rescue evidence. "
            "Unknown filesystem/encryption/free-space fields remain unobserved."
        )
    )
    parser.add_argument("--devices-root", type=Path, default=Path("devices"))
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--handoff-assessment", type=Path, required=True)
    parser.add_argument("--rescue-diagnostics", type=Path, required=True)
    parser.add_argument("--functional-probes", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    profile = get_profile(args.devices_root, args.profile_id)
    assessment = load_rootfs_handoff_assessment(args.handoff_assessment)
    diagnostics = load_physical_rescue_diagnostics_evidence(args.rescue_diagnostics)
    functional = load_physical_rescue_functional_probe_evidence(args.functional_probes)
    report = create_physical_storage_discovery_template(profile, assessment, diagnostics, functional)
    digest = write_physical_storage_discovery_template(report, args.out)
    print(report.canonical_json(), end="")
    print(f"template sha256={digest}")
    print("filesystem/encryption/free-space observations: unknown")
    print("target selected: false")
    print("write authorized: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
