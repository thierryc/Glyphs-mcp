"""Behavior and safety tests for structured Glyphs MCP feedback tools."""

from __future__ import annotations

import asyncio
import importlib.util
import re
from pathlib import Path
import sys
import types
import unittest
from unittest import mock


def _resources_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "Glyphs MCP.glyphsPlugin" / "Contents" / "Resources"


class _FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def decorator(fn):
            self.tools[fn.__name__] = kwargs
            return fn

        return decorator


class _Bounds:
    def __init__(self, width=500, height=700):
        self.size = types.SimpleNamespace(width=width, height=height)


class _Layer:
    def __init__(self, layer_id="M1", name="Regular"):
        self.layerId = layer_id
        self.name = name
        self.width = 600
        self.LSB = 50
        self.RSB = 50
        self.bounds = _Bounds()
        self.anchors = [types.SimpleNamespace(name="top"), types.SimpleNamespace(name="bottom")]
        self.components = [types.SimpleNamespace(componentName="acute")]
        self.shapes = []
        self.parent = None


class _Layers:
    def __init__(self, layers):
        self.values = list(layers)
        self.by_id = {layer.layerId: layer for layer in layers}

    def __getitem__(self, key):
        if isinstance(key, int):
            return self.values[key]
        return self.by_id.get(str(key))

    def __iter__(self):
        return iter(self.values)

    def __len__(self):
        return len(self.values)


class _GlyphCollection:
    def __init__(self, glyphs):
        self.values = list(glyphs)
        self.by_name = {glyph.name: glyph for glyph in glyphs}

    def __getitem__(self, key):
        return self.by_name.get(key)

    def __iter__(self):
        return iter(self.values)

    def __len__(self):
        return len(self.values)


class _Font:
    def __init__(self):
        master = types.SimpleNamespace(id="M1", name="Regular")
        layer = _Layer()
        glyph = types.SimpleNamespace(
            name="A",
            productionName="A",
            unicode="0041",
            category="Letter",
            subCategory="Uppercase",
            layers=_Layers([layer]),
        )
        layer.parent = glyph
        self.familyName = "Feedback Sans"
        self.filepath = None
        self.upm = 1000
        self.masters = [master]
        self.instances = [types.SimpleNamespace(name="Regular")]
        self.selectedFontMaster = master
        self.glyphs = _GlyphCollection([glyph])
        self.selectedLayers = [layer]
        self.features = [
            types.SimpleNamespace(name="ss01", active=True, automatic=False, code="sub A by A.ss01;\npos A V -10;", notes="Name: Alternate A", labels=None),
            types.SimpleNamespace(name="liga", active=True, automatic=True, code="sub f i by fi;", notes="", labels=None),
            types.SimpleNamespace(name="ss02", active=False, automatic=False, code="sub A by A.ss02;", notes="", labels=None),
        ]
        self.opened_tabs = []
        self.save_calls = 0

    def newTab(self, layers):
        self.opened_tabs.append(layers)

    def save(self):
        self.save_calls += 1


