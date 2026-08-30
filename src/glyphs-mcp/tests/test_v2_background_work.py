"""Non-blocking and bounded convenience-work coordination contracts."""

from __future__ import annotations

import statistics
import sys
import threading
import time
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.background_work import BackgroundWorkCoordinator  # noqa: E402


class BackgroundWorkCoordinatorTests(unittest.TestCase):
    def test_latest_generation_is_the_only_result_published(self) -> None:
        coordinator = BackgroundWorkCoordinator(capacity=4, thread_name="latest-test")
        running = threading.Event()
        release = threading.Event()
        completed: list[int] = []

        def first(_context):
            running.set()
            release.wait(1.0)
            return 1

        try:
            coordinator.submit("diff", "layer", first, completed=completed.append)
            self.assertTrue(running.wait(1.0))
            coordinator.submit("diff", "layer", lambda _context: 2, completed=completed.append)
            coordinator.submit("diff", "layer", lambda _context: 3, completed=completed.append)
            release.set()
            deadline = time.monotonic() + 1.0
            while completed != [3] and time.monotonic() < deadline:
                time.sleep(0.005)
            self.assertEqual(completed, [3])
        finally:
            release.set()
            coordinator.close(wait=True)

    def test_save_barrier_defers_layer_diff_work(self) -> None:
        coordinator = BackgroundWorkCoordinator(thread_name="save-barrier-test")
        path = "/fonts/Family.glyphs"
        started = threading.Event()
        try:
            coordinator.pause_for_save(path, timeout=1.0)
            coordinator.submit(
                "diff",
                (path, "A", "m0"),
                lambda _context: started.set(),
            )
            self.assertFalse(started.wait(0.05))
            coordinator.resume_after_save(path, delay=0.0)
            self.assertTrue(started.wait(1.0))
        finally:
            coordinator.close(wait=True)

    def test_save_barrier_rejects_a_running_old_layer_generation(self) -> None:
        coordinator = BackgroundWorkCoordinator(thread_name="save-stale-test")
        path = "/fonts/Family.glyphs"
        running = threading.Event()
        release = threading.Event()
        completed = []

        def old_diff(_context):
            running.set()
            release.wait(1.0)
            return "obsolete"

        try:
            coordinator.submit(
                "diff",
                (path, "A", "m0"),
                old_diff,
                completed=completed.append,
            )
            self.assertTrue(running.wait(1.0))
            coordinator.pause_for_save(path)
            coordinator.resume_after_save(path, delay=0.0)
            release.set()
            time.sleep(0.02)
            self.assertEqual(completed, [])
        finally:
            release.set()
            coordinator.close(wait=True)

    def test_post_save_quiet_window_defers_new_work(self) -> None:
        coordinator = BackgroundWorkCoordinator(thread_name="debounce-test")
        path = "/fonts/Family.glyphs"
        started = threading.Event()
        try:
            coordinator.resume_after_save(path, delay=0.05)
            coordinator.submit(
                "diff",
                (path, "A", "m0"),
                lambda _context: started.set(),
            )
            self.assertFalse(started.wait(0.02))
            self.assertTrue(started.wait(1.0))
        finally:
            coordinator.close(wait=True)

    def test_queue_pressure_stays_bounded_and_retains_source_work(self) -> None:
        coordinator = BackgroundWorkCoordinator(capacity=3, thread_name="pressure-test")
        running = threading.Event()
        release = threading.Event()
        completed = []

        def blocked(_context):
            running.set()
            release.wait(1.0)

        try:
            coordinator.submit("diff", "running", blocked)
            self.assertTrue(running.wait(1.0))
            coordinator.submit(
                "source", "/fonts/Family.glyphs", lambda _context: "source",
                completed=completed.append,
            )
            for index in range(20):
                coordinator.submit(
                    "diff", "layer-{}".format(index),
                    lambda _context, value=index: value,
                    completed=completed.append,
                )
            release.set()
            deadline = time.monotonic() + 1.0
            while "source" not in completed and time.monotonic() < deadline:
                time.sleep(0.005)
            self.assertIn("source", completed)
            self.assertLessEqual(len(completed), 3)
        finally:
            release.set()
            coordinator.close(wait=True)

    def test_submission_latency_stays_below_the_save_callback_budget(self) -> None:
        coordinator = BackgroundWorkCoordinator(capacity=2, thread_name="latency-test")
        durations = []
        try:
            for index in range(500):
                started = time.perf_counter_ns()
                coordinator.submit("diff", "layer", lambda _context: index)
                durations.append((time.perf_counter_ns() - started) / 1_000_000)
            p95 = statistics.quantiles(durations, n=20)[18]
            self.assertLess(p95, 5.0)
        finally:
            coordinator.close(wait=True)

    def test_completed_and_dropped_generations_do_not_accumulate(self) -> None:
        coordinator = BackgroundWorkCoordinator(capacity=4, thread_name="retire-test")
        try:
            for index in range(200):
                coordinator.submit(
                    "diff",
                    "layer-{}".format(index),
                    lambda _context: None,
                )
            deadline = time.monotonic() + 1.0
            while coordinator._latest and time.monotonic() < deadline:
                time.sleep(0.005)
            self.assertEqual(coordinator._latest, {})
        finally:
            coordinator.close(wait=True)

    def test_non_waiting_close_never_joins_active_work(self) -> None:
        coordinator = BackgroundWorkCoordinator(thread_name="close-test")
        running = threading.Event()
        release = threading.Event()

        def blocked(_context):
            running.set()
            release.wait(1.0)

        coordinator.submit("diff", "layer", blocked)
        self.assertTrue(running.wait(1.0))
        started = time.perf_counter_ns()
        coordinator.close(wait=False)
        duration_ms = (time.perf_counter_ns() - started) / 1_000_000
        release.set()

        self.assertLess(duration_ms, 5.0)


if __name__ == "__main__":
    unittest.main()
