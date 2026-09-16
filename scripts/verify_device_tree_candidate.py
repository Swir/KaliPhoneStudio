#!/usr/bin/env python3
"""Verify DTB/DTBO structure and bind exact artifacts to an approved boot plan."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from kaliphonestudio.boot_builder import BootBuildPlan, BuildInput
from kaliphonestudio.device_tree import (
    DeviceTreeError,
    bind_device_tree_candidate_evidence,
    write_device_tree_candidate_evidence,
)
from kaliphonestudio.profiles import ProfileError, get_profile


def load_boot_plan(path: Path) -> BootBuildPlan:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeviceTreeError(f"cannot load boot build plan: {exc}") from exc
    if not isinstance(raw, dict):
        raise DeviceTreeError("boot build plan root must be an object")
    inputs_raw = raw.get("inputs")
    if not isinstance(inputs_raw, list) or not inputs_raw:
        raise DeviceTreeError("boot build plan inputs must be a non-empty list")
    try:
        inputs = tuple(
            BuildInput(
                name=item["name"],
                path=item["path"],
                size=item["size"],
                sha256=item["sha256"],
            )
            for item in inputs_raw
        )
        cmdline = raw.get("kernel_cmdline", [])
        if not isinstance(cmdline, list) or any(not isinstance(item, str) for item in cmdline):
            raise DeviceTreeError("boot build plan kernel_cmdline must be a list of strings")
        return BootBuildPlan(
            schema_version=raw["schema_version"],
            profile_id=raw["profile_id"],
            stock_boot_sha256=raw["stock_boot_sha256"],
            stock_ota_sha256=raw["stock_ota_sha256"],
            header_version=raw["header_version"],
            page_size=raw["page_size"],
            ramdisk_compression=raw["ramdisk_compression"],
            kernel_cmdline=tuple(cmdline),
            inputs=inputs,
        )
    except (KeyError, TypeError) as exc:
        raise DeviceTreeError(f"boot build plan is missing required typed fields: {exc}") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fail-closed offline DTB/DTBO verification for a KaliPhoneStudio boot plan."
    )
    parser.add_argument("--devices-root", type=Path, default=Path("devices"))
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--boot-plan", type=Path, required=True)
    parser.add_argument("--dtb", type=Path)
    parser.add_argument("--dtbo", type=Path)
    parser.add_argument(
        "--format-lock",
        type=Path,
        default=Path("tools/device-tree-format-locks.json"),
    )
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        profile = get_profile(args.devices_root, args.profile_id)
        plan = load_boot_plan(args.boot_plan)
        evidence = bind_device_tree_candidate_evidence(
            profile,
            plan,
            format_lock=args.format_lock,
            dtb=args.dtb,
            dtbo=args.dtbo,
        )
        digest = write_device_tree_candidate_evidence(evidence, args.out)
    except (DeviceTreeError, ProfileError) as exc:
        print(f"device-tree verification failed: {exc}", file=sys.stderr)
        return 2
    print(evidence.canonical_json(), end="")
    print(f"device-tree evidence sha256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
