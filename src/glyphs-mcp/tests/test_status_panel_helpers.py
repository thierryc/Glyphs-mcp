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

        self.assertEqual(status_text(True), "running")
        self.assertEqual(status_text(False), "stopped")

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

    def test_server_lifecycle_state_requires_uvicorn_readiness(self) -> None:
        from status_panel_helpers import server_lifecycle_state

        class Thread:
            def __init__(self, alive):
                self.alive = alive

            def is_alive(self):
                return self.alive

        class Server:
            def __init__(self, started):
                self.started = started

        self.assertEqual(
            server_lifecycle_state(Server(False), Thread(True)),
            "starting",
        )
        self.assertEqual(
            server_lifecycle_state(Server(True), Thread(True)),
            "running",
        )
        self.assertEqual(
            server_lifecycle_state(Server(True), Thread(True), stopping=True),
            "stopping",
        )
        self.assertEqual(
            server_lifecycle_state(Server(False), Thread(False)),
            "stopped",
        )
        self.assertEqual(
            server_lifecycle_state(Server(True), Thread(False)),
            "stopped",
        )

    def test_server_lifecycle_state_tolerates_missing_or_broken_server(self) -> None:
        from status_panel_helpers import server_lifecycle_state

        class Alive:
            def is_alive(self):
                return True

        class Broken:
            @property
            def started(self):
                raise RuntimeError("unavailable")

        self.assertEqual(server_lifecycle_state(None, Alive()), "starting")
        self.assertEqual(server_lifecycle_state(Broken(), Alive()), "starting")

    def test_server_exit_kind_distinguishes_lifecycle_failures(self) -> None:
        from status_panel_helpers import server_exit_kind

        self.assertEqual(server_exit_kind(), "startup_failed")
        self.assertEqual(server_exit_kind(server_started=True), "unexpected")
        self.assertEqual(server_exit_kind(was_ready=True), "unexpected")
        self.assertEqual(
            server_exit_kind(
                server_started=True,
                was_ready=True,
                stop_requested=True,
            ),
            "intentional",
        )

    def test_start_success_is_emitted_once_after_readiness(self) -> None:
        from status_panel_helpers import should_emit_start_success

        self.assertFalse(should_emit_start_success(False, False))
        self.assertTrue(should_emit_start_success(True, False))
        self.assertFalse(should_emit_start_success(True, True))

    def test_only_manual_startup_failures_show_an_alert(self) -> None:
        from status_panel_helpers import should_show_start_failure_alert

        self.assertTrue(
            should_show_start_failure_alert(True, "startup_failed")
        )
        self.assertFalse(
            should_show_start_failure_alert(False, "startup_failed")
        )
        self.assertFalse(should_show_start_failure_alert(True, "unexpected"))
        self.assertFalse(should_show_start_failure_alert(True, "intentional"))


if __name__ == "__main__":
    unittest.main()
