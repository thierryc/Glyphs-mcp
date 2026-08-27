"""Connection-state and compact palette indicator contracts for v2."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.connection_status import (  # noqa: E402
    ConnectionStatusStore,
    indicator_presentation,
)


class ConnectionStatusStoreTests(unittest.TestCase):
    def test_store_starts_stopped_and_publishes_real_changes(self) -> None:
        store = ConnectionStatusStore()
        observed = []
        unsubscribe = store.subscribe(observed.append)

        initial = store.current()
        self.assertEqual(initial.state, "stopped")
        self.assertEqual(initial.sequence, 0)

        starting = store.publish("starting", "Starting")
        duplicate = store.publish("starting", "Starting")
        ready = store.publish("running", "Running")

        self.assertIs(duplicate, starting)
        self.assertEqual([item.state for item in observed], ["starting", "running"])
        self.assertEqual(ready.sequence, 2)

        unsubscribe()
        store.publish("stopping", "Stopping")
        self.assertEqual(len(observed), 2)

    def test_observer_failure_cannot_block_other_observers(self) -> None:
        store = ConnectionStatusStore()
        observed = []
        store.subscribe(
            lambda _snapshot: (_ for _ in ()).throw(RuntimeError("UI failed"))
        )
        store.subscribe(observed.append)

        store.publish("running", "Running")

        self.assertEqual([item.state for item in observed], ["running"])

    def test_store_rejects_unknown_lifecycle_states(self) -> None:
        store = ConnectionStatusStore()

        with self.assertRaises(ValueError):
            store.publish("busy", "Busy")


class IndicatorPresentationTests(unittest.TestCase):
    def _resolve(
        self,
        connection: str,
        activity: str = "idle",
        elapsed: float = 0.0,
        active: bool = False,
    ):
        return indicator_presentation(
            connection,
            activity,
            elapsed,
            active,
            heavy_after_seconds=2.0,
        )

    def test_connection_transitions_take_priority(self) -> None:
        for state in ("starting", "waiting"):
            presentation = self._resolve(state, "running", 10.0, True)
            self.assertEqual(presentation.tone, "blue")
            self.assertTrue(presentation.pulsing)
            self.assertEqual(presentation.text_key, "palette.connecting")

        stopping = self._resolve("stopping", "running", 10.0, True)
        self.assertEqual(stopping.tone, "blue")
        self.assertTrue(stopping.pulsing)
        self.assertEqual(stopping.text_key, "palette.disconnecting")

    def test_ready_short_and_heavy_task_states(self) -> None:
        ready = self._resolve("running")
        short = self._resolve("running", "running", 1.99, True)
        heavy = self._resolve("running", "running", 2.0, True)

        self.assertEqual((ready.tone, ready.pulsing), ("green", False))
        self.assertEqual((short.tone, short.pulsing), ("green", True))
        self.assertEqual((heavy.tone, heavy.pulsing), ("magenta", True))
        self.assertIsNone(ready.text_key)
        self.assertIsNone(short.text_key)
        self.assertIsNone(heavy.text_key)

    def test_error_and_stopped_states_are_steady(self) -> None:
        connection_error = self._resolve("error", "running", 10.0, True)
        task_error = self._resolve("running", "error")
        stopped = self._resolve("stopped", "running", 10.0, True)

        self.assertEqual(
            (connection_error.tone, connection_error.pulsing, connection_error.text_key),
            ("red", False, "status.error"),
        )
        self.assertEqual(
            (task_error.tone, task_error.pulsing, task_error.text_key),
            ("red", False, None),
        )
        self.assertEqual(
            (stopped.tone, stopped.pulsing, stopped.text_key),
            ("gray", False, "status.stopped"),
        )

    def test_terminal_task_messages_return_to_steady_green(self) -> None:
        for state in ("success", "cancelled"):
            presentation = self._resolve("running", state)
            self.assertEqual(presentation.tone, "green")
            self.assertFalse(presentation.pulsing)
            self.assertIsNone(presentation.text_key)


class PaletteLocalizationTests(unittest.TestCase):
    def test_palette_status_strings_cover_every_supported_language(self) -> None:
        path = (
            REPO
            / "src"
            / "glyphs-mcp"
            / "Glyphs MCP.glyphsPlugin"
            / "Contents"
            / "Resources"
            / "i18n.py"
        )
        spec = importlib.util.spec_from_file_location("glyphs_mcp_palette_i18n", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        languages = {"en", "de", "fr", "es", "pt", "zh-Hans"}
        for key in (
            "palette.ready",
            "palette.connecting",
            "palette.disconnecting",
        ):
            self.assertEqual(set(module.STRINGS[key]), languages)


if __name__ == "__main__":
    unittest.main()
