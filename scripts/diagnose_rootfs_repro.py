from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.rootfs_repro_diagnostics import (
    write_rootfs_repro_diagnostics,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate bounded non-release diagnostics for two KaliPhoneStudio "
            "rootfs tar.xz builds. Strict byte-for-byte acceptance remains "
            "unchanged."
        )
    )
    parser.add_argument("--archive-a", required=True, type=Path)
    parser.add_argument("--archive-b", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--max-differences", type=int, default=200)
    args = parser.parse_args()

    report = write_rootfs_repro_diagnostics(
        args.archive_a,
        args.archive_b,
        args.out,
        max_differences=args.max_differences,
    )
    summary = report["summary"]
    print(
        "rootfs diagnostics: "
        f"strict_reproducible={str(report['strict_reproducible']).lower()} "
        f"semantic_equal={str(report['semantic_equal']).lower()} "
        f"differences={summary['difference_count_total']} "
        f"out={args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
