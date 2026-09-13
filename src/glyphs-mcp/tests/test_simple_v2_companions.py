"""Independent companion cores, registration, and drawing-boundary tests."""

from __future__ import annotations

import ast
import builtins
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[3]
ROOTS = (
    REPO / "src" / "companions" / "sdk",
    REPO / "src" / "companions" / "curve-inspector",
)
for root in ROOTS:
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

import glyphs_mcp_companions as companions  # noqa: E402
from curve_core import (  # noqa: E402
    DEFAULT_SAMPLES_PER_CURVE,
    DEFAULT_STROKE_LIMIT,
    NEGATIVE_RGBA,
    OVERLAY_ALPHA,
    POSITIVE_RGBA,
    analyze_cubic,
    analyze_cubics,
    build_curvature_comb,
    choose_sample_count,
    curvature,
    overlay_line_widths,
)


def test_curve_core_handles_straight_curved_and_multiple_segments() -> None:
    straight = ((0, 0), (10, 0), (20, 0), (30, 0))
    curved = ((0, 0), (0, 100), (100, 100), (100, 0))
    assert curvature(straight, 0.5) == 0
    result = analyze_cubic(curved, samples=31)
    assert result["absoluteCurvature"] > 0
    assert 0 <= result["t"] <= 1
    assert [item["segment"] for item in analyze_cubics([straight, curved])] == [0, 1]


def test_curve_core_builds_a_visible_bounded_signed_comb() -> None:
    curved = ((0, 0), (0, 100), (100, 100), (100, 0))
    model = build_curvature_comb([curved] * 128, upm=1000)
    strokes = model["strokes"]
    assert model["samplesPerCurve"] == 15
    assert 0 < len(strokes) <= DEFAULT_STROKE_LIMIT
    assert {item["sign"] for item in strokes} <= {"positive", "negative"}
    assert all(item["start"] != item["end"] for item in strokes)
    assert all(
        ((item["end"][0] - item["start"][0]) ** 2 + (item["end"][1] - item["start"][1]) ** 2)
        ** 0.5
        <= 120.000001
        for item in strokes
    )
    assert model["envelopes"]


def test_curve_display_constants_and_zoom_widths_match_the_previous_inspector() -> None:
    assert DEFAULT_SAMPLES_PER_CURVE == 51
    assert DEFAULT_STROKE_LIMIT == 2000
    assert OVERLAY_ALPHA == 0.65
    assert POSITIVE_RGBA == (0.00, 0.62, 0.62, 0.65)
    assert NEGATIVE_RGBA == (0.86, 0.18, 0.55, 0.65)
    assert overlay_line_widths(1.0) == (0.75, 1.15)
    assert overlay_line_widths(100.0) == (0.35, 0.5)


def test_sample_reduction_is_odd_deterministic_and_never_below_nine() -> None:
    assert choose_sample_count(1) == (51, False)
    assert choose_sample_count(128) == (15, True)
    assert choose_sample_count(300) == (9, True)
    model = build_curvature_comb(
        [((0, 0), (0, 100), (100, 100), (100, 0))] * 300
    )
    assert model["strokeCount"] == 2000
    assert model["strokeCapReached"] is True


def test_legacy_numeric_reference_for_teeth_and_connected_envelopes() -> None:
    """Frozen output from the previous Glyphs MCP Curvature implementation."""

    curve = ((0, 0), (0, 100), (100, 100), (100, 0))
    expected_ends = [
        (66.66666666666667, 0.0),
        (109.15447500000002, 2.229033333333323),
        (111.625, -15.75),
        (88.11121323529412, -35.569852941176464),
        (50.0, -45.0),
        (11.888786764705884, -35.569852941176464),
        (-11.625, -15.75),
        (-9.15447500000002, 2.229033333333323),
        (33.33333333333333, 0.0),
    ]
    model = build_curvature_comb([curve], samples=9)
    assert model["strokeCount"] == 9
    assert [item["sign"] for item in model["strokes"]] == ["negative"] * 9
    for observed, expected in zip(
        (item["end"] for item in model["strokes"]), expected_ends
    ):
        assert observed == pytest.approx(expected, abs=1.0e-12)
    assert len(model["envelopes"]) == 1
    assert model["envelopes"][0]["sign"] == "negative"
    for observed, expected in zip(model["envelopes"][0]["points"], expected_ends):
        assert observed == pytest.approx(expected, abs=1.0e-12)


