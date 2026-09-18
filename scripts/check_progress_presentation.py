#!/usr/bin/env python3
"""Fail-closed policy checks for the maintained SWIR progress presentation.

This is deliberately separate from SVG generation: the generator proves that
committed SVG bytes match BUILD_STATUS.json, while this checker proves that the
maintained README/ROADMAP cannot silently re-introduce retired text-art meters,
duplicate live progress graphics, or embed the N/A template as project data.

Fenced code blocks are excluded from legacy-meter detection so preserved command
examples and directory trees remain untouched.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README_PATH = ROOT / "README.md"
ROADMAP_PATH = ROOT / "ROADMAP.md"
TEMPLATE_PATH = ROOT / "assets/readme/progress-template.svg"

CARD_EMBED = 'src="assets/readme/progress-card.svg"'
MINI_EMBED = 'src="assets/readme/progress-mini.svg"'
TEMPLATE_EMBED = 'src="assets/readme/progress-template.svg"'

# Strictly meter-like character runs. Markdown checkboxes and directory-tree
# glyphs are intentionally outside these character classes.
_UNICODE_METER = re.compile(r"[█▓▒░▰▱■□]{6,}")
_BRACKETED_METER = re.compile(r"\[[#=+\-█▓▒░▰▱■□]{6,}\]")
_BARE_ASCII_METER = re.compile(
    r"(?i)\b(?:progress|complete|completion|roadmap|status)\b"
    r"[^\n]{0,48}[#=+\-]{8,}[^\n]{0,24}\d{1,3}(?:\.\d+)?\s*%"
)


class ProgressPresentationError(ValueError):
    pass


def _outside_fenced_code(text: str):
    """Yield ``(line_number, line)`` only outside Markdown fenced code blocks."""
    fence: str | None = None
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        marker = "```" if stripped.startswith("```") else "~~~" if stripped.startswith("~~~") else None
        if marker is not None:
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            continue
        if fence is None:
            yield line_number, line


def find_legacy_progress_meters(text: str) -> list[tuple[int, str]]:
    """Return suspicious live text-art meter lines outside fenced code blocks."""
    matches: list[tuple[int, str]] = []
    for line_number, line in _outside_fenced_code(text):
        if (
            _UNICODE_METER.search(line)
            or _BRACKETED_METER.search(line)
            or _BARE_ASCII_METER.search(line)
        ):
            matches.append((line_number, line.strip()))
    return matches


def _require_count(text: str, needle: str, expected: int, label: str) -> None:
    actual = text.count(needle)
    if actual != expected:
        raise ProgressPresentationError(
            f"{label}: expected {expected} occurrence(s) of {needle!r}, found {actual}"
        )


def verify_progress_presentation(
    readme_path: Path = README_PATH,
    roadmap_path: Path = ROADMAP_PATH,
    template_path: Path = TEMPLATE_PATH,
) -> None:
    try:
        readme = Path(readme_path).read_text(encoding="utf-8")
        roadmap = Path(roadmap_path).read_text(encoding="utf-8")
        template = Path(template_path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ProgressPresentationError(f"cannot read maintained progress presentation: {exc}") from exc

    # One suitable live graphic per maintained scope. The card is README-only;
    # the compact mini is ROADMAP-only; the reusable template is never live data.
    _require_count(readme, CARD_EMBED, 1, "README")
    _require_count(readme, MINI_EMBED, 0, "README")
    _require_count(readme, TEMPLATE_EMBED, 0, "README")
    _require_count(roadmap, CARD_EMBED, 0, "ROADMAP")
    _require_count(roadmap, MINI_EMBED, 1, "ROADMAP")
    _require_count(roadmap, TEMPLATE_EMBED, 0, "ROADMAP")

    for label, text in (("README", readme), ("ROADMAP", roadmap)):
        meters = find_legacy_progress_meters(text)
        if meters:
            line_number, line = meters[0]
            raise ProgressPresentationError(
                f"{label} contains retired text-art progress meter at line {line_number}: {line!r}"
            )

    if "TEMPLATE / NOT PROJECT DATA" not in template:
        raise ProgressPresentationError("progress template lost its TEMPLATE / NOT PROJECT DATA label")
    if ">N/A<" not in template:
        raise ProgressPresentationError("progress template must render N/A, never live project data")
    if "KaliPhoneStudio" in template:
        raise ProgressPresentationError("progress template must remain project-neutral")


def main() -> int:
    try:
        verify_progress_presentation()
    except ProgressPresentationError as exc:
        print(f"progress presentation policy error: {exc}")
        return 2
    print("progress presentation policy verified: SVG-only live dashboards; no legacy meters")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
