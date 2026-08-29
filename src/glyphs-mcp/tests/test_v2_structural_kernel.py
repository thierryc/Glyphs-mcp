"""Canonical structural contracts shared by schema-v6 document changes."""

from __future__ import annotations

import copy
import itertools
import json
import sys
import unittest
from pathlib import Path
from unittest import mock


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.canonical_tree import (  # noqa: E402
    CANONICAL_MODEL_SCHEMA_VERSION,
    CanonicalSnapshot,
)
from glyphs_mcp_v2.application import GlyphsMCPApplication  # noqa: E402
from glyphs_mcp_v2.catalog import TOOL_CATALOG  # noqa: E402
from glyphs_mcp_v2.semantic import (  # noqa: E402
    ChangeSet,
    SemanticChange,
    diff_models,
    fingerprint_model,
    public_change_dict,
    revert_change_set_onto,
    subset_change_set,
)
from glyphs_mcp_v2.generic_tools import build_change_set  # noqa: E402
from glyphs_mcp_v2.mutation import master_owns_layer_order_change  # noqa: E402


def _model() -> dict:
    return {
        "font": {"familyName": "Structure", "upm": 1000},
        "masters": [{"id": "m0", "name": "Regular"}],
        "instances": [
            {
                "id": "instance_regular",
                "name": "Regular",
                "type": "static",
                "included": True,
                "inclusionReason": None,
                "interpolationSupported": True,
                "axes": [{"tag": "wght", "internal": 100, "external": 400}],
            }
        ],
        "glyphs": {
            "A": {
                "id": "glyph_A",
                "name": "A",
                "category": "Letter",
                "subCategory": "Uppercase",
                "unicode": "0041",
                "export": True,
                "leftKerningGroup": "A",
                "rightKerningGroup": "A",
                "layers": [],
            }
        },
        "kerning": {},
        "features": [
            {
                "id": "liga",
                "name": "liga",
                "code": "sub f i by fi;",
                "automatic": False,
                "disabled": False,
            }
        ],
        "classes": [],
        "featurePrefixes": [],
    }


