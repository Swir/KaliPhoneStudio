#!/usr/bin/env python3
"""Apply or verify a tiny fail-closed BusyBox Kconfig overlay.

BusyBox 1.38.0 does not reliably merge ``KCONFIG_ALLCONFIG`` into its older
``allnoconfig`` implementation.  This helper starts from a fully enumerated
``.config`` produced by BusyBox, replaces only explicitly locked symbols, and
can then verify that Kconfig dependency resolution preserved every requested
setting.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re


class MiniConfigError(ValueError):
    pass


_SETTING_RE = re.compile(r'^(CONFIG_[A-Z0-9_]+)=(y|n|-?[0-9]+|"(?:[^"\\]|\\.)*")$')
_UNSET_RE = re.compile(r'^# (CONFIG_[A-Z0-9_]+) is not set$')
_VALUE_RE = re.compile(r'^(CONFIG_[A-Z0-9_]+)=(.*)$')


def load_miniconfig(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise MiniConfigError(f"cannot read miniconfig: {exc}") from exc
    result: dict[str, str] = {}
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _SETTING_RE.fullmatch(line)
        if match is None:
            raise MiniConfigError(f"unsafe miniconfig syntax at line {number}: {raw!r}")
        symbol, value = match.groups()
        if symbol in result:
            raise MiniConfigError(f"duplicate locked symbol: {symbol}")
        result[symbol] = value
    if not result:
        raise MiniConfigError("miniconfig contains no locked symbols")
    return result


def _config_symbol(line: str) -> tuple[str, str] | None:
    match = _UNSET_RE.fullmatch(line)
    if match:
        return match.group(1), "n"
    match = _VALUE_RE.fullmatch(line)
    if match:
        return match.group(1), match.group(2)
    return None


def apply_overlay(config_path: Path, locked: dict[str, str]) -> int:
    try:
        lines = config_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise MiniConfigError(f"cannot read BusyBox .config: {exc}") from exc

    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        parsed = _config_symbol(line)
        if parsed is None or parsed[0] not in locked:
            output.append(line)
            continue
        symbol = parsed[0]
        if symbol in seen:
            raise MiniConfigError(f"BusyBox .config contains duplicate symbol: {symbol}")
        seen.add(symbol)
        value = locked[symbol]
        output.append(f"# {symbol} is not set" if value == "n" else f"{symbol}={value}")

    missing = sorted(set(locked) - seen)
    if missing:
        raise MiniConfigError("locked symbols missing from BusyBox .config: " + ", ".join(missing))

    temporary = config_path.with_name(config_path.name + ".kps-tmp")
    temporary.write_text("\n".join(output) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(config_path)
    return len(locked)


def verify_overlay(config_path: Path, locked: dict[str, str]) -> int:
    try:
        lines = config_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise MiniConfigError(f"cannot read BusyBox .config: {exc}") from exc
    actual: dict[str, str] = {}
    for line in lines:
        parsed = _config_symbol(line)
        if parsed is None or parsed[0] not in locked:
            continue
        symbol, value = parsed
        if symbol in actual:
            raise MiniConfigError(f"BusyBox .config contains duplicate symbol: {symbol}")
        actual[symbol] = value

    missing = sorted(set(locked) - set(actual))
    if missing:
        raise MiniConfigError("locked symbols missing after Kconfig resolution: " + ", ".join(missing))
    drift = [f"{key}: expected {locked[key]!r}, got {actual[key]!r}" for key in locked if actual[key] != locked[key]]
    if drift:
        raise MiniConfigError("Kconfig changed locked rescue settings: " + "; ".join(drift))
    return len(locked)


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply or verify KaliPhoneStudio's BusyBox rescue miniconfig")
    parser.add_argument("--miniconfig", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    locked = load_miniconfig(args.miniconfig)
    count = verify_overlay(args.config, locked) if args.check else apply_overlay(args.config, locked)
    print(f"verified {count} locked BusyBox rescue symbols" if args.check else f"applied {count} locked BusyBox rescue symbols")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
