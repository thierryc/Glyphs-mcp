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


def _sequence_values(sequence):
    if sequence is None:
        return []
    try:
        return [sequence[index] for index in range(len(sequence))]
    except Exception:
        try:
            return list(sequence)
        except Exception:
            return []


def _add_font(fonts, seen, font):
    if font is None:
        return
    key = ("path", str(getattr(font, "filepath", "") or "")) if getattr(font, "filepath", None) else ("object", id(font))
    if key in seen:
        return
    seen.add(key)
    fonts.append(font)


def _open_fonts_from_glyphs(glyphs):
    fonts = []
    seen = set()
    try:
        fonts_proxy = getattr(glyphs, "fonts", None)
    except Exception:
        fonts_proxy = None
    for font in _sequence_values(fonts_proxy):
        _add_font(fonts, seen, font)
    for document in _sequence_values(getattr(glyphs, "documents", None)):
        _add_font(fonts, seen, getattr(document, "font", None))
    _add_font(fonts, seen, getattr(getattr(glyphs, "currentDocument", None), "font", None))
    try:
        _add_font(fonts, seen, getattr(glyphs, "font", None))
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
    fonts = list(fonts or [])
    payload = {
        "error": "Font index {} out of range. Available fonts: {}".format(font_index, len(fonts)) if fonts else "No open fonts found. Open a font in Glyphs and run list_open_fonts to choose a font_index.",
        "fontIndex": font_index,
        "availableFontCount": len(fonts),
        "availableFonts": [{"fontIndex": i, "familyName": getattr(font, "familyName", ""), "filePath": getattr(font, "filepath", None)} for i, font in enumerate(fonts)],
    }
    if ok_key == "ok":
        payload["ok"] = False
    elif ok_key == "success":
        payload["success"] = False
    return payload


def _component_transform_values(component):
    position = getattr(component, "position", None)
    scale = getattr(component, "scale", None)
    pos_x = getattr(position, "x", None)
    pos_y = getattr(position, "y", None)
    scale_x = getattr(scale, "x", 1.0)
    scale_y = getattr(scale, "y", 1.0)
    if pos_x is not None and pos_y is not None:
        return [float(scale_x), 0.0, 0.0, float(scale_y), float(pos_x), float(pos_y)]

    transform = getattr(component, "transform", component)
    defaults = [1, 0, 0, 1, 0, 0]
    if not isinstance(transform, (list, tuple)):
        return [float(value) for value in defaults]

    values = []
    for index, default in enumerate(defaults):
        try:
            values.append(float(transform[index]))
        except Exception:
            values.append(float(default))
    return values


def _layer_components(layer):
    try:
        shapes = getattr(layer, "shapes", None)
    except Exception:
        shapes = None
    if shapes is not None:
        return [shape for shape in shapes if getattr(shape, "componentName", None) is not None]
    components = getattr(layer, "components", [])
    if isinstance(components, (list, tuple)):
        return [component for component in components if getattr(component, "componentName", None) is not None]
    return []


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


