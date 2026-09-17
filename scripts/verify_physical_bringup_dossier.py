#!/usr/bin/env python3
"""Reverify an exact-file physical bring-up dossier after transfer/archive."""
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.physical_bringup_dossier import (
    load_physical_bringup_dossier_evidence,
)
from kaliphonestudio.physical_bringup_dossier_verify import (
    PhysicalBringupDossierError,
    verify_physical_bringup_dossier_files,
    write_physical_bringup_dossier_verification_evidence,
)


def _role_file(value: str) -> tuple[str, Path]:
    role, sep, raw_path = value.partition("=")
    if not sep or not role or not raw_path:
        raise argparse.ArgumentTypeError("expected ROLE=PATH")
    if any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789_" for ch in role):
        raise argparse.ArgumentTypeError("ROLE must use lowercase letters, digits or underscore")
    return role, Path(raw_path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Reverify every exact file named by a physical bring-up dossier without "
            "phone I/O, target selection or write authorization."
        )
    )
    parser.add_argument("--dossier", type=Path, required=True)
    parser.add_argument(
        "--file",
        action="append",
        type=_role_file,
        required=True,
        metavar="ROLE=PATH",
        help="repeat exactly once for every role recorded in the dossier",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    role_files: dict[str, Path] = {}
    for role, path in args.file:
        if role in role_files:
            parser.error(f"duplicate --file role: {role}")
        role_files[role] = path

    try:
        dossier = load_physical_bringup_dossier_evidence(args.dossier)
        evidence = verify_physical_bringup_dossier_files(
            dossier,
            dossier_file=args.dossier,
            role_files=role_files,
        )
        digest = write_physical_bringup_dossier_verification_evidence(evidence, args.out)
    except (PhysicalBringupDossierError, ValueError, OSError) as exc:
        parser.error(str(exc))

    print(evidence.canonical_json(), end="")
    print(f"dossier reverification evidence sha256={digest}")
    print(f"verified roles={evidence.verified_role_count}")
    print(f"verified bytes={evidence.verified_byte_count}")
    print("target selected: false")
    print("write authorized: false")
    print("hardware/Beta credit: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
