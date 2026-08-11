"""Regression tests for MCP spacing tools."""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
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
            save_calls=0,
        )
        font.save = mock.Mock(side_effect=lambda: setattr(font, "save_calls", font.save_calls + 1))

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
            DEFAULTS={
                "area": 400.0,
                "depth": 15.0,
                "over": 0.0,
                "frequency": 5.0,
                "referenceGlyph": "auto",
                "tabularMode": "auto",
            },
            SPACING_PARAM_FIELDS=["area", "depth", "over", "frequency"],
            SPACING_PARAM_KEYS_CANONICAL={"area": "a", "depth": "d", "over": "o", "frequency": "f"},
            SPACING_PARAM_KEYS_GMCP_LEGACY={"area": "ga", "depth": "gd", "over": "go", "frequency": "gf"},
            SPACING_PARAM_KEYS_PARAM_LEGACY={"area": "pa", "depth": "pd", "over": "po", "frequency": "pf"},
            resolve_param_precedence=lambda **kwargs: kwargs.get("fallback"),
            normalize_guards=lambda value: {
                "negativeBearingPolicy": "guarded",
                **(value or {}),
            },
            compute_suggestion_for_layer=lambda **kwargs: {
                "status": "ok",
                "glyphName": "A",
                "masterId": "m1",
                "masterName": "Master 1",
                "reference": {"yMin": 0.0, "yMax": 500.0, "overUnits": 0.0},
                "referenceMode": "auto",
                "resolvedReferenceGlyph": "H",
                "current": {"width": 300, "lsb": 40, "rsb": 60},
                "proposed": {"lsb": 50, "rsb": 70, "width": 320},
                "suggested": {"lsb": 50, "rsb": 70, "width": 320},
                "measured": {"lFullExtreme": 10.0, "rFullExtreme": 210.0},
                "negativeBearingAssessment": {
                    "leftEm": 0.05,
                    "rightEm": 0.07,
                    "severity": "informational",
                    "reason": "safe",
                    "exempted": False,
                },
                "applicationAssessment": {
                    "disposition": "ready",
                    "eligible": True,
                    "requiredOverrides": [],
                    "userOverride": None,
                },
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
                "tool_registration": types.SimpleNamespace(glyphs_tool=lambda *_args, **_kwargs: (lambda fn: fn)),
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

    def test_public_signatures_expose_guards_overrides_and_auto_guides(self) -> None:
        module, _layer, _font, _master = self._load_module()

        self.assertIn("guards", inspect.signature(module.review_spacing).parameters)
        apply_params = inspect.signature(module.apply_spacing).parameters
        self.assertIn("guards", apply_params)
        self.assertIn("overrides", apply_params)
        self.assertEqual(inspect.signature(module.set_spacing_guides).parameters["reference_glyph"].default, "auto")

    def test_review_and_apply_dry_run_return_equivalent_guard_assessments(self) -> None:
        module, _layer, _font, _master = self._load_module()

        review = json.loads(
            asyncio.run(module.review_spacing(font_index=0, glyph_names=["A"], master_id="m1"))
        )
        dry_run = json.loads(
            asyncio.run(
                module.apply_spacing(
                    font_index=0,
                    glyph_names=["A"],
                    master_id="m1",
                    dry_run=True,
                )
            )
        )

        self.assertEqual(
            review["results"][0]["negativeBearingAssessment"],
            dry_run["results"][0]["negativeBearingAssessment"],
        )
        self.assertEqual(
            review["results"][0]["applicationAssessment"]["disposition"],
            dry_run["results"][0]["applicationAssessment"]["disposition"],
        )

    def test_mutating_apply_refuses_blocked_result_without_named_override(self) -> None:
        module, layer, font, _master = self._load_module()
        original_compute = module.spacing_engine.compute_suggestion_for_layer

        def blocked_compute(**kwargs):
            result = dict(original_compute(**kwargs))
            result["proposed"] = {"width": 100, "lsb": -120, "rsb": -120}
            result["suggested"] = dict(result["proposed"])
            result["negativeBearingAssessment"] = {
                "leftEm": -0.12,
                "rightEm": -0.12,
                "severity": "blocked",
                "reason": "Extreme negative bearing on an ordinary upright base glyph",
                "exempted": False,
            }
            result["applicationAssessment"] = {
                "disposition": "blocked",
                "eligible": False,
                "requiredOverrides": ["blockedGlyphs"],
                "userOverride": None,
            }
            return result

        module.spacing_engine.compute_suggestion_for_layer = blocked_compute
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

        self.assertEqual(payload["summary"]["blockedCount"], 1)
        self.assertEqual(payload["summary"]["refusedCount"], 1)
        self.assertEqual(payload["summary"]["appliedCount"], 0)
        self.assertEqual(layer.leftSideBearing, 40.0)
        self.assertEqual(layer.rightSideBearing, 60.0)
        font.save.assert_not_called()

    def test_named_block_override_is_applied_and_recorded(self) -> None:
        module, layer, font, _master = self._load_module()
        original_compute = module.spacing_engine.compute_suggestion_for_layer

        def blocked_compute(**kwargs):
            result = dict(original_compute(**kwargs))
            result["applicationAssessment"] = {
                "disposition": "blocked",
                "eligible": False,
                "requiredOverrides": ["blockedGlyphs"],
                "userOverride": None,
            }
            return result

        module.spacing_engine.compute_suggestion_for_layer = blocked_compute
        payload = json.loads(
            asyncio.run(
                module.apply_spacing(
                    font_index=0,
                    glyph_names=["A"],
                    master_id="m1",
                    overrides={"blockedGlyphs": ["A"]},
                    confirm=True,
                )
            )
        )

        self.assertEqual(payload["summary"]["appliedCount"], 1)
        self.assertEqual(payload["summary"]["overrideCount"], 1)
        self.assertEqual(payload["results"][0]["applicationAssessment"]["disposition"], "overridden")
        self.assertEqual(payload["overrides"]["used"][0]["type"], "blocked_outlier")
        self.assertEqual(layer.leftSideBearing, 50.0)
        self.assertEqual(layer.rightSideBearing, 70.0)
        font.save.assert_not_called()

    def test_manual_review_result_requires_separate_named_approval(self) -> None:
        module, layer, _font, _master = self._load_module()
        original_compute = module.spacing_engine.compute_suggestion_for_layer

        def manual_compute(**kwargs):
            result = dict(original_compute(**kwargs))
            result["applicationAssessment"] = {
                "disposition": "manual_review",
                "eligible": False,
                "requiredOverrides": ["manualReviewGlyphs"],
                "userOverride": None,
            }
            return result

        module.spacing_engine.compute_suggestion_for_layer = manual_compute
        refused = json.loads(
            asyncio.run(
                module.apply_spacing(font_index=0, glyph_names=["A"], master_id="m1", confirm=True)
            )
        )
        approved = json.loads(
            asyncio.run(
                module.apply_spacing(
                    font_index=0,
                    glyph_names=["A"],
                    master_id="m1",
                    overrides={"manualReviewGlyphs": ["A"]},
                    confirm=True,
                )
            )
        )

        self.assertEqual(refused["summary"]["appliedCount"], 0)
        self.assertEqual(approved["summary"]["appliedCount"], 1)
        self.assertEqual(approved["overrides"]["used"][0]["type"], "manual_review_approval")
        self.assertEqual(layer.leftSideBearing, 50.0)

    def test_legacy_clamp_arguments_still_work_without_becoming_default(self) -> None:
        module, _layer, _font, _master = self._load_module()
        payload = json.loads(
            asyncio.run(
                module.apply_spacing(
                    font_index=0,
                    glyph_names=["A"],
                    master_id="m1",
                    clamp={"maxDeltaLSB": 80, "minLSB": -50},
                    dry_run=True,
                )
            )
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["results"][0]["clampAssessment"]["kind"], "absolute_font_units")

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
                    reference_glyph="auto",
                    style="band",
                    dry_run=True,
                )
            )
        )

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["dryRun"])
        self.assertEqual(payload["summary"]["addedCount"], 2)
        self.assertEqual(payload["results"][0]["referenceGlyph"], "H")
        self.assertEqual(payload["results"][0]["referenceMode"], "auto")
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