class StructuralKernelTests(unittest.TestCase):
    def test_schema_v6_is_explicit(self) -> None:
        self.assertEqual(CANONICAL_MODEL_SCHEMA_VERSION, 6)

    def test_identity_collection_diff_is_entity_based_and_reproducible(self) -> None:
        before = _model()
        after = copy.deepcopy(before)
        after["features"][0]["code"] = "sub f f i by ffi;"
        after["features"].append(
            {
                "id": "kern",
                "name": "kern",
                "code": "pos A V -80;",
                "automatic": False,
                "disabled": False,
            }
        )

        changes = diff_models(before, after)

        self.assertEqual(changes.apply(before), after)
        self.assertEqual(
            {change.path for change in changes.changes},
            {("features", "liga", "code"), ("features", "kern")},
        )

    def test_reorder_is_one_identity_order_change(self) -> None:
        before = _model()
        before["features"].append(
            {"id": "kern", "name": "kern", "code": "", "automatic": True, "disabled": False}
        )
        after = copy.deepcopy(before)
        after["features"] = list(reversed(after["features"]))

        changes = diff_models(before, after)

        self.assertEqual([change.path for change in changes.changes], [("features", "$order")])
        self.assertEqual(changes.apply(before), after)

    def test_multiple_additions_preserve_declared_identity_order(self) -> None:
        before = _model()
        after = copy.deepcopy(before)
        after["features"].extend(
            [
                {"id": "cv99", "name": "cv99", "code": "", "automatic": False, "disabled": False},
                {"id": "cv98", "name": "cv98", "code": "", "automatic": False, "disabled": False},
            ]
        )

        changes = diff_models(before, after)

        self.assertEqual(changes.apply(before), after)
        self.assertIn(("features", "$order"), [change.path for change in changes.changes])

    def test_multiple_deletions_keep_the_inverse_reproducible(self) -> None:
        before = _model()
        before["features"] = [
            {"id": name, "name": name, "code": "", "automatic": False, "disabled": False}
            for name in ("cv98", "liga", "cv99")
        ]
        after = copy.deepcopy(before)
        after["features"] = [after["features"][1]]

        changes = diff_models(before, after)

        self.assertEqual(changes.apply(before), after)
        self.assertEqual(changes.inverse().apply(after), before)
        self.assertIn(("features", "$order"), [change.path for change in changes.changes])

    def test_rebased_order_inverse_preserves_an_unrelated_later_entity(self) -> None:
        before = _model()
        before["features"].append(
            {"id": "kern", "name": "kern", "code": "", "automatic": False, "disabled": False}
        )
        after = copy.deepcopy(before)
        after["features"] = list(reversed(after["features"]))
        original = diff_models(before, after)
        current = copy.deepcopy(after)
        current["features"].insert(
            1,
            {"id": "calt", "name": "calt", "code": "", "automatic": False, "disabled": False},
        )

        inverse, conflicts = revert_change_set_onto(current, original)

        self.assertEqual(conflicts, ())
        self.assertIsNotNone(inverse)
        reverted = inverse.apply(current)
        self.assertEqual(
            [item["id"] for item in reverted["features"]],
            ["liga", "calt", "kern"],
        )

    def test_snapshot_projection_and_revert_never_copy_the_complete_font(self) -> None:
        before = _model()
        before["glyphs"].update(
            {
                "g{:03d}".format(index): {
                    "id": "glyph_g{:03d}".format(index),
                    "name": "g{:03d}".format(index),
                    "export": True,
                    "layers": [],
                }
                for index in range(382)
            }
        )
        snapshot = CanonicalSnapshot.from_model(before)
        after = snapshot.materialize()
        after["font"]["note"] = "unrelated derived projection"
        after["glyphs"]["A"]["export"] = False
        observed = diff_models(snapshot, after)

        complete_copies = []
        real_deepcopy = copy.deepcopy

        def tracked_deepcopy(value, memo=None):
            if isinstance(value, dict) and "glyphs" in value:
                complete_copies.append(value)
            return real_deepcopy(value, memo) if memo is not None else real_deepcopy(value)

        with mock.patch(
            "glyphs_mcp_v2.semantic.copy.deepcopy",
            side_effect=tracked_deepcopy,
        ):
            glyph_only = subset_change_set(
                snapshot,
                observed,
                lambda change: change.path[:2] == ("glyphs", "A"),
            )
            changed = glyph_only.apply(snapshot)
            inverse, conflicts = revert_change_set_onto(changed, glyph_only)

        self.assertEqual(conflicts, ())
        self.assertIsNotNone(inverse)
        restored = inverse.apply(changed)
        self.assertEqual(restored.document_fingerprint, snapshot.document_fingerprint)
        self.assertIs(restored.glyph_shards["g381"], snapshot.glyph_shards["g381"])
        self.assertEqual(complete_copies, [])

    def test_master_owns_layer_insertion_when_a_glyph_lacks_other_master_layers(self) -> None:
        master_add = SemanticChange(
            path=("masters", "m4"),
            after={"id": "m4", "name": "Added"},
            before_present=False,
        )
        layer_add = SemanticChange(
            path=("glyphs", "A", "layers", "m4"),
            after={"id": "m4", "masterId": "m4", "isMasterLayer": True},
            before_present=False,
        )
        master_order = SemanticChange(
            path=("masters", "$order"),
            before=["m1", "m2", "m3"],
            after=["m1", "m4", "m2", "m3"],
        )
        layer_order = SemanticChange(
            path=("glyphs", "A", "layers", "$order"),
            before=["m1", "m3", "special"],
            after=["m1", "m4", "m3", "special"],
        )
        changes = ChangeSet.from_changes(
            before_fingerprint="before",
            after_fingerprint="after",
            changes=(master_add, layer_add, master_order, layer_order),
        )

        self.assertTrue(master_owns_layer_order_change(layer_order, changes))

    def test_all_small_identity_membership_and_order_transitions_are_reversible(self) -> None:
        identities = ("a", "b", "c", "d")
        orders = [
            order
            for length in range(len(identities) + 1)
            for members in itertools.combinations(identities, length)
            for order in itertools.permutations(members)
        ]

        for before_order in orders:
            before = _model()
            before["features"] = [
                {"id": name, "name": name, "code": "", "automatic": False, "disabled": False}
                for name in before_order
            ]
            for after_order in orders:
                after = copy.deepcopy(before)
                after["features"] = [
                    {"id": name, "name": name, "code": "", "automatic": False, "disabled": False}
                    for name in after_order
                ]
                changes = diff_models(before, after)
                self.assertEqual(changes.apply(before), after)
                self.assertEqual(changes.inverse().apply(after), before)

    def test_numeric_entity_ids_are_not_confused_with_list_indexes(self) -> None:
        before = _model()
        before["features"] = [
            {"id": "1234", "name": "1234", "code": "before", "automatic": False, "disabled": False}
        ]
        after = copy.deepcopy(before)
        after["features"][0]["code"] = "after"

        changes = diff_models(before, after)

        self.assertEqual(changes.changes[0].path, ("features", "1234", "code"))
        self.assertEqual(changes.apply(before), after)

    def test_membership_and_reorder_inverse_restores_exact_original_order(self) -> None:
        before = _model()
        before["features"].extend(
            [
                {"id": "kern", "name": "kern", "code": "", "automatic": True, "disabled": False},
                {"id": "calt", "name": "calt", "code": "", "automatic": True, "disabled": False},
            ]
        )
        after_delete = copy.deepcopy(before)
        del after_delete["features"][1]
        after_delete["features"] = list(reversed(after_delete["features"]))
        deletion = diff_models(before, after_delete)

        self.assertEqual(deletion.inverse().apply(after_delete), before)
        rebased_delete, conflicts = revert_change_set_onto(after_delete, deletion)
        self.assertEqual(conflicts, ())
        self.assertIsNotNone(rebased_delete)
        self.assertEqual(rebased_delete.apply(after_delete), before)

        after_add = copy.deepcopy(before)
        after_add["features"].insert(
            0,
            {"id": "rvrn", "name": "rvrn", "code": "", "automatic": True, "disabled": False},
        )
        addition = diff_models(before, after_add)
        self.assertEqual(addition.inverse().apply(after_add), before)

    def test_structural_result_summarizes_large_entities_without_losing_stored_diff(self) -> None:
        before = _model()
        after = copy.deepcopy(before)
        after["glyphs"]["B"] = {
            "id": "glyph_B",
            "name": "B",
            "layers": {"m0": {"paths": [{"payload": "x" * 100_000}]}},
        }
        changes = diff_models(before, after)

        public = public_change_dict(changes.changes[0])

        self.assertLess(len(json.dumps(public).encode("utf-8")), 2048)
        self.assertEqual(public["after"]["id"], "glyph_B")
        self.assertEqual(changes.apply(before), after)

    def test_selective_revert_of_structural_append_preserves_later_append(self) -> None:
        baseline = _model()
        first = copy.deepcopy(baseline)
        first["features"].append(
            {"id": "kern", "name": "kern", "code": "", "automatic": True, "disabled": False}
        )
        first_change = diff_models(baseline, first)
        current = copy.deepcopy(first)
        current["classes"].append(
            {"id": "Uppercase", "name": "Uppercase", "code": "A B", "automatic": False, "disabled": False}
        )

        inverse, conflicts = revert_change_set_onto(current, first_change)

        self.assertEqual(conflicts, ())
        self.assertIsNotNone(inverse)
        reverted = inverse.apply(current)
        self.assertEqual(reverted["features"], baseline["features"])
        self.assertEqual(reverted["classes"], current["classes"])

    def test_selective_revert_rebases_order_only_identity_sequence(self) -> None:
        baseline = _model()
        baseline["glyphOrder"] = ["A"]
        first = copy.deepcopy(baseline)
        first["glyphOrder"].append("B")
        first_change = diff_models(baseline, first)
        current = copy.deepcopy(first)
        current["glyphOrder"].append("C")

        inverse, conflicts = revert_change_set_onto(current, first_change)

        self.assertEqual(conflicts, ())
        self.assertIsNotNone(inverse)
        self.assertEqual(inverse.apply(current)["glyphOrder"], ["A", "C"])

    def test_selective_revert_restores_deleted_identity_without_moving_later_one(self) -> None:
        baseline = _model()
        baseline["glyphOrder"] = ["A", "B"]
        first = copy.deepcopy(baseline)
        first["glyphOrder"] = ["B"]
        first_change = diff_models(baseline, first)
        current = copy.deepcopy(first)
        current["glyphOrder"].append("C")

        inverse, conflicts = revert_change_set_onto(current, first_change)

        self.assertEqual(conflicts, ())
        self.assertIsNotNone(inverse)
        self.assertEqual(inverse.apply(current)["glyphOrder"], ["A", "B", "C"])

    def test_selective_revert_refuses_a_third_identity_sequence_order(self) -> None:
        baseline = _model()
        baseline["glyphOrder"] = ["A", "B", "C"]
        first = copy.deepcopy(baseline)
        first["glyphOrder"] = ["B", "A", "C"]
        first_change = diff_models(baseline, first)
        current = copy.deepcopy(first)
        current["glyphOrder"] = ["A", "C", "B"]

        inverse, conflicts = revert_change_set_onto(current, first_change)

        self.assertIsNone(inverse)
        self.assertEqual(conflicts, (("glyphOrder", "$order"),))

    def test_glyph_collection_create_and_delete_use_generic_operations(self) -> None:
        before = _model()
        created = build_change_set(
            before,
            [
                {
                    "op": "insert",
                    "target": {"entity": "document", "ids": ["document"]},
                    "field": "glyphs",
                    "newId": "B",
                    "value": {
                        "id": "glyph_B",
                        "name": "B",
                        "category": "Letter",
                        "subCategory": "Uppercase",
                        "unicode": "0042",
                        "export": True,
                        "layers": [],
                    },
                }
            ],
        ).change_set.apply(before)
        self.assertIn("B", created["glyphs"])
        self.assertEqual(created["glyphs"]["B"]["name"], "B")

        deleted = build_change_set(
            created,
            [{"op": "remove", "target": {"entity": "glyph", "ids": ["B"]}}],
        ).change_set.apply(created)
        self.assertNotIn("B", deleted["glyphs"])

    def test_opentype_collection_lifecycle_uses_generic_operations(self) -> None:
        before = _model()
        changed = build_change_set(
            before,
            [
                {
                    "op": "insert",
                    "target": {"entity": "document", "ids": ["document"]},
                    "field": "features",
                    "value": {
                        "id": "kern",
                        "name": "kern",
                        "code": "pos A V -80;",
                        "automatic": False,
                        "disabled": False,
                    },
                    "index": 0,
                },
                {
                    "op": "set",
                    "target": {"entity": "feature", "ids": ["liga"]},
                    "field": "disabled",
                    "value": True,
                },
            ],
        ).change_set.apply(before)

        self.assertEqual([item["id"] for item in changed["features"]], ["kern", "liga"])
        self.assertTrue(changed["features"][1]["disabled"])
        moved = build_change_set(
            changed,
            [{"op": "move", "target": {"entity": "feature", "ids": ["liga"]}, "index": 0}],
        ).change_set.apply(changed)
        self.assertEqual([item["id"] for item in moved["features"]], ["liga", "kern"])
        deleted = build_change_set(
            moved,
            [{"op": "remove", "target": {"entity": "feature", "ids": ["kern"]}}],
        ).change_set.apply(moved)
        self.assertEqual([item["id"] for item in deleted["features"]], ["liga"])

    def test_instance_collection_has_one_generic_apply_contract(self) -> None:
        self.assertIn("preview_change", TOOL_CATALOG)
        self.assertIn("apply_change", TOOL_CATALOG)
        self.assertNotIn("apply_instance_updates", TOOL_CATALOG)
        before = _model()
        changed = build_change_set(
            before,
            [
                {
                    "op": "insert",
                    "target": {"entity": "document", "ids": ["document"]},
                    "field": "instances",
                    "value": {
                        "id": "instance_bold",
                        "name": "Bold",
                        "type": "static",
                        "included": True,
                        "axes": [{"tag": "wght", "internal": 200, "external": 700}],
                    },
                },
                {
                    "op": "set",
                    "target": {"entity": "instance", "ids": ["instance_regular"]},
                    "field": "name",
                    "value": "Text",
                },
                {
                    "op": "set",
                    "target": {"entity": "instance", "ids": ["instance_regular"]},
                    "field": "included",
                    "value": False,
                },
            ],
        ).change_set.apply(before)

        self.assertEqual([item["id"] for item in changed["instances"]], ["instance_regular", "instance_bold"])
        self.assertEqual(changed["instances"][0]["name"], "Text")
        self.assertFalse(changed["instances"][0]["included"])
        created = changed["instances"][1]
        self.assertEqual(created["name"], "Bold")
        self.assertTrue(created["included"])

        deleted = build_change_set(
            changed,
            [{"op": "remove", "target": {"entity": "instance", "ids": ["instance_regular"]}}],
        ).change_set.apply(changed)
        self.assertEqual([item["id"] for item in deleted["instances"]], ["instance_bold"])

    def test_structural_apply_and_revert_use_the_shared_transaction_kernel(self) -> None:
        class Host:
            def __init__(self) -> None:
                self.model = _model()
                self.apply_calls = 0

            def capture_model(self, document_id):
                return copy.deepcopy(self.model)

            def simulate_change_set(self, document_id, change_set):
                return change_set.apply(self.model)

            def apply_change_set(self, document_id, change_set):
                self.apply_calls += 1
                self.model = change_set.apply(self.model)

            def restore_model(self, document_id, model):
                self.model = copy.deepcopy(model)

        host = Host()
        app = GlyphsMCPApplication(host)
        baseline = copy.deepcopy(host.model)
        before = fingerprint_model(host.model)
        preview = app.invoke(
            "preview_change",
            {
                "documentId": "doc_structure",
                "expectedDocumentFingerprint": before,
                "operations": [
                    {
                        "op": "insert",
                        "target": {"entity": "document", "ids": ["document"]},
                        "field": "instances",
                        "value": {
                            "id": "instance_bold",
                            "name": "Bold",
                            "type": "static",
                            "included": True,
                            "inclusionReason": None,
                            "interpolationSupported": True,
                            "axes": [
                                {"tag": "wght", "internal": 200, "external": 700}
                            ],
                        },
                    }
                ],
                "constraints": [],
            },
        ).to_dict()
        self.assertTrue(preview["ok"], preview)
        response = app.invoke(
            "apply_change",
            {
                "documentId": "doc_structure",
                "previewId": preview["data"]["previewId"],
                "expectedDocumentFingerprint": before,
                "reason": "generic structural transaction test",
            },
        ).to_dict()

        self.assertTrue(response["ok"], response)
        self.assertEqual(host.apply_calls, 1)
        operation_id = response["data"]["operationId"]
        reverted = app.invoke(
            "revert_change",
            {
                "documentId": "doc_structure",
                "operationId": operation_id,
                "expectedDocumentFingerprint": fingerprint_model(host.model),
            },
        ).to_dict()

        self.assertTrue(reverted["ok"], reverted)
        self.assertEqual(host.model, baseline)
        self.assertEqual(host.apply_calls, 2)


if __name__ == "__main__":
    unittest.main()
