"""KaliPhoneStudio host entrypoint.

The desktop/operator workspace remains offline by default. The explicit
``capture-fastboot-baseline`` subcommand is the only top-level physical capture
path exposed here and delegates to the guarded read-only capture module.
"""
from __future__ import annotations

import sys
from typing import Sequence

from kaliphonestudio.app import main as app_main
from kaliphonestudio.physical_fastboot_capture import main as physical_capture_main


PHYSICAL_FASTBOOT_CAPTURE_COMMAND = "capture-fastboot-baseline"


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == PHYSICAL_FASTBOOT_CAPTURE_COMMAND:
        return physical_capture_main(args[1:])
    return app_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
