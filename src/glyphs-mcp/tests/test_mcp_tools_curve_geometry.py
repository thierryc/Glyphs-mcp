"""Regression tests for cleanroom curve-geometry MCP wrappers."""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import json
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


def _resources_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "Glyphs MCP.glyphsPlugin" / "Contents" / "Resources"


def _module_path() -> Path:
    return _resources_dir() / "mcp_tools_curve_geometry.py"


class _FakeMCP:
    def tool(self, *args, **kwargs):
        def decorator(fn):
            return fn

        return decorator


class _Point:
    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)


class _Node:
    def __init__(self, x, y, node_type, smooth=False):
        self._position = _Point(x, y)
        self.type = node_type
        self.smooth = bool(smooth)
        self.ignore_next_write = False
        self.raise_next_write = False
        self.write_count = 0
        self.raise_from_write = None

    @property
    def position(self):
        return self._position

    @position.setter
    def position(self, value):
        self.write_count += 1
        if self.raise_from_write is not None and self.write_count >= self.raise_from_write:
            raise RuntimeError("controlled persistent write failure")
        if self.raise_next_write:
            self.raise_next_write = False
            raise RuntimeError("controlled write failure")
        if self.ignore_next_write:
            self.ignore_next_write = False
            return
        self._position = _Point(value[0], value[1])


class _Path:
    def __init__(self, nodes, closed=False):
        self.nodes = list(nodes)
        self.closed = bool(closed)


class _NodeProxy:
    """Fresh Python wrapper around one stable host-node value."""

    def __init__(self, node):
        self._node = node

    @property
    def position(self):
        return self._node.position

    @position.setter
    def position(self, value):
        self._node.position = value

    @property
    def type(self):
        return self._node.type

    @property
    def smooth(self):
        return self._node.smooth


class _FreshProxyPath:
    """Model a Glyphs collection that re-wraps nodes on every iteration."""

    def __init__(self, nodes, closed=False):
        self._nodes = list(nodes)
        self.closed = bool(closed)

    @property
    def nodes(self):
        return [_NodeProxy(node) for node in self._nodes]


class _Component:
    pass


class _Layer:
    def __init__(self, path, *, glyphs4=False):
        self.associatedMasterId = "m1"
        self.layerId = "m1"
        self.name = "Regular"
        self.begin_count = 0
        self.end_count = 0
        self.raise_begin_changes = False
        self.raise_end_changes = False
        self.width = 500
        self.components = ["component-marker"]
        if glyphs4:
            self.shapes = [_Component(), path]
            self.paths = []
        else:
            self.paths = [path]

    def beginChanges(self):
        self.begin_count += 1
        if self.raise_begin_changes:
            raise RuntimeError("controlled beginChanges failure")

    def endChanges(self):
        self.end_count += 1
        if self.raise_end_changes:
            raise RuntimeError("controlled endChanges failure")


def _nodes():
    return [
        _Node(0, 0, "line"),
        _Node(20, 0, "offcurve"),
        _Node(100, 60, "offcurve"),
        _Node(100, 100, "curve", smooth=True),
    ]


def _two_cubic_nodes():
    return [
        _Node(0, 0, "line"),
        _Node(20, 0, "offcurve"),
        _Node(100, 60, "offcurve"),
        _Node(100, 100, "curve", smooth=True),
        _Node(100, 120, "offcurve"),
        _Node(40, 200, "offcurve"),
        _Node(0, 200, "curve", smooth=True),
    ]


def _positions(nodes):
    return [(node.position.x, node.position.y) for node in nodes]


