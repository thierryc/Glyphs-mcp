"""Behavior and safety tests for Unicode assignment MCP tools."""

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
    return _resources_dir() / "mcp_tools_unicode_assignments.py"


class _FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def decorator(fn):
            self.tools[fn.__name__] = kwargs
            return fn

        return decorator


class _GlyphCollection:
    def __init__(self, glyphs):
        self.values = list(glyphs)
        self.by_name = {glyph.name: glyph for glyph in glyphs}

    def __iter__(self):
        return iter(self.values)

    def __len__(self):
        return len(self.values)

    def __getitem__(self, key):
        return self.by_name.get(key)


class _Glyph:
    def __init__(self, name, unicodes=None, export=True, fail_on=None):
        self.name = name
        self.export = export
        self._unicodes = list(unicodes or [])
        self.fail_on = list(fail_on) if fail_on is not None else None

    @property
    def unicodes(self):
        return list(self._unicodes)

    @unicodes.setter
    def unicodes(self, value):
        values = list(value or [])
        if self.fail_on is not None and values == self.fail_on:
            raise RuntimeError("simulated write failure")
        self._unicodes = values

    @property
    def unicode(self):
        return self._unicodes[0] if self._unicodes else None

    @unicode.setter
    def unicode(self, value):
        self._unicodes = [value] if value else []


class _Font:
    def __init__(self, glyphs, selected_names=None):
        self.familyName = "Unicode Test"
        self.filepath = "/tmp/UnicodeTest.glyphs"
        self.glyphs = _GlyphCollection(glyphs)
        self.selectedLayers = [
            types.SimpleNamespace(parent=self.glyphs[name])
            for name in list(selected_names or [])
        ]
        self.save_calls = 0

    def save(self):
        self.save_calls += 1


def _resolve_font_by_index(glyphs, font_index):
    fonts = list(getattr(glyphs, "fonts", []) or [])
    index = int(font_index)
    if index < 0 or index >= len(fonts):
        return None, fonts
    return fonts[index], fonts


def _font_resolution_error(font_index, fonts=None, ok_key=None):
    payload = {
        "error": "Font index out of range",
        "fontIndex": font_index,
        "availableFontCount": len(fonts or []),
    }
    if ok_key:
        payload[ok_key] = False
    return payload


