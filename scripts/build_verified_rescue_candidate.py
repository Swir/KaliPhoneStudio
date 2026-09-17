#!/usr/bin/env python3
"""Build an offline profile-compressed rescue candidate from two verified ARM64 builds."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kaliphonestudio.profiles import get_profile  # noqa: E402
from kaliphonestudio.rescue_candidate import (  # noqa: E402
    build_verified_rescue_candidate,
    write_rescue_candidate_evidence,
)
from kaliphonestudio.rescue_payload_repro import (  # noqa: E402
    verify_reproducible_payload_pair,
    write_repro_evidence,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Verify two independent source/material-locked static ARM64 BusyBox builds, "
            "stage the reviewed offline rescue userspace, add one deterministic provenance "
            "probe id, and build the device profile's deterministic rescue ramdisk. "
            "This never connects to or boots a phone."
        )
    )
    result.add_argument("--profile-id", required=True)
    result.add_argument("--devices-root", type=Path, default=ROOT / "devices")
    result.add_argument("--lock", type=Path, default=ROOT / "tools" / "rescue-payload-lock.json")
    result.add_argument("--source-archive", type=Path, required=True)
    result.add_argument("--busybox-a", type=Path, required=True)
    result.add_argument("--busybox-b", type=Path, required=True)
    result.add_argument("--applets-a", type=Path, required=True)
    result.add_argument("--applets-b", type=Path, required=True)
    result.add_argument("--compiler-id", required=True)
    result.add_argument("--target-machine", default="aarch64-linux-gnu")
    result.add_argument("--out", type=Path, required=True)
    result.add_argument("--repro-evidence", type=Path, required=True)
    result.add_argument("--candidate-evidence", type=Path, required=True)
    return result


def _refuse_overwrite(paths: tuple[Path, ...]) -> None:
    seen: set[Path] = set()
    for path in paths:
        resolved = path.absolute()
        if resolved in seen:
            raise SystemExit(f"output paths must be distinct: {path}")
        seen.add(resolved)
        if path.exists() or path.is_symlink():
            raise SystemExit(f"refusing to overwrite existing output: {path}")


def main() -> int:
    args = parser().parse_args()
    _refuse_overwrite((args.out, args.repro_evidence, args.candidate_evidence))

    profile = get_profile(args.devices_root, args.profile_id)
    repro = verify_reproducible_payload_pair(
        lock_manifest_path=args.lock,
        repository_root=ROOT,
        source_archive=args.source_archive,
        first_binary=args.busybox_a,
        second_binary=args.busybox_b,
        first_applet_list=args.applets_a,
        second_applet_list=args.applets_b,
        compiler_id=args.compiler_id,
        target_machine=args.target_machine,
    )
    candidate = build_verified_rescue_candidate(
        profile=profile,
        repro=repro,
        lock_manifest_path=args.lock,
        repository_root=ROOT,
        busybox=args.busybox_a,
        applet_list=args.applets_a,
        destination=args.out,
    )
    repro_digest = write_repro_evidence(repro, args.repro_evidence)
    candidate_digest = write_rescue_candidate_evidence(candidate, args.candidate_evidence)

    print(f"profile_id={candidate.profile_id}")
    print(f"payload_id={repro.payload_id}")
    print(f"busybox_sha256={repro.busybox_sha256}")
    print(f"ramdisk_compression={candidate.ramdisk_compression}")
    print(f"ramdisk_sha256={candidate.ramdisk_sha256}")
    print(f"ramdisk_size={candidate.ramdisk_size}")
    print(f"rescue_probe_id={candidate.rescue_probe_id}")
    print(f"rescue_probe_file_sha256={candidate.rescue_probe_file_sha256}")
    print(f"repro_evidence_sha256={repro_digest}")
    print(f"candidate_evidence_sha256={candidate_digest}")
    print("hardware_verified=false")
    print("beta_gate_credit=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
