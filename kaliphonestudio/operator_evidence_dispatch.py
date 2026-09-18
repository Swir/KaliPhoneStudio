"""Dispatch the single ``KaliPhoneStudio evidence`` surface.

The core evidence workspace and the late bring-up/dossier audit extension are
kept in separate modules to keep each safety boundary reviewable.  This module
provides one user-facing command group for source and frozen Windows builds.
"""
from __future__ import annotations

import sys
from typing import Sequence

from .operator_bringup_evidence_cli import BRINGUP_EVIDENCE_COMMANDS, main as bringup_main
from .operator_evidence_cli import EVIDENCE_COMMANDS, main as core_main


ALL_EVIDENCE_COMMANDS = EVIDENCE_COMMANDS + BRINGUP_EVIDENCE_COMMANDS


def _print_help() -> None:
    print("usage: KaliPhoneStudio evidence <command> [options]")
    print()
    print("Offline exact-file evidence workspace. These commands do not connect to a phone,")
    print("do not run adb/fastboot, do not select storage targets and grant no hardware/Beta credit.")
    print()
    print("commands:")
    for command in ALL_EVIDENCE_COMMANDS:
        print(f"  {command}")
    print()
    print("Use 'KaliPhoneStudio evidence <command> --help' for stage-specific arguments.")


def main(argv: Sequence[str] | None = None) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]
    if not args or args[0] in {"-h", "--help"}:
        _print_help()
        return 0
    if args[0] in BRINGUP_EVIDENCE_COMMANDS:
        return bringup_main(args)
    return core_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
