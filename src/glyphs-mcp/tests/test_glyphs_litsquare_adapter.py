"""Guarded LitSquare Glyphs-adapter tests using small object doubles."""

from __future__ import annotations

import importlib.util
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
        self.x = x
        self.y = y


class Size:
    def __init__(self, width, height):
        self.width = width
        self.height = height


class Rect:
    def __init__(self, x, y, width, height):
        self.origin = Point(x, y)
        self.size = Size(width, height)


class Node:
    def __init__(self, x, y, selected=False, node_type="line"):
        self.position = Point(x, y)
        self.selected = selected
        self.type = node_type


class PathDouble:
    def __init__(self, nodes, selected=False, bounds=None, attributes=None):
        self.nodes = nodes
        self.selected = selected
        self.closed = True
        self.bounds = bounds or Rect(0, 0, 10, 10)
        self.attributes = dict(attributes or {})


class Layer:
    def __init__(self, layer_id, paths):
        self.layerId = layer_id
        self.name = "Regular"
        self.paths = paths
        self.userData = {}
        self.parent = None
        self.change_depth = 0
        self.change_count = 0

    def beginChanges(self):
        self.change_depth += 1
        self.change_count += 1

    def endChanges(self):
        self.change_depth -= 1


class Glyph:
    def __init__(self, name, layer):
        self.name = name
        self.layers = {layer.layerId: layer}
        self.userData = {}
        self.undo_depth = 0
        self.undo_count = 0
        layer.parent = self

    def beginUndo(self):
        self.undo_depth += 1
        self.undo_count += 1

    def endUndo(self):
        self.undo_depth -= 1


class Font:
    def __init__(self, glyph, layer):
        self.familyName = "LitSquare Test"
        self.glyphs = {glyph.name: glyph}
        self.selectedLayers = [layer]
        self.userData = {"unrelated.namespace": {"keep": True}}
        self.parent = Document()


class UndoManager:
    def __init__(self):
        self.depth = 0
        self.group_count = 0
        self.handlers = []

    def beginUndoGrouping(self):
        self.depth += 1
        self.group_count += 1

    def endUndoGrouping(self):
        self.depth -= 1

    def registerUndoWithTarget_handler_(self, target, handler):
        self.handlers.append((target, handler))

    def undo(self):
        target, handler = self.handlers.pop()
        handler(target)


class Document:
    def __init__(self):
        self.undoManager = UndoManager()


def _load_adapter():
    sys.path.insert(0, str(RESOURCES))
    helper = types.ModuleType("mcp_tool_helpers")
    helper._get_layer_id = lambda layer: layer.layerId
    helper._resolve_font_by_index = lambda app, index: (
        (app.fonts[int(index)] if 0 <= int(index) < len(app.fonts) else None),
        app.fonts,
    )
    helper._run_on_main_thread = lambda callback: callback()
    path = RESOURCES / "glyphs_litsquare_adapter.py"
    spec = importlib.util.spec_from_file_location("glyphs_mcp_test_litsquare_adapter", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, {"mcp_tool_helpers": helper}):
        spec.loader.exec_module(module)
    return module


class GlyphsLitSquareAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = _load_adapter()

    def setUp(self):
        self.path1 = PathDouble(
            [Node(0, 0, selected=True), Node(20, 0)],
            bounds=Rect(0, 0, 20, 30),
            attributes={"fill": True, "com.litsquare.role": "body"},
        )
        self.path2 = PathDouble(
            [Node(30, 0), Node(40, 0)],
            selected=True,
            bounds=Rect(30, 0, 10, 10),
            attributes={"mask": True},
        )
        self.layer = Layer("MASTER-1", [self.path1, self.path2])
        self.glyph = Glyph("A", self.layer)
        self.font = Font(self.glyph, self.layer)
        self.app = types.SimpleNamespace(fonts=[self.font])
        self.font.userData["com.litsquare"] = {
            "schemaVersion": 1,
            "updatedAt": "2026-08-11T18:30:00Z",
            "settings": {"grid": 24, "mode": "font"},
            "unknown": {"keep": True},
        }
        self.glyph.userData["com.litsquare"] = {
            "schemaVersion": 1,
            "updatedAt": "2026-08-11T18:31:00Z",
            "settings": {"mode": "glyph"},
        }

    def test_metadata_snapshot_returns_scopes_and_effective_settings(self):
        result = self.adapter.metadata_snapshot(app=self.app)
        self.assertTrue(result["ok"])
        self.assertEqual(result["scopes"]["font"]["state"], "valid")
        self.assertEqual(result["scopes"]["glyph"]["state"], "valid")
        self.assertEqual(result["scopes"]["layer"]["state"], "missing")
        self.assertEqual(result["target"]["layerName"], "Regular")
        self.assertEqual(result["target"]["layerId"], "MASTER-1")
        self.assertEqual(result["effectiveSettings"]["values"], {"grid": 24, "mode": "glyph"})
        self.assertEqual(result["effectiveSettings"]["provenance"]["mode"], "glyph")

    def test_selection_snapshot_aggregates_identical_and_mixed_glyph_roots(self):
        second_layer = Layer("MASTER-2", [])
        second_glyph = Glyph("B", second_layer)
        second_glyph.userData["com.litsquare"] = dict(
            self.glyph.userData["com.litsquare"]
        )
        self.font.glyphs["B"] = second_glyph
        self.font.selectedLayers = [self.layer, second_layer]

        shared = self.adapter.metadata_selection_snapshot("glyph", font=self.font)
        self.assertTrue(shared["ok"])
        self.assertFalse(shared["summary"]["mixed"])
        self.assertEqual(shared["summary"]["targetCount"], 2)
        self.assertEqual(shared["sharedResult"]["state"], "valid")

        second_glyph.userData["com.litsquare"]["settings"] = {"mode": "other"}
        mixed = self.adapter.metadata_selection_snapshot("glyph", font=self.font)
        self.assertTrue(mixed["summary"]["mixed"])
        self.assertIsNone(mixed["sharedResult"])

    def test_selection_replace_is_atomic_document_bound_and_preserves_namespaces(self):
        second_layer = Layer("MASTER-2", [])
        second_glyph = Glyph("B", second_layer)
        second_glyph.userData = {"other.namespace": {"keep": 2}}
        self.font.glyphs["B"] = second_glyph
        self.font.selectedLayers = [self.layer, second_layer]
        snapshot = self.adapter.metadata_selection_snapshot("glyph", font=self.font)
        proposed = {
            "schemaVersion": 1,
            "updatedAt": "2026-08-11T19:00:00Z",
            "status": {"value": "shared"},
        }
        result = self.adapter.replace_metadata_selection_transaction(
            "glyph",
            [entry["target"] for entry in snapshot["entries"]],
            proposed,
            font=self.font,
        )
        self.assertEqual(result["summary"]["changedTargetCount"], 2)
        self.assertEqual(self.glyph.userData["com.litsquare"]["status"], {"value": "shared"})
        self.assertEqual(second_glyph.userData["com.litsquare"]["status"], {"value": "shared"})
        self.assertEqual(second_glyph.userData["other.namespace"], {"keep": 2})
        self.assertEqual(self.font.parent.undoManager.group_count, 1)
        self.assertEqual(len(self.font.parent.undoManager.handlers), 1)
        self.assertFalse(result["fontSaved"])
        self.font.parent.undoManager.undo()
        self.assertEqual(self.glyph.userData["com.litsquare"]["settings"], {"mode": "glyph"})
        self.assertNotIn("com.litsquare", second_glyph.userData)
        self.font.parent.undoManager.undo()
        self.assertEqual(self.glyph.userData["com.litsquare"]["status"], {"value": "shared"})
        self.assertEqual(second_glyph.userData["com.litsquare"]["status"], {"value": "shared"})

    def test_selection_replace_rejects_stale_target_before_any_write(self):
        second_layer = Layer("MASTER-2", [])
        second_glyph = Glyph("B", second_layer)
        second_glyph.userData["com.litsquare"] = dict(
            self.glyph.userData["com.litsquare"]
        )
        self.font.glyphs["B"] = second_glyph
        self.font.selectedLayers = [self.layer, second_layer]
        snapshot = self.adapter.metadata_selection_snapshot("glyph", font=self.font)
        second_glyph.userData["com.litsquare"]["status"] = {"changed": True}
        before = dict(self.glyph.userData["com.litsquare"])
        with self.assertRaisesRegex(ValueError, "changed since"):
            self.adapter.replace_metadata_selection_transaction(
                "glyph",
                [entry["target"] for entry in snapshot["entries"]],
                {
                    "schemaVersion": 1,
                    "updatedAt": "2026-08-11T19:00:00Z",
                    "status": {"value": "shared"},
                },
                font=self.font,
            )
        self.assertEqual(self.glyph.userData["com.litsquare"], before)
        self.assertNotIn("value", second_glyph.userData["com.litsquare"]["status"])

    def test_selection_replace_rolls_back_all_roots_when_one_write_fails(self):
        second_layer = Layer("MASTER-2", [])
        second_glyph = Glyph("B", second_layer)
        self.font.glyphs["B"] = second_glyph
        self.font.selectedLayers = [self.layer, second_layer]
        snapshot = self.adapter.metadata_selection_snapshot("glyph", font=self.font)
        original = dict(self.glyph.userData["com.litsquare"])
        original_write = self.adapter._write_root
        calls = {"count": 0}

        def fail_second(owner, value, present=None):
            calls["count"] += 1
            if calls["count"] == 2:
                raise RuntimeError("simulated metadata write failure")
            return original_write(owner, value, present=present)

        with mock.patch.object(self.adapter, "_write_root", side_effect=fail_second):
            with self.assertRaisesRegex(RuntimeError, "simulated"):
                self.adapter.replace_metadata_selection_transaction(
                    "glyph",
                    [entry["target"] for entry in snapshot["entries"]],
                    {
                        "schemaVersion": 1,
                        "updatedAt": "2026-08-11T19:00:00Z",
                        "status": {"value": "shared"},
                    },
                    font=self.font,
                )
        self.assertEqual(self.glyph.userData["com.litsquare"], original)
        self.assertNotIn("com.litsquare", second_glyph.userData)
        self.assertEqual(self.font.parent.undoManager.handlers, [])

    def test_selected_paths_include_node_and_path_selection(self):
        result = self.adapter.selected_path_snapshot(app=self.app)
        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"]["selectedPathCount"], 2)
        self.assertEqual(result["aggregation"]["state"], "mixed")
        self.assertEqual(result["aggregation"]["counts"], {"body": 1, "unassigned": 1})
        self.assertEqual([entry["bounds"]["width"] for entry in result["paths"]], [20.0, 10.0])
        self.assertNotIn("centering", result)

    def test_full_metadata_snapshot_projects_every_native_scope(self):
        self.layer.userData["other.layer"] = {"unicode": "café"}
        font_snapshot = self.adapter.full_metadata_selection_snapshot(
            "font", font=self.font
        )
        self.assertTrue(font_snapshot["ok"])
        self.assertEqual(font_snapshot["summary"]["targetCount"], 1)
        self.assertEqual(
            font_snapshot["entries"][0]["target"]["familyName"],
            "LitSquare Test",
        )
        self.assertIn("unrelated.namespace", font_snapshot["entries"][0]["userData"])
        self.assertIn("com.litsquare", font_snapshot["entries"][0]["userData"])

        glyph_snapshot = self.adapter.full_metadata_selection_snapshot(
            "glyph", font=self.font
        )
        self.assertEqual(glyph_snapshot["entries"][0]["target"]["glyphName"], "A")
        self.assertIn("com.litsquare", glyph_snapshot["entries"][0]["userData"])

        layer_snapshot = self.adapter.full_metadata_selection_snapshot(
            "layer", font=self.font
        )
        self.assertEqual(layer_snapshot["entries"][0]["target"]["layerId"], "MASTER-1")
        self.assertEqual(
            layer_snapshot["entries"][0]["userData"]["other.layer"]["unicode"],
            "café",
        )
        self.assertFalse(layer_snapshot["fontSaved"])

    def test_full_metadata_snapshot_enumerates_multiple_targets_in_selection_order(self):
        second_layer = Layer("MASTER-2", [])
        second_layer.userData["layer.plugin"] = {"second": True}
        second_glyph = Glyph("B", second_layer)
        second_glyph.userData["glyph.plugin"] = {"second": True}
        self.font.glyphs["B"] = second_glyph
        self.font.selectedLayers = [self.layer, second_layer, self.layer]

        glyphs = self.adapter.full_metadata_selection_snapshot("glyph", font=self.font)
        self.assertEqual(glyphs["summary"]["targetCount"], 2)
        self.assertEqual(
            [entry["target"]["glyphName"] for entry in glyphs["entries"]],
            ["A", "B"],
        )
        self.assertIn("glyph.plugin", glyphs["entries"][1]["userData"])

        layers = self.adapter.full_metadata_selection_snapshot("layer", font=self.font)
        self.assertEqual(layers["summary"]["targetCount"], 2)
        self.assertEqual(
            [entry["target"]["layerId"] for entry in layers["entries"]],
            ["MASTER-1", "MASTER-2"],
        )
        self.assertIn("layer.plugin", layers["entries"][1]["userData"])

    def test_full_metadata_paths_include_selected_attributes_only(self):
        unselected = PathDouble(
            [Node(50, 0), Node(60, 0)],
            attributes={"unselected.plugin": True},
        )
        self.layer.paths.append(unselected)
        snapshot = self.adapter.full_metadata_selection_snapshot(
            "paths", font=self.font
        )
        self.assertEqual(snapshot["summary"]["targetCount"], 2)
        self.assertEqual(
            [entry["target"]["pathIndex"] for entry in snapshot["entries"]],
            [0, 1],
        )
        self.assertEqual(
            snapshot["entries"][0]["attributes"],
            {"fill": True, "com.litsquare.role": "body"},
        )
        self.assertEqual(snapshot["entries"][1]["attributes"], {"mask": True})
        self.assertNotIn("bounds", snapshot["entries"][0]["target"])
        self.assertNotIn("pathFingerprint", snapshot["entries"][0]["target"])
        self.assertNotIn(
            "unselected.plugin",
            str(snapshot["entries"]),
        )

    def test_full_metadata_snapshot_reports_projection_warnings_without_mutation(self):
        class NativeThing:
            def __str__(self):
                return "native"

        thing = NativeThing()
        self.font.userData["plugin.native"] = thing
        snapshot = self.adapter.full_metadata_selection_snapshot("font", font=self.font)
        self.assertEqual(snapshot["summary"]["warningCount"], 1)
        self.assertEqual(
            snapshot["entries"][0]["userData"]["plugin.native"]["$nativeObject"]["type"],
            "NativeThing",
        )
        self.assertIs(self.font.userData["plugin.native"], thing)

    def test_patch_dry_run_then_confirm_preserves_unknown_namespace_and_fields(self):
        dry = self.adapter.patch_metadata_transaction(
            "font",
            {"settings": {"grid": 32}},
            expected_updated_at="2026-08-11T18:30:00Z",
            dry_run=True,
            confirm=False,
            app=self.app,
        )
        self.assertTrue(dry["summary"]["changed"])
        self.assertEqual(self.font.userData["com.litsquare"]["settings"]["grid"], 24)

        confirmed = self.adapter.patch_metadata_transaction(
            "font",
            {"settings": {"grid": 32}},
            expected_updated_at="2026-08-11T18:30:00Z",
            dry_run=False,
            confirm=True,
            app=self.app,
        )
        self.assertTrue(confirmed["summary"]["changed"])
        root = self.font.userData["com.litsquare"]
        self.assertEqual(root["settings"], {"grid": 32, "mode": "font"})
        self.assertEqual(root["unknown"], {"keep": True})
        self.assertEqual(self.font.userData["unrelated.namespace"], {"keep": True})
        self.assertFalse(confirmed["fontSaved"])
        self.assertTrue(confirmed["undoGrouped"])
        self.assertTrue(confirmed["undoRegistered"])
        self.assertEqual(self.font.parent.undoManager.depth, 0)
        self.font.parent.undoManager.undo()
        self.assertEqual(self.font.userData["com.litsquare"]["settings"]["grid"], 24)
        self.font.parent.undoManager.undo()
        self.assertEqual(self.font.userData["com.litsquare"]["settings"]["grid"], 32)

    def test_patch_rejects_stale_updated_at_and_schema_change(self):
        with self.assertRaisesRegex(ValueError, "changed since review"):
            self.adapter.patch_metadata_transaction(
                "font", {"status": {"state": "ready"}}, expected_updated_at="stale", app=self.app
            )
        with self.assertRaisesRegex(ValueError, "migration"):
            self.adapter.patch_metadata_transaction("font", {"schemaVersion": 2}, app=self.app)

    def test_patch_undo_restores_an_explicit_empty_root(self):
        self.layer.userData["com.litsquare"] = {}
        result = self.adapter.patch_metadata_transaction(
            "layer",
            {"status": {"state": "ready"}},
            glyph_name="A",
            layer_id="MASTER-1",
            dry_run=False,
            confirm=True,
            app=self.app,
        )
        self.assertTrue(result["summary"]["changed"])
        self.font.parent.undoManager.undo()
        self.assertIn("com.litsquare", self.layer.userData)
        self.assertEqual(self.layer.userData["com.litsquare"], {})

    def test_patch_rolls_back_when_native_readback_does_not_match(self):
        original_write = self.adapter._write_root

        def mismatched_readback(owner, value, present=None):
            result = original_write(owner, value, present=present)
            if value.get("settings", {}).get("grid") == 99:
                result = dict(result)
                result["value"] = dict(result["value"])
                result["value"]["settings"] = {"grid": -1}
            return result

        with mock.patch.object(self.adapter, "_write_root", side_effect=mismatched_readback):
            with self.assertRaisesRegex(RuntimeError, "readback"):
                self.adapter.patch_metadata_transaction(
                    "font",
                    {"settings": {"grid": 99}},
                    dry_run=False,
                    confirm=True,
                    app=self.app,
                )
        self.assertEqual(self.font.userData["com.litsquare"]["settings"]["grid"], 24)
        self.assertEqual(self.font.parent.undoManager.handlers, [])

    def test_role_write_preserves_builtins_groups_undo_and_can_clear(self):
        snapshot = self.adapter.selected_path_snapshot(app=self.app)
        targets = [snapshot["paths"][0]]
        dry = self.adapter.set_path_roles_transaction(targets, "detail", app=self.app)
        self.assertEqual(dry["replacements"][0]["before"], "body")
        self.assertEqual(self.path1.attributes["com.litsquare.role"], "body")

        confirmed = self.adapter.set_path_roles_transaction(
            targets, "detail", dry_run=False, confirm=True, app=self.app
        )
        self.assertEqual(self.path1.attributes["com.litsquare.role"], "detail")
        self.assertTrue(self.path1.attributes["fill"])
        self.assertTrue(confirmed["undoGrouped"])
        self.assertTrue(confirmed["undoRegistered"])
        self.assertEqual(self.font.parent.undoManager.group_count, 1)
        self.assertEqual(self.glyph.undo_depth, 0)
        self.assertEqual(self.layer.change_depth, 0)
        self.assertEqual(self.layer.change_count, 1)

        self.font.parent.undoManager.undo()
        self.assertEqual(self.path1.attributes["com.litsquare.role"], "body")
        self.font.parent.undoManager.undo()
        self.assertEqual(self.path1.attributes["com.litsquare.role"], "detail")

        refreshed = self.adapter.selected_path_snapshot(app=self.app)
        self.adapter.set_path_roles_transaction(
            [refreshed["paths"][0]], None, dry_run=False, confirm=True, app=self.app
        )
        self.assertNotIn("com.litsquare.role", self.path1.attributes)
        self.assertTrue(self.path1.attributes["fill"])

    def test_role_write_accepts_trimmed_custom_unicode_and_empty_removes(self):
        self.path1.attributes["com.litsquare.role"] = " body "
        snapshot = self.adapter.selected_path_snapshot(app=self.app)
        target = snapshot["paths"][0]
        self.assertEqual(target["role"], "body")
        self.assertEqual(target["expectedRole"], " body ")

        confirmed = self.adapter.set_path_roles_transaction(
            [target],
            "  Icône principale  ",
            dry_run=False,
            confirm=True,
            app=self.app,
        )
        self.assertEqual(confirmed["replacements"][0]["after"], "Icône principale")
        self.assertEqual(self.path1.attributes["com.litsquare.role"], "Icône principale")

        refreshed = self.adapter.selected_path_snapshot(app=self.app)["paths"][0]
        self.adapter.set_path_roles_transaction(
            [refreshed],
            "   ",
            dry_run=False,
            confirm=True,
            app=self.app,
        )
        self.assertNotIn("com.litsquare.role", self.path1.attributes)

    def test_role_write_can_use_palette_document_bound_font(self):
        other_path = PathDouble(
            [Node(0, 0, selected=True), Node(10, 0)],
            attributes={"com.litsquare.role": "source"},
        )
        other_layer = Layer("MASTER-2", [other_path])
        other_glyph = Glyph("B", other_layer)
        other_font = Font(other_glyph, other_layer)
        target = self.adapter.selected_path_snapshot(font=other_font)["paths"][0]

        self.adapter.set_path_roles_transaction(
            [target],
            "destination",
            dry_run=False,
            confirm=True,
            app=self.app,
            font=other_font,
        )
        self.assertEqual(other_path.attributes["com.litsquare.role"], "destination")
        self.assertEqual(self.path1.attributes["com.litsquare.role"], "body")

    def test_role_write_rejects_stale_fingerprint_atomically(self):
        snapshot = self.adapter.selected_path_snapshot(app=self.app)
        targets = snapshot["paths"]
        targets[1]["pathFingerprint"] = "sha256:stale"
        with self.assertRaisesRegex(ValueError, "changed since review"):
            self.adapter.set_path_roles_transaction(
                targets, "detail", dry_run=False, confirm=True, app=self.app
            )
        self.assertEqual(self.path1.attributes["com.litsquare.role"], "body")
        self.assertNotIn("com.litsquare.role", self.path2.attributes)
        self.assertTrue(self.path2.attributes["mask"])

    def test_role_write_rolls_back_every_path_when_one_assignment_fails(self):
        targets = self.adapter.selected_path_snapshot(app=self.app)["paths"]
        original_set = self.adapter._mapping_set

        def fail_second(owner, attribute_name, key, value):
            if owner is self.path2 and key == "com.litsquare.role" and value == "detail":
                raise RuntimeError("simulated role write failure")
            return original_set(owner, attribute_name, key, value)

        with mock.patch.object(self.adapter, "_mapping_set", side_effect=fail_second):
            with self.assertRaisesRegex(RuntimeError, "simulated"):
                self.adapter.set_path_roles_transaction(
                    targets, "detail", dry_run=False, confirm=True, app=self.app
                )
        self.assertEqual(self.path1.attributes["com.litsquare.role"], "body")
        self.assertNotIn("com.litsquare.role", self.path2.attributes)
        self.assertTrue(self.path2.attributes["mask"])
        self.assertEqual(self.layer.change_depth, 0)
        self.assertEqual(self.font.parent.undoManager.handlers, [])

    def test_role_write_rejects_duplicate_targets(self):
        target = self.adapter.selected_path_snapshot(app=self.app)["paths"][0]
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.adapter.set_path_roles_transaction([target, dict(target)], "detail", app=self.app)


if __name__ == "__main__":
    unittest.main()
