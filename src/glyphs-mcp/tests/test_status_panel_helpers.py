"""Tests for status_panel_helpers (pure functions)."""

from __future__ import annotations

import unittest
from pathlib import Path
import sys


def _resources_dir() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Resources"
    )


class StatusPanelHelpersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(_resources_dir()))

    def test_endpoint_for_defaults(self) -> None:
        from status_panel_helpers import endpoint_for

        self.assertEqual(endpoint_for(9680), "http://127.0.0.1:9680/mcp/")
        self.assertEqual(endpoint_for("9681"), "http://127.0.0.1:9681/mcp/")
        self.assertEqual(endpoint_for(None), "http://127.0.0.1:9680/mcp/")
        self.assertEqual(endpoint_for("oops"), "http://127.0.0.1:9680/mcp/")

    def test_status_text(self) -> None:
        from status_panel_helpers import status_text

        self.assertEqual(status_text(True), "Running")
        self.assertEqual(status_text(False), "Stopped")

    def test_is_thread_running(self) -> None:
        from status_panel_helpers import is_thread_running

        class Alive:
            def is_alive(self):
                return True

        class Dead:
            def is_alive(self):
                return False

        self.assertTrue(is_thread_running(Alive()))
        self.assertFalse(is_thread_running(Dead()))
        self.assertFalse(is_thread_running(None))


if __name__ == "__main__":
    unittest.main()
