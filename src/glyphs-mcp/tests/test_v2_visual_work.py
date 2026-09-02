"""Process-local visual-work arbitration contracts."""

from __future__ import annotations

import ast
import sys
import threading
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.visual_work import VisualWorkGate  # noqa: E402


class VisualWorkGateTests(unittest.TestCase):
    def test_nested_leases_publish_monotonic_immutable_snapshots(self) -> None:
        ids = iter(("lease_a", "lease_b"))
        gate = VisualWorkGate(id_factory=lambda: next(ids))
        observed = []
        gate.subscribe(observed.append)

        first = gate.acquire(" MCP Operation ")
        second = gate.acquire("python   script")
        nested = gate.current()
        gate.release(first)
        gate.release(second)

        self.assertEqual(nested.active_lease_count, 2)
        self.assertEqual(nested.reasons, ("mcp_operation", "python_script"))
        self.assertTrue(nested.suspended)
        self.assertEqual(
            [snapshot.sequence for snapshot in observed], [1, 2, 3, 4]
        )
        self.assertFalse(gate.current().suspended)
        with self.assertRaises(Exception):
            nested.reasons[0] = "changed"

    def test_context_release_is_exception_safe_and_observers_are_isolated(self) -> None:
        gate = VisualWorkGate(id_factory=lambda: "lease")
        observed = []
        gate.subscribe(
            lambda _snapshot: (_ for _ in ()).throw(RuntimeError("broken UI"))
        )
        gate.subscribe(observed.append)

        with self.assertRaisesRegex(RuntimeError, "operation failed"):
            with gate.hold("python_script"):
                self.assertTrue(gate.current().suspended)
                raise RuntimeError("operation failed")

        self.assertFalse(gate.current().suspended)
        self.assertEqual(len(observed), 2)

    def test_callbacks_run_outside_the_store_lock(self) -> None:
        gate = VisualWorkGate()
        callback_was_unlocked = []

        def observer(_snapshot) -> None:
            completed = threading.Event()

            def read_from_another_thread() -> None:
                gate.current()
                completed.set()

            thread = threading.Thread(target=read_from_another_thread)
            thread.start()
            thread.join(timeout=0.5)
            callback_was_unlocked.append(completed.is_set())

        gate.subscribe(observer)
        lease = gate.acquire("test")
        gate.release(lease)

        self.assertEqual(callback_was_unlocked, [True, True])

    def test_concurrent_leases_are_reference_counted(self) -> None:
        gate = VisualWorkGate()
        acquired = threading.Barrier(5)
        release = threading.Barrier(5)

        def worker(index: int) -> None:
            lease = gate.acquire("worker {}".format(index))
            acquired.wait()
            release.wait()
            gate.release(lease)

        threads = [
            threading.Thread(target=worker, args=(index,)) for index in range(4)
        ]
        for thread in threads:
            thread.start()
        acquired.wait()
        self.assertEqual(gate.current().active_lease_count, 4)
        release.wait()
        for thread in threads:
            thread.join(timeout=1.0)
            self.assertFalse(thread.is_alive())
        self.assertEqual(gate.current().active_lease_count, 0)
        self.assertEqual(gate.current().sequence, 8)

    def test_module_is_ui_neutral(self) -> None:
        source = (
            V2_SOURCE / "glyphs_mcp_v2" / "visual_work.py"
        ).read_text(encoding="utf-8")
        imported = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(
                    alias.name.split(".", 1)[0] for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom):
                imported.add(str(node.module or "").split(".", 1)[0])
        self.assertFalse(imported & {"AppKit", "GlyphsApp", "Foundation", "objc"})


if __name__ == "__main__":
    unittest.main()
