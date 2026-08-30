"""Git-like canonical font trees and per-save action history contracts."""

from __future__ import annotations

import copy
import os
import stat
import sys
import tempfile
import time
import unittest
from collections.abc import Mapping
from pathlib import Path
from unittest import mock


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.canonical_tree import (  # noqa: E402
    CANONICAL_MODEL_SCHEMA_VERSION,
    CanonicalSnapshot,
    CanonicalFontTree,
    MemoryObjectStore,
    SQLiteObjectStore,
)
from glyphs_mcp_v2.change_history import ChangeHistory  # noqa: E402
from glyphs_mcp_v2.change_trace import ActionTraceCoordinator  # noqa: E402
from glyphs_mcp_v2.contracts import ToolResponse  # noqa: E402
from glyphs_mcp_v2.semantic import (  # noqa: E402
    compose_change_sets,
    diff_models,
    fingerprint_model,
)
from glyphs_mcp_v2.structural_registry import build_master_updates  # noqa: E402


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
    def test_schema_activation_clears_process_local_v5_history_with_reason(self) -> None:
        trees = CanonicalFontTree(MemoryObjectStore())
        history = ChangeHistory(trees)
        before = _model(glyph_count=1, master_count=1)
        after = copy.deepcopy(before)
        after["font"]["familyName"] = "Changed"
        history.record_action(
            document_id="doc_schema_reset",
            tool="test",
            effect="edit",
            status="applied",
            run_id="run",
            before_model=before,
            after_model=after,
        )

        reason = history.reset_for_schema_change(5, 6)

        self.assertEqual(reason, "canonical_schema_changed:5_to_6")
        self.assertEqual(history.last_reset_reason, reason)
        self.assertEqual(history.list_commits("doc_schema_reset"), ())
        self.assertIsNone(history.head_tree_hash("doc_schema_reset"))
        self.assertEqual(len(trees._store), 0)

    def test_snapshot_caches_exact_fingerprint_and_immutable_shards(self) -> None:
        model = _model(glyph_count=383, master_count=5)
        snapshot = CanonicalSnapshot.from_model(
            model,
            native_revision_evidence={"glyphs": {"g0000": ("revision-1",)}},
        )

        self.assertEqual(snapshot.model_schema_version, CANONICAL_MODEL_SCHEMA_VERSION)
        self.assertEqual(snapshot.document_fingerprint, fingerprint_model(model))
        self.assertEqual(fingerprint_model(snapshot), snapshot.document_fingerprint)
        self.assertTrue(snapshot.content_tree_hash.startswith("sha256:"))
        self.assertEqual(snapshot.native_revision_evidence["glyphs"]["g0000"], ("revision-1",))
        self.assertEqual(snapshot.materialize(), model)

    def test_sharded_snapshot_streams_the_exact_canonical_document_fingerprint(self) -> None:
        model = {
            "font": {"familyName": "G\u00e9\u03b2", "upm": 1000.0},
            "settings": {"negativeZero": -0.0, "fraction": 1.25},
            "glyphs": {
                "A": {"name": "A", "export": True, "layers": []},
                "\u03b2": {"name": "\u03b2", "export": False, "layers": []},
            },
        }

        with mock.patch(
            "glyphs_mcp_v2.canonical_tree.fingerprint_model",
            side_effect=AssertionError("snapshot encoded the complete document"),
        ):
            snapshot = CanonicalSnapshot.from_shards(
                {"font": model["font"], "settings": model["settings"]},
                model["glyphs"],
            )

        self.assertEqual(snapshot.document_fingerprint, fingerprint_model(model))

    def test_rebased_snapshot_encodes_only_the_changed_glyph_shard(self) -> None:
        before = _model(glyph_count=383, master_count=5)
        baseline = CanonicalSnapshot.from_shards(
            {name: value for name, value in before.items() if name != "glyphs"},
            before["glyphs"],
        )
        after = dict(baseline)
        glyphs = dict(baseline.glyph_shards)
        changed = copy.deepcopy(glyphs["g0191"])
        changed["export"] = False
        glyphs["g0191"] = changed
        after["glyphs"] = glyphs

        from glyphs_mcp_v2 import canonical_tree

        original = canonical_tree._json_bytes
        encoded_values = []

        def record(value):
            encoded_values.append(value)
            return original(value)

        with mock.patch(
            "glyphs_mcp_v2.canonical_tree._json_bytes",
            side_effect=record,
        ), mock.patch(
            "glyphs_mcp_v2.canonical_tree.fingerprint_model",
            side_effect=AssertionError("rebase encoded the complete document"),
        ):
            rebased = baseline._rebase_shared_model(after)

        self.assertEqual(rebased.document_fingerprint, fingerprint_model(after))
        self.assertIs(rebased.glyph_shards["g0190"], baseline.glyph_shards["g0190"])
        self.assertIsNot(rebased.glyph_shards["g0191"], baseline.glyph_shards["g0191"])
        self.assertIn(False, encoded_values)
        self.assertFalse(
            any(
                isinstance(value, Mapping)
                and "layers" in value
                and "name" in value
                for value in encoded_values
            )
        )
        self.assertFalse(any(value is glyphs["g0190"] for value in encoded_values))

    def test_equal_verified_snapshots_diff_without_materializing_or_walking_the_tree(self) -> None:
        snapshot = CanonicalSnapshot.from_model(_model(glyph_count=383, master_count=5))

        with mock.patch(
            "glyphs_mcp_v2.semantic._plain",
            side_effect=AssertionError("equal snapshots were materialized"),
        ), mock.patch(
            "glyphs_mcp_v2.semantic._diff",
            side_effect=AssertionError("equal snapshots were recursively walked"),
        ):
            changes = diff_models(snapshot, snapshot)

        self.assertEqual(changes.changes, ())
        self.assertEqual(changes.before_fingerprint, snapshot.document_fingerprint)
        self.assertEqual(changes.after_fingerprint, snapshot.document_fingerprint)

    def test_verified_snapshot_transition_reuses_unchanged_glyph_shards_without_full_hash(self) -> None:
        before = _model(glyph_count=383, master_count=5)
        baseline = CanonicalSnapshot.from_model(before)
        after = copy.deepcopy(before)
        after["glyphs"]["g0191"]["layers"]["m3"]["paths"][0]["nodes"][0]["x"] = 12
        changes = diff_models(before, after)

        with mock.patch(
            "glyphs_mcp_v2.canonical_tree.fingerprint_model",
            side_effect=AssertionError("verified transition rehashed the complete model"),
        ):
            transitioned = baseline.store_verified_transition(after, changes)

        self.assertEqual(transitioned.document_fingerprint, changes.after_fingerprint)
        self.assertEqual(transitioned.materialize(), after)
        self.assertIs(
            transitioned.glyph_shards["g0190"],
            baseline.glyph_shards["g0190"],
        )
        self.assertIsNot(
            transitioned.glyph_shards["g0191"],
            baseline.glyph_shards["g0191"],
        )
        self.assertEqual(transitioned.reused_glyph_count, 382)

    def test_verified_snapshot_transition_removes_a_deleted_root_encoding(self) -> None:
        before = _model(glyph_count=3, master_count=1)
        before["uiSession"] = {"tab": "A"}
        baseline = CanonicalSnapshot.from_model(before)
        after = copy.deepcopy(before)
        del after["uiSession"]

        changes = diff_models(baseline, after)
        transitioned = changes.apply(baseline)

        self.assertNotIn("uiSession", transitioned)
        self.assertNotIn("uiSession", transitioned.root_encodings)
        self.assertEqual(transitioned.materialize(), after)
        self.assertEqual(
            transitioned.document_fingerprint,
            fingerprint_model(after),
        )

    def test_master_duplication_reuses_every_unchanged_layer_encoding(self) -> None:
        model = _model(glyph_count=40, master_count=5)
        for glyph in model["glyphs"].values():
            glyph["layers"] = list(glyph["layers"].values())
        baseline = CanonicalSnapshot.from_model(model)
        build = build_master_updates(
            baseline,
            [
                {
                    "action": "duplicate",
                    "sourceMasterId": "m0",
                    "masterId": "m5",
                    "name": "M5",
                }
            ],
        )
        from glyphs_mcp_v2 import canonical_tree

        original = canonical_tree._json_bytes
        encoded_values = []

        def record(value):
            encoded_values.append(value)
            return original(value)

        with mock.patch(
            "glyphs_mcp_v2.canonical_tree._json_bytes",
            side_effect=record,
        ):
            transitioned = build.change_set.apply(baseline)

        for glyph_name in baseline.glyph_shards:
            for master_id in ("m0", "m1", "m2", "m3", "m4"):
                self.assertIs(
                    transitioned.glyph_layer_encodings[glyph_name][master_id],
                    baseline.glyph_layer_encodings[glyph_name][master_id],
                )
        self.assertFalse(
            any(
                isinstance(value, Mapping)
                and "layers" in value
                and "name" in value
                for value in encoded_values
            )
        )

    def test_master_request_builder_never_hashes_a_plain_whole_font_target(self) -> None:
        model = _model(glyph_count=40, master_count=5)
        for glyph in model["glyphs"].values():
            glyph["layers"] = list(glyph["layers"].values())
        baseline = CanonicalSnapshot.from_model(model)

        from glyphs_mcp_v2 import semantic

        original = semantic.canonical_json

        def reject_whole_font(value):
            if (
                isinstance(value, Mapping)
                and "font" in value
                and "glyphs" in value
            ):
                raise AssertionError("builder hashed a plain whole-font target")
            return original(value)

        with mock.patch(
            "glyphs_mcp_v2.semantic.canonical_json",
            side_effect=reject_whole_font,
        ):
            build = build_master_updates(
                baseline,
                [
                    {
                        "action": "duplicate",
                        "sourceMasterId": "m0",
                        "masterId": "m5",
                        "name": "M5",
                    }
                ],
            )

        self.assertEqual(len(build.change_set.changes), 41)
        self.assertTrue(build.change_set.after_fingerprint.startswith("sha256:"))

    def test_tree_store_persists_snapshot_shards_without_encoding_the_complete_model(self) -> None:
        snapshot = CanonicalSnapshot.from_model(_model(glyph_count=383, master_count=5))
        store = MemoryObjectStore()
        trees = CanonicalFontTree(store)
        from glyphs_mcp_v2 import canonical_tree

        original = canonical_tree.canonical_json
        encoded_values = []

        def record(value):
            encoded_values.append(value)
            return original(value)

        with mock.patch.object(
            CanonicalSnapshot,
            "materialize",
            side_effect=AssertionError("snapshot store materialized the complete model"),
        ), mock.patch(
            "glyphs_mcp_v2.canonical_tree.canonical_json",
            side_effect=record,
        ):
            stored = trees.store_model(snapshot)

        self.assertEqual(stored.model_fingerprint, snapshot.document_fingerprint)
        self.assertFalse(any(value is snapshot for value in encoded_values))
        self.assertFalse(
            any(
                isinstance(value, Mapping)
                and "font" in value
                and "glyphs" in value
                for value in encoded_values
            )
        )

    def test_applying_a_verified_change_set_to_a_snapshot_stays_copy_on_write(self) -> None:
        before = _model(glyph_count=383, master_count=5)
        baseline = CanonicalSnapshot.from_model(before)
        after = copy.deepcopy(before)
        after["masters"] = [after["masters"][1], after["masters"][0], *after["masters"][2:]]
        changes = diff_models(before, after)

        with mock.patch.object(
            CanonicalSnapshot,
            "materialize",
            side_effect=AssertionError("snapshot apply materialized the complete model"),
        ), mock.patch(
            "glyphs_mcp_v2.canonical_tree.fingerprint_model",
            side_effect=AssertionError("snapshot apply rehashed the complete model"),
        ):
            transitioned = changes.apply(baseline)

        self.assertIsInstance(transitioned, CanonicalSnapshot)
        self.assertEqual(transitioned.document_fingerprint, changes.after_fingerprint)
        self.assertEqual(transitioned.materialize(), after)
        self.assertEqual(transitioned.reused_glyph_count, 383)

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
            "complete_semantic_state",
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

    def test_verified_transition_accepts_large_glyph_membership_growth(self) -> None:
        trees = CanonicalFontTree(MemoryObjectStore())
        before = _model(glyph_count=389, master_count=5)
        after = _model(glyph_count=423, master_count=5)
        baseline = trees.store_model(before)
        changes = diff_models(before, after)

        transition = trees.store_verified_transition(
            baseline.tree_hash,
            after,
            changes,
        )

        self.assertEqual(len(after["glyphs"]) - len(before["glyphs"]), 34)
        self.assertEqual(transition.model_fingerprint, fingerprint_model(after))
        self.assertEqual(trees.load_model(transition.tree_hash), after)

    def test_verified_transition_accepts_top_level_deletion(self) -> None:
        trees = CanonicalFontTree(MemoryObjectStore())
        before = _model(glyph_count=3, master_count=1)
        before["temporaryRoot"] = {"value": True}
        after = copy.deepcopy(before)
        del after["temporaryRoot"]
        baseline = trees.store_model(before)

        transition = trees.store_verified_transition(
            baseline.tree_hash,
            after,
            diff_models(before, after),
        )

        self.assertEqual(transition.model_fingerprint, fingerprint_model(after))
        self.assertNotIn("temporaryRoot", trees.load_model(transition.tree_hash))

    def test_tree_diff_reads_only_changed_shards_not_both_complete_models(self) -> None:
        trees = CanonicalFontTree(MemoryObjectStore())
        before = _model(glyph_count=383, master_count=5)
        first = trees.store_model(before)
        after = copy.deepcopy(before)
        after["glyphs"]["g0191"]["export"] = False
        changes = diff_models(before, after)
        second = trees.store_verified_transition(
            first.tree_hash, after, changes
        )

        with mock.patch.object(
            trees,
            "load_model",
            side_effect=AssertionError("tree diff loaded a complete model"),
        ):
            observed = trees.diff(first.tree_hash, second.tree_hash)

        self.assertEqual(observed, changes)

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

    def test_initial_observation_stores_without_a_redundant_match_fingerprint(self) -> None:
        trace = ActionTraceCoordinator(ChangeHistory(CanonicalFontTree(MemoryObjectStore())))

        with mock.patch(
            "glyphs_mcp_v2.change_trace.fingerprint_model",
            side_effect=AssertionError("cold observation attempted a tree match"),
        ):
            tree_hash = trace.observe_model("doc_cold", self.before)

        self.assertTrue(tree_hash.startswith("sha256:"))

    def test_verified_patch_composition_preserves_unrelated_changes_and_cancellation(self) -> None:
        middle = copy.deepcopy(self.before)
        middle["glyphs"]["g0000"]["layers"]["m0"]["width"] = 520
        middle["glyphs"]["g0001"]["export"] = False
        final = copy.deepcopy(middle)
        final["glyphs"]["g0000"]["layers"]["m0"]["width"] = 500
        final["glyphs"]["g0002"]["export"] = False

        first = diff_models(self.before, middle)
        second = diff_models(middle, final)
        retained = next(
            change
            for change in first.changes
            if change.path == ("glyphs", "g0001", "export")
        )
        composed = compose_change_sets(first, second)

        self.assertEqual(composed, diff_models(self.before, final))
        self.assertEqual(composed.apply(self.before), final)
        self.assertIs(
            next(
                change
                for change in composed.changes
                if change.path == retained.path
            ),
            retained,
        )

    def test_verified_patch_composition_folds_child_edit_into_parent_addition(self) -> None:
        middle = copy.deepcopy(self.before)
        middle["glyphs"]["newGlyph"] = copy.deepcopy(
            middle["glyphs"]["g0000"]
        )
        middle["glyphs"]["newGlyph"]["name"] = "newGlyph"
        middle["glyphs"]["newGlyph"]["id"] = "id_newGlyph"
        final = copy.deepcopy(middle)
        final["glyphs"]["newGlyph"]["layers"]["m0"]["width"] = 640

        addition = diff_models(self.before, middle)
        nested_paths = addition.changes[0].after["layers"]["m0"]["paths"]
        composed = compose_change_sets(
            addition,
            diff_models(middle, final),
        )

        self.assertEqual(composed, diff_models(self.before, final))
        self.assertEqual(len(composed.changes), 1)
        self.assertEqual(composed.changes[0].path, ("glyphs", "newGlyph"))
        self.assertEqual(composed.apply(self.before), final)
        self.assertIs(
            composed.changes[0].after["layers"]["m0"]["paths"],
            nested_paths,
        )

    def test_verified_patch_composition_reconstructs_parent_before_deletion(self) -> None:
        middle = copy.deepcopy(self.before)
        middle["glyphs"]["g0000"]["layers"]["m0"]["width"] = 640
        final = copy.deepcopy(middle)
        del final["glyphs"]["g0000"]

        composed = compose_change_sets(
            diff_models(self.before, middle),
            diff_models(middle, final),
        )

        self.assertEqual(composed, diff_models(self.before, final))
        self.assertEqual(len(composed.changes), 1)
        self.assertEqual(composed.changes[0].path, ("glyphs", "g0000"))
        self.assertEqual(composed.changes[0].before, self.before["glyphs"]["g0000"])
        self.assertEqual(composed.apply(self.before), final)

    def test_master_membership_and_order_compose_to_the_exact_lifecycle_delta(self) -> None:
        baseline = _model(glyph_count=3, master_count=3)
        added = copy.deepcopy(baseline)
        added["masters"].append({"id": "m3", "name": "M3"})
        for glyph in added["glyphs"].values():
            glyph["layers"]["m3"] = _layer("m3")
        moved = copy.deepcopy(added)
        moved["masters"].insert(0, moved["masters"].pop())
        restored = copy.deepcopy(moved)
        restored["masters"].pop(0)
        for glyph in restored["glyphs"].values():
            glyph["layers"].pop("m3")

        composed = compose_change_sets(
            compose_change_sets(
                diff_models(baseline, added),
                diff_models(added, moved),
            ),
            diff_models(moved, restored),
        )

        self.assertEqual(composed, diff_models(baseline, restored))
        self.assertEqual(composed.apply(baseline), restored)

    def test_save_resets_visible_history(self) -> None:
        self.history.record_action(
            document_id="doc_a", tool="edit", effect="edit", status="success", run_id="run_1",
            before_model=self.before, after_model=self.after,
        )
        self.history.reset_after_save("doc_a")

        self.assertEqual(self.history.list_commits("doc_a"), ())
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
        trace.finish_action(
            scope,
            ToolResponse.success(
                tool="apply_spacing",
                effect="edit",
                summary="Applied spacing.",
                data={},
            ),
        )

        self.assertEqual(observed, baseline.tree_hash)
        self.assertEqual(token.before_tree_hash, baseline.tree_hash)
        self.assertEqual(trees.full_store_calls, 0)
        self.assertEqual(trees.transition_store_calls, 1)
        self.assertTrue(scope.transaction_completed)


if __name__ == "__main__":
    unittest.main()
