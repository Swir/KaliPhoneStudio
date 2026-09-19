"""Unified dispatcher for KaliPhoneStudio's offline operator evidence namespace."""
from __future__ import annotations

import sys
from typing import Sequence

from .operator_evidence_cli import EVIDENCE_COMMANDS, main as core_evidence_main
from .operator_host_evidence_cli import HOST_EVIDENCE_COMMANDS, main as host_evidence_main
from .operator_release_evidence_cli import LATE_EVIDENCE_COMMANDS, main as release_evidence_main
from .operator_strategy_evidence_cli import STRATEGY_EVIDENCE_COMMANDS, main as strategy_evidence_main
from .operator_trial_evidence_cli import TRIAL_EVIDENCE_COMMANDS, main as trial_evidence_main


_COMMAND_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("core", EVIDENCE_COMMANDS),
    ("host", HOST_EVIDENCE_COMMANDS),
    ("late", LATE_EVIDENCE_COMMANDS),
    ("strategy", STRATEGY_EVIDENCE_COMMANDS),
    ("trial", TRIAL_EVIDENCE_COMMANDS),
)
_GLOBAL_OPTIONS_BEFORE_COMMAND = frozenset({"--json"})


def _build_command_owners(
    groups: Sequence[tuple[str, Sequence[str]]] = _COMMAND_GROUPS,
) -> dict[str, str]:
    """Build one unambiguous command registry and reject ownership collisions."""
    owners: dict[str, str] = {}
    for owner, commands in groups:
        if not isinstance(owner, str) or not owner:
            raise RuntimeError("evidence command owner names must be non-empty strings")
        for command in commands:
            if not isinstance(command, str) or not command:
                raise RuntimeError("evidence command names must be non-empty strings")
            if command in owners:
                raise RuntimeError(f"duplicate evidence command ownership: {command}")
            owners[command] = owner
    return owners


COMMAND_OWNERS = _build_command_owners()
ALL_EVIDENCE_COMMANDS = tuple(COMMAND_OWNERS)


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
        return token if token in COMMAND_OWNERS else None
    return None


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help"}:
        _print_help()
        return 0
    command = _select_command(args)
    owner = COMMAND_OWNERS.get(command, "core")
    if owner == "host":
        return host_evidence_main(args)
    if owner == "trial":
        return trial_evidence_main(args)
    if owner == "strategy":
        return strategy_evidence_main(args)
    if owner == "late":
        return release_evidence_main(args)
    return core_evidence_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
