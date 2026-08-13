"""Behavioral tests for deterministic cyclic path alignment."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


RESOURCES = (
    Path(__file__).resolve().parent.parent
    / "Glyphs MCP.glyphsPlugin"
    / "Contents"
    / "Resources"
)


def _load_engine():
    path = RESOURCES / "cyclic_path_alignment_engine.py"
    spec = importlib.util.spec_from_file_location("cyclic_path_alignment_engine_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _node(x, y, kind="line", smooth=False):
    return {"x": float(x), "y": float(y), "type": kind, "smooth": bool(smooth)}


def _path(master_id, points, *, rotation=0, closed=True, direction=1):
    nodes = [_node(x, y) for x, y in points]
    if rotation:
        nodes = nodes[rotation:] + nodes[:rotation]
    return {"masterId": master_id, "closed": closed, "direction": direction, "nodes": nodes}


SQUARE = [(0, 0), (100, 0), (100, 100), (0, 100)]


class CyclicPathAlignmentEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = _load_engine()

    def test_joint_alignment_finds_one_semantic_landmark_across_many_masters(self) -> None:
        paths = [
            _path("M1", SQUARE),
            _path("M2", [(20, 30), (220, 30), (220, 230), (20, 230)], rotation=2),
            _path("M3", [(0, 0), (50, 0), (50, 150), (0, 150)], rotation=1),
        ]

        result = self.engine.plan_joint_alignment(
            paths,
            reference_master_id="M1",
            reference_node_index=0,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "ready")
        self.assertEqual(
            {item["masterId"]: item["proposedStartNodeIndex"] for item in result["masters"]},
            {"M1": 0, "M2": 2, "M3": 3},
        )
        self.assertEqual(result["summary"]["rotationCount"], 2)

    def test_master_order_does_not_change_the_joint_plan(self) -> None:
        paths = [_path("B", SQUARE, rotation=2), _path("A", SQUARE)]
        first = self.engine.plan_joint_alignment(paths, reference_master_id="A", reference_node_index=0)
        second = self.engine.plan_joint_alignment(reversed(paths), reference_master_id="A", reference_node_index=0)
        self.assertEqual(first, second)

    def test_all_aligned_is_a_verified_noop(self) -> None:
        result = self.engine.plan_joint_alignment(
            [_path("M1", SQUARE), _path("M2", SQUARE)],
            reference_master_id="M1",
            reference_node_index=3,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "already_aligned")
        self.assertEqual(result["summary"]["rotationCount"], 0)

    def test_open_path_and_offcurve_reference_fail_closed(self) -> None:
        open_result = self.engine.plan_joint_alignment(
            [_path("M1", SQUARE, closed=False)],
            reference_master_id="M1",
            reference_node_index=0,
        )
        cubic = {
            "masterId": "M1",
            "closed": True,
            "direction": 1,
            "nodes": [
                _node(0, 0, "curve"),
                _node(30, 0, "offcurve"),
                _node(70, 100, "offcurve"),
                _node(100, 100, "curve"),
            ],
        }
        offcurve_result = self.engine.plan_joint_alignment(
            [cubic],
            reference_master_id="M1",
            reference_node_index=1,
        )
        self.assertEqual(open_result["errorType"], "open_path")
        self.assertEqual(offcurve_result["errorType"], "reference_node_not_oncurve")

    def test_incompatible_cyclic_types_are_blocked(self) -> None:
        reference = _path("M1", SQUARE)
        incompatible = _path("M2", SQUARE)
        incompatible["nodes"][2]["type"] = "curve"
        result = self.engine.plan_joint_alignment(
            [reference, incompatible],
            reference_master_id="M1",
            reference_node_index=0,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["errorType"], "path_topology_mismatch")

    def test_heterogeneous_node_types_keep_one_canonical_cyclic_phase(self) -> None:
        reference_nodes = [
            _node(0, 0, "curve"),
            _node(30, 0, "offcurve"),
            _node(70, 0, "offcurve"),
            _node(100, 100, "curve"),
            _node(0, 100, "line"),
        ]
        target_nodes = [
            _node(20, 30, "curve"),
            _node(80, 30, "offcurve"),
            _node(160, 30, "offcurve"),
            _node(220, 230, "curve"),
            _node(20, 230, "line"),
        ]
        target_nodes = target_nodes[3:] + target_nodes[:3]
        result = self.engine.plan_joint_alignment(
            [
                {"masterId": "M1", "closed": True, "direction": 1, "nodes": reference_nodes},
                {"masterId": "M2", "closed": True, "direction": 1, "nodes": target_nodes},
            ],
            reference_master_id="M1",
            reference_node_index=0,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(
            {item["masterId"]: item["proposedStartNodeIndex"] for item in result["masters"]},
            {"M1": 0, "M2": 2},
        )
        for item in result["masters"]:
            rotated = item["proposedStartNodeIndex"]
            source = reference_nodes if item["masterId"] == "M1" else target_nodes
            types = [node["type"] for node in source]
            self.assertEqual(types[rotated:] + types[:rotated], result["canonicalNodeTypes"])

    def test_missing_semantic_landmark_is_blocked(self) -> None:
        diamond = [(0, 50), (50, 0), (100, 50), (50, 100)]
        result = self.engine.plan_joint_alignment(
            [_path("M1", SQUARE), _path("M2", diamond)],
            reference_master_id="M1",
            reference_node_index=0,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["errorType"], "semantic_conflict")

    def test_duplicate_semantic_landmark_is_blocked(self) -> None:
        repeated = SQUARE + SQUARE
        result = self.engine.plan_joint_alignment(
            [_path("M1", SQUARE), _path("M2", repeated)],
            reference_master_id="M1",
            reference_node_index=0,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["errorType"], "path_topology_mismatch")

        ambiguous_reference = _path("M1", repeated)
        ambiguous_target = _path("M2", repeated, rotation=1)
        ambiguous = self.engine.plan_joint_alignment(
            [ambiguous_reference, ambiguous_target],
            reference_master_id="M1",
            reference_node_index=0,
        )
        self.assertFalse(ambiguous["ok"])
        self.assertEqual(ambiguous["errorType"], "landmark_ambiguous")

    def test_contour_direction_conflict_is_blocked(self) -> None:
        result = self.engine.plan_joint_alignment(
            [_path("M1", SQUARE, direction=1), _path("M2", SQUARE, direction=-1)],
            reference_master_id="M1",
            reference_node_index=0,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["errorType"], "contour_direction_mismatch")


if __name__ == "__main__":
    unittest.main()
