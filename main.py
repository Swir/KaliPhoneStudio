"""KaliPhoneStudio host entrypoint.

The desktop/operator workspace remains offline by default. Physical-device
interaction is exposed only through explicit guarded subcommands. Stock
provenance and physical-stock binding are offline and never query a phone.
"""
from __future__ import annotations

import sys
from typing import Sequence

from kaliphonestudio.app import main as app_main
from kaliphonestudio.physical_fastboot_capture import main as physical_capture_main
from kaliphonestudio.stock_baseline_ingress import (
    bind_physical_stock_main,
    prepare_stock_provenance_main,
)


PHYSICAL_FASTBOOT_CAPTURE_COMMAND = "capture-fastboot-baseline"
PREPARE_STOCK_PROVENANCE_COMMAND = "prepare-stock-provenance"
BIND_PHYSICAL_STOCK_BASELINE_COMMAND = "bind-physical-stock-baseline"


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == PHYSICAL_FASTBOOT_CAPTURE_COMMAND:
        return physical_capture_main(args[1:])
    if args and args[0] == PREPARE_STOCK_PROVENANCE_COMMAND:
        return prepare_stock_provenance_main(args[1:])
    if args and args[0] == BIND_PHYSICAL_STOCK_BASELINE_COMMAND:
        return bind_physical_stock_main(args[1:])
    return app_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
