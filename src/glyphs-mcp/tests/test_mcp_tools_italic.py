"""Regression tests for italic first-pass MCP tools."""

from __future__ import annotations

import importlib.util
import json
import math
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
    def __init__(self, node_types, transformed=False):
        self.nodes = [_FakeNode(t) for t in node_types]
        self.transformed = transformed

    def copy(self):
        return _FakePath([node.type for node in self.nodes], transformed=self.transformed)


class _FakeComponent:
    def __init__(self, component_name, transform=None, component_master_id="italic"):
        self.componentName = component_name
        self.name = component_name
        self.componentMasterId = component_master_id
        self.transform = list(transform or [1, 0, 0, 1, 10, 20])
        self.position = types.SimpleNamespace(x=self.transform[4], y=self.transform[5])
        self.scale = types.SimpleNamespace(x=1.0, y=1.0)
        self.rotation = 0.0
        self.slant = 0.0

    def copy(self):
        return _FakeComponent(self.componentName, transform=list(self.transform), component_master_id=self.componentMasterId)


class _FakeAnchor:
    def __init__(self, name, x=100, y=200):
        self.name = name
        self.position = types.SimpleNamespace(x=x, y=y)

    def copy(self):
        return _FakeAnchor(self.name, self.position.x, self.position.y)


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
        layer.components = [component.copy() for component in self.components]
        layer.anchors = [anchor.copy() for anchor in self.anchors]
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
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def filter(self, layer, include, args):
        self.calls.append(
            {
                "layer": layer,
                "include": include,
                "args": dict(args),
                "pathCount": len(layer.paths),
                "componentCount": len(layer.components),
                "anchorCount": len(layer.anchors),
            }
        )
        if self.fail:
            raise RuntimeError("transform failed")
        for path in layer.paths:
            path.transformed = True
        for component in layer.components:
            component.transform = [2, 0, 1, 2, 999, 999]
        for anchor in layer.anchors:
            anchor.position.x = 999


