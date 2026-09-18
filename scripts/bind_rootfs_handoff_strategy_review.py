#!/usr/bin/env python3
"""Bind an exact rootfs strategy review to an exact physical evidence chain."""
from __future__ import annotations

from pathlib import Path
import sys
from typing import Sequence

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from kaliphonestudio.operator_strategy_evidence_cli import main as strategy_evidence_main


COMMAND = "bind-rootfs-handoff-strategy-review"


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    return strategy_evidence_main([COMMAND, *args])


if __name__ == "__main__":
    raise SystemExit(main())
