"""Regression tests for font/master MCP tools."""

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
        / "mcp_tools_font.py"
    )


class _FakeMCP:
    def tool(self, *args, **kwargs):
        def decorator(fn):
            return fn

        return decorator


def _coerce_numeric(value):
    try:
        return float(value)
    except Exception:
        return None


def _custom_parameter(obj, key, default=None):
    params = getattr(obj, "customParameters", {}) or {}
    try:
        return params.get(key, default)
    except Exception:
        return default


def _master(master_id, name, italic_angle, slant_angle=0):
    return types.SimpleNamespace(
        id=master_id,
        name=name,
        italicAngle=italic_angle,
        customName=None,
        customParameters={"postscriptSlantAngle": slant_angle},
        ascender=800,
        capHeight=700,
        descender=-200,
        xHeight=500,
    )


def _font():
    masters = [
        _master("roman", "Roman", 0, 0),
        _master("italic", "Italic", 12, 3),
    ]
    return types.SimpleNamespace(
        familyName="Test",
        filepath="/tmp/Test.glyphs",
        masters=masters,
        instances=[],
        glyphs=[],
        axes=[],
        upm=1000,
        versionMajor=1,
        versionMinor=0,
    )


class _GlyphsWithBrokenFonts:
    def __init__(self, font):
        self.documents = [types.SimpleNamespace(font=font)]
        self.currentDocument = types.SimpleNamespace(font=font)
        self.font = font

    @property
    def fonts(self):
        raise TypeError(
            "Can't instantiate abstract class AppFontProxy without an implementation "
            "for abstract methods 'getByIndex', 'insertAtIndex', 'removeByIndex', 'setByIndex'"
        )


class McpToolsFontTests(unittest.TestCase):
    def _load_module(self, font, glyphs=None):
        glyphs_module = types.SimpleNamespace(
            Glyphs=glyphs or types.SimpleNamespace(fonts=[font], documents=[], currentDocument=None, font=font)
        )
        helpers_module = types.SimpleNamespace(
            _coerce_numeric=_coerce_numeric,
            _custom_parameter=_custom_parameter,
            _get_component_automatic=lambda component: False,
            _get_layer_id=lambda layer: "",
            _get_left_sidebearing=lambda layer: None,
            _get_right_sidebearing=lambda layer: None,
            _glyphs_show_layer_link_fields=lambda *args, **kwargs: {},
            _glyphs_show_link_fields=lambda *args, **kwargs: {},
            _safe_attr=lambda obj, attr, default=None: getattr(obj, attr, default),
            _safe_json=lambda payload: json.dumps(payload),
        )
        module_name = "glyphs_mcp_test_mcp_tools_font"
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
            sys.modules.pop(module_name, None)
            assert spec.loader is not None
            spec.loader.exec_module(module)
        return module

    def test_list_open_fonts_falls_back_to_documents_when_fonts_proxy_fails(self) -> None:
        font = _font()
        module = self._load_module(font, glyphs=_GlyphsWithBrokenFonts(font))

        payload = json.loads(asyncio.run(module.list_open_fonts()))

        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["familyName"], "Test")
        self.assertEqual(payload[0]["filePath"], "/tmp/Test.glyphs")

    def test_get_font_masters_falls_back_to_documents_when_fonts_proxy_fails(self) -> None:
        font = _font()
        module = self._load_module(font, glyphs=_GlyphsWithBrokenFonts(font))

        payload = json.loads(asyncio.run(module.get_font_masters(0)))

        self.assertEqual(payload[0]["id"], "roman")
        self.assertEqual(payload[1]["id"], "italic")

    def test_get_font_masters_reports_italic_angle_separately_from_slant_angle(self) -> None:
        font = _font()
        module = self._load_module(font)

        payload = json.loads(asyncio.run(module.get_font_masters(0)))

        italic = payload[1]
        self.assertEqual(italic["id"], "italic")
        self.assertEqual(italic["italicAngle"], 12.0)
        self.assertEqual(italic["slantAngle"], 3)

    def test_set_master_italic_angle_dry_run_does_not_mutate(self) -> None:
        font = _font()
        module = self._load_module(font)

        payload = json.loads(
            asyncio.run(
                module.set_master_italic_angle(
                    font_index=0,
                    master_id="italic",
                    italic_angle=14,
                    dry_run=True,
                )
            )
        )

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["dryRun"])
        self.assertEqual(payload["before"]["italicAngle"], 12.0)
        self.assertEqual(payload["after"]["italicAngle"], 14.0)
        self.assertEqual(font.masters[1].italicAngle, 12)

    def test_set_master_italic_angle_requires_confirm_to_mutate(self) -> None:
        font = _font()
        module = self._load_module(font)

        payload = json.loads(
            asyncio.run(
                module.set_master_italic_angle(
                    font_index=0,
                    master_id="italic",
                    italic_angle=14,
                )
            )
        )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "Use dry_run=true first or confirm=true to mutate")
        self.assertEqual(font.masters[1].italicAngle, 12)

    def test_set_master_italic_angle_confirm_mutates_only_target_master(self) -> None:
        font = _font()
        module = self._load_module(font)

        payload = json.loads(
            asyncio.run(
                module.set_master_italic_angle(
                    font_index=0,
                    master_id="italic",
                    italic_angle=14,
                    confirm=True,
                )
            )
        )

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["applied"])
        self.assertEqual(font.masters[0].italicAngle, 0)
        self.assertEqual(font.masters[1].italicAngle, 14.0)

    def test_set_master_italic_angle_rejects_invalid_inputs(self) -> None:
        font = _font()
        module = self._load_module(font)

        bad_angle = json.loads(
            asyncio.run(
                module.set_master_italic_angle(
                    font_index=0,
                    master_id="italic",
                    italic_angle=89,
                    confirm=True,
                )
            )
        )
        missing_master = json.loads(
            asyncio.run(
                module.set_master_italic_angle(
                    font_index=0,
                    master_id="missing",
                    italic_angle=12,
                    confirm=True,
                )
            )
        )

        self.assertFalse(bad_angle["ok"])
        self.assertEqual(bad_angle["error"], "italic_angle must be greater than -89 and less than 89")
        self.assertFalse(missing_master["ok"])
        self.assertEqual(missing_master["error"], "Master not found")
        self.assertEqual(font.masters[1].italicAngle, 12)


if __name__ == "__main__":
    unittest.main()
