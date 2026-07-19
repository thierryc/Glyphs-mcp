"""Regression tests for glyph operation MCP tools."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


def _resources_dir() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Resources"
    )


def _module_path() -> Path:
    return _resources_dir() / "mcp_tools_glyph_ops.py"


class _FakeMCP:
    def tool(self, *args, **kwargs):
        def decorator(fn):
            return fn

        return decorator


class _FakeGSGlyph:
    def __init__(self, *args) -> None:
        if args:
            raise TypeError("GSGlyph() does not accept positional arguments")
        self.name = ""
        self.unicode = None
        self.category = None
        self.subCategory = None


class _FakeLayer:
    def __init__(self, name="Regular", *, width=500, lsb=40, rsb=60) -> None:
        self.name = name
        self.associatedMasterId = "m1"
        self.width = width
        self.leftSideBearing = lsb
        self.rightSideBearing = rsb
        self.components = ["acute"]
        self.anchors = ["top"]

    def setComponents_(self, value) -> None:
        self.components = [] if value is None else value

    def copy(self):
        copied = _FakeLayer(
            self.name,
            width=self.width,
            lsb=self.leftSideBearing,
            rsb=self.rightSideBearing,
        )
        copied.associatedMasterId = self.associatedMasterId
        copied.components = list(self.components)
        copied.anchors = list(self.anchors)
        return copied


class _GeometryFakeLayer(_FakeLayer):
    def __init__(self, name="Regular", *, width=500, lsb=100, rsb=140, shape_width=260) -> None:
        self._width = width
        self._shape_width = shape_width
        super().__init__(name, width=width, lsb=lsb, rsb=rsb)

    @property
    def width(self):
        return self._width

    @width.setter
    def width(self, value):
        self._width = float(value)
        if hasattr(self, "leftSideBearing") and hasattr(self, "_shape_width"):
            self.rightSideBearing = self._width - float(self.leftSideBearing) - float(self._shape_width)


class _FakeLayerCollection(dict):
    def __getitem__(self, key):
        return self.get(key)

    def __iter__(self):
        return iter(self.values())


class _FakeGlyph:
    def __init__(self, name, *, unicode=None, layers=None) -> None:
        self.name = name
        self.unicode = unicode
        self.category = "Letter"
        self.subCategory = "Uppercase"
        self.leftKerningGroup = name
        self.rightKerningGroup = name
        self.export = True
        self.layers = _FakeLayerCollection(layers or {"m1": _FakeLayer()})

    def copy(self):
        copied_layers = _FakeLayerCollection(
            {layer_id: layer.copy() for layer_id, layer in self.layers.items()}
        )
        copied = _FakeGlyph(self.name, unicode=self.unicode, layers=copied_layers)
        copied.category = self.category
        copied.subCategory = self.subCategory
        copied.leftKerningGroup = self.leftKerningGroup
        copied.rightKerningGroup = self.rightKerningGroup
        copied.export = self.export
        return copied


class _FakeGlyphs(dict):
    def __getitem__(self, key):
        return self.get(key)

    def append(self, glyph) -> None:
        self[glyph.name] = glyph


class _IgnoringGlyphs(dict):
    def __getitem__(self, key):
        return self.get(key)

    def append(self, glyph) -> None:
        return None


class McpToolsGlyphOpsTests(unittest.TestCase):
    def _load_module(self, glyphs_collection, *, filepath="/tmp/UnitTestSans.glyphs"):
        resources = str(_resources_dir())
        if resources not in sys.path:
            sys.path.insert(0, resources)

        font = types.SimpleNamespace(
            glyphs=glyphs_collection,
            familyName="Unit Test Sans",
            filepath=filepath,
            masters=[types.SimpleNamespace(id="m1", name="Regular")],
            instances=[],
            formatVersion=3,
            appVersion="3300",
        )
        font.removeGlyph_ = lambda glyph: glyphs_collection.pop(glyph.name, None)
        glyphs_module = types.SimpleNamespace(
            Glyphs=types.SimpleNamespace(fonts=[font], showNotification=lambda *args, **kwargs: None),
            GSGlyph=_FakeGSGlyph,
        )

        module_name = "glyphs_mcp_test_mcp_tools_glyph_ops"
        spec = importlib.util.spec_from_file_location(module_name, _module_path())
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(
            sys.modules,
            {
                "GlyphsApp": glyphs_module,
                "mcp_runtime": types.SimpleNamespace(mcp=_FakeMCP()),
            },
        ):
            sys.modules.pop(module_name, None)
            assert spec.loader is not None
            spec.loader.exec_module(module)
        return module, font

    def test_create_glyph_uses_safe_constructor_fallback(self) -> None:
        module, font = self._load_module(_FakeGlyphs())

        payload = json.loads(
            asyncio.run(
                module.create_glyph(
                    font_index=0,
                    glyph_name="mcpProbe",
                    unicode="E000",
                    category="Letter",
                    sub_category="Private Use",
                )
            )
        )

        self.assertTrue(payload["success"])
        self.assertIn("mcpProbe", font.glyphs)
        self.assertEqual(font.glyphs["mcpProbe"].unicode, "E000")

    def test_create_glyph_fails_when_append_cannot_be_verified(self) -> None:
        module, _font = self._load_module(_IgnoringGlyphs())

        payload = json.loads(
            asyncio.run(module.create_glyph(font_index=0, glyph_name="mcpProbe"))
        )

        self.assertFalse(payload["success"])
        self.assertIn("could not be verified", payload["error"])

    def test_delete_glyph_removes_only_requested_glyph(self) -> None:
        glyphs = _FakeGlyphs({"A": _FakeGlyph("A"), "B": _FakeGlyph("B")})
        module, font = self._load_module(glyphs)

        payload = json.loads(asyncio.run(module.delete_glyph(font_index=0, glyph_name="A")))

        self.assertTrue(payload["success"])
        self.assertNotIn("A", font.glyphs)
        self.assertIn("B", font.glyphs)

    def test_delete_glyph_reports_missing_name_and_missing_glyph(self) -> None:
        module, _font = self._load_module(_FakeGlyphs())

        missing_name = json.loads(asyncio.run(module.delete_glyph(font_index=0)))
        missing_glyph = json.loads(asyncio.run(module.delete_glyph(font_index=0, glyph_name="A")))

        self.assertEqual(missing_name["error"], "Glyph name is required")
        self.assertEqual(missing_glyph["error"], "Glyph 'A' not found")

    def test_update_glyph_properties_mutates_requested_fields_only(self) -> None:
        glyph = _FakeGlyph("A", unicode="0041")
        glyphs = _FakeGlyphs({"A": glyph})
        module, _font = self._load_module(glyphs)

        payload = json.loads(
            asyncio.run(
                module.update_glyph_properties(
                    font_index=0,
                    glyph_name="A",
                    unicode="00C0",
                    left_kerning_group="A.left",
                    export=False,
                )
            )
        )

        self.assertTrue(payload["success"])
        self.assertEqual(glyph.unicode, "00C0")
        self.assertEqual(glyph.category, "Letter")
        self.assertEqual(glyph.leftKerningGroup, "A.left")
        self.assertEqual(glyph.rightKerningGroup, "A")
        self.assertFalse(glyph.export)
        self.assertEqual(payload["glyph"]["unicode"], "00C0")

    def test_copy_glyph_creates_target_and_can_strip_components_and_anchors(self) -> None:
        source = _FakeGlyph("A", unicode="0041")
        glyphs = _FakeGlyphs({"A": source})
        module, font = self._load_module(glyphs)

        payload = json.loads(
            asyncio.run(
                module.copy_glyph(
                    font_index=0,
                    source_glyph="A",
                    target_glyph="A.mcpCopy",
                    copy_components=False,
                    copy_anchors=False,
                )
            )
        )

        self.assertTrue(payload["success"])
        self.assertIn("A.mcpCopy", font.glyphs)
        copied = font.glyphs["A.mcpCopy"]
        self.assertEqual(copied.unicode, "0041")
        self.assertEqual(copied.layers["m1"].components, [])
        self.assertEqual(copied.layers["m1"].anchors, [])

    def test_copy_glyph_replaces_existing_target(self) -> None:
        source = _FakeGlyph("A")
        existing = _FakeGlyph("A.copy")
        glyphs = _FakeGlyphs({"A": source, "A.copy": existing})
        module, font = self._load_module(glyphs)

        payload = json.loads(
            asyncio.run(module.copy_glyph(font_index=0, source_glyph="A", target_glyph="A.copy"))
        )

        self.assertTrue(payload["success"])
        self.assertIsNot(font.glyphs["A.copy"], existing)
        self.assertEqual(font.glyphs["A.copy"].name, "A.copy")

    def test_copy_glyph_reports_missing_source(self) -> None:
        module, _font = self._load_module(_FakeGlyphs())

        payload = json.loads(
            asyncio.run(module.copy_glyph(font_index=0, source_glyph="A", target_glyph="A.copy"))
        )

        self.assertEqual(payload["error"], "Source glyph 'A' not found")

    def test_update_glyph_metrics_updates_selected_master(self) -> None:
        layer = _FakeLayer(width=500, lsb=40, rsb=60)
        glyph = _FakeGlyph("A", layers={"m1": layer})
        glyphs = _FakeGlyphs({"A": glyph})
        module, _font = self._load_module(glyphs)

        payload = json.loads(
            asyncio.run(
                module.update_glyph_metrics(
                    font_index=0,
                    glyph_name="A",
                    master_id="m1",
                    width=620,
                    left_sidebearing=55,
                    right_sidebearing=65,
                )
            )
        )

        self.assertTrue(payload["success"])
        self.assertEqual(layer.width, 620)
        self.assertEqual(layer.leftSideBearing, 55)
        self.assertEqual(layer.rightSideBearing, 65)
        self.assertEqual(payload["metrics"][0]["width"], 620)

    def test_update_glyph_metrics_reports_readback_mismatch(self) -> None:
        layer = _GeometryFakeLayer(width=500, lsb=100, rsb=140, shape_width=260)
        glyph = _FakeGlyph("A", layers={"m1": layer})
        glyphs = _FakeGlyphs({"A": glyph})
        module, _font = self._load_module(glyphs)

        payload = json.loads(
            asyncio.run(
                module.update_glyph_metrics(
                    font_index=0,
                    glyph_name="A",
                    master_id="m1",
                    width=500,
                    left_sidebearing=120,
                    right_sidebearing=130,
                )
            )
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["metrics"][0]["rightSideBearing"], 120.0)
        self.assertIn("warnings", payload)
        self.assertIn("right_sidebearing requested 130", payload["warnings"][0]["messages"][0])

    def test_update_glyph_metrics_reports_missing_master(self) -> None:
        module, _font = self._load_module(_FakeGlyphs({"A": _FakeGlyph("A")}))

        payload = json.loads(
            asyncio.run(module.update_glyph_metrics(font_index=0, glyph_name="A", master_id="missing"))
        )

        self.assertEqual(payload["error"], "Master ID 'missing' not found")

    def test_save_font_uses_mocked_save_helper_for_existing_path(self) -> None:
        module, _font = self._load_module(_FakeGlyphs())
        with mock.patch.object(module, "_save_font_on_main_thread", return_value="/tmp/UnitTestSans.glyphs") as save:
            payload = json.loads(asyncio.run(module.save_font(font_index=0)))

        self.assertTrue(payload["success"])
        self.assertEqual(payload["path"], "/tmp/UnitTestSans.glyphs")
        self.assertEqual(payload["formatVersionBefore"], 3)
        self.assertEqual(payload["formatVersionAfter"], 3)
        self.assertEqual(payload["formatVersion"], 3)
        save.assert_called_once_with(mock.ANY, None)

    def test_save_font_uses_mocked_save_helper_for_save_as_path(self) -> None:
        module, _font = self._load_module(_FakeGlyphs())
        with mock.patch.object(module, "_save_font_on_main_thread", return_value="/tmp/copy.glyphs") as save:
            payload = json.loads(asyncio.run(module.save_font(font_index=0, path="/tmp/copy.glyphs")))

        self.assertTrue(payload["success"])
        self.assertEqual(payload["path"], "/tmp/copy.glyphs")
        save.assert_called_once_with(mock.ANY, "/tmp/copy.glyphs")

    def test_save_font_rejects_unsaved_font_without_path(self) -> None:
        module, _font = self._load_module(_FakeGlyphs(), filepath=None)

        payload = json.loads(asyncio.run(module.save_font(font_index=0)))

        self.assertEqual(payload["error"], "No file path specified and font has not been saved before")


if __name__ == "__main__":
    unittest.main()
