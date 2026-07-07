"""Regression tests for master stem metric MCP tools."""

from __future__ import annotations

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


def _module_path() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Resources"
        / "mcp_tools_stems.py"
    )


def _resources_dir() -> Path:
    return _module_path().parent


class _FakeMCP:
    def tool(self, *args, **kwargs):
        def decorator(fn):
            return fn

        return decorator


class _FakeStem:
    def __init__(self, name="", horizontal=False):
        self.name = name
        self.horizontal = horizontal
        self.id = name


class _FakePoint:
    def __init__(self, x, y):
        self.x = x
        self.y = y


class _FakeBounds:
    def __init__(self):
        self.origin = types.SimpleNamespace(x=0.0, y=0.0)
        self.size = types.SimpleNamespace(width=100.0, height=100.0)


class _FakeLayer:
    def __init__(self):
        self.bounds = _FakeBounds()

    def intersectionsBetweenPoints(self, start, end, components=True):
        if start[1] == end[1]:
            y = start[1]
            return [_FakePoint(-20, y), _FakePoint(10, y), _FakePoint(90, y), _FakePoint(120, y)]
        x = start[0]
        return [_FakePoint(x, -20), _FakePoint(x, 20), _FakePoint(x, 70), _FakePoint(x, 120)]


class _FakeGlyphs(dict):
    def __iter__(self):
        return iter(self.values())


class _Glyphs4StemProxy:
    def __init__(self, values):
        self._values = list(values)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return 0.0

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)


def _resolve_font_by_index(glyphs, font_index):
    fonts = list(getattr(glyphs, "fonts", []) or [])
    index = int(font_index)
    if index < 0 or index >= len(fonts):
        return None, fonts
    return fonts[index], fonts


def _font_resolution_error(font_index, fonts=None, ok_key=None):
    payload = {"error": "Font index out of range", "fontIndex": font_index, "availableFontCount": len(fonts or [])}
    if ok_key == "ok":
        payload["ok"] = False
    return payload


def _font_with_stems(master_stems):
    master = types.SimpleNamespace(
        id="m1",
        name="Regular",
        stems=dict(master_stems),
        capHeight=700,
        xHeight=500,
    )
    glyph = types.SimpleNamespace(layers={"m1": _FakeLayer()})
    glyphs = _FakeGlyphs({"H": glyph, "n": glyph, "o": glyph, "E": glyph})
    font = types.SimpleNamespace(
        familyName="Test",
        stems=[_FakeStem("Vertical", False), _FakeStem("Horizontal", True)],
        masters=[master],
        glyphs=glyphs,
        upm=1000,
    )
    return font, master


class McpToolsStemsTests(unittest.TestCase):
    def _load_module(self, font):
        class FakeGSMetric(_FakeStem):
            def __init__(self):
                super().__init__("", False)

        glyphs_module = types.SimpleNamespace(
            Glyphs=types.SimpleNamespace(fonts=[font], font=font),
            GSMetric=FakeGSMetric,
        )
        helpers_module = types.SimpleNamespace(
            _coerce_numeric=lambda value: None if value is None else float(value),
            _font_resolution_error=_font_resolution_error,
            _resolve_font_by_index=_resolve_font_by_index,
            _safe_attr=lambda obj, attr, default=None: getattr(obj, attr, default),
            _safe_json=lambda payload: json.dumps(payload),
        )
        module_name = "glyphs_mcp_test_mcp_tools_stems"
        spec = importlib.util.spec_from_file_location(module_name, _module_path())
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(
            sys.modules,
            {
                "GlyphsApp": glyphs_module,
                "mcp_runtime": types.SimpleNamespace(mcp=_FakeMCP()),
                "mcp_tool_helpers": helpers_module,
            },
        ):
            sys.path.insert(0, str(_resources_dir()))
            sys.modules.pop(module_name, None)
            sys.modules.pop("stem_metrics_helpers", None)
            assert spec.loader is not None
            spec.loader.exec_module(module)
        return module

    def test_review_detects_complete_stems(self) -> None:
        font, _master = _font_with_stems({"Vertical": 82, "Horizontal": 74})
        module = self._load_module(font)

        payload = module._review_master_stem_metrics_impl(
            font_index=0,
            master_ids=["m1"],
            include_measurements=False,
        )

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["readyForCursivy"])
        self.assertEqual(payload["summary"]["readyCount"], 1)

    def test_review_reads_glyphs4_stem_proxy_by_index_when_name_returns_zero(self) -> None:
        font, master = _font_with_stems({})
        master.stems = _Glyphs4StemProxy([82, 74])
        module = self._load_module(font)

        payload = module._review_master_stem_metrics_impl(
            font_index=0,
            master_ids=["m1"],
            include_measurements=False,
        )

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["readyForCursivy"])
        stems = payload["masters"][0]["stems"]
        self.assertEqual(stems[0]["value"], 82.0)
        self.assertEqual(stems[1]["value"], 74.0)

    def test_review_reports_missing_target_stems(self) -> None:
        font, _master = _font_with_stems({"Vertical": 82})
        module = self._load_module(font)

        payload = module._review_master_stem_metrics_impl(
            font_index=0,
            master_ids=["m1"],
            include_measurements=False,
        )

        self.assertTrue(payload["ok"])
        self.assertFalse(payload["readyForCursivy"])
        self.assertEqual(payload["masters"][0]["missingOrientations"], ["horizontal"])

    def test_review_reports_measured_suggestions(self) -> None:
        font, master = _font_with_stems({})
        font.stems = []
        module = self._load_module(font)

        payload = module._review_master_stem_metrics_impl(
            font_index=0,
            master_ids=[master.id],
            include_measurements=True,
            reference_glyphs=["H"],
            samples=1,
        )

        self.assertTrue(payload["ok"])
        self.assertFalse(payload["readyForCursivy"])
        self.assertEqual(payload["masters"][0]["measurements"]["vertical"]["value"], 80.0)
        self.assertEqual(payload["masters"][0]["measurements"]["horizontal"]["value"], 50.0)

    def test_review_handles_invalid_master_id(self) -> None:
        font, _master = _font_with_stems({"Vertical": 82, "Horizontal": 74})
        module = self._load_module(font)

        payload = module._review_master_stem_metrics_impl(font_index=0, master_ids=["missing"])

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["missingMasterIds"], ["missing"])

    def test_set_stems_dry_run_does_not_mutate(self) -> None:
        font, master = _font_with_stems({})
        font.stems = []
        module = self._load_module(font)

        payload = module._set_master_stem_metrics_impl(
            font_index=0,
            master_id=master.id,
            vertical_stem=82,
            horizontal_stem=74,
            dry_run=True,
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(len(font.stems), 0)
        self.assertEqual(master.stems, {})

    def test_set_stems_confirm_creates_and_updates(self) -> None:
        font, master = _font_with_stems({})
        font.stems = []
        module = self._load_module(font)

        payload = module._set_master_stem_metrics_impl(
            font_index=0,
            master_id=master.id,
            vertical_stem=82,
            horizontal_stem=74,
            confirm=True,
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(len(font.stems), 2)
        self.assertEqual(master.stems["Vertical"], 82.0)
        self.assertEqual(master.stems["Horizontal"], 74.0)

    def test_set_stems_rejects_invalid_values(self) -> None:
        font, master = _font_with_stems({})
        module = self._load_module(font)

        payload = module._set_master_stem_metrics_impl(
            font_index=0,
            master_id=master.id,
            vertical_stem=0,
            confirm=True,
        )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errors"][0]["error"], "Stem value must be a positive number")


if __name__ == "__main__":
    unittest.main()
