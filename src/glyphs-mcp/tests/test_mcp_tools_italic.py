"""Regression tests for italic first-pass MCP tools."""

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
        / "mcp_tools_italic.py"
    )


def _resources_dir() -> Path:
    return _module_path().parent


class _FakeMCP:
    def tool(self, *args, **kwargs):
        def decorator(fn):
            return fn

        return decorator


class _FakeStem:
    def __init__(self, name, horizontal):
        self.name = name
        self.horizontal = horizontal
        self.id = name


class _FakeNode:
    def __init__(self, node_type="line"):
        self.type = node_type


class _FakePath:
    def __init__(self, node_types):
        self.nodes = [_FakeNode(t) for t in node_types]

    def copy(self):
        return _FakePath([node.type for node in self.nodes])


class _FakeLayer:
    def __init__(self, width=500, node_types=None):
        self.paths = [_FakePath(node_types or ["line", "line"])]
        self.components = []
        self.anchors = []
        self.width = width
        self.leftSideBearing = 40
        self.rightSideBearing = 60
        self.bounds = types.SimpleNamespace(
            origin=types.SimpleNamespace(x=0.0, y=0.0),
            size=types.SimpleNamespace(width=100.0, height=100.0),
        )
        self.parent = None

    def copy(self):
        layer = _FakeLayer(self.width)
        layer.paths = [path.copy() for path in self.paths]
        layer.components = list(self.components)
        layer.anchors = list(self.anchors)
        layer.leftSideBearing = self.leftSideBearing
        layer.rightSideBearing = self.rightSideBearing
        return layer


class _FakeLayers(dict):
    def __init__(self):
        super().__init__()
        self.backups = []

    def append(self, layer):
        self.backups.append(layer)


class _FakeGlyph:
    def __init__(self, name, source_layer, target_layer):
        self.name = name
        self.unicode = None
        self.category = "Letter"
        self.subCategory = "Lowercase"
        self.export = True
        self.layers = _FakeLayers()
        self.layers["roman"] = source_layer
        self.layers["italic"] = target_layer
        source_layer.parent = self
        target_layer.parent = self
        self.undo_depth = 0

    def beginUndo(self):
        self.undo_depth += 1

    def endUndo(self):
        self.undo_depth -= 1


class _FakeGlyphs(dict):
    def __iter__(self):
        return iter(self.values())

    def append(self, glyph):
        self[glyph.name] = glyph


class GlyphsFilterTransformations:
    def __init__(self):
        self.calls = []

    def filter(self, layer, include, args):
        self.calls.append({"layer": layer, "include": include, "args": dict(args)})


def _make_font(complete_stems=True):
    source_master = types.SimpleNamespace(id="roman", name="Roman", stems={"Vertical": 82, "Horizontal": 74})
    target_stems = {"Vertical": 82, "Horizontal": 74} if complete_stems else {"Vertical": 82}
    target_master = types.SimpleNamespace(id="italic", name="Italic", stems=target_stems)

    a = _FakeGlyph("a", _FakeLayer(500, ["line", "curve"]), _FakeLayer(490, ["line"]))
    b = _FakeGlyph("b", _FakeLayer(510, ["line", "line"]), _FakeLayer(500, ["line", "line"]))
    glyphs = _FakeGlyphs({"a": a, "b": b})
    font = types.SimpleNamespace(
        familyName="Test",
        stems=[_FakeStem("Vertical", False), _FakeStem("Horizontal", True)],
        masters=[source_master, target_master],
        selectedFontMaster=target_master,
        selectedLayers=[a.layers["italic"], b.layers["italic"]],
        glyphs=glyphs,
        upm=1000,
    )
    return font


