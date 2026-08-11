"""Pure grid planning and shared atomic node-transaction coverage."""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path
import unittest


RESOURCES = (
    Path(__file__).resolve().parent.parent
    / "Glyphs MCP.glyphsPlugin"
    / "Contents"
    / "Resources"
)


def _load(name):
    spec = importlib.util.spec_from_file_location("glyphs_mcp_test_" + name, RESOURCES / (name + ".py"))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Point:
    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)


class Node:
    def __init__(self, x, y, node_type="offcurve"):
        self._position = Point(x, y)
        self.type = node_type
        self.rawType = 65 if node_type == "offcurve" else 35
        self.rawConnection = 0
        self.smooth = False
        self.orientation = 0
        self._name = None
        self.coerce_none_name = False
        self.ignore_next_write = False
        self.raise_next_write = False
        self.change_smooth_on_write = False
        self.write_hook = None

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = str(value) if self.coerce_none_name else value

    @property
    def position(self):
        return self._position

    @position.setter
    def position(self, value):
        if self.raise_next_write:
            self.raise_next_write = False
            raise RuntimeError("controlled write failure")
        if self.ignore_next_write:
            self.ignore_next_write = False
            return
        self._position = Point(value[0], value[1])
        if self.change_smooth_on_write:
            self.smooth = True
        if self.write_hook is not None:
            hook = self.write_hook
            self.write_hook = None
            hook()


class PathValue:
    def __init__(self, nodes, *, locked=False):
        self.nodes = list(nodes)
        self.closed = False
        self.locked = locked


class Anchor:
    def __init__(self, name, x, y):
        self.name = name
        self._position = Point(x, y)

    @property
    def position(self):
        return self._position

    @position.setter
    def position(self, value):
        self._position = Point(value[0], value[1])


class Layer:
    def __init__(self, paths):
        self.paths = list(paths)
        self.shapes = list(paths)
        self.anchors = []
        self.width = 500
        self.begin_count = 0
        self.end_count = 0
        self.raise_end = False

    def beginChanges(self):
        self.begin_count += 1

    def endChanges(self):
        self.end_count += 1
        if self.raise_end:
            raise RuntimeError("controlled end failure")


def update(path_index, node_index, x, y, expected_x=0, expected_y=0):
    return {
        "pathIndex": path_index,
        "nodeIndex": node_index,
        "expectedType": "offcurve",
        "expected": {"x": expected_x, "y": expected_y},
        "proposed": {"x": x, "y": y},
    }


class OutlineNodePatchEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = _load("outline_node_patch_engine")

    @staticmethod
    def raw(**overrides):
        value = {
            "path_index": 0,
            "node_index": 1,
            "expected_x": 0,
            "expected_y": 0,
            "expected_type": "offcurve",
            "x": 2.5,
            "y": -2.5,
        }
        value.update(overrides)
        return value

    def test_font_grid_rounds_half_away_from_zero(self):
        plan, error = self.engine.prepare_node_position_updates([self.raw()], grid_length=1, grid_subdivision=1)
        self.assertIsNone(error)
        self.assertEqual(plan["updates"][0]["proposed"], {"x": 3, "y": -3})
        self.assertTrue(plan["updates"][0]["snapped"])

    def test_subdivision_grid_and_disabled_grid_preserve_expected_precision(self):
        decimal, error = self.engine.prepare_node_position_updates(
            [self.raw(x=3.14, y=7.86)], grid_length=0.1, grid_subdivision=10
        )
        self.assertIsNone(error)
        self.assertTrue(math.isclose(decimal["updates"][0]["proposed"]["x"], 3.1))
        self.assertTrue(math.isclose(decimal["updates"][0]["proposed"]["y"], 7.9))
        self.assertEqual(decimal["grid"]["effectivePolicy"], "font")

        disabled, error = self.engine.prepare_node_position_updates(
            [self.raw(x=3.142, y=7.816)], grid_length=0, grid_subdivision=1
        )
        self.assertIsNone(error)
        self.assertEqual(disabled["updates"][0]["proposed"], {"x": 3.142, "y": 7.816})
        self.assertEqual(disabled["grid"]["effectivePolicy"], "continuous")
        self.assertTrue(disabled["grid"]["fontGridDisabled"])

    def test_subdivision_half_ties_are_deterministically_away_from_zero(self):
        plan, error = self.engine.prepare_node_position_updates(
            [self.raw(x=0.15, y=-0.15)], grid_length=0.1, grid_subdivision=10
        )
        self.assertIsNone(error)
        self.assertEqual(plan["updates"][0]["proposed"], {"x": 0.2, "y": -0.2})

    def test_continuous_is_explicit_and_does_not_require_grid_metadata(self):
        plan, error = self.engine.prepare_node_position_updates(
            [self.raw(x=1.125, y=-2.875)], grid_policy="continuous", grid_length=None
        )
        self.assertIsNone(error)
        self.assertEqual(plan["updates"][0]["proposed"], {"x": 1.125, "y": -2.875})
        self.assertFalse(plan["updates"][0]["snapped"])

    def test_strict_validation_rejects_nonfinite_duplicates_unknowns_and_limit(self):
        cases = (
            ([self.raw(x=float("nan"))], "finite"),
            ([self.raw(), self.raw()], "duplicate"),
            ([dict(self.raw(), surprise=True)], "unknown fields"),
            ([self.raw(path_index=True)], "integer"),
        )
        for values, marker in cases:
            with self.subTest(marker=marker):
                plan, error = self.engine.prepare_node_position_updates(values, grid_length=1)
                self.assertIsNone(plan)
                self.assertIn(marker, error)
        many = [self.raw(node_index=index) for index in range(257)]
        plan, error = self.engine.prepare_node_position_updates(many, grid_length=1)
        self.assertIsNone(plan)
        self.assertIn("256", error)

    def test_invalid_font_grid_is_rejected_but_continuous_remains_available(self):
        for value in (None, -1, float("nan")):
            with self.subTest(value=value):
                plan, error = self.engine.prepare_node_position_updates([self.raw()], grid_length=value)
                self.assertIsNone(plan)
                self.assertIn("font.gridLength", error)


class OutlineNodeTransactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.transaction = _load("outline_node_transaction")

    def make_layer(self):
        paths = [
            PathValue([Node(0, 0), Node(10, 0)]),
            PathValue([Node(0, 0), Node(0, 10)]),
        ]
        return Layer(paths)

    def test_multi_path_update_is_one_verified_change_batch(self):
        layer = self.make_layer()
        result = self.transaction.apply_position_updates(
            layer,
            layer.paths,
            [update(0, 0, 2, 3), update(1, 0, -2, -3)],
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["verification"]["changedNodeCount"], 2)
        self.assertEqual((layer.begin_count, layer.end_count), (1, 1))
        self.assertEqual((layer.paths[0].nodes[0].position.x, layer.paths[0].nodes[0].position.y), (2, 3))
        self.assertEqual((layer.paths[1].nodes[0].position.x, layer.paths[1].nodes[0].position.y), (-2, -3))

    def test_noop_update_is_verified_without_reporting_a_change(self):
        layer = self.make_layer()
        result = self.transaction.apply_position_updates(
            layer,
            layer.paths,
            [update(0, 0, 0, 0)],
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["changed"], [])
        self.assertEqual(result["verification"]["changedNodeCount"], 0)
        self.assertEqual((layer.begin_count, layer.end_count), (1, 1))

    def test_stale_and_locked_targets_fail_before_mutation(self):
        layer = self.make_layer()
        stale = self.transaction.apply_position_updates(
            layer, layer.paths, [update(0, 0, 2, 3, expected_x=9)]
        )
        self.assertFalse(stale["ok"])
        self.assertEqual(stale["errorCode"], "stale_target")
        self.assertEqual((layer.begin_count, layer.end_count), (0, 0))

        layer.paths[0].locked = True
        locked = self.transaction.apply_position_updates(layer, layer.paths, [update(0, 0, 2, 3)])
        self.assertFalse(locked["ok"])
        self.assertEqual(locked["errorCode"], "path_locked")
        self.assertEqual((layer.begin_count, layer.end_count), (0, 0))

    def test_write_and_readback_failures_restore_every_position(self):
        for failure in ("write", "readback"):
            with self.subTest(failure=failure):
                layer = self.make_layer()
                before = [
                    [(node.position.x, node.position.y) for node in path.nodes]
                    for path in layer.paths
                ]
                if failure == "write":
                    layer.paths[1].nodes[0].raise_next_write = True
                else:
                    layer.paths[1].nodes[0].ignore_next_write = True
                result = self.transaction.apply_position_updates(
                    layer,
                    layer.paths,
                    [update(0, 0, 2, 3), update(1, 0, -2, -3)],
                )
                self.assertFalse(result["ok"])
                self.assertTrue(result["rollback"]["succeeded"])
                after = [
                    [(node.position.x, node.position.y) for node in path.nodes]
                    for path in layer.paths
                ]
                self.assertEqual(after, before)
                self.assertEqual((layer.begin_count, layer.end_count), (1, 1))

    def test_rollback_does_not_coerce_untouched_null_node_names(self):
        layer = self.make_layer()
        for path in layer.paths:
            for node in path.nodes:
                node.coerce_none_name = True
                self.assertIsNone(node.name)
        layer.paths[1].nodes[0].ignore_next_write = True

        result = self.transaction.apply_position_updates(
            layer,
            layer.paths,
            [update(0, 0, 2, 3), update(1, 0, -2, -3)],
        )

        self.assertFalse(result["ok"])
        self.assertTrue(result["rollback"]["succeeded"])
        self.assertTrue(all(node.name is None for path in layer.paths for node in path.nodes))

    def test_protected_field_change_and_end_failure_roll_back(self):
        layer = self.make_layer()
        node = layer.paths[0].nodes[0]
        node.change_smooth_on_write = True
        result = self.transaction.apply_position_updates(layer, layer.paths, [update(0, 0, 2, 3)])
        self.assertFalse(result["ok"])
        self.assertEqual(result["errorCode"], "verification_failed")
        self.assertFalse(node.smooth)
        self.assertEqual((node.position.x, node.position.y), (0, 0))

        layer = self.make_layer()
        layer.raise_end = True
        result = self.transaction.apply_position_updates(layer, layer.paths, [update(0, 0, 2, 3)])
        self.assertFalse(result["ok"])
        self.assertEqual(result["errorCode"], "end_changes_failed")
        self.assertTrue(result["rollback"]["succeeded"])
        self.assertEqual((layer.paths[0].nodes[0].position.x, layer.paths[0].nodes[0].position.y), (0, 0))

    def test_complete_snapshot_restores_order_width_and_anchors(self):
        layer = self.make_layer()
        component = object()
        layer.shapes = [layer.paths[0], component, layer.paths[1]]
        anchor = Anchor("top", 50, 700)
        layer.anchors = [anchor]
        expected_shapes = list(layer.shapes)
        expected_nodes = list(layer.paths[0].nodes)

        def corrupt_protected_state():
            layer.shapes.reverse()
            layer.paths[0].nodes.reverse()
            layer.width = 777
            anchor.name = "moved"
            anchor.position = (1, 2)

        layer.paths[0].nodes[0].write_hook = corrupt_protected_state
        result = self.transaction.apply_position_updates(
            layer,
            layer.paths,
            [update(0, 0, 2, 3)],
        )

        self.assertFalse(result["ok"])
        self.assertTrue(result["rollback"]["succeeded"])
        self.assertEqual(layer.shapes, expected_shapes)
        self.assertEqual(layer.paths[0].nodes, expected_nodes)
        self.assertEqual(layer.width, 500)
        self.assertEqual(anchor.name, "top")
        self.assertEqual((anchor.position.x, anchor.position.y), (50, 700))

    def test_missing_change_batch_is_rejected(self):
        layer = self.make_layer()
        layer.beginChanges = None
        result = self.transaction.apply_position_updates(layer, layer.paths, [update(0, 0, 2, 3)])
        self.assertFalse(result["ok"])
        self.assertEqual(result["errorCode"], "change_batch_unavailable")
        self.assertFalse(result["changeBatch"]["available"])


if __name__ == "__main__":
    unittest.main()
