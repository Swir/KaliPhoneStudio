"""Unified dispatcher for KaliPhoneStudio's offline operator evidence namespace."""
from __future__ import annotations

import sys
from typing import Callable, Sequence

from .operator_evidence_cli import EVIDENCE_COMMANDS, main as core_evidence_main
from .operator_host_evidence_cli import HOST_EVIDENCE_COMMANDS, main as host_evidence_main
from .operator_release_evidence_cli import LATE_EVIDENCE_COMMANDS, main as release_evidence_main
from .operator_strategy_evidence_cli import STRATEGY_EVIDENCE_COMMANDS, main as strategy_evidence_main
from .operator_trial_evidence_cli import TRIAL_EVIDENCE_COMMANDS, main as trial_evidence_main


EvidenceHandler = Callable[[Sequence[str] | None], int]
_COMMAND_GROUPS: tuple[tuple[tuple[str, ...], EvidenceHandler], ...] = (
    (EVIDENCE_COMMANDS, core_evidence_main),
    (HOST_EVIDENCE_COMMANDS, host_evidence_main),
    (LATE_EVIDENCE_COMMANDS, release_evidence_main),
    (STRATEGY_EVIDENCE_COMMANDS, strategy_evidence_main),
    (TRIAL_EVIDENCE_COMMANDS, trial_evidence_main),
)
_GLOBAL_OPTIONS_BEFORE_COMMAND = frozenset({"--json"})


def _build_command_handlers(
    groups: Sequence[tuple[Sequence[str], EvidenceHandler]] = _COMMAND_GROUPS,
) -> dict[str, EvidenceHandler]:
    """Build one unambiguous command registry and reject ownership collisions."""
    handlers: dict[str, EvidenceHandler] = {}
    for commands, handler in groups:
        for command in commands:
            if not isinstance(command, str) or not command:
                raise RuntimeError("evidence command names must be non-empty strings")
            if command in handlers:
                raise RuntimeError(f"duplicate evidence command ownership: {command}")
            handlers[command] = handler
    return handlers


COMMAND_HANDLERS = _build_command_handlers()
ALL_EVIDENCE_COMMANDS = tuple(COMMAND_HANDLERS)


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
        return token if token in COMMAND_HANDLERS else None
    return None


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help"}:
        _print_help()
        return 0
    command = _select_command(args)
    handler = COMMAND_HANDLERS.get(command, core_evidence_main)
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
