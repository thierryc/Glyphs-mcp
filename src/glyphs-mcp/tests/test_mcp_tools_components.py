"""Regression tests for MCP component tool wrappers."""

from __future__ import annotations

import asyncio
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
        / "mcp_tools_components.py"
    )


class _FakeMCP:
    def tool(self, *args, **kwargs):
        def decorator(fn):
            return fn

        return decorator


class _FakeGSComponent:
    def __init__(self, component_name: str) -> None:
        self.componentName = component_name
        self.transform = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
        self.automaticAlignment = True


class _FakeGSNode:
    def __init__(self, x=0, y=0, *, selected=False, node_type="line") -> None:
        self.position = (x, y)
        self.selected = selected
        self.type = node_type


class _FakeGSPath:
    def __init__(self, nodes=None) -> None:
        self.nodes = list(nodes or [])


class _FakeGSHint:
    pass


class _FakeGSAnchor:
    def __init__(self) -> None:
        self.name = ""
        self.position = None


class _FakeLayer:
    def __init__(self, master_id="m1", *, selected_node=False) -> None:
        self.shapes = []
        self._components_override = None
        self.anchors = {}
        self.name = None
        self.associatedMasterId = master_id
        node = _FakeGSNode(100, 200, selected=selected_node)
        self.paths = [_FakeGSPath([node, _FakeGSNode(200, 200)])]
        self.selection = [node] if selected_node else []
        self.hints = []

    @property
    def components(self):
        if self._components_override is not None:
            return self._components_override
        return [shape for shape in self.shapes if isinstance(shape, _FakeGSComponent)]

    @components.setter
    def components(self, value):
        self._components_override = value


class _FakeGlyphCollection:
    def __init__(self, glyphs) -> None:
        self._glyphs = {glyph.name: glyph for glyph in glyphs}

    def __iter__(self):
        return iter(self._glyphs.values())

    def __getitem__(self, key):
        return self._glyphs.get(key)


class _FakeLayerCollection(dict):
    def __getitem__(self, key):
        return self.get(key)


def _resolve_font_by_index(glyphs, font_index):
    fonts = list(getattr(glyphs, "fonts", []) or [])
    index = int(font_index)
    if index < 0 or index >= len(fonts):
        return None, fonts
    return fonts[index], fonts


def _font_resolution_error(font_index, fonts=None, ok_key=None):
    payload = {"error": "Font index out of range", "fontIndex": font_index, "availableFontCount": len(fonts or [])}
    if ok_key == "success":
        payload["success"] = False
    return payload


def _layer_components(layer):
    return [
        shape
        for shape in getattr(layer, "shapes", [])
        if getattr(shape, "componentName", None) is not None
    ]


