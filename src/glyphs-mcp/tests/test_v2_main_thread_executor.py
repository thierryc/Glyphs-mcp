"""Correctness boundaries for live Cocoa main-thread execution."""

from __future__ import annotations

import sys
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.adapters.main_thread import GlyphsMainThreadExecutor  # noqa: E402
from glyphs_mcp_v2.ports import HostAccessError  # noqa: E402


class _BackgroundThread:
    @staticmethod
    def isMainThread():
        return False


class _DelayedQueue:
    delay = 0.0

    @classmethod
    def mainQueue(cls):
        return cls()

    def addOperationWithBlock_(self, callback):
        def run():
            time.sleep(self.delay)
            callback()

        threading.Thread(target=run, daemon=True).start()


class _BlockedQueue:
    scheduled = None

    @classmethod
    def mainQueue(cls):
        return cls()

    def addOperationWithBlock_(self, callback):
        self.__class__.scheduled = callback


class MainThreadExecutorTests(unittest.TestCase):
    def _foundation(self, queue):
        return mock.patch.dict(
            sys.modules,
            {
                "Foundation": types.SimpleNamespace(
                    NSOperationQueue=queue,
                    NSThread=_BackgroundThread,
                )
            },
        )

    def test_started_callback_is_never_abandoned_after_timeout(self) -> None:
        _DelayedQueue.delay = 0

        def slow_callback():
            time.sleep(0.03)
            return "complete"

        with self._foundation(_DelayedQueue):
            started = time.perf_counter()
            result = GlyphsMainThreadExecutor(timeout_seconds=0.01).run(
                slow_callback
            )

        self.assertEqual(result, "complete")
        self.assertGreaterEqual(time.perf_counter() - started, 0.03)

    def test_callback_that_never_started_can_be_cancelled_safely(self) -> None:
        called = []
        with self._foundation(_BlockedQueue):
            with self.assertRaisesRegex(HostAccessError, "before it started"):
                GlyphsMainThreadExecutor(timeout_seconds=0.01).run(
                    lambda: called.append(True)
                )
            _BlockedQueue.scheduled()

        self.assertEqual(called, [])


if __name__ == "__main__":
    unittest.main()
