"""Regression tests for compensated tuning MCP tool wrappers."""

from __future__ import annotations

import importlib.util
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
        / "mcp_tools_compensated_tuning.py"
    )


class _FakeFunctionTool:
    def __init__(self, fn):
        self.fn = fn


class _FakeMCP:
    def tool(self, *args, **kwargs):
        def decorator(fn):
            return _FakeFunctionTool(fn)

        return decorator


class _FakeGSNode:
    def __init__(self) -> None:
        self.position = (0.0, 0.0)
        self.type = "line"
        self.smooth = False


class _FakeGSPath:
    def __init__(self) -> None:
        self.nodes = []
        self.closed = True


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


class CompensatedTuningToolWrapperTests(unittest.TestCase):
    def _load_module(self, font) -> types.ModuleType:
        glyphs_module = types.SimpleNamespace(
            Glyphs=types.SimpleNamespace(fonts=[font], font=font),
            GSNode=_FakeGSNode,
            GSPath=_FakeGSPath,
        )
        helpers_module = types.SimpleNamespace(
            _clear_layer_paths=lambda layer: getattr(layer, "paths", []).clear(),
            _coerce_numeric=lambda value: None if value is None else float(value),
            _font_resolution_error=_font_resolution_error,
            _is_active_font=lambda glyphs, current_font: getattr(glyphs, "font", None) is current_font,
            _replace_layer_paths_and_metrics=lambda layer, paths, width=None, **_kwargs: (
                setattr(layer, "paths", list(paths or [])),
                setattr(layer, "width", float(width)) if width is not None else None,
                {"ok": True, "pathCount": len(paths or []), "nodeCount": 0},
            )[-1],
            _resolve_font_by_index=_resolve_font_by_index,
            _safe_attr=lambda obj, attr: getattr(obj, attr, None),
            _safe_json=lambda payload: payload,
            _spacing_selected_glyph_names_for_font=lambda current_font: list(current_font.glyphs.keys()),
        )
        engine_module = types.SimpleNamespace(
            keep_stroke_to_exponent_a=lambda value: value,
            clamp=lambda value, lower, upper: min(max(value, lower), upper),
            compute_q=lambda scale, b, a: 1.0,
            clamp_q=lambda value: value,
            italic_shear=lambda angle: 0.0,
            transform_point=lambda **kwargs: (kwargs["xr"], kwargs["yr"]),
            units=lambda value, round_units=True: value,
            interpolate_metric=lambda mr, mb, s, q: mr,
            stem_thickness_from_scanlines=lambda **kwargs: None,
            iqr_ratio=lambda values: None,
            _median=lambda values: None,
        )
        module_name = "test_mcp_tools_compensated_tuning_module"
        spec = importlib.util.spec_from_file_location(module_name, _module_path())
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(
            sys.modules,
            {
                "GlyphsApp": glyphs_module,
                "mcp_runtime": types.SimpleNamespace(mcp=_FakeMCP()),
                "mcp_tool_helpers": helpers_module,
                "compensated_tuning_engine": engine_module,
            },
        ):
            sys.modules.pop(module_name, None)
            assert spec.loader is not None
            spec.loader.exec_module(module)
        return module

    def test_apply_uses_internal_review_impl_instead_of_tool_wrapper(self) -> None:
        base_master = types.SimpleNamespace(id="m01")
        ref_master = types.SimpleNamespace(id="m002")
        dest_layer = types.SimpleNamespace(components=[], paths=[], width=600)
        glyph = types.SimpleNamespace(layers={"m01": dest_layer})
        font = types.SimpleNamespace(
            masters=[base_master, ref_master],
            glyphs={"L": glyph},
            selectedFontMaster=base_master,
        )
        module = self._load_module(font)

        self.assertFalse(callable(module.review_compensated_tuning))

        review_calls = []

        def fake_review_impl(**kwargs):
            review_calls.append(kwargs)
            return {"paths": [], "width": 600, "gmcp": {"ok": True}}

        module._review_compensated_tuning_impl = fake_review_impl

        result = module._apply_compensated_tuning_impl(
            font_index=0,
            glyph_names=["L"],
            base_master_id="m01",
            ref_master_id="m002",
            output_master_id="m01",
            sx=1.0,
            sy=1.0,
            q_x=0.995,
            q_y=0.995,
            dry_run=True,
            backup=False,
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["dryRun"])
        self.assertEqual(result["summary"]["okCount"], 1)
        self.assertEqual(result["results"][0]["action"], "preview")
        self.assertEqual(review_calls[0]["glyph_name"], "L")


if __name__ == "__main__":
    unittest.main()
