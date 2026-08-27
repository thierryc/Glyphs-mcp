"""Pure production review workflows and scale-sensitive result behavior."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.workflows import (  # noqa: E402
    build_glyph_updates,
    build_master_updates,
    list_instances,
    list_kerning_pairs,
    review_anchor_consistency,
    review_export,
    review_compatibility_updates,
    review_kerning_coverage,
    review_kerning_updates,
    review_master_compatibility,
    review_metrics_inheritance,
    review_metrics_updates,
    build_opentype_updates,
    simulate_spacing,
)
from glyphs_mcp_v2.canonical_views import layer_components  # noqa: E402


def _review_layer(
    layer_id: str,
    master_id: str,
    *,
    is_master: bool | None = None,
    roles: tuple[str, ...] | None = None,
    is_special: bool = False,
    path_node_counts: tuple[int, ...] = (4,),
    components: tuple[str, ...] = (),
    anchors: tuple[str, ...] = (),
    **values: object,
) -> dict[str, object]:
    layer: dict[str, object] = {
        "id": layer_id,
        "masterId": master_id,
        "isSpecialLayer": is_special,
        "paths": [
            {"nodes": [{"type": "line"} for _ in range(count)]}
            for count in path_node_counts
        ],
        "components": [{"name": name} for name in components],
        "anchors": {name: [0, 0] for name in anchors},
        **values,
    }
    if is_master is not None:
        layer["isMasterLayer"] = is_master
    if roles is not None:
        layer["roles"] = list(roles)
    return layer


def _review_model(
    layers: object,
    *,
    component_glyphs: tuple[str, ...] = (),
) -> dict[str, object]:
    glyphs: dict[str, object] = {
        "A": {
            "export": True,
            "mastersCompatible": True,
            "layers": layers,
        }
    }
    for name in component_glyphs:
        glyphs[name] = {"export": False, "layers": []}
    return {
        "masters": [{"id": "m1"}, {"id": "m2"}],
        "glyphs": glyphs,
    }


class V2WorkflowTests(unittest.TestCase):
    def test_glyph_builder_does_not_deepcopy_unrelated_canonical_shards(self) -> None:
        class UnrelatedGlyph(dict):
            def __deepcopy__(self, _memo):
                raise AssertionError("unrelated glyph shard was deep-copied")

        model = {
            "font": {"familyName": "Copy-on-write"},
            "glyphs": {
                "A": {
                    "id": "glyph:A",
                    "name": "A",
                    "export": True,
                    "layers": [],
                },
                "B": UnrelatedGlyph(
                    {
                        "id": "glyph:B",
                        "name": "B",
                        "export": True,
                        "layers": [],
                    }
                ),
            },
        }

        changes = build_glyph_updates(
            model,
            [{"action": "update", "glyphName": "A", "export": False}],
        )

        self.assertEqual([change.path for change in changes.changes], [("glyphs", "A", "export")])
        self.assertFalse(changes.apply(model)["glyphs"]["A"]["export"])

    def test_opentype_updates_share_one_existing_collection_contract(self) -> None:
        model = {
            "features": [
                {
                    "id": "liga",
                    "name": "liga",
                    "code": "sub f i by fi;",
                    "automatic": False,
                    "disabled": False,
                }
            ],
            "classes": [
                {
                    "id": "Uppercase",
                    "name": "Uppercase",
                    "code": "A B",
                    "automatic": False,
                    "disabled": False,
                }
            ],
            "featurePrefixes": [
                {
                    "id": "Languagesystems",
                    "name": "Languagesystems",
                    "code": "languagesystem DFLT dflt;",
                    "automatic": False,
                    "disabled": False,
                }
            ],
        }

        changes = build_opentype_updates(
            model,
            [
                {"kind": "feature", "name": "liga", "code": "sub f f i by ffi;"},
                {"kind": "class", "name": "Uppercase", "disabled": True},
                {"kind": "prefix", "name": "Languagesystems", "automatic": True},
            ],
        )
        after = changes.apply(model)

        self.assertEqual(after["features"][0]["code"], "sub f f i by ffi;")
        self.assertTrue(after["classes"][0]["disabled"])
        self.assertTrue(after["featurePrefixes"][0]["automatic"])
        self.assertEqual(len(changes.changes), 3)

        with self.assertRaisesRegex(ValueError, "automatic false"):
            build_opentype_updates(
                model,
                [{"kind": "feature", "name": "liga", "automatic": True, "code": "sub a by b;"}],
            )

    def test_compatibility_explains_host_and_component_mismatches(self) -> None:
        model = {
            "masters": [{"id": "m1"}, {"id": "m2"}],
            "glyphs": {
                "A": {
                    "export": True,
                    "mastersCompatible": False,
                    "layers": {
                        "m1": {"components": ["A.base"], "pathSignature": [4]},
                        "m2": {"components": ["A.alt"], "pathSignature": [4]},
                    },
                }
            },
        }

        result = review_master_compatibility(model, mode="component_preserving")
        codes = {finding["code"] for finding in result["findings"]}
        self.assertIn("host_incompatible", codes)
        self.assertIn("component_sequence_mismatch", codes)
        self.assertTrue(result["hasHardFailures"])

    def test_backup_appended_after_master_does_not_replace_master_layer(self) -> None:
        model = _review_model(
            [
                _review_layer(
                    "m1",
                    "m1",
                    is_master=True,
                    roles=("master",),
                    components=("Base",),
                ),
                _review_layer(
                    "m2",
                    "m2",
                    is_master=True,
                    roles=("master",),
                    components=("Base",),
                ),
                _review_layer(
                    "backup",
                    "m2",
                    is_master=False,
                    roles=("backup",),
                    path_node_counts=(7,),
                ),
            ],
            component_glyphs=("Base",),
        )

        result = review_master_compatibility(model)
        codes = {finding["code"] for finding in result["findings"]}

        self.assertNotIn("missing_master_layer", codes)
        self.assertNotIn("component_sequence_mismatch", codes)
        self.assertNotIn("path_topology_mismatch", codes)

    def test_multiple_backups_for_one_master_do_not_affect_compatibility(self) -> None:
        model = _review_model(
            [
                _review_layer("m1", "m1", is_master=True, roles=("master",)),
                _review_layer("m2", "m2", is_master=True, roles=("master",)),
                _review_layer(
                    "backup-1",
                    "m2",
                    is_master=False,
                    roles=("backup",),
                    path_node_counts=(7,),
                    components=("Ghost",),
                ),
                _review_layer(
                    "backup-2",
                    "m2",
                    is_master=False,
                    roles=("backup",),
                    path_node_counts=(9,),
                ),
            ],
            component_glyphs=("Ghost",),
        )

        result = review_master_compatibility(model)
        codes = {finding["code"] for finding in result["findings"]}

        self.assertFalse(result["hasHardFailures"])
        self.assertFalse(
            codes.intersection(
                {"component_sequence_mismatch", "path_topology_mismatch"}
            )
        )

    def test_explicit_false_master_flag_overrides_a_master_role(self) -> None:
        model = _review_model(
            [
                _review_layer("m1", "m1", is_master=True, roles=("master",)),
                _review_layer("m2", "m2", is_master=True, roles=("master",)),
                _review_layer(
                    "not-a-master",
                    "m2",
                    is_master=False,
                    roles=("master",),
                    path_node_counts=(7,),
                ),
            ]
        )

        result = review_master_compatibility(model)
        codes = {finding["code"] for finding in result["findings"]}

        self.assertNotIn("path_topology_mismatch", codes)

    def test_backup_role_is_excluded_when_master_flag_is_absent(self) -> None:
        model = _review_model(
            [
                _review_layer("m1", "m1", is_master=True, roles=("master",)),
                _review_layer("m2", "m2", is_master=True, roles=("master",)),
                _review_layer(
                    "backup",
                    "m2",
                    roles=("backup",),
                    path_node_counts=(7,),
                ),
            ]
        )

        result = review_master_compatibility(model)
        codes = {finding["code"] for finding in result["findings"]}

        self.assertNotIn("path_topology_mismatch", codes)

    def test_genuine_master_path_topology_mismatch_is_reported(self) -> None:
        model = _review_model(
            [
                _review_layer("m1", "m1", is_master=True, roles=("master",)),
                _review_layer(
                    "m2",
                    "m2",
                    is_master=True,
                    roles=("master",),
                    path_node_counts=(7,),
                ),
            ]
        )

        result = review_master_compatibility(model)

        self.assertIn(
            "path_topology_mismatch",
            {finding["code"] for finding in result["findings"]},
        )

    def test_genuine_master_component_order_mismatch_is_reported(self) -> None:
        model = _review_model(
            [
                _review_layer(
                    "m1",
                    "m1",
                    is_master=True,
                    roles=("master",),
                    components=("Base", "Accent"),
                ),
                _review_layer(
                    "m2",
                    "m2",
                    is_master=True,
                    roles=("master",),
                    components=("Accent", "Base"),
                ),
            ],
            component_glyphs=("Base", "Accent"),
        )

        result = review_master_compatibility(model)

        self.assertIn(
            "component_sequence_mismatch",
            {finding["code"] for finding in result["findings"]},
        )

    def test_missing_master_layer_is_still_reported(self) -> None:
        model = _review_model(
            [_review_layer("m1", "m1", is_master=True, roles=("master",))]
        )

        result = review_master_compatibility(model)
        missing = [
            finding
            for finding in result["findings"]
            if finding["code"] == "missing_master_layer"
        ]

        self.assertEqual(missing[0]["target"]["masterIds"], ["m2"])

    def test_backup_layers_do_not_change_anchor_consistency(self) -> None:
        masters = [
            _review_layer(
                "m1", "m1", is_master=True, roles=("master",), anchors=("top",)
            ),
            _review_layer(
                "m2", "m2", is_master=True, roles=("master",), anchors=("top",)
            ),
        ]
        backup = _review_layer(
            "backup",
            "m2",
            is_master=False,
            roles=("backup",),
            anchors=("bottom",),
        )

        expected = review_anchor_consistency(_review_model(masters))
        actual = review_anchor_consistency(_review_model([*masters, backup]))

        self.assertEqual(actual, expected)

    def test_backup_layers_do_not_change_metrics_inheritance(self) -> None:
        masters = [
            _review_layer("m1", "m1", is_master=True, roles=("master",)),
            _review_layer("m2", "m2", is_master=True, roles=("master",)),
        ]
        backup = _review_layer(
            "backup",
            "m2",
            is_master=False,
            roles=("backup",),
            leftMetricsKey="=Missing",
        )

        expected = review_metrics_inheritance(_review_model(masters))
        actual = review_metrics_inheritance(_review_model([*masters, backup]))

        self.assertEqual(actual, expected)

    def test_backup_components_do_not_enter_export_dependencies(self) -> None:
        model = _review_model(
            [
                _review_layer(
                    "m1",
                    "m1",
                    is_master=True,
                    roles=("master",),
                    components=("Base",),
                ),
                _review_layer(
                    "m2",
                    "m2",
                    is_master=True,
                    roles=("master",),
                    components=("Base",),
                ),
                _review_layer(
                    "backup",
                    "m2",
                    is_master=False,
                    roles=("backup",),
                    components=("Ghost",),
                ),
            ],
            component_glyphs=("Base", "Ghost"),
        )

        result = review_master_compatibility(model)
        dependency = next(
            item
            for item in result["componentDependencies"]
            if item["glyphName"] == "A"
        )

        self.assertEqual(dependency["direct"], ["Base"])

    def test_special_layer_is_reviewed_without_replacing_its_master(self) -> None:
        model = _review_model(
            [
                _review_layer("m1", "m1", is_master=True, roles=("master",)),
                _review_layer("m2", "m2", is_master=True, roles=("master",)),
                _review_layer(
                    "brace-500",
                    "m2",
                    is_master=False,
                    roles=("intermediate",),
                    is_special=True,
                    path_node_counts=(7,),
                ),
            ]
        )

        result = review_master_compatibility(model)
        master_mismatches = [
            finding
            for finding in result["findings"]
            if finding["code"] == "path_topology_mismatch"
        ]
        special_mismatches = [
            finding
            for finding in result["findings"]
            if finding["code"] == "special_layer_path_topology_mismatch"
        ]

        self.assertEqual(result["specialLayerCount"], 1)
        self.assertEqual(master_mismatches, [])
        self.assertEqual(special_mismatches[0]["target"]["layerId"], "brace-500")

    def test_mapping_shaped_legacy_layers_without_flags_remain_supported(self) -> None:
        model = _review_model(
            {
                "m1": {"paths": [{"nodes": [{}, {}, {}, {}]}]},
                "m2": {"paths": [{"nodes": [{}, {}, {}, {}]}]},
            }
        )

        result = review_master_compatibility(model)
        codes = {finding["code"] for finding in result["findings"]}

        self.assertFalse(result["hasHardFailures"])
        self.assertNotIn("missing_master_layer", codes)

    def test_master_role_selects_a_layer_when_boolean_flag_is_absent(self) -> None:
        model = _review_model(
            [
                _review_layer("m1", "m1", roles=("master",)),
                _review_layer("m2", "m2", roles=("master",)),
            ]
        )

        result = review_master_compatibility(model)

        self.assertFalse(result["hasHardFailures"])

    def test_duplicate_explicit_master_layers_are_reported(self) -> None:
        model = _review_model(
            [
                _review_layer("m1", "m1", is_master=True, roles=("master",)),
                _review_layer("m2", "m2", is_master=True, roles=("master",)),
                _review_layer(
                    "m2-duplicate",
                    "m2",
                    is_master=True,
                    roles=("master",),
                ),
            ]
        )

        result = review_master_compatibility(model)
        duplicates = [
            finding
            for finding in result["findings"]
            if finding["code"] == "duplicate_master_layer"
        ]

        self.assertEqual(duplicates[0]["target"]["masterId"], "m2")
        self.assertEqual(
            duplicates[0]["target"]["layerIds"], ["m2", "m2-duplicate"]
        )

    def test_export_does_not_require_acknowledging_backup_findings(self) -> None:
        model = _review_model(
            [
                _review_layer("m1", "m1", is_master=True, roles=("master",)),
                _review_layer("m2", "m2", is_master=True, roles=("master",)),
                _review_layer(
                    "backup",
                    "m2",
                    is_master=False,
                    roles=("backup",),
                    path_node_counts=(7,),
                    components=("Missing",),
                ),
            ]
        )
        compatibility = review_master_compatibility(model)

        result = review_export(
            destination_state={"exists": False, "empty": True},
            compatibility=compatibility,
        )

        self.assertFalse(compatibility["hasHardFailures"])
        self.assertTrue(result["ready"])
        self.assertNotIn("hard_compatibility_failure", result["blockingCodes"])

    def test_anchor_review_preserves_outliers_as_soft_findings(self) -> None:
        model = {
            "masters": [{"id": "m1"}, {"id": "m2"}],
            "glyphs": {
                "acutecomb": {
                    "layers": {
                        "m1": {"anchors": {"_top": [0, 500], "top": [0, 700]}},
                        "m2": {"anchors": {"_top": [0, 510]}},
                    }
                }
            },
        }
        result = review_anchor_consistency(model)
        self.assertEqual(result["findings"][0]["severity"], "soft")
        self.assertEqual(result["findings"][0]["code"], "anchor_set_difference")

    def test_zero_width_mark_is_a_valid_spacing_skip(self) -> None:
        result = simulate_spacing(
            [{"glyphName": "strokeshortcomb", "width": 0, "category": "Mark"}],
            max_iterations=5,
            tolerance=1,
        )
        item = result["items"][0]
        self.assertEqual(item["status"], "skipped")
        self.assertEqual(item["reason"], "zero_width_mark")
        self.assertNotIn("blocked", repr(item))

    def test_automatically_aligned_width_is_a_host_owned_spacing_skip(self) -> None:
        result = simulate_spacing(
            [
                {
                    "glyphName": "j",
                    "masterId": "m1",
                    "width": 265,
                    "targetWidth": 267,
                    "hostOwnsWidth": True,
                }
            ],
            max_iterations=5,
            tolerance=1,
        )

        item = result["items"][0]
        self.assertEqual(item["status"], "skipped")
        self.assertEqual(item["reason"], "automatic_alignment")
        self.assertEqual(result["actionableCount"], 0)

    def test_spacing_revalidates_dependencies_in_a_bounded_fixed_point(self) -> None:
        result = simulate_spacing(
            [
                {"glyphName": "A", "masterId": "m1", "width": 500, "targetWidth": 600},
                {
                    "glyphName": "Aacute",
                    "masterId": "m1",
                    "width": 500,
                    "referenceGlyphName": "A",
                    "offset": 10,
                },
            ],
            max_iterations=5,
            tolerance=1,
        )
        by_name = {item["glyphName"]: item for item in result["items"]}
        self.assertTrue(result["converged"])
        self.assertLessEqual(result["completedIterations"], 5)
        self.assertEqual(by_name["Aacute"]["proposedWidth"], 610)
        self.assertEqual(result["dependencyCount"], 1)

    def test_kerning_keys_and_instance_axes_are_typed(self) -> None:
        model = {
            "kerning": [
                {
                    "masterId": "m1",
                    "left": {"kind": "group", "id": "@MMK_L_A", "name": "A"},
                    "right": {"kind": "glyph", "id": "-841259840", "name": None},
                    "value": -20,
                }
            ],
            "instances": [
                {
                    "id": "i1",
                    "name": "Variable",
                    "type": "variable",
                    "axes": [{"tag": "wght", "internal": 400, "external": 90}],
                    "included": True,
                    "interpolationSupported": False,
                }
            ],
        }
        pairs = list_kerning_pairs(model)
        self.assertEqual(pairs[0]["right"]["id"], "-841259840")
        self.assertIsNone(pairs[0]["right"]["name"])
        instances = list_instances(model)
        self.assertEqual(instances[0]["axes"][0]["external"], 90)
        self.assertFalse(instances[0]["interpolationSupported"])
        coverage = review_kerning_coverage(model, mode="glyph_expansion")
        self.assertEqual(coverage["eligibleCount"], 1)
        self.assertEqual(coverage["measuredCount"], 0)
        self.assertEqual(coverage["untestedCount"], 1)
        self.assertTrue(coverage["accountingComplete"])
        self.assertFalse(coverage["complete"])

    def test_directional_pairs_and_contexts_are_listed_without_crossing_domains(self) -> None:
        model = {
            "glyphs": {
                name: {"id": "g{}".format(name), "name": name}
                for name in ("L", "quoteright", "A", "V")
            },
            "kerning": {
                "ltr": {"m1": {"gA": {"gV": -80}}},
                "rtl": {"m1": {"gV": {"gA": -40}}},
                "vertical": {"m1": {"gA": {"gV": -20}}},
                "context": {
                    "L * quoteright A": {"m1": -40},
                    "L quoteright * A": {"m1": 80},
                    "[L Lacute] * quoteright A": {"m1": -15},
                },
            },
        }

        pairs = list_kerning_pairs(model)
        contexts = list_kerning_pairs(model, entry_kind="context")
        combined = list_kerning_pairs(model, entry_kind="all")

        self.assertEqual(
            [pair["direction"] for pair in pairs],
            ["ltr", "rtl", "vertical"],
        )
        self.assertTrue(all(pair["entryKind"] == "pair" for pair in pairs))
        self.assertEqual(len(contexts), 3)
        first_boundary = next(
            item
            for item in contexts
            if item["rawContextKey"] == "L * quoteright A"
        )
        second_boundary = next(
            item
            for item in contexts
            if item["rawContextKey"] == "L quoteright * A"
        )
        raw_only = next(item for item in contexts if not item["editable"])
        self.assertEqual(first_boundary["sequence"], ["L", "quoteright", "A"])
        self.assertEqual(first_boundary["boundaryIndex"], 1)
        self.assertEqual(second_boundary["boundaryIndex"], 2)
        self.assertIsNone(raw_only["sequence"])
        self.assertEqual(len(combined), len(pairs) + len(contexts))

        coverage = review_kerning_coverage(model, mode="context_sequences")
        self.assertEqual(coverage["entryKind"], "context")
        self.assertEqual(coverage["contextEntryCount"], 3)
        self.assertEqual(coverage["editableCount"], 2)
        self.assertEqual(coverage["rawOnlyCount"], 1)
        self.assertEqual(coverage["byMaster"][0]["entryCount"], 3)

    def test_mixed_pair_and_context_updates_are_atomic_and_preserve_other_domains(self) -> None:
        model = {
            "masters": [{"id": "m1"}, {"id": "m2"}],
            "glyphs": {
                name: {"id": "g{}".format(name), "name": name}
                for name in ("L", "quoteright", "A", "V")
            },
            "kerning": {
                "ltr": {"m1": {"gA": {"gV": -80}}},
                "rtl": {"m1": {"gV": {"gA": -40}}},
                "vertical": {"m1": {"gA": {"gV": -20}}},
                "context": {"manual [class] key": {"m2": -15}},
            },
        }
        updates = [
            {
                "entryKind": "pair",
                "direction": "ltr",
                "masterId": "m1",
                "left": "A",
                "right": "V",
                "value": -90,
            },
            {
                "entryKind": "context",
                "masterId": "m1",
                "sequence": ["L", "quoteright", "A"],
                "boundaryIndex": 1,
                "value": -40,
            },
            {
                "entryKind": "context",
                "masterId": "m1",
                "sequence": ["L", "quoteright", "A"],
                "boundaryIndex": 2,
                "value": 80,
            },
        ]

        after = review_kerning_updates(model, updates).apply(model)

        self.assertEqual(after["kerning"]["ltr"]["m1"]["gA"]["gV"], -90)
        self.assertEqual(after["kerning"]["rtl"], model["kerning"]["rtl"])
        self.assertEqual(after["kerning"]["vertical"], model["kerning"]["vertical"])
        self.assertEqual(
            after["kerning"]["context"]["L * quoteright A"]["m1"], -40
        )
        self.assertEqual(
            after["kerning"]["context"]["L quoteright * A"]["m1"], 80
        )
        self.assertEqual(
            after["kerning"]["context"]["manual [class] key"]["m2"], -15
        )

        removed = review_kerning_updates(
            after,
            [
                {
                    "entryKind": "context",
                    "masterId": "m1",
                    "sequence": ["L", "quoteright", "A"],
                    "boundaryIndex": 1,
                    "value": None,
                },
                {
                    "entryKind": "context",
                    "masterId": "m1",
                    "sequence": ["L", "quoteright", "A"],
                    "boundaryIndex": 2,
                    "value": 0,
                },
            ],
        ).apply(after)
        self.assertNotIn("L * quoteright A", removed["kerning"]["context"])
        self.assertEqual(
            removed["kerning"]["context"]["L quoteright * A"]["m1"], 0
        )

    def test_context_updates_reject_ambiguous_or_invalid_targets(self) -> None:
        model = {
            "masters": [{"id": "m1"}],
            "glyphs": {
                name: {"id": "g{}".format(name), "name": name}
                for name in ("L", "quoteright", "A")
            },
            "kerning": {"ltr": {}, "rtl": {}, "vertical": {}, "context": {}},
        }
        base = {
            "entryKind": "context",
            "masterId": "m1",
            "sequence": ["L", "quoteright", "A"],
            "boundaryIndex": 1,
            "value": -40,
        }
        invalid = (
            {**base, "sequence": ["L", "A"]},
            {**base, "sequence": ["L", "missing", "A"]},
            {**base, "sequence": ["L", "[quoteright]", "A"]},
            {**base, "boundaryIndex": 0},
            {**base, "boundaryIndex": "1"},
            {**base, "masterId": "missing"},
            {**base, "value": float("inf")},
        )
        for update in invalid:
            with self.subTest(update=update), self.assertRaises(ValueError):
                review_kerning_updates(model, [update])
        with self.assertRaisesRegex(ValueError, "unique explicit targets"):
            review_kerning_updates(model, [base, dict(base)])

    def test_master_lifecycle_updates_context_values_inside_each_context_key(self) -> None:
        def layer(master_id: str) -> dict[str, object]:
            return {
                "id": master_id,
                "masterId": master_id,
                "name": master_id,
                "isMasterLayer": True,
                "isSpecialLayer": False,
            }

        model = {
            "masters": [
                {"id": "m1", "name": "Regular", "axes": []},
                {"id": "m2", "name": "Bold", "axes": []},
            ],
            "glyphs": {
                "A": {
                    "id": "gA",
                    "name": "A",
                    "layers": [layer("m1"), layer("m2")],
                }
            },
            "kerning": {
                "ltr": {"m1": {"gA": {"gA": -10}}},
                "rtl": {},
                "vertical": {},
                "context": {"A * A A": {"m1": -25}},
            },
        }

        duplicate = build_master_updates(
            model,
            [
                {
                    "action": "duplicate",
                    "masterId": "m3",
                    "sourceMasterId": "m1",
                    "name": "Medium",
                }
            ],
        )
        duplicated = duplicate.change_set.apply(model)
        self.assertEqual(
            duplicated["kerning"]["context"]["A * A A"],
            {"m1": -25, "m3": -25},
        )

        deletion = build_master_updates(
            model, [{"action": "delete", "masterId": "m1"}]
        )
        deleted = deletion.change_set.apply(model)
        self.assertNotIn("A * A A", deleted["kerning"]["context"])

    def test_export_blocks_hard_findings_and_nonempty_destinations(self) -> None:
        compatibility = {"hasHardFailures": True, "findings": [{"id": "f1"}]}
        blocked = review_export(
            destination_state={"exists": True, "empty": False, "fingerprint": "dest_a"},
            compatibility=compatibility,
            overwrite_policy="fail_if_nonempty",
        )
        self.assertFalse(blocked["ready"])
        self.assertIn("destination_not_empty", blocked["blockingCodes"])
        self.assertIn("hard_compatibility_failure", blocked["blockingCodes"])

    def test_metrics_and_compatibility_batches_are_explicit_semantic_patches(self) -> None:
        model = {
            "glyphs": {
                "A": {
                    "layers": [
                        {
                            "id": "m1",
                            "masterId": "m1",
                            "isMasterLayer": True,
                            "leftMetricsKey": None,
                            "rightMetricsKey": None,
                            "widthMetricsKey": None,
                            "paths": [],
                            "components": [],
                            "pathSignature": [],
                        }
                    ]
                }
            }
        }
        metrics = review_metrics_updates(
            model,
            [
                {
                    "scope": "layer",
                    "glyphName": "A",
                    "layerId": "m1",
                    "leftMetricsKey": "=H",
                }
            ],
        )
        self.assertEqual(metrics.apply(model)["glyphs"]["A"]["layers"][0]["leftMetricsKey"], "=H")

        glyph_metrics = review_metrics_updates(
            model,
            [
                {
                    "scope": "glyph",
                    "glyphName": "A",
                    "rightMetricsKey": "=O",
                }
            ],
        ).apply(model)
        self.assertEqual(glyph_metrics["glyphs"]["A"]["rightMetricsKey"], "=O")
        self.assertIsNone(
            glyph_metrics["glyphs"]["A"]["layers"][0]["rightMetricsKey"]
        )

        with self.assertRaisesRegex(ValueError, "masterId is not part"):
            review_metrics_updates(
                model,
                [
                    {
                        "scope": "layer",
                        "glyphName": "A",
                        "layerId": "m1",
                        "masterId": "m1",
                        "leftMetricsKey": "=H",
                    }
                ],
            )

        compatibility = review_compatibility_updates(
            model,
            [
                {
                    "glyphName": "A",
                    "masterId": "m1",
                    "components": [{"name": "A.base", "transform": [1, 0, 0, 1, 0, 0]}],
                }
            ],
        )
        self.assertEqual(
            layer_components(
                compatibility.apply(model)["glyphs"]["A"]["layers"][0]
            )[0]["name"],
            "A.base",
        )

    def test_metrics_review_reports_resolved_deltas_and_stale_layers(self) -> None:
        model = {
            "masters": [{"id": "m1", "name": "Regular"}],
            "glyphs": {
                "L": {
                    "name": "L",
                    "leftMetricsKey": "=H",
                    "rightMetricsKey": None,
                    "widthMetricsKey": None,
                    "layers": [
                        {
                            "id": "m1",
                            "masterId": "m1",
                            "isMasterLayer": True,
                            "roles": ["master"],
                            "width": 500,
                            "leftMetricsKey": None,
                            "rightMetricsKey": None,
                            "widthMetricsKey": None,
                        }
                    ],
                },
                "H": {"name": "H", "layers": []},
            },
        }
        observations = {
            ("L", "m1"): {
                "currentMetrics": {
                    "width": 500,
                    "leftBearing": 40,
                    "rightBearing": 60,
                },
                "resolvedMetrics": {
                    "width": 520,
                    "leftBearing": 55,
                    "rightBearing": 65,
                },
            }
        }

        result = review_metrics_inheritance(
            model,
            glyph_names=["L"],
            tolerance=0.5,
            observations=observations,
        )

        self.assertEqual(result["staleLayerCount"], 1)
        row = result["metrics"][0]
        self.assertTrue(row["stale"])
        self.assertEqual(row["effectiveMetricsKeys"]["leftMetricsKey"]["source"], "glyph")
        self.assertEqual(row["delta"]["width"], 20.0)
        self.assertEqual(row["delta"]["leftBearing"], 15.0)


if __name__ == "__main__":
    unittest.main()
