import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from scripts.generate_progress_svgs import (
    CARD_TRACK_WIDTH,
    MINI_TRACK_WIDTH,
    CARD_PATH,
    MINI_PATH,
    TEMPLATE_PATH,
    ProgressSvgError,
    build_model,
    fill_width,
    render_card,
    render_mini,
    render_template,
    verify_outputs,
)

ROOT = Path(__file__).resolve().parents[1]


def _status(percent=58):
    return {
        "version": "0.6.64-dev",
        "project_progress_percent": percent,
        "beta_gate": "BLOCKED",
        "hardware_verified": False,
        "rootfs_reproducibility_authority_state": "passed-reviewed",
        "kernel_reproducibility_authority_state": "passed-reviewed",
        "device_tree_reproducibility_authority_state": "passed-reviewed",
    }


def _xml(text):
    return ET.fromstring(text)


def test_partial_progress_math_and_bounded_default_geometry():
    model = build_model(_status(58))
    assert model.percent_label == "58.0%"
    assert model.authority_label == "Host authorities: 3/3 reviewed"
    assert fill_width(CARD_TRACK_WIDTH, model.percentage) == pytest.approx(638.0)
    assert fill_width(MINI_TRACK_WIDTH, model.percentage) == pytest.approx(406.0)
    assert 'width="638.000"' in render_card(model)
    assert 'width="406.000"' in render_mini(model)


def test_zero_partial_and_complete_geometry_are_exact_and_bounded():
    zero = build_model(_status(0))
    assert fill_width(CARD_TRACK_WIDTH, zero.percentage) == 0
    assert 'filter="url(#softGlow)" clip-path="url(#trackClip)"' not in render_card(zero)

    partial = build_model(_status(7.6923))
    assert fill_width(CARD_TRACK_WIDTH, partial.percentage) == pytest.approx(84.6153)
    assert partial.percent_label == "7.7%"

    complete = build_model(_status(100))
    assert fill_width(CARD_TRACK_WIDTH, complete.percentage) == CARD_TRACK_WIDTH
    assert fill_width(MINI_TRACK_WIDTH, complete.percentage) == MINI_TRACK_WIDTH


def test_unknown_progress_is_na_and_has_no_fill():
    model = build_model(_status(None))
    assert model.percent_label == "N/A"
    assert fill_width(CARD_TRACK_WIDTH, model.percentage) is None
    svg = render_card(model)
    assert "N/A" in svg
    assert 'filter="url(#softGlow)" clip-path="url(#trackClip)"' not in svg


def test_invalid_percent_is_rejected():
    for value in (-0.1, 100.1, float("nan"), float("inf"), "58", True):
        with pytest.raises(ProgressSvgError):
            build_model(_status(value))


def test_template_is_valid_na_and_never_project_data():
    svg = render_template()
    root = _xml(svg)
    assert root.tag.endswith("svg")
    assert "TEMPLATE / NOT PROJECT DATA" in svg
    assert ">N/A<" in svg
    assert "KaliPhoneStudio" not in svg
    assert 'filter="url(#softGlow)" clip-path="url(#trackClip)"' not in svg


def test_generated_xml_has_accessible_metadata():
    model = build_model(_status())
    for svg in (render_card(model), render_mini(model), render_template()):
        root = _xml(svg)
        ns = {"svg": "http://www.w3.org/2000/svg"}
        assert root.find("svg:title", ns) is not None
        assert root.find("svg:desc", ns) is not None
        view_box = [float(item) for item in root.attrib["viewBox"].split()]
        assert view_box[2] > 0 and view_box[3] > 0


def test_long_scope_does_not_change_progress_geometry():
    model = build_model(_status())
    longer = type(model)(
        project=model.project,
        scope="A deliberately very long measured scope label used to test bounded SVG geometry",
        version=model.version,
        percentage=model.percentage,
        status=model.status,
        beta_status=model.beta_status,
        authority_completed=model.authority_completed,
        authority_total=model.authority_total,
    )
    assert 'width="638.000"' in render_card(longer)
    assert 'width="406.000"' in render_mini(longer)


def test_committed_assets_and_text_fallback_match_authoritative_status():
    status = json.loads((ROOT / "BUILD_STATUS.json").read_text(encoding="utf-8"))
    assert status["project_progress_percent"] == 58
    assert status["beta_gate"] == "BLOCKED"
    assert status["progress_svg_standard"] == "SWIR-PROGRESS-SVG-PRO:v1"
    assert status["progress_svg_source"] == "BUILD_STATUS.json"
    assert "project_progress_percent" in status["progress_svg_calculation"]
    verify_outputs(build_model(status))
    assert CARD_PATH.is_file() and MINI_PATH.is_file() and TEMPLATE_PATH.is_file()