def test_inflection_splits_the_legacy_envelope_at_zero_curvature() -> None:
    curve = ((0, 0), (100, 0), (0, 100), (100, 100))
    model = build_curvature_comb([curve], samples=9)
    assert [item["sign"] for item in model["strokes"]] == [
        "positive",
        "positive",
        "positive",
        "positive",
        "negative",
        "negative",
        "negative",
        "negative",
    ]
    assert [(item["sign"], len(item["points"])) for item in model["envelopes"]] == [
        ("positive", 4),
        ("negative", 4),
    ]
    assert model["envelopes"][0]["points"][-1] == pytest.approx(
        (168.16609808191618, 15.780978589077845), abs=1.0e-12
    )
    assert model["envelopes"][1]["points"][0] == pytest.approx(
        (169.72859808191618, 52.49972858907785), abs=1.0e-12
    )


def test_straight_degenerate_and_segment_boundaries_never_join_envelopes() -> None:
    straight = ((0, 0), (10, 0), (20, 0), (30, 0))
    degenerate = ((5, 5), (5, 5), (5, 5), (5, 5))
    curved = ((0, 0), (0, 100), (100, 100), (100, 0))
    model = build_curvature_comb([curved, straight, degenerate, curved], samples=9)
    assert {item["segment"] for item in model["envelopes"]} == {0, 3}
    assert all(len(item["points"]) == 9 for item in model["envelopes"])


def test_companion_registration_works_before_or_after_the_bridge() -> None:
    if hasattr(builtins, companions._SLOT):
        delattr(builtins, companions._SLOT)

    class Registry:
        def __init__(self):
            self.items = {}

        def register(self, value):
            changed = self.items.get(value["id"]) != value
            self.items[value["id"]] = value
            return changed

        def unregister(self, identity):
            return self.items.pop(identity, None) is not None

    manifest = {
        "protocol": 1,
        "id": "curve-inspector",
        "version": "0.1.0",
        "capabilities": ["curve.measure", "curve.overlay"],
    }
    assert companions.publish(manifest) is True
    registry = Registry()
    companions.attach_registry(registry)
    assert registry.items == {"curve-inspector": manifest}
    assert companions.withdraw("curve-inspector") is True
    assert registry.items == {}
    companions.detach_registry(registry)


def test_reporter_foreground_is_drawing_only() -> None:
    source = (
        REPO
        / "src"
        / "companions"
        / "curve-inspector"
        / "glyphs_curve_inspector"
        / "plugin.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    foreground = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "foreground"
    )
    body = ast.unparse(foreground)
    assert "paths" not in body
    assert "extract_visible_cubics" not in body
    assert "analyze_cubics" not in body
    assert "build_curvature_comb" not in body
    assert "Glyphs" not in body
    assert "envelopes" in body
    assert "overlay_line_widths" in body


def test_reporter_coalesces_unchanged_ui_updates() -> None:
    source = (
        REPO
        / "src"
        / "companions"
        / "curve-inspector"
        / "glyphs_curve_inspector"
        / "plugin.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    update = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "update_"
    )
    body = ast.unparse(update)
    assert "if source_key == self._source_key:" in body
    assert "return" in body


def test_reporter_redraws_only_when_cached_overlay_changes() -> None:
    source = (
        REPO
        / "src"
        / "companions"
        / "curve-inspector"
        / "glyphs_curve_inspector"
        / "plugin.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    publish = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_publish"
    )
    body = ast.unparse(publish)
    assert "changed = next_cache != self._cache" in body
    assert "if changed:" in body
    assert body.count("invalidate_view(Glyphs)") == 1
    assert "Glyphs.redraw()" not in body