class McpToolsUnicodeAssignmentsTests(unittest.TestCase):
    def _load_module(self, font):
        resources = str(_resources_dir())
        if resources not in sys.path:
            sys.path.insert(0, resources)

        glyphs_api = types.SimpleNamespace(fonts=[font], font=font)
        fake_mcp = _FakeMCP()
        helpers = types.SimpleNamespace(
            _font_resolution_error=_font_resolution_error,
            _is_active_font=lambda glyphs, candidate: getattr(glyphs, "font", None) is candidate,
            _resolve_font_by_index=_resolve_font_by_index,
            _run_on_main_thread=lambda callback: callback(),
            _safe_json=json.dumps,
            _selected_glyph_names_for_font=lambda candidate: [
                layer.parent.name for layer in list(getattr(candidate, "selectedLayers", []) or [])
            ],
        )

        module_name = "glyphs_mcp_test_mcp_tools_unicode_assignments"
        spec = importlib.util.spec_from_file_location(module_name, _module_path())
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(
            sys.modules,
            {
                "GlyphsApp": types.SimpleNamespace(Glyphs=glyphs_api),
                "mcp_runtime": types.SimpleNamespace(mcp=fake_mcp),
                "tool_registration": types.SimpleNamespace(glyphs_tool=lambda *_args, **_kwargs: (lambda fn: fn)),
                "mcp_tool_helpers": helpers,
            },
        ):
            sys.modules.pop(module_name, None)
            assert spec.loader is not None
            spec.loader.exec_module(module)
        return module, fake_mcp

    def test_tool_annotations_and_profile_intent_are_explicit(self) -> None:
        module, _fake_mcp = self._load_module(_Font([_Glyph("A")], ["A"]))
        from tool_catalog import TOOL_CATALOG

        self.assertTrue(TOOL_CATALOG["review_unicode_assignments"].annotations["readOnlyHint"])
        self.assertFalse(TOOL_CATALOG["review_unicode_assignments"].annotations["destructiveHint"])
        self.assertTrue(TOOL_CATALOG["apply_unicode_assignments"].annotations["destructiveHint"])
        self.assertFalse(TOOL_CATALOG["apply_unicode_assignments"].annotations["readOnlyHint"])
        self.assertIsNotNone(module)

    def test_review_selected_allocates_after_untargeted_occupied_value(self) -> None:
        target = _Glyph("newCharacter")
        font = _Font([target, _Glyph("existing", ["E000"])], ["newCharacter"])
        module, _fake_mcp = self._load_module(font)

        payload = json.loads(
            asyncio.run(module.review_unicode_assignments(allocate_unencoded=True))
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["targetGlyphs"], ["newCharacter"])
        self.assertEqual(payload["proposedAssignments"][0]["unicodes"], ["E001"])

    def test_review_requires_nonempty_selection(self) -> None:
        module, _fake_mcp = self._load_module(_Font([_Glyph("A")]))

        payload = json.loads(asyncio.run(module.review_unicode_assignments()))

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "No glyphs to review.")

    def test_explicit_glyph_names_override_scope(self) -> None:
        font = _Font([_Glyph("A"), _Glyph("B")], ["A"])
        module, _fake_mcp = self._load_module(font)

        payload = json.loads(
            asyncio.run(
                module.review_unicode_assignments(
                    scope="selected",
                    glyph_names=["B"],
                )
            )
        )

        self.assertEqual(payload["scope"], "glyph_names")
        self.assertEqual(payload["targetGlyphs"], ["B"])

    def test_whole_font_scope_must_be_explicit_and_targets_every_glyph(self) -> None:
        font = _Font([_Glyph("home"), _Glyph("regularTextCharacter", ["0041"])])
        module, _fake_mcp = self._load_module(font)

        payload = json.loads(
            asyncio.run(module.review_unicode_assignments(scope="font"))
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["scope"], "font")
        self.assertEqual(payload["targetGlyphs"], ["home", "regularTextCharacter"])

    def test_dry_run_returns_exact_changes_without_mutation(self) -> None:
        glyph = _Glyph("gaiji")
        font = _Font([glyph])
        module, _fake_mcp = self._load_module(font)
        assignments = [{"glyphName": "gaiji", "expectedUnicodes": [], "unicodes": ["E100"]}]

        payload = json.loads(
            asyncio.run(module.apply_unicode_assignments(assignments=assignments, dry_run=True))
        )

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["dryRun"])
        self.assertFalse(payload["applied"])
        self.assertEqual(payload["changes"][0]["after"], ["E100"])
        self.assertEqual(glyph.unicodes, [])

    def test_apply_refuses_without_confirmation(self) -> None:
        glyph = _Glyph("historicalSign")
        module, _fake_mcp = self._load_module(_Font([glyph]))
        assignments = [
            {
                "glyphName": "historicalSign",
                "expectedUnicodes": [],
                "unicodes": ["E200"],
            }
        ]

        payload = json.loads(
            asyncio.run(module.apply_unicode_assignments(assignments=assignments))
        )

        self.assertFalse(payload["ok"])
        self.assertIn("confirm=true", payload["error"])
        self.assertEqual(glyph.unicodes, [])

    def test_confirmed_apply_verifies_multiple_values_and_does_not_save(self) -> None:
        glyph = _Glyph("phoneticCharacter")
        font = _Font([glyph])
        module, _fake_mcp = self._load_module(font)
        assignments = [
            {
                "glyphName": "phoneticCharacter",
                "expectedUnicodes": [],
                "unicodes": ["E200", "F0001"],
            }
        ]

        payload = json.loads(
            asyncio.run(
                module.apply_unicode_assignments(
                    assignments=assignments,
                    confirm=True,
                )
            )
        )

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["applied"])
        self.assertEqual(glyph.unicodes, ["E200", "F0001"])
        self.assertEqual(payload["verifiedGlyphNames"], ["phoneticCharacter"])
        self.assertEqual(font.save_calls, 0)

    def test_stale_expected_state_rejects_whole_batch(self) -> None:
        glyph = _Glyph("gaiji", ["E100"])
        module, _fake_mcp = self._load_module(_Font([glyph]))

        payload = json.loads(
            asyncio.run(
                module.apply_unicode_assignments(
                    assignments=[
                        {
                            "glyphName": "gaiji",
                            "expectedUnicodes": [],
                            "unicodes": ["E101"],
                        }
                    ],
                    confirm=True,
                )
            )
        )

        self.assertFalse(payload["ok"])
        self.assertIn("stale_expected_state", {item["code"] for item in payload["errors"]})
        self.assertEqual(glyph.unicodes, ["E100"])

    def test_preflight_rejects_collision_with_untargeted_glyph(self) -> None:
        target = _Glyph("target")
        existing = _Glyph("existing", ["E100"])
        module, _fake_mcp = self._load_module(_Font([target, existing]))

        payload = json.loads(
            asyncio.run(
                module.apply_unicode_assignments(
                    assignments=[
                        {
                            "glyphName": "target",
                            "expectedUnicodes": [],
                            "unicodes": ["E100"],
                        }
                    ],
                    confirm=True,
                )
            )
        )

        self.assertFalse(payload["ok"])
        self.assertIn("unicode_collision", {item["code"] for item in payload["errors"]})
        self.assertEqual(target.unicodes, [])

    def test_partial_write_failure_rolls_back_all_glyphs(self) -> None:
        first = _Glyph("first")
        second = _Glyph("second", fail_on=["E101"])
        font = _Font([first, second])
        module, _fake_mcp = self._load_module(font)

        payload = json.loads(
            asyncio.run(
                module.apply_unicode_assignments(
                    assignments=[
                        {
                            "glyphName": "first",
                            "expectedUnicodes": [],
                            "unicodes": ["E100"],
                        },
                        {
                            "glyphName": "second",
                            "expectedUnicodes": [],
                            "unicodes": ["E101"],
                        },
                    ],
                    confirm=True,
                )
            )
        )

        self.assertFalse(payload["ok"])
        self.assertTrue(payload["rollback"]["succeeded"])
        self.assertEqual(first.unicodes, [])
        self.assertEqual(second.unicodes, [])
        self.assertEqual(font.save_calls, 0)


if __name__ == "__main__":
    unittest.main()
