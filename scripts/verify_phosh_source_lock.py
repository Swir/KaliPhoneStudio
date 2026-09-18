#!/usr/bin/env python3
"""Verify the immutable NetHunter Pro Phosh source snapshot against its lock."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from kaliphonestudio.phosh import load_phosh_source_lock, verify_phosh_source_tree


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, default=Path("tools/phosh-source-lock.json"))
    parser.add_argument("--source-root", type=Path, required=True)
    args = parser.parse_args()

    lock = load_phosh_source_lock(args.lock)
    evidence = verify_phosh_source_tree(lock, args.source_root)
    print(json.dumps({
        "schema_version": evidence.schema_version,
        "source_lock_sha256": evidence.source_lock_sha256,
        "upstream_commit": evidence.upstream_commit,
        "architecture": evidence.architecture,
        "environment": evidence.environment,
        "verified_files": [list(item) for item in evidence.verified_files],
        "required_packages": list(evidence.required_packages),
        "source_verified": evidence.source_verified,
        "hardware_verified": evidence.hardware_verified,
        "beta_gate_credit": evidence.beta_gate_credit,
    }, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
