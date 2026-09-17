#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
import shutil

from kaliphonestudio.device_tree_build import (
    create_device_tree_build_plan,
    execute_device_tree_build,
    write_evidence,
)
from kaliphonestudio.kernel_authority import load_and_verify_kernel_authority
from kaliphonestudio.kernel_contract import create_kernel_build_plan
from kaliphonestudio.kernel_toolchain import load_kernel_toolchain_lock
from kaliphonestudio.profiles import get_profile


def _export_artifacts(build_root: Path, plan, dtbo_image: Path, destination: Path) -> None:
    if destination.exists():
        raise ValueError(f"refusing to overwrite artifact export directory: {destination}")
    destination.mkdir(parents=True)
    shutil.copyfile(build_root.joinpath(*PurePosixPath(plan.dtb_output).parts), destination / "dtb.bin")
    raw_dir = destination / "raw-dtbo"
    raw_dir.mkdir()
    for index, relative in enumerate(plan.dtbo_outputs):
        source = build_root.joinpath(*PurePosixPath(relative).parts)
        shutil.copyfile(source, raw_dir / f"{index:03d}.dtbo")
    target = destination / "dtbo.img"
    if dtbo_image.resolve() != target.resolve():
        shutil.copyfile(dtbo_image, target)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build profile-selected DTB/DTBO artifacts from an exact reviewed kernel build root"
    )
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--devices-root", type=Path, default=Path("devices"))
    parser.add_argument("--toolchain-lock", type=Path, required=True)
    parser.add_argument("--format-lock", type=Path, required=True)
    parser.add_argument("--kernel-authority", type=Path, required=True)
    parser.add_argument("--kernel-authority-evidence-dir", type=Path, required=True)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--toolchain-root", type=Path, required=True)
    parser.add_argument("--build-root", type=Path, required=True)
    parser.add_argument("--dtbo-image", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--plan-out", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    profile = get_profile(args.devices_root, args.profile_id)
    kernel_plan = create_kernel_build_plan(profile)
    lock = load_kernel_toolchain_lock(args.toolchain_lock)
    checked = args.kernel_authority_evidence_dir
    authority = load_and_verify_kernel_authority(
        args.kernel_authority,
        kernel_plan,
        lock,
        checked / "kernel-reproducibility.json",
        checked / "kernel-reproducibility-binding.json",
        checked / "kernel-build-a.json",
        checked / "kernel-build-b.json",
    )
    plan = create_device_tree_build_plan(
        profile,
        kernel_plan,
        authority,
        format_lock=args.format_lock,
    )
    plan_digest = write_evidence(plan, args.plan_out)
    evidence = execute_device_tree_build(
        profile,
        kernel_plan,
        lock,
        authority,
        plan,
        checkout=args.checkout,
        toolchain_root=args.toolchain_root,
        output_root=args.build_root,
        dtbo_image=args.dtbo_image,
        jobs=args.jobs,
    )
    digest = write_evidence(evidence, args.out)
    if args.artifact_dir is not None:
        _export_artifacts(args.build_root, plan, args.dtbo_image, args.artifact_dir)
    print(plan.canonical_json(), end="")
    print(f"device-tree plan sha256={plan_digest}")
    print(evidence.canonical_json(), end="")
    print(f"device-tree build evidence sha256={digest}")
    print("hardware/Beta credit: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
