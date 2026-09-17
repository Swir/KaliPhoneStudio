#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from kaliphonestudio.device_tree_build import (
    DeviceTreeBuildPlan,
    DeviceTreeBuildRunEvidence,
    RawOverlayEvidence,
    verify_device_tree_reproducibility,
    write_evidence,
)


def _load_plan(path: Path) -> DeviceTreeBuildPlan:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("device-tree plan must be a JSON object")
    if isinstance(raw.get("dtbo_outputs"), list):
        raw["dtbo_outputs"] = tuple(raw["dtbo_outputs"])
    return DeviceTreeBuildPlan(**raw)


def _load_run(path: Path) -> DeviceTreeBuildRunEvidence:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("device-tree build evidence must be a JSON object")
    overlays = raw.get("raw_dtbo")
    if not isinstance(overlays, list):
        raise ValueError("device-tree build evidence raw_dtbo must be a list")
    raw["raw_dtbo"] = tuple(RawOverlayEvidence(**item) for item in overlays)
    return DeviceTreeBuildRunEvidence(**raw)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify strict A/B DTB/DTBO byte reproducibility")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--build-evidence-a", type=Path, required=True)
    parser.add_argument("--build-evidence-b", type=Path, required=True)
    parser.add_argument("--build-root-a", type=Path, required=True)
    parser.add_argument("--build-root-b", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    plan = _load_plan(args.plan)
    run_a = _load_run(args.build_evidence_a)
    run_b = _load_run(args.build_evidence_b)
    evidence = verify_device_tree_reproducibility(
        plan,
        run_a,
        run_b,
        build_root_a=args.build_root_a,
        build_root_b=args.build_root_b,
    )
    digest = write_evidence(evidence, args.out)
    print(evidence.canonical_json(), end="")
    print(f"device-tree reproducibility evidence sha256={digest}")
    print("hardware/Beta credit: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