class McpToolsComponentsTests(unittest.TestCase):
    def _load_module(self):
        layer = _FakeLayer("m1", selected_node=True)
        layer2 = _FakeLayer("m2")
        glyph_a = types.SimpleNamespace(
            name="A",
            unicode="0041",
            layers=_FakeLayerCollection({"m1": layer, "m2": layer2}),
        )
        layer.parent = glyph_a
        layer2.parent = glyph_a
        glyph_acute = types.SimpleNamespace(
            name="acute",
            unicode="00B4",
            category="Mark",
            layers={},
        )
        corner = types.SimpleNamespace(name="_corner.inktrap", unicode=None, category="Corner", layers={})
        font = types.SimpleNamespace(
            familyName="Component Sans",
            filepath="/tmp/ComponentSans.glyphs",
            glyphs=_FakeGlyphCollection([glyph_a, glyph_acute, corner]),
            masters=[
                types.SimpleNamespace(id="m1", name="Regular"),
                types.SimpleNamespace(id="m2", name="Bold"),
            ],
            selectedLayers=[layer],
        )
        glyphs_module = types.SimpleNamespace(
            Glyphs=types.SimpleNamespace(fonts=[font], font=font),
            GSComponent=_FakeGSComponent,
            GSAnchor=_FakeGSAnchor,
            GSHandle=type("GSHandle", (), {}),
            GSHint=_FakeGSHint,
            GSNode=_FakeGSNode,
            GSPath=_FakeGSPath,
            CORNER=0,
        )
        module_name = "glyphs_mcp_test_mcp_tools_components"
        spec = importlib.util.spec_from_file_location(module_name, _module_path())
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(
            sys.modules,
            {
                "GlyphsApp": glyphs_module,
                "mcp_runtime": types.SimpleNamespace(mcp=_FakeMCP()),
                "mcp_tool_helpers": types.SimpleNamespace(
                    _active_font=lambda glyphs: getattr(glyphs, "font", None),
                    _append_layer_anchor=lambda layer_obj, anchor: layer_obj.anchors.__setitem__(anchor.name, anchor) is None or True,
                    _append_layer_shape=lambda layer_obj, shape: layer_obj.shapes.append(shape) is None or True,
                    _component_transform_values=lambda component: list(getattr(component, "transform", (1, 0, 0, 1, 0, 0))),
                    _font_resolution_error=_font_resolution_error,
                    _get_component_automatic=lambda component: getattr(component, "automaticAlignment", None),
                    _layer_components=_layer_components,
                    _layer_display_name=lambda _font, _layer, _master_id=None: "Regular",
                    _new_anchor=lambda _GSAnchor, name, x, y: types.SimpleNamespace(name=name, position=(float(x), float(y))),
                    _resolve_font_by_index=_resolve_font_by_index,
                ),
            },
        ):
            sys.modules.pop(module_name, None)
            assert spec.loader is not None
            spec.loader.exec_module(module)
        return module, layer, font

    def test_add_component_to_glyph_disables_auto_alignment_for_explicit_offsets(self) -> None:
        module, layer, _font = self._load_module()

        payload = json.loads(
            asyncio.run(
                module.add_component_to_glyph(
                    font_index=0,
                    glyph_name="A",
                    component_name="acute",
                    master_id="m1",
                    x_offset=25,
                    y_offset=10,
                )
            )
        )

        self.assertTrue(payload["success"])
        self.assertEqual(layer.components[0].transform, (1, 0, 0, 1, 25, 10))
        self.assertFalse(layer.components[0].automaticAlignment)

    def test_add_component_to_glyph_keeps_auto_alignment_for_default_transform(self) -> None:
        module, layer, _font = self._load_module()

        payload = json.loads(
            asyncio.run(
                module.add_component_to_glyph(
                    font_index=0,
                    glyph_name="A",
                    component_name="acute",
                    master_id="m1",
                )
            )
        )

        self.assertTrue(payload["success"])
        self.assertTrue(layer.components[0].automaticAlignment)

    def test_add_component_to_glyph_fails_when_readback_cannot_verify_write(self) -> None:
        module, _layer, _font = self._load_module()
        module._append_layer_shape = lambda _layer_obj, _shape: True
        module._layer_components = lambda _layer_obj: []

        payload = json.loads(
            asyncio.run(
                module.add_component_to_glyph(
                    font_index=0,
                    glyph_name="A",
                    component_name="acute",
                    master_id="m1",
                )
            )
        )

        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"], "Component write could not be verified after append")

    def test_add_anchor_to_glyph_uses_helper_anchor_insertion(self) -> None:
        module, layer, _font = self._load_module()

        payload = json.loads(
            asyncio.run(
                module.add_anchor_to_glyph(
                    font_index=0,
                    glyph_name="A",
                    anchor_name="top",
                    master_id="m1",
                    x=100,
                    y=200,
                )
            )
        )

        self.assertTrue(payload["success"])
        self.assertEqual(layer.anchors["top"].position, (100.0, 200.0))

    def test_get_glyph_components_reports_component_details(self) -> None:
        module, layer, _font = self._load_module()
        class HostileComponents:
            def __iter__(self):
                raise AssertionError("layer.components must not be iterated")

            def __len__(self):
                raise AssertionError("layer.components must not be sized")

        component = _FakeGSComponent("acute")
        component.transform = (1.0, 0.0, 0.0, 1.0, 25.0, 10.0)
        component.automaticAlignment = False
        layer.shapes.append(component)
        layer.components = HostileComponents()

        payload = json.loads(
            asyncio.run(
                module.get_glyph_components(
                    font_index=0,
                    glyph_name="A",
                    master_id="m1",
                )
            )
        )

        self.assertEqual(payload["glyphName"], "A")
        self.assertEqual(payload["totalLayers"], 1)
        layer_payload = payload["layers"][0]
        self.assertEqual(layer_payload["masterId"], "m1")
        self.assertEqual(layer_payload["componentCount"], 1)
        component_payload = layer_payload["components"][0]
        self.assertEqual(component_payload["name"], "acute")
        self.assertEqual(component_payload["transform"]["xOffset"], 25.0)
        self.assertFalse(component_payload["automatic"])
        self.assertTrue(component_payload["componentGlyphExists"])
        self.assertEqual(component_payload["componentUnicode"], "00B4")

    def test_get_glyph_components_reports_missing_glyph_and_master(self) -> None:
        module, _layer, _font = self._load_module()

        missing_glyph = json.loads(
            asyncio.run(module.get_glyph_components(font_index=0, glyph_name="missing"))
        )
        missing_master = json.loads(
            asyncio.run(module.get_glyph_components(font_index=0, glyph_name="A", master_id="missing"))
        )

        self.assertEqual(missing_glyph["error"], "Glyph 'missing' not found")
        self.assertEqual(missing_master["error"], "Master ID 'missing' not found")

    def test_add_corner_to_all_masters_reports_no_active_font(self) -> None:
        module, _layer, _font = self._load_module()
        module.Glyphs.font = None

        payload = json.loads(asyncio.run(module.add_corner_to_all_masters(_corner_name="_corner.inktrap")))

        self.assertEqual(payload["error"], "No font is currently active")

    def test_add_corner_to_all_masters_validates_corner_name(self) -> None:
        module, _layer, _font = self._load_module()

        payload = json.loads(asyncio.run(module.add_corner_to_all_masters(_corner_name="inktrap")))

        self.assertEqual(payload["error"], "Invalid _corner_name (must start with '_corner.')")
        self.assertIn("_corner.inktrap", payload["availableCorners"])

    def test_add_corner_to_all_masters_adds_hints_to_matching_master_layers(self) -> None:
        module, layer, font = self._load_module()

        payload = json.loads(
            asyncio.run(
                module.add_corner_to_all_masters(
                    _corner_name="_corner.inktrap",
                    _alignment="right",
                )
            )
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["totalAdded"], 2)
        self.assertEqual(payload["alignmentApplied"], 1)
        self.assertEqual(len(layer.hints), 1)
        self.assertEqual(len(font.glyphs["A"].layers["m2"].hints), 1)
        self.assertEqual(layer.hints[0].name, "_corner.inktrap")
        self.assertIs(layer.hints[0].originNode, layer.paths[0].nodes[0])
        self.assertEqual(layer.hints[0].options, 1)


if __name__ == "__main__":
    unittest.main()
