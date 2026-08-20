"""Schema-v3 contracts for identity-aware structural document changes."""

from __future__ import annotations

import copy
import itertools
import json
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.canonical_tree import CANONICAL_MODEL_SCHEMA_VERSION  # noqa: E402
from glyphs_mcp_v2.application import GlyphsMCPApplication  # noqa: E402
from glyphs_mcp_v2.catalog import TOOL_CATALOG  # noqa: E402
from glyphs_mcp_v2.semantic import (  # noqa: E402
    diff_models,
    fingerprint_model,
    public_change_dict,
    revert_change_set_onto,
)
from glyphs_mcp_v2.workflows import (  # noqa: E402
    build_glyph_updates,
    build_instance_updates,
    build_opentype_updates,
)


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
    def test_schema_v5_is_explicit(self) -> None:
        self.assertEqual(CANONICAL_MODEL_SCHEMA_VERSION, 5)

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

    def test_glyph_collection_create_and_delete_use_the_existing_domain_tool(self) -> None:
        before = _model()
        created = build_glyph_updates(
            before,
            [
                {
                    "action": "create",
                    "glyphName": "B",
                    "category": "Letter",
                    "subCategory": "Uppercase",
                    "unicode": "0042",
                    "export": True,
                }
            ],
        ).apply(before)
        self.assertIn("B", created["glyphs"])
        self.assertEqual(created["glyphs"]["B"]["name"], "B")

        deleted = build_glyph_updates(
            created, [{"action": "delete", "glyphName": "B"}]
        ).apply(created)
        self.assertNotIn("B", deleted["glyphs"])

    def test_opentype_collection_create_update_move_delete_share_one_builder(self) -> None:
        before = _model()
        changed = build_opentype_updates(
            before,
            [
                {
                    "action": "create",
                    "kind": "feature",
                    "name": "kern",
                    "code": "pos A V -80;",
                    "automatic": False,
                },
                {"action": "move", "kind": "feature", "name": "kern", "index": 0},
                {"action": "update", "kind": "feature", "name": "liga", "disabled": True},
            ],
        ).apply(before)

        self.assertEqual([item["id"] for item in changed["features"]], ["kern", "liga"])
        self.assertTrue(changed["features"][1]["disabled"])
        deleted = build_opentype_updates(
            changed, [{"action": "delete", "kind": "feature", "name": "kern"}]
        ).apply(changed)
        self.assertEqual([item["id"] for item in deleted["features"]], ["liga"])

    def test_instance_collection_has_one_direct_apply_contract(self) -> None:
        self.assertIn("apply_instance_updates", TOOL_CATALOG)
        before = _model()
        changed = build_instance_updates(
            before,
            [
                {
                    "action": "create",
                    "instanceId": "instance_bold",
                    "name": "Bold",
                    "type": "static",
                    "included": True,
                    "axes": [{"tag": "wght", "internal": 200, "external": 700}],
                },
                {
                    "action": "update",
                    "instanceId": "instance_regular",
                    "name": "Text",
                    "included": False,
                },
            ],
        ).apply(before)

        self.assertEqual([item["id"] for item in changed["instances"]], ["instance_regular", "instance_bold"])
        self.assertEqual(changed["instances"][0]["name"], "Text")
        self.assertFalse(changed["instances"][0]["included"])

        deleted = build_instance_updates(
            changed, [{"action": "delete", "instanceId": "instance_regular"}]
        ).apply(changed)
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
        response = app.invoke(
            "apply_instance_updates",
            {
                "documentId": "doc_structure",
                "expectedDocumentFingerprint": fingerprint_model(host.model),
                "updates": [
                    {
                        "action": "create",
                        "instanceId": "instance_bold",
                        "name": "Bold",
                        "axes": [{"tag": "wght", "internal": 200, "external": 700}],
                    }
                ],
                "reason": "structural transaction test",
            },
        ).to_dict()

        self.assertTrue(response["ok"], response)
        self.assertEqual(host.apply_calls, 1)
        operation_id = response["operationId"]
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
