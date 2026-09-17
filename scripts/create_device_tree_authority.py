#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.device_tree_authority import (
    build_reviewed_device_tree_authority,
    plan_from_json,
    reproducibility_from_json,
    run_from_json,
    write_device_tree_authority,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a reviewed non-hardware DTB/DTBO reproducibility authority record"
    )
    parser.add_argument("--authority-name", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--artifact-id", type=int, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--build-a", type=Path, required=True)
    parser.add_argument("--build-b", type=Path, required=True)
    parser.add_argument("--reproducibility", type=Path, required=True)
    parser.add_argument("--reviewed", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    authority = build_reviewed_device_tree_authority(
        authority_name=args.authority_name,
        authority_run_id=args.run_id,
        authority_commit=args.commit,
        authority_artifact_id=args.artifact_id,
        plan=plan_from_json(args.plan),
        run_a=run_from_json(args.build_a),
        run_b=run_from_json(args.build_b),
        reproducibility=reproducibility_from_json(args.reproducibility),
        reviewed=args.reviewed,
    )
    digest = write_device_tree_authority(authority, args.out)
    print(authority.canonical_json(), end="")
    print(f"device-tree authority sha256={digest}")
    print("hardware/Beta credit: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
