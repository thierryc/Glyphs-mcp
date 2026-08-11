from __future__ import annotations

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
