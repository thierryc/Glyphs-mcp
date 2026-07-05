"""Unit tests for mcp_tool_helpers (pure helpers).

These helpers intentionally avoid importing GlyphsApp so they can be tested in
the normal unit test runner.
"""

from __future__ import annotations

import json
import sys
import types
import unittest
from pathlib import Path


def _resources_dir() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Resources"
    )


class McpToolHelpersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(_resources_dir()))
        global helpers  # noqa: PLW0603 - simple test import
        import mcp_tool_helpers as helpers  # type: ignore

    def test_round_half_away_from_zero(self) -> None:
        self.assertEqual(helpers._round_half_away_from_zero(0.0), 0)
        self.assertEqual(helpers._round_half_away_from_zero(0.49), 0)
        self.assertEqual(helpers._round_half_away_from_zero(0.5), 1)
        self.assertEqual(helpers._round_half_away_from_zero(1.5), 2)
        self.assertEqual(helpers._round_half_away_from_zero(-0.5), -1)
        self.assertEqual(helpers._round_half_away_from_zero(-1.5), -2)

    def test_sanitize_for_json_nested_objects(self) -> None:
        class Weird:
            def __str__(self) -> str:  # pragma: no cover - exercised via sanitizer
                return "weird"

        payload = {
            "a": 1,
            "b": {1, 2, 3},
            "c": ("x", Weird()),
            "d": {"k": Weird()},
        }

        sanitized = helpers._sanitize_for_json(payload)
        # Must be JSON-serializable without throwing.
        encoded = json.dumps(sanitized)
        self.assertIn('"a"', encoded)
        self.assertIn('"weird"', encoded)

    def test_open_fonts_falls_back_when_fonts_proxy_raises(self) -> None:
        font = types.SimpleNamespace(familyName="Doc Font", filepath="/tmp/doc.glyphs")

        class BrokenGlyphs:
            @property
            def fonts(self):
                raise TypeError("broken private font proxy")

        glyphs = BrokenGlyphs()
        glyphs.documents = [types.SimpleNamespace(font=font)]
        glyphs.currentDocument = types.SimpleNamespace(font=font)
        glyphs.font = font

        fonts = helpers._open_fonts_from_glyphs(glyphs)

        self.assertEqual(fonts, [font])

    def test_open_fonts_falls_back_to_cocoa_documents_when_glyphs_proxies_raise(self) -> None:
        first = types.SimpleNamespace(familyName="Archivo", filepath="/tmp/Archivo.glyphs")
        second = types.SimpleNamespace(familyName="Gee gee", filepath="/tmp/Gee gee.glyphspackage")
        third = types.SimpleNamespace(familyName="Inter", filepath="/tmp/Inter-Roman.glyphspackage")

        class BrokenGlyphs:
            @property
            def fonts(self):
                raise TypeError("broken font proxy")

            @property
            def documents(self):
                raise TypeError("broken document proxy")

        class FakeNSDocumentController:
            @staticmethod
            def sharedDocumentController():
                return types.SimpleNamespace(
                    documents=lambda: [
                        types.SimpleNamespace(font=first),
                        types.SimpleNamespace(font=second),
                        types.SimpleNamespace(font=third),
                    ]
                )

        original_appkit = sys.modules.get("AppKit")
        sys.modules["AppKit"] = types.SimpleNamespace(NSDocumentController=FakeNSDocumentController)
        try:
            glyphs = BrokenGlyphs()
            glyphs.currentDocument = types.SimpleNamespace(font=second)
            glyphs.font = second

            fonts = helpers._open_fonts_from_glyphs(glyphs)
        finally:
            if original_appkit is None:
                sys.modules.pop("AppKit", None)
            else:
                sys.modules["AppKit"] = original_appkit

        self.assertEqual(fonts, [first, second, third])

    def test_font_context_source_uses_cocoa_documents_when_glyphs_proxies_raise(self) -> None:
        first = types.SimpleNamespace(familyName="Archivo", filepath="/tmp/Archivo.glyphs")
        second = types.SimpleNamespace(familyName="Inter", filepath="/tmp/Inter.glyphspackage")

        class BrokenGlyphs:
            @property
            def fonts(self):
                raise TypeError("broken font proxy")

            @property
            def documents(self):
                raise TypeError("broken document proxy")

        class FakeNSDocumentController:
            @staticmethod
            def sharedDocumentController():
                return types.SimpleNamespace(
                    documents=lambda: [
                        types.SimpleNamespace(font=first),
                        types.SimpleNamespace(font=second),
                    ]
                )

        namespace = {}
        original_appkit = sys.modules.get("AppKit")
        sys.modules["AppKit"] = types.SimpleNamespace(NSDocumentController=FakeNSDocumentController)
        try:
            exec(helpers._font_context_source(), namespace)
            resolved = namespace["__glyphs_mcp_font_by_index"](BrokenGlyphs(), 1)
        finally:
            if original_appkit is None:
                sys.modules.pop("AppKit", None)
            else:
                sys.modules["AppKit"] = original_appkit

        self.assertIs(resolved, second)

    def test_open_fonts_preserves_fonts_order_then_adds_public_fallbacks(self) -> None:
        first = types.SimpleNamespace(familyName="First", filepath="/tmp/first.glyphs")
        second = types.SimpleNamespace(familyName="Second", filepath="/tmp/second.glyphs")
        third = types.SimpleNamespace(familyName="Third", filepath="/tmp/third.glyphs")
        glyphs = types.SimpleNamespace(
            fonts=[first, second],
            documents=[types.SimpleNamespace(font=second), types.SimpleNamespace(font=third)],
            currentDocument=types.SimpleNamespace(font=third),
            font=first,
        )

        fonts = helpers._open_fonts_from_glyphs(glyphs)

        self.assertEqual(fonts, [first, second, third])

    def test_open_fonts_uses_current_document_and_active_font_without_documents(self) -> None:
        current = types.SimpleNamespace(familyName="Current", filepath="/tmp/current.glyphs")
        active = types.SimpleNamespace(familyName="Active", filepath="/tmp/active.glyphs")
        glyphs = types.SimpleNamespace(
            currentDocument=types.SimpleNamespace(font=current),
            font=active,
        )

        fonts = helpers._open_fonts_from_glyphs(glyphs)

        self.assertEqual(fonts, [current, active])

    def test_resolve_font_invalid_index_returns_actionable_error(self) -> None:
        font = types.SimpleNamespace(familyName="Only", filepath="/tmp/only.glyphs")
        glyphs = types.SimpleNamespace(fonts=[font])

        resolved, fonts = helpers._resolve_font_by_index(glyphs, 2)
        error = helpers._font_resolution_error(2, fonts, ok_key="ok")

        self.assertIsNone(resolved)
        self.assertFalse(error["ok"])
        self.assertEqual(error["fontIndex"], 2)
        self.assertEqual(error["availableFontCount"], 1)
        self.assertEqual(error["availableFonts"][0]["fontIndex"], 0)
        self.assertIn("run list_open_fonts", helpers._font_resolution_error(0, [], ok_key="success")["error"])

    def test_is_active_font_matches_by_identity_or_filepath(self) -> None:
        active = types.SimpleNamespace(familyName="Active", filepath="/tmp/shared.glyphs")
        same_path = types.SimpleNamespace(familyName="Same Path", filepath="/tmp/shared.glyphs")
        other = types.SimpleNamespace(familyName="Other", filepath="/tmp/other.glyphs")
        glyphs = types.SimpleNamespace(font=active)

        self.assertTrue(helpers._is_active_font(glyphs, active))
        self.assertTrue(helpers._is_active_font(glyphs, same_path))
        self.assertFalse(helpers._is_active_font(glyphs, other))

    def test_get_component_automatic_prefers_present_flags(self) -> None:
        class HasAutomatic:
            automatic = True

        class HasAutomaticAlignment:
            automaticAlignment = False

        class HasNeither:
            pass

        self.assertIs(helpers._get_component_automatic(HasAutomatic()), True)
        self.assertIs(helpers._get_component_automatic(HasAutomaticAlignment()), False)
        self.assertIsNone(helpers._get_component_automatic(HasNeither()))

    def test_coerce_numeric_handles_callables_and_errors(self) -> None:
        self.assertEqual(helpers._coerce_numeric("3.5"), 3.5)
        self.assertEqual(helpers._coerce_numeric(2), 2.0)

        class CallableValue:
            def __call__(self):  # pragma: no cover - used by helper
                return "4"

        self.assertEqual(helpers._coerce_numeric(CallableValue()), 4.0)

        class BrokenCallable:
            def __call__(self):  # pragma: no cover - used by helper
                raise RuntimeError("boom")

        self.assertIsNone(helpers._coerce_numeric(BrokenCallable()))

        class NotNumeric:
            def __str__(self) -> str:  # pragma: no cover - helper ignores
                return "nope"

        self.assertIsNone(helpers._coerce_numeric(NotNumeric()))

    def test_clear_layer_paths_preserves_non_path_shapes(self) -> None:
        class FakePath:
            def __init__(self) -> None:
                self.nodes = [object()]

        class FakeComponent:
            pass

        path = FakePath()
        component = FakeComponent()
        layer = type("Layer", (), {"shapes": [path, component]})()

        helpers._clear_layer_paths(layer)

        self.assertEqual(layer.shapes, [component])

    def test_sidebearing_helpers_fall_back_to_lsb_rsb(self) -> None:
        class LegacyLayer:
            __slots__ = ("LSB", "RSB")

            def __init__(self) -> None:
                self.LSB = 40
                self.RSB = 55

        layer = LegacyLayer()

        self.assertEqual(helpers._get_left_sidebearing(layer), 40)
        self.assertEqual(helpers._get_right_sidebearing(layer), 55)
        self.assertTrue(helpers._set_sidebearing(layer, "leftSideBearing", "LSB", 25))
        self.assertTrue(helpers._set_sidebearing(layer, "rightSideBearing", "RSB", 35))
        self.assertEqual(layer.LSB, 25)
        self.assertEqual(layer.RSB, 35)

    def test_glyphs_show_url_encodes_path_and_glyph(self) -> None:
        url, reason = helpers._glyphs_show_url(
            "/Users/example/My Font.glyphs",
            glyph_name="A.alt",
        )

        self.assertIsNone(reason)
        self.assertEqual(
            url,
            "glyphsapp://show/?path=%2FUsers%2Fexample%2FMy+Font.glyphs&glyph=A.alt",
        )

    def test_glyphs_show_url_preserves_repeated_layer_order(self) -> None:
        url, reason = helpers._glyphs_show_url(
            "/Users/example/Font.glyphs",
            glyph_name="A",
            layer_ids=["master-1", "backup-2"],
        )

        self.assertIsNone(reason)
        self.assertEqual(
            url,
            "glyphsapp://show/?path=%2FUsers%2Fexample%2FFont.glyphs&glyph=A&layer=master-1&layer=backup-2",
        )

    def test_glyphs_show_url_treats_layer_id_string_as_one_layer(self) -> None:
        url, reason = helpers._glyphs_show_url(
            "/Users/example/Font.glyphs",
            glyph_name="A",
            layer_ids="master-1",
        )

        self.assertIsNone(reason)
        self.assertEqual(
            url,
            "glyphsapp://show/?path=%2FUsers%2Fexample%2FFont.glyphs&glyph=A&layer=master-1",
        )

    def test_glyphs_show_glyphs_url_repeats_glyph_params(self) -> None:
        url, reason = helpers._glyphs_show_glyphs_url(
            "/Users/example/Font.glyphs",
            ["a.ss01", "b.ss01", "a.ss01"],
        )

        self.assertIsNone(reason)
        self.assertEqual(
            url,
            "glyphsapp://show/?path=%2FUsers%2Fexample%2FFont.glyphs&glyph=a.ss01&glyph=b.ss01",
        )

    def test_glyphs_show_url_can_use_production_name(self) -> None:
        url, reason = helpers._glyphs_show_url(
            "/Users/example/Font.glyphs",
            production_name="uni01F4",
        )

        self.assertIsNone(reason)
        self.assertEqual(
            url,
            "glyphsapp://show/?path=%2FUsers%2Fexample%2FFont.glyphs&production=uni01F4",
        )

    def test_glyphs_show_link_fields_return_markdown(self) -> None:
        fields = helpers._glyphs_show_link_fields(
            "/Users/example/Font.glyphs",
            glyph_name="A",
            label="Open [A]",
        )

        self.assertEqual(
            fields["showUrl"],
            "glyphsapp://show/?path=%2FUsers%2Fexample%2FFont.glyphs&glyph=A",
        )
        self.assertEqual(
            fields["showMarkdown"],
            "[Open \\[A\\]](http://127.0.0.1:9680/glyphs-show/?path=%2FUsers%2Fexample%2FFont.glyphs&glyph=A)",
        )
        self.assertEqual(
            fields["showHttpUrl"],
            "http://127.0.0.1:9680/glyphs-show/?path=%2FUsers%2Fexample%2FFont.glyphs&glyph=A",
        )

    def test_glyphs_show_bridge_url_preserves_repeated_params(self) -> None:
        url = helpers._glyphs_show_bridge_url(
            "glyphsapp://show/?path=%2FUsers%2Fexample%2FFont.glyphs&glyph=A&glyph=B&layer=master-1"
        )

        self.assertEqual(
            url,
            "http://127.0.0.1:9680/glyphs-show/?path=%2FUsers%2Fexample%2FFont.glyphs&glyph=A&glyph=B&layer=master-1",
        )

    def test_glyphs_show_link_fields_explain_missing_path(self) -> None:
        fields = helpers._glyphs_show_link_fields(None, glyph_name="A")

        self.assertNotIn("showUrl", fields)
        self.assertIn("absolute file path", fields["showUrlUnavailableReason"])

    def test_glyphs_show_layer_link_fields_require_layer_id(self) -> None:
        fields = helpers._glyphs_show_layer_link_fields(
            "/Users/example/Font.glyphs",
            glyph_name="A",
            layer_id=None,
        )

        self.assertNotIn("showUrl", fields)
        self.assertIn("Layer ID unavailable", fields["showUrlUnavailableReason"])

    def test_get_layer_id_prefers_layer_id(self) -> None:
        layer = type(
            "Layer",
            (),
            {
                "layerId": "layer-1",
                "id": "other-id",
                "associatedMasterId": "master-1",
            },
        )()

        self.assertEqual(helpers._get_layer_id(layer), "layer-1")

    def test_parse_style_set_substitutions_simple_rules(self) -> None:
        parsed = helpers._parse_style_set_substitutions(
            """
            # Round dots
            sub period by period.ss01;
            sub comma by comma.ss01;
            """
        )

        self.assertEqual(parsed["unsupportedRuleCount"], 0)
        self.assertEqual(
            parsed["substitutions"],
            [
                {"source": "period", "replacement": "period.ss01"},
                {"source": "comma", "replacement": "comma.ss01"},
            ],
        )

    def test_parse_style_set_substitutions_bracketed_one_to_one(self) -> None:
        parsed = helpers._parse_style_set_substitutions(
            "sub [a b c] by [a.ss01 b.ss01 c.ss01];"
        )

        self.assertEqual(parsed["unsupportedRuleCount"], 0)
        self.assertEqual(
            parsed["substitutions"],
            [
                {"source": "a", "replacement": "a.ss01"},
                {"source": "b", "replacement": "b.ss01"},
                {"source": "c", "replacement": "c.ss01"},
            ],
        )

    def test_parse_style_set_substitutions_skips_contextual_rules(self) -> None:
        parsed = helpers._parse_style_set_substitutions(
            """
            sub a' by a.ss01;
            sub f i by f_i.ss01;
            sub a from [a.ss01 a.ss02];
            sub b by b.ss01;
            """
        )

        self.assertEqual(parsed["unsupportedRuleCount"], 3)
        self.assertEqual(parsed["substitutions"], [{"source": "b", "replacement": "b.ss01"}])
        self.assertTrue(parsed["warnings"])

    def test_style_set_name_from_notes_and_labels(self) -> None:
        self.assertEqual(
            helpers._style_set_name_from_metadata("ss01", notes="Name: Round Dots"),
            "Round Dots",
        )
        self.assertEqual(
            helpers._style_set_name_from_metadata("ss02", labels=["Round Dots", "Alternate Lowercase"]),
            "Alternate Lowercase",
        )

    def test_is_style_set_tag_range(self) -> None:
        self.assertTrue(helpers._is_style_set_tag("ss01"))
        self.assertTrue(helpers._is_style_set_tag("ss20"))
        self.assertFalse(helpers._is_style_set_tag("ss00"))
        self.assertFalse(helpers._is_style_set_tag("ss21"))
        self.assertFalse(helpers._is_style_set_tag("liga"))

    def test_set_kerning_pairs_on_main_thread_updates_kerning_dict(self) -> None:
        font = type("Font", (), {"kerning": {}})()

        helpers._set_kerning_pairs_on_main_thread(
            font,
            "m1",
            [
                ("A", "V", -80),
                ("A", "Y", -60),
                ("A", "V", 0),
            ],
        )

        self.assertIn("m1", font.kerning)
        self.assertEqual(font.kerning["m1"]["A"]["Y"], -60)
        self.assertNotIn("V", font.kerning["m1"]["A"])


if __name__ == "__main__":
    unittest.main()
