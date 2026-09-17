#!/usr/bin/env python3
"""Generate deterministic SWIR Progress SVG PRO assets from BUILD_STATUS.json.

The project percentage is an authoritative reviewed roadmap ledger value in
``BUILD_STATUS.json``. It is intentionally *not* recomputed from raw roadmap
checkboxes because KaliPhoneStudio's milestones are not documented as equally
weighted. Geometry is derived directly from that numeric field. Beta readiness
is rendered separately and never inferred from the project percentage.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from html import escape
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

STANDARD = "SWIR-PROGRESS-SVG-PRO:v1"
ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / "BUILD_STATUS.json"
CARD_PATH = ROOT / "assets/readme/progress-card.svg"
MINI_PATH = ROOT / "assets/readme/progress-mini.svg"
TEMPLATE_PATH = ROOT / "assets/readme/progress-template.svg"
README_PATH = ROOT / "README.md"
ROADMAP_PATH = ROOT / "ROADMAP.md"

CARD_TRACK_X = 50.0
CARD_TRACK_WIDTH = 1100.0
MINI_TRACK_X = 170.0
MINI_TRACK_WIDTH = 700.0

AUTHORITY_KEYS = (
    "rootfs_reproducibility_authority_state",
    "kernel_reproducibility_authority_state",
    "device_tree_reproducibility_authority_state",
)


class ProgressSvgError(ValueError):
    pass


@dataclass(frozen=True)
class ProgressModel:
    project: str
    scope: str
    version: str
    percentage: float | None
    status: str
    beta_status: str
    authority_completed: int
    authority_total: int

    @property
    def percent_label(self) -> str:
        return "N/A" if self.percentage is None else f"{self.percentage:.1f}%"

    @property
    def authority_label(self) -> str:
        return f"Host authorities: {self.authority_completed}/{self.authority_total} reviewed"


def _finite_percent(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProgressSvgError("project_progress_percent must be numeric or null")
    result = float(value)
    if not math.isfinite(result) or result < 0.0 or result > 100.0:
        raise ProgressSvgError("project_progress_percent must be finite and in [0, 100]")
    return result


def build_model(status: dict[str, object]) -> ProgressModel:
    if not isinstance(status, dict):
        raise ProgressSvgError("BUILD_STATUS.json must contain an object")
    version = status.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ProgressSvgError("BUILD_STATUS.json version is missing")
    beta_status = status.get("beta_gate")
    if not isinstance(beta_status, str) or not beta_status.strip():
        raise ProgressSvgError("BUILD_STATUS.json beta_gate is missing")
    hardware_verified = status.get("hardware_verified")
    if hardware_verified is not False:
        raise ProgressSvgError("progress presentation expects current hardware_verified=false state")

    authority_states = [status.get(key) for key in AUTHORITY_KEYS]
    completed = sum(value == "passed-reviewed" for value in authority_states)
    if any(not isinstance(value, str) for value in authority_states):
        raise ProgressSvgError("reviewed authority state is missing")

    percentage = _finite_percent(status.get("project_progress_percent"))
    status_label = "BLOCKED" if beta_status == "BLOCKED" else "IN PROGRESS"
    return ProgressModel(
        project="KaliPhoneStudio",
        scope="Current project roadmap",
        version=version,
        percentage=percentage,
        status=status_label,
        beta_status=beta_status,
        authority_completed=completed,
        authority_total=len(AUTHORITY_KEYS),
    )


def load_model(path: Path = STATUS_PATH) -> ProgressModel:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProgressSvgError(f"cannot read authoritative progress source: {exc}") from exc
    return build_model(raw)


def fill_width(track_width: float, percentage: float | None) -> float | None:
    if percentage is None:
        return None
    width = track_width * (percentage / 100.0)
    if not math.isfinite(width):
        raise ProgressSvgError("computed progress geometry is not finite")
    return min(track_width, max(0.0, width))


def _progress_fill(x: float, y: float, height: float, track_width: float, percentage: float | None) -> str:
    width = fill_width(track_width, percentage)
    if width is None or width <= 0.0:
        return ""
    return (
        f'<rect x="{x:.0f}" y="{y:.0f}" width="{width:.3f}" height="{height:.0f}" '
        'rx="7" fill="url(#progressGradient)" filter="url(#softGlow)" clip-path="url(#trackClip)"/>'
    )


def render_card(model: ProgressModel) -> str:
    fill = _progress_fill(CARD_TRACK_X, 112, 18, CARD_TRACK_WIDTH, model.percentage)
    description = (
        f"{model.project}; {model.scope}; progress {model.percent_label}; status {model.status}; "
        f"{model.authority_label}; Beta readiness {model.beta_status}."
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="180" viewBox="0 0 1200 180" role="img" aria-labelledby="title desc">
  <title id="title">{escape(model.project)} roadmap progress — {escape(model.percent_label)}</title>
  <desc id="desc">{escape(description)}</desc>
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#02050A"/><stop offset="1" stop-color="#07111C"/></linearGradient>
    <linearGradient id="progressGradient" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#0088FF"/><stop offset="1" stop-color="#62E5FF"/></linearGradient>
    <pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse"><path d="M32 0H0V32" fill="none" stroke="#62E5FF" stroke-opacity="0.045" stroke-width="1"/></pattern>
    <filter id="softGlow" x="-20%" y="-100%" width="140%" height="300%"><feGaussianBlur stdDeviation="3" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <clipPath id="trackClip"><rect x="50" y="112" width="1100" height="18" rx="7"/></clipPath>
  </defs>
  <rect x="1" y="1" width="1198" height="178" rx="20" fill="url(#bg)" stroke="#62E5FF" stroke-opacity="0.24" stroke-width="2"/>
  <rect x="1" y="1" width="1198" height="178" rx="20" fill="url(#grid)"/>
  <text x="50" y="38" fill="#8DA8B8" font-family="Segoe UI,Arial,sans-serif" font-size="14" font-weight="700" letter-spacing="2">SWIR PROJECT • {escape(model.scope.upper())}</text>
  <text x="50" y="76" fill="#F4FAFF" font-family="Segoe UI,Arial,sans-serif" font-size="30" font-weight="700">{escape(model.project)}</text>
  <text x="1150" y="76" text-anchor="end" fill="#62E5FF" font-family="Segoe UI,Arial,sans-serif" font-size="30" font-weight="800">{escape(model.percent_label)}</text>
  <text x="50" y="99" fill="#8DA8B8" font-family="Segoe UI,Arial,sans-serif" font-size="14">Version {escape(model.version)} • Status {escape(model.status)} • Beta readiness {escape(model.beta_status)}</text>
  <rect x="50" y="112" width="1100" height="18" rx="7" fill="#02050A" stroke="#62E5FF" stroke-opacity="0.28"/>
  {fill}
  <text x="50" y="154" fill="#F4FAFF" font-family="Segoe UI,Arial,sans-serif" font-size="15" font-weight="600">{escape(model.authority_label)}</text>
  <text x="1150" y="154" text-anchor="end" fill="#8DA8B8" font-family="Segoe UI,Arial,sans-serif" font-size="13">Source: BUILD_STATUS.json • Beta gate shown separately</text>
</svg>
'''


def render_mini(model: ProgressModel) -> str:
    fill = _progress_fill(MINI_TRACK_X, 43, 12, MINI_TRACK_WIDTH, model.percentage)
    description = (
        f"{model.project} compact roadmap dashboard; progress {model.percent_label}; {model.authority_label}; "
        f"status {model.status}; Beta readiness {model.beta_status}."
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="900" height="72" viewBox="0 0 900 72" role="img" aria-labelledby="title desc">
  <title id="title">{escape(model.project)} compact roadmap progress — {escape(model.percent_label)}</title>
  <desc id="desc">{escape(description)}</desc>
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#02050A"/><stop offset="1" stop-color="#07111C"/></linearGradient>
    <linearGradient id="progressGradient" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#0088FF"/><stop offset="1" stop-color="#62E5FF"/></linearGradient>
    <filter id="softGlow" x="-20%" y="-100%" width="140%" height="300%"><feGaussianBlur stdDeviation="2" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <clipPath id="trackClip"><rect x="170" y="43" width="700" height="12" rx="5"/></clipPath>
  </defs>
  <rect x="1" y="1" width="898" height="70" rx="16" fill="url(#bg)" stroke="#62E5FF" stroke-opacity="0.24" stroke-width="2"/>
  <text x="28" y="28" fill="#F4FAFF" font-family="Segoe UI,Arial,sans-serif" font-size="17" font-weight="700">{escape(model.project)}</text>
  <text x="870" y="28" text-anchor="end" fill="#62E5FF" font-family="Segoe UI,Arial,sans-serif" font-size="18" font-weight="800">{escape(model.percent_label)} • {escape(model.status)}</text>
  <text x="28" y="55" fill="#8DA8B8" font-family="Segoe UI,Arial,sans-serif" font-size="12">{escape(model.authority_completed.__str__())}/{escape(model.authority_total.__str__())} authorities</text>
  <rect x="170" y="43" width="700" height="12" rx="5" fill="#02050A" stroke="#62E5FF" stroke-opacity="0.28"/>
  {fill}
</svg>
'''


def render_template() -> str:
    return '''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="180" viewBox="0 0 1200 180" role="img" aria-labelledby="title desc">
  <title id="title">SWIR Progress SVG PRO template — N/A</title>
  <desc id="desc">Reusable TEMPLATE / NOT PROJECT DATA. Progress is N/A and no fill is rendered.</desc>
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#02050A"/><stop offset="1" stop-color="#07111C"/></linearGradient>
    <linearGradient id="progressGradient" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#0088FF"/><stop offset="1" stop-color="#62E5FF"/></linearGradient>
    <pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse"><path d="M32 0H0V32" fill="none" stroke="#62E5FF" stroke-opacity="0.045" stroke-width="1"/></pattern>
    <clipPath id="trackClip"><rect x="50" y="112" width="1100" height="18" rx="7"/></clipPath>
  </defs>
  <rect x="1" y="1" width="1198" height="178" rx="20" fill="url(#bg)" stroke="#62E5FF" stroke-opacity="0.24" stroke-width="2"/>
  <rect x="1" y="1" width="1198" height="178" rx="20" fill="url(#grid)"/>
  <text x="50" y="38" fill="#8DA8B8" font-family="Segoe UI,Arial,sans-serif" font-size="14" font-weight="700" letter-spacing="2">SWIR PROGRESS SVG PRO • TEMPLATE / NOT PROJECT DATA</text>
  <text x="50" y="76" fill="#F4FAFF" font-family="Segoe UI,Arial,sans-serif" font-size="30" font-weight="700">PROJECT NAME</text>
  <text x="1150" y="76" text-anchor="end" fill="#62E5FF" font-family="Segoe UI,Arial,sans-serif" font-size="30" font-weight="800">N/A</text>
  <text x="50" y="99" fill="#8DA8B8" font-family="Segoe UI,Arial,sans-serif" font-size="14">Measured scope: VERIFY SOURCE BEFORE GENERATION • Status N/A • Beta readiness N/A</text>
  <rect x="50" y="112" width="1100" height="18" rx="7" fill="#02050A" stroke="#62E5FF" stroke-opacity="0.28"/>
  <text x="50" y="154" fill="#F4FAFF" font-family="Segoe UI,Arial,sans-serif" font-size="15" font-weight="600">Counter: N/A</text>
  <text x="1150" y="154" text-anchor="end" fill="#8DA8B8" font-family="Segoe UI,Arial,sans-serif" font-size="13">TEMPLATE ONLY • NEVER EMBED AS LIVE PROGRESS</text>
</svg>
'''


def expected_outputs(model: ProgressModel) -> dict[Path, str]:
    return {
        CARD_PATH: render_card(model),
        MINI_PATH: render_mini(model),
        TEMPLATE_PATH: render_template(),
    }


def _parse_svg(text: str, label: str) -> ET.Element:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ProgressSvgError(f"{label} is not valid XML: {exc}") from exc
    if root.tag != "{http://www.w3.org/2000/svg}svg":
        raise ProgressSvgError(f"{label} root is not SVG")
    view_box = root.attrib.get("viewBox", "").split()
    if len(view_box) != 4:
        raise ProgressSvgError(f"{label} has invalid viewBox")
    try:
        numbers = [float(item) for item in view_box]
    except ValueError as exc:
        raise ProgressSvgError(f"{label} viewBox is not numeric") from exc
    if not all(math.isfinite(item) for item in numbers) or numbers[2] <= 0 or numbers[3] <= 0:
        raise ProgressSvgError(f"{label} viewBox is not finite/bounded")
    if not root.findall("{http://www.w3.org/2000/svg}title") or not root.findall("{http://www.w3.org/2000/svg}desc"):
        raise ProgressSvgError(f"{label} must contain accessible title and description")
    return root


def verify_embeddings(model: ProgressModel) -> None:
    try:
        readme = README_PATH.read_text(encoding="utf-8")
        roadmap = ROADMAP_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProgressSvgError(f"cannot read README/ROADMAP embedding: {exc}") from exc
    if 'src="assets/readme/progress-card.svg"' not in readme:
        raise ProgressSvgError("README is missing the local progress card embedding")
    if 'src="assets/readme/progress-mini.svg"' not in roadmap:
        raise ProgressSvgError("ROADMAP is missing the local compact progress embedding")
    expected_readme = f"**Roadmap progress:** **{model.percent_label}**"
    expected_roadmap = f"**Roadmap dashboard:** **{model.percent_label}**"
    if expected_readme not in readme or expected_roadmap not in roadmap:
        raise ProgressSvgError("textual progress fallback does not match BUILD_STATUS.json")
    if f"Beta readiness: **{model.beta_status}**" not in readme or f"Beta readiness: **{model.beta_status}**" not in roadmap:
        raise ProgressSvgError("Beta readiness textual fallback does not match BUILD_STATUS.json")
    legacy = f"**{int(model.percentage)}% complete**" if model.percentage is not None and model.percentage.is_integer() else None
    if legacy and legacy not in readme:
        raise ProgressSvgError("protected README textual progress marker disappeared")
    if legacy and legacy not in roadmap:
        raise ProgressSvgError("protected ROADMAP textual progress marker disappeared")


def verify_outputs(model: ProgressModel) -> None:
    for path, expected in expected_outputs(model).items():
        if not path.is_file() or path.is_symlink():
            raise ProgressSvgError(f"generated asset is missing or unsafe: {path.relative_to(ROOT)}")
        actual = path.read_text(encoding="utf-8")
        if actual != expected:
            raise ProgressSvgError(f"generated asset is stale: {path.relative_to(ROOT)}")
        root = _parse_svg(actual, str(path.relative_to(ROOT)))
        if "XXX" in actual or "NaN" in actual or "Infinity" in actual:
            raise ProgressSvgError(f"generated asset contains placeholder/non-finite geometry: {path.relative_to(ROOT)}")
        for node in root.iter():
            for attribute, value in node.attrib.items():
                if attribute in {"x", "y", "width", "height", "rx", "ry"}:
                    try:
                        number = float(value)
                    except ValueError:
                        continue
                    if not math.isfinite(number) or number < 0:
                        raise ProgressSvgError(f"generated asset has invalid numeric geometry: {path.relative_to(ROOT)}")
    verify_embeddings(model)


def write_outputs(model: ProgressModel) -> None:
    for path, content in expected_outputs(model).items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if committed assets/embeddings are stale")
    args = parser.parse_args()
    try:
        model = load_model()
        if args.check:
            verify_outputs(model)
            print(
                f"progress SVGs current: {model.percent_label}; {model.status}; "
                f"{model.authority_label}; Beta readiness {model.beta_status}"
            )
        else:
            write_outputs(model)
            verify_outputs(model)
            print(f"generated progress SVGs from {STATUS_PATH.name}: {model.percent_label}")
    except ProgressSvgError as exc:
        print(f"progress SVG error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
