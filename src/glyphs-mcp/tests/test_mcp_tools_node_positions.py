"""Contracts for the guarded node-position MCP wrapper."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest import mock


RESOURCES = (
    Path(__file__).resolve().parent.parent
    / "Glyphs MCP.glyphsPlugin"
    / "Contents"
    / "Resources"
)
if str(RESOURCES) not in sys.path:
    sys.path.insert(0, str(RESOURCES))


class Point:
    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)


class Node:
    def __init__(
        self,
        x,
        y,
        node_type="offcurve",
        *,
        force_integer=False,
        glyphs_name_semantics=False,
    ):
        self._position = Point(x, y)
        self.type = node_type
        self.rawType = 65
        self.rawConnection = 0
        self.smooth = False
        self.orientation = 0
        self._name = None if glyphs_name_semantics else ""
        self.glyphs_name_semantics = glyphs_name_semantics
        self.force_integer = force_integer

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = str(value) if self.glyphs_name_semantics else value

    @property
    def position(self):
        return self._position

    @position.setter
    def position(self, value):
        if self.force_integer:
            self._position = Point(round(value[0]), round(value[1]))
        else:
            self._position = Point(value[0], value[1])


class PathValue:
    def __init__(self, nodes, *, locked=False):
        self.nodes = list(nodes)
        self.closed = False
        self.locked = locked


class Layer:
    def __init__(self, paths):
        self.paths = list(paths)
        self.shapes = list(paths)
        self.anchors = []
        self.width = 500
        self.layerId = "m1"
        self.associatedMasterId = "m1"
        self.name = "Regular"
        self.begin_count = 0
        self.end_count = 0

    def beginChanges(self):
        self.begin_count += 1

    def endChanges(self):
        self.end_count += 1


def raw_update(path_index=0, node_index=0, *, expected_x=0, expected_y=0, x=2.5, y=-2.5):
    return {
        "path_index": path_index,
        "node_index": node_index,
        "expected_x": expected_x,
        "expected_y": expected_y,
        "expected_type": "offcurve",
        "x": x,
        "y": y,
    }


class McpToolsNodePositionsTests(unittest.TestCase):
    def _load(
        self,
        *,
        grid_length=1.0,
        force_integer=False,
        glyphs_name_semantics=False,
    ):
        paths = [
            PathValue(
                [
                    Node(
                        0,
                        0,
                        force_integer=force_integer,
                        glyphs_name_semantics=glyphs_name_semantics,
                    ),
                    Node(10, 0, glyphs_name_semantics=glyphs_name_semantics),
                ]
            ),
            PathValue(
                [
                    Node(0, 0, glyphs_name_semantics=glyphs_name_semantics),
                    Node(0, 10, glyphs_name_semantics=glyphs_name_semantics),
                ]
            ),
        ]
        layer = Layer(paths)
        glyph = types.SimpleNamespace(layers={"m1": layer})
        font = types.SimpleNamespace(
            familyName="Unit Test Sans",
            filepath=None,
            gridLength=grid_length,
            gridSubDivision=10 if grid_length == 0.1 else 1,
            glyphs={"A": glyph},
        )
        glyphs = types.SimpleNamespace(fonts=[font])

        helpers = types.SimpleNamespace(
            _font_resolution_error=lambda *args, **kwargs: {"ok": False, "error": "bad font"},
            _get_layer_id=lambda value: value.layerId,
            _glyphs_show_layer_link_fields=lambda *args, **kwargs: {},
            _layer_display_name=lambda *args, **kwargs: "Regular",
            _layer_paths=lambda value: list(value.paths),
            _normalized_node_type=lambda node: str(node.type).lower(),
            _resolve_font_by_index=lambda _glyphs, index: ((font, [font]) if index == 0 else (None, [font])),
            _run_on_main_thread=lambda callback: callback(),
            _safe_json=json.dumps,
        )
        spec = importlib.util.spec_from_file_location(
            "glyphs_mcp_test_node_positions_{}".format(id(layer)),
            RESOURCES / "mcp_tools_node_positions.py",
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(
            sys.modules,
            {
                "GlyphsApp": types.SimpleNamespace(Glyphs=glyphs),
                "mcp_tool_helpers": helpers,
                "tool_registration": types.SimpleNamespace(glyphs_tool=lambda: (lambda function: function)),
            },
        ):
            spec.loader.exec_module(module)
        return module, font, layer

    def test_dry_run_snaps_and_does_not_mutate(self):
        module, _font, layer = self._load()
        payload = json.loads(
            asyncio.run(
                module.update_glyph_node_positions(
                    glyph_name="A",
                    master_id="m1",
                    updates=[raw_update()],
                    dry_run=True,
                )
            )
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["updates"][0]["proposed"], {"x": 3, "y": -3})
        self.assertEqual(payload["summary"]["snappedCount"], 1)
        self.assertEqual(payload["summary"]["changedCount"], 0)
        self.assertEqual((layer.paths[0].nodes[0].position.x, layer.paths[0].nodes[0].position.y), (0, 0))
        self.assertEqual((layer.begin_count, layer.end_count), (0, 0))

    def test_direct_confirm_updates_multiple_paths_atomically(self):
        module, _font, layer = self._load()
        payload = json.loads(
            asyncio.run(
                module.update_glyph_node_positions(
                    glyph_name="A",
                    master_id="m1",
                    updates=[
                        raw_update(x=2, y=3),
                        raw_update(path_index=1, x=-2, y=-3),
                    ],
                    confirm=True,
                )
            )
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["summary"]["appliedCount"], 2)
        self.assertEqual(payload["summary"]["verifiedCount"], 2)
        self.assertFalse(payload["fontSaved"])
        self.assertEqual((layer.begin_count, layer.end_count), (1, 1))
        self.assertEqual(payload["updates"][0]["actual"], {"x": 2.0, "y": 3.0})

    def test_confirmed_noop_reports_authoritative_actual_position(self):
        module, _font, layer = self._load()
        payload = json.loads(
            asyncio.run(
                module.update_glyph_node_positions(
                    glyph_name="A",
                    master_id="m1",
                    updates=[raw_update(x=0, y=0)],
                    confirm=True,
                )
            )
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["summary"]["changedCount"], 0)
        self.assertEqual(payload["updates"][0]["status"], "unchanged")
        self.assertEqual(payload["updates"][0]["actual"], {"x": 0.0, "y": 0.0})

    def test_font_subdivision_and_disabled_grid_preserve_fractional_coordinates(self):
        module, _font, layer = self._load(grid_length=0.1)
        payload = json.loads(
            asyncio.run(
                module.update_glyph_node_positions(
                    glyph_name="A",
                    master_id="m1",
                    updates=[raw_update(x=2.26, y=-2.26)],
                    confirm=True,
                )
            )
        )
        self.assertTrue(payload["ok"])
        self.assertAlmostEqual(layer.paths[0].nodes[0].position.x, 2.3)
        self.assertAlmostEqual(layer.paths[0].nodes[0].position.y, -2.3)

        module, _font, layer = self._load(grid_length=0)
        payload = json.loads(
            asyncio.run(
                module.update_glyph_node_positions(
                    glyph_name="A",
                    master_id="m1",
                    updates=[raw_update(x=2.26, y=-2.26)],
                    confirm=True,
                )
            )
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["grid"]["effectivePolicy"], "continuous")
        self.assertAlmostEqual(layer.paths[0].nodes[0].position.x, 2.26)

    def test_stale_and_locked_targets_fail_without_change_batch(self):
        module, _font, layer = self._load()
        stale = json.loads(
            asyncio.run(
                module.update_glyph_node_positions(
                    glyph_name="A",
                    master_id="m1",
                    updates=[raw_update(expected_x=9)],
                    confirm=True,
                )
            )
        )
        self.assertFalse(stale["ok"])
        self.assertEqual(stale["errorCode"], "stale_target")
        layer.paths[0].locked = True
        locked = json.loads(
            asyncio.run(
                module.update_glyph_node_positions(
                    glyph_name="A",
                    master_id="m1",
                    updates=[raw_update()],
                    confirm=True,
                )
            )
        )
        self.assertFalse(locked["ok"])
        self.assertEqual(locked["errorCode"], "path_locked")
        self.assertEqual((layer.begin_count, layer.end_count), (0, 0))

    def test_continuous_readback_mismatch_rolls_back_with_specific_error(self):
        module, _font, layer = self._load(
            force_integer=True,
            glyphs_name_semantics=True,
        )
        self.assertTrue(all(node.name is None for path in layer.paths for node in path.nodes))
        payload = json.loads(
            asyncio.run(
                module.update_glyph_node_positions(
                    glyph_name="A",
                    master_id="m1",
                    updates=[raw_update(x=2.25, y=-2.25)],
                    grid_policy="continuous",
                    confirm=True,
                )
            )
        )
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errorCode"], "continuous_coordinate_not_preserved")
        self.assertTrue(payload["rollback"]["attempted"])
        self.assertTrue(payload["rollback"]["succeeded"])
        self.assertEqual(payload["rollback"]["errors"], [])
        self.assertEqual(payload["updates"][0]["actual"], {"x": 0.0, "y": 0.0})
        self.assertEqual(payload["updates"][0]["status"], "rolled_back")
        self.assertEqual((layer.paths[0].nodes[0].position.x, layer.paths[0].nodes[0].position.y), (0, 0))
        self.assertTrue(all(node.name is None for path in layer.paths for node in path.nodes))

    def test_safety_modes_are_exact_booleans(self):
        module, _font, _layer = self._load()
        neither = json.loads(
            asyncio.run(
                module.update_glyph_node_positions(
                    glyph_name="A", master_id="m1", updates=[raw_update()]
                )
            )
        )
        both = json.loads(
            asyncio.run(
                module.update_glyph_node_positions(
                    glyph_name="A",
                    master_id="m1",
                    updates=[raw_update()],
                    dry_run=True,
                    confirm=True,
                )
            )
        )
        nonbool = json.loads(
            asyncio.run(
                module.update_glyph_node_positions(
                    glyph_name="A",
                    master_id="m1",
                    updates=[raw_update()],
                    dry_run="true",
                )
            )
        )
        self.assertFalse(neither["ok"])
        self.assertFalse(both["ok"])
        self.assertFalse(nonbool["ok"])


if __name__ == "__main__":
    unittest.main()
