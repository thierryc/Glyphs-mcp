"""Guarded Glyphs adapter tests for fixed IconGrid centering."""

from __future__ import annotations

import importlib.util
import math
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
    def __init__(self, x, y):
        self.position = Point(x, y)
        self.type = "line"
        self.smooth = False
        self.selected = False


class PathDouble:
    def __init__(self, role, bounds):
        self.nodes = [Node(bounds[0], bounds[1]), Node(bounds[0] + bounds[2], bounds[1])]
        self.closed = False
        self.selected = False
        self.bounds = Rect(*bounds)
        self.attributes = {"mask": True, "com.litsquare.role": role}


class ComponentDouble:
    def __init__(self, bounds):
        self.bounds = Rect(*bounds)


class Layer:
    def __init__(self, paths, components=None):
        self.layerId = "MASTER-1"
        self.name = "Regular"
        self.width = 1000
        self.paths = paths
        self.components = list(components or [])
        self.userData = {"com.example.keep": {"value": 7}}
        self.parent = None


class Glyph:
    def __init__(self, layer):
        self.name = "A"
        self.layers = {layer.layerId: layer}
        layer.parent = self


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

    def setActionName_(self, name):
        self.action_name = name

    def undo(self):
        target, handler = self.handlers.pop()
        handler(target)


class Font:
    def __init__(self, glyph, layer):
        self.familyName = "Icon Grid Test"
        self.glyphs = {glyph.name: glyph}
        self.selectedLayers = [layer]
        self.parent = types.SimpleNamespace(undoManager=UndoManager())


class NotificationCenterDouble:
    notifications = []

    @classmethod
    def defaultCenter(cls):
        return cls

    @classmethod
    def postNotificationName_object_userInfo_(cls, name, owner, info):
        cls.notifications.append((name, owner, info))


def _load_adapter():
    sys.path.insert(0, str(RESOURCES))
    helper = types.ModuleType("mcp_tool_helpers")
    helper._get_layer_id = lambda layer: layer.layerId
    helper._resolve_font_by_index = lambda app, index: (
        (app.fonts[int(index)] if 0 <= int(index) < len(app.fonts) else None),
        app.fonts,
    )
    helper._run_on_main_thread = lambda callback: callback()
    path = RESOURCES / "glyphs_icon_grid_adapter.py"
    spec = importlib.util.spec_from_file_location("glyphs_mcp_test_icon_grid_adapter", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, {"mcp_tool_helpers": helper}):
        spec.loader.exec_module(module)
    return module


class GlyphsIconGridAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = _load_adapter()

    def setUp(self):
        NotificationCenterDouble.notifications = []
        self.adapter.NSNotificationCenter = NotificationCenterDouble
        self.path1 = PathDouble("body", (100, 0, 200, 300))
        self.path2 = PathDouble("detail", (500, 20, 100, 50))
        self.component = ComponentDouble((700, -20, 100, 80))
        self.layer = Layer([self.path1, self.path2], [self.component])
        self.glyph = Glyph(self.layer)
        self.font = Font(self.glyph, self.layer)
        self.app = types.SimpleNamespace(fonts=[self.font], redraw_count=0)
        self.app.redraw = lambda: setattr(self.app, "redraw_count", self.app.redraw_count + 1)

    def test_snapshot_returns_policy_candidates_and_fingerprint(self):
        result = self.adapter.icon_grid_snapshot(app=self.app)
        self.assertTrue(result["ok"])
        self.assertEqual(result["center"]["state"], "default")
        self.assertEqual(result["center"]["resolvedX"], 500.0)
        self.assertEqual(result["candidates"]["advance"]["x"], 500.0)
        self.assertEqual(result["candidates"]["layerContent"]["bounds"]["x"], 100.0)
        self.assertEqual(result["candidates"]["layerContent"]["x"], 450.0)
        self.assertEqual(result["candidates"]["layerContent"]["shapeCount"], 3)
        self.assertNotIn("bodyPaths", result)
        self.assertTrue(result["stateFingerprint"].startswith("sha256:"))
        self.assertFalse(result["fontSaved"])

    def test_fingerprint_and_fixed_center_ignore_artwork_roles_and_width(self):
        before = self.adapter.icon_grid_snapshot(app=self.app)
        self.path1.bounds = Rect(-1000, 0, 20, 20)
        self.path1.nodes[0].position.x = -1000
        self.path1.attributes["com.litsquare.role"] = "container"
        self.component.bounds = Rect(1500, 0, 20, 20)
        self.layer.width = 1200
        after_artwork = self.adapter.icon_grid_snapshot(app=self.app)
        self.assertEqual(after_artwork["stateFingerprint"], before["stateFingerprint"])
        self.assertNotEqual(
            after_artwork["candidates"]["layerContent"]["x"],
            before["candidates"]["layerContent"]["x"],
        )

        confirmed = self.adapter.set_icon_grid_horizontal_center_transaction(
            before["stateFingerprint"],
            321.5,
            dry_run=False,
            confirm=True,
            app=self.app,
        )
        self.assertEqual(confirmed["after"]["center"]["resolvedX"], 321.5)
        self.path2.bounds = Rect(5000, 0, 100, 100)
        self.layer.width = 1600
        fixed = self.adapter.icon_grid_snapshot(app=self.app)
        self.assertEqual(fixed["center"]["resolvedX"], 321.5)
        self.assertEqual(fixed["stateFingerprint"], confirmed["after"]["stateFingerprint"])

    def test_dry_run_and_confirm_set_preserve_artwork_domains_and_support_undo_redo(self):
        snapshot = self.adapter.icon_grid_snapshot(app=self.app)
        dry = self.adapter.set_icon_grid_horizontal_center_transaction(
            snapshot["stateFingerprint"], 350.0, app=self.app
        )
        self.assertFalse(dry["applied"])
        self.assertEqual(dry["readback"]["stateFingerprint"], snapshot["stateFingerprint"])
        self.assertTrue(dry["summary"]["changed"])
        self.assertNotIn("com.litsquare.icongrid", self.layer.userData)

        confirmed = self.adapter.set_icon_grid_horizontal_center_transaction(
            snapshot["stateFingerprint"],
            350.0,
            dry_run=False,
            confirm=True,
            app=self.app,
        )
        self.assertTrue(confirmed["applied"])
        self.assertEqual(
            self.layer.userData["com.litsquare.icongrid"],
            {"schemaVersion": 1, "centerX": {"mode": "coordinate", "x": 350.0}},
        )
        self.assertEqual(self.layer.userData["com.example.keep"], {"value": 7})
        self.assertEqual(self.path2.attributes["com.litsquare.role"], "detail")
        self.assertTrue(self.path1.attributes["mask"])
        self.assertTrue(confirmed["undoGrouped"])
        self.assertTrue(confirmed["undoRegistered"])
        self.assertTrue(confirmed["redrawn"])
        self.assertFalse(confirmed["fontSaved"])
        self.assertEqual(
            NotificationCenterDouble.notifications[-1][0],
            "com.litsquare.icongrid.changed",
        )

        manager = self.font.parent.undoManager
        manager.undo()
        self.assertNotIn("com.litsquare.icongrid", self.layer.userData)
        manager.undo()
        self.assertIn("com.litsquare.icongrid", self.layer.userData)
        self.assertEqual(len(NotificationCenterDouble.notifications), 3)

    def test_stale_policy_and_nonfinite_coordinate_are_rejected(self):
        snapshot = self.adapter.icon_grid_snapshot(app=self.app)
        self.layer.userData["com.litsquare.icongrid"] = {
            "schemaVersion": 1,
            "centerX": {"mode": "coordinate", "x": 200},
        }
        with self.assertRaisesRegex(ValueError, "changed since review"):
            self.adapter.set_icon_grid_horizontal_center_transaction(
                snapshot["stateFingerprint"], 250, app=self.app
            )
        fresh = self.adapter.icon_grid_snapshot(app=self.app)
        for coordinate in (True, math.nan, math.inf):
            with self.assertRaisesRegex(ValueError, "finite number"):
                self.adapter.set_icon_grid_horizontal_center_transaction(
                    fresh["stateFingerprint"], coordinate, app=self.app
                )

    def test_set_replaces_unreleased_role_policy_without_touching_roles(self):
        self.layer.userData["com.litsquare.icongrid"] = {
            "schemaVersion": 1,
            "centerX": {
                "mode": "roleBounds",
                "role": "body",
                "futureOption": {"keep": True},
            },
            "future": {"keep": True},
        }
        snapshot = self.adapter.icon_grid_snapshot(app=self.app)
        result = self.adapter.set_icon_grid_horizontal_center_transaction(
            snapshot["stateFingerprint"], 400, app=self.app
        )
        self.assertEqual(
            result["proposed"]["root"]["centerX"],
            {"mode": "coordinate", "x": 400.0, "futureOption": {"keep": True}},
        )
        self.assertEqual(self.path1.attributes["com.litsquare.role"], "body")

    def test_reset_preserves_roles_and_unknown_icon_grid_fields(self):
        self.layer.userData["com.litsquare.icongrid"] = {
            "schemaVersion": 1,
            "centerX": {"mode": "coordinate", "x": 350},
            "future": {"keep": True},
        }
        snapshot = self.adapter.icon_grid_snapshot(app=self.app)
        confirmed = self.adapter.reset_icon_grid_horizontal_center_transaction(
            snapshot["stateFingerprint"],
            dry_run=False,
            confirm=True,
            app=self.app,
        )
        self.assertEqual(
            self.layer.userData["com.litsquare.icongrid"],
            {"schemaVersion": 1, "future": {"keep": True}},
        )
        self.assertEqual(self.path1.attributes["com.litsquare.role"], "body")
        self.assertTrue(confirmed["summary"]["changed"])

    def test_reset_can_remove_obsolete_v1_center_but_rejects_future_schema(self):
        self.layer.userData["com.litsquare.icongrid"] = {
            "schemaVersion": 1,
            "centerX": {"mode": "roleBounds", "role": "body"},
        }
        snapshot = self.adapter.icon_grid_snapshot(app=self.app)
        result = self.adapter.reset_icon_grid_horizontal_center_transaction(
            snapshot["stateFingerprint"], app=self.app
        )
        self.assertFalse(result["proposed"]["rootPresent"])
        self.layer.userData["com.litsquare.icongrid"] = {
            "schemaVersion": 2,
            "centerX": {},
        }
        future = self.adapter.icon_grid_snapshot(app=self.app)
        with self.assertRaisesRegex(ValueError, "read-only"):
            self.adapter.reset_icon_grid_horizontal_center_transaction(
                future["stateFingerprint"], app=self.app
            )

    def test_misspelled_domain_is_unrelated(self):
        self.layer.userData["com.leetsquare.icongrid"] = {"centerX": 100}
        result = self.adapter.icon_grid_snapshot(app=self.app)
        self.assertEqual(result["policy"]["state"], "missing")
        self.assertEqual(self.layer.userData["com.leetsquare.icongrid"], {"centerX": 100})


if __name__ == "__main__":
    unittest.main()
