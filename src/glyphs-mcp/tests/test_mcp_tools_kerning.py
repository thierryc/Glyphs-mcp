"""Regression tests for MCP kerning tools."""

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
        / "mcp_tools_kerning.py"
    )


class _FakeMCP:
    def tool(self, *args, **kwargs):
        def decorator(fn):
            return fn

        return decorator


class _GlyphCollection:
    def __init__(self, glyphs) -> None:
        self._glyphs = {glyph.name: glyph for glyph in glyphs}

    def __iter__(self):
        return iter(self._glyphs.values())

    def __getitem__(self, key):
        return self._glyphs.get(key)


class _FakeGlyph:
    def __init__(
        self,
        name: str,
        char: str | None = None,
        *,
        export: bool = True,
        left_group: str | None = None,
        right_group: str | None = None,
    ) -> None:
        self.name = name
        self.char = char
        self.export = export
        self.leftKerningGroup = left_group
        self.rightKerningGroup = right_group
        self.layers = {}


class _ProofGlyph:
    def __init__(self, name: str, char: str | None) -> None:
        self.name = name
        self.char = char


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
    elif ok_key == "success":
        payload["success"] = False
    return payload


class McpToolsKerningTests(unittest.TestCase):
    def _load_module(self):
        glyphs = [
            _FakeGlyph("A", "A"),
            _FakeGlyph("V", "V"),
            _FakeGlyph("H", "H"),
            _FakeGlyph("O", "O"),
        ]
        font = types.SimpleNamespace(
            glyphs=_GlyphCollection(glyphs),
            masters=[types.SimpleNamespace(id="m1")],
            kerning={"m1": {"A": {"V": -80}}},
        )
        glyphs_module = types.SimpleNamespace(
            Glyphs=types.SimpleNamespace(fonts=[font], showNotification=lambda *args, **kwargs: None),
        )
        helpers_module = types.SimpleNamespace(
            _coerce_numeric=lambda value: None if value is None else float(value),
            _font_resolution_error=_font_resolution_error,
            _glyph_unicode_char=lambda glyph: getattr(glyph, "char", None),
            _load_andre_fuchs_relevant_pairs=lambda: ({"id": "test_pairs", "pairCount": 1}, [("A", "V")], []),
            _open_tab_on_main_thread=lambda font_obj, text: object(),
            _resolve_font_by_index=_resolve_font_by_index,
            _safe_json=lambda payload: json.dumps(payload),
            _set_kerning_pairs_on_main_thread=lambda *args, **kwargs: None,
            _show_notification=lambda *args, **kwargs: None,
        )
        proof_module = types.SimpleNamespace(
            ProofGlyph=_ProofGlyph,
            assemble_tab_text=lambda sections, rendering, per_line: ("proof", []),
        )
        module_name = "glyphs_mcp_test_mcp_tools_kerning"
        spec = importlib.util.spec_from_file_location(module_name, _module_path())
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(
            sys.modules,
            {
                "GlyphsApp": glyphs_module,
                "kerning_collision_engine": types.SimpleNamespace(),
                "kerning_proof_engine": proof_module,
                "mcp_runtime": types.SimpleNamespace(mcp=_FakeMCP()),
                "mcp_tool_helpers": helpers_module,
            },
        ):
            sys.modules.pop(module_name, None)
            assert spec.loader is not None
            spec.loader.exec_module(module)
        return module, font

    def test_generate_kerning_tab_handles_numeric_kerning_values(self) -> None:
        module, _font = self._load_module()

        payload = json.loads(
            asyncio.run(
                module.generate_kerning_tab(
                    font_index=0,
                    master_id="m1",
                    relevant_limit=1,
                    missing_limit=1,
                    audit_limit=1,
                    per_line=4,
                    glyph_names=["A", "V"],
                )
            )
        )

        self.assertTrue(payload["success"])
        self.assertTrue(payload["openedTab"])
        self.assertEqual(payload["dataset"]["id"], "test_pairs")
        self.assertEqual(payload["counts"]["existingTightIncluded"], 1)
        self.assertEqual(payload["counts"]["existingWideIncluded"], 1)
        self.assertEqual(payload["text"], "proof")

    def test_set_kerning_pair_sets_and_removes_pair(self) -> None:
        module, font = self._load_module()

        set_payload = json.loads(
            asyncio.run(
                module.set_kerning_pair(
                    font_index=0,
                    master_id="m1",
                    left="A",
                    right="T",
                    value=-40,
                )
            )
        )
        remove_payload = json.loads(
            asyncio.run(
                module.set_kerning_pair(
                    font_index=0,
                    master_id="m1",
                    left="A",
                    right="T",
                    value=0,
                )
            )
        )

        self.assertTrue(set_payload["success"])
        self.assertEqual(set_payload["kerning"]["value"], -40)
        self.assertEqual(remove_payload["message"], "Removed kerning for 'A' - 'T'")
        self.assertNotIn("T", font.kerning["m1"]["A"])

    def test_set_kerning_pair_reports_required_arguments_and_bad_font(self) -> None:
        module, _font = self._load_module()

        missing_sides = json.loads(asyncio.run(module.set_kerning_pair(font_index=0, value=-20)))
        missing_value = json.loads(
            asyncio.run(module.set_kerning_pair(font_index=0, left="A", right="V"))
        )
        bad_font = json.loads(
            asyncio.run(module.set_kerning_pair(font_index=2, left="A", right="V", value=-20))
        )

        self.assertEqual(missing_sides["error"], "Both left and right glyph/group names are required")
        self.assertEqual(missing_value["error"], "Kerning value is required")
        self.assertFalse(bad_font["success"])
        self.assertEqual(bad_font["fontIndex"], 2)

    def test_apply_kerning_bumper_refuses_without_dry_run_or_confirm(self) -> None:
        module, _font = self._load_module()

        payload = json.loads(asyncio.run(module.apply_kerning_bumper(font_index=0)))

        self.assertFalse(payload["ok"])
        self.assertIn("confirm=true", payload["error"])

    def test_apply_kerning_bumper_dry_run_reports_changes_without_writing(self) -> None:
        module, _font = self._load_module()
        applied = []
        module._set_kerning_pairs_on_main_thread = lambda *args: applied.append(args)
        module._kerning_bumper_analyze = lambda **kwargs: {
            "warnings": [],
            "collisions": [
                {
                    "left": "A",
                    "right": "V",
                    "kerningValue": -120,
                    "recommendedException": -80,
                    "minGap": -5,
                }
            ],
            "usedTopN": 1,
            "minGap": 5.0,
            "maxDelta": 200,
            "scanMode": "two_pass",
            "scanHeights": [0.25, 0.5, 0.75],
            "denseStep": 10.0,
            "bands": 8,
        }

        payload = json.loads(
            asyncio.run(
                module.apply_kerning_bumper(
                    font_index=0,
                    master_id="m1",
                    pairs=[["A", "V"]],
                    dry_run=True,
                )
            )
        )

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["dryRun"])
        self.assertEqual(payload["counts"]["pairsToApply"], 1)
        self.assertEqual(payload["counts"]["pairsApplied"], 0)
        self.assertEqual(payload["changes"][0]["newKerningValue"], -80)
        self.assertEqual(applied, [])

    def test_apply_kerning_bumper_confirm_writes_only_planned_pairs(self) -> None:
        module, font = self._load_module()
        applied = []
        module._set_kerning_pairs_on_main_thread = lambda *args: applied.append(args)
        module._kerning_bumper_analyze = lambda **kwargs: {
            "warnings": ["scan warning"],
            "collisions": [
                {
                    "left": "A",
                    "right": "V",
                    "kerningValue": -120,
                    "recommendedException": -80,
                    "minGap": -5,
                },
                {
                    "left": "H",
                    "right": "O",
                    "kerningValue": 0,
                    "recommendedException": 0,
                    "minGap": 20,
                },
            ],
            "usedTopN": 2,
            "minGap": 5.0,
            "maxDelta": 200,
            "scanMode": "two_pass",
            "scanHeights": [0.25],
            "denseStep": 10.0,
            "bands": 8,
        }

        payload = json.loads(
            asyncio.run(
                module.apply_kerning_bumper(
                    font_index=0,
                    master_id="m1",
                    pairs=[["A", "V"], ["H", "O"]],
                    confirm=True,
                )
            )
        )

        self.assertTrue(payload["ok"])
        self.assertFalse(payload["dryRun"])
        self.assertEqual(payload["counts"]["pairsToApply"], 1)
        self.assertEqual(payload["counts"]["pairsApplied"], 1)
        self.assertEqual(applied, [(font, "m1", [("A", "V", -80)])])
        self.assertEqual(payload["warnings"], ["scan warning"])


if __name__ == "__main__":
    unittest.main()
