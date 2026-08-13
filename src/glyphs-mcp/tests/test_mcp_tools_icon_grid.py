"""Typed fixed-coordinate IconGrid MCP forwarding and catalog tests."""

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


class McpToolsIconGridTests(unittest.TestCase):
    def _load(self):
        calls = []
        glyphs = object()

        def record(name, result):
            def function(*args, **kwargs):
                calls.append((name, args, kwargs))
                return dict(result)

            return function

        adapter = types.SimpleNamespace(
            icon_grid_snapshot=record("read", {"ok": True, "fontSaved": False}),
            set_icon_grid_horizontal_center_transaction=record(
                "set", {"ok": True, "summary": {"changed": True}, "fontSaved": False}
            ),
            reset_icon_grid_horizontal_center_transaction=record(
                "reset", {"ok": True, "summary": {"changed": True}, "fontSaved": False}
            ),
        )
        modules = {
            "GlyphsApp": types.SimpleNamespace(Glyphs=glyphs),
            "glyphs_icon_grid_adapter": adapter,
            "mcp_tool_helpers": types.SimpleNamespace(
                _safe_json=lambda value: json.dumps(value, sort_keys=True)
            ),
            "tool_registration": types.SimpleNamespace(
                glyphs_tool=lambda *_args, **_kwargs: (lambda function: function)
            ),
        }
        path = RESOURCES / "mcp_tools_icon_grid.py"
        spec = importlib.util.spec_from_file_location("mcp_tools_icon_grid_under_test", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules, modules):
            spec.loader.exec_module(module)
        return module, adapter, calls, glyphs

    def test_read_and_mutations_forward_context_fingerprint_and_modes(self):
        module, _adapter, calls, glyphs = self._load()
        read = json.loads(
            asyncio.run(
                module.get_icon_grid_horizontal_center(
                    font_index=2, glyph_name="A", layer_id="M1"
                )
            )
        )
        set_result = json.loads(
            asyncio.run(
                module.set_icon_grid_horizontal_center(
                    font_index=2,
                    glyph_name="A",
                    layer_id="M1",
                    center_x=521.5,
                    expected_state_fingerprint="sha256:reviewed",
                    dry_run=False,
                    confirm=True,
                )
            )
        )
        reset = json.loads(
            asyncio.run(
                module.reset_icon_grid_horizontal_center(
                    font_index=2,
                    glyph_name="A",
                    layer_id="M1",
                    expected_state_fingerprint="sha256:reviewed",
                )
            )
        )
        self.assertFalse(read["fontSaved"])
        self.assertFalse(set_result["fontSaved"])
        self.assertFalse(reset["fontSaved"])
        self.assertEqual(calls[0][2]["app"], glyphs)
        self.assertEqual(calls[1][2]["expected_state_fingerprint"], "sha256:reviewed")
        self.assertEqual(calls[1][2]["center_x"], 521.5)
        self.assertFalse(calls[1][2]["dry_run"])
        self.assertTrue(calls[1][2]["confirm"])
        self.assertTrue(calls[2][2]["dry_run"])

    def test_errors_are_bounded_and_never_claim_save_or_redraw(self):
        module, adapter, _calls, _glyphs = self._load()

        def fail(**_kwargs):
            raise ValueError("stale state")

        adapter.set_icon_grid_horizontal_center_transaction = fail
        module.set_icon_grid_horizontal_center_transaction = fail
        payload = json.loads(
            asyncio.run(
                module.set_icon_grid_horizontal_center(
                    font_index=0,
                    glyph_name="A",
                    layer_id="M1",
                    center_x=200,
                    expected_state_fingerprint="sha256:stale",
                )
            )
        )
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "icon_grid_centering_error")
        self.assertFalse(payload["fontSaved"])
        self.assertFalse(payload["redrawn"])

    def test_catalog_marks_read_and_mutations_correctly(self):
        sys.path.insert(0, str(RESOURCES))
        from tool_catalog import TOOL_CATALOG

        self.assertTrue(
            TOOL_CATALOG["get_icon_grid_horizontal_center"].annotations["readOnlyHint"]
        )
        self.assertFalse(
            TOOL_CATALOG["set_icon_grid_horizontal_center"].annotations["readOnlyHint"]
        )
        self.assertFalse(
            TOOL_CATALOG["reset_icon_grid_horizontal_center"].annotations["readOnlyHint"]
        )


if __name__ == "__main__":
    unittest.main()