def _glyph(
    name,
    unicode=None,
    category="Letter",
    sub_category="Uppercase",
    export=True,
    left_kerning_group=None,
    right_kerning_group=None,
):
    return types.SimpleNamespace(
        name=name,
        unicode=unicode,
        category=category,
        subCategory=sub_category,
        layers=[object(), object()],
        leftKerningGroup=left_kerning_group if left_kerning_group is not None else name,
        rightKerningGroup=right_kerning_group if right_kerning_group is not None else name,
        export=export,
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
        kerning={"roman": {"A": {"V": -80}, "@MMK_L_T": {"@MMK_R_o": -30}}},
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
            _component_transform_values=_component_transform_values,
            _custom_parameter=_custom_parameter,
            _font_resolution_error=_font_resolution_error,
            _get_component_automatic=lambda component: False,
            _get_layer_id=lambda layer: "",
            _get_left_sidebearing=lambda layer: None,
            _get_right_sidebearing=lambda layer: None,
            _glyphs_show_layer_link_fields=lambda *args, **kwargs: {},
            _glyphs_show_link_fields=lambda *args, **kwargs: {"showMarkdown": kwargs.get("label", "Open in Glyphs")},
            _layer_display_name=lambda _font, layer, master_id=None: getattr(layer, "name", None) or "Regular",
            _layer_components=_layer_components,
            _open_fonts_from_glyphs=_open_fonts_from_glyphs,
            _resolve_font_by_index=_resolve_font_by_index,
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

    def test_get_glyph_details_reads_component_transform_without_iteration(self) -> None:
        class HostileComponents:
            def __iter__(self):
                raise AssertionError("layer.components must not be iterated")

            def __len__(self):
                raise AssertionError("layer.components must not be sized")

        class NonIterableTransform:
            def __iter__(self):
                raise AssertionError("component transform must not be iterated")

            def __getitem__(self, index):
                raise AssertionError("component transform proxy must not be indexed")

        component = types.SimpleNamespace(
            componentName="H",
            transform=NonIterableTransform(),
            position=types.SimpleNamespace(x=10, y=0),
            scale=types.SimpleNamespace(x=0.25, y=0.25),
            rotation=0,
            automaticAlignment=False,
        )
        layer = types.SimpleNamespace(
            name="Regular",
            associatedMasterId="roman",
            width=400,
            paths=[object()],
            components=HostileComponents(),
            shapes=[object(), component],
            anchors=[],
        )
        glyph = types.SimpleNamespace(
            name="mcpProbe",
            unicode=None,
            category="Letter",
            subCategory="Test",
            script=None,
            productionName=None,
            layers=[layer],
        )

        class GlyphCollection(list):
            def __getitem__(self, key):
                if isinstance(key, str):
                    for item in self:
                        if item.name == key:
                            return item
                    return None
                return super().__getitem__(key)

        font = _font()
        font.glyphs = GlyphCollection([glyph])
        module = self._load_module(font)

        payload = json.loads(asyncio.run(module.get_glyph_details(0, "mcpProbe")))

        self.assertEqual(payload["name"], "mcpProbe")
        self.assertEqual(payload["layers"][0]["componentCount"], 1)
        self.assertEqual(payload["layers"][0]["components"][0]["transform"], [0.25, 0.0, 0.0, 0.25, 10.0, 0.0])

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

    def test_get_font_glyphs_returns_metadata_and_show_links(self) -> None:
        font = _font()
        font.glyphs = [
            _glyph("A", unicode="0041", left_kerning_group="A_L", right_kerning_group="A_R"),
            _glyph("space", category="Separator", sub_category="Space", export=False),
        ]
        module = self._load_module(font)

        payload = json.loads(asyncio.run(module.get_font_glyphs(0)))

        self.assertEqual([item["name"] for item in payload], ["A", "space"])
        self.assertEqual(payload[0]["unicode"], "0041")
        self.assertEqual(payload[0]["leftKerningGroup"], "A_L")
        self.assertEqual(payload[0]["rightKerningGroup"], "A_R")
        self.assertEqual(payload[0]["layerCount"], 2)
        self.assertFalse(payload[1]["export"])
        self.assertEqual(payload[0]["showMarkdown"], "Open A in Glyphs")

    def test_get_font_glyphs_invalid_font_index_is_structured(self) -> None:
        module = self._load_module(_font())

        payload = json.loads(asyncio.run(module.get_font_glyphs(3)))

        self.assertIn("error", payload)
        self.assertEqual(payload["fontIndex"], 3)
        self.assertEqual(payload["availableFontCount"], 1)
        self.assertEqual(payload["availableFonts"][0]["familyName"], "Test")

    def test_get_font_instances_returns_instance_metadata(self) -> None:
        font = _font()
        font.instances = [
            types.SimpleNamespace(
                name="Regular",
                weight="400",
                width="100",
                customName="Text",
                interpolationWeight="400",
                interpolationWidth="100",
                active=True,
                export=True,
            ),
            types.SimpleNamespace(
                name="Black",
                weight=900,
                width=110,
                customName=None,
                interpolationWeight=900,
                interpolationWidth=110,
                active=False,
                export=False,
            ),
        ]
        module = self._load_module(font)

        payload = json.loads(asyncio.run(module.get_font_instances(0)))

        self.assertEqual(len(payload), 2)
        self.assertEqual(payload[0]["name"], "Regular")
        self.assertEqual(payload[0]["weight"], 400.0)
        self.assertEqual(payload[0]["width"], 100.0)
        self.assertTrue(payload[0]["active"])
        self.assertFalse(payload[1]["export"])

    def test_get_font_kerning_reads_default_and_explicit_master(self) -> None:
        font = _font()
        font.kerning["italic"] = {"A": {"T": -40}}
        module = self._load_module(font)

        default_payload = json.loads(asyncio.run(module.get_font_kerning(0)))
        explicit_payload = json.loads(asyncio.run(module.get_font_kerning(0, master_id="italic")))

        self.assertEqual(default_payload["masterId"], "roman")
        self.assertEqual(default_payload["pairCount"], 2)
        self.assertIn({"left": "A", "right": "V", "value": -80}, default_payload["kerningPairs"])
        self.assertEqual(explicit_payload["masterId"], "italic")
        self.assertEqual(explicit_payload["kerningPairs"], [{"left": "A", "right": "T", "value": -40}])


if __name__ == "__main__":
    unittest.main()
