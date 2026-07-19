"""Unit tests for mcp_tool_helpers (pure helpers).

These helpers intentionally avoid importing GlyphsApp so they can be tested in
the normal unit test runner.
"""

from __future__ import annotations

import json
import sys
import types
import unittest
from pathlib import Path


def _resources_dir() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Resources"
    )


class McpToolHelpersTests(unittest.TestCase):
    def test_node_orientation_uses_raw_objc_value(self) -> None:
        class InstanceMethods:
            @staticmethod
            def orientation():
                return 2

        node = types.SimpleNamespace(
            orientation=lambda: "native selector",
            pyobjc_instanceMethods=InstanceMethods(),
        )

        self.assertEqual(helpers._node_orientation(node), ("center", 2))

    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(_resources_dir()))
        global helpers  # noqa: PLW0603 - simple test import
        import mcp_tool_helpers as helpers  # type: ignore

    def test_round_half_away_from_zero(self) -> None:
        self.assertEqual(helpers._round_half_away_from_zero(0.0), 0)
        self.assertEqual(helpers._round_half_away_from_zero(0.49), 0)
        self.assertEqual(helpers._round_half_away_from_zero(0.5), 1)
        self.assertEqual(helpers._round_half_away_from_zero(1.5), 2)
        self.assertEqual(helpers._round_half_away_from_zero(-0.5), -1)
        self.assertEqual(helpers._round_half_away_from_zero(-1.5), -2)

    def test_sanitize_for_json_nested_objects(self) -> None:
        class Weird:
            def __str__(self) -> str:  # pragma: no cover - exercised via sanitizer
                return "weird"

        payload = {
            "a": 1,
            "b": {1, 2, 3},
            "c": ("x", Weird()),
            "d": {"k": Weird()},
        }

        sanitized = helpers._sanitize_for_json(payload)
        # Must be JSON-serializable without throwing.
        encoded = json.dumps(sanitized)
        self.assertIn('"a"', encoded)
        self.assertIn('"weird"', encoded)

    def test_font_format_metadata_supports_glyphs_3_and_4_values(self) -> None:
        glyphs_3 = types.SimpleNamespace(formatVersion=3, appVersion="3300")
        glyphs_4 = types.SimpleNamespace(
            formatVersion=lambda: 4,
            appVersion=lambda: 4012,
        )

        self.assertEqual(
            helpers._font_format_metadata(glyphs_3),
            {"formatVersion": 3, "lastSavedAppVersion": "3300"},
        )
        self.assertEqual(
            helpers._font_format_metadata(glyphs_4),
            {"formatVersion": 4, "lastSavedAppVersion": "4012"},
        )

    def test_font_resolution_error_includes_format_metadata(self) -> None:
        font = types.SimpleNamespace(
            familyName="Glyphs Four",
            filepath="/tmp/GlyphsFour.glyphs",
            formatVersion=4,
            appVersion="4012",
        )

        payload = helpers._font_resolution_error(2, [font])

        self.assertEqual(payload["availableFonts"][0]["formatVersion"], 4)
        self.assertEqual(
            payload["availableFonts"][0]["lastSavedAppVersion"], "4012"
        )

    def test_component_transform_values_do_not_iterate_proxy(self) -> None:
        class NonIterableTransform:
            def __iter__(self):
                raise AssertionError("component transform must not be iterated")

            def __getitem__(self, index):
                raise AssertionError("component transform proxy must not be indexed")

        component = types.SimpleNamespace(
            transform=NonIterableTransform(),
            position=types.SimpleNamespace(x=10, y=0),
            scale=types.SimpleNamespace(x=0.25, y=0.25),
            rotation=0,
        )

        self.assertEqual(
            helpers._component_transform_values(component),
            [0.25, 0.0, 0.0, 0.25, 10.0, 0.0],
        )

    def test_component_transform_values_accept_plain_python_sequence(self) -> None:
        self.assertEqual(
            helpers._component_transform_values((0.5, 0.0, 0.0, 0.75, 25.0, 12.0)),
            [0.5, 0.0, 0.0, 0.75, 25.0, 12.0],
        )

    def test_layer_components_prefers_shapes_over_hostile_components_proxy(self) -> None:
        class HostileComponents:
            def __iter__(self):
                raise AssertionError("layer.components must not be iterated")

            def __len__(self):
                raise AssertionError("layer.components must not be sized")

        component = types.SimpleNamespace(componentName="acute")
        path = types.SimpleNamespace(nodes=[])
        layer = types.SimpleNamespace(shapes=[path, component], components=HostileComponents())

        self.assertEqual(helpers._layer_components(layer), [component])

    def test_layer_components_falls_back_when_shapes_has_no_component_data(self) -> None:
        component = types.SimpleNamespace(componentName="acute")
        path = types.SimpleNamespace(nodes=[])
        layer = types.SimpleNamespace(shapes=[path], components=[component])
        previous_glyphs_app = sys.modules.get("GlyphsApp")

        try:
            sys.modules["GlyphsApp"] = types.SimpleNamespace(
                Glyphs=types.SimpleNamespace(versionNumber=4.0)
            )
            self.assertEqual(helpers._layer_components(layer), [component])
        finally:
            if previous_glyphs_app is None:
                sys.modules.pop("GlyphsApp", None)
            else:
                sys.modules["GlyphsApp"] = previous_glyphs_app

    def test_layer_components_skips_components_fallback_in_glyphs3(self) -> None:
        class HostileComponents:
            def __len__(self):
                raise AssertionError("Glyphs 3 layer.components fallback must not be touched")

            def __getitem__(self, _index):
                raise AssertionError("Glyphs 3 layer.components fallback must not be touched")

            def __iter__(self):
                raise AssertionError("Glyphs 3 layer.components fallback must not be touched")

        path = types.SimpleNamespace(nodes=[])
        layer = types.SimpleNamespace(shapes=[path], components=HostileComponents())
        previous_glyphs_app = sys.modules.get("GlyphsApp")

        try:
            sys.modules["GlyphsApp"] = types.SimpleNamespace(
                Glyphs=types.SimpleNamespace(versionNumber=3.5)
            )
            self.assertEqual(helpers._layer_components(layer), [])
        finally:
            if previous_glyphs_app is None:
                sys.modules.pop("GlyphsApp", None)
            else:
                sys.modules["GlyphsApp"] = previous_glyphs_app

    def test_append_component_shape_does_not_use_components_fallback_in_glyphs3(self) -> None:
        class IgnoringShapes(list):
            def append(self, _item):
                return None

        class Layer:
            def __init__(self) -> None:
                self._shapes = IgnoringShapes()

            @property
            def shapes(self):
                return self._shapes

            @shapes.setter
            def shapes(self, _value):
                raise RuntimeError("shapes assignment ignored")

            @property
            def components(self):
                raise AssertionError("Glyphs 3 component append fallback must not be touched")

        previous_glyphs_app = sys.modules.get("GlyphsApp")

        try:
            sys.modules["GlyphsApp"] = types.SimpleNamespace(
                Glyphs=types.SimpleNamespace(versionNumber=3.5)
            )
            self.assertFalse(
                helpers._append_layer_shape_unmanaged(
                    Layer(), types.SimpleNamespace(componentName="acute")
                )
            )
        finally:
            if previous_glyphs_app is None:
                sys.modules.pop("GlyphsApp", None)
            else:
                sys.modules["GlyphsApp"] = previous_glyphs_app

    def test_run_on_main_thread_reuses_objc_helper_class(self) -> None:
        class FakeObjCSuper:
            def __init__(self, obj) -> None:
                self.obj = obj

            def init(self):
                return self.obj

        class FakeObjC:
            def __init__(self) -> None:
                self.classes = {}

            def super(self, _cls, obj):
                return FakeObjCSuper(obj)

            def lookUpClass(self, name):
                if name not in self.classes:
                    raise RuntimeError("not registered")
                return self.classes[name]

        class FakeNSObject:
            @classmethod
            def alloc(cls):
                return cls.__new__(cls)

            def performSelectorOnMainThread_withObject_waitUntilDone_(self, selector, obj, _wait):
                getattr(self, selector.replace(":", "_"))(obj)

        class FakeThread:
            @staticmethod
            def isMainThread():
                return False

        original_objc = helpers.objc
        original_nsobject = helpers.NSObject
        original_nsthread = helpers.NSThread
        original_helper_class = helpers._OBJC_MAIN_THREAD_HELPER_CLASS
        fake_objc = FakeObjC()

        try:
            helpers.objc = fake_objc
            helpers.NSObject = FakeNSObject
            helpers.NSThread = FakeThread
            helpers._OBJC_MAIN_THREAD_HELPER_CLASS = None

            self.assertEqual(helpers._run_on_main_thread(lambda: "first"), "first")
            first_class = helpers._OBJC_MAIN_THREAD_HELPER_CLASS
            self.assertIsNotNone(first_class)

            self.assertEqual(helpers._run_on_main_thread(lambda: "second"), "second")
            self.assertIs(helpers._OBJC_MAIN_THREAD_HELPER_CLASS, first_class)

            fake_objc.classes[helpers._OBJC_MAIN_THREAD_HELPER_CLASS_NAME] = first_class
            helpers._OBJC_MAIN_THREAD_HELPER_CLASS = None
            self.assertEqual(helpers._run_on_main_thread(lambda: "reloaded"), "reloaded")
            self.assertIs(helpers._OBJC_MAIN_THREAD_HELPER_CLASS, first_class)
        finally:
            helpers.objc = original_objc
            helpers.NSObject = original_nsobject
            helpers.NSThread = original_nsthread
            helpers._OBJC_MAIN_THREAD_HELPER_CLASS = original_helper_class

    def test_open_fonts_falls_back_when_fonts_proxy_raises(self) -> None:
        font = types.SimpleNamespace(familyName="Doc Font", filepath="/tmp/doc.glyphs")

        class BrokenGlyphs:
            @property
            def fonts(self):
                raise TypeError("broken private font proxy")

        glyphs = BrokenGlyphs()
        glyphs.documents = [types.SimpleNamespace(font=font)]
        glyphs.currentDocument = types.SimpleNamespace(font=font)
        glyphs.font = font

        fonts = helpers._open_fonts_from_glyphs(glyphs)

        self.assertEqual(fonts, [font])

    def test_open_fonts_falls_back_to_cocoa_documents_when_glyphs_proxies_raise(self) -> None:
        first = types.SimpleNamespace(familyName="Archivo", filepath="/tmp/Archivo.glyphs")
        second = types.SimpleNamespace(familyName="Gee gee", filepath="/tmp/Gee gee.glyphspackage")
        third = types.SimpleNamespace(familyName="Inter", filepath="/tmp/Inter-Roman.glyphspackage")

        class BrokenGlyphs:
            @property
            def fonts(self):
                raise TypeError("broken font proxy")

            @property
            def documents(self):
                raise TypeError("broken document proxy")

        class FakeNSDocumentController:
            @staticmethod
            def sharedDocumentController():
                return types.SimpleNamespace(
                    documents=lambda: [
                        types.SimpleNamespace(font=first),
                        types.SimpleNamespace(font=second),
                        types.SimpleNamespace(font=third),
                    ]
                )

        original_appkit = sys.modules.get("AppKit")
        sys.modules["AppKit"] = types.SimpleNamespace(NSDocumentController=FakeNSDocumentController)
        try:
            glyphs = BrokenGlyphs()
            glyphs.currentDocument = types.SimpleNamespace(font=second)
            glyphs.font = second

            fonts = helpers._open_fonts_from_glyphs(glyphs)
        finally:
            if original_appkit is None:
                sys.modules.pop("AppKit", None)
            else:
                sys.modules["AppKit"] = original_appkit

        self.assertEqual(fonts, [first, second, third])

    def test_font_context_source_uses_cocoa_documents_when_glyphs_proxies_raise(self) -> None:
        first = types.SimpleNamespace(familyName="Archivo", filepath="/tmp/Archivo.glyphs")
        second = types.SimpleNamespace(familyName="Inter", filepath="/tmp/Inter.glyphspackage")

        class BrokenGlyphs:
            @property
            def fonts(self):
                raise TypeError("broken font proxy")

            @property
            def documents(self):
                raise TypeError("broken document proxy")

        class FakeNSDocumentController:
            @staticmethod
            def sharedDocumentController():
                return types.SimpleNamespace(
                    documents=lambda: [
                        types.SimpleNamespace(font=first),
                        types.SimpleNamespace(font=second),
                    ]
                )

        namespace = {}
        original_appkit = sys.modules.get("AppKit")
        sys.modules["AppKit"] = types.SimpleNamespace(NSDocumentController=FakeNSDocumentController)
        try:
            exec(helpers._font_context_source(), namespace)
            resolved = namespace["__glyphs_mcp_font_by_index"](BrokenGlyphs(), 1)
        finally:
            if original_appkit is None:
                sys.modules.pop("AppKit", None)
            else:
                sys.modules["AppKit"] = original_appkit

        self.assertIs(resolved, second)

    def test_open_fonts_preserves_fonts_order_then_adds_public_fallbacks(self) -> None:
        first = types.SimpleNamespace(familyName="First", filepath="/tmp/first.glyphs")
        second = types.SimpleNamespace(familyName="Second", filepath="/tmp/second.glyphs")
        third = types.SimpleNamespace(familyName="Third", filepath="/tmp/third.glyphs")
        glyphs = types.SimpleNamespace(
            fonts=[first, second],
            documents=[types.SimpleNamespace(font=second), types.SimpleNamespace(font=third)],
            currentDocument=types.SimpleNamespace(font=third),
            font=first,
        )

        fonts = helpers._open_fonts_from_glyphs(glyphs)

        self.assertEqual(fonts, [first, second, third])

    def test_open_fonts_uses_current_document_and_active_font_without_documents(self) -> None:
        current = types.SimpleNamespace(familyName="Current", filepath="/tmp/current.glyphs")
        active = types.SimpleNamespace(familyName="Active", filepath="/tmp/active.glyphs")
        glyphs = types.SimpleNamespace(
            currentDocument=types.SimpleNamespace(font=current),
            font=active,
        )

        fonts = helpers._open_fonts_from_glyphs(glyphs)

        self.assertEqual(fonts, [current, active])

    def test_resolve_font_invalid_index_returns_actionable_error(self) -> None:
        font = types.SimpleNamespace(familyName="Only", filepath="/tmp/only.glyphs")
        glyphs = types.SimpleNamespace(fonts=[font])

        resolved, fonts = helpers._resolve_font_by_index(glyphs, 2)
        error = helpers._font_resolution_error(2, fonts, ok_key="ok")

        self.assertIsNone(resolved)
        self.assertFalse(error["ok"])
        self.assertEqual(error["fontIndex"], 2)
        self.assertEqual(error["availableFontCount"], 1)
        self.assertEqual(error["availableFonts"][0]["fontIndex"], 0)
        self.assertIn("run list_open_fonts", helpers._font_resolution_error(0, [], ok_key="success")["error"])

    def test_is_active_font_matches_by_identity_or_filepath(self) -> None:
        active = types.SimpleNamespace(familyName="Active", filepath="/tmp/shared.glyphs")
        same_path = types.SimpleNamespace(familyName="Same Path", filepath="/tmp/shared.glyphs")
        other = types.SimpleNamespace(familyName="Other", filepath="/tmp/other.glyphs")
        glyphs = types.SimpleNamespace(font=active)

        self.assertTrue(helpers._is_active_font(glyphs, active))
        self.assertTrue(helpers._is_active_font(glyphs, same_path))
        self.assertFalse(helpers._is_active_font(glyphs, other))

    def test_get_component_automatic_prefers_present_flags(self) -> None:
        class HasAutomatic:
            automatic = True

        class HasAutomaticAlignment:
            automaticAlignment = False

        class HasNeither:
            pass

        self.assertIs(helpers._get_component_automatic(HasAutomatic()), True)
        self.assertIs(helpers._get_component_automatic(HasAutomaticAlignment()), False)
        self.assertIsNone(helpers._get_component_automatic(HasNeither()))

    def test_coerce_numeric_handles_callables_and_errors(self) -> None:
        self.assertEqual(helpers._coerce_numeric("3.5"), 3.5)
        self.assertEqual(helpers._coerce_numeric(2), 2.0)

        class CallableValue:
            def __call__(self):  # pragma: no cover - used by helper
                return "4"

        self.assertEqual(helpers._coerce_numeric(CallableValue()), 4.0)

        class BrokenCallable:
            def __call__(self):  # pragma: no cover - used by helper
                raise RuntimeError("boom")

        self.assertIsNone(helpers._coerce_numeric(BrokenCallable()))

        class NotNumeric:
            def __str__(self) -> str:  # pragma: no cover - helper ignores
                return "nope"

        self.assertIsNone(helpers._coerce_numeric(NotNumeric()))

    def test_clear_layer_paths_preserves_non_path_shapes(self) -> None:
        class FakePath:
            def __init__(self) -> None:
                self.nodes = [object()]

        class FakeComponent:
            pass

        path = FakePath()
        component = FakeComponent()
        layer = type("Layer", (), {"shapes": [path, component]})()

        helpers._clear_layer_paths(layer)

        self.assertEqual(layer.shapes, [component])

    def test_new_glyph_falls_back_when_positional_constructor_fails(self) -> None:
        class FakeGSGlyph:
            def __init__(self, *args) -> None:
                if args:
                    raise TypeError("positional constructor unavailable")
                self.name = ""

        glyph = helpers._new_glyph(FakeGSGlyph, "mcpProbe")

        self.assertEqual(glyph.name, "mcpProbe")

    def test_new_glyph_disables_auto_name_for_named_constructor(self) -> None:
        calls = []

        class FakeGSGlyph:
            def __init__(self, *args) -> None:
                calls.append(args)
                self.name = "normalized" if args and len(args) == 1 else ""

        glyph = helpers._new_glyph(FakeGSGlyph, "mcpProbe")

        self.assertEqual(calls[0], ("mcpProbe", False))
        self.assertEqual(glyph.name, "mcpProbe")

    def test_append_font_glyph_returns_verified_lookup(self) -> None:
        class FakeGlyphs(dict):
            def append(self, glyph) -> None:
                self[glyph.name] = glyph

        glyph = type("Glyph", (), {"name": ""})()
        font = type("Font", (), {"glyphs": FakeGlyphs()})()

        self.assertIs(helpers._append_font_glyph(font, glyph, "mcpProbe"), glyph)
        self.assertIn("mcpProbe", font.glyphs)

    def test_append_font_glyph_brackets_font_update_interface(self) -> None:
        log = []

        class FakeGlyphs(dict):
            def append(self, glyph) -> None:
                log.append("append")
                self[glyph.name] = glyph

        class FakeFont:
            def __init__(self) -> None:
                self.glyphs = FakeGlyphs()

            def disableUpdateInterface(self) -> None:
                log.append("disable")

            def enableUpdateInterface(self) -> None:
                log.append("enable")

        glyph = type("Glyph", (), {"name": ""})()
        font = FakeFont()

        self.assertIs(helpers._append_font_glyph(font, glyph, "mcpProbe"), glyph)
        self.assertEqual(log, ["disable", "append", "enable"])

    def test_append_font_glyph_closes_update_interface_on_failure(self) -> None:
        log = []

        class RejectingGlyphs(dict):
            def append(self, _glyph) -> None:
                log.append("append")
                raise RuntimeError("append failed")

        class FakeFont:
            def __init__(self) -> None:
                self.glyphs = RejectingGlyphs()

            def disableUpdateInterface(self) -> None:
                log.append("disable")

            def enableUpdateInterface(self) -> None:
                log.append("enable")

        glyph = type("Glyph", (), {"name": ""})()
        font = FakeFont()

        self.assertIsNone(helpers._append_font_glyph(font, glyph, "mcpProbe"))
        self.assertEqual(log, ["disable", "append", "enable"])

    def test_delete_font_glyph_brackets_font_update_interface(self) -> None:
        log = []

        class FakeGlyphs(dict):
            def __delitem__(self, key) -> None:
                log.append("delete")
                super().__delitem__(key)

            def __getitem__(self, key):
                return self.get(key)

        class FakeFont:
            def __init__(self) -> None:
                self.glyphs = FakeGlyphs({"mcpProbe": object(), "A": object()})

            def disableUpdateInterface(self) -> None:
                log.append("disable")

            def enableUpdateInterface(self) -> None:
                log.append("enable")

        font = FakeFont()

        self.assertTrue(helpers._delete_font_glyph(font, "mcpProbe"))
        self.assertEqual(log, ["disable", "delete", "enable"])
        self.assertIn("A", font.glyphs)
        self.assertNotIn("mcpProbe", font.glyphs)

    def test_new_anchor_falls_back_when_positional_constructor_fails(self) -> None:
        class FakeGSAnchor:
            def __init__(self, *args) -> None:
                if args:
                    raise TypeError("positional constructor unavailable")
                self.name = ""
                self.position = None

        anchor = helpers._new_anchor(FakeGSAnchor, "top", 10, 20)

        self.assertEqual(anchor.name, "top")
        self.assertEqual(anchor.position, (10.0, 20.0))

    def test_replace_layer_paths_uses_shapes_and_preserves_components(self) -> None:
        class FakePath:
            def __init__(self, node_count=1) -> None:
                self.nodes = [object() for _ in range(node_count)]

        class FakeComponent:
            pass

        class FakeLayer:
            def __init__(self) -> None:
                self.component = FakeComponent()
                self.shapes = [FakePath(), self.component]

            @property
            def paths(self):
                return [shape for shape in self.shapes if hasattr(shape, "nodes")]

        layer = FakeLayer()
        new_path = FakePath(node_count=3)

        result = helpers._replace_layer_paths(layer, [new_path])

        self.assertTrue(result["ok"])
        self.assertEqual(layer.shapes, [new_path, layer.component])
        self.assertEqual(result["pathCount"], 1)
        self.assertEqual(result["nodeCount"], 3)

    def test_apply_path_specs_updates_matching_topology_in_place(self) -> None:
        class Point:
            def __init__(self, x=0, y=0) -> None:
                self.x = float(x)
                self.y = float(y)

        class Node:
            def __init__(self, x=0, y=0, raw_type=1) -> None:
                self._position = Point(x, y)
                self.rawType = raw_type
                self.rawConnection = 0
                self.smooth = False
                self.orientation = 0
                self.name = None
                self.attributes = {"hoi": {"wght": {"linear": True}}}
                self.userData = {"node": "metadata"}

            @property
            def position(self):
                return self._position

            @position.setter
            def position(self, value):
                self._position = Point(value[0], value[1])

            @property
            def type(self):
                return {1: "line", 35: "curve"}.get(self.rawType, "line")

            @type.setter
            def type(self, value):
                if isinstance(value, int):
                    self.rawType = value
                else:
                    self.rawType = {"line": 1, "curve": 35}[value]

            @property
            def connection(self):
                return self.rawConnection

            @connection.setter
            def connection(self, value):
                self.rawConnection = int(value)

        class Path:
            def __init__(self):
                self.nodes = [Node(10, 20), Node(30, 40)]
                self.closed = True
                self.locked = True
                self.attributes = {"gradient": {"type": "linear"}, "group": "g1"}
                self.userData = {"path": "metadata"}

        class Layer:
            def __init__(self):
                self.shapes = [Path()]
                self.width = 500
                self.leftSideBearing = 40
                self.rightSideBearing = 60

            @property
            def paths(self):
                return [shape for shape in self.shapes if hasattr(shape, "nodes")]

        layer = Layer()
        original_path = layer.paths[0]
        original_nodes = list(original_path.nodes)
        specs = [
            {
                "closed": True,
                "locked": True,
                "nodes": [
                    {"x": 11, "y": 21, "type": "line", "rawType": 1},
                    {"x": 31, "y": 41, "type": "line", "rawType": 1},
                ],
            }
        ]

        result = helpers._apply_path_specs_and_metrics(
            layer, specs, Path, Node, width=510
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["pathEditMode"], "inPlace")
        self.assertIs(layer.paths[0], original_path)
        self.assertEqual(layer.paths[0].nodes, original_nodes)
        self.assertEqual(layer.paths[0].attributes["group"], "g1")
        self.assertIn("hoi", layer.paths[0].nodes[0].attributes)
        self.assertEqual(layer.width, 510)

    def test_apply_path_specs_topology_rewrite_preserves_shape_order_and_metadata(self) -> None:
        class Point:
            def __init__(self, x=0, y=0) -> None:
                self.x = float(x)
                self.y = float(y)

        class Node:
            def __init__(self, x=0, y=0, raw_type=1) -> None:
                self._position = Point(x, y)
                self.rawType = raw_type
                self.rawConnection = 0
                self.smooth = False
                self.orientation = 0
                self.name = None
                self.attributes = {"hoi": {"wght": {"linear": True}}}
                self.userData = {"node": "metadata"}

            @property
            def position(self):
                return self._position

            @position.setter
            def position(self, value):
                self._position = Point(value[0], value[1])

            @property
            def type(self):
                return {1: "line", 35: "curve"}.get(self.rawType, "line")

            @type.setter
            def type(self, value):
                if isinstance(value, int):
                    self.rawType = value
                else:
                    self.rawType = {"line": 1, "curve": 35}.get(value, 1)

            @property
            def connection(self):
                return self.rawConnection

            @connection.setter
            def connection(self, value):
                self.rawConnection = int(value)

            def copy(self):
                copied = Node(
                    self.position.x, self.position.y, raw_type=self.rawType
                )
                copied.rawConnection = self.rawConnection
                copied.smooth = self.smooth
                copied.orientation = self.orientation
                copied.name = self.name
                copied.attributes = json.loads(json.dumps(self.attributes))
                copied.userData = dict(self.userData)
                return copied

        class Path:
            def __init__(self, nodes=None, token="path"):
                self.nodes = list(nodes or [])
                self.closed = True
                self.locked = True
                self.attributes = {
                    "gradient": {"type": "linear"},
                    "fillColor": [1, 0, 0, 1],
                    "group": "g1",
                }
                self.userData = {"path": "metadata"}
                self.unknownProperty = token

            def copy(self):
                copied = Path(
                    [node.copy() for node in self.nodes],
                    token=self.unknownProperty,
                )
                copied.closed = self.closed
                copied.locked = self.locked
                copied.attributes = json.loads(json.dumps(self.attributes))
                copied.userData = dict(self.userData)
                return copied

        class Component:
            componentName = "acute"

        class GSImage:
            pass

        class GSShapeGroup:
            def __init__(self):
                self.groupId = "g1"
                self.attributes = {}
                self.userData = {}

        class Layer:
            def __init__(self):
                self.first = Path([Node(0, 0), Node(100, 0)], token="first")
                self.second = Path([Node(0, 100), Node(100, 100)], token="second")
                self.component = Component()
                self.image = GSImage()
                self.group = GSShapeGroup()
                self.shapes = [
                    self.first,
                    self.component,
                    self.image,
                    self.group,
                    self.second,
                ]
                self.width = 500
                self.leftSideBearing = 40
                self.rightSideBearing = 60

            @property
            def paths(self):
                return [shape for shape in self.shapes if hasattr(shape, "nodes")]

        layer = Layer()
        non_paths = [layer.component, layer.image, layer.group]
        specs = [
            {
                "closed": True,
                "locked": True,
                "nodes": [
                    {"x": 1, "y": 2, "type": "line"},
                    {"x": 101, "y": 2, "type": "line"},
                    {"x": 101, "y": 50, "type": "line"},
                ],
            },
            {
                "closed": True,
                "locked": True,
                "nodes": [
                    {"x": 2, "y": 102, "type": "line"},
                    {"x": 102, "y": 102, "type": "line"},
                ],
            },
        ]

        result = helpers._apply_path_specs_and_metrics(
            layer, specs, Path, Node
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["pathEditMode"], "topologyRewrite")
        self.assertEqual(
            layer.shapes[1:4],
            non_paths,
        )
        self.assertIsNot(layer.paths[0], layer.first)
        self.assertEqual(layer.paths[0].unknownProperty, "first")
        self.assertEqual(layer.paths[0].attributes["group"], "g1")
        self.assertIn("gradient", layer.paths[0].attributes)
        self.assertIn("hoi", layer.paths[0].nodes[0].attributes)
        self.assertEqual(layer.paths[0].userData, {"path": "metadata"})

        diagnostics = helpers._layer_shape_summary(layer)
        self.assertEqual(diagnostics["shapeTypeCounts"]["shapeGroup"], 1)
        self.assertEqual(diagnostics["shapeTypeCounts"]["image"], 1)
        self.assertEqual(diagnostics["groupedShapeCount"], 2)
        self.assertIn("gradient", diagnostics["shapeAttributeKeys"])
        self.assertTrue(diagnostics["compatibilityWarnings"])

    def test_apply_path_specs_rejects_unknown_raw_type_before_mutation(self) -> None:
        class Point:
            def __init__(self, x=0, y=0) -> None:
                self.x = float(x)
                self.y = float(y)

        class Node:
            def __init__(self):
                self._position = Point(10, 20)
                self.rawType = 77
                self.rawConnection = 0
                self.smooth = False
                self.orientation = 0
                self.name = None

            @property
            def position(self):
                return self._position

            @position.setter
            def position(self, value):
                self._position = Point(value[0], value[1])

            def copy(self):
                copied = Node()
                copied.position = (self.position.x, self.position.y)
                return copied

        class Path:
            def __init__(self):
                self.nodes = [Node()]
                self.closed = True
                self.locked = False

            def copy(self):
                copied = Path()
                copied.nodes = [node.copy() for node in self.nodes]
                return copied

        class Layer:
            def __init__(self):
                self.shapes = [Path()]
                self.width = 500
                self.leftSideBearing = 40
                self.rightSideBearing = 60
                self.change_count = 0

            @property
            def paths(self):
                return [shape for shape in self.shapes if hasattr(shape, "nodes")]

            def beginChanges(self):
                self.change_count += 1

        layer = Layer()
        original_path = layer.paths[0]
        original_position = (
            original_path.nodes[0].position.x,
            original_path.nodes[0].position.y,
        )

        result = helpers._apply_path_specs_and_metrics(
            layer,
            [
                {
                    "closed": True,
                    "nodes": [
                        {"x": 99, "y": 20, "type": "line"}
                    ],
                }
            ],
            Path,
            Node,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "Unsafe path rewrite rejected")
        self.assertTrue(result["rolledBack"])
        self.assertEqual(layer.change_count, 0)
        self.assertIs(layer.paths[0], original_path)
        self.assertEqual(
            (
                original_path.nodes[0].position.x,
                original_path.nodes[0].position.y,
            ),
            original_position,
        )

    def test_apply_path_specs_rolls_back_after_verification_failure(self) -> None:
        class Point:
            def __init__(self, x=0, y=0) -> None:
                self.x = float(x)
                self.y = float(y)

        class Node:
            def __init__(self, x=0, y=0):
                self._position = Point(x, y)
                self.rawType = 1
                self.rawConnection = 0
                self.smooth = False
                self.orientation = 0
                self.name = None

            @property
            def position(self):
                return self._position

            @position.setter
            def position(self, value):
                self._position = Point(value[0], value[1])

            @property
            def type(self):
                return "line"

            @type.setter
            def type(self, _value):
                self.rawType = 1

            def copy(self):
                return Node(self.position.x, self.position.y)

        class Path:
            def __init__(self, nodes=None):
                self.nodes = list(nodes or [])
                self.closed = True
                self.locked = False
                self.attributes = {"group": "g1"}

            def copy(self):
                copied = Path([node.copy() for node in self.nodes])
                copied.attributes = dict(self.attributes)
                return copied

        class Component:
            componentName = "acute"

        class Layer:
            def __init__(self):
                self.original_path = Path([Node(0, 0)])
                self.component = Component()
                self._shapes = [self.original_path, self.component]
                self._shape_writes = 0
                self.width = 500
                self.leftSideBearing = 40
                self.rightSideBearing = 60

            @property
            def shapes(self):
                return self._shapes

            @shapes.setter
            def shapes(self, value):
                self._shape_writes += 1
                self._shapes = list(value)
                if self._shape_writes == 1:
                    self.paths[0].nodes[0].position = (999, 999)

            @property
            def paths(self):
                return [shape for shape in self._shapes if hasattr(shape, "nodes")]

        layer = Layer()
        original_shapes = list(layer.shapes)
        result = helpers._apply_path_specs_and_metrics(
            layer,
            [
                {
                    "closed": True,
                    "nodes": [
                        {"x": 10, "y": 20, "type": "line"},
                        {"x": 30, "y": 40, "type": "line"},
                    ],
                }
            ],
            Path,
            Node,
            width=700,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "Path write verification failed")
        self.assertTrue(result["rolledBack"])
        self.assertEqual(layer.shapes, original_shapes)
        self.assertIs(layer.shapes[0], layer.original_path)
        self.assertIs(layer.shapes[1], layer.component)
        self.assertEqual(layer.width, 500)

    def test_append_layer_shape_prefers_shapes_for_components(self) -> None:
        class RejectingComponents(list):
            def append(self, _item):  # pragma: no cover - should not be called
                raise AssertionError("components append should not be used")

        class FakeComponent:
            pass

        layer = types.SimpleNamespace(shapes=[], components=RejectingComponents())
        component = FakeComponent()

        self.assertTrue(helpers._append_layer_shape(layer, component))
        self.assertEqual(layer.shapes, [component])

    def test_append_layer_shape_brackets_public_layer_changes_without_glyph_undo(self) -> None:
        log = []

        class FakeGlyph:
            def beginUndo(self) -> None:
                log.append("glyph.beginUndo")

            def endUndo(self) -> None:
                log.append("glyph.endUndo")

        class FakeLayer:
            def __init__(self) -> None:
                self.parent = FakeGlyph()
                self.shapes = []

            def beginChanges(self) -> None:
                log.append("layer.beginChanges")

            def endChanges(self) -> None:
                log.append("layer.endChanges")

        component = type("Component", (), {})()
        layer = FakeLayer()

        self.assertTrue(helpers._append_layer_shape(layer, component))
        self.assertEqual(layer.shapes, [component])
        self.assertEqual(
            log,
            [
                "layer.beginChanges",
                "layer.endChanges",
            ],
        )

    def test_replace_layer_paths_brackets_public_layer_changes_without_glyph_undo(self) -> None:
        log = []

        class FakeGlyph:
            def beginUndo(self) -> None:
                log.append("glyph.beginUndo")

            def endUndo(self) -> None:
                log.append("glyph.endUndo")

        class FakePath:
            def __init__(self, node_count=1) -> None:
                self.nodes = [object() for _ in range(node_count)]

        class FakeLayer:
            def __init__(self) -> None:
                self.parent = FakeGlyph()
                self.shapes = []

            @property
            def paths(self):
                return [shape for shape in self.shapes if hasattr(shape, "nodes")]

            def beginChanges(self) -> None:
                log.append("layer.beginChanges")

            def endChanges(self) -> None:
                log.append("layer.endChanges")

        layer = FakeLayer()
        path = FakePath(node_count=4)

        result = helpers._replace_layer_paths(layer, [path])

        self.assertTrue(result["ok"])
        self.assertEqual(result["pathCount"], 1)
        self.assertEqual(
            log,
            [
                "layer.beginChanges",
                "layer.endChanges",
            ],
        )

    def test_replace_layer_paths_and_metrics_uses_one_layer_change_block(self) -> None:
        log = []

        class FakePath:
            def __init__(self, node_count=1) -> None:
                self.nodes = [object() for _ in range(node_count)]

        class FakeLayer:
            def __init__(self) -> None:
                self.shapes = []
                self.width = 0
                self.leftSideBearing = 0
                self.rightSideBearing = 0

            @property
            def paths(self):
                return [shape for shape in self.shapes if hasattr(shape, "nodes")]

            def beginChanges(self) -> None:
                log.append("layer.beginChanges")

            def endChanges(self) -> None:
                log.append("layer.endChanges")

        layer = FakeLayer()
        path = FakePath(node_count=4)

        result = helpers._replace_layer_paths_and_metrics(
            layer,
            [path],
            width=400,
            left_sidebearing=100,
            right_sidebearing=100,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(layer.width, 400)
        self.assertEqual(layer.leftSideBearing, 100)
        self.assertEqual(layer.rightSideBearing, 100)
        self.assertEqual(log, ["layer.beginChanges", "layer.endChanges"])

    def test_append_layer_anchor_brackets_public_layer_changes_without_glyph_undo(self) -> None:
        log = []

        class FakeGlyph:
            def beginUndo(self) -> None:
                log.append("glyph.beginUndo")

            def endUndo(self) -> None:
                log.append("glyph.endUndo")

        class FakeLayer:
            def __init__(self) -> None:
                self.parent = FakeGlyph()
                self.anchors = {}

            def beginChanges(self) -> None:
                log.append("layer.beginChanges")

            def endChanges(self) -> None:
                log.append("layer.endChanges")

        anchor = types.SimpleNamespace(name="top")
        layer = FakeLayer()

        self.assertTrue(helpers._append_layer_anchor(layer, anchor))
        self.assertIs(layer.anchors["top"], anchor)
        self.assertEqual(
            log,
            [
                "layer.beginChanges",
                "layer.endChanges",
            ],
        )

    def test_layer_display_name_falls_back_to_master_name(self) -> None:
        layer = types.SimpleNamespace(name=None, associatedMasterId="m1")
        font = types.SimpleNamespace(masters=[types.SimpleNamespace(id="m1", name="Regular")])

        self.assertEqual(helpers._layer_display_name(font, layer), "Regular")

    def test_sidebearing_helpers_fall_back_to_lsb_rsb(self) -> None:
        class LegacyLayer:
            __slots__ = ("LSB", "RSB")

            def __init__(self) -> None:
                self.LSB = 40
                self.RSB = 55

        layer = LegacyLayer()

        self.assertEqual(helpers._get_left_sidebearing(layer), 40)
        self.assertEqual(helpers._get_right_sidebearing(layer), 55)
        self.assertTrue(helpers._set_sidebearing(layer, "leftSideBearing", "LSB", 25))
        self.assertTrue(helpers._set_sidebearing(layer, "rightSideBearing", "RSB", 35))
        self.assertEqual(layer.LSB, 25)
        self.assertEqual(layer.RSB, 35)

    def test_sidebearing_reads_use_main_thread_bridge(self) -> None:
        layer = types.SimpleNamespace(leftSideBearing=40, rightSideBearing=55)
        calls = []
        original_run_on_main_thread = helpers._run_on_main_thread

        def fake_run_on_main_thread(callback):
            calls.append(callback)
            return callback()

        try:
            helpers._run_on_main_thread = fake_run_on_main_thread

            self.assertEqual(helpers._get_left_sidebearing(layer), 40)
            self.assertEqual(helpers._get_right_sidebearing(layer), 55)
        finally:
            helpers._run_on_main_thread = original_run_on_main_thread

        self.assertEqual(len(calls), 2)

    def test_sidebearing_reads_are_skipped_in_glyphs3_host(self) -> None:
        class HostileLayer:
            @property
            def leftSideBearing(self):
                raise AssertionError("Glyphs 3 LSB getter must not be touched")

            @property
            def LSB(self):
                raise AssertionError("Glyphs 3 LSB fallback must not be touched")

        original = sys.modules.get("GlyphsApp")
        sys.modules["GlyphsApp"] = types.SimpleNamespace(
            Glyphs=types.SimpleNamespace(versionNumber=3.5)
        )
        try:
            self.assertIsNone(helpers._get_left_sidebearing(HostileLayer()))
        finally:
            if original is None:
                sys.modules.pop("GlyphsApp", None)
            else:
                sys.modules["GlyphsApp"] = original

    def test_sidebearing_writes_are_skipped_in_glyphs3_host(self) -> None:
        class HostileLayer:
            @property
            def leftSideBearing(self):
                return None

            @leftSideBearing.setter
            def leftSideBearing(self, _value):
                raise AssertionError("Glyphs 3 LSB setter must not be touched")

            @property
            def LSB(self):
                return None

            @LSB.setter
            def LSB(self, _value):
                raise AssertionError("Glyphs 3 LSB fallback setter must not be touched")

        original = sys.modules.get("GlyphsApp")
        sys.modules["GlyphsApp"] = types.SimpleNamespace(
            Glyphs=types.SimpleNamespace(versionNumber=3.5)
        )
        try:
            self.assertFalse(
                helpers._set_sidebearing(HostileLayer(), "leftSideBearing", "LSB", 25)
            )
        finally:
            if original is None:
                sys.modules.pop("GlyphsApp", None)
            else:
                sys.modules["GlyphsApp"] = original

    def test_glyphs_show_url_encodes_path_and_glyph(self) -> None:
        url, reason = helpers._glyphs_show_url(
            "/Users/example/My Font.glyphs",
            glyph_name="A.alt",
        )

        self.assertIsNone(reason)
        self.assertEqual(
            url,
            "glyphsapp://show/?path=%2FUsers%2Fexample%2FMy+Font.glyphs&glyph=A.alt",
        )

    def test_glyphs_show_url_preserves_repeated_layer_order(self) -> None:
        url, reason = helpers._glyphs_show_url(
            "/Users/example/Font.glyphs",
            glyph_name="A",
            layer_ids=["master-1", "backup-2"],
        )

        self.assertIsNone(reason)
        self.assertEqual(
            url,
            "glyphsapp://show/?path=%2FUsers%2Fexample%2FFont.glyphs&glyph=A&layer=master-1&layer=backup-2",
        )

    def test_glyphs_show_url_treats_layer_id_string_as_one_layer(self) -> None:
        url, reason = helpers._glyphs_show_url(
            "/Users/example/Font.glyphs",
            glyph_name="A",
            layer_ids="master-1",
        )

        self.assertIsNone(reason)
        self.assertEqual(
            url,
            "glyphsapp://show/?path=%2FUsers%2Fexample%2FFont.glyphs&glyph=A&layer=master-1",
        )

    def test_glyphs_show_glyphs_url_repeats_glyph_params(self) -> None:
        url, reason = helpers._glyphs_show_glyphs_url(
            "/Users/example/Font.glyphs",
            ["a.ss01", "b.ss01", "a.ss01"],
        )

        self.assertIsNone(reason)
        self.assertEqual(
            url,
            "glyphsapp://show/?path=%2FUsers%2Fexample%2FFont.glyphs&glyph=a.ss01&glyph=b.ss01",
        )

    def test_glyphs_show_url_can_use_production_name(self) -> None:
        url, reason = helpers._glyphs_show_url(
            "/Users/example/Font.glyphs",
            production_name="uni01F4",
        )

        self.assertIsNone(reason)
        self.assertEqual(
            url,
            "glyphsapp://show/?path=%2FUsers%2Fexample%2FFont.glyphs&production=uni01F4",
        )

    def test_glyphs_show_link_fields_return_markdown(self) -> None:
        fields = helpers._glyphs_show_link_fields(
            "/Users/example/Font.glyphs",
            glyph_name="A",
            label="Open [A]",
        )

        self.assertEqual(
            fields["showUrl"],
            "glyphsapp://show/?path=%2FUsers%2Fexample%2FFont.glyphs&glyph=A",
        )
        self.assertEqual(
            fields["showMarkdown"],
            "[Open \\[A\\]](http://127.0.0.1:9680/glyphs-show/?path=%2FUsers%2Fexample%2FFont.glyphs&glyph=A)",
        )
        self.assertEqual(
            fields["showHttpUrl"],
            "http://127.0.0.1:9680/glyphs-show/?path=%2FUsers%2Fexample%2FFont.glyphs&glyph=A",
        )

    def test_glyphs_show_bridge_url_preserves_repeated_params(self) -> None:
        url = helpers._glyphs_show_bridge_url(
            "glyphsapp://show/?path=%2FUsers%2Fexample%2FFont.glyphs&glyph=A&glyph=B&layer=master-1"
        )

        self.assertEqual(
            url,
            "http://127.0.0.1:9680/glyphs-show/?path=%2FUsers%2Fexample%2FFont.glyphs&glyph=A&glyph=B&layer=master-1",
        )

    def test_glyphs_show_link_fields_explain_missing_path(self) -> None:
        fields = helpers._glyphs_show_link_fields(None, glyph_name="A")

        self.assertNotIn("showUrl", fields)
        self.assertIn("absolute file path", fields["showUrlUnavailableReason"])

    def test_glyphs_show_layer_link_fields_require_layer_id(self) -> None:
        fields = helpers._glyphs_show_layer_link_fields(
            "/Users/example/Font.glyphs",
            glyph_name="A",
            layer_id=None,
        )

        self.assertNotIn("showUrl", fields)
        self.assertIn("Layer ID unavailable", fields["showUrlUnavailableReason"])

    def test_get_layer_id_prefers_layer_id(self) -> None:
        layer = type(
            "Layer",
            (),
            {
                "layerId": "layer-1",
                "id": "other-id",
                "associatedMasterId": "master-1",
            },
        )()

        self.assertEqual(helpers._get_layer_id(layer), "layer-1")

    def test_parse_style_set_substitutions_simple_rules(self) -> None:
        parsed = helpers._parse_style_set_substitutions(
            """
            # Round dots
            sub period by period.ss01;
            sub comma by comma.ss01;
            """
        )

        self.assertEqual(parsed["unsupportedRuleCount"], 0)
        self.assertEqual(
            parsed["substitutions"],
            [
                {"source": "period", "replacement": "period.ss01"},
                {"source": "comma", "replacement": "comma.ss01"},
            ],
        )

    def test_parse_style_set_substitutions_bracketed_one_to_one(self) -> None:
        parsed = helpers._parse_style_set_substitutions(
            "sub [a b c] by [a.ss01 b.ss01 c.ss01];"
        )

        self.assertEqual(parsed["unsupportedRuleCount"], 0)
        self.assertEqual(
            parsed["substitutions"],
            [
                {"source": "a", "replacement": "a.ss01"},
                {"source": "b", "replacement": "b.ss01"},
                {"source": "c", "replacement": "c.ss01"},
            ],
        )

    def test_parse_style_set_substitutions_skips_contextual_rules(self) -> None:
        parsed = helpers._parse_style_set_substitutions(
            """
            sub a' by a.ss01;
            sub f i by f_i.ss01;
            sub a from [a.ss01 a.ss02];
            sub b by b.ss01;
            """
        )

        self.assertEqual(parsed["unsupportedRuleCount"], 3)
        self.assertEqual(parsed["substitutions"], [{"source": "b", "replacement": "b.ss01"}])
        self.assertTrue(parsed["warnings"])

    def test_style_set_name_from_notes_and_labels(self) -> None:
        self.assertEqual(
            helpers._style_set_name_from_metadata("ss01", notes="Name: Round Dots"),
            "Round Dots",
        )
        self.assertEqual(
            helpers._style_set_name_from_metadata("ss02", labels=["Round Dots", "Alternate Lowercase"]),
            "Alternate Lowercase",
        )

    def test_is_style_set_tag_range(self) -> None:
        self.assertTrue(helpers._is_style_set_tag("ss01"))
        self.assertTrue(helpers._is_style_set_tag("ss20"))
        self.assertFalse(helpers._is_style_set_tag("ss00"))
        self.assertFalse(helpers._is_style_set_tag("ss21"))
        self.assertFalse(helpers._is_style_set_tag("liga"))

    def test_set_kerning_pairs_on_main_thread_updates_kerning_dict(self) -> None:
        font = type("Font", (), {"kerning": {}})()

        helpers._set_kerning_pairs_on_main_thread(
            font,
            "m1",
            [
                ("A", "V", -80),
                ("A", "Y", -60),
                ("A", "V", 0),
            ],
        )

        self.assertIn("m1", font.kerning)
        self.assertEqual(font.kerning["m1"]["A"]["Y"], -60)
        self.assertNotIn("V", font.kerning["m1"]["A"])

    def test_set_kerning_pairs_on_main_thread_removes_empty_left_key(self) -> None:
        font = type("Font", (), {"kerning": {"m1": {"A": {"V": -80}}}})()

        helpers._set_kerning_pairs_on_main_thread(font, "m1", [("A", "V", 0)])

        self.assertNotIn("A", font.kerning["m1"])


if __name__ == "__main__":
    unittest.main()
