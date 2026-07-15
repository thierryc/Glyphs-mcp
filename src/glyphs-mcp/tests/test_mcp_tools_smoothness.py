"""Regression tests for MCP smoothness tools."""

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
        / "mcp_tools_smoothness.py"
    )


class _FakeMCP:
    def tool(self, *args, **kwargs):
        def decorator(fn):
            return fn

        return decorator


class _FakeNode:
    def __init__(self) -> None:
        self.type = "curve"
        self.connection = 0
        self._smooth = False

    @property
    def smooth(self):
        return self._smooth

    @smooth.setter
    def smooth(self, value) -> None:  # pragma: no cover - tool should not rely on this alone
        self._smooth = bool(self._smooth)

    def setConnection_(self, value) -> None:
        self.connection = int(value)
        self._smooth = int(value) == 100


def _open_fonts_from_glyphs(glyphs):
    fonts = []
    try:
        fonts.extend(list(getattr(glyphs, "fonts", None) or []))
    except Exception:
        pass
    for attr in ("documents",):
        try:
            for document in list(getattr(glyphs, attr, None) or []):
                font = getattr(document, "font", None)
                if font is not None and font not in fonts:
                    fonts.append(font)
        except Exception:
            pass
    try:
        font = getattr(getattr(glyphs, "currentDocument", None), "font", None)
        if font is not None and font not in fonts:
            fonts.append(font)
    except Exception:
        pass
    try:
        font = getattr(glyphs, "font", None)
        if font is not None and font not in fonts:
            fonts.append(font)
    except Exception:
        pass
    return fonts


def _resolve_font_by_index(glyphs, font_index):
    fonts = _open_fonts_from_glyphs(glyphs)
    index = int(font_index)
    if index < 0 or index >= len(fonts):
        return None, fonts
    return fonts[index], fonts


def _font_resolution_error(font_index, fonts=None, ok_key=None):
    payload = {"error": "Font index {} out of range. Available fonts: {}".format(font_index, len(fonts or []))}
    if ok_key == "ok":
        payload["ok"] = False
    return payload


class McpToolsSmoothnessTests(unittest.TestCase):
    def _load_module(self, broken_fonts=False):
        node = _FakeNode()
        path = types.SimpleNamespace(nodes=[node], closed=True)
        layer = types.SimpleNamespace(paths=[path])
        glyph = types.SimpleNamespace(layers={"m1": layer})
        font = types.SimpleNamespace(glyphs={"A": glyph})
        if broken_fonts:
            class BrokenGlyphs:
                @property
                def fonts(self):
                    raise RuntimeError("broken fonts proxy")

            glyphs_obj = BrokenGlyphs()
            glyphs_obj.documents = [types.SimpleNamespace(font=font)]
            glyphs_obj.currentDocument = types.SimpleNamespace(font=font)
            glyphs_obj.font = font
        else:
            glyphs_obj = types.SimpleNamespace(fonts=[font])
        glyphs_module = types.SimpleNamespace(Glyphs=glyphs_obj, GSSMOOTH=100)
        smoothness_engine = types.SimpleNamespace(
            evaluate_collinear_handles_at_node=lambda *args, **kwargs: {"ok": True},
            find_collinear_handle_nodes=lambda *args, **kwargs: [],
        )
        module_name = "glyphs_mcp_test_mcp_tools_smoothness"
        spec = importlib.util.spec_from_file_location(module_name, _module_path())
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(
            sys.modules,
            {
                "GlyphsApp": glyphs_module,
                "mcp_runtime": types.SimpleNamespace(mcp=_FakeMCP()),
                "mcp_tool_helpers": types.SimpleNamespace(
                    _font_resolution_error=_font_resolution_error,
                    _resolve_font_by_index=_resolve_font_by_index,
                    _safe_json=lambda payload: json.dumps(payload),
                ),
                "smoothness_engine": smoothness_engine,
            },
        ):
            sys.modules.pop(module_name, None)
            assert spec.loader is not None
            spec.loader.exec_module(module)
        return module, node

    def test_apply_collinear_handles_smooth_uses_connection_mutation(self) -> None:
        module, node = self._load_module()

        payload = json.loads(
            asyncio.run(
                module.apply_collinear_handles_smooth(
                    font_index=0,
                    glyph_name="A",
                    master_id="m1",
                    path_index=0,
                    node_indices=["0"],
                    confirm=True,
                )
            )
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["applied"], [0])
        self.assertTrue(node.smooth)
        self.assertEqual(node.connection, 100)

    def test_smoothness_tools_fall_back_when_fonts_proxy_fails(self) -> None:
        module, node = self._load_module(broken_fonts=True)

        review = json.loads(
            asyncio.run(
                module.review_collinear_handles(
                    font_index=0,
                    glyph_name="A",
                    master_id="m1",
                    path_index=0,
                )
            )
        )
        apply = json.loads(
            asyncio.run(
                module.apply_collinear_handles_smooth(
                    font_index=0,
                    glyph_name="A",
                    master_id="m1",
                    path_index=0,
                    node_indices=[0],
                    dry_run=True,
                )
            )
        )

        self.assertTrue(review["ok"])
        self.assertTrue(apply["ok"])
        self.assertFalse(node.smooth)


if __name__ == "__main__":
    unittest.main()
