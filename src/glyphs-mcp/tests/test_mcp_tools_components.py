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


class McpToolsComponentsTests(unittest.TestCase):
    def _load_module(self):
        layer = types.SimpleNamespace(components=[])
        font = types.SimpleNamespace(
            glyphs={
                "A": types.SimpleNamespace(layers={"m1": layer}),
                "acute": types.SimpleNamespace(unicode="00B4", category="Mark"),
            },
            masters=[types.SimpleNamespace(id="m1")],
        )
        glyphs_module = types.SimpleNamespace(
            Glyphs=types.SimpleNamespace(fonts=[font]),
            GSComponent=_FakeGSComponent,
            GSAnchor=type("GSAnchor", (), {}),
            GSHandle=type("GSHandle", (), {}),
            GSHint=type("GSHint", (), {}),
            GSNode=type("GSNode", (), {}),
            GSPath=type("GSPath", (), {}),
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
                "mcp_tool_helpers": types.SimpleNamespace(_get_component_automatic=lambda component: getattr(component, "automaticAlignment", None)),
            },
        ):
            sys.modules.pop(module_name, None)
            assert spec.loader is not None
            spec.loader.exec_module(module)
        return module, layer

    def test_add_component_to_glyph_disables_auto_alignment_for_explicit_offsets(self) -> None:
        module, layer = self._load_module()

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
        module, layer = self._load_module()

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


if __name__ == "__main__":
    unittest.main()
