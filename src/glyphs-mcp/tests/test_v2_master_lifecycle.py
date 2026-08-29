"""Schema-v4 contracts for verified master lifecycle mutations."""

from __future__ import annotations

import copy
import json
import sys
import time
import unittest
from pathlib import Path
from unittest import mock


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.application import GlyphsMCPApplication  # noqa: E402
from glyphs_mcp_v2.adapters import document as document_adapter  # noqa: E402
from glyphs_mcp_v2.canonical_tree import (  # noqa: E402
    CANONICAL_MODEL_SCHEMA_VERSION,
    CanonicalSnapshot,
)
from glyphs_mcp_v2.catalog import TOOL_CATALOG  # noqa: E402
from glyphs_mcp_v2.mutation import (  # noqa: E402
    MASTER_LIFECYCLE_CAPABILITY,
    CanonicalImpact,
    mutation_scope,
)
from glyphs_mcp_v2.semantic import diff_models, fingerprint_model  # noqa: E402
from glyphs_mcp_v2.generic_tools import resolve_selector  # noqa: E402
from glyphs_mcp_v2.structural_registry import build_master_updates  # noqa: E402


def _layer(master_id: str, name: str, x: float) -> dict:
    return {
        "id": master_id,
        "masterId": master_id,
        "name": name,
        "isMasterLayer": True,
        "isSpecialLayer": False,
        "hasAlignedWidth": False,
        "width": 600,
        "LSB": 50,
        "RSB": 50,
        "leftMetricsKey": None,
        "rightMetricsKey": None,
        "widthMetricsKey": None,
        "anchors": {},
        "paths": [
            {
                "closed": True,
                "nodes": [
                    {"x": x, "y": 0, "type": "line", "smooth": False, "name": None},
                    {"x": x + 100, "y": 0, "type": "line", "smooth": False, "name": None},
                ],
            }
        ],
        "components": [],
        "pathSignature": [2],
    }


def _model(glyph_count: int = 2) -> dict:
    masters = [
        {
            "id": "master_regular",
            "name": "Regular",
            "italicAngle": 0,
            "axes": [{"tag": "wght", "internal": 100}],
        },
        {
            "id": "master_bold",
            "name": "Bold",
            "italicAngle": 0,
            "axes": [{"tag": "wght", "internal": 200}],
        },
    ]
    glyphs = {}
    for index in range(glyph_count):
        name = "glyph{:04d}".format(index)
        glyphs[name] = {
            "id": "glyph_{}".format(name),
            "name": name,
            "category": "Letter",
            "subCategory": None,
            "unicode": None,
            "export": True,
            "leftKerningGroup": None,
            "rightKerningGroup": None,
            "mastersCompatible": True,
            "layers": [
                _layer("master_regular", "Regular", index),
                _layer("master_bold", "Bold", index + 20),
            ],
        }
    return {
        "font": {"familyName": "Master Lifecycle", "upm": 1000},
        "masters": masters,
        "instances": [],
        "glyphs": glyphs,
        "kerning": {
            "master_regular": {"glyph_glyph0000": {"glyph_glyph0001": -40}},
            "master_bold": {"glyph_glyph0000": {"glyph_glyph0001": -60}},
        },
        "features": [],
        "classes": [],
        "featurePrefixes": [],
    }


class _Host:
    def __init__(self, model: dict) -> None:
        self.model = copy.deepcopy(model)
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


def _layer_for(glyph: dict, identity: str) -> dict:
    return next(layer for layer in glyph["layers"] if layer["id"] == identity)


def _duplicate_master(app, host, document_id: str) -> dict:
    before = fingerprint_model(host.model)
    preview = app.invoke(
        "preview_change",
        {
            "documentId": document_id,
            "expectedDocumentFingerprint": before,
            "operations": [
                {
                    "op": "duplicate",
                    "target": {
                        "entity": "master",
                        "ids": ["master_regular"],
                    },
                    "newId": "master_text",
                    "overrides": {"name": "Text"},
                }
            ],
            "constraints": [],
        },
    ).to_dict()
    if not preview["ok"]:
        return preview
    return app.invoke(
        "apply_change",
        {
            "documentId": document_id,
            "previewId": preview["data"]["previewId"],
            "expectedDocumentFingerprint": before,
            "reason": "duplicate an exact master and its owned layers",
        },
    ).to_dict()


