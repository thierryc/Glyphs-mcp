"""Schema-v5 contracts for identity-addressed non-master layer lifecycle."""

from __future__ import annotations

import copy
import inspect
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.adapters.document import native_layer_to_model  # noqa: E402
from glyphs_mcp_v2.application import GlyphsMCPApplication  # noqa: E402
from glyphs_mcp_v2.canonical_collections import (  # noqa: E402
    is_identity_collection_path,
)
from glyphs_mcp_v2.canonical_tree import (  # noqa: E402
    CANONICAL_MODEL_SCHEMA_VERSION,
    CanonicalFontTree,
    CanonicalSnapshot,
    MemoryObjectStore,
)
from glyphs_mcp_v2.change_history import ChangeHistory  # noqa: E402
from glyphs_mcp_v2.catalog import TOOL_CATALOG  # noqa: E402
from glyphs_mcp_v2.mutation import (  # noqa: E402
    CanonicalImpact,
    LAYER_LIFECYCLE_CAPABILITY,
)
from glyphs_mcp_v2.semantic import (  # noqa: E402
    diff_models,
    fingerprint_model,
    public_change_dict,
    revert_change_set_onto,
)
from glyphs_mcp_v2.diff_overlay import overlay_for_layer  # noqa: E402
from glyphs_mcp_v2.transport.fastmcp import ToolHandlers  # noqa: E402
from glyphs_mcp_v2.workflows import (  # noqa: E402
    build_layer_updates,
    list_layers,
)


def _layer(
    identity: str,
    master_id: str,
    name: str,
    *,
    roles: tuple[str, ...],
    interpolation=None,
    x: float = 0,
) -> dict:
    return {
        "id": identity,
        "masterId": master_id,
        "name": name,
        "roles": list(roles),
        "isMasterLayer": "master" in roles,
        "isSpecialLayer": bool(set(roles) & {"intermediate", "alternate", "smart"}),
        "hasAlignedWidth": False,
        "interpolation": copy.deepcopy(interpolation),
        "attributes": {},
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


def _model() -> dict:
    return {
        "font": {"familyName": "Layer Lifecycle", "upm": 1000},
        "masters": [
            {
                "id": "m0",
                "name": "Regular",
                "italicAngle": 0,
                "axes": [
                    {"tag": "wght", "internal": 100},
                    {"tag": "wdth", "internal": 100},
                ],
            }
        ],
        "instances": [],
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
                "mastersCompatible": True,
                "layers": [
                    _layer("m0", "m0", "Regular", roles=("master",)),
                    _layer(
                        "brace-125",
                        "m0",
                        "{125}",
                        roles=("intermediate",),
                        interpolation={
                            "kind": "intermediate",
                            "coordinates": {"wght": 125},
                        },
                        x=10,
                    ),
                    _layer(
                        "bracket-400",
                        "m0",
                        "[400]",
                        roles=("alternate",),
                        interpolation={
                            "kind": "alternate",
                            "ranges": {"wght": {"min": 400, "max": None}},
                        },
                        x=20,
                    ),
                    _layer("backup-1", "m0", "Backup", roles=("backup",), x=30),
                ],
            },
            "B": {
                "id": "glyph_B",
                "name": "B",
                "category": "Letter",
                "subCategory": "Uppercase",
                "unicode": "0042",
                "export": True,
                "leftKerningGroup": "B",
                "rightKerningGroup": "B",
                "mastersCompatible": True,
                "layers": [_layer("m0", "m0", "Regular", roles=("master",))],
            },
        },
        "kerning": {},
        "features": [],
        "classes": [],
        "featurePrefixes": [],
    }