class FeedbackToolsTests(unittest.TestCase):
    def _load_module(self, *, fonts=True, glyphs_version=4.0):
        font = _Font()
        glyphs = types.SimpleNamespace(fonts=[font] if fonts else [], versionNumber=glyphs_version, font=font if fonts else None)
        fake_mcp = _FakeMCP()
        state = {"metric": 50, "raise_apply": False, "partial": False, "apply_calls": 0}

        async def apply_spacing(**kwargs):
            current = state["metric"]
            response = {
                "ok": True,
                "summary": {
                    "okCount": 1,
                    "skippedCount": 0,
                    "errorCount": 0,
                    "appliedCount": 0,
                    "dryRun": bool(kwargs.get("dry_run")),
                },
                "results": [{
                    "glyphName": "A",
                    "masterId": "M1",
                    "masterName": "Regular",
                    "status": "ok",
                    "current": {"lsb": current, "rsb": current, "width": 600},
                    "suggested": {"lsb": current + 10, "rsb": current + 10, "width": 600},
                    "delta": {"lsb": 10, "rsb": 10, "width": 0},
                }],
                "applied": [],
            }
            if kwargs.get("confirm") and not kwargs.get("dry_run"):
                state["apply_calls"] += 1
                if state["raise_apply"]:
                    raise RuntimeError("uncertain transport")
                state["metric"] += 10
                response["summary"]["appliedCount"] = 1
                if state["partial"]:
                    response["summary"]["errorCount"] = 1
                response["applied"] = [{"glyphName": "A", "masterId": "M1"}]
            return __import__("json").dumps(response)

        async def apply_kerning_bumper(**kwargs):
            return __import__("json").dumps({
                "ok": True,
                "masterId": kwargs.get("master_id") or "M1",
                "counts": {"pairsRequested": 1, "pairsToApply": 1, "pairsApplied": 1 if kwargs.get("confirm") else 0, "pairsSkippedMissing": 0, "pairsSkippedAlreadySafe": 0},
                "changes": [{"left": "A", "right": "V", "oldKerningValue": -80, "newKerningValue": -60, "delta": 20}],
                "warnings": [],
            })

        async def apply_collinear_handles_smooth(**kwargs):
            return __import__("json").dumps({
                "ok": True,
                "target": {"fontIndex": 0, "glyphName": kwargs.get("glyph_name"), "masterId": kwargs.get("master_id"), "pathIndex": kwargs.get("path_index")},
                "applied": [2],
                "skipped": [],
                "summary": {"analyzedNodes": 1, "appliedCount": 1, "skippedCount": 0, "skippedSummary": {}},
            })

        def parse_substitutions(code):
            matches = re.findall(r"sub\s+(\S+)\s+by\s+(\S+);", code)
            unsupported = len([line for line in code.splitlines() if line.strip() and not re.match(r"sub\s+\S+\s+by\s+\S+;", line.strip())])
            return {
                "substitutions": [{"source": left, "replacement": right} for left, right in matches],
                "unsupportedRuleCount": unsupported,
                "warnings": ["One unsupported rule was preserved as read-only feedback."] if unsupported else [],
            }

        def resolve_font(_glyphs, index):
            all_fonts = list(_glyphs.fonts)
            try:
                return all_fonts[int(index)], all_fonts
            except Exception:
                return None, all_fonts

        helpers = types.SimpleNamespace(
            _font_summary=lambda value, index=None: {"fontIndex": index, "familyName": value.familyName},
            _get_layer_id=lambda layer: layer.layerId,
            _get_left_sidebearing=lambda layer: layer.LSB,
            _get_right_sidebearing=lambda layer: layer.RSB,
            _is_style_set_tag=lambda tag: bool(re.match(r"^ss\d\d$", tag)),
            _layer_display_name=lambda _font, layer: layer.name,
            _open_fonts_from_glyphs=lambda value: list(value.fonts),
            _open_tab_on_main_thread=lambda target_font, layers: target_font.newTab(layers),
            _parse_style_set_substitutions=parse_substitutions,
            _resolve_font_by_index=resolve_font,
            _style_set_name_from_metadata=lambda tag, notes=None, labels=None: (notes or "").replace("Name:", "").strip() or tag,
        )
        module_name = "glyphs_mcp_test_mcp_tools_feedback"
        spec = importlib.util.spec_from_file_location(module_name, _resources_dir() / "mcp_tools_feedback.py")
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        patched = {
            "GlyphsApp": types.SimpleNamespace(Glyphs=glyphs),
            "mcp_app_ui": types.SimpleNamespace(FEEDBACK_RESOURCE_URI="ui://glyphs-mcp/feedback-v1.html"),
            "mcp_runtime": types.SimpleNamespace(mcp=fake_mcp),
            "mcp_tool_helpers": helpers,
            "mcp_tools_spacing": types.SimpleNamespace(apply_spacing=apply_spacing),
            "mcp_tools_kerning": types.SimpleNamespace(apply_kerning_bumper=apply_kerning_bumper),
            "mcp_tools_smoothness": types.SimpleNamespace(apply_collinear_handles_smooth=apply_collinear_handles_smooth),
            "versioning": types.SimpleNamespace(get_runtime_info=lambda: {"version": "0.8.0", "runtimeId": "0.8.0+test"}),
        }
        with mock.patch.dict(sys.modules, patched):
            sys.modules.pop(module_name, None)
            assert spec.loader is not None
            spec.loader.exec_module(module)
        return module, font, state, fake_mcp

    @staticmethod
    def _data(result):
        return result.structured_content

    def test_tool_metadata_links_every_tool_to_the_panel_with_safety_annotations(self) -> None:
        _module, _font, _state, fake_mcp = self._load_module()

        self.assertEqual(len(fake_mcp.tools), 9)
        for name, metadata in fake_mcp.tools.items():
            self.assertEqual(metadata["meta"]["ui"]["resourceUri"], "ui://glyphs-mcp/feedback-v1.html")
            self.assertIsInstance(metadata["output_schema"], dict)
            self.assertIn("readOnlyHint", metadata["annotations"])
        self.assertEqual(fake_mcp.tools["apply_feedback_plan"]["meta"]["ui"]["visibility"], ["app"])
        self.assertTrue(fake_mcp.tools["apply_feedback_plan"]["annotations"]["destructiveHint"])
        self.assertEqual(fake_mcp.tools["open_feedback_target"]["meta"]["ui"]["visibility"], ["app"])

    def test_status_font_glyph_and_features_return_shared_schema_without_paths(self) -> None:
        module, _font, _state, _fake_mcp = self._load_module()

        results = [
            asyncio.run(module.show_glyphs_status()),
            asyncio.run(module.show_font_feedback()),
            asyncio.run(module.show_glyph_feedback()),
            asyncio.run(module.show_opentype_features()),
        ]

        for result in results:
            data = self._data(result)
            for key in ("schemaVersion", "kind", "status", "title", "summary", "target", "items", "warnings", "actions", "progress", "result"):
                self.assertIn(key, data)
            self.assertLessEqual(len(data["actions"]), 2)
            self.assertNotIn("filePath", data.get("target", {}))
            self.assertNotIn("outline", str(data).lower())
        glyph = self._data(results[2])
        self.assertEqual(glyph["target"]["glyphName"], "A")
        self.assertEqual(glyph["kind"], "glyph")
        features = self._data(results[3])
        self.assertEqual([item["label"] for item in features["items"]], ["Alternate A", "liga"])
        self.assertTrue(any("inactive" in str(warning).lower() for warning in features["warnings"]))
        self.assertTrue(any("unsupported" in str(warning).lower() for warning in features["warnings"]))
        self.assertNotIn("code", features["items"][0])

        font_card = self._data(results[1])
        self.assertTrue(any("not been saved" in str(warning).lower() for warning in font_card["warnings"]))

    def test_status_supports_a_glyphs_3_host(self) -> None:
        module, _font, _state, _fake_mcp = self._load_module(glyphs_version=3.5)

        data = self._data(asyncio.run(module.show_glyphs_status()))

        glyphs_item = next(item for item in data["items"] if item["label"] == "Glyphs")
        self.assertEqual(glyphs_item["value"], 3.5)

    def test_features_can_include_inactive_and_code_only_when_requested(self) -> None:
        module, _font, _state, _fake_mcp = self._load_module()

        data = self._data(asyncio.run(module.show_opentype_features(include_inactive=True, include_code=True)))

        self.assertEqual(len(data["items"]), 3)
        self.assertEqual(data["items"][0]["code"], "sub A by A.ss01;\npos A V -10;")

    def test_no_font_and_missing_selection_are_normalized_errors_with_retry(self) -> None:
        no_font_module, _font, _state, _fake_mcp = self._load_module(fonts=False)
        font_error = self._data(asyncio.run(no_font_module.show_font_feedback()))
        self.assertEqual(font_error["error"]["code"], "no_font_open")
        self.assertEqual(font_error["actions"][0]["label"], "Refresh")

        module, font, _state, _fake_mcp = self._load_module()
        font.selectedLayers = []
        glyph_error = self._data(asyncio.run(module.show_glyph_feedback()))
        self.assertEqual(glyph_error["error"]["code"], "target_not_found")
        self.assertTrue(glyph_error["error"]["recoverable"])

        invalid = self._data(asyncio.run(module.show_font_feedback(font_index=9)))
        self.assertEqual(invalid["error"]["code"], "target_not_found")

    def test_preview_is_non_mutating_and_apply_requires_confirmation(self) -> None:
        module, font, state, _fake_mcp = self._load_module()

        preview = self._data(asyncio.run(module.preview_spacing_feedback(glyph_names=["A"])))
        self.assertEqual(preview["kind"], "dry_run")
        self.assertEqual(state["metric"], 50)
        self.assertEqual(state["apply_calls"], 0)
        self.assertTrue(preview["actions"][0]["requiresConfirmation"])
        plan_id = preview["actions"][0]["arguments"]["plan_id"]

        declined = self._data(asyncio.run(module.apply_feedback_plan(plan_id, confirm=False)))
        self.assertEqual(declined["error"]["code"], "validation_failed")
        self.assertIn(plan_id, module._plans)

        applied = self._data(asyncio.run(module.apply_feedback_plan(plan_id, confirm=True)))
        self.assertEqual(applied["status"], "success")
        self.assertEqual(state["metric"], 60)
        self.assertEqual(state["apply_calls"], 1)
        self.assertEqual(font.save_calls, 0)

        repeated = self._data(asyncio.run(module.apply_feedback_plan(plan_id, confirm=True)))
        self.assertEqual(repeated["error"]["code"], "plan_expired")
        self.assertEqual(state["apply_calls"], 1)

    def test_stale_expired_capacity_partial_and_uncertain_plans(self) -> None:
        module, font, state, _fake_mcp = self._load_module()

        preview = self._data(asyncio.run(module.preview_spacing_feedback(glyph_names=["A"])))
        stale_id = preview["actions"][0]["arguments"]["plan_id"]
        state["metric"] = 55
        stale = self._data(asyncio.run(module.apply_feedback_plan(stale_id, confirm=True)))
        self.assertEqual(stale["error"]["code"], "stale_plan")
        self.assertNotIn(stale_id, module._plans)

        state["metric"] = 50
        preview = self._data(asyncio.run(module.preview_spacing_feedback(glyph_names=["A"])))
        expired_id = preview["actions"][0]["arguments"]["plan_id"]
        module._plans[expired_id].created_at -= module.PLAN_TTL_SECONDS + 1
        expired = self._data(asyncio.run(module.apply_feedback_plan(expired_id, confirm=True)))
        self.assertEqual(expired["error"]["code"], "plan_expired")

        module._reset_feedback_plans_for_tests()
        for index in range(module.PLAN_CAPACITY + 5):
            module._store_plan("spacing", {"font_index": index}, str(index))
        self.assertEqual(len(module._plans), module.PLAN_CAPACITY)

        module._reset_feedback_plans_for_tests()
        preview = self._data(asyncio.run(module.preview_spacing_feedback(glyph_names=["A"])))
        partial_id = preview["actions"][0]["arguments"]["plan_id"]
        state["partial"] = True
        partial = self._data(asyncio.run(module.apply_feedback_plan(partial_id, confirm=True)))
        self.assertEqual(partial["status"], "partial")
        self.assertEqual(partial["error"]["code"], "partial_failure")
        self.assertEqual(font.save_calls, 0)

        state["partial"] = False
        preview = self._data(asyncio.run(module.preview_spacing_feedback(glyph_names=["A"])))
        uncertain_id = preview["actions"][0]["arguments"]["plan_id"]
        state["raise_apply"] = True
        with self.assertLogs(module.logger, level="ERROR"):
            uncertain = self._data(asyncio.run(module.apply_feedback_plan(uncertain_id, confirm=True)))
        self.assertEqual(uncertain["error"]["code"], "apply_failed")
        self.assertNotIn(uncertain_id, module._plans)
        self.assertEqual(uncertain["actions"][0]["label"], "New Dry Run")
        self.assertEqual(font.save_calls, 0)

    def test_all_preview_adapters_are_dry_runs_and_return_apply_plans(self) -> None:
        module, _font, _state, _fake_mcp = self._load_module()

        kerning = self._data(asyncio.run(module.preview_kerning_feedback(master_id="M1", pairs=[["A", "V"]])))
        smoothing = self._data(asyncio.run(module.preview_handle_smoothing_feedback(glyph_name="A", master_id="M1", path_index=0)))

        self.assertEqual(kerning["progress"]["changed"], 1)
        self.assertEqual(smoothing["progress"]["changed"], 1)
        self.assertEqual(kerning["actions"][0]["tool"], "apply_feedback_plan")
        self.assertEqual(smoothing["actions"][0]["tool"], "apply_feedback_plan")

    def test_open_target_accepts_only_resolved_open_objects(self) -> None:
        module, font, _state, _fake_mcp = self._load_module()

        opened = self._data(asyncio.run(module.open_feedback_target(glyph_names=["A"], master_id="M1")))
        self.assertEqual(opened["status"], "success")
        self.assertEqual(len(font.opened_tabs), 1)

        missing = self._data(asyncio.run(module.open_feedback_target(glyph_names=["/tmp/font.glyphs"])))
        bad_master = self._data(asyncio.run(module.open_feedback_target(glyph_names=["A"], master_id="missing")))
        arbitrary_url = self._data(asyncio.run(module.open_feedback_target(glyph_names=["https://example.com"])))
        self.assertEqual(missing["error"]["code"], "target_not_found")
        self.assertEqual(bad_master["error"]["code"], "target_not_found")
        self.assertEqual(arbitrary_url["error"]["code"], "target_not_found")
        self.assertEqual(len(font.opened_tabs), 1)
        self.assertEqual(font.save_calls, 0)

    def test_feedback_module_never_calls_a_font_save_api(self) -> None:
        source = (_resources_dir() / "mcp_tools_feedback.py").read_text(encoding="utf-8")

        self.assertNotIn(".save(", source)
        self.assertNotIn("_save_font", source)


if __name__ == "__main__":
    unittest.main()
