"""Git-like canonical font trees and per-save action history contracts."""

from __future__ import annotations

import copy
import os
import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.canonical_tree import (  # noqa: E402
    CANONICAL_MODEL_SCHEMA_VERSION,
    CanonicalFontTree,
    MemoryObjectStore,
    SQLiteObjectStore,
)
from glyphs_mcp_v2.change_history import ChangeHistory  # noqa: E402
from glyphs_mcp_v2.change_trace import ActionTraceCoordinator  # noqa: E402
from glyphs_mcp_v2.semantic import diff_models, fingerprint_model  # noqa: E402


def _layer(master_id: str, x: float = 0.0) -> dict:
    return {
        "id": master_id,
        "masterId": master_id,
        "name": master_id,
        "isMasterLayer": True,
        "isSpecialLayer": False,
        "width": 500,
        "LSB": 40,
        "RSB": 40,
        "leftMetricsKey": None,
        "rightMetricsKey": None,
        "widthMetricsKey": None,
        "anchors": {"top": [250, 700]},
        "paths": [
            {
                "closed": True,
                "nodes": [
                    {"x": x, "y": 0, "type": "line", "smooth": False, "name": None},
                    {"x": 250, "y": 700, "type": "line", "smooth": False, "name": None},
                    {"x": 500, "y": 0, "type": "line", "smooth": False, "name": None},
                ],
            }
        ],
        "components": [],
        "pathSignature": [3],
    }


def _model(glyph_count: int = 3, master_count: int = 2) -> dict:
    masters = [{"id": "m{}".format(index), "name": "M{}".format(index)} for index in range(master_count)]
    glyphs = {}
    for index in range(glyph_count):
        name = "g{:04d}".format(index)
        glyphs[name] = {
            "name": name,
            "id": "id_{}".format(name),
            "category": "Letter",
            "subCategory": "Uppercase",
            "unicode": "{:04X}".format(0xE000 + index),
            "export": True,
            "leftKerningGroup": None,
            "rightKerningGroup": None,
            "mastersCompatible": True,
            "layers": {master["id"]: _layer(master["id"]) for master in masters},
        }
    return {
        "font": {"familyName": "Canonical Test", "upm": 1000},
        "masters": masters,
        "instances": [],
        "glyphs": glyphs,
        "kerning": {},
        "features": [],
        "classes": [],
        "featurePrefixes": [],
    }


class CanonicalFontTreeTests(unittest.TestCase):
    def test_tree_hash_is_deterministic_and_mapping_order_independent(self) -> None:
        store = MemoryObjectStore()
        trees = CanonicalFontTree(store)
        model = _model()
        reordered = {key: model[key] for key in reversed(list(model))}

        first = trees.store_model(model)
        second = trees.store_model(reordered)

        self.assertEqual(first.tree_hash, second.tree_hash)
        self.assertEqual(first.model_fingerprint, second.model_fingerprint)
        self.assertEqual(second.inserted_object_count, 0)
        self.assertEqual(trees.load_model(first.tree_hash), model)
        self.assertEqual(
            trees.descriptor(first.tree_hash)["modelSchemaVersion"],
            CANONICAL_MODEL_SCHEMA_VERSION,
        )
        self.assertEqual(
            trees.descriptor(first.tree_hash)["reversibilityCoverage"],
            "modeled_fields_only",
        )

    def test_one_glyph_edit_reuses_every_unchanged_glyph_object(self) -> None:
        store = MemoryObjectStore()
        trees = CanonicalFontTree(store)
        before = _model(glyph_count=383, master_count=5)
        first = trees.store_model(before)
        after = copy.deepcopy(before)
        after["glyphs"]["g0191"]["layers"]["m3"]["paths"][0]["nodes"][0]["x"] = 12
        second = trees.store_model(after)

        self.assertGreater(first.inserted_object_count, 383)
        self.assertLessEqual(second.inserted_object_count, 4)
        self.assertEqual(second.reused_glyph_count, 382)
        changes = trees.diff(first.tree_hash, second.tree_hash)
        self.assertEqual(len(changes.changes), 1)
        self.assertEqual(
            changes.changes[0].path,
            ("glyphs", "g0191", "layers", "m3", "paths", "0", "nodes", "0", "x"),
        )

    def test_verified_transition_hashes_only_changed_shards(self) -> None:
        class CountingTree(CanonicalFontTree):
            def __init__(self):
                super().__init__(MemoryObjectStore())
                self.value_writes = 0

            def _put_value(self, value):
                self.value_writes += 1
                return super()._put_value(value)

        trees = CountingTree()
        before = _model(glyph_count=383, master_count=5)
        baseline = trees.store_model(before)
        after = copy.deepcopy(before)
        after["glyphs"]["g0191"]["layers"]["m3"]["paths"][0]["nodes"][0]["x"] = 12
        changes = diff_models(before, after)
        trees.value_writes = 0

        transition = trees.store_verified_transition(
            baseline.tree_hash,
            after,
            changes,
        )

        self.assertEqual(trees.value_writes, 1)
        self.assertEqual(transition.model_fingerprint, fingerprint_model(after))
        self.assertEqual(transition.reused_glyph_count, 382)
        self.assertEqual(trees.load_model(transition.tree_hash), after)

    def test_scale_snapshot_hashing_stays_off_the_ui_budget(self) -> None:
        # This measures detached Python data only. Native Glyphs capture is
        # already required by the transaction kernel and must not be repeated.
        trees = CanonicalFontTree(MemoryObjectStore())
        model = _model(glyph_count=1000, master_count=5)
        started = time.perf_counter()
        snapshot = trees.store_model(model)
        elapsed = time.perf_counter() - started

        self.assertEqual(snapshot.glyph_count, 1000)
        self.assertLess(elapsed, 2.0)

    def test_sqlite_store_is_private_compressed_and_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "private" / "objects.sqlite3"
            store = SQLiteObjectStore(path)
            trees = CanonicalFontTree(store)
            first = trees.store_model(_model(glyph_count=20, master_count=2))
            second = trees.store_model(_model(glyph_count=20, master_count=2))
            store.close()

            self.assertEqual(first.tree_hash, second.tree_hash)
            self.assertEqual(second.inserted_object_count, 0)
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertLess(path.stat().st_size, first.inserted_byte_count * 2)


class ChangeHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.trees = CanonicalFontTree(MemoryObjectStore())
        self.history = ChangeHistory(self.trees, id_factory=iter(("c1", "c2", "c3", "c4", "c5")).__next__)
        self.before = _model()
        self.after = copy.deepcopy(self.before)
        self.after["glyphs"]["g0000"]["layers"]["m0"]["width"] = 520

    def test_every_tool_call_is_a_commit_but_only_mutations_change_tree(self) -> None:
        changed = self.history.record_action(
            document_id="doc_a",
            tool="apply_spacing",
            effect="edit",
            status="success",
            run_id="run_1",
            before_model=self.before,
            after_model=self.after,
        )
        read = self.history.record_action(
            document_id="doc_a",
            tool="get_document_status",
            effect="read",
            status="success",
            run_id="run_1",
        )

        self.assertEqual(changed.commit_id, "c1")
        self.assertEqual(read.commit_id, "c2")
        self.assertNotEqual(changed.before_tree_hash, changed.after_tree_hash)
        self.assertEqual(read.before_tree_hash, read.after_tree_hash)
        self.assertEqual([item.tool for item in self.history.list_commits("doc_a")], ["apply_spacing", "get_document_status"])

    def test_latest_session_diff_collapses_tool_calls_to_one_net_comparison(self) -> None:
        middle = copy.deepcopy(self.after)
        middle["glyphs"]["g0001"]["export"] = False
        final = copy.deepcopy(middle)
        final["glyphs"]["g0000"]["layers"]["m0"]["width"] = 500
        self.history.record_action(
            document_id="doc_a", tool="first", effect="edit", status="success", run_id="run_1",
            before_model=self.before, after_model=middle,
        )
        self.history.record_action(
            document_id="doc_a", tool="second", effect="edit", status="success", run_id="run_1",
            before_model=middle, after_model=final,
        )

        session = self.history.latest_session_diff("doc_a")
        self.assertIsNotNone(session)
        self.assertEqual(session.run_id, "run_1")
        self.assertEqual(len(session.change_set.changes), 1)
        self.assertEqual(session.change_set.changes[0].path[:3], ("glyphs", "g0001", "export"))

    def test_latest_agent_session_spans_distinct_tool_run_ids_until_an_external_boundary(self) -> None:
        middle = copy.deepcopy(self.before)
        middle["glyphs"]["g0000"]["export"] = False
        final = copy.deepcopy(middle)
        final["glyphs"]["g0001"]["export"] = False
        self.history.record_action(
            document_id="doc_a", tool="first", effect="edit", status="success", run_id="run_1",
            before_model=self.before, after_model=middle,
        )
        self.history.record_action(
            document_id="doc_a", tool="second", effect="edit", status="success", run_id="run_2",
            before_model=middle, after_model=final,
        )

        session = self.history.latest_session_diff("doc_a")
        self.assertIsNotNone(session)
        self.assertEqual(session.commit_ids, ("c1", "c2"))
        self.assertEqual(len(session.change_set.changes), 2)

        manual = copy.deepcopy(final)
        manual["font"]["note"] = "manual"
        after_manual = copy.deepcopy(manual)
        after_manual["glyphs"]["g0002"]["export"] = False
        self.history.record_action(
            document_id="doc_a", tool="third", effect="edit", status="success", run_id="run_3",
            before_model=manual, after_model=after_manual,
        )
        session = self.history.latest_session_diff("doc_a")
        self.assertIsNotNone(session)
        self.assertEqual(session.commit_ids, ("c4",))
        self.assertEqual(session.change_set.changes[0].path[:3], ("glyphs", "g0002", "export"))

    def test_save_resets_visible_history_and_overlay_ref(self) -> None:
        self.history.record_action(
            document_id="doc_a", tool="edit", effect="edit", status="success", run_id="run_1",
            before_model=self.before, after_model=self.after,
        )
        self.history.reset_after_save("doc_a")

        self.assertEqual(self.history.list_commits("doc_a"), ())
        self.assertIsNone(self.history.latest_session_diff("doc_a"))
        self.assertIsNone(self.history.head_tree_hash("doc_a"))

    def test_manual_working_tree_gap_is_preserved_as_hidden_boundary(self) -> None:
        manual = copy.deepcopy(self.after)
        manual["font"]["note"] = "manual"
        final = copy.deepcopy(manual)
        final["glyphs"]["g0002"]["export"] = False
        self.history.record_action(
            document_id="doc_a", tool="agent_one", effect="edit", status="success", run_id="run_1",
            before_model=self.before, after_model=self.after,
        )
        self.history.record_action(
            document_id="doc_a", tool="agent_two", effect="edit", status="success", run_id="run_2",
            before_model=manual, after_model=final,
        )

        self.assertEqual(len(self.history.list_commits("doc_a")), 2)
        all_commits = self.history.list_commits("doc_a", include_external=True)
        self.assertEqual(len(all_commits), 3)
        self.assertEqual(all_commits[1].source, "external")

    def test_verified_change_set_is_reused_and_reporter_reads_a_cached_session_diff(self) -> None:
        class CountingTree(CanonicalFontTree):
            def __init__(self):
                super().__init__(MemoryObjectStore())
                self.diff_calls = 0

            def diff(self, before_tree_hash, after_tree_hash):
                self.diff_calls += 1
                return super().diff(before_tree_hash, after_tree_hash)

        trees = CountingTree()
        history = ChangeHistory(trees)
        verified = diff_models(self.before, self.after)
        history.record_action(
            document_id="doc_fast",
            tool="apply_spacing",
            effect="edit",
            status="success",
            run_id="run_fast",
            before_model=self.before,
            after_model=self.after,
            change_set=verified,
        )

        first = history.latest_session_diff("doc_fast")
        second = history.latest_session_diff("doc_fast")
        self.assertIs(first, second)
        self.assertEqual(first.change_set, verified)
        self.assertEqual(trees.diff_calls, 0)

    def test_action_trace_reuses_head_and_stores_only_verified_transition(self) -> None:
        class CountingTree(CanonicalFontTree):
            def __init__(self):
                super().__init__(MemoryObjectStore())
                self.full_store_calls = 0
                self.transition_store_calls = 0

            def store_model(self, model):
                self.full_store_calls += 1
                return super().store_model(model)

            def store_verified_transition(self, before_tree_hash, after_model, change_set):
                self.transition_store_calls += 1
                return super().store_verified_transition(
                    before_tree_hash,
                    after_model,
                    change_set,
                )

        trees = CountingTree()
        history = ChangeHistory(trees)
        baseline = trees.store_model(self.before)
        history.record_action(
            document_id="doc_trace",
            tool="baseline",
            effect="read",
            status="success",
            run_id="run_baseline",
            before_tree_hash=baseline.tree_hash,
            after_tree_hash=baseline.tree_hash,
        )
        trees.full_store_calls = 0
        trace = ActionTraceCoordinator(history)
        scope = trace.start_action(
            "apply_spacing",
            "edit",
            {"documentId": "doc_trace"},
        )
        observed = trace.observe_model("doc_trace", self.before)
        token = trace.prepare_transaction("doc_trace", self.before)
        changes = diff_models(self.before, self.after)
        trace.commit_transaction(
            token,
            "doc_trace",
            self.before,
            self.after,
            changes,
        )

        self.assertEqual(observed, baseline.tree_hash)
        self.assertEqual(token.before_tree_hash, baseline.tree_hash)
        self.assertEqual(trees.full_store_calls, 0)
        self.assertEqual(trees.transition_store_calls, 1)
        self.assertTrue(scope.transaction_completed)


if __name__ == "__main__":
    unittest.main()