class MasterLifecycleTests(unittest.TestCase):
    def test_schema_v6_and_master_tools_are_explicit(self) -> None:
        self.assertEqual(CANONICAL_MODEL_SCHEMA_VERSION, 6)
        self.assertIn("read_document", TOOL_CATALOG)
        self.assertIn("preview_change", TOOL_CATALOG)
        self.assertIn("apply_change", TOOL_CATALOG)
        self.assertNotIn("list_masters", TOOL_CATALOG)
        self.assertNotIn("apply_master_updates", TOOL_CATALOG)

    def test_master_builder_accepts_the_immutable_snapshot_mapping(self) -> None:
        snapshot = CanonicalSnapshot.from_model(_model())

        build = build_master_updates(
            snapshot,
            [{"action": "move", "masterId": "master_bold", "index": 0}],
        )

        self.assertEqual(
            build.change_set.apply(snapshot)["masters"][0]["id"],
            "master_bold",
        )

    def test_list_masters_preserves_canonical_order_and_axes(self) -> None:
        items = [
            reference.value
            for reference in resolve_selector(
                _model(), {"entity": "master", "orderBy": "canonical"}
            )
        ]

        self.assertEqual([item["id"] for item in items], ["master_regular", "master_bold"])
        self.assertEqual(items[1]["axes"], [{"tag": "wght", "internal": 200}])

    def test_duplicate_is_one_build_with_derived_layers_and_kerning(self) -> None:
        before = _model()
        build = build_master_updates(
            before,
            [
                {
                    "action": "duplicate",
                    "sourceMasterId": "master_regular",
                    "masterId": "master_text",
                    "name": "Text",
                    "axes": [{"tag": "wght", "internal": 125}],
                    "index": 1,
                }
            ],
        )
        after = build.change_set.apply(before)

        self.assertEqual(build.capabilities, ("master_lifecycle",))
        self.assertEqual(
            build.execution_context["masterSources"],
            {"master_text": "master_regular"},
        )
        self.assertEqual(
            [master["id"] for master in after["masters"]],
            ["master_regular", "master_text", "master_bold"],
        )
        self.assertEqual(after["masters"][1]["name"], "Text")
        for glyph in after["glyphs"].values():
            self.assertEqual(
                [layer["id"] for layer in glyph["layers"][:3]],
                ["master_regular", "master_text", "master_bold"],
            )
            self.assertEqual(
                _layer_for(glyph, "master_text")["paths"],
                _layer_for(glyph, "master_regular")["paths"],
            )
            self.assertEqual(_layer_for(glyph, "master_text")["masterId"], "master_text")
        self.assertEqual(
            after["kerning"]["master_text"], before["kerning"]["master_regular"]
        )
        self.assertEqual(build.change_set.inverse().apply(after), before)

    def test_update_move_delete_share_the_same_builder(self) -> None:
        before = _model()
        updated = build_master_updates(
            before,
            [
                {
                    "action": "update",
                    "masterId": "master_bold",
                    "name": "Display",
                    "italicAngle": 12,
                    "axes": [{"tag": "wght", "internal": 240}],
                },
                {"action": "move", "masterId": "master_bold", "index": 0},
            ],
        ).change_set.apply(before)

        self.assertEqual(updated["masters"][0]["id"], "master_bold")
        self.assertEqual(updated["masters"][0]["name"], "Display")
        self.assertEqual(updated["masters"][0]["italicAngle"], 12)

        build = build_master_updates(
            updated, [{"action": "delete", "masterId": "master_regular"}]
        )
        deleted = build.change_set.apply(updated)
        self.assertEqual([master["id"] for master in deleted["masters"]], ["master_bold"])
        self.assertNotIn("master_regular", deleted["kerning"])
        self.assertTrue(
            all(
                all(layer["id"] != "master_regular" for layer in glyph["layers"])
                for glyph in deleted["glyphs"].values()
            )
        )
        self.assertEqual(build.change_set.inverse().apply(deleted), updated)

    def test_delete_refuses_the_final_master_and_special_layer_dependencies(self) -> None:
        final = _model()
        final["masters"] = final["masters"][:1]
        for glyph in final["glyphs"].values():
            glyph["layers"] = [
                layer for layer in glyph["layers"] if layer["id"] != "master_bold"
            ]
        final["kerning"].pop("master_bold")
        with self.assertRaisesRegex(ValueError, "final master"):
            build_master_updates(final, [{"action": "delete", "masterId": "master_regular"}])

        special = _model()
        special["glyphs"]["glyph0000"]["layers"].append({
            **_layer("brace-layer", "{125}", 3),
            "masterId": "master_regular",
            "isMasterLayer": False,
            "isSpecialLayer": True,
        })
        with self.assertRaisesRegex(ValueError, "special layer"):
            build_master_updates(special, [{"action": "delete", "masterId": "master_regular"}])

    def test_master_duplicate_impacts_one_layer_entity_per_glyph(self) -> None:
        before = _model(40)
        build = build_master_updates(
            before,
            [
                {
                    "action": "duplicate",
                    "sourceMasterId": "master_regular",
                    "masterId": "master_text",
                    "name": "Text",
                }
            ],
        )

        scope = mutation_scope(before, build.change_set)
        impact = CanonicalImpact.from_change_set(before, build.change_set)
        self.assertEqual(scope.roots, ("glyphs", "kerning", "masters"))
        self.assertEqual(len(scope.glyph_names), 40)
        self.assertEqual(len(impact.glyph_names), 40)
        self.assertTrue(
            all(impact.layer_ids(name) == ("master_text",) for name in impact.glyph_names)
        )
        self.assertTrue(
            all(not impact.requires_complete_glyph(name) for name in impact.glyph_names)
        )

    def test_master_builder_reuses_unchanged_layer_branches_and_never_full_diffs_glyphs(self) -> None:
        snapshot = CanonicalSnapshot.from_model(_model(383))
        source_paths = _layer_for(
            snapshot.glyph_shards["glyph0000"], "master_regular"
        )["paths"]

        with mock.patch(
            "glyphs_mcp_v2.mutation.diff_models",
            wraps=diff_models,
        ) as diff:
            build = build_master_updates(
                snapshot,
                [
                    {
                        "action": "duplicate",
                        "sourceMasterId": "master_regular",
                        "masterId": "master_text",
                        "name": "Text",
                    }
                ],
            )

        layer_addition = next(
            change
            for change in build.change_set.changes
            if change.path == (
                "glyphs",
                "glyph0000",
                "layers",
                "master_text",
            )
        )
        self.assertIs(layer_addition.after["paths"], source_paths)
        self.assertTrue(
            all("glyphs" not in call.args[0] for call in diff.call_args_list)
        )

    def test_master_move_and_scalar_update_materialize_no_glyphs(self) -> None:
        before = _model(40)
        moved = build_master_updates(
            before, [{"action": "move", "masterId": "master_bold", "index": 0}]
        )
        updated = build_master_updates(
            before,
            [
                {
                    "action": "update",
                    "masterId": "master_bold",
                    "italicAngle": 12,
                    "axes": [{"tag": "wght", "internal": 240}],
                }
            ],
        )

        self.assertEqual(
            CanonicalImpact.from_change_set(before, moved.change_set).glyph_names,
            (),
        )
        self.assertEqual(
            CanonicalImpact.from_change_set(before, updated.change_set).glyph_names,
            (),
        )

    def test_master_verification_strategy_follows_path_derived_impact(self) -> None:
        before = _model(40)
        moved = build_master_updates(
            before, [{"action": "move", "masterId": "master_bold", "index": 0}]
        )
        updated = build_master_updates(
            before,
            [{
                "action": "update",
                "masterId": "master_bold",
                "italicAngle": 12,
                "axes": [{"tag": "wght", "internal": 240}],
            }],
        )
        renamed = build_master_updates(
            before,
            [{"action": "update", "masterId": "master_bold", "name": "Display"}],
        )
        duplicated = build_master_updates(
            before,
            [{
                "action": "duplicate",
                "sourceMasterId": "master_regular",
                "masterId": "master_text",
                "name": "Text",
            }],
        )

        self.assertFalse(document_adapter._impact_prefers_persistent_verification(
            CanonicalImpact.from_change_set(before, moved.change_set)
        ))
        self.assertFalse(document_adapter._impact_prefers_persistent_verification(
            CanonicalImpact.from_change_set(before, updated.change_set)
        ))
        self.assertTrue(document_adapter._impact_prefers_persistent_verification(
            CanonicalImpact.from_change_set(before, renamed.change_set)
        ))
        self.assertTrue(document_adapter._impact_prefers_persistent_verification(
            CanonicalImpact.from_change_set(before, duplicated.change_set)
        ))

    def test_master_rename_targets_only_corresponding_layer_name_fragments(self) -> None:
        before = _model(40)
        renamed = build_master_updates(
            before,
            [
                {
                    "action": "update",
                    "masterId": "master_bold",
                    "name": "Display",
                }
            ],
        )
        impact = CanonicalImpact.from_change_set(before, renamed.change_set)

        self.assertEqual(len(impact.glyph_names), 40)
        self.assertTrue(
            all(impact.layer_ids(name) == ("master_bold",) for name in impact.glyph_names)
        )
        self.assertTrue(
            all(
                all(path[-1] == "name" for path in impact.glyph_paths[name])
                for name in impact.glyph_names
            )
        )

    def test_direct_apply_and_revert_use_one_transaction_each(self) -> None:
        baseline = _model()
        host = _Host(baseline)
        app = GlyphsMCPApplication(host)
        response = _duplicate_master(app, host, "doc_master")

        self.assertTrue(response["ok"], response)
        self.assertEqual(host.apply_calls, 1)
        self.assertEqual(response["data"]["transactionCount"], 1)
        self.assertNotIn("stageTimings", response["data"])
        self.assertLess(len(json.dumps(response).encode("utf-8")), 64 * 1024)

        reverted = app.invoke(
            "revert_change",
            {
                "documentId": "doc_master",
                "operationId": response["data"]["operationId"],
                "expectedDocumentFingerprint": fingerprint_model(host.model),
            },
        ).to_dict()
        self.assertTrue(reverted["ok"], reverted)
        self.assertEqual(host.apply_calls, 2)
        self.assertEqual(host.model, baseline)

    def test_direct_apply_composes_capabilities_from_the_semantic_patch(self) -> None:
        class CapabilityHost(_Host):
            def __init__(self, model):
                super().__init__(model)
                self.simulated_capabilities = ()

            def simulate_verified_change_set(
                self,
                document_id,
                change_set,
                before_model,
                *,
                required_after_model=None,
                capabilities=(),
                execution_context=None,
                removes_contribution_id=None,
            ):
                self.simulated_capabilities = tuple(capabilities)
                return {
                    "afterModel": change_set.apply(before_model),
                    "replayReplacements": [],
                }

        host = CapabilityHost(_model())
        app = GlyphsMCPApplication(host)
        with mock.patch(
            "glyphs_mcp_v2.application.lifecycle_capabilities",
            return_value=("derived_capability",),
        ) as derive:
            response = _duplicate_master(app, host, "doc_master")

        self.assertTrue(response["ok"], response)
        derive.assert_called_once()
        self.assertEqual(
            set(host.simulated_capabilities),
            {
                MASTER_LIFECYCLE_CAPABILITY,
                "derived_capability",
            },
        )

    def test_master_revert_preserves_unrelated_edits_and_refuses_overlap(self) -> None:
        host = _Host(_model())
        app = GlyphsMCPApplication(host)
        response = _duplicate_master(app, host, "doc_master")
        host.model["font"]["note"] = "later unrelated edit"
        reverted = app.invoke(
            "revert_change",
            {
                "documentId": "doc_master",
                "operationId": response["data"]["operationId"],
                "expectedDocumentFingerprint": fingerprint_model(host.model),
            },
        ).to_dict()
        self.assertTrue(reverted["ok"], reverted)
        self.assertEqual(host.model["font"]["note"], "later unrelated edit")
        self.assertNotIn("master_text", [item["id"] for item in host.model["masters"]])

        conflicting_host = _Host(_model())
        conflicting_app = GlyphsMCPApplication(conflicting_host)
        created = _duplicate_master(
            conflicting_app, conflicting_host, "doc_master_conflict"
        )
        conflicting_host.model["masters"][-1]["name"] = "Manual Edit"
        before_conflict = copy.deepcopy(conflicting_host.model)
        refused = conflicting_app.invoke(
            "revert_change",
            {
                "documentId": "doc_master_conflict",
                "operationId": created["data"]["operationId"],
                "expectedDocumentFingerprint": fingerprint_model(conflicting_host.model),
            },
        ).to_dict()
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["error"]["code"], "revert_conflict")
        self.assertEqual(conflicting_host.model, before_conflict)

    def test_scale_build_is_linear_and_public_response_is_bounded(self) -> None:
        before = _model(383)
        build = build_master_updates(
            before,
            [
                {
                    "action": "duplicate",
                    "sourceMasterId": "master_regular",
                    "masterId": "master_text",
                    "name": "Text",
                }
            ],
        )
        after = build.change_set.apply(before)

        self.assertEqual(len(after["glyphs"]), 383)
        self.assertEqual(build.change_set.inverse().apply(after), before)

        host = _Host(before)
        response = _duplicate_master(
            GlyphsMCPApplication(host), host, "doc_master_scale"
        )
        self.assertTrue(response["ok"], response)
        self.assertEqual(response["data"]["transactionCount"], 1)
        self.assertGreater(response["data"]["observedChangeCount"], 383)
        self.assertEqual(host.apply_calls, 1)
        self.assertLess(len(json.dumps(response).encode("utf-8")), 64 * 1024)

    def test_1000_glyph_master_plan_stays_inside_snapshot_budget(self) -> None:
        before = _model(1000)
        started = time.perf_counter()
        build = build_master_updates(
            before,
            [
                {
                    "action": "duplicate",
                    "sourceMasterId": "master_regular",
                    "masterId": "master_text",
                    "name": "Text",
                }
            ],
        )
        elapsed = time.perf_counter() - started
        after = build.change_set.apply(before)

        self.assertLess(elapsed, 2.0)
        self.assertEqual(len(build.change_set.changes), 1002)
        self.assertEqual(build.change_set.inverse().apply(after), before)


if __name__ == "__main__":
    unittest.main()
