"""Regression tests for guarded start-node review and mutation."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


RESOURCES = (
    Path(__file__).resolve().parent.parent
    / "Glyphs MCP.glyphsPlugin"
    / "Contents"
    / "Resources"
)


class Point:
    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)

    def __getitem__(self, index):
        return (self.x, self.y)[index]


class Node:
    _next_identity = 1

    def __init__(self, x, y, *, selected=False):
        self.identityToken = "node-{}".format(Node._next_identity)
        Node._next_identity += 1
        self.position = Point(x, y)
        self.type = "line"
        self.smooth = False
        self.rawType = 1
        self.rawConnection = 0
        self.orientation = 0
        self.name = None
        self.selected = bool(selected)
        self.attributes = {}
        self.userData = {}
        self.parent = None
        self.fail_make_first = False
        self.mutate_name_on_make_first = False

    def makeNodeFirst(self):
        if self.fail_make_first:
            raise RuntimeError("injected makeNodeFirst failure")
        nodes = self.parent.nodes
        index = nodes.index(self)
        nodes[:] = nodes[index:] + nodes[:index]
        if self.mutate_name_on_make_first:
            self.name = "unexpected-native-metadata-change"


class PathFixture:
    _next_identity = 1

    def __init__(self, points, *, rotation=0, closed=True):
        self.identityToken = "path-{}".format(PathFixture._next_identity)
        PathFixture._next_identity += 1
        nodes = [Node(x, y) for x, y in points]
        if rotation:
            nodes = nodes[rotation:] + nodes[:rotation]
        self.nodes = nodes
        for node in self.nodes:
            node.parent = self
        self.closed = bool(closed)
        self.locked = False
        self.direction = 1
        self.attributes = {"role": "body"}
        self.userData = {"protected": True}


class Layer:
    def __init__(self, master_id, path):
        self.layerId = master_id
        self.associatedMasterId = master_id
        self.name = master_id
        self.paths = [path]
        self.shapes = [path]
        self.width = 500
        self.components = []
        self.anchors = []
        self.hints = []
        self.guides = []
        self.annotations = []
        self.userData = {"layer": master_id}
        self.begin_count = 0
        self.end_count = 0

    def beginChanges(self):
        self.begin_count += 1

    def endChanges(self):
        self.end_count += 1


class Font:
    def __init__(self, layers):
        self.identityToken = "font-1"
        self.filepath = "/private/tmp/Alignment.glyphs"
        self.familyName = "Alignment"
        self.glyphs = {"A": types.SimpleNamespace(layers=layers)}


def _set_path_nodes(path, nodes):
    path.nodes = list(nodes)
    for node in path.nodes:
        node.parent = path
    return True


class StartNodeAlignmentToolsTests(unittest.TestCase):
    SQUARE = [(0, 0), (100, 0), (100, 100), (0, 100)]

    def _load_module(self, rotations=(0, 2), closed=True):
        paths = [PathFixture(self.SQUARE, rotation=rotation, closed=closed) for rotation in rotations]
        layers = {"M{}".format(index + 1): Layer("M{}".format(index + 1), path) for index, path in enumerate(paths)}
        font = Font(layers)
        glyphs = types.SimpleNamespace(fonts=[font])
        paths[0].nodes[0].selected = True

        def decorator():
            return lambda function: function

        helpers = types.SimpleNamespace(
            _font_resolution_error=lambda index, fonts, ok_key=None: {"ok": False, "error": "font not found"},
            _get_layer_id=lambda layer: layer.layerId,
            _glyphs_show_layer_link_fields=lambda *args, **kwargs: {},
            _layer_display_name=lambda font_value, layer, master_id=None: layer.name,
            _layer_paths=lambda layer: list(layer.paths),
            _node_orientation=lambda node: ("left", int(node.orientation)),
            _node_raw_connection=lambda node: int(node.rawConnection),
            _node_raw_type=lambda node: int(node.rawType),
            _normalized_node_type=lambda node: str(node.type),
            _resolve_font_by_index=lambda glyphs_value, index: (font, [font]) if int(index) == 0 else (None, [font]),
            _run_on_main_thread=lambda callback: callback(),
            _safe_json=lambda payload: json.dumps(payload, sort_keys=True),
            _set_path_nodes=_set_path_nodes,
        )
        module_name = "mcp_tools_start_node_alignment_test_{}".format(id(font))
        spec = importlib.util.spec_from_file_location(module_name, RESOURCES / "mcp_tools_start_node_alignment.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(RESOURCES))
        with mock.patch.dict(
            sys.modules,
            {
                "GlyphsApp": types.SimpleNamespace(Glyphs=glyphs),
                "tool_registration": types.SimpleNamespace(glyphs_tool=decorator),
                "mcp_tool_helpers": helpers,
            },
        ):
            spec.loader.exec_module(module)
        return module, font, layers, paths

    @staticmethod
    def _review(module, master_ids):
        return json.loads(
            asyncio.run(
                module.review_start_node_alignment(
                    font_index=0,
                    glyph_name="A",
                    reference_master_id="M1",
                    path_index=0,
                    reference_node_index=0,
                    target_master_ids=master_ids,
                )
            )
        )

    def test_review_dry_run_and_confirmed_apply_are_fingerprint_bound(self) -> None:
        module, _font, layers, paths = self._load_module()
        original_orders = [[node.identityToken for node in path.nodes] for path in paths]
        review = self._review(module, ["M1", "M2"])

        self.assertTrue(review["ok"])
        self.assertEqual(review["summary"]["rotationCount"], 1)
        self.assertEqual([[node.identityToken for node in path.nodes] for path in paths], original_orders)

        dry_run = json.loads(
            asyncio.run(
                module.apply_start_node_alignment(
                    font_index=0,
                    glyph_name="A",
                    reference_master_id="M1",
                    path_index=0,
                    reference_node_index=0,
                    target_master_ids=["M1", "M2"],
                    expected_plan_fingerprint=review["planFingerprint"],
                    dry_run=True,
                )
            )
        )
        self.assertTrue(dry_run["ok"])
        self.assertTrue(dry_run["dryRun"])
        self.assertEqual([[node.identityToken for node in path.nodes] for path in paths], original_orders)

        applied = json.loads(
            asyncio.run(
                module.apply_start_node_alignment(
                    font_index=0,
                    glyph_name="A",
                    reference_master_id="M1",
                    path_index=0,
                    reference_node_index=0,
                    target_master_ids=["M1", "M2"],
                    expected_plan_fingerprint=review["planFingerprint"],
                    confirm=True,
                )
            )
        )
        self.assertTrue(applied["ok"])
        self.assertEqual(applied["summary"]["appliedCount"], 1)
        self.assertEqual((paths[1].nodes[0].position.x, paths[1].nodes[0].position.y), (0.0, 0.0))
        self.assertTrue(applied["verification"]["nodeFieldsPreserved"])
        self.assertFalse(applied["fontSaved"])
        self.assertEqual(layers["M1"].begin_count, 1)
        self.assertEqual(layers["M2"].end_count, 1)

    def test_stale_source_blocks_before_mutation(self) -> None:
        module, _font, _layers, paths = self._load_module()
        review = self._review(module, ["M1", "M2"])
        paths[1].nodes[0].name = "changed-after-review"
        before = [node.identityToken for node in paths[1].nodes]

        stale = json.loads(
            asyncio.run(
                module.apply_start_node_alignment(
                    font_index=0,
                    glyph_name="A",
                    reference_master_id="M1",
                    path_index=0,
                    reference_node_index=0,
                    target_master_ids=["M1", "M2"],
                    expected_plan_fingerprint=review["planFingerprint"],
                    confirm=True,
                )
            )
        )
        self.assertFalse(stale["ok"])
        self.assertEqual(stale["errorType"], "stale_plan")
        self.assertEqual([node.identityToken for node in paths[1].nodes], before)

    def test_mid_batch_failure_restores_every_master(self) -> None:
        module, _font, layers, paths = self._load_module(rotations=(0, 2, 1))
        review = self._review(module, ["M1", "M2", "M3"])
        original_orders = [[node.identityToken for node in path.nodes] for path in paths]
        planned_by_master = {item["masterId"]: item for item in review["masters"]}
        failing_index = planned_by_master["M3"]["proposedStartNodeIndex"]
        paths[2].nodes[failing_index].fail_make_first = True

        failed = json.loads(
            asyncio.run(
                module.apply_start_node_alignment(
                    font_index=0,
                    glyph_name="A",
                    reference_master_id="M1",
                    path_index=0,
                    reference_node_index=0,
                    target_master_ids=["M1", "M2", "M3"],
                    expected_plan_fingerprint=review["planFingerprint"],
                    confirm=True,
                )
            )
        )
        self.assertFalse(failed["ok"])
        self.assertEqual(failed["errorType"], "mutation_failed")
        self.assertTrue(failed["rollback"]["succeeded"])
        self.assertEqual([[node.identityToken for node in path.nodes] for path in paths], original_orders)
        self.assertEqual(layers["M2"].begin_count, 1)

    def test_unexpected_native_node_field_change_is_detected_and_reported(self) -> None:
        module, _font, _layers, paths = self._load_module()
        review = self._review(module, ["M1", "M2"])
        original_order = [node.identityToken for node in paths[1].nodes]
        planned = next(item for item in review["masters"] if item["masterId"] == "M2")
        paths[1].nodes[planned["proposedStartNodeIndex"]].mutate_name_on_make_first = True

        failed = json.loads(
            asyncio.run(
                module.apply_start_node_alignment(
                    font_index=0,
                    glyph_name="A",
                    reference_master_id="M1",
                    path_index=0,
                    reference_node_index=0,
                    target_master_ids=["M1", "M2"],
                    expected_plan_fingerprint=review["planFingerprint"],
                    confirm=True,
                )
            )
        )

        self.assertFalse(failed["ok"])
        self.assertEqual(failed["errorType"], "rollback_failed")
        self.assertTrue(failed["fontChanged"])
        self.assertIn("verification_failed:M2:layer.paths[0].nodes", failed["error"])
        self.assertEqual([node.identityToken for node in paths[1].nodes], original_order)

    def test_unselected_reference_and_open_paths_are_rejected(self) -> None:
        module, _font, _layers, paths = self._load_module()
        paths[0].nodes[0].selected = False
        unselected = self._review(module, ["M1", "M2"])
        self.assertEqual(unselected["errorType"], "reference_node_not_selected")

        open_module, _font, _layers, _paths = self._load_module(closed=False)
        opened = self._review(open_module, ["M1", "M2"])
        self.assertEqual(opened["errorType"], "open_path")

    def test_confirmation_flags_and_fingerprint_are_required(self) -> None:
        module, _font, _layers, paths = self._load_module()
        missing_mode = json.loads(
            asyncio.run(
                module.apply_start_node_alignment(
                    font_index=0,
                    glyph_name="A",
                    reference_master_id="M1",
                    path_index=0,
                    reference_node_index=0,
                    target_master_ids=["M1", "M2"],
                    expected_plan_fingerprint="abc",
                )
            )
        )
        missing_fingerprint = json.loads(
            asyncio.run(
                module.apply_start_node_alignment(
                    font_index=0,
                    glyph_name="A",
                    reference_master_id="M1",
                    path_index=0,
                    reference_node_index=0,
                    target_master_ids=["M1", "M2"],
                    dry_run=True,
                )
            )
        )
        original_orders = [[node.identityToken for node in path.nodes] for path in paths]
        non_boolean_confirm = json.loads(
            asyncio.run(
                module.apply_start_node_alignment(
                    font_index=0,
                    glyph_name="A",
                    reference_master_id="M1",
                    path_index=0,
                    reference_node_index=0,
                    target_master_ids=["M1", "M2"],
                    expected_plan_fingerprint="abc",
                    confirm="false",
                )
            )
        )
        self.assertEqual(missing_mode["errorType"], "confirmation_required")
        self.assertEqual(missing_fingerprint["errorType"], "plan_fingerprint_required")
        self.assertEqual(non_boolean_confirm["errorType"], "confirmation_required")
        self.assertEqual(
            [[node.identityToken for node in path.nodes] for path in paths],
            original_orders,
        )


if __name__ == "__main__":
    unittest.main()
