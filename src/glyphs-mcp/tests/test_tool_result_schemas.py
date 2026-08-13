"""Structured-result envelope conformance and legacy-text compatibility."""

from __future__ import annotations

import importlib
import json
import sys
import unittest
from pathlib import Path

from jsonschema import validate


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

    def test_outline_node_update_uses_outline_envelope_and_legacy_text(self) -> None:
        raw = json.dumps(
            {
                "ok": True,
                "target": {"glyphName": "C", "masterId": "M1"},
                "summary": {"changedNodeCount": 2, "verified": True},
                "verification": {"succeeded": True},
                "fontSaved": False,
            }
        )

        result = self.module.workflow_tool_result(
            "update_glyph_node_positions",
            "edit",
            raw,
            {"dry_run": False, "confirm": True},
        )

        self._assert_envelope(result, mode="confirmed", status="success", ok=True)
        self.assertEqual(self._text(result), raw)
        validate(result.structured_content, self.module.schema_for("outline"))
        self.assertTrue(result.structured_content["data"]["verification"]["succeeded"])

    def test_litsquare_schema_accepts_direct_scopes_and_confirmed_write_fields(self) -> None:
        scope = {
            "state": "valid",
            "label": "Valid v1",
            "schemaVersion": 1,
            "updatedAt": "2026-08-11T18:30:00Z",
            "value": {"schemaVersion": 1, "updatedAt": "2026-08-11T18:30:00Z"},
            "errors": [],
            "warnings": [],
        }
        raw = json.dumps(
            {
                "ok": True,
                "target": {"fontIndex": 0, "glyphName": "A", "layerId": "M1"},
                "summary": {"changed": True},
                "scopes": {"font": scope, "glyph": scope, "layer": scope},
                "effectiveSettings": {"values": {"grid": 24}, "provenance": {"grid": "font"}},
                "fontSaved": False,
                "undoGrouped": True,
                "undoRegistered": True,
            }
        )
        result = self.module.workflow_tool_result(
            "patch_litsquare_metadata",
            "edit",
            raw,
            {"dry_run": False, "confirm": True},
        )
        self._assert_envelope(result, mode="confirmed", status="success", ok=True)
        validate(result.structured_content, self.module.schema_for("litsquare"))
        self.assertFalse(result.structured_content["data"]["fontSaved"])

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

    def test_document_audit_schema_accepts_idle_active_and_error_results(self) -> None:
        audit = importlib.import_module("document_change_audit")
        schema = self.module.schema_for("document-audit")
        ledger = audit.DocumentChangeLedger()
        idle = ledger.snapshot()
        validate(idle, schema)

        ledger.record(
            {
                "objectId": 42,
                "fontIndex": 0,
                "familyName": "Audit Sans",
                "filePath": None,
                "fileState": "Unsaved",
            },
            {
                "tool": "update_glyph_metrics",
                "title": "Update Glyph Metrics",
                "effect": "edit",
                "outcome": "changed",
                "target": {"glyphName": "a"},
                "summary": "Changed one width.",
            },
        )
        active = ledger.snapshot()
        validate(active, schema)

        error = dict(active)
        error.update(
            {
                "ok": False,
                "status": "error",
                "entries": [],
                "error": {
                    "code": "tracked_document_mismatch",
                    "message": "Requested font is not tracked.",
                    "recoverable": True,
                },
            }
        )
        validate(error, schema)


if __name__ == "__main__":
    unittest.main()
