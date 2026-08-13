"""Public LitSquare MCP tool forwarding and error-contract tests."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


RESOURCES = (
    Path(__file__).resolve().parent.parent
    / "Glyphs MCP.glyphsPlugin"
    / "Contents"
    / "Resources"
)


class McpToolsLitSquareTests(unittest.TestCase):
    def _load(self):
        calls = []
        glyphs = object()

        def record(name, result):
            def function(*args, **kwargs):
                calls.append((name, args, kwargs))
                return dict(result)

            return function

        adapter = types.SimpleNamespace(
            metadata_snapshot=record(
                "metadata", {"ok": True, "target": {"fontIndex": 0}, "fontSaved": False}
            ),
            selected_path_snapshot=record(
                "roles", {"ok": True, "paths": [], "fontSaved": False}
            ),
            patch_metadata_transaction=record(
                "patch", {"ok": True, "summary": {"changed": False}, "fontSaved": False}
            ),
            set_path_roles_transaction=record(
                "set_roles",
                {"ok": True, "summary": {"changedPathCount": 0}, "fontSaved": False},
            ),
        )
        helpers = types.SimpleNamespace(
            _run_on_main_thread=lambda callback: callback(),
            _safe_json=lambda value: json.dumps(value, sort_keys=True),
        )
        modules = {
            "GlyphsApp": types.SimpleNamespace(Glyphs=glyphs),
            "glyphs_litsquare_adapter": adapter,
            "mcp_tool_helpers": helpers,
            "tool_registration": types.SimpleNamespace(
                glyphs_tool=lambda *_args, **_kwargs: (lambda function: function)
            ),
        }
        path = RESOURCES / "mcp_tools_litsquare.py"
        spec = importlib.util.spec_from_file_location("mcp_tools_litsquare_under_test", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules, modules):
            spec.loader.exec_module(module)
        return module, adapter, calls, glyphs

    def test_reads_forward_explicit_context_on_main_thread(self):
        module, _adapter, calls, glyphs = self._load()
        metadata = json.loads(
            asyncio.run(
                module.get_litsquare_metadata(
                    font_index=2, glyph_name="A", layer_id="M1", include_inherited=False
                )
            )
        )
        roles = json.loads(asyncio.run(module.get_selected_litsquare_path_roles(font_index=1)))
        self.assertTrue(metadata["ok"])
        self.assertFalse(roles["fontSaved"])
        self.assertEqual(
            calls[0][2],
            {
                "font_index": 2,
                "glyph_name": "A",
                "layer_id": "M1",
                "include_inherited": False,
                "app": glyphs,
            },
        )
        self.assertEqual(calls[1][2], {"font_index": 1, "app": glyphs})

    def test_writes_forward_dry_run_confirmation_and_concurrency_fields(self):
        module, _adapter, calls, glyphs = self._load()
        patch = json.loads(
            asyncio.run(
                module.patch_litsquare_metadata(
                    "layer",
                    {"status": {"state": "ready"}},
                    font_index=1,
                    glyph_name="A",
                    layer_id="M1",
                    expected_updated_at="2026-08-11T18:30:00Z",
                    dry_run=False,
                    confirm=True,
                )
            )
        )
        roles = json.loads(
            asyncio.run(
                module.set_litsquare_path_roles(
                    [{"glyphName": "A", "layerId": "M1", "pathIndex": 0}],
                    role="body",
                )
            )
        )
        self.assertFalse(patch["fontSaved"])
        self.assertFalse(roles["fontSaved"])
        self.assertEqual(calls[0][2]["app"], glyphs)
        self.assertFalse(calls[0][2]["dry_run"])
        self.assertTrue(calls[0][2]["confirm"])
        self.assertEqual(calls[0][2]["expected_updated_at"], "2026-08-11T18:30:00Z")
        self.assertTrue(calls[1][2]["dry_run"])
        self.assertFalse(calls[1][2]["confirm"])

    def test_adapter_errors_are_bounded_and_never_claim_a_save(self):
        module, adapter, _calls, _glyphs = self._load()

        def fail(**_kwargs):
            raise ValueError("stale target")

        adapter.patch_metadata_transaction = fail
        module.patch_metadata_transaction = fail
        payload = json.loads(
            asyncio.run(module.patch_litsquare_metadata("font", {"status": {"state": "ready"}}))
        )
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "litsquare_error")
        self.assertTrue(payload["error"]["recoverable"])
        self.assertFalse(payload["fontSaved"])

    def test_catalog_marks_only_the_two_reads_as_read_only(self):
        sys.path.insert(0, str(RESOURCES))
        from tool_catalog import TOOL_CATALOG

        self.assertTrue(TOOL_CATALOG["get_litsquare_metadata"].annotations["readOnlyHint"])
        self.assertTrue(
            TOOL_CATALOG["get_selected_litsquare_path_roles"].annotations["readOnlyHint"]
        )
        self.assertFalse(TOOL_CATALOG["patch_litsquare_metadata"].annotations["readOnlyHint"])
        self.assertFalse(TOOL_CATALOG["set_litsquare_path_roles"].annotations["readOnlyHint"])
        self.assertNotIn("set_metadata_inspector_collapsed", TOOL_CATALOG)


if __name__ == "__main__":
    unittest.main()
