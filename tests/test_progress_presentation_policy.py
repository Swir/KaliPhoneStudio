from pathlib import Path

import pytest

from scripts.check_progress_presentation import (
    ProgressPresentationError,
    find_legacy_progress_meters,
    verify_progress_presentation,
)

ROOT = Path(__file__).resolve().parents[1]


def test_current_readme_and_roadmap_pass_svg_only_policy():
    verify_progress_presentation()


def test_unicode_and_bracketed_legacy_meters_are_rejected():
    assert find_legacy_progress_meters("Progress: ██████░░░░ 60%")
    assert find_legacy_progress_meters("Roadmap [######----] 60%")
    assert find_legacy_progress_meters("Status [========--] 80%")


def test_bare_ascii_meter_with_progress_context_is_rejected():
    assert find_legacy_progress_meters("Project progress ########-------- 50%")


def test_numeric_fallback_checkboxes_and_directory_tree_are_not_meters():
    text = """**58% complete**
- [x] deterministic generator
- [ ] physical device gate
```text
KaliPhoneStudio/
├── kaliphonestudio/
└── devices/
```
"""
    assert find_legacy_progress_meters(text) == []


def test_fenced_historical_examples_do_not_trigger_cleanup_policy():
    text = """Historical evidence retained verbatim:
```text
Progress: ██████░░░░ 60%
Roadmap [######----] 60%
```
Current progress is rendered by SVG.
"""
    assert find_legacy_progress_meters(text) == []


def _write_fixture(tmp_path: Path, readme: str, roadmap: str, template: str | None = None):
    readme_path = tmp_path / "README.md"
    roadmap_path = tmp_path / "ROADMAP.md"
    template_path = tmp_path / "progress-template.svg"
    readme_path.write_text(readme, encoding="utf-8")
    roadmap_path.write_text(roadmap, encoding="utf-8")
    template_path.write_text(
        template
        or '<svg><text>TEMPLATE / NOT PROJECT DATA</text><text>N/A</text><text>N/A</text></svg>'.replace(">N/A<", ">N/A<"),
        encoding="utf-8",
    )
    return readme_path, roadmap_path, template_path


def _valid_template() -> str:
    return "<svg><text>TEMPLATE / NOT PROJECT DATA</text><text>N/A</text></svg>"


def test_duplicate_or_wrong_scope_graphics_fail_closed(tmp_path):
    card = '<img src="assets/readme/progress-card.svg" />'
    mini = '<img src="assets/readme/progress-mini.svg" />'
    readme_path, roadmap_path, template_path = _write_fixture(
        tmp_path,
        f"{card}\n{card}\n",
        f"{mini}\n",
        _valid_template(),
    )
    with pytest.raises(ProgressPresentationError, match="README"):
        verify_progress_presentation(readme_path, roadmap_path, template_path)

    readme_path.write_text(f"{card}\n{mini}\n", encoding="utf-8")
    with pytest.raises(ProgressPresentationError, match="README"):
        verify_progress_presentation(readme_path, roadmap_path, template_path)


def test_template_can_never_be_embedded_as_live_data(tmp_path):
    card = '<img src="assets/readme/progress-card.svg" />'
    mini = '<img src="assets/readme/progress-mini.svg" />'
    template_embed = '<img src="assets/readme/progress-template.svg" />'
    readme_path, roadmap_path, template_path = _write_fixture(
        tmp_path,
        f"{card}\n{template_embed}\n",
        f"{mini}\n",
        _valid_template(),
    )
    with pytest.raises(ProgressPresentationError, match="README"):
        verify_progress_presentation(readme_path, roadmap_path, template_path)


def test_live_legacy_meter_fails_document_policy(tmp_path):
    card = '<img src="assets/readme/progress-card.svg" />'
    mini = '<img src="assets/readme/progress-mini.svg" />'
    readme_path, roadmap_path, template_path = _write_fixture(
        tmp_path,
        f"{card}\nProgress: ██████░░░░ 60%\n",
        f"{mini}\n",
        _valid_template(),
    )
    with pytest.raises(ProgressPresentationError, match="retired text-art progress meter"):
        verify_progress_presentation(readme_path, roadmap_path, template_path)


def test_template_must_remain_na_and_project_neutral(tmp_path):
    card = '<img src="assets/readme/progress-card.svg" />'
    mini = '<img src="assets/readme/progress-mini.svg" />'
    readme_path, roadmap_path, template_path = _write_fixture(
        tmp_path,
        f"{card}\n",
        f"{mini}\n",
        "<svg><text>TEMPLATE / NOT PROJECT DATA</text><text>KaliPhoneStudio</text></svg>",
    )
    with pytest.raises(ProgressPresentationError):
        verify_progress_presentation(readme_path, roadmap_path, template_path)
