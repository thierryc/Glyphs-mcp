"""Versioned read-only geometry contract used by the desktop glyph diff."""

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src/protocol"))
sys.path.insert(0, str(ROOT / "src/sidecar"))

from glyphs_mcp_sidecar import glyph_diff_worker as worker
from glyphs_mcp_protocol.geometry import comparison


class FakePath:
    def __init__(self, elements):
        self.elements = elements

    def elementCount(self):
        return len(self.elements)

    def elementAtIndex_associatedPoints_(self, index):
        return self.elements[index]


def point(x, y):
    return SimpleNamespace(x=x, y=y)


class GlyphDiffWorkerTests(unittest.TestCase):
    def test_layer_serializes_decomposed_closed_and_open_geometry(self):
        master = SimpleNamespace(name="Regular", ascender=810, capHeight=710, xHeight=510, descender=-210)
        layer = SimpleNamespace(
            layerId="MASTER-1",
            name="Regular",
            master=master,
            isMasterLayer=True,
            completeBezierPath=FakePath([(0, [point(0, 0)]), (1, [point(100, 0)]), (3, [])]),
            completeOpenBezierPath=FakePath([(0, [point(20, 20)]), (2, [point(30, 40), point(50, 60), point(70, 80)])]),
            anchors=[SimpleNamespace(name="top", position=point(50, 700))],
            width=620,
        )
        value = worker._layer(layer)
        self.assertEqual(value["label"], "Regular")
        self.assertTrue(value["isMaster"])
        self.assertEqual(value["outline"][-1], {"kind": 3, "points": []})
        self.assertEqual(value["openOutline"][-1]["points"], [[30.0, 40.0], [50.0, 60.0], [70.0, 80.0]])
        self.assertEqual(value["anchors"], {"top": [50.0, 700.0]})
        self.assertEqual(value["width"], 620.0)
        self.assertEqual(value["metrics"]["capHeight"], 710.0)
        self.assertEqual(value["bounds"], [0.0, 0.0, 100.0, 80.0])

    def test_contract_marks_changed_added_deleted_and_special_layers(self):
        unchanged = {"id": "regular", "label": "Regular", "isMaster": True, "outline": [],
                     "openOutline": [], "anchors": {}, "width": 600, "metrics": {}}
        changed_before = {**unchanged, "id": "bold", "label": "Bold", "width": 700}
        changed_after = {**changed_before, "width": 710}
        deleted = {**unchanged, "id": "deleted", "label": "Brace 100"}
        added = {**unchanged, "id": "added", "label": "[100]"}
        snapshots = [
            {"missingGlyph": False, "glyphName": "A", "layers": [unchanged, changed_before, deleted]},
            {"missingGlyph": False, "glyphName": "A", "layers": [unchanged, changed_after, added]},
        ]
        with mock.patch.object(worker, "_snapshot", side_effect=snapshots):
            value = worker.run({})
        self.assertEqual(value["schemaVersion"], 2)
        self.assertEqual(value["changedLayerIDs"], ["bold", "added", "deleted"])
        self.assertEqual(value["before"]["glyphName"], "A")
        self.assertEqual(value["after"]["glyphName"], "A")
        self.assertEqual([item["id"] for item in value["differences"]],
                         ["regular", "bold", "added", "deleted"])
        self.assertFalse(value["differences"][0]["hasVisibleDifference"])
        self.assertTrue(value["differences"][1]["hasVisibleDifference"])
        self.assertEqual(value["differences"][1]["regions"][0]["kind"], "width")

    def test_missing_side_represents_added_or_deleted_glyph(self):
        with mock.patch.object(worker, "_snapshot", side_effect=[
            {"missingGlyph": True, "glyphName": None, "layers": []},
            {"missingGlyph": False, "glyphName": "A", "layers": [
                {"id": "regular", "label": "Regular", "isMaster": True, "outline": [],
                 "openOutline": [], "anchors": {}, "width": 600, "metrics": {}}
            ]},
        ]):
            value = worker.run({})
        self.assertEqual(value["changedLayerIDs"], ["regular"])

    def test_delta_contract_localizes_changed_segments_and_anchors(self):
        before = {
            "id": "regular", "label": "Regular", "isMaster": True,
            "outline": [
                {"kind": 0, "points": [[0, 0]]},
                {"kind": 1, "points": [[100, 0]]},
                {"kind": 1, "points": [[100, 100]]},
                {"kind": 3, "points": []},
            ],
            "openOutline": [], "anchors": {"top": [50, 100]}, "width": 500,
            "metrics": {},
        }
        after = {
            **before,
            "outline": [
                {"kind": 0, "points": [[0, 0]]},
                {"kind": 1, "points": [[100, 0]]},
                {"kind": 1, "points": [[110, 100]]},
                {"kind": 3, "points": []},
            ],
            "anchors": {"top": [60, 100]},
        }
        value = worker._difference("regular", "Regular", before, after)
        self.assertTrue(value["hasVisibleDifference"])
        self.assertEqual(len(value["referenceSegments"]), 2)
        self.assertEqual(len(value["currentSegments"]), 2)
        self.assertEqual(value["anchors"][0]["name"], "top")
        self.assertEqual([region["kind"] for region in value["regions"]],
                         ["geometry", "anchor"])

    def test_changed_segment_regions_merge_and_sort_top_to_bottom(self):
        before = {
            "outline": [],
            "openOutline": [
                [0, [[0, 0]]], [1, [[100, 0]]],
                [0, [[0, 500]]], [1, [[100, 500]]],
            ],
            "anchors": {}, "width": 600,
        }
        after = {
            **before,
            "openOutline": [
                [0, [[0, 0]]], [1, [[100, 20]]],
                [0, [[0, 500]]], [1, [[100, 520]]],
            ],
        }
        regions = comparison(before, after)["regions"]
        self.assertEqual([value["kind"] for value in regions], ["geometry", "geometry"])
        self.assertGreater(regions[0]["bounds"][1], regions[1]["bounds"][1])
        self.assertEqual([value["id"] for value in regions], ["difference-1", "difference-2"])

    def test_added_and_deleted_contours_are_entirely_changed(self):
        square = [
            [0, [[0, 0]]], [1, [[100, 0]]], [1, [[100, 100]]],
            [1, [[0, 100]]], [3, []],
        ]
        empty = {"outline": [], "openOutline": [], "anchors": {}, "width": None}
        added = comparison(empty, {**empty, "outline": square, "width": 120})
        deleted = comparison({**empty, "outline": square, "width": 120}, empty)
        self.assertEqual(len(added["currentSegments"]), 4)
        self.assertEqual(added["referenceSegments"], [])
        self.assertEqual(len(deleted["referenceSegments"]), 4)
        self.assertEqual(deleted["currentSegments"], [])
        self.assertEqual(added["currentOutline"], square)
        self.assertEqual(deleted["referenceOutline"], square)


if __name__ == "__main__":
    unittest.main()
