"""Tests for the native curvature Reporter MCP controls."""

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
        / "mcp_tools_curve_overlay.py"
    )


class _FakeMCP:
    def tool(self):
        return lambda fn: fn


class _Reporter:
    def __init__(self) -> None:
        self.last_draw = {
            "glyphName": "a",
            "layerId": "m1",
            "strokeCount": 17,
        }

    def overlayStateSnapshot(self):
        return {
            "lastDraw": dict(self.last_draw),
            "lastError": None,
        }


class McpToolsCurveOverlayTests(unittest.TestCase):
    def _load_module(self, *, include_reporter=True, expose_actions=True, update_active=True):
        reporter = _Reporter()
        glyphs = types.SimpleNamespace(
            reporters=[reporter] if include_reporter else [],
            activeReporters=[],
            redrawCount=0,
        )

        # The wrapper compares the public class name. Give the fake the exact
        # name while retaining a tiny Python implementation.
        reporter.__class__ = type(
            "GlyphsMCPCurvatureReporter",
            (_Reporter,),
            {},
        )

        if expose_actions:
            def activate(value):
                if update_active and value not in glyphs.activeReporters:
                    glyphs.activeReporters.append(value)

            def deactivate(value):
                if update_active and value in glyphs.activeReporters:
                    glyphs.activeReporters.remove(value)

            glyphs.activateReporter = activate
            glyphs.deactivateReporter = deactivate

        def redraw():
            glyphs.redrawCount += 1

        glyphs.redraw = redraw
        dispatch_count = {"value": 0}

        def run_on_main_thread(callback):
            dispatch_count["value"] += 1
            return callback()

        spec = importlib.util.spec_from_file_location(
            "glyphs_mcp_test_mcp_tools_curve_overlay",
            _module_path(),
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(
            sys.modules,
            {
                "GlyphsApp": types.SimpleNamespace(Glyphs=glyphs),
                "glyphs_curve_reporter": types.SimpleNamespace(
                    REPORTER_CLASS_NAME="GlyphsMCPCurvatureReporter",
                    REPORTER_MENU_PATH="View > Show Glyphs MCP Curvature",
                ),
                "mcp_runtime": types.SimpleNamespace(mcp=_FakeMCP()),
                "mcp_tool_helpers": types.SimpleNamespace(
                    _run_on_main_thread=run_on_main_thread,
                    _safe_json=json.dumps,
                ),
            },
        ):
            spec.loader.exec_module(module)
        return module, glyphs, reporter, dispatch_count

    def test_state_reports_availability_activity_and_last_draw(self) -> None:
        module, glyphs, reporter, dispatch = self._load_module()
        glyphs.activeReporters.append(reporter)

        payload = json.loads(asyncio.run(module.get_curve_review_overlay_state()))

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["available"])
        self.assertTrue(payload["enabled"])
        self.assertEqual(payload["lastDraw"]["glyphName"], "a")
        self.assertFalse(payload["fontChanged"])
        self.assertFalse(payload["fontSaved"])
        self.assertEqual(dispatch["value"], 1)

    def test_enable_and_disable_are_verified_and_redrawn(self) -> None:
        module, glyphs, _reporter, dispatch = self._load_module()

        enabled = json.loads(asyncio.run(module.set_curve_review_overlay(True)))
        disabled = json.loads(asyncio.run(module.set_curve_review_overlay(False)))

        self.assertTrue(enabled["ok"])
        self.assertFalse(enabled["enabledBefore"])
        self.assertTrue(enabled["enabledAfter"])
        self.assertTrue(disabled["ok"])
        self.assertTrue(disabled["enabledBefore"])
        self.assertFalse(disabled["enabledAfter"])
        self.assertEqual(glyphs.redrawCount, 2)
        self.assertEqual(dispatch["value"], 2)

    def test_invalid_boolean_is_rejected_before_main_thread_dispatch(self) -> None:
        module, _glyphs, _reporter, dispatch = self._load_module()

        for invalid in (1, 0, "true", None):
            payload = json.loads(asyncio.run(module.set_curve_review_overlay(invalid)))
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error"], "enabled must be a boolean")
        self.assertEqual(dispatch["value"], 0)

    def test_missing_reporter_returns_stable_restart_guidance(self) -> None:
        module, glyphs, _reporter, _dispatch = self._load_module(include_reporter=False)

        payload = json.loads(asyncio.run(module.set_curve_review_overlay(True)))

        self.assertFalse(payload["ok"])
        self.assertFalse(payload["available"])
        self.assertIn("Restart Glyphs", payload["error"])
        self.assertEqual(glyphs.redrawCount, 0)

    def test_missing_activation_api_does_not_claim_success(self) -> None:
        module, glyphs, _reporter, _dispatch = self._load_module(expose_actions=False)

        payload = json.loads(asyncio.run(module.set_curve_review_overlay(True)))

        self.assertFalse(payload["ok"])
        self.assertTrue(payload["available"])
        self.assertIn("activateReporter", payload["error"])
        self.assertEqual(glyphs.redrawCount, 0)

    def test_failed_state_readback_is_reported(self) -> None:
        module, glyphs, _reporter, _dispatch = self._load_module(update_active=False)

        payload = json.loads(asyncio.run(module.set_curve_review_overlay(True)))

        self.assertFalse(payload["ok"])
        self.assertFalse(payload["enabledAfter"])
        self.assertEqual(payload["warnings"][0]["code"], "reporter_state_verification_failed")
        self.assertEqual(glyphs.redrawCount, 1)


if __name__ == "__main__":
    unittest.main()
