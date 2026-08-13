from __future__ import annotations

import asyncio
import copy
import importlib.util
import inspect
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
sys.path.insert(0, str(RESOURCES))


class _MCP:
    def tool(self):
        return lambda function: function


def _snapshot():
    return {
        "paths": [
            {
                "closed": False,
                "nodes": [
                    {"x": 0.0, "y": 0.0, "type": "line", "smooth": False},
                    {"x": 20.0, "y": 0.0, "type": "offcurve", "smooth": False},
                    {"x": 100.0, "y": 60.0, "type": "offcurve", "smooth": False},
                    {"x": 100.0, "y": 100.0, "type": "curve", "smooth": True},
                ],
            }
        ],
        "components": [],
        "anchors": [],
        "shapeOrder": [{"kind": "path", "index": 0}],
        "width": 400.0,
        "protected": {"hints": [], "guides": [], "annotations": []},
    }


def _gee_gee_a_snapshot():
    node_counts = [20, 4, 24, 24]
    node_types = ["line", "offcurve", "offcurve", "curve"]
    paths = []
    for path_index, node_count in enumerate(node_counts):
        nodes = []
        for node_index in range(node_count):
            node_type = node_types[(path_index + node_index) % len(node_types)]
            nodes.append(
                {
                    "x": float(path_index * 300 + node_index * 10),
                    "y": float((node_index % 5) * 100),
                    "type": node_type,
                    "smooth": node_type == "curve",
                    "protected": {"name": None, "userData": {}},
                }
            )
        paths.append(
            {
                "closed": True,
                "nodes": nodes,
                "protected": {"attributes": {}, "userData": {}},
            }
        )
    return {
        "paths": paths,
        "components": [],
        "anchors": [
            {"name": "bottom", "x": 500.0, "y": 0.0},
            {"name": "ogonek", "x": 120.0, "y": -80.0},
            {"name": "top", "x": 520.0, "y": 1400.0},
        ],
        "shapeOrder": [{"kind": "path", "index": index} for index in range(4)],
        "width": 1025.0,
        "protected": {"hints": [], "guides": [], "annotations": [], "userData": {}},
    }


class _FixturePoint:
    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)


class _FixtureNode:
    def __init__(self, data):
        self.position = _FixturePoint(data["x"], data["y"])
        self.type = data["type"]
        self.smooth = bool(data.get("smooth"))
        protected = data.get("protected") or {}
        self.name = protected.get("name")
        self.userData = copy.deepcopy(protected.get("userData") or {})


class _FixturePath:
    def __init__(self, data):
        self.closed = bool(data.get("closed"))
        self.nodes = [_FixtureNode(item) for item in data.get("nodes") or []]
        protected = data.get("protected") or {}
        self.attributes = copy.deepcopy(protected.get("attributes") or {})
        self.userData = copy.deepcopy(protected.get("userData") or {})


class _FixtureAnchor:
    def __init__(self, data):
        self.name = data["name"]
        self.position = _FixturePoint(data["x"], data["y"])


class _FixtureLayer:
    def __init__(self, snapshot, layer_id):
        self.paths = [_FixturePath(item) for item in snapshot.get("paths") or []]
        self.components = []
        self.anchors = [_FixtureAnchor(item) for item in snapshot.get("anchors") or []]
        self.shapes = list(self.paths)
        self.hints = []
        self.guides = []
        self.annotations = []
        self.userData = copy.deepcopy((snapshot.get("protected") or {}).get("userData") or {})
        self.width = float(snapshot.get("width", 0.0))
        self.layerId = layer_id
        self.associatedMasterId = layer_id
        self.name = layer_id
        self.parent = None


class OutlineCandidateWrapperContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "glyphs_mcp_test_outline_candidates",
            RESOURCES / "mcp_tools_outline_candidates.py",
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        helper_stub = types.SimpleNamespace(
            _font_resolution_error=lambda *args, **kwargs: {"ok": False, "error": "font"},
            _get_layer_id=lambda layer: getattr(layer, "layerId", None),
            _glyphs_show_layer_link_fields=lambda *args, **kwargs: {},
            _layer_components=lambda layer: list(getattr(layer, "components", []) or []),
            _layer_paths=lambda layer: list(getattr(layer, "paths", []) or []),
            _normalized_node_type=lambda node: getattr(node, "type", "line"),
            _resolve_font_by_index=lambda *args: (None, []),
            _run_on_main_thread=lambda callback: callback(),
            _safe_json=json.dumps,
        )
        with mock.patch.dict(
            sys.modules,
            {
                "GlyphsApp": types.SimpleNamespace(Glyphs=types.SimpleNamespace()),
                "mcp_runtime": types.SimpleNamespace(mcp=_MCP()),
                "tool_registration": types.SimpleNamespace(glyphs_tool=lambda *_args, **_kwargs: (lambda fn: fn)),
                "mcp_tool_helpers": helper_stub,
                "mcp_tools_compensated_tuning": types.SimpleNamespace(),
                "mcp_tools_curve_geometry": types.SimpleNamespace(_normalize_grid_policy=lambda value: (value, None)),
                "mcp_tools_italic": types.SimpleNamespace(),
            },
        ):
            spec.loader.exec_module(module)
        cls.module = module

    def _entry(self, operation="tunni"):
        source = _snapshot()
        candidate = copy.deepcopy(source)
        candidate["paths"][0]["nodes"][1].update({"x": 30, "y": 0})
        return {
            "operation": operation,
            "candidate": candidate,
            "allowed": {"nodeCoordinates": [{"pathIndex": 0, "nodeIndex": 1}]},
        }

    def _italic_preview_with_candidate(self, candidate_snapshot):
        source_snapshot = _gee_gee_a_snapshot()
        source_layer = _FixtureLayer(source_snapshot, "roman")
        target_layer = _FixtureLayer(source_snapshot, "italic")
        candidate_layer = _FixtureLayer(candidate_snapshot, "candidate")
        glyph = types.SimpleNamespace(
            name="A",
            layers={"roman": source_layer, "italic": target_layer},
            parent=None,
        )
        source_layer.parent = glyph
        target_layer.parent = glyph
        candidate_layer.parent = glyph
        font = types.SimpleNamespace(
            filepath=None,
            upm=2048,
            glyphs={"A": glyph},
            masters=[types.SimpleNamespace(id="italic", name="Thin Condensed Italic")],
        )
        glyph.parent = font
        review = {
            "ok": True,
            "readyToApply": True,
            "sourceFontIndex": 0,
            "targetFontIndex": 0,
            "sourceMasterId": "roman",
            "targetMasterId": "italic",
            "copyOptions": {"paths": True, "components": True, "anchors": True, "metrics": True},
            "angle": 12.0,
            "effectiveSlantMode": "balanced",
            "origin": 3,
            "curveStrength": 0.75,
            "stemCompensation": 1.0,
            "stemReview": None,
            "results": [{"status": "ok", "glyphName": "A", "outcome": "balanced_applied", "warnings": []}],
        }
        italic = self.module.mcp_tools_italic
        with mock.patch.multiple(
            italic,
            _review_italic_first_pass_impl=mock.Mock(return_value=review),
            _get_font=mock.Mock(return_value=font),
            _master_by_id=mock.Mock(return_value=font.masters[0]),
            _stem_values=mock.Mock(return_value={}),
            _glyph_lookup=mock.Mock(side_effect=lambda value, name: value.glyphs[name]),
            _layer_for_glyph=mock.Mock(side_effect=lambda value, master_id: value.layers[master_id]),
            _prepare_path_only_candidate=mock.Mock(
                return_value={"ok": True, "candidateLayer": candidate_layer}
            ),
            create=True,
        ):
            return self.module._italic_preview_impl(0, {})

    def test_tunni_allows_only_targeted_grid_coordinates(self):
        entry = self._entry()
        current = copy.deepcopy(entry["candidate"])
        current["paths"][0]["nodes"][1]["x"] = 31

        diffs, error = self.module._validate_candidate(entry, current, types.SimpleNamespace(gridLength=1.0))

        self.assertIsNone(error)
        self.assertEqual(diffs[0]["kind"], "node_coordinate")

    def test_tunni_rejects_untargeted_and_off_grid_manual_edits(self):
        entry = self._entry()
        untargeted = copy.deepcopy(entry["candidate"])
        untargeted["paths"][0]["nodes"][2]["x"] += 1
        _diffs, error = self.module._validate_candidate(entry, untargeted, types.SimpleNamespace(gridLength=1.0))
        self.assertEqual(error, "untargeted_handle_changed")

        off_grid = copy.deepcopy(entry["candidate"])
        off_grid["paths"][0]["nodes"][1]["x"] = 31.25
        _diffs, error = self.module._validate_candidate(entry, off_grid, types.SimpleNamespace(gridLength=1.0))
        self.assertEqual(error, "coordinate_off_grid")

    def test_conflicting_multi_target_handle_proposals_are_rejected(self):
        proposals = {}
        self.module._record_candidate_proposal(proposals, (0, 1), {"x": 30, "y": 0})
        self.module._record_candidate_proposal(proposals, (0, 1), {"x": 30.0, "y": 0.0})
        with self.assertRaisesRegex(ValueError, "conflicting_candidate_proposals"):
            self.module._record_candidate_proposal(proposals, (0, 1), {"x": 31, "y": 0})

    def test_display_paths_include_direction_without_changing_snapshots(self):
        path = types.SimpleNamespace(direction=-1)
        layer = types.SimpleNamespace(paths=[path])
        snapshot = _snapshot()

        display = self.module._display_paths_with_directions(layer, snapshot["paths"])

        self.assertEqual(display[0]["direction"], -1)
        self.assertNotIn("direction", snapshot["paths"][0])

    def test_failed_end_change_remains_available_for_rollback_pairing(self):
        class Layer:
            def __init__(self):
                self.calls = 0

            def endChanges(self):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("end failed once")

        layer = Layer()
        begun = [layer]
        with self.assertRaisesRegex(RuntimeError, "end failed once"):
            self.module._end_change_batches(begun)
        self.assertEqual(begun, [layer])
        self.module._end_change_batches(begun)
        self.assertEqual(begun, [])
        self.assertEqual(layer.calls, 2)

    def test_topology_and_component_smart_values_are_protected(self):
        entry = self._entry("italic_first_pass")
        entry["allowed"] = {"allNodeCoordinates": True, "allSmoothFlags": True, "anchors": True, "componentTransforms": True, "width": True}
        changed = copy.deepcopy(entry["candidate"])
        changed["paths"][0]["nodes"][0]["type"] = "curve"
        _diffs, error = self.module._validate_candidate(entry, changed, types.SimpleNamespace(gridLength=1.0))
        self.assertEqual(error, "topology_changed")

        entry["candidate"]["components"] = [{"name": "A", "transform": [1, 0, 0, 1, 0, 0], "smartValues": {"x": 1}, "alignment": False}]
        entry["candidate"]["shapeOrder"].append({"kind": "component", "index": 0})
        changed = copy.deepcopy(entry["candidate"])
        changed["components"][0]["smartValues"]["x"] = 2
        _diffs, error = self.module._validate_candidate(entry, changed, types.SimpleNamespace(gridLength=1.0))
        self.assertEqual(error, "operation_external_change")

    def test_gee_gee_a_balanced_coordinate_candidate_succeeds_after_anchor_reordering(self):
        candidate = copy.deepcopy(_gee_gee_a_snapshot())
        for path in candidate["paths"]:
            for node in path["nodes"]:
                node["x"] += 12.0
        candidate["anchors"] = [candidate["anchors"][1], candidate["anchors"][0], candidate["anchors"][2]]

        session, summaries = self._italic_preview_with_candidate(candidate)

        self.assertEqual(session["operation"], "italic_first_pass")
        self.assertEqual(session["expectedEntryCount"], 1)
        self.assertEqual(summaries[0]["outcome"], "balanced_applied")
        entry = session["entries"][0]
        self.assertEqual([len(path["nodes"]) for path in entry["source"]["paths"]], [20, 4, 24, 24])
        self.assertEqual([item["name"] for item in entry["source"]["anchors"]], ["bottom", "ogonek", "top"])
        self.assertEqual([item["name"] for item in entry["candidate"]["anchors"]], ["bottom", "ogonek", "top"])
        self.assertEqual(entry["candidate"]["paths"][0]["nodes"][0]["x"], 12.0)
        self.assertEqual(entry["sourceTopologyFingerprint"], entry["generatedTopologyFingerprint"])

    def test_first_topology_mismatch_covers_path_and_node_safety_fields(self):
        source = _gee_gee_a_snapshot()

        candidate = copy.deepcopy(source)
        candidate["paths"].pop()
        self.assertEqual(self.module._topology_mismatch(source, candidate)["field"], "paths.length")

        candidate = copy.deepcopy(source)
        candidate["paths"][0]["closed"] = False
        self.assertEqual(self.module._topology_mismatch(source, candidate)["field"], "paths[0].closed")

        candidate = copy.deepcopy(source)
        candidate["paths"][0]["nodes"].pop()
        self.assertEqual(self.module._topology_mismatch(source, candidate)["field"], "paths[0].types.length")

        candidate = copy.deepcopy(source)
        candidate["paths"][0]["nodes"][0]["type"] = "curve"
        self.assertEqual(self.module._topology_mismatch(source, candidate)["field"], "paths[0].types[0]")

        candidate = copy.deepcopy(source)
        candidate["paths"][0]["nodes"][0], candidate["paths"][0]["nodes"][1] = (
            candidate["paths"][0]["nodes"][1],
            candidate["paths"][0]["nodes"][0],
        )
        self.assertEqual(self.module._topology_mismatch(source, candidate)["field"], "paths[0].types[0]")

    def test_first_topology_mismatch_covers_components_and_shape_order(self):
        source = _gee_gee_a_snapshot()
        source["components"] = [
            {"name": "acute", "transform": [1, 0, 0, 1, 0, 0], "smartValues": {}, "alignment": False},
            {"name": "dotaccent", "transform": [1, 0, 0, 1, 0, 0], "smartValues": {}, "alignment": False},
        ]
        source["shapeOrder"] += [
            {"kind": "component", "index": 0},
            {"kind": "component", "index": 1},
        ]

        candidate = copy.deepcopy(source)
        candidate["components"].reverse()
        self.assertEqual(self.module._topology_mismatch(source, candidate)["field"], "componentNames[0]")

        candidate = copy.deepcopy(source)
        candidate["shapeOrder"][0], candidate["shapeOrder"][4] = (
            candidate["shapeOrder"][4],
            candidate["shapeOrder"][0],
        )
        self.assertEqual(self.module._topology_mismatch(source, candidate)["field"], "shapeOrder[0].kind")

    def test_first_topology_mismatch_covers_all_protected_metadata_scopes(self):
        source = _gee_gee_a_snapshot()

        candidate = copy.deepcopy(source)
        candidate["paths"][0]["nodes"][0]["protected"]["userData"]["role"] = "changed"
        self.assertEqual(
            self.module._topology_mismatch(source, candidate)["field"],
            "paths[0].nodeProtected[0].userData.role",
        )

        candidate = copy.deepcopy(source)
        candidate["paths"][0]["protected"]["attributes"]["group"] = "changed"
        self.assertEqual(
            self.module._topology_mismatch(source, candidate)["field"],
            "paths[0].pathProtected.attributes.group",
        )

        candidate = copy.deepcopy(source)
        candidate["protected"]["userData"]["owner"] = "changed"
        self.assertEqual(
            self.module._topology_mismatch(source, candidate)["field"],
            "protected.userData.owner",
        )

    def test_italic_anchor_alignment_requires_unique_identical_names(self):
        source = _gee_gee_a_snapshot()
        reordered = copy.deepcopy(source)
        reordered["anchors"] = [reordered["anchors"][1], reordered["anchors"][0], reordered["anchors"][2]]
        aligned, mismatch = self.module._italic_topology_mismatch(source, reordered)
        self.assertIsNone(mismatch)
        self.assertEqual([item["name"] for item in aligned["anchors"]], ["bottom", "ogonek", "top"])

        missing = copy.deepcopy(source)
        missing["anchors"].pop()
        _aligned, mismatch = self.module._italic_topology_mismatch(source, missing)
        self.assertEqual(mismatch["field"], "anchorNames.length")

        duplicate = copy.deepcopy(source)
        duplicate["anchors"][2]["name"] = "ogonek"
        _aligned, mismatch = self.module._italic_topology_mismatch(source, duplicate)
        self.assertEqual(mismatch["field"], "anchorNames.unique")

    def test_italic_failure_payload_names_glyph_and_first_differing_field(self):
        source = _gee_gee_a_snapshot()
        candidate = copy.deepcopy(source)
        candidate["paths"][0]["nodes"].pop()
        mismatch = self.module._topology_mismatch(source, candidate)
        error = self.module._TopologyMismatchError("A", mismatch)

        with mock.patch.object(self.module, "_italic_preview_impl", side_effect=error):
            payload = json.loads(asyncio.run(self.module.preview_italic_first_pass_candidate(glyph_names=["A"])))

        self.assertEqual(payload["error"], "topology_change_blocked:A:paths[0].types.length")
        self.assertEqual(payload["errorType"], "topology_change_blocked")
        self.assertEqual(payload["topologyMismatch"]["glyphName"], "A")
        self.assertEqual(payload["topologyMismatch"]["field"], "paths[0].types.length")

    def test_italic_anchor_promotion_matches_names_and_preserves_metadata(self):
        desired = _gee_gee_a_snapshot()
        desired["anchors"][0].update({"x": 101.0, "y": 1.0})
        desired["anchors"][1].update({"x": 202.0, "y": 2.0})
        desired["anchors"][2].update({"x": 303.0, "y": 3.0})
        layer = _FixtureLayer(_gee_gee_a_snapshot(), "italic")
        layer.anchors = [layer.anchors[1], layer.anchors[0], layer.anchors[2]]
        layer.paths[0].nodes[0].name = "protected-node"
        layer.paths[0].nodes[0].userData = {"node": "kept"}
        layer.paths[0].attributes = {"group": "kept"}
        layer.paths[0].userData = {"path": "kept"}
        layer.userData = {"layer": "kept"}

        self.module._apply_allowed_snapshot(
            layer,
            desired,
            {"operation": "italic_first_pass", "allowed": {}},
        )

        positions = {anchor.name: self.module._point_values(anchor.position) for anchor in layer.anchors}
        self.assertEqual(positions["bottom"], (101.0, 1.0))
        self.assertEqual(positions["ogonek"], (202.0, 2.0))
        self.assertEqual(positions["top"], (303.0, 3.0))
        self.assertEqual(layer.paths[0].nodes[0].name, "protected-node")
        self.assertEqual(layer.paths[0].nodes[0].userData, {"node": "kept"})
        self.assertEqual(layer.paths[0].attributes, {"group": "kept"})
        self.assertEqual(layer.paths[0].userData, {"path": "kept"})
        self.assertEqual(layer.userData, {"layer": "kept"})

    def test_all_ten_public_tools_are_registered_and_safety_modes_are_strict(self):
        expected = {
            "preview_tunni_balance_candidate",
            "preview_collinear_handles_candidate",
            "preview_italic_first_pass_candidate",
            "preview_compensated_tuning_candidate",
            "set_outline_candidate_overlay",
            "get_outline_candidate_state",
            "materialize_outline_candidate_session",
            "review_outline_candidate_session",
            "accept_outline_candidate_session",
            "discard_outline_candidate_session",
        }
        self.assertTrue(expected.issubset(set(dir(self.module))))
        source = (RESOURCES / "mcp_tools_outline_candidates.py").read_text(encoding="utf-8")
        self.assertGreaterEqual(source.count("set exactly one of dry_run=true or confirm=true"), 3)

    def test_candidate_preview_schemas_do_not_include_curvature(self):
        tunni = inspect.signature(self.module.preview_tunni_balance_candidate)
        italic = inspect.signature(self.module.preview_italic_first_pass_candidate)

        self.assertNotIn("show_curvature", tunni.parameters)
        self.assertNotIn("show_curvature", italic.parameters)
        source = (RESOURCES / "mcp_tools_outline_candidates.py").read_text(encoding="utf-8")
        self.assertNotIn("showCurvature", source)

    def test_materialize_manual_review_and_accept_round_trip(self):
        module = self.module

        class Point:
            def __init__(self, x, y):
                self.x, self.y = float(x), float(y)

        class Node:
            def __init__(self, data):
                self.position = Point(data["x"], data["y"])
                self.type = data["type"]
                self.smooth = data["smooth"]

        class PathValue:
            def __init__(self, data):
                self.closed = data["closed"]
                self.nodes = [Node(item) for item in data["nodes"]]

        class Layer:
            def __init__(self, snapshot, layer_id="m1"):
                self.paths = [PathValue(item) for item in snapshot["paths"]]
                self.components = []
                self.anchors = []
                self.hints = []
                self.guides = []
                self.annotations = []
                self.width = snapshot["width"]
                self.layerId = layer_id
                self.associatedMasterId = "m1"
                self.name = "Regular"
                self.userData = {}
                self.parent = None
                self.begin_count = 0
                self.end_count = 0

            def copy(self):
                clone = Layer(module._layer_snapshot(self), self.layerId)
                clone.name = self.name
                clone.associatedMasterId = self.associatedMasterId
                return clone

            def beginChanges(self):
                self.begin_count += 1

            def endChanges(self):
                self.end_count += 1

        class Layers:
            def __init__(self, glyph, initial):
                self.glyph, self.items, self.serial = glyph, [initial], 0
                initial.parent = glyph

            def __iter__(self):
                return iter(self.items)

            def __getitem__(self, key):
                if isinstance(key, int):
                    return self.items[key]
                return next(item for item in self.items if str(item.layerId) == str(key))

            def __delitem__(self, index):
                del self.items[index]

            def append(self, layer):
                if getattr(layer, "_gmcp_was_attached", False) or any(
                    str(item.layerId) == str(layer.layerId) for item in self.items
                ):
                    self.serial += 1
                    layer.layerId = "candidate-{}".format(self.serial)
                layer._gmcp_was_attached = True
                layer.parent = self.glyph
                self.items.append(layer)

            def remove(self, layer):
                self.items.remove(layer)

        source_layer = Layer(_snapshot())
        glyph = types.SimpleNamespace(name="A", parent=None)
        glyph.layers = Layers(glyph, source_layer)
        font = types.SimpleNamespace(
            filepath=None,
            upm=1000,
            gridLength=1.0,
            gridSubDivision=1,
            userData={},
            masters=[types.SimpleNamespace(id="m1", name="Regular")],
            glyphs={"A": glyph},
        )
        glyph.parent = font
        module.outline_candidate_state.STORE.reset()
        source = module._layer_snapshot(source_layer)
        candidate = copy.deepcopy(source)
        candidate["paths"][0]["nodes"][1].update({"x": 30, "y": 0})
        candidate["paths"][0]["nodes"][2].update({"x": 100, "y": 70})
        entry = module._entry_base(
            font,
            0,
            glyph,
            source_layer,
            "tunni",
            source,
            candidate,
            {
                "targets": [{"masterId": "m1", "pathIndex": 0, "segmentEndNodeIndices": [3]}],
                "imbalanceThreshold": 0.05,
                "minHandleLength": 1.0,
                "gridPolicy": "font",
                "gridLength": 1.0,
                "gridSubDivision": 1,
                "upm": 1000.0,
            },
            {"nodeCoordinates": [{"pathIndex": 0, "nodeIndex": 1}, {"pathIndex": 0, "nodeIndex": 2}]},
        )
        session = module._session_payload(font, 0, "A", "tunni", [entry])
        module.outline_candidate_state.STORE.put_session(session)

        with mock.patch.object(module, "_resolve_font", return_value=font):
            dry = module._materialize_transaction(0, session["sessionId"], True)
            self.assertTrue(dry["dryRun"])
            self.assertEqual(len(list(glyph.layers)), 1)

            created = module._materialize_transaction(0, session["sessionId"], False)
            self.assertTrue(created["ok"])
            self.assertEqual(len(list(glyph.layers)), 2)
            materialized = list(glyph.layers)[1]
            self.assertEqual(materialized.associatedMasterId, "m1")
            self.assertTrue(materialized.name.startswith("GMCP Candidate — Tunni"))
            self.assertIn(module.LAYER_METADATA_KEY, materialized.userData)
            self.assertIn(module.FONT_MANIFEST_KEY, font.userData)
            self.assertIsInstance(materialized.userData[module.LAYER_METADATA_KEY], str)
            self.assertIsInstance(font.userData[module.FONT_MANIFEST_KEY], str)
            self.assertEqual(json.loads(materialized.userData[module.LAYER_METADATA_KEY])["sessionId"], session["sessionId"])

            # The geometry engine serializes integral grid coordinates as JSON
            # integers, while Glyphs reads the same NSPoint values back as
            # floats. An unchanged materialized candidate must still pass the
            # guarded recomputation check.
            _font, _unchanged_session, unchanged_records, unchanged_source_fps, unchanged_candidate_fps, unchanged_ready = (
                module._review_session_impl(0, session["sessionId"], False)
            )
            self.assertTrue(unchanged_ready)
            self.assertEqual(unchanged_records[0]["candidateStatus"], "generated_unchanged")
            unchanged_token = module.outline_candidate_state.STORE.issue_token(
                session["sessionId"], unchanged_source_fps, unchanged_candidate_fps
            )
            unchanged_dry_run = module._accept_transaction(0, session["sessionId"], unchanged_token, True)
            self.assertTrue(unchanged_dry_run["ok"])
            self.assertTrue(unchanged_dry_run["dryRun"])

            # Glyphs 4 assigns a fresh layer ID when rollback reattaches a
            # candidate removed during cleanup. The repaired manifest and
            # layer metadata must follow that new identity.
            materialized_id_before_rollback = materialized.layerId
            with mock.patch.object(
                module,
                "_manifest_delete_session",
                side_effect=RuntimeError("injected cleanup failure"),
            ):
                rolled_back = module._accept_transaction(0, session["sessionId"], unchanged_token, False)
            self.assertFalse(rolled_back["ok"])
            self.assertTrue(rolled_back["rollback"]["attempted"])
            self.assertTrue(rolled_back["rollback"]["succeeded"])
            self.assertNotEqual(materialized.layerId, materialized_id_before_rollback)
            repaired_manifest = module._manifest_get(font)["sessions"][session["sessionId"]]
            self.assertEqual(repaired_manifest["entries"][0]["materializedLayerId"], materialized.layerId)
            self.assertEqual(
                json.loads(materialized.userData[module.LAYER_METADATA_KEY])["entry"]["materializedLayerId"],
                materialized.layerId,
            )
            _font, _session, repaired_records, _source_fps, _candidate_fps, repaired_ready = (
                module._review_session_impl(0, session["sessionId"], False)
            )
            self.assertTrue(repaired_ready)
            self.assertEqual(repaired_records[0]["candidateStatus"], "generated_unchanged")

            # Process-local state is intentionally disposable; the plist-safe
            # manifest and layer metadata recover materialized sessions.
            module.outline_candidate_state.STORE.reset()
            recovered = module._load_session(font, session["sessionId"])
            self.assertEqual(recovered["entries"][0]["materializedLayerId"], materialized.layerId)

            # Manual edit stays on-grid, on-ray, and inside the requested
            # post-grid imbalance threshold.
            materialized.paths[0].nodes[1].position = Point(31, 0)
            _font, reviewed_session, records, source_fps, candidate_fps, ready = module._review_session_impl(
                0, session["sessionId"], True
            )
            self.assertTrue(ready)
            self.assertEqual(records[0]["candidateStatus"], "manually_edited")
            token = module.outline_candidate_state.STORE.issue_token(
                session["sessionId"], source_fps, candidate_fps
            )
            accepted = module._accept_transaction(0, session["sessionId"], token, False)

        self.assertTrue(accepted["ok"])
        self.assertEqual(module._point_values(source_layer.paths[0].nodes[1].position)[0], 31.0)
        self.assertEqual(module._point_values(source_layer.paths[0].nodes[2].position)[1], 70.0)
        self.assertEqual(len(list(glyph.layers)), 1)
        self.assertEqual(source_layer.begin_count, source_layer.end_count)
        self.assertNotIn(module.FONT_MANIFEST_KEY, font.userData)

    def test_snapshot_semantic_equality_normalizes_integral_coordinate_types(self):
        expected = _snapshot()
        expected["paths"][0]["nodes"][1].update({"x": 30, "y": 0})
        actual = copy.deepcopy(expected)
        actual["paths"][0]["nodes"][1].update({"x": 30.0, "y": 0.0})

        self.assertTrue(self.module._snapshots_semantically_equal(expected, actual))
        actual["paths"][0]["nodes"][1]["x"] = 30.25
        self.assertFalse(self.module._snapshots_semantically_equal(expected, actual))

    def test_discarding_ephemeral_only_session_does_not_touch_font_userdata(self):
        module = self.module
        module.outline_candidate_state.STORE.reset()
        font = types.SimpleNamespace(userData={})
        session = {"sessionId": "ephemeral", "entries": [], "fontKey": "memory"}
        module.outline_candidate_state.STORE._sessions["ephemeral"] = copy.deepcopy(session)
        module.outline_candidate_state.STORE._active_session_id = "ephemeral"
        with mock.patch.object(module, "_resolve_font", return_value=font), mock.patch.object(
            module, "_load_session", return_value=session
        ):
            result = module._discard_transaction(0, "ephemeral", False)

        self.assertTrue(result["ok"])
        self.assertFalse(result["fontChanged"])
        self.assertEqual(font.userData, {})

    def test_review_rejects_stale_source_before_token(self):
        entry = self._entry()
        entry.update(
            {
                "entryId": "e1",
                "glyphName": "A",
                "sourceLayerId": "m1",
                "sourceFingerprint": self.module._fingerprint(_snapshot()),
                "source": _snapshot(),
            }
        )
        font = types.SimpleNamespace(gridLength=1.0)
        with mock.patch.object(self.module, "_assert_current_source", side_effect=ValueError("stale_source")):
            # The per-entry review contains the stable blocker and cannot be ready.
            with mock.patch.object(self.module, "_resolve_font", return_value=font), mock.patch.object(
                self.module, "_load_session", return_value={"entries": [entry]}
            ):
                _font, _session, records, _sources, _candidates, ready = self.module._review_session_impl(
                    0, "s1", False
                )
        self.assertFalse(ready)
        self.assertEqual(records[0]["reason"], "stale_source")


if __name__ == "__main__":
    unittest.main()
