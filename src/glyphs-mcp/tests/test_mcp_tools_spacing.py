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


class _FakeBounds:
    def __init__(self, y=0, height=500) -> None:
        self.origin = types.SimpleNamespace(y=y)
        self.size = types.SimpleNamespace(height=height)


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


class McpToolsSpacingTests(unittest.TestCase):
    def _load_module(self):
        layer = types.SimpleNamespace(
            width=300.0,
            leftSideBearing=40.0,
            rightSideBearing=60.0,
            guides=[],
            bounds=_FakeBounds(y=0, height=500),
        )
        glyph = types.SimpleNamespace(name="A", layers={"m1": layer})
        master = types.SimpleNamespace(
            id="m1",
            name="Master 1",
            xHeight=500,
            italicAngle=0.0,
            customParameters={},
        )
        font = types.SimpleNamespace(
            glyphs={"A": glyph},
            masters=[master],
            selectedFontMaster=master,
            selectedLayers=[layer],
            customParameters={},
        )

        glyphs_module = types.SimpleNamespace(Glyphs=types.SimpleNamespace(fonts=[font], font=font), GSGuide=type("GSGuide", (), {}))
        custom_parameter = lambda obj, key, default=None: getattr(obj, "customParameters", {}).get(key, default)
        def _set_layer_metrics(layer_obj, width=None, left_sidebearing=None, right_sidebearing=None):
            if left_sidebearing is not None:
                layer_obj.leftSideBearing = float(left_sidebearing)
            if right_sidebearing is not None:
                layer_obj.rightSideBearing = float(right_sidebearing)
            if width is not None:
                layer_obj.width = float(width)
            return True

        helpers_module = types.SimpleNamespace(
            _custom_parameter=custom_parameter,
            _font_resolution_error=_font_resolution_error,
            _get_left_sidebearing=lambda layer_obj: layer_obj.leftSideBearing,
            _get_right_sidebearing=lambda layer_obj: layer_obj.rightSideBearing,
            _is_active_font=lambda glyphs, font_obj: getattr(glyphs, "font", None) is font_obj,
            _resolve_font_by_index=_resolve_font_by_index,
            _safe_json=lambda payload: json.dumps(payload),
            _set_layer_metrics=_set_layer_metrics,
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
                "reference": {"yMin": 0.0, "yMax": 500.0, "overUnits": 0.0},
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
        return module, layer, font, master

    def test_apply_spacing_confirm_uses_sidebearing_helpers(self) -> None:
        module, layer, _font, _master = self._load_module()

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

    def test_set_spacing_params_dry_run_reports_without_mutating(self) -> None:
        module, _layer, font, _master = self._load_module()

        payload = json.loads(
            asyncio.run(
                module.set_spacing_params(
                    font_index=0,
                    scope="font",
                    params={"area": 420, "depth": None},
                    dry_run=True,
                )
            )
        )

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["dryRun"])
        self.assertEqual(payload["scopeApplied"], "font")
        self.assertEqual(len(payload["changed"]), 2)
        self.assertEqual(font.customParameters, {})

    def test_set_spacing_params_sets_and_deletes_custom_parameters(self) -> None:
        module, _layer, font, _master = self._load_module()
        font.customParameters["d"] = 15.0

        payload = json.loads(
            asyncio.run(
                module.set_spacing_params(
                    font_index=0,
                    scope="font",
                    params={"area": "450", "depth": None},
                )
            )
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(font.customParameters["a"], 450.0)
        self.assertNotIn("d", font.customParameters)
        self.assertEqual(payload["effectiveReadback"][0]["values"]["area"]["canonicalValue"], 450.0)

    def test_set_spacing_params_reports_invalid_scope(self) -> None:
        module, _layer, _font, _master = self._load_module()

        payload = json.loads(asyncio.run(module.set_spacing_params(font_index=0, scope="bad", params={})))

        self.assertFalse(payload["ok"])
        self.assertIn("Invalid scope", payload["error"])

    def test_set_spacing_guides_dry_run_reports_without_mutating(self) -> None:
        module, layer, _font, _master = self._load_module()

        payload = json.loads(
            asyncio.run(
                module.set_spacing_guides(
                    font_index=0,
                    glyph_names=["A"],
                    master_scope="master",
                    master_id="m1",
                    reference_glyph="*",
                    style="band",
                    dry_run=True,
                )
            )
        )

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["dryRun"])
        self.assertEqual(payload["summary"]["addedCount"], 2)
        self.assertEqual(layer.guides, [])

    def test_set_spacing_guides_adds_and_clears_managed_guides(self) -> None:
        module, layer, _font, _master = self._load_module()

        added = json.loads(
            asyncio.run(
                module.set_spacing_guides(
                    font_index=0,
                    glyph_names=["A"],
                    master_scope="master",
                    master_id="m1",
                    reference_glyph="*",
                    style="band",
                )
            )
        )
        cleared = json.loads(
            asyncio.run(
                module.set_spacing_guides(
                    font_index=0,
                    glyph_names=["A"],
                    master_scope="master",
                    master_id="m1",
                    mode="clear",
                    reference_glyph="*",
                    style="band",
                )
            )
        )

        self.assertTrue(added["ok"])
        self.assertEqual(added["summary"]["addedCount"], 2)
        self.assertEqual(len(cleared["results"][0]["removed"]), 2)
        self.assertEqual(layer.guides, [])


if __name__ == "__main__":
    unittest.main()