class LayerLifecycleTests(unittest.TestCase):
    def test_schema_v6_and_public_tools_are_explicit(self) -> None:
        self.assertEqual(CANONICAL_MODEL_SCHEMA_VERSION, 6)
        self.assertIn("list_layers", TOOL_CATALOG)
        self.assertIn("apply_layer_updates", TOOL_CATALOG)
        parameters = inspect.signature(ToolHandlers.apply_layer_updates).parameters
        self.assertEqual(
            set(parameters),
            {"self", "documentId", "expectedDocumentFingerprint", "updates", "reason"},
        )

    def test_nested_layer_collection_uses_registered_identity_semantics(self) -> None:
        self.assertTrue(is_identity_collection_path(("glyphs", "A", "layers")))
        before = _model()
        after = copy.deepcopy(before)
        after["glyphs"]["A"]["layers"][1]["name"] = "{130}"
        after["glyphs"]["A"]["layers"] = [
            after["glyphs"]["A"]["layers"][0],
            after["glyphs"]["A"]["layers"][2],
            after["glyphs"]["A"]["layers"][1],
            after["glyphs"]["A"]["layers"][3],
        ]

        changes = diff_models(before, after)

        self.assertEqual(changes.apply(before), after)
        self.assertEqual(changes.inverse().apply(after), before)
        self.assertEqual(
            {change.path for change in changes.changes},
            {
                ("glyphs", "A", "layers", "brace-125", "name"),
                ("glyphs", "A", "layers", "$order"),
            },
        )

    def test_nested_selective_revert_preserves_later_unrelated_layer_change(self) -> None:
        before = _model()
        first = copy.deepcopy(before)
        first["glyphs"]["A"]["layers"][1]["name"] = "{130}"
        original = diff_models(before, first)
        current = copy.deepcopy(first)
        current["glyphs"]["A"]["layers"][2]["width"] = 640

        inverse, conflicts = revert_change_set_onto(current, original)

        self.assertEqual(conflicts, ())
        self.assertIsNotNone(inverse)
        reverted = inverse.apply(current)
        self.assertEqual(reverted["glyphs"]["A"]["layers"][1]["name"], "{125}")
        self.assertEqual(reverted["glyphs"]["A"]["layers"][2]["width"], 640)

    def test_list_layers_filters_by_glyph_and_role_without_losing_order(self) -> None:
        items = list_layers(_model(), glyph_names=["A"], roles=["intermediate", "alternate"])

        self.assertEqual([item["id"] for item in items], ["brace-125", "bracket-400"])
        self.assertEqual([item["order"] for item in items], [1, 2])
        self.assertEqual(items[0]["interpolation"]["coordinates"], {"wght": 125})

    def test_list_layers_full_detail_joins_observations_without_canonicalizing_them(self) -> None:
        model = _model()
        layer = model["glyphs"]["A"]["layers"][0]
        layer["components"] = [
            {
                "name": "A.base",
                "transform": [1, 0, 0, 1, 12, 0],
                "automaticAlignment": True,
            }
        ]
        observations = {
            ("A", "m0"): {
                "bounds": {"x": 10, "y": 0, "width": 500, "height": 700},
                "currentMetrics": {
                    "width": 600,
                    "leftBearing": 45,
                    "rightBearing": 55,
                },
                "resolvedMetrics": {
                    "width": 620,
                    "leftBearing": 50,
                    "rightBearing": 50,
                },
                "delta": {
                    "width": 20,
                    "leftBearing": 5,
                    "rightBearing": -5,
                },
                "stale": True,
                "hasAlignedWidth": True,
            }
        }

        item = list_layers(
            model,
            glyph_names=["A"],
            roles=["master"],
            detail="full",
            observations=observations,
        )[0]

        self.assertEqual(item["currentMetrics"]["leftBearing"], 45)
        self.assertEqual(item["resolvedMetrics"]["width"], 620)
        self.assertTrue(item["stale"])
        self.assertTrue(item["hasAlignedWidth"])
        self.assertEqual(item["bounds"]["height"], 700)
        self.assertEqual(item["components"][0]["transform"], [1, 0, 0, 1, 12, 0])
        self.assertTrue(item["components"][0]["automaticAlignment"])

    def test_duplicate_update_move_delete_and_inverse_share_one_builder(self) -> None:
        before = _model()
        build = build_layer_updates(
            before,
            [
                {
                    "action": "duplicate",
                    "glyphName": "A",
                    "sourceLayerId": "brace-125",
                    "layerId": "brace-150",
                    "name": "{150}",
                    "interpolation": {
                        "kind": "intermediate",
                        "coordinates": {"wght": 150},
                    },
                    "index": 2,
                },
                {
                    "action": "update",
                    "glyphName": "A",
                    "layerId": "bracket-400",
                    "interpolation": None,
                    "name": "Alternate source",
                },
                {
                    "action": "move",
                    "glyphName": "A",
                    "layerId": "backup-1",
                    "index": 1,
                },
                {
                    "action": "delete",
                    "glyphName": "A",
                    "layerId": "brace-125",
                },
            ],
        )
        after = build.change_set.apply(before)

        self.assertEqual(build.capabilities, (LAYER_LIFECYCLE_CAPABILITY,))
        self.assertEqual(build.execution_context["layerSources"], {"A/brace-150": "brace-125"})
        self.assertEqual(
            [layer["id"] for layer in after["glyphs"]["A"]["layers"]],
            ["m0", "backup-1", "brace-150", "bracket-400"],
        )
        alternate = after["glyphs"]["A"]["layers"][3]
        self.assertIsNone(alternate["interpolation"])
        self.assertEqual(alternate["roles"], ["backup"])
        self.assertEqual(build.change_set.inverse().apply(after), before)

    def test_master_layers_are_exclusively_owned_by_master_updates(self) -> None:
        for action in ("update", "move", "delete"):
            with self.subTest(action=action), self.assertRaisesRegex(ValueError, "master layer"):
                update = {"action": action, "glyphName": "A", "layerId": "m0"}
                if action == "update":
                    update["name"] = "Wrong owner"
                if action == "move":
                    update["index"] = 1
                build_layer_updates(_model(), [update])

    def test_non_master_reordering_cannot_cross_the_master_layer_prefix(self) -> None:
        for update in (
            {
                "action": "move",
                "glyphName": "A",
                "layerId": "backup-1",
                "index": 0,
            },
            {
                "action": "duplicate",
                "glyphName": "A",
                "sourceLayerId": "brace-125",
                "layerId": "brace-150",
                "index": 0,
            },
        ):
            with self.subTest(action=update["action"]), self.assertRaisesRegex(
                ValueError, "master-layer prefix"
            ):
                build_layer_updates(_model(), [update])

    def test_interpolation_configuration_validates_known_axis_tags_and_ranges(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown axis tag"):
            build_layer_updates(
                _model(),
                [
                    {
                        "action": "update",
                        "glyphName": "A",
                        "layerId": "brace-125",
                        "interpolation": {
                            "kind": "intermediate",
                            "coordinates": {"opsz": 14},
                        },
                    }
                ],
            )
        with self.assertRaisesRegex(ValueError, "minimum.*maximum"):
            build_layer_updates(
                _model(),
                [
                    {
                        "action": "update",
                        "glyphName": "A",
                        "layerId": "bracket-400",
                        "interpolation": {
                            "kind": "alternate",
                            "ranges": {"wght": {"min": 700, "max": 400}},
                        },
                    }
                ],
            )

    def test_one_layer_edit_reuses_every_unrelated_snapshot_shard(self) -> None:
        before = CanonicalSnapshot.from_model(_model())
        changed = copy.deepcopy(before.materialize())
        changed["glyphs"]["A"]["layers"][1]["name"] = "{130}"
        change_set = diff_models(before, changed)

        after = before.store_verified_transition(changed, change_set)

        self.assertIs(before.glyph_shards["B"], after.glyph_shards["B"])
        before_layers = before.glyph_shards["A"]["layers"]
        after_layers = after.glyph_shards["A"]["layers"]
        self.assertIs(before_layers[0], after_layers[0])
        self.assertIsNot(before_layers[1], after_layers[1])
        self.assertIs(before_layers[2], after_layers[2])
        self.assertIs(before_layers[3], after_layers[3])

    def test_path_impact_names_only_the_changed_nested_layer(self) -> None:
        before = _model()
        after = copy.deepcopy(before)
        after["glyphs"]["A"]["layers"][1]["width"] = 620
        impact = CanonicalImpact.from_change_set(before, diff_models(before, after))

        self.assertEqual(impact.glyph_names, ("A",))
        self.assertEqual(impact.layer_ids("A"), ("brace-125",))
        self.assertFalse(impact.requires_complete_glyph("A"))

    def test_layer_membership_diff_has_a_bounded_change_log_representation(self) -> None:
        before = _model()
        after = copy.deepcopy(before)
        removed = after["glyphs"]["A"]["layers"].pop(1)

        change_set = diff_models(before, after)
        public = public_change_dict(
            next(change for change in change_set.changes if change.path[-1] == removed["id"])
        )

        self.assertEqual(public["before"]["kind"], "canonical_layer_entity")
        self.assertEqual(public["before"]["id"], "brace-125")
        self.assertLess(len(str(public)), 2048)

    def test_non_master_layer_uses_the_existing_live_overlay_projection(self) -> None:
        trees = CanonicalFontTree(MemoryObjectStore())
        history = ChangeHistory(trees, id_factory=lambda: "commit_layer")
        before = _model()
        after = copy.deepcopy(before)
        after["glyphs"]["A"]["layers"][1]["paths"][0]["nodes"][0]["x"] = 25
        history.record_action(
            document_id="doc_layers",
            tool="apply_layer_updates",
            effect="edit",
            status="success",
            run_id="run_layers",
            reason="Intermediate optical correction",
            before_model=before,
            after_model=after,
        )

        overlay = overlay_for_layer(
            trees=trees,
            session=history.latest_session_diff("doc_layers"),
            glyph_name="A",
            layer_key="brace-125",
            live_layer=after["glyphs"]["A"]["layers"][1],
        )

        self.assertTrue(overlay.visible)
        self.assertEqual(overlay.baseline_paths[0]["nodes"][0]["x"], 10)
        self.assertEqual(overlay.current_paths[0]["nodes"][0]["x"], 25)

    def test_native_capture_preserves_roles_attributes_and_axis_tag_interpolation(self) -> None:
        axis_id = "axis-weight"
        native = SimpleNamespace(
            layerId="brace-native",
            associatedMasterId="m0",
            name="{125}",
            isMasterLayer=False,
            isSpecialLayer=True,
            isBraceLayer=True,
            isBracketLayer=False,
            isSmartComponentLayer=False,
            isColorPaletteLayer=False,
            isBackupLayer=False,
            hasAlignedWidth=False,
            attributes={"coordinates": {axis_id: 125}, "color": 2},
            width=600,
            leftMetricsKey=None,
            rightMetricsKey=None,
            widthMetricsKey=None,
            anchors=[],
            paths=[],
            shapes=[],
            components=[],
        )

        model = native_layer_to_model(native, axis_tags={axis_id: "wght"})

        self.assertEqual(model["roles"], ["intermediate"])
        self.assertEqual(
            model["interpolation"],
            {"kind": "intermediate", "coordinates": {"wght": 125}},
        )
        self.assertEqual(model["attributes"], {"color": 2})

    def test_public_apply_and_revert_share_one_operation_pipeline(self) -> None:
        class Host:
            def __init__(self):
                self.model = _model()
                self.clone_calls = 0
                self.apply_calls = 0

            def capture_model(self, document_id):
                return copy.deepcopy(self.model)

            def simulate_change_set(self, document_id, change_set):
                self.clone_calls += 1
                return change_set.apply(self.model)

            def apply_change_set(self, document_id, change_set):
                self.apply_calls += 1
                self.model = change_set.apply(self.model)

            def restore_model(self, document_id, model):
                self.model = copy.deepcopy(model)

        host = Host()
        app = GlyphsMCPApplication(host)
        baseline = copy.deepcopy(host.model)
        listed = app.invoke(
            "list_layers",
            {
                "documentId": "doc_layers",
                "glyphNames": ["A"],
                "roles": ["intermediate", "alternate"],
                "pageSize": 1,
            },
        ).to_dict()
        self.assertTrue(listed["ok"])
        self.assertEqual(listed["page"]["totalItems"], 2)
        self.assertEqual(len(listed["data"]["layers"]), 1)

        applied = app.invoke(
            "apply_layer_updates",
            {
                "documentId": "doc_layers",
                "expectedDocumentFingerprint": fingerprint_model(host.model),
                "updates": [
                    {
                        "action": "duplicate",
                        "glyphName": "A",
                        "sourceLayerId": "brace-125",
                        "layerId": "brace-150",
                        "interpolation": {
                            "kind": "intermediate",
                            "coordinates": {"wght": 150},
                        },
                    }
                ],
            },
        ).to_dict()
        self.assertTrue(applied["ok"])
        self.assertEqual(applied["data"]["transactionCount"], 1)
        self.assertIsNotNone(applied["auditReceipt"])
        self.assertEqual(host.clone_calls, 1)
        self.assertEqual(host.apply_calls, 1)

        reverted = app.invoke(
            "revert_change",
            {
                "documentId": "doc_layers",
                "operationId": applied["operationId"],
                "expectedDocumentFingerprint": fingerprint_model(host.model),
            },
        ).to_dict()
        self.assertTrue(reverted["ok"])
        self.assertEqual(host.model, baseline)
        self.assertEqual(host.clone_calls, 2)
        self.assertEqual(host.apply_calls, 2)
        self.assertIsNotNone(reverted["auditReceipt"])


if __name__ == "__main__":
    unittest.main()
