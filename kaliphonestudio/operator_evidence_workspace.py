"""Unified dispatcher for KaliPhoneStudio's offline operator evidence namespace."""
from __future__ import annotations

import sys
from typing import Sequence

from .operator_evidence_cli import EVIDENCE_COMMANDS, main as core_evidence_main
from .operator_host_evidence_cli import HOST_EVIDENCE_COMMANDS, main as host_evidence_main
from .operator_release_evidence_cli import LATE_EVIDENCE_COMMANDS, main as release_evidence_main
from .operator_strategy_evidence_cli import STRATEGY_EVIDENCE_COMMANDS, main as strategy_evidence_main
from .operator_trial_evidence_cli import TRIAL_EVIDENCE_COMMANDS, main as trial_evidence_main


ALL_EVIDENCE_COMMANDS = (
    EVIDENCE_COMMANDS
    + HOST_EVIDENCE_COMMANDS
    + LATE_EVIDENCE_COMMANDS
    + STRATEGY_EVIDENCE_COMMANDS
    + TRIAL_EVIDENCE_COMMANDS
)

_GLOBAL_OPTIONS_BEFORE_COMMAND = frozenset({"--json"})


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


def _select_command(args: Sequence[str]) -> str | None:
    """Select only the first positional command after known flag-only globals.

    Specialized evidence parsers accept ``--json`` before their subcommand. The
    dispatcher must support that form without scanning arbitrary later tokens:
    an unknown option may consume a value that happens to equal a valid command,
    and routing on that value would hand arguments to the wrong parser. Unknown
    leading options and unknown first positional tokens therefore fail closed to
    the core parser, which owns the final argparse error.
    """
    for token in args:
        if token in _GLOBAL_OPTIONS_BEFORE_COMMAND:
            continue
        if token.startswith("-"):
            return None
        return token if token in ALL_EVIDENCE_COMMANDS else None
    return None


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help"}:
        _print_help()
        return 0
    command = _select_command(args)
    if command in HOST_EVIDENCE_COMMANDS:
        return host_evidence_main(args)
    if command in TRIAL_EVIDENCE_COMMANDS:
        return trial_evidence_main(args)
    if command in STRATEGY_EVIDENCE_COMMANDS:
        return strategy_evidence_main(args)
    if command in LATE_EVIDENCE_COMMANDS:
        return release_evidence_main(args)
    return core_evidence_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
