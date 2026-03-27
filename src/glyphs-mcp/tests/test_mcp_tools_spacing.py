"""Regression tests for MCP spacing tools."""

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
        / "mcp_tools_spacing.py"
    )


class _FakeMCP:
    def tool(self, *args, **kwargs):
        def decorator(fn):
            return fn

        return decorator


class McpToolsSpacingTests(unittest.TestCase):
    def _load_module(self):
        layer = types.SimpleNamespace(width=300.0, leftSideBearing=40.0, rightSideBearing=60.0)
        glyph = types.SimpleNamespace(name="A", layers={"m1": layer})
        master = types.SimpleNamespace(id="m1", name="Master 1", xHeight=500, italicAngle=0.0)
        font = types.SimpleNamespace(glyphs={"A": glyph}, masters=[master])

        glyphs_module = types.SimpleNamespace(Glyphs=types.SimpleNamespace(fonts=[font], font=font), GSGuide=type("GSGuide", (), {}))
        helpers_module = types.SimpleNamespace(
            _custom_parameter=lambda obj, key, default=None: default,
            _get_left_sidebearing=lambda layer_obj: layer_obj.leftSideBearing,
            _get_right_sidebearing=lambda layer_obj: layer_obj.rightSideBearing,
            _safe_json=lambda payload: json.dumps(payload),
            _set_sidebearing=lambda layer_obj, attr_name, legacy_attr, value: setattr(layer_obj, attr_name, float(value)) or True,
            _spacing_selected_glyph_names_for_font=lambda font_obj: ["A"],
        )
        spacing_engine = types.SimpleNamespace(
            DEFAULTS={"area": 400.0, "depth": 15.0, "over": 0.0, "frequency": 5.0},
            SPACING_PARAM_FIELDS=["area", "depth", "over", "frequency"],
            SPACING_PARAM_KEYS_CANONICAL={"area": "a", "depth": "d", "over": "o", "frequency": "f"},
            SPACING_PARAM_KEYS_GMCP_LEGACY={"area": "ga", "depth": "gd", "over": "go", "frequency": "gf"},
            SPACING_PARAM_KEYS_PARAM_LEGACY={"area": "pa", "depth": "pd", "over": "po", "frequency": "pf"},
            resolve_param_precedence=lambda **kwargs: kwargs.get("fallback"),
            compute_suggestion_for_layer=lambda **kwargs: {
                "status": "ok",
                "glyphName": "A",
                "masterId": "m1",
                "masterName": "Master 1",
                "current": {"width": 300, "lsb": 40, "rsb": 60},
                "suggested": {"lsb": 50, "rsb": 70, "width": 320},
                "measured": {"lFullExtreme": 10.0, "rFullExtreme": 210.0},
                "warnings": [],
            },
            clamp_suggestion=lambda current, suggested, clamp: (dict(suggested), []),
        )

        module_name = "glyphs_mcp_test_mcp_tools_spacing"
        spec = importlib.util.spec_from_file_location(module_name, _module_path())
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(
            sys.modules,
            {
                "GlyphsApp": glyphs_module,
                "mcp_runtime": types.SimpleNamespace(mcp=_FakeMCP()),
                "mcp_tool_helpers": helpers_module,
                "spacing_engine": spacing_engine,
            },
        ):
            sys.modules.pop(module_name, None)
            assert spec.loader is not None
            spec.loader.exec_module(module)
        return module, layer

    def test_apply_spacing_confirm_uses_sidebearing_helpers(self) -> None:
        module, layer = self._load_module()

        payload = json.loads(
            asyncio.run(
                module.apply_spacing(
                    font_index=0,
                    glyph_names=["A"],
                    master_id="m1",
                    confirm=True,
                )
            )
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["summary"]["appliedCount"], 1)
        self.assertEqual(layer.leftSideBearing, 50.0)
        self.assertEqual(layer.rightSideBearing, 70.0)


if __name__ == "__main__":
    unittest.main()
