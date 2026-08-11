"""Tests for document-change observation and the public overview tool."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest import mock


def _resources():
    return Path(__file__).resolve().parent.parent / "Glyphs MCP.glyphsPlugin" / "Contents" / "Resources"


class _Font:
    def __init__(self, name, path=None):
        self.familyName = name
        self.filepath = path


class DocumentChangeToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(_resources()))
        import document_change_audit
        import tool_catalog

        cls.audit = document_change_audit
        cls.catalog = tool_catalog

    def setUp(self):
        self.audit.DOCUMENT_CHANGE_LEDGER.reset()
        self.fonts = [_Font("Audit Sans")]
        glyphs = types.SimpleNamespace(fonts=self.fonts, font=self.fonts[0])
        observers = []

        def _resolve(_glyphs, index):
            try:
                return self.fonts[index], self.fonts
            except Exception:
                return None, self.fonts

        helper = types.SimpleNamespace(
            _font_object_id=id,
            _open_fonts_from_glyphs=lambda _glyphs: list(self.fonts),
            _resolve_font_by_index=_resolve,
        )
        registration = types.SimpleNamespace(
            glyphs_tool=lambda: (lambda function: function),
            register_tool_result_observer=lambda observer: observers.append(observer),
        )
        glyphs_app = types.ModuleType("GlyphsApp")
        glyphs_app.Glyphs = glyphs
        module_name = "glyphs_mcp_test_document_changes_{}".format(id(self))
        spec = importlib.util.spec_from_file_location(module_name, _resources() / "mcp_tools_document_changes.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(
            sys.modules,
            {
                "GlyphsApp": glyphs_app,
                "mcp_tool_helpers": helper,
                "tool_registration": registration,
            },
        ):
            spec.loader.exec_module(module)
        self.module = module
        self.assertEqual(observers, [module.observe_document_change])

    @staticmethod
    def _entry(name, effect="edit", title="Mutation"):
        return types.SimpleNamespace(name=name, effect=effect, title=title)

    def test_every_catalog_edit_and_save_tool_has_an_explicit_adapter(self):
        expected = {
            entry.name
            for entry in self.catalog.active_entries()
            if entry.effect in {"edit", "save"}
        }
        self.assertEqual(self.module.AUDITED_EDIT_SAVE_TOOLS, expected)
        expected_code = {
            entry.name for entry in self.catalog.active_entries() if entry.effect == "code"
        }
        self.assertEqual(self.module.AUDITED_CODE_TOOLS, expected_code)

    def test_confirmed_change_is_recorded_and_payload_is_redacted(self):
        result = json.dumps(
            {
                "ok": True,
                "changed": True,
                "message": "Changed one layer.",
                "target": {"glyphName": "a", "masterId": "M1"},
            }
        )
        self.module.observe_document_change(
            entry=self._entry("apply_collinear_handles_smooth", title="Smooth Handles"),
            arguments={
                "font_index": 0,
                "confirm": True,
                "glyph_name": "a",
                "paths_data": "secret outline payload",
                "code": "secret code",
            },
            result=result,
        )
        snapshot = self.audit.DOCUMENT_CHANGE_LEDGER.snapshot()
        self.assertEqual(snapshot["counts"]["changed"], 1)
        encoded = json.dumps(snapshot)
        self.assertNotIn("secret outline payload", encoded)
        self.assertNotIn("secret code", encoded)
        self.assertEqual(snapshot["entries"][0]["target"]["glyphName"], "a")

    def test_dry_run_and_unconfirmed_plan_are_not_recorded(self):
        entry = self._entry("apply_spacing")
        self.module.observe_document_change(
            entry=entry,
            arguments={"font_index": 0, "dry_run": True, "confirm": False},
            result=json.dumps({"ok": True}),
        )
        self.module.observe_document_change(
            entry=entry,
            arguments={"font_index": 0, "dry_run": False, "confirm": False},
            result=json.dumps({"ok": False, "error": "confirmation required"}),
        )
        self.assertEqual(self.audit.DOCUMENT_CHANGE_LEDGER.snapshot()["status"], "idle")

    def test_reads_previews_ui_and_exports_are_not_recorded(self):
        for name, effect in (
            ("get_glyph_details", "read"),
            ("preview_tunni_balance_candidate", "ui"),
            ("generate_kerning_tab", "ui"),
            ("ExportDesignspaceAndUFO", "files"),
        ):
            self.module.observe_document_change(
                entry=self._entry(name, effect=effect),
                arguments={"font_index": 0},
                result=json.dumps({"ok": True}),
            )
        self.assertEqual(self.audit.DOCUMENT_CHANGE_LEDGER.snapshot()["status"], "idle")

    def test_proved_no_action_is_not_recorded_but_save_is(self):
        self.module.observe_document_change(
            entry=self._entry("update_glyph_metrics"),
            arguments={"font_index": 0, "glyph_name": "a"},
            result=json.dumps({"ok": True, "changedCount": 0}),
        )
        self.assertEqual(self.audit.DOCUMENT_CHANGE_LEDGER.snapshot()["status"], "idle")
        self.fonts[0].filepath = "/tmp/AuditSans.glyphs"
        self.module.observe_document_change(
            entry=self._entry("save_font", effect="save", title="Save Font"),
            arguments={"font_index": 0, "path": "/tmp/AuditSans.glyphs"},
            result=json.dumps({"success": True, "path": "/tmp/AuditSans.glyphs"}),
        )
        snapshot = self.audit.DOCUMENT_CHANGE_LEDGER.snapshot()
        self.assertEqual(snapshot["counts"]["no_change"], 0)
        self.assertEqual(snapshot["counts"]["saved"], 1)
        self.assertEqual(snapshot["target"]["filePath"], "/tmp/AuditSans.glyphs")
        self.assertEqual(snapshot["lastSave"]["filePath"], "/tmp/AuditSans.glyphs")

    def test_missing_glyph_rejection_does_not_start_a_session(self):
        self.module.observe_document_change(
            entry=self._entry("delete_glyph", title="Delete Glyph"),
            arguments={"font_index": 0, "glyph_name": "glyphsMCPDoesNotExist"},
            result=json.dumps(
                {
                    "success": False,
                    "changed": False,
                    "deletedCount": 0,
                    "error": "Glyph 'glyphsMCPDoesNotExist' not found",
                }
            ),
        )
        snapshot = self.audit.DOCUMENT_CHANGE_LEDGER.snapshot()
        self.assertEqual(snapshot["status"], "idle")
        self.assertEqual(snapshot["entries"], [])
        self.assertEqual(snapshot["counts"]["failed"], 0)

    def test_failed_confirmed_attempt_and_opaque_code_are_distinct(self):
        self.module.observe_document_change(
            entry=self._entry("apply_spacing"),
            arguments={"font_index": 0, "dry_run": False, "confirm": True},
            result=json.dumps({"ok": False, "error": "read-back failed"}),
        )
        self.module.observe_document_change(
            entry=self._entry("execute_code_with_context", effect="code", title="Execute Code With Context"),
            arguments={"font_index": 0, "code": "font.familyName = 'Nope'"},
            result=json.dumps({"success": True}),
        )
        snapshot = self.audit.DOCUMENT_CHANGE_LEDGER.snapshot()
        self.assertEqual(snapshot["counts"]["failed"], 1)
        self.assertEqual(snapshot["counts"]["uncertain"], 1)
        self.assertTrue(snapshot["entries"][1]["opaque"])
        self.assertNotIn("Nope", json.dumps(snapshot))

    def test_precondition_failure_is_omitted_but_started_rollback_failure_is_retained(self):
        entry = self._entry("update_glyph_node_positions")
        arguments = {
            "font_index": 0,
            "glyph_name": "C",
            "dry_run": False,
            "confirm": True,
        }
        self.module.observe_document_change(
            entry=entry,
            arguments=arguments,
            result=json.dumps(
                {
                    "ok": False,
                    "error": "Target path 0 node 1 no longer has the expected position",
                    "errorCode": "stale_target",
                }
            ),
        )
        self.assertEqual(self.audit.DOCUMENT_CHANGE_LEDGER.snapshot()["status"], "idle")

        self.module.observe_document_change(
            entry=entry,
            arguments=arguments,
            result=json.dumps(
                {
                    "ok": False,
                    "error": "Path 0 node 0 read-back did not match the expected position",
                    "errorCode": "continuous_coordinate_not_preserved",
                    "summary": {
                        "changedCount": 0,
                        "appliedCount": 0,
                        "verifiedCount": 0,
                    },
                    "changeBatch": {"available": True, "began": True, "ended": True},
                    "rollback": {"attempted": True, "succeeded": True, "errors": []},
                }
            ),
        )
        snapshot = self.audit.DOCUMENT_CHANGE_LEDGER.snapshot()
        self.assertEqual(snapshot["counts"]["failed"], 1)
        self.assertEqual(len(snapshot["entries"]), 1)
        self.assertEqual(snapshot["entries"][0]["tool"], "update_glyph_node_positions")

    def test_unscoped_code_with_multiple_fonts_is_unattributed(self):
        self.fonts.append(_Font("Second Font"))
        self.module.observe_document_change(
            entry=self._entry("execute_code", effect="code"),
            arguments={"code": "print('hello')"},
            result="{}",
        )
        snapshot = self.audit.DOCUMENT_CHANGE_LEDGER.snapshot()
        self.assertEqual(snapshot["status"], "idle")
        self.assertEqual(snapshot["unattributedOperationCount"], 1)

    def test_active_font_resolution_uses_stable_native_identity(self):
        listed = _Font("Listed Font")
        listed.native_id = 101
        other = _Font("Other Font")
        other.native_id = 202
        active_proxy = _Font("Listed Font Proxy")
        active_proxy.native_id = 101
        self.fonts[:] = [listed, other]
        self.module.Glyphs.font = active_proxy
        self.module._font_object_id = lambda font: font.native_id

        font, font_index = self.module._resolve_font(self._entry("update_glyph_metrics"), {}, {})

        self.assertIs(font, listed)
        self.assertEqual(font_index, 0)

    def test_public_tool_returns_idle_active_and_mismatch_results(self):
        idle = asyncio.run(self.module.get_document_change_overview())
        self.assertEqual(idle.structured_content["status"], "idle")

        self.module.observe_document_change(
            entry=self._entry("update_glyph_metrics", title="Update Glyph Metrics"),
            arguments={"font_index": 0, "glyph_name": "a"},
            result=json.dumps({"success": True, "message": "Updated metrics"}),
        )
        active = asyncio.run(self.module.get_document_change_overview(limit=1000))
        self.assertTrue(active.structured_content["ok"])
        self.assertEqual(active.structured_content["status"], "active")
        self.assertEqual(active.structured_content["entries"][0]["outcome"], "succeeded")

        self.fonts.append(_Font("Second Font"))
        mismatch = asyncio.run(self.module.get_document_change_overview(font_index=1))
        self.assertFalse(mismatch.structured_content["ok"])
        self.assertEqual(mismatch.structured_content["error"]["code"], "tracked_document_mismatch")

    def test_default_overview_follows_the_tracked_document(self):
        self.fonts.append(_Font("Second Font"))
        self.module.observe_document_change(
            entry=self._entry("update_glyph_metrics", title="Update Glyph Metrics"),
            arguments={"font_index": 1, "glyph_name": "a"},
            result=json.dumps({"success": True, "message": "Updated metrics"}),
        )

        active = asyncio.run(self.module.get_document_change_overview())
        self.assertTrue(active.structured_content["ok"])
        self.assertEqual(active.structured_content["target"]["familyName"], "Second Font")

        mismatch = asyncio.run(self.module.get_document_change_overview(font_index=0))
        self.assertEqual(mismatch.structured_content["error"]["code"], "tracked_document_mismatch")


if __name__ == "__main__":
    unittest.main()
