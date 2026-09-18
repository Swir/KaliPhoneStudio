"""Unified dispatcher for KaliPhoneStudio's offline operator evidence namespace."""
from __future__ import annotations

import sys
from typing import Sequence

from .operator_evidence_cli import EVIDENCE_COMMANDS, main as core_evidence_main
from .operator_release_evidence_cli import LATE_EVIDENCE_COMMANDS, main as release_evidence_main


ALL_EVIDENCE_COMMANDS = EVIDENCE_COMMANDS + LATE_EVIDENCE_COMMANDS


def _print_help() -> None:
    print("KaliPhoneStudio evidence — offline exact-file evidence workspace")
    print()
    print("These commands do not connect to a phone, do not run adb/fastboot, do not select storage targets,")
    print("do not authorize persistent writes and grant no hardware/Beta credit.")
    print()
    print("Commands:")
    for command in ALL_EVIDENCE_COMMANDS:
        print(f"  {command}")
    print()
    print("Run 'KaliPhoneStudio evidence <command> --help' for command-specific arguments.")


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help"}:
        _print_help()
        return 0
    if args[0] in LATE_EVIDENCE_COMMANDS:
        return release_evidence_main(args)
    return core_evidence_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
