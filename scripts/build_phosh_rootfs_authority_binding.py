#!/usr/bin/env python3
"""Build host-only Phosh/rootfs authority binding evidence."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from kaliphonestudio.phosh_rootfs_binding import (
    PhoshRootfsBindingError,
    build_phosh_rootfs_authority_binding_from_paths,
    write_phosh_rootfs_authority_binding,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Bind an exact Phosh package manifest to one reviewed reproducible rootfs authority. "
            "This command is host-only and never grants hardware or Beta credit."
        )
    )
    parser.add_argument("--source-lock", type=Path, default=Path("tools/phosh-source-lock.json"))
    parser.add_argument("--rootfs-authority", type=Path, required=True)
    parser.add_argument("--package-manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        evidence = build_phosh_rootfs_authority_binding_from_paths(
            args.source_lock,
            args.rootfs_authority,
            args.package_manifest,
        )
        digest = write_phosh_rootfs_authority_binding(evidence, args.out)
    except PhoshRootfsBindingError as exc:
        print(f"Phosh rootfs binding error: {exc}", file=sys.stderr)
        return 2
    print(f"Wrote host-only Phosh/rootfs authority binding: {args.out}")
    print(f"Evidence SHA-256: {digest}")
    print("Hardware/Beta credit: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