class GlyphsFilterTransformationsNoFilter:
    pass


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
        fonts = font if isinstance(font, list) else [font]
        glyphs_module = types.SimpleNamespace(
            Glyphs=types.SimpleNamespace(fonts=fonts, font=fonts[0], filters=[filter_obj]),
            GSGlyph=FakeGSGlyph,
            GSMetric=lambda: _FakeStem("", False),
        )
        helpers_module = types.SimpleNamespace(
            _clear_layer_paths=lambda layer: layer.paths.clear(),
            _coerce_numeric=lambda value: None if value is None else float(value),
            _font_resolution_error=_font_resolution_error,
            _get_left_sidebearing=lambda layer: getattr(layer, "leftSideBearing", None),
            _get_right_sidebearing=lambda layer: getattr(layer, "rightSideBearing", None),
            _resolve_font_by_index=_resolve_font_by_index,
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
        self.assertTrue(target_layer.paths[0].transformed)

    def test_confirm_copies_live_components_but_skews_only_paths(self) -> None:
        font = _make_font()
        source_layer = font.glyphs["b"].layers["roman"]
        target_layer = font.glyphs["b"].layers["italic"]
        source_component = _FakeComponent("acute", transform=[1, 0, 0, 1, 35, 40], component_master_id="italic")
        baseline_component = _FakeComponent("dotaccent", transform=[1, 0, 0, 1, 12, 0], component_master_id="italic")
        source_anchor = _FakeAnchor("top", 120, 700)
        source_layer.components = [source_component, baseline_component]
        source_layer.anchors = [source_anchor]
        target_layer.components = [_FakeComponent("old", transform=[1, 0, 0, 1, 1, 2])]
        target_layer.anchors = [_FakeAnchor("old", 1, 2)]
        module, filter_obj = self._load_module(font)

        payload = module._apply_italic_first_pass_impl(
            source_master_id="roman",
            target_master_id="italic",
            scope="glyph_names",
            glyph_names=["b"],
            slant_mode="raw",
            confirm=True,
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(filter_obj.calls[0]["pathCount"], 1)
        self.assertEqual(filter_obj.calls[0]["componentCount"], 0)
        self.assertEqual(filter_obj.calls[0]["anchorCount"], 0)
        self.assertTrue(target_layer.paths[0].transformed)
        self.assertEqual(len(target_layer.components), 2)
        self.assertIsNot(target_layer.components[0], source_component)
        expected_x = 35 + math.tan(math.radians(12.0)) * 40
        self.assertEqual(target_layer.components[0].componentName, "acute")
        self.assertEqual(target_layer.components[0].componentMasterId, "italic")
        self.assertAlmostEqual(target_layer.components[0].transform[4], expected_x)
        self.assertEqual(target_layer.components[0].transform[5], 40)
        self.assertAlmostEqual(target_layer.components[0].position.x, expected_x)
        self.assertEqual(target_layer.components[1].componentName, "dotaccent")
        self.assertEqual(target_layer.components[1].transform, [1, 0, 0, 1, 12, 0])
        self.assertEqual(len(target_layer.anchors), 1)
        self.assertIsNot(target_layer.anchors[0], source_anchor)
        self.assertEqual(target_layer.anchors[0].name, "top")
        self.assertEqual(target_layer.anchors[0].position.x, 120)
        self.assertEqual(payload["results"][0]["componentsPreserved"], True)
        self.assertEqual(payload["results"][0]["componentPositioning"]["adjustedCount"], 1)
        self.assertEqual(payload["results"][0]["componentPositioning"]["baselineCount"], 1)
        self.assertEqual(payload["results"][0]["componentTransformPolicy"], "copy_components_preserve_unskewed")

    def test_transform_failure_leaves_existing_target_unchanged(self) -> None:
        font = _make_font()
        source_layer = font.glyphs["b"].layers["roman"]
        target_layer = font.glyphs["b"].layers["italic"]
        source_layer.components = [_FakeComponent("acute")]
        target_component = _FakeComponent("existing", transform=[1, 0, 0, 1, 5, 6])
        target_layer.components = [target_component]
        original_paths = list(target_layer.paths)
        original_components = list(target_layer.components)
        original_width = target_layer.width
        module, filter_obj = self._load_module(font, filter_obj=GlyphsFilterTransformations(fail=True))

        payload = module._apply_italic_first_pass_impl(
            source_master_id="roman",
            target_master_id="italic",
            scope="glyph_names",
            glyph_names=["b"],
            slant_mode="raw",
            confirm=True,
        )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["results"][0]["reason"], "transform_failed")
        self.assertEqual(len(filter_obj.calls), 1)
        self.assertEqual(target_layer.paths, original_paths)
        self.assertEqual(target_layer.components, original_components)
        self.assertEqual(target_layer.width, original_width)
        self.assertEqual(len(font.glyphs["b"].layers.backups), 0)
        self.assertEqual(font.glyphs["b"].undo_depth, 0)

    def test_transform_failure_does_not_create_missing_target_glyph(self) -> None:
        source_font = _make_font()
        target_font = _make_font()
        target_font.glyphs = _FakeGlyphs({})
        target_font.selectedLayers = []
        module, _filter = self._load_module([source_font, target_font], filter_obj=GlyphsFilterTransformations(fail=True))

        payload = module._apply_italic_first_pass_impl(
            source_font_index=0,
            target_font_index=1,
            source_master_id="roman",
            target_master_id="italic",
            scope="glyph_names",
            glyph_names=["b"],
            slant_mode="raw",
            confirm=True,
        )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["results"][0]["reason"], "transform_failed")
        self.assertNotIn("b", target_font.glyphs)

    def test_missing_transform_filter_method_fails_without_mutation(self) -> None:
        font = _make_font()
        target_layer = font.glyphs["b"].layers["italic"]
        original_paths = list(target_layer.paths)
        original_width = target_layer.width
        module, _filter = self._load_module(font, filter_obj=GlyphsFilterTransformationsNoFilter())

        payload = module._apply_italic_first_pass_impl(
            source_master_id="roman",
            target_master_id="italic",
            scope="glyph_names",
            glyph_names=["b"],
            slant_mode="raw",
            confirm=True,
        )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["results"][0]["reason"], "transform_failed")
        self.assertIn("no callable filter method", payload["results"][0]["transform"]["error"])
        self.assertEqual(target_layer.paths, original_paths)
        self.assertEqual(target_layer.width, original_width)
        self.assertEqual(len(font.glyphs["b"].layers.backups), 0)

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