class McpToolsItalicTests(unittest.TestCase):
    def _load_module(self, font, filter_obj=None):
        class FakeGSGlyph(_FakeGlyph):
            def __init__(self, name):
                super().__init__(name, _FakeLayer(), _FakeLayer())

        filter_obj = filter_obj or GlyphsFilterTransformations()
        glyphs_module = types.SimpleNamespace(
            Glyphs=types.SimpleNamespace(fonts=[font], font=font, filters=[filter_obj]),
            GSGlyph=FakeGSGlyph,
            GSMetric=lambda: _FakeStem("", False),
        )
        helpers_module = types.SimpleNamespace(
            _clear_layer_paths=lambda layer: layer.paths.clear(),
            _coerce_numeric=lambda value: None if value is None else float(value),
            _get_left_sidebearing=lambda layer: getattr(layer, "leftSideBearing", None),
            _get_right_sidebearing=lambda layer: getattr(layer, "rightSideBearing", None),
            _safe_attr=lambda obj, attr, default=None: getattr(obj, attr, default),
            _safe_json=lambda payload: json.dumps(payload),
            _set_sidebearing=lambda layer, attr_name, legacy_attr, value: setattr(layer, attr_name, float(value)) or True,
        )
        module_name = "glyphs_mcp_test_mcp_tools_italic"
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
            for name in (module_name, "mcp_tools_stems", "stem_metrics_helpers"):
                sys.modules.pop(name, None)
            assert spec.loader is not None
            spec.loader.exec_module(module)
        return module, filter_obj

    def test_scope_resolution_modes(self) -> None:
        font = _make_font()
        module, _filter = self._load_module(font)

        named = module._review_italic_first_pass_impl(
            source_master_id="roman",
            target_master_id="italic",
            scope="glyph_names",
            glyph_names=["b"],
            slant_mode="raw",
        )
        selected = module._review_italic_first_pass_impl(
            source_master_id="roman",
            target_master_id="italic",
            scope="selected_glyphs",
            slant_mode="raw",
        )
        current = module._review_italic_first_pass_impl(
            source_master_id="roman",
            target_master_id="italic",
            scope="current_glyph",
            slant_mode="raw",
        )
        all_glyphs = module._review_italic_first_pass_impl(
            source_master_id="roman",
            target_master_id="italic",
            scope="all_glyphs",
            slant_mode="raw",
        )

        self.assertEqual([r["glyphName"] for r in named["results"]], ["b"])
        self.assertEqual(selected["summary"]["glyphCount"], 2)
        self.assertEqual([r["glyphName"] for r in current["results"]], ["a"])
        self.assertEqual(all_glyphs["summary"]["glyphCount"], 2)

    def test_cursivy_missing_stems_blocks_confirm_before_mutation(self) -> None:
        font = _make_font(complete_stems=False)
        original_paths = list(font.glyphs["a"].layers["italic"].paths)
        module, filter_obj = self._load_module(font)

        payload = module._apply_italic_first_pass_impl(
            source_master_id="roman",
            target_master_id="italic",
            scope="glyph_names",
            glyph_names=["a"],
            slant_mode="cursivy",
            confirm=True,
        )

        self.assertFalse(payload["ok"])
        self.assertEqual(font.glyphs["a"].layers["italic"].paths, original_paths)
        self.assertEqual(filter_obj.calls, [])

    def test_dry_run_does_not_mutate(self) -> None:
        font = _make_font()
        target_layer = font.glyphs["a"].layers["italic"]
        original_width = target_layer.width
        original_path_count = len(target_layer.paths)
        module, filter_obj = self._load_module(font)

        payload = module._apply_italic_first_pass_impl(
            source_master_id="roman",
            target_master_id="italic",
            scope="glyph_names",
            glyph_names=["a"],
            slant_mode="raw",
            dry_run=True,
        )

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["dryRun"])
        self.assertEqual(target_layer.width, original_width)
        self.assertEqual(len(target_layer.paths), original_path_count)
        self.assertEqual(filter_obj.calls, [])

    def test_confirm_copies_layer_and_invokes_transform_filter(self) -> None:
        font = _make_font()
        target_layer = font.glyphs["b"].layers["italic"]
        module, filter_obj = self._load_module(font)

        payload = module._apply_italic_first_pass_impl(
            source_master_id="roman",
            target_master_id="italic",
            scope="glyph_names",
            glyph_names=["b"],
            slant_mode="cursivy",
            confirm=True,
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(target_layer.width, 510.0)
        self.assertEqual(len(target_layer.paths), 1)
        self.assertEqual(len(font.glyphs["b"].layers.backups), 1)
        self.assertEqual(len(filter_obj.calls), 1)
        self.assertEqual(filter_obj.calls[0]["args"]["Slant"], 12.0)
        self.assertEqual(filter_obj.calls[0]["args"]["SlantCorrection"], 1)
        self.assertEqual(filter_obj.calls[0]["args"]["Origin"], 3)

    def test_strict_compatibility_blocks_incompatible_target_layer(self) -> None:
        font = _make_font()
        module, _filter = self._load_module(font)

        payload = module._review_italic_first_pass_impl(
            source_master_id="roman",
            target_master_id="italic",
            scope="glyph_names",
            glyph_names=["a"],
            slant_mode="raw",
            compatibility_mode="strict",
        )

        self.assertTrue(payload["ok"])
        self.assertFalse(payload["readyToApply"])
        self.assertEqual(payload["results"][0]["blockedReasons"], ["strict_compatibility_would_replace_incompatible_layer"])

    def test_copy_from_source_policy_reports_source_stems(self) -> None:
        font = _make_font(complete_stems=False)
        module, _filter = self._load_module(font)

        payload = module._review_italic_first_pass_impl(
            source_master_id="roman",
            target_master_id="italic",
            scope="glyph_names",
            glyph_names=["b"],
            stem_policy="copy_from_source",
        )

        self.assertTrue(payload["ok"])
        self.assertFalse(payload["stemReview"]["readyForCursivy"])
        self.assertTrue(payload["sourceStemReview"]["readyForCursivy"])


if __name__ == "__main__":
    unittest.main()
