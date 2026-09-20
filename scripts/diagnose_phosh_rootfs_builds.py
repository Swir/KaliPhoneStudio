#!/usr/bin/env python3
"""Create a bounded, non-promoting diagnostic report for Phosh A/B rootfs drift."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kaliphonestudio.phosh_repro_diagnostics import (  # noqa: E402
    PhoshReproDiagnosticError,
    diagnose_phosh_rootfs_builds,
    write_phosh_rootfs_reproducibility_diagnostic,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Explain differences between two independently built canonical Phosh rootfs "
            "artifacts using exact per-member manifests. This is diagnostic-only."
        )
    )
    result.add_argument("--build-a", type=Path, required=True)
    result.add_argument("--build-b", type=Path, required=True)
    result.add_argument("--members-a", type=Path, required=True)
    result.add_argument("--members-b", type=Path, required=True)
    result.add_argument("--out", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    diagnostic = diagnose_phosh_rootfs_builds(
        args.build_a, args.build_b, args.members_a, args.members_b
    )
    digest = write_phosh_rootfs_reproducibility_diagnostic(diagnostic, args.out)
    print(f"artifact_bytes_identical={str(diagnostic.artifact_bytes_identical).lower()}")
    print(f"package_manifest_identical={str(diagnostic.package_manifest_identical).lower()}")
    print(f"member_path_set_identical={str(diagnostic.member_path_set_identical).lower()}")
    print(f"member_order_identical={str(diagnostic.member_order_identical).lower()}")
    print(f"member_records_identical={str(diagnostic.member_records_identical).lower()}")
    print(f"ordering_only_difference={str(diagnostic.ordering_only_difference).lower()}")
    print(
        "archive_encoding_only_difference="
        f"{str(diagnostic.archive_encoding_only_difference).lower()}"
    )
    print(f"differing_member_count={diagnostic.differing_member_count}")
    print(f"reported_difference_count={diagnostic.reported_difference_count}")
    for index, difference in enumerate(diagnostic.differences[:20]):
        safe_path = json.dumps(difference.path, ensure_ascii=True, separators=(",", ":"))
        fields = ",".join(difference.fields)
        print(f"difference[{index}]={safe_path}\t{difference.kind}\t{fields}")
    if diagnostic.differences_truncated or diagnostic.reported_difference_count > 20:
        print("difference_log_truncated=true")
    print(f"diagnostic_sha256={digest}")
    print("reproducibility_authority=false")
    print("hardware_verified=false")
    print("beta_gate_credit=false")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PhoshReproDiagnosticError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
