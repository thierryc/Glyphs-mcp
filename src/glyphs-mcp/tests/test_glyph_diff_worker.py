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
from glyphs_mcp_protocol.geometry import comparison, glyphs_path_elements


class FakePath:
    def __init__(self, elements):
        self.elements = elements

    def elementCount(self):
        return len(self.elements)

    def elementAtIndex_associatedPoints_(self, index):
        return self.elements[index]


def point(x, y):
    return SimpleNamespace(x=x, y=y)


class FakeSegment(list):
    def __init__(self, kind, *points):
        super().__init__(points)
        self.type = kind


class FakeNativeSegment:
    def __init__(self, kind, *points):
        self.type = kind
        self.countOfPoints = len(points)
        self._points = points

    def __getitem__(self, index):
        if index >= len(self._points):
            raise AssertionError("the serializer must honor countOfPoints")
        return self._points[index]


class FakeGSPath:
    def __init__(self, segments, closed=True):
        self.segments = segments
        self.closed = closed


class FakeLayer(SimpleNamespace):
    def copy(self):
        return FakeLayer(paths=list(self.closed_paths))

    def flattenOutlines(self):
        self.paths = list(self.paths)

    def copyDecomposedLayer(self):
        return FakeLayer(paths=list(self.open_paths))


class GlyphDiffWorkerTests(unittest.TestCase):
    def test_layer_serializes_decomposed_closed_and_open_geometry(self):
        master = SimpleNamespace(name="Regular", ascender=810, capHeight=710, xHeight=510, descender=-210)
        closed = FakeGSPath([
            FakeSegment("line", point(0, 0), point(100, 0)),
            FakeSegment("line", point(100, 0), point(0, 0)),
        ])
        opened = FakeGSPath([
            FakeSegment("curve", point(20, 20), point(30, 40), point(50, 60), point(70, 80)),
        ], closed=False)
        component_path = FakeGSPath([
            FakeSegment("line", point(40, 600), point(80, 700)),
            FakeSegment("line", point(80, 700), point(40, 600)),
        ])
        layer = FakeLayer(
            layerId="MASTER-1",
            name="Regular",
            master=master,
            isMasterLayer=True,
            closed_paths=[closed],
            open_paths=[opened],
            components=[SimpleNamespace(
                componentName="acute",
                decomposedPathsRemovingOverlap_=lambda _: [component_path],
            )],
            anchors=[SimpleNamespace(name="top", position=point(50, 700))],
            width=620,
        )
        value = worker._layer(layer)
        self.assertEqual(value["label"], "Regular")
        self.assertTrue(value["isMaster"])
        self.assertEqual(value["outline"][-1], {"kind": 3, "points": []})
        self.assertEqual(value["openOutline"][-1]["points"], [[30.0, 40.0], [50.0, 60.0], [70.0, 80.0]])
        self.assertEqual(value["componentOutlines"], [[
            {"kind": 0, "points": [[40.0, 600.0]]},
            {"kind": 1, "points": [[80.0, 700.0]]},
            {"kind": 1, "points": [[40.0, 600.0]]},
            {"kind": 3, "points": []},
        ]])
        self.assertEqual(value["anchors"], {"top": [50.0, 700.0]})
        self.assertEqual(value["width"], 620.0)
        self.assertEqual(value["metrics"]["capHeight"], 710.0)
        self.assertEqual(value["bounds"], [0.0, 0.0, 100.0, 700.0])
        self.assertEqual(value["warnings"], [])

    def test_layer_uses_ref_shapes_for_component_outlines(self):
        component = SimpleNamespace(
            componentName="A",
            decomposedPathsRemovingOverlap_=lambda _: [FakeGSPath([
                FakeSegment("line", point(0, 0), point(100, 0)),
                FakeSegment("line", point(100, 0), point(0, 0)),
            ])],
        )
        layer = SimpleNamespace(shapes=[SimpleNamespace(nodes=[]), component])
        outlines, warnings = worker._component_outlines(layer)
        self.assertEqual(outlines, [[
            {"kind": 0, "points": [[0.0, 0.0]]},
            {"kind": 1, "points": [[100.0, 0.0]]},
            {"kind": 1, "points": [[0.0, 0.0]]},
            {"kind": 3, "points": []},
        ]])
        self.assertEqual(warnings, [])

    def test_open_path_and_component_failures_are_nonfatal_layer_warnings(self):
        closed = FakeGSPath([
            FakeSegment("line", point(0, 0), point(100, 0)),
            FakeSegment("line", point(100, 0), point(0, 0)),
        ])
        master = SimpleNamespace(name="Regular", ascender=800, capHeight=700,
                                 xHeight=500, descender=-200)
        layer = FakeLayer(
            layerId="MASTER-1", name="Regular", master=master, isMasterLayer=True,
            closed_paths=[closed], open_paths=[], anchors=[], width=500,
            components=[SimpleNamespace(
                componentName="broken",
                decomposedPathsRemovingOverlap_=lambda _: (_ for _ in ()).throw(RuntimeError("boom")),
            )],
        )
        layer.copyDecomposedLayer = lambda: (_ for _ in ()).throw(RuntimeError("boom"))

        value = worker._layer(layer)

        self.assertTrue(value["outline"])
        self.assertEqual(value["openOutline"], [])
        self.assertEqual(value["componentOutlines"], [])
        self.assertEqual([warning["scope"] for warning in value["warnings"]],
                         ["openPaths", "component"])

    def test_closed_outline_failure_remains_fatal(self):
        layer = SimpleNamespace(copy=lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        with self.assertRaisesRegex(ValueError, "flattened safely"):
            from glyphs_mcp_protocol.geometry import resolved_closed_layer_elements
            resolved_closed_layer_elements(layer, context="layer 'Regular'")

    def test_quadratic_segments_emit_implied_midpoint_elements(self):
        path = FakeGSPath([
            FakeSegment("qcurve", point(10, 20), point(30, 40), point(50, 80), point(90, 100)),
        ], closed=False)
        self.assertEqual(glyphs_path_elements([path]), [
            [0, [[10.0, 20.0]]],
            [4, [[30.0, 40.0], [40.0, 60.0]]],
            [4, [[50.0, 80.0], [90.0, 100.0]]],
        ])

    def test_native_segments_use_count_instead_of_unbounded_iteration(self):
        path = FakeGSPath([
            FakeNativeSegment("qcurve", point(0, 0), point(50, 100), point(100, 0)),
        ], closed=False)
        self.assertEqual(glyphs_path_elements([path]), [
            [0, [[0.0, 0.0]]],
            [4, [[50.0, 100.0], [100.0, 0.0]]],
        ])

    def test_unknown_segment_reports_context(self):
        with self.assertRaisesRegex(ValueError, "test outline.*unsupported segment"):
            glyphs_path_elements([
                FakeGSPath([FakeSegment("arc", point(0, 0), point(10, 10))])
            ], context="test outline")

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
        self.assertEqual(value["schemaVersion"], 3)
        self.assertEqual(value["protocolAPIVersion"], 1)
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

    def test_reordered_contours_are_not_reported_as_changed(self):
        first = [
            [0, [[0, 0]]], [1, [[100, 0]]], [1, [[100, 100]]],
            [1, [[0, 100]]], [3, []],
        ]
        second = [
            [0, [[200, 0]]], [1, [[300, 0]]], [1, [[300, 100]]],
            [1, [[200, 100]]], [3, []],
        ]
        base = {"openOutline": [], "anchors": {}, "width": 400}
        value = comparison({**base, "outline": first + second},
                           {**base, "outline": second + first})
        self.assertFalse(value["hasVisibleDifference"])
        self.assertEqual(value["referenceSegments"], [])
        self.assertEqual(value["currentSegments"], [])

    def test_inserted_contour_does_not_mark_existing_contour_changed(self):
        original = [
            [0, [[0, 0]]], [1, [[100, 0]]], [1, [[100, 100]]],
            [1, [[0, 100]]], [3, []],
        ]
        inserted = [
            [0, [[200, 0]]], [1, [[260, 0]]], [1, [[260, 60]]],
            [1, [[200, 60]]], [3, []],
        ]
        base = {"openOutline": [], "anchors": {}, "width": 400}
        value = comparison({**base, "outline": original},
                           {**base, "outline": inserted + original})
        self.assertEqual(value["referenceSegments"], [])
        self.assertEqual(len(value["currentSegments"]), 4)
        self.assertTrue(all(point[0] >= 200 for segment in value["currentSegments"]
                            for point in segment[1]))


if __name__ == "__main__":
    unittest.main()