class McpToolsCurveGeometryTests(unittest.TestCase):
    def _load_module(
        self,
        *,
        glyphs4=False,
        node_values=None,
        upm=1000,
        before_main_thread=None,
        fresh_node_proxies=False,
        grid_length=1.0,
        grid_subdivision=1,
    ):
        nodes = list(node_values) if node_values is not None else _nodes()
        path = _FreshProxyPath(nodes) if fresh_node_proxies else _Path(nodes)
        layer = _Layer(path, glyphs4=glyphs4)
        glyph = types.SimpleNamespace(name="A", layers={"m1": layer})
        font = types.SimpleNamespace(
            familyName="Geometry Test",
            upm=upm,
            gridLength=grid_length,
            gridSubDivision=grid_subdivision,
            filepath=None,
            glyphs={"A": glyph},
        )
        glyphs = types.SimpleNamespace(fonts=[font], font=font)

        def _resolve_font_by_index(_glyphs, font_index):
            return (font, [font]) if int(font_index) == 0 else (None, [font])

        def _layer_paths(layer_obj):
            shapes = list(getattr(layer_obj, "shapes", []) or [])
            if shapes:
                return [shape for shape in shapes if hasattr(shape, "nodes")]
            return list(getattr(layer_obj, "paths", []) or [])

        def _run_on_main_thread(callback):
            if before_main_thread is not None:
                before_main_thread(layer, path, nodes)
            return callback()

        helpers = types.SimpleNamespace(
            _font_resolution_error=lambda index, fonts, ok_key=None: {"ok": False, "error": "bad font"},
            _get_layer_id=lambda layer_obj: layer_obj.layerId,
            _glyphs_show_layer_link_fields=lambda *args, **kwargs: {},
            _layer_display_name=lambda *args, **kwargs: "Regular",
            _layer_paths=_layer_paths,
            _normalized_node_type=lambda node: str(node.type).lower(),
            _resolve_font_by_index=_resolve_font_by_index,
            _run_on_main_thread=_run_on_main_thread,
            _safe_json=lambda payload: json.dumps(payload),
        )

        engine_name = "outline_geometry_engine"
        engine_spec = importlib.util.spec_from_file_location(engine_name, _resources_dir() / "outline_geometry_engine.py")
        assert engine_spec is not None and engine_spec.loader is not None
        engine = importlib.util.module_from_spec(engine_spec)
        engine_spec.loader.exec_module(engine)

        module_name = "glyphs_mcp_test_mcp_tools_curve_geometry_{}".format("g4" if glyphs4 else "g3")
        spec = importlib.util.spec_from_file_location(module_name, _module_path())
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(
            sys.modules,
            {
                "GlyphsApp": types.SimpleNamespace(Glyphs=glyphs),
                "mcp_runtime": types.SimpleNamespace(mcp=_FakeMCP()),
                "mcp_tool_helpers": helpers,
                engine_name: engine,
            },
        ):
            spec.loader.exec_module(module)
        return module, font, layer, path, nodes

    def test_tool_descriptions_are_discoverable_and_explain_safe_workflows(self) -> None:
        module, _font, _layer, _path, _nodes_value = self._load_module()
        descriptions = {
            name: inspect.getdoc(getattr(module, name)) or ""
            for name in ("review_tunni_geometry", "apply_tunni_balance", "review_curve_quality")
        }

        tunni = descriptions["review_tunni_geometry"]
        self.assertIn("Tunni intersection", tunni)
        self.assertIn("endpoint handle ratios", tunni)
        self.assertIn("stable rejection reason", tunni)
        self.assertIn("before ``apply_tunni_balance``", tunni)

        apply_description = descriptions["apply_tunni_balance"]
        self.assertIn("nonempty unique list", apply_description)
        self.assertIn("recomputes every proposal", apply_description)
        self.assertIn("review_tunni_geometry", apply_description)
        self.assertIn("actual before/after", apply_description)
        self.assertIn("never saves the font", apply_description)

        quality = descriptions["review_curve_quality"]
        self.assertIn("signed cubic curvature", quality)
        self.assertIn("UPM-normalized", quality)
        self.assertIn("JSON-safe", quality)
        self.assertIn("9–257", quality)
        self.assertIn("64 selected segments", quality)
        self.assertIn("never an artistic score or pass/fail", quality)

    def test_review_requires_explicit_master_and_path(self) -> None:
        module, _font, _layer, _path, _nodes_value = self._load_module()
        payload = json.loads(asyncio.run(module.review_tunni_geometry(glyph_name="A")))
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "master_id is required")

    def test_path_index_is_a_strict_integer(self) -> None:
        module, _font, _layer, _path, _nodes_value = self._load_module()
        for path_index in (True, 0.0, 0.5, "0"):
            with self.subTest(path_index=path_index):
                payload = json.loads(
                    asyncio.run(
                        module.review_tunni_geometry(
                            glyph_name="A",
                            master_id="m1",
                            path_index=path_index,
                        )
                    )
                )
                self.assertFalse(payload["ok"])
                self.assertEqual(payload["error"], "path_index must be an integer")

    def test_tunni_review_is_read_only_and_reports_proposal(self) -> None:
        module, _font, _layer, _path, nodes = self._load_module()
        before = _positions(nodes)
        payload = json.loads(
            asyncio.run(
                module.review_tunni_geometry(
                    glyph_name="A",
                    master_id="m1",
                    path_index=0,
                )
            )
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["geometryDataVersion"], 1)
        self.assertEqual(payload["summary"]["eligibleSegmentCount"], 1)
        self.assertEqual(payload["segments"][0]["segmentEndNodeIndex"], 3)
        self.assertAlmostEqual(payload["segments"][0]["ratios"]["start"], 0.2, places=12)
        self.assertAlmostEqual(payload["segments"][0]["ratios"]["end"], 0.4, places=12)
        self.assertAlmostEqual(payload["segments"][0]["relativeImbalance"], 0.5, places=12)
        self.assertAlmostEqual(payload["segments"][0]["targetRatio"], 0.3, places=12)
        proposed = payload["segments"][0]["proposed"]
        self.assertAlmostEqual(proposed["handle1"]["x"], 30.0, places=12)
        self.assertAlmostEqual(proposed["handle1"]["y"], 0.0, places=12)
        self.assertAlmostEqual(proposed["handle2"]["x"], 100.0, places=12)
        self.assertAlmostEqual(proposed["handle2"]["y"], 70.0, places=12)
        self.assertEqual(_positions(nodes), before)

    def test_tunni_defaults_to_font_grid_and_continuous_is_explicit(self) -> None:
        module, _font, _layer, _path, _nodes_value = self._load_module(
            grid_length=0.5,
            grid_subdivision=2,
        )
        gridded = json.loads(
            asyncio.run(
                module.review_tunni_geometry(
                    glyph_name="A", master_id="m1", path_index=0
                )
            )
        )
        continuous = json.loads(
            asyncio.run(
                module.review_tunni_geometry(
                    glyph_name="A", master_id="m1", path_index=0, grid_policy="continuous"
                )
            )
        )

        self.assertEqual(gridded["params"]["gridPolicy"], "font")
        self.assertEqual(gridded["params"]["gridLength"], 0.5)
        self.assertEqual(gridded["params"]["gridSubDivision"], 2)
        self.assertTrue(gridded["segments"][0]["grid"]["onGrid"])
        self.assertIn("idealProposed", gridded["segments"][0])
        self.assertEqual(continuous["params"]["gridPolicy"], "continuous")
        self.assertEqual(continuous["segments"][0]["grid"]["policy"], "continuous")

    def test_tunni_rejects_unknown_grid_policy_before_mutation(self) -> None:
        module, _font, layer, _path, nodes = self._load_module()
        before = _positions(nodes)

        payload = json.loads(
            asyncio.run(
                module.apply_tunni_balance(
                    glyph_name="A",
                    master_id="m1",
                    path_index=0,
                    segment_end_node_indices=[3],
                    grid_policy="nearest",
                    confirm=True,
                )
            )
        )

        self.assertFalse(payload["ok"])
        self.assertIn("grid_policy", payload["error"])
        self.assertEqual(_positions(nodes), before)
        self.assertEqual((layer.begin_count, layer.end_count), (0, 0))

    def test_review_captures_plain_snapshot_inside_main_thread_dispatch(self) -> None:
        dispatch_count = [0]

        def update_before_snapshot(_layer, _path, nodes):
            dispatch_count[0] += 1
            nodes[1].position = (10.0, 0.0)
            nodes[2].position = (100.0, 70.0)

        module, _font, layer, _path, nodes = self._load_module(before_main_thread=update_before_snapshot)
        payload = json.loads(
            asyncio.run(
                module.review_tunni_geometry(
                    glyph_name="A",
                    master_id="m1",
                    path_index=0,
                    segment_end_node_indices=[3],
                )
            )
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(dispatch_count[0], 1)
        self.assertAlmostEqual(payload["segments"][0]["ratios"]["start"], 0.1)
        self.assertAlmostEqual(payload["segments"][0]["ratios"]["end"], 0.3)
        self.assertEqual(_positions(nodes)[1:], [(10.0, 0.0), (100.0, 70.0), (100.0, 100.0)])
        self.assertEqual((layer.begin_count, layer.end_count), (0, 0))

    def test_apply_requires_exactly_one_safety_mode(self) -> None:
        module, _font, _layer, _path, _nodes_value = self._load_module()
        neither = json.loads(
            asyncio.run(
                module.apply_tunni_balance(
                    glyph_name="A", master_id="m1", path_index=0, segment_end_node_indices=[3]
                )
            )
        )
        both = json.loads(
            asyncio.run(
                module.apply_tunni_balance(
                    glyph_name="A",
                    master_id="m1",
                    path_index=0,
                    segment_end_node_indices=[3],
                    dry_run=True,
                    confirm=True,
                )
            )
        )
        self.assertFalse(neither["ok"])
        self.assertFalse(both["ok"])

    def test_apply_safety_modes_require_actual_booleans_before_dispatch(self) -> None:
        dispatch_count = [0]

        def observe_dispatch(_layer, _path, _nodes_value):
            dispatch_count[0] += 1

        module, _font, layer, _path, nodes = self._load_module(before_main_thread=observe_dispatch)
        before = _positions(nodes)
        cases = (
            ("dry_run", "true"),
            ("dry_run", 1),
            ("dry_run", None),
            ("confirm", "true"),
            ("confirm", 1),
            ("confirm", None),
        )
        for field, value in cases:
            with self.subTest(field=field, value=value):
                arguments = {
                    "glyph_name": "A",
                    "master_id": "m1",
                    "path_index": 0,
                    "segment_end_node_indices": [3],
                    "dry_run": False,
                    "confirm": False,
                }
                arguments[field] = value
                payload = json.loads(asyncio.run(module.apply_tunni_balance(**arguments)))

                self.assertFalse(payload["ok"])
                self.assertEqual(payload["error"], "{} must be a boolean".format(field))

        self.assertEqual(dispatch_count[0], 0)
        self.assertEqual(_positions(nodes), before)
        self.assertEqual((layer.begin_count, layer.end_count), (0, 0))

    def test_segment_indices_are_strict_unique_json_integers(self) -> None:
        module, _font, _layer, _path, _nodes_value = self._load_module()
        for indices in ([True], [3.0], [3.5], ["3"], [3, 3]):
            with self.subTest(indices=indices):
                reviewed = json.loads(
                    asyncio.run(
                        module.review_tunni_geometry(
                            glyph_name="A",
                            master_id="m1",
                            path_index=0,
                            segment_end_node_indices=indices,
                        )
                    )
                )
                applied = json.loads(
                    asyncio.run(
                        module.apply_tunni_balance(
                            glyph_name="A",
                            master_id="m1",
                            path_index=0,
                            segment_end_node_indices=indices,
                            dry_run=True,
                        )
                    )
                )
                self.assertFalse(reviewed["ok"])
                self.assertFalse(applied["ok"])
                self.assertIn("segment_end_node_indices", reviewed["error"])

    def test_numeric_parameters_must_be_finite_and_handle_minimum_is_one(self) -> None:
        module, _font, _layer, _path, nodes = self._load_module()
        before = _positions(nodes)
        tunni_cases = (
            {"imbalance_threshold": float("nan")},
            {"imbalance_threshold": float("inf")},
            {"min_handle_length": float("nan")},
            {"min_handle_length": float("inf")},
            {"min_handle_length": 0.999},
        )
        for extra in tunni_cases:
            with self.subTest(tool="tunni", extra=extra):
                payload = json.loads(
                    asyncio.run(
                        module.review_tunni_geometry(
                            glyph_name="A",
                            master_id="m1",
                            path_index=0,
                            **extra,
                        )
                    )
                )
                self.assertFalse(payload["ok"])

        curve_cases = (
            {"samples_per_curve": float("nan")},
            {"samples_per_curve": float("inf")},
            {"discontinuity_threshold": float("nan")},
            {"discontinuity_threshold": float("inf")},
            {"spike_ratio_threshold": float("nan")},
            {"spike_ratio_threshold": float("inf")},
        )
        for extra in curve_cases:
            with self.subTest(tool="curve", extra=extra):
                payload = json.loads(
                    asyncio.run(
                        module.review_curve_quality(
                            glyph_name="A",
                            master_id="m1",
                            path_index=0,
                            **extra,
                        )
                    )
                )
                self.assertFalse(payload["ok"])
        self.assertEqual(_positions(nodes), before)

    def test_dry_run_does_not_mutate(self) -> None:
        dispatch_count = [0]

        def observe_dispatch(_layer, _path, _nodes_value):
            dispatch_count[0] += 1

        module, _font, layer, _path, nodes = self._load_module(before_main_thread=observe_dispatch)
        before = _positions(nodes)
        payload = json.loads(
            asyncio.run(
                module.apply_tunni_balance(
                    glyph_name="A",
                    master_id="m1",
                    path_index=0,
                    segment_end_node_indices=[3],
                    dry_run=True,
                )
            )
        )

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["dryRun"])
        self.assertEqual(payload["summary"]["plannedSegmentCount"], 1)
        self.assertEqual(_positions(nodes), before)
        self.assertEqual(dispatch_count[0], 1)
        self.assertEqual(layer.begin_count, 0)
        self.assertEqual(layer.end_count, 0)

    def test_dry_run_reports_stable_skipped_and_rejected_records(self) -> None:
        module, _font, layer, _path, nodes = self._load_module()
        before = _positions(nodes)
        payload = json.loads(
            asyncio.run(
                module.apply_tunni_balance(
                    glyph_name="A",
                    master_id="m1",
                    path_index=0,
                    segment_end_node_indices=[0, 3],
                    imbalance_threshold=1.0,
                    dry_run=True,
                )
            )
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["planned"], [])
        self.assertEqual(payload["applied"], [])
        self.assertEqual(
            payload["skipped"],
            [
                {
                    "segmentEndNodeIndex": 3,
                    "status": "skipped",
                    "eligible": False,
                    "reason": "below_imbalance_threshold",
                }
            ],
        )
        self.assertEqual(
            payload["rejected"],
            [
                {
                    "segmentEndNodeIndex": 0,
                    "status": "rejected",
                    "eligible": False,
                    "reason": "open_path_boundary",
                }
            ],
        )
        self.assertEqual(payload["summary"]["skippedSegmentCount"], 1)
        self.assertEqual(payload["summary"]["rejectedSegmentCount"], 1)
        self.assertEqual(payload["target"]["omittedComponentCount"], 1)
        self.assertEqual(payload["summary"]["omittedComponentCount"], 1)
        self.assertEqual(_positions(nodes), before)
        self.assertEqual((layer.begin_count, layer.end_count), (0, 0))

    def test_confirm_changes_only_two_handles_and_batches_layer(self) -> None:
        module, _font, layer, path, nodes = self._load_module()
        before = _positions(nodes)
        types_before = [node.type for node in nodes]
        smooth_before = [node.smooth for node in nodes]
        width_before = layer.width
        components_before = list(layer.components)
        payload = json.loads(
            asyncio.run(
                module.apply_tunni_balance(
                    glyph_name="A",
                    master_id="m1",
                    path_index=0,
                    segment_end_node_indices=[3],
                    confirm=True,
                )
            )
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["applied"]), 1)
        applied = payload["applied"][0]
        self.assertEqual(applied["segmentEndNodeIndex"], 3)
        self.assertEqual(applied["status"], "applied")
        self.assertEqual(applied["handles"]["handle1"]["nodeIndex"], 1)
        self.assertEqual(applied["handles"]["handle1"]["before"], {"x": 20.0, "y": 0.0})
        self.assertAlmostEqual(applied["handles"]["handle1"]["after"]["x"], 30.0)
        self.assertAlmostEqual(applied["handles"]["handle1"]["after"]["y"], 0.0)
        self.assertEqual(applied["handles"]["handle2"]["nodeIndex"], 2)
        self.assertEqual(applied["handles"]["handle2"]["before"], {"x": 100.0, "y": 60.0})
        self.assertAlmostEqual(applied["handles"]["handle2"]["after"]["x"], 100.0)
        self.assertAlmostEqual(applied["handles"]["handle2"]["after"]["y"], 70.0)
        self.assertEqual(payload["verification"]["changedNodeCount"], 2)
        self.assertEqual(_positions(nodes)[0], before[0])
        self.assertEqual(_positions(nodes)[3], before[3])
        self.assertAlmostEqual(_positions(nodes)[1][0], 30.0)
        self.assertAlmostEqual(_positions(nodes)[1][1], 0.0)
        self.assertAlmostEqual(_positions(nodes)[2][0], 100.0)
        self.assertAlmostEqual(_positions(nodes)[2][1], 70.0)
        self.assertEqual([node.type for node in nodes], types_before)
        self.assertEqual([node.smooth for node in nodes], smooth_before)
        self.assertFalse(path.closed)
        self.assertEqual(layer.width, width_before)
        self.assertEqual(layer.components, components_before)
        self.assertEqual((layer.begin_count, layer.end_count), (1, 1))

    def test_confirm_verifies_fresh_node_proxies_by_structure_and_coordinates(self) -> None:
        module, _font, layer, path, nodes = self._load_module(fresh_node_proxies=True)
        first_nodes = path.nodes
        second_nodes = path.nodes
        self.assertTrue(all(first is not second for first, second in zip(first_nodes, second_nodes)))

        before = _positions(nodes)
        payload = json.loads(
            asyncio.run(
                module.apply_tunni_balance(
                    glyph_name="A",
                    master_id="m1",
                    path_index=0,
                    segment_end_node_indices=[3],
                    confirm=True,
                )
            )
        )

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["verification"]["succeeded"])
        self.assertTrue(payload["verification"]["topologyPreserved"])
        self.assertTrue(payload["verification"]["untargetedNodesPreserved"])
        self.assertEqual(payload["verification"]["changedNodeCount"], 2)
        self.assertEqual(_positions(nodes)[0], before[0])
        self.assertEqual(_positions(nodes)[3], before[3])
        self.assertAlmostEqual(nodes[1].position.x, 30.0)
        self.assertAlmostEqual(nodes[2].position.y, 70.0)
        self.assertEqual((layer.begin_count, layer.end_count), (1, 1))

    def test_confirm_resolves_snapshots_and_recomputes_after_main_thread_dispatch(self) -> None:
        def mutate_before_dispatch(_layer, _path, nodes):
            nodes[1].position = (10.0, 0.0)
            nodes[2].position = (100.0, 70.0)

        module, _font, layer, _path, nodes = self._load_module(before_main_thread=mutate_before_dispatch)
        payload = json.loads(
            asyncio.run(
                module.apply_tunni_balance(
                    glyph_name="A",
                    master_id="m1",
                    path_index=0,
                    segment_end_node_indices=[3],
                    confirm=True,
                )
            )
        )

        self.assertTrue(payload["ok"])
        applied = payload["applied"][0]
        self.assertEqual(applied["handles"]["handle1"]["before"], {"x": 10.0, "y": 0.0})
        self.assertEqual(applied["handles"]["handle2"]["before"], {"x": 100.0, "y": 70.0})
        self.assertAlmostEqual(applied["handles"]["handle1"]["after"]["x"], 20.0)
        self.assertAlmostEqual(applied["handles"]["handle2"]["after"]["y"], 80.0)
        self.assertAlmostEqual(nodes[1].position.x, 20.0)
        self.assertAlmostEqual(nodes[2].position.y, 80.0)
        self.assertEqual((layer.begin_count, layer.end_count), (1, 1))

    def test_confirm_applies_multiple_explicit_segments_in_one_batch(self) -> None:
        module, _font, layer, _path, nodes = self._load_module(node_values=_two_cubic_nodes())
        before = _positions(nodes)
        payload = json.loads(
            asyncio.run(
                module.apply_tunni_balance(
                    glyph_name="A",
                    master_id="m1",
                    path_index=0,
                    segment_end_node_indices=[3, 6],
                    confirm=True,
                )
            )
        )

        self.assertTrue(payload["ok"])
        self.assertEqual([record["segmentEndNodeIndex"] for record in payload["applied"]], [3, 6])
        self.assertEqual(payload["verification"]["changedNodeCount"], 4)
        self.assertEqual(payload["summary"]["appliedSegmentCount"], 2)
        self.assertEqual((layer.begin_count, layer.end_count), (1, 1))
        self.assertEqual(_positions(nodes)[0], before[0])
        self.assertEqual(_positions(nodes)[3], before[3])
        self.assertEqual(_positions(nodes)[6], before[6])
        self.assertAlmostEqual(nodes[1].position.x, 30.0)
        self.assertAlmostEqual(nodes[2].position.y, 70.0)
        self.assertAlmostEqual(nodes[4].position.y, 130.0)
        self.assertAlmostEqual(nodes[5].position.x, 30.0)

    def test_conflicting_multi_segment_proposals_fail_before_change_batch(self) -> None:
        module, _font, layer, _path, nodes = self._load_module(node_values=_two_cubic_nodes())
        before = _positions(nodes)
        reviewed = [
            {
                "ok": True,
                "eligible": True,
                "segmentEndNodeIndex": 3,
                "nodeIndices": {"handle1": 1, "handle2": 2},
                "proposed": {
                    "handle1": {"x": 30.0, "y": 0.0},
                    "handle2": {"x": 100.0, "y": 70.0},
                },
            },
            {
                "ok": True,
                "eligible": True,
                "segmentEndNodeIndex": 6,
                "nodeIndices": {"handle1": 2, "handle2": 5},
                "proposed": {
                    "handle1": {"x": 90.0, "y": 80.0},
                    "handle2": {"x": 30.0, "y": 200.0},
                },
            },
        ]
        with mock.patch.object(module, "_analyze_tunni_target", return_value=reviewed):
            payload = json.loads(
                asyncio.run(
                    module.apply_tunni_balance(
                        glyph_name="A",
                        master_id="m1",
                        path_index=0,
                        segment_end_node_indices=[3, 6],
                        confirm=True,
                    )
                )
            )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errorCode"], "invalid_current_proposal")
        self.assertEqual(payload["error"], "Conflicting proposals target node 2")
        self.assertEqual(payload["applied"], [])
        self.assertFalse(payload["rollback"]["attempted"])
        self.assertEqual(_positions(nodes), before)
        self.assertEqual((layer.begin_count, layer.end_count), (0, 0))

    def test_confirm_refuses_write_when_change_batch_methods_are_unavailable(self) -> None:
        for missing_method in ("beginChanges", "endChanges"):
            with self.subTest(missing_method=missing_method):
                module, _font, layer, _path, nodes = self._load_module()
                before = _positions(nodes)
                setattr(layer, missing_method, None)
                payload = json.loads(
                    asyncio.run(
                        module.apply_tunni_balance(
                            glyph_name="A",
                            master_id="m1",
                            path_index=0,
                            segment_end_node_indices=[3],
                            confirm=True,
                        )
                    )
                )

                self.assertFalse(payload["ok"])
                self.assertEqual(payload["errorCode"], "change_batch_unavailable")
                self.assertEqual(payload["applied"], [])
                self.assertFalse(payload["changeBatch"]["available"])
                self.assertEqual(_positions(nodes), before)
                self.assertEqual((layer.begin_count, layer.end_count), (0, 0))

    def test_begin_changes_exception_performs_no_write_or_unmatched_end(self) -> None:
        module, _font, layer, _path, nodes = self._load_module()
        before = _positions(nodes)
        layer.raise_begin_changes = True
        payload = json.loads(
            asyncio.run(
                module.apply_tunni_balance(
                    glyph_name="A",
                    master_id="m1",
                    path_index=0,
                    segment_end_node_indices=[3],
                    confirm=True,
                )
            )
        )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errorCode"], "begin_changes_failed")
        self.assertEqual(payload["applied"], [])
        self.assertFalse(payload["changeBatch"]["began"])
        self.assertFalse(payload["changeBatch"]["ended"])
        self.assertEqual(_positions(nodes), before)
        self.assertEqual((layer.begin_count, layer.end_count), (1, 0))

    def test_confirmed_balance_round_trip_has_equal_recomputed_ratios(self) -> None:
        module, _font, _layer, _path, _nodes_value = self._load_module()
        applied = json.loads(
            asyncio.run(
                module.apply_tunni_balance(
                    glyph_name="A",
                    master_id="m1",
                    path_index=0,
                    segment_end_node_indices=[3],
                    confirm=True,
                )
            )
        )
        reviewed = json.loads(
            asyncio.run(
                module.review_tunni_geometry(
                    glyph_name="A",
                    master_id="m1",
                    path_index=0,
                    segment_end_node_indices=[3],
                )
            )
        )

        self.assertTrue(applied["ok"])
        segment = reviewed["segments"][0]
        self.assertAlmostEqual(segment["ratios"]["start"], 0.3, places=12)
        self.assertAlmostEqual(segment["ratios"]["end"], 0.3, places=12)
        self.assertAlmostEqual(segment["relativeImbalance"], 0.0, places=12)
        self.assertFalse(segment["eligible"])
        self.assertEqual(segment["reason"], "below_imbalance_threshold")

    def test_failed_readback_rolls_back_entire_path(self) -> None:
        module, _font, layer, _path, nodes = self._load_module()
        before = _positions(nodes)
        nodes[2].ignore_next_write = True
        payload = json.loads(
            asyncio.run(
                module.apply_tunni_balance(
                    glyph_name="A",
                    master_id="m1",
                    path_index=0,
                    segment_end_node_indices=[3],
                    confirm=True,
                )
            )
        )

        self.assertFalse(payload["ok"])
        self.assertTrue(payload["rollback"]["attempted"])
        self.assertTrue(payload["rollback"]["succeeded"])
        self.assertEqual(_positions(nodes), before)
        self.assertEqual((layer.begin_count, layer.end_count), (1, 1))

    def test_write_exception_rolls_back_and_ends_change_batch(self) -> None:
        module, _font, layer, _path, nodes = self._load_module()
        before = _positions(nodes)
        nodes[2].raise_next_write = True
        payload = json.loads(
            asyncio.run(
                module.apply_tunni_balance(
                    glyph_name="A",
                    master_id="m1",
                    path_index=0,
                    segment_end_node_indices=[3],
                    confirm=True,
                )
            )
        )

        self.assertFalse(payload["ok"])
        self.assertTrue(payload["rollback"]["succeeded"])
        self.assertEqual(_positions(nodes), before)
        self.assertEqual((layer.begin_count, layer.end_count), (1, 1))

    def test_end_changes_failure_rolls_back_all_positions(self) -> None:
        module, _font, layer, _path, nodes = self._load_module()
        before = _positions(nodes)
        layer.raise_end_changes = True
        payload = json.loads(
            asyncio.run(
                module.apply_tunni_balance(
                    glyph_name="A",
                    master_id="m1",
                    path_index=0,
                    segment_end_node_indices=[3],
                    confirm=True,
                )
            )
        )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errorCode"], "end_changes_failed")
        self.assertEqual(payload["applied"], [])
        self.assertTrue(payload["rollback"]["attempted"])
        self.assertTrue(payload["rollback"]["succeeded"])
        self.assertEqual(payload["rollback"]["errors"], [])
        self.assertTrue(payload["changeBatch"]["began"])
        self.assertFalse(payload["changeBatch"]["ended"])
        self.assertEqual(_positions(nodes), before)
        self.assertEqual((layer.begin_count, layer.end_count), (1, 1))

    def test_persistent_rollback_write_failure_is_reported(self) -> None:
        module, _font, layer, _path, nodes = self._load_module()
        before = _positions(nodes)
        layer.raise_end_changes = True
        nodes[1].raise_from_write = 2
        payload = json.loads(
            asyncio.run(
                module.apply_tunni_balance(
                    glyph_name="A",
                    master_id="m1",
                    path_index=0,
                    segment_end_node_indices=[3],
                    confirm=True,
                )
            )
        )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errorCode"], "end_changes_failed")
        self.assertEqual(payload["applied"], [])
        self.assertTrue(payload["rollback"]["attempted"])
        self.assertFalse(payload["rollback"]["succeeded"])
        self.assertTrue(
            any(error.get("nodeIndex") == 1 for error in payload["rollback"]["errors"])
        )
        self.assertNotEqual(_positions(nodes)[1], before[1])
        self.assertEqual(_positions(nodes)[0], before[0])
        self.assertEqual(_positions(nodes)[2:], before[2:])
        self.assertEqual((layer.begin_count, layer.end_count), (1, 1))

    def test_glyphs4_shapes_report_shape_index(self) -> None:
        module, _font, _layer, _path, _nodes_value = self._load_module(glyphs4=True)
        payload = json.loads(
            asyncio.run(
                module.review_tunni_geometry(
                    glyph_name="A", master_id="m1", path_index=0, segment_end_node_indices=[3]
                )
            )
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["target"]["shapeIndex"], 1)
        self.assertEqual(payload["target"]["omittedComponentCount"], 1)

    def test_glyphs3_and_glyphs4_reviews_match(self) -> None:
        module3, _font3, _layer3, _path3, _nodes3 = self._load_module(glyphs4=False)
        module4, _font4, _layer4, _path4, _nodes4 = self._load_module(glyphs4=True)
        args = {"glyph_name": "A", "master_id": "m1", "path_index": 0, "segment_end_node_indices": [3]}

        result3 = json.loads(asyncio.run(module3.review_tunni_geometry(**args)))
        result4 = json.loads(asyncio.run(module4.review_tunni_geometry(**args)))

        self.assertEqual(result3["segments"], result4["segments"])
        self.assertEqual(result3["summary"], result4["summary"])

    def test_glyphs3_paths_and_glyphs4_mixed_shapes_apply_and_quality_match(self) -> None:
        module3, _font3, layer3, _path3, nodes3 = self._load_module(glyphs4=False)
        module4, _font4, layer4, _path4, nodes4 = self._load_module(glyphs4=True)
        target = {"glyph_name": "A", "master_id": "m1", "path_index": 0}

        quality3 = json.loads(asyncio.run(module3.review_curve_quality(**target, include_samples=True)))
        quality4 = json.loads(asyncio.run(module4.review_curve_quality(**target, include_samples=True)))
        apply3 = json.loads(
            asyncio.run(module3.apply_tunni_balance(**target, segment_end_node_indices=[3], confirm=True))
        )
        apply4 = json.loads(
            asyncio.run(module4.apply_tunni_balance(**target, segment_end_node_indices=[3], confirm=True))
        )

        self.assertEqual(quality3["segments"], quality4["segments"])
        self.assertEqual(quality3["joins"], quality4["joins"])
        self.assertEqual(quality3["summary"], quality4["summary"])
        self.assertEqual(apply3["planned"], apply4["planned"])
        self.assertEqual(apply3["applied"], apply4["applied"])
        self.assertEqual(_positions(nodes3), _positions(nodes4))
        self.assertEqual((layer3.begin_count, layer3.end_count), (1, 1))
        self.assertEqual((layer4.begin_count, layer4.end_count), (1, 1))

    def test_curve_quality_returns_metrics_and_warnings_without_mutation(self) -> None:
        module, _font, _layer, _path, nodes = self._load_module()
        before = _positions(nodes)
        payload = json.loads(
            asyncio.run(
                module.review_curve_quality(
                    glyph_name="A",
                    master_id="m1",
                    path_index=0,
                    include_samples=True,
                )
            )
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["geometryDataVersion"], 1)
        self.assertEqual(payload["params"]["samplesPerCurve"], 51)
        self.assertEqual(len(payload["segments"][0]["samples"]), 51)
        self.assertEqual(_positions(nodes), before)

    def test_curve_quality_public_samples_match_exact_parabola(self) -> None:
        parabola_nodes = [
            _Node(0.0, 0.0, "line"),
            _Node(1.0 / 3.0, 0.0, "offcurve"),
            _Node(2.0 / 3.0, 1.0 / 3.0, "offcurve"),
            _Node(1.0, 1.0, "curve"),
        ]
        module, _font, _layer, _path, _nodes_value = self._load_module(
            node_values=parabola_nodes,
            upm=1000,
        )
        payload = json.loads(
            asyncio.run(
                module.review_curve_quality(
                    glyph_name="A",
                    master_id="m1",
                    path_index=0,
                    samples_per_curve=9,
                    include_samples=True,
                )
            )
        )

        self.assertTrue(payload["ok"])
        for sample in payload["segments"][0]["samples"]:
            t = sample["t"]
            expected = 2.0 / ((1.0 + 4.0 * t * t) ** 1.5)
            self.assertAlmostEqual(sample["x"], t, places=14)
            self.assertAlmostEqual(sample["y"], t * t, places=14)
            self.assertAlmostEqual(sample["curvature"], expected, places=13)
            self.assertAlmostEqual(sample["normalizedCurvature"], expected * 1000.0, places=10)

    def test_sample_detail_limit_fails_before_analysis(self) -> None:
        module, _font, _layer, _path, _nodes_value = self._load_module()
        payload = json.loads(
            asyncio.run(
                module.review_curve_quality(
                    glyph_name="A",
                    master_id="m1",
                    path_index=0,
                    segment_end_node_indices=list(range(65)),
                    include_samples=True,
                )
            )
        )
        self.assertFalse(payload["ok"])
        self.assertIn("64", payload["error"])


if __name__ == "__main__":
    unittest.main()
