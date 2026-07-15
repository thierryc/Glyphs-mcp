"""Regression tests for MCP annotation tool wrappers."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


def _module_path() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Resources"
        / "mcp_tools_annotations.py"
    )


class _FakeMCP:
    def tool(self, *args, **kwargs):
        def decorator(fn):
            return fn

        return decorator


class _Lookup(dict):
    def __getitem__(self, key):
        return self.get(key)


def _resolve_font_by_index(glyphs, font_index):
    fonts = list(getattr(glyphs, "fonts", []) or [])
    index = int(font_index)
    if index < 0 or index >= len(fonts):
        return None, fonts
    return fonts[index], fonts


def _font_resolution_error(font_index, fonts=None, ok_key=None):
    return {"error": "Font index out of range", "fontIndex": font_index, "availableFontCount": len(fonts or [])}


class _FakePoint:
    def __init__(self, x=0.0, y=0.0):
        self.x = x
        self.y = y

    def __getitem__(self, index):
        return (self.x, self.y)[index]


class _FakeGSAnnotation:
    def __init__(self):
        self._position = _FakePoint()
        self.type = 1
        self.text = ""
        self.angle = 0.0
        self.width = 0.0

    @property
    def position(self):
        return self._position

    @position.setter
    def position(self, value):
        self._position = _FakePoint(float(value[0]), float(value[1]))


class _ProxyUserData(dict):
    def __setitem__(self, key, value):
        self.ignored_setitem = (key, value)

    def setObject_forKey_(self, value, key):
        dict.__setitem__(self, key, value)

    def __delitem__(self, key):
        self.ignored_delitem = key

    def removeObjectForKey_(self, key):
        dict.pop(self, key, None)


class _DroppingUserData(dict):
    def __setitem__(self, key, value):
        self.ignored_setitem = (key, value)

    def setObject_forKey_(self, value, key):
        self.ignored_set_object = (key, value)


class _NoOpAppendAnnotations(list):
    def append(self, item):
        self.ignored_append = item


class _ProxyList:
    def __init__(self, items):
        self._items = list(items)

    def __iter__(self):
        return iter(self._items)


class _ReadOnlyUserDataFont:
    def __init__(self, source, user_data):
        self.familyName = source.familyName
        self.filepath = source.filepath
        self.glyphs = source.glyphs
        self.masters = source.masters
        self.selectedFontMaster = source.selectedFontMaster
        self._userData = user_data

    @property
    def userData(self):
        return self._userData

    @userData.setter
    def userData(self, value):
        raise AttributeError("userData is read-only")


class McpToolsAnnotationsTests(unittest.TestCase):
    def _load_module(self):
        layer = types.SimpleNamespace(
            name="Regular",
            associatedMasterId="m1",
            layerId="layer-1",
            annotations=[],
            userData={},
            change_log=[],
        )
        glyph = types.SimpleNamespace(layers=_Lookup({"m1": layer}), undo_log=[], userData={})
        layer.parent = glyph

        def begin_changes():
            layer.change_log.append("beginChanges")

        def end_changes():
            layer.change_log.append("endChanges")

        layer.beginChanges = begin_changes
        layer.endChanges = end_changes

        def begin_undo():
            glyph.undo_log.append("begin")

        def end_undo():
            glyph.undo_log.append("end")

        glyph.beginUndo = begin_undo
        glyph.endUndo = end_undo

        font = types.SimpleNamespace(
            familyName="Test Family",
            filepath="/tmp/Test.glyphs",
            glyphs=_Lookup({"A": glyph}),
            masters=[types.SimpleNamespace(id="m1")],
            selectedFontMaster=types.SimpleNamespace(id="m1"),
            userData={},
        )
        glyph.name = "A"
        glyphs_module = types.SimpleNamespace(
            Glyphs=types.SimpleNamespace(fonts=[font]),
            GSAnnotation=_FakeGSAnnotation,
            TEXT=1,
            ARROW=2,
            CIRCLE=3,
            PLUS=4,
            MINUS=5,
        )
        helpers_module = types.SimpleNamespace(
            _font_resolution_error=_font_resolution_error,
            _get_layer_id=lambda target_layer: getattr(target_layer, "layerId", ""),
            _glyphs_show_layer_link_fields=lambda *args, **kwargs: {},
            _layer_display_name=lambda _font, target_layer, master_id=None: getattr(target_layer, "name", None) or "Regular",
            _resolve_font_by_index=_resolve_font_by_index,
            _safe_json=json.dumps,
        )

        module_name = "glyphs_mcp_test_mcp_tools_annotations"
        spec = importlib.util.spec_from_file_location(module_name, _module_path())
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(
            sys.modules,
            {
                "GlyphsApp": glyphs_module,
                "mcp_runtime": types.SimpleNamespace(mcp=_FakeMCP()),
                "mcp_tool_helpers": helpers_module,
            },
        ):
            sys.modules.pop(module_name, None)
            assert spec.loader is not None
            spec.loader.exec_module(module)
        return module, layer, glyph, font

    def _font_registry(self, module, font, glyph, layer):
        return font.userData[module._target_registry_key(glyph, layer)]

    def test_registry_from_raw_materializes_objective_c_array_proxy_items(self) -> None:
        module, _layer, _glyph, _font = self._load_module()
        raw = {
            "owner": "Glyphs MCP",
            "kind": "agentAnnotations",
            "schemaVersion": 1,
            "items": _ProxyList(
                [
                    {
                        "annotationId": "mcp-ann-proxy",
                        "lastIndex": 0,
                        "fingerprint": {"text": "Proxy"},
                    }
                ]
            ),
        }

        registry = module._registry_from_raw(raw)

        self.assertEqual(len(registry["items"]), 1)
        self.assertEqual(registry["items"][0]["annotationId"], "mcp-ann-proxy")

    def test_add_annotation_stores_obvious_registry_without_prefixing_visible_text(self) -> None:
        module, layer, glyph, font = self._load_module()

        payload = json.loads(
            asyncio.run(
                module.add_glyph_annotation(
                    font_index=0,
                    glyph_name="A",
                    x=320,
                    y=510,
                    annotation_type="TEXT",
                    text="Adjust shoulder tension",
                    width=180,
                    role="commentText",
                    comment="Agent review note",
                )
            )
        )

        self.assertTrue(payload["success"])
        self.assertEqual(layer.annotations[0].text, "Adjust shoulder tension")
        self.assertEqual(glyph.undo_log, [])
        self.assertEqual(layer.change_log, ["beginChanges", "endChanges"])

        registry = self._font_registry(module, font, glyph, layer)
        self.assertEqual(registry["owner"], "Glyphs MCP")
        self.assertEqual(registry["kind"], "agentAnnotations")
        self.assertEqual(registry["schemaVersion"], 1)
        self.assertIn("safe to delete", registry["doNotEdit"])
        self.assertEqual(len(registry["items"]), 1)
        item = registry["items"][0]
        self.assertTrue(item["annotationId"].startswith("mcp-ann-"))
        self.assertEqual(item["role"], "commentText")
        self.assertEqual(item["comment"], "Agent review note")
        self.assertEqual(item["fingerprint"]["text"], "Adjust shoulder tension")

    def test_get_update_and_delete_managed_annotation_by_id(self) -> None:
        module, layer, glyph, font = self._load_module()

        added = json.loads(
            asyncio.run(module.add_glyph_annotation(font_index=0, glyph_name="A", x=10, y=20, text="First"))
        )
        annotation_id = added["annotation"]["annotationId"]

        listed = json.loads(
            asyncio.run(module.get_glyph_annotations(font_index=0, glyph_name="A", include_user_annotations=False))
        )
        self.assertEqual(listed["annotationCount"], 1)
        self.assertEqual(listed["annotations"][0]["annotationId"], annotation_id)

        updated = json.loads(
            asyncio.run(
                module.update_glyph_annotation(
                    font_index=0,
                    glyph_name="A",
                    annotation_id=annotation_id,
                    text="Updated",
                    x=11,
                )
            )
        )
        self.assertTrue(updated["success"])
        self.assertEqual(layer.annotations[0].text, "Updated")
        self.assertEqual(layer.annotations[0].position.x, 11)

        deleted = json.loads(
            asyncio.run(
                module.delete_glyph_annotation(
                    font_index=0,
                    glyph_name="A",
                    annotation_id=annotation_id,
                )
            )
        )
        self.assertTrue(deleted["success"])
        self.assertEqual(layer.annotations, [])
        self.assertNotIn(module._target_registry_key(glyph, layer), font.userData)

    def test_managed_annotation_registry_persists_through_proxy_user_data(self) -> None:
        module, layer, _glyph, _font = self._load_module()
        layer.userData = _ProxyUserData()

        added = json.loads(
            asyncio.run(module.add_glyph_annotation(font_index=0, glyph_name="A", x=10, y=20, text="First"))
        )
        annotation_id = added["annotation"]["annotationId"]

        listed = json.loads(
            asyncio.run(module.get_glyph_annotations(font_index=0, glyph_name="A", include_user_annotations=False))
        )
        self.assertEqual(listed["managedCount"], 1)
        self.assertEqual(listed["annotations"][0]["annotationId"], annotation_id)

        updated = json.loads(
            asyncio.run(
                module.update_glyph_annotation(
                    font_index=0,
                    glyph_name="A",
                    annotation_id=annotation_id,
                    text="Updated",
                )
            )
        )
        self.assertTrue(updated["success"])

        deleted = json.loads(
            asyncio.run(
                module.delete_glyph_annotation(
                    font_index=0,
                    glyph_name="A",
                    annotation_id=annotation_id,
                )
            )
        )
        self.assertTrue(deleted["success"])
        self.assertNotIn(module.REGISTRY_KEY, layer.userData)

    def test_add_annotation_assigns_annotations_when_append_proxy_drops_write(self) -> None:
        module, layer, _glyph, _font = self._load_module()
        layer.annotations = _NoOpAppendAnnotations()

        payload = json.loads(
            asyncio.run(module.add_glyph_annotation(font_index=0, glyph_name="A", x=10, y=20, text="First"))
        )

        self.assertTrue(payload["success"])
        self.assertEqual(len(layer.annotations), 1)
        self.assertEqual(layer.annotations[0].text, "First")

    def test_managed_annotation_registry_falls_back_to_parent_glyph_user_data(self) -> None:
        module, layer, glyph, font = self._load_module()
        layer.userData = _DroppingUserData()
        module.Glyphs.fonts[0] = _ReadOnlyUserDataFont(font, _DroppingUserData())

        added = json.loads(
            asyncio.run(module.add_glyph_annotation(font_index=0, glyph_name="A", x=10, y=20, text="First"))
        )
        annotation_id = added["annotation"]["annotationId"]
        layer_key = module._target_registry_key(glyph, layer)

        self.assertIn(layer_key, glyph.userData)
        layer.userData = _DroppingUserData()

        listed = json.loads(
            asyncio.run(module.get_glyph_annotations(font_index=0, glyph_name="A", include_user_annotations=False))
        )
        self.assertEqual(listed["managedCount"], 1)
        self.assertEqual(listed["annotations"][0]["annotationId"], annotation_id)

        deleted = json.loads(
            asyncio.run(
                module.delete_glyph_annotation(
                    font_index=0,
                    glyph_name="A",
                    annotation_id=annotation_id,
                )
            )
        )
        self.assertTrue(deleted["success"])
        self.assertNotIn(layer_key, glyph.userData)

    def test_clear_mcp_scope_preserves_user_annotations(self) -> None:
        module, layer, glyph, font = self._load_module()
        user_annotation = _FakeGSAnnotation()
        user_annotation.position = (1, 2)
        user_annotation.text = "User note"
        layer.annotations.append(user_annotation)

        json.loads(
            asyncio.run(module.add_glyph_annotation(font_index=0, glyph_name="A", x=10, y=20, text="MCP note"))
        )

        cleared = json.loads(
            asyncio.run(module.clear_glyph_annotations(font_index=0, glyph_name="A", scope="mcp"))
        )

        self.assertTrue(cleared["success"])
        self.assertEqual(cleared["deletedCount"], 1)
        self.assertEqual(cleared["preservedUserCount"], 1)
        self.assertEqual(len(layer.annotations), 1)
        self.assertEqual(layer.annotations[0].text, "User note")
        self.assertNotIn(module._target_registry_key(glyph, layer), font.userData)

    def test_group_annotations_share_generated_group_id(self) -> None:
        module, layer, glyph, font = self._load_module()
        annotations_json = json.dumps(
            [
                {"type": "CIRCLE", "x": 100, "y": 200, "role": "focusCircle"},
                {"type": "TEXT", "x": 130, "y": 240, "text": "Check this curve", "role": "commentText"},
            ]
        )

        grouped = json.loads(
            asyncio.run(
                module.add_glyph_annotation_group(
                    font_index=0,
                    glyph_name="A",
                    annotations_json=annotations_json,
                    comment="Linked review mark",
                )
            )
        )

        self.assertTrue(grouped["success"])
        self.assertTrue(grouped["groupId"].startswith("mcp-grp-"))
        self.assertEqual(len(grouped["annotations"]), 2)
        registry_items = self._font_registry(module, font, glyph, layer)["items"]
        self.assertEqual({item["groupId"] for item in registry_items}, {grouped["groupId"]})

        groups = json.loads(asyncio.run(module.get_glyph_annotation_groups(font_index=0, glyph_name="A")))
        self.assertEqual(groups["groupCount"], 1)
        self.assertEqual(groups["groups"][0]["groupId"], grouped["groupId"])
        self.assertEqual(len(groups["groups"][0]["annotations"]), 2)

    def test_reconciles_managed_annotation_after_user_index_shift(self) -> None:
        module, layer, _glyph, _font = self._load_module()
        added = json.loads(
            asyncio.run(module.add_glyph_annotation(font_index=0, glyph_name="A", x=10, y=20, text="MCP note"))
        )
        annotation_id = added["annotation"]["annotationId"]

        user_annotation = _FakeGSAnnotation()
        user_annotation.position = (5, 6)
        user_annotation.text = "User inserted"
        layer.annotations.insert(0, user_annotation)

        listed = json.loads(
            asyncio.run(module.get_glyph_annotations(font_index=0, glyph_name="A", include_user_annotations=False))
        )

        self.assertEqual(listed["annotationCount"], 1)
        self.assertEqual(listed["annotations"][0]["annotationId"], annotation_id)
        self.assertEqual(listed["annotations"][0]["index"], 1)

    def test_marks_registry_item_orphaned_when_visible_annotation_is_missing(self) -> None:
        module, layer, _glyph, _font = self._load_module()
        json.loads(asyncio.run(module.add_glyph_annotation(font_index=0, glyph_name="A", x=10, y=20, text="Gone")))
        layer.annotations[:] = []

        listed = json.loads(
            asyncio.run(module.get_glyph_annotations(font_index=0, glyph_name="A", include_user_annotations=False))
        )

        self.assertEqual(listed["annotationCount"], 0)
        self.assertEqual(listed["orphanedRegistryCount"], 1)


if __name__ == "__main__":
    unittest.main()
