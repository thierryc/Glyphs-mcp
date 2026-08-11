"""Structured-result envelope conformance and legacy-text compatibility."""

from __future__ import annotations

import importlib
import json
import sys
import unittest
from pathlib import Path


def _resources() -> Path:
    return Path(__file__).resolve().parent.parent / "Glyphs MCP.glyphsPlugin" / "Contents" / "Resources"


class ToolResultSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(_resources()))
        cls.module = importlib.import_module("tool_result_schemas")

    @staticmethod
    def _text(result) -> str:
        return "".join(getattr(item, "text", "") for item in result.content)

    def _assert_envelope(self, result, *, mode, status, ok):
        value = result.structured_content
        self.assertEqual(value["resultSchemaVersion"], 1)
        self.assertEqual(value["mode"], mode)
        self.assertEqual(value["status"], status)
        self.assertIs(value["ok"], ok)
        self.assertEqual(
            set(value),
            {"resultSchemaVersion", "ok", "tool", "mode", "status", "target", "summary", "warnings", "data", "error"},
        )

    def test_success_preserves_exact_legacy_json_text(self) -> None:
        raw = json.dumps({"ok": True, "target": {"glyphName": "a"}, "summary": {"count": 2}})
        result = self.module.workflow_tool_result("review_curve_quality", "read", raw, {})

        self._assert_envelope(result, mode="review", status="success", ok=True)
        self.assertEqual(self._text(result), raw)

    def test_validation_error_has_normalized_recoverable_error(self) -> None:
        raw = json.dumps({"ok": False, "error": "path_index is required"})
        result = self.module.workflow_tool_result("review_curve_quality", "read", raw, {})

        self._assert_envelope(result, mode="review", status="error", ok=False)
        self.assertEqual(result.structured_content["error"]["code"], "tool_error")
        self.assertTrue(result.structured_content["error"]["recoverable"])

    def test_dry_run_and_confirmation_modes_are_distinct(self) -> None:
        raw = json.dumps({"ok": True})
        dry_run = self.module.workflow_tool_result(
            "accept_outline_candidate_session", "edit", raw, {"dry_run": True, "confirm": False}
        )
        confirmed = self.module.workflow_tool_result(
            "accept_outline_candidate_session", "edit", raw, {"dry_run": False, "confirm": True}
        )

        self._assert_envelope(dry_run, mode="dry_run", status="success", ok=True)
        self._assert_envelope(confirmed, mode="confirmed", status="success", ok=True)

    def test_stale_candidate_partial_and_rollback_are_bounded(self) -> None:
        stale = self.module.workflow_tool_result(
            "review_outline_candidate_session",
            "read",
            json.dumps({"ok": False, "reason": "stale_source", "target": {"sessionId": "s1"}}),
            {},
        )
        partial = self.module.workflow_tool_result(
            "review_spacing",
            "read",
            json.dumps({"ok": True, "status": "partial", "warnings": [{"code": "glyph_skipped"}]}),
            {},
        )
        rollback = self.module.workflow_tool_result(
            "apply_tunni_balance",
            "edit",
            json.dumps({"ok": False, "error": "verification failed", "rollback": {"attempted": True, "succeeded": True}}),
            {"confirm": True},
        )

        self._assert_envelope(stale, mode="review", status="error", ok=False)
        self.assertEqual(stale.structured_content["error"]["code"], "stale_source")
        self._assert_envelope(partial, mode="review", status="partial", ok=True)
        self.assertEqual(partial.structured_content["warnings"][0]["message"], "glyph skipped")
        self._assert_envelope(rollback, mode="confirmed", status="error", ok=False)
        self.assertTrue(rollback.structured_content["data"]["rollback"]["succeeded"])

    def test_ui_mode_and_warning_normalization(self) -> None:
        result = self.module.workflow_tool_result(
            "set_curve_review_overlay",
            "ui",
            json.dumps({"ok": True, "warnings": [{"code": "stroke_cap", "message": "Stroke cap reached."}]}),
            {},
        )

        self._assert_envelope(result, mode="ui", status="warning", ok=True)
        self.assertEqual(result.structured_content["warnings"][0]["code"], "stroke_cap")


if __name__ == "__main__":
    unittest.main()
