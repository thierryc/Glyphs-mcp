"""Native-adapter recovery invariants exercised with disposable fakes."""

from __future__ import annotations

import copy
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.adapters.document import (  # noqa: E402
    GlyphsDocumentHost,
    native_font_to_model,
    native_layer_to_model,
)
from glyphs_mcp_v2.adapters import document as document_adapter  # noqa: E402
from glyphs_mcp_v2.python_execution import PythonExecutionRequest  # noqa: E402
from glyphs_mcp_v2.semantic import diff_models  # noqa: E402


class _Immediate:
    def run(self, callback):
        return callback()


class _Font:
    def __init__(self) -> None:
        self.familyName = "Recovery Test"
        self.filepath = "/fonts/original.glyphs"
        self.dirty = True
        self.saved = []

    def save(self, path, formatVersion=3, makeCopy=False):
        self.saved.append((path, formatVersion, makeCopy))
        Path(path).write_text("disposable recovery", encoding="utf-8")

    def copy(self):
        clone = _Font()
        clone.filepath = self.filepath
        clone.dirty = self.dirty
        return clone


class _NativeSelector:
    def __init__(self, value, owner):
        self.value = value
        self.owner = owner

    def __call__(self):
        return self.value

    def __str__(self):
        return "<native-selector id of {}>".format(self.owner)


class _Instance:
    def __init__(self, native_id, owner):
        self.id = _NativeSelector(native_id, owner)
        self.name = "Regular"
        self.type = 0
        self.active = True
        self.axes = [400]
        self.externalAxes = []


class _InstanceFont(_Font):
    def __init__(self, native_id, owner):
        super().__init__()
        self.axes = []
        self.masters = []
        self.instances = [_Instance(native_id, owner)]
        self.glyphs = []
        self.kerning = {}
        self.features = []
        self.classes = []
        self.featurePrefixes = []


class _ArchiveInstanceFont(_InstanceFont):
    def __init__(self, native_id, owner, *, unsupported_native_value="same"):
        super().__init__(native_id, owner)
        self.unsupported_native_value = unsupported_native_value

    def save(self, path, formatVersion=3, makeCopy=False):
        instance_id = self.instances[0].id()
        Path(path).write_text(
            "instances = (\n{id = \"%s\";}\n);\nunsupportedNativeValue = %s;\n"
            % (instance_id, self.unsupported_native_value),
            encoding="utf-8",
        )


class _Glyphs4SaveFont(_Font):
    def __init__(self, *, native_failure=False):
        super().__init__()
        self.formatVersion = 4
        self.tempData = {"filePath": "original-temp-path"}
        self.native_failure = native_failure
        self.native_calls = []

    def save(self, path, formatVersion=None, makeCopy=False):
        # Reproduce Glyphs 4.0.1: its Python wrapper sets tempData before
        # calling the removed saveToURL_type_format_error_ selector.
        self.tempData["filePath"] = path
        raise AttributeError("saveToURL_type_format_error_")

    def saveToURL_type_format_context_error_(
        self, url, type_id, format_version, context, error
    ):
        self.native_calls.append((url, type_id, format_version, context, error))
        if self.native_failure:
            raise RuntimeError("native save failed")
        Path(url).write_text("glyphs 4 recovery", encoding="utf-8")
        return True


class _App:
    def __init__(self, font) -> None:
        self.font = font
        self.fonts = [font]
        self.documents = []
        self.opened = []

    def open(self, path, showInterface=True):
        self.opened.append((path, showInterface))


class _EditableDocument:
    def __init__(
        self,
        *,
        edited=False,
        stale_unsaved_signal=False,
        sticky_after_undo=False,
    ):
        self._preexisting_edits = 1 if edited else 0
        self._mcp_edits = 0
        self._stale_unsaved_signal = stale_unsaved_signal
        self._sticky_after_undo = sticky_after_undo
        self.isDocumentEdited = edited
        self.hasUnautosavedChanges = edited and not stale_unsaved_signal
        self.change_counts = []

    def updateChangeCount_(self, change):
        self.change_counts.append(change)
        if change == 0:
            self._mcp_edits += 1
        elif change == 1:
            self._mcp_edits = max(0, self._mcp_edits - 1)
        elif change == 2:
            self._mcp_edits = 0
            self._preexisting_edits = 0
        self.isDocumentEdited = bool(self._preexisting_edits or self._mcp_edits)
        self.hasUnautosavedChanges = (
            False
            if self._stale_unsaved_signal
            else bool(self._preexisting_edits or self._mcp_edits)
        )
        if change == 1 and self._sticky_after_undo:
            # Glyphs 4 native setters may register the inverse write itself as
            # another edit even though the canonical content is back at the
            # verified pre-MCP baseline.
            self.isDocumentEdited = True
            self.hasUnautosavedChanges = True


class _TransactionalFont:
    def __init__(
        self,
        *,
        edited=False,
        stale_unsaved_signal=False,
        sticky_after_undo=False,
    ):
        self.familyName = "Transaction Test"
        self.filepath = "/fonts/transaction.glyphs"
        self.parent = _EditableDocument(
            edited=edited,
            stale_unsaved_signal=stale_unsaved_signal,
            sticky_after_undo=sticky_after_undo,
        )
        self.upm = 1000
        self.versionMajor = 1
        self.versionMinor = 0
        self.note = None
        self.grid = 1
        self.gridSubDivision = 1
        self.axes = []
        self.masters = []
        self.instances = []
        self.glyphs = []
        self.kerning = {}
        self.features = []
        self.classes = []
        self.featurePrefixes = []


class _ObjectiveCBooleanFeature:
    """Reproduce a PyObjC Boolean property with is/set selectors.

    Glyphs 4 exposes ``disabled`` as Objective-C ``isDisabled`` and
    ``setDisabled:``. Attribute lookup can therefore yield a truthy selector
    object while direct assignment is read-only.
    """

    __slots__ = ("name", "code", "_automatic", "_disabled")

    def __init__(self, *, name="ss02", code="sub a by a.ss02;"):
        self.name = name
        self.code = code
        self._automatic = False
        self._disabled = False

    @property
    def automatic(self):
        return self._automatic

    @automatic.setter
    def automatic(self, value):
        self._automatic = bool(value)

    def isAutomatic(self):
        return self._automatic

    def setAutomatic_(self, value):
        self._automatic = bool(value)

    def disabled(self):
        return True

    def isDisabled(self):
        return self._disabled

    def setDisabled_(self, value):
        self._disabled = bool(value)


class _OutlineNode:
    def __init__(self, x, y, *, node_type="line", smooth=False, name=None):
        self._position = SimpleNamespace(x=float(x), y=float(y))
        self.type = node_type
        self.smooth = smooth
        self.name = name

    @property
    def position(self):
        return self._position

    @position.setter
    def position(self, value):
        self._position = SimpleNamespace(x=float(value[0]), y=float(value[1]))


class _GlyphsOptionalNameNode(_OutlineNode):
    """Glyphs stringifies None when it is assigned to GSNode.name."""

    def __init__(self, position=(0, 0), node_type="line"):
        super().__init__(position[0], position[1], node_type=node_type)
        self._native_name = None

    @property
    def name(self):
        return self._native_name

    @name.setter
    def name(self, value):
        self._native_name = "None" if value is None else str(value)


class _OutlinePath:
    def __init__(self, nodes):
        self.nodes = nodes
        self.closed = True


class _OutlineComponent:
    def __init__(self, name):
        self.componentName = name
        self.transform = (1, 0, 0, 1, 0, 0)
        self.automaticAlignment = True


class _OutlineLayer:
    def __init__(self, path, component):
        self.layerId = "master-regular"
        self.associatedMasterId = "master-regular"
        self.paths = (path,)
        self.components = (component,)
        self.shapes = [component, path]
        self.hasAlignedWidth = True
        self.begin_count = 0
        self.end_count = 0

    def beginChanges(self):
        self.begin_count += 1

    def endChanges(self):
        self.end_count += 1


class _ReadOnlyShapeProxyLayer:
    """Match Glyphs 4: paths/components iterate, shapes owns mutation."""

    def __init__(self, shapes):
        self.layerId = "master-regular"
        self.associatedMasterId = "master-regular"
        self.shapes = list(shapes)
        self.begin_count = 0
        self.end_count = 0

    @property
    def paths(self):
        return tuple(shape for shape in self.shapes if hasattr(shape, "nodes"))

    @property
    def components(self):
        return tuple(
            shape for shape in self.shapes if hasattr(shape, "componentName")
        )

    def beginChanges(self):
        self.begin_count += 1

    def endChanges(self):
        self.end_count += 1


class _MetricsLayer:
    def __init__(self):
        self.layerId = "master-regular"
        self.associatedMasterId = "master-regular"
        self.leftMetricsKey = None
        self.rightMetricsKey = None
        self.widthMetricsKey = None
        self.width = 500
        self.LSB = 40
        self.RSB = 60
        self.paths = ()
        self.shapes = []
        self.begin_count = 0
        self.end_count = 0
        self.sync_count = 0

    def beginChanges(self):
        self.begin_count += 1

    def endChanges(self):
        self.end_count += 1

    def syncMetrics(self):
        self.sync_count += 1
        self.LSB = 73


class _LoggedNode(_OutlineNode):
    def __init__(self, x, y, log):
        self.log = log
        super().__init__(x, y)

    @_OutlineNode.position.setter
    def position(self, value):
        self.log.append("path")
        self._position = SimpleNamespace(x=float(value[0]), y=float(value[1]))


class _LoggedMetricsLayer(_MetricsLayer):
    def __init__(self, log, path):
        self.log = log
        self._width = 529
        self._lsb = 69
        self._rsb = 60
        super().__init__()
        self._width = 529
        self._lsb = 69
        self._rsb = 60
        self.paths = (path,)
        self.shapes = [path]

    @property
    def width(self):
        return self._width

    @width.setter
    def width(self, value):
        if hasattr(self, "log"):
            self.log.append("width")
        self._width = value

    @property
    def LSB(self):
        return self._lsb

    @LSB.setter
    def LSB(self, value):
        if hasattr(self, "log"):
            self.log.append("LSB")
        self._lsb = value

    @property
    def RSB(self):
        return self._rsb

    @RSB.setter
    def RSB(self, value):
        if hasattr(self, "log"):
            self.log.append("RSB")
        self._rsb = value


class _RecoveryHost(GlyphsDocumentHost):
    def __init__(self, app, root):
        super().__init__(app, executor=_Immediate())
        self._test_recovery_root = Path(root)

    def _recovery_root(self):
        return self._test_recovery_root


class V2DocumentAdapterTests(unittest.TestCase):
    def test_opentype_boolean_properties_use_objc_getter_and_setter_selectors(self) -> None:
        feature = _ObjectiveCBooleanFeature()
        font = _TransactionalFont()
        font.features = [feature]
        before = native_font_to_model(font)

        self.assertFalse(before["features"][0]["disabled"])
        after = copy.deepcopy(before)
        after["features"][0]["disabled"] = True
        changes = diff_models(before, after)

        document_adapter._apply_target_model(font, before, after, changes)

        self.assertTrue(feature.isDisabled())
        self.assertTrue(native_font_to_model(font)["features"][0]["disabled"])

    def test_opentype_code_fields_apply_in_place_without_collection_replacement(self) -> None:
        feature = SimpleNamespace(
            name="liga", code="sub f i by fi;", automatic=False, disabled=False
        )
        font = _TransactionalFont()
        font.features = [feature]
        before = native_font_to_model(font)
        after = copy.deepcopy(before)
        after["features"][0]["code"] = "sub f f i by ffi;"
        after["features"][0]["disabled"] = True
        changes = diff_models(before, after)
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())

        self.assertTrue(host.supports_change_set(changes))
        document_adapter._apply_target_model(font, before, after, changes)

        self.assertIs(font.features[0], feature)
        self.assertEqual(feature.code, "sub f f i by ffi;")
        self.assertTrue(feature.disabled)

    def test_live_capture_reuses_only_unchanged_revision_bound_glyph_models(self) -> None:
        font = _TransactionalFont()

        def glyph(name, marker, *, export=True):
            return SimpleNamespace(
                name=name,
                id="id-{}".format(name),
                lastChange=marker,
                changeCount=lambda: 0,
                mastersCompatible=True,
                layers=[],
                category="Letter",
                subCategory="Uppercase",
                unicode=None,
                export=export,
                leftKerningGroup=None,
                rightKerningGroup=None,
            )

        first_glyph = glyph("A", "revision-1")
        second_glyph = glyph("B", "revision-1")
        font.glyphs = [first_glyph, second_glyph]
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id

        with mock.patch.object(
            document_adapter,
            "_glyph_model",
            wraps=document_adapter._glyph_model,
        ) as capture_glyph:
            first = host.capture_model(document_id)
            first["glyphs"]["A"]["export"] = False
            second = host.capture_model(document_id)

            self.assertEqual(capture_glyph.call_count, 2)
            self.assertTrue(second["glyphs"]["A"]["export"])

            first_glyph.export = False
            first_glyph.lastChange = "revision-2"
            changed = host.capture_model(document_id)
            self.assertEqual(capture_glyph.call_count, 3)
            self.assertFalse(changed["glyphs"]["A"]["export"])

            font.masters.append(
                SimpleNamespace(
                    id="master-new",
                    name="New Master",
                    italicAngle=0,
                    axes=[],
                )
            )
            host.capture_model(document_id)
            self.assertEqual(capture_glyph.call_count, 5)

    def test_verified_write_refreshes_only_the_affected_cached_glyph(self) -> None:
        font = _TransactionalFont()

        def glyph(name):
            return SimpleNamespace(
                name=name,
                id="id-{}".format(name),
                lastChange="unchanged-test-marker",
                changeCount=lambda: 0,
                mastersCompatible=True,
                layers=[],
                category="Letter",
                subCategory="Uppercase",
                unicode=None,
                export=True,
                leftKerningGroup=None,
                rightKerningGroup=None,
            )

        font.glyphs = [glyph("A"), glyph("B")]
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id

        with mock.patch.object(
            document_adapter,
            "_glyph_model",
            wraps=document_adapter._glyph_model,
        ) as capture_glyph:
            before = host.capture_model(document_id)
            after = copy.deepcopy(before)
            after["glyphs"]["A"]["export"] = False

            host.apply_verified_change_set(
                document_id,
                diff_models(before, after),
                operation_id="op_cached_write",
            )
            captured = host.capture_model(document_id)

        self.assertFalse(captured["glyphs"]["A"]["export"])
        self.assertEqual(capture_glyph.call_count, 3)

    def test_detached_simulation_recaptures_only_the_change_scope(self) -> None:
        font = _TransactionalFont()

        def glyph(name):
            return SimpleNamespace(
                name=name,
                id="id-{}".format(name),
                lastChange="revision-1",
                changeCount=lambda: 0,
                mastersCompatible=True,
                layers=[],
                category="Letter",
                subCategory="Uppercase",
                unicode=None,
                export=True,
                leftKerningGroup=None,
                rightKerningGroup=None,
            )

        font.glyphs = [glyph("A"), glyph("B")]
        font.copy = lambda: copy.deepcopy(font)
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        before = host.capture_model(document_id)
        target = copy.deepcopy(before)
        target["glyphs"]["A"]["export"] = False
        changes = diff_models(before, target)

        with mock.patch.object(
            document_adapter,
            "_glyph_model",
            wraps=document_adapter._glyph_model,
        ) as capture_glyph:
            simulated = host.simulate_change_set(document_id, changes)

        self.assertEqual(simulated, target)
        self.assertLessEqual(capture_glyph.call_count, 2)

    def test_read_python_reuses_canonical_capture_instead_of_full_native_models(self) -> None:
        font = _TransactionalFont()
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        host.capture_model(document_id)
        request = PythonExecutionRequest(
            code="print(font.familyName)",
            reason="bounded read",
            intended_effect="read",
            document_id=document_id,
        )

        with mock.patch.object(
            document_adapter,
            "native_font_to_model",
            wraps=document_adapter.native_font_to_model,
        ) as full_capture:
            result = host.run_live_python(request)

        self.assertIn("Transaction Test", result["stdout"])
        self.assertEqual(full_capture.call_count, 0)

    def test_staged_layer_python_compares_only_the_declared_native_scope(self) -> None:
        node = _OutlineNode(0, 0)
        path = _OutlinePath([node])
        layer = _ReadOnlyShapeProxyLayer([path])
        layer.name = "Regular"
        layer.isMasterLayer = True
        layer.isSpecialLayer = False
        glyph = SimpleNamespace(
            name="A",
            id="id-A",
            lastChange="revision-1",
            changeCount=lambda: 0,
            mastersCompatible=True,
            layers=[layer],
            category="Letter",
            subCategory="Uppercase",
            unicode="0041",
            export=True,
            leftKerningGroup=None,
            rightKerningGroup=None,
        )
        font = _TransactionalFont()
        font.masters = [
            SimpleNamespace(
                id="master-regular",
                name="Regular",
                italicAngle=0,
                axes=[],
            )
        ]
        font.glyphs = [glyph]
        font.copy = lambda: copy.deepcopy(font)
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        before = host.capture_model(document_id)
        request = PythonExecutionRequest(
            code="layer.paths[0].nodes[0].position = (25, 0)",
            reason="scoped staged path test",
            intended_effect="document_edit",
            execution_mode="staged_document",
            document_id=document_id,
            glyph_name="A",
            master_id="master-regular",
            layer_id="master-regular",
            expected_document_fingerprint=document_adapter.fingerprint_model(before),
        )

        def scoped_archive(candidate, scoped_request):
            candidate_glyph = document_adapter._lookup_by_name(
                candidate.glyphs, scoped_request.glyph_name
            )
            candidate_layer = document_adapter._lookup_layer(
                candidate_glyph, scoped_request.layer_id
            )
            return repr(native_layer_to_model(candidate_layer)).encode("utf-8")

        with mock.patch.object(
            document_adapter,
            "_serialized_font_archive",
            return_value=b"full-font-archive",
        ) as full_archive, mock.patch.object(
            document_adapter,
            "_serialized_review_scope",
            side_effect=scoped_archive,
            create=True,
        ):
            preview = host.preview_python(request, before)

        self.assertEqual(
            preview["afterModel"]["glyphs"]["A"]["layers"]["master-regular"]
            ["paths"][0]["nodes"][0]["x"],
            25,
        )
        self.assertTrue(preview["nativeArchiveComparison"]["equivalent"])
        self.assertEqual(full_archive.call_count, 0)

    def test_canonical_layer_records_native_width_ownership(self) -> None:
        path = _OutlinePath([_OutlineNode(0, 0), _OutlineNode(100, 0)])
        component = _OutlineComponent("jdotless")
        layer = _OutlineLayer(path, component)

        model = native_layer_to_model(layer)

        self.assertTrue(model["hasAlignedWidth"])
        self.assertTrue(model["components"][0]["automaticAlignment"])

    def test_topology_compatible_outline_delta_updates_native_nodes_in_place(self) -> None:
        first_node = _OutlineNode(0, 0)
        second_node = _OutlineNode(100, 0)
        path = _OutlinePath([first_node, second_node])
        component = _OutlineComponent("acute")
        layer = _OutlineLayer(path, component)
        glyph = SimpleNamespace(name="A", layers={"master-regular": layer})
        font = SimpleNamespace(glyphs={"A": glyph})
        before_paths = [
            {
                "closed": True,
                "nodes": [
                    {"x": 0.0, "y": 0.0, "type": "line", "smooth": False, "name": None},
                    {"x": 100.0, "y": 0.0, "type": "line", "smooth": False, "name": None},
                ],
            }
        ]
        after_paths = copy.deepcopy(before_paths)
        after_paths[0]["nodes"][0]["x"] = 24.0
        current = {"glyphs": {"A": {"layers": {"master-regular": {"paths": before_paths}}}}}
        target = {"glyphs": {"A": {"layers": {"master-regular": {"paths": after_paths}}}}}

        document_adapter._apply_target_model(font, current, target, diff_models(current, target))

        self.assertIs(layer.paths[0], path)
        self.assertIs(path.nodes[0], first_node)
        self.assertIs(path.nodes[1], second_node)
        self.assertEqual(layer.shapes, [component, path])
        self.assertEqual((first_node.position.x, first_node.position.y), (24.0, 0.0))
        self.assertEqual((second_node.position.x, second_node.position.y), (100.0, 0.0))
        self.assertEqual((layer.begin_count, layer.end_count), (1, 1))

    def test_metrics_key_write_synchronizes_derived_native_metrics(self) -> None:
        layer = _MetricsLayer()
        glyph = SimpleNamespace(name="A", layers={"master-regular": layer})
        font = SimpleNamespace(glyphs={"A": glyph})
        before_layer = {
            "width": 500,
            "LSB": 40,
            "RSB": 60,
            "leftMetricsKey": None,
            "rightMetricsKey": None,
            "widthMetricsKey": None,
        }
        after_layer = copy.deepcopy(before_layer)
        after_layer["leftMetricsKey"] = "=H"
        current = {
            "glyphs": {"A": {"layers": {"master-regular": before_layer}}}
        }
        target = {
            "glyphs": {"A": {"layers": {"master-regular": after_layer}}}
        }

        document_adapter._apply_target_model(
            font, current, target, diff_models(current, target)
        )

        self.assertEqual(layer.leftMetricsKey, "=H")
        self.assertEqual(layer.sync_count, 1)
        self.assertEqual(layer.LSB, 73)
        self.assertEqual((layer.begin_count, layer.end_count), (1, 1))

    def test_topology_compatible_component_delta_updates_transform_in_place(self) -> None:
        path = _OutlinePath([_OutlineNode(0, 0), _OutlineNode(100, 0)])
        component = _OutlineComponent("acute")
        layer = _OutlineLayer(path, component)
        glyph = SimpleNamespace(name="Aacute", layers={"master-regular": layer})
        font = SimpleNamespace(glyphs={"Aacute": glyph})
        before_component = {
            "name": "acute",
            "transform": [1, 0, 0, 1, 12, 20],
        }
        component.transform = tuple(before_component["transform"])
        after_component = copy.deepcopy(before_component)
        after_component["transform"][4] = 37
        current = {
            "glyphs": {
                "Aacute": {
                    "layers": {
                        "master-regular": {"components": [before_component]}
                    }
                }
            }
        }
        target = {
            "glyphs": {
                "Aacute": {
                    "layers": {
                        "master-regular": {"components": [after_component]}
                    }
                }
            }
        }

        document_adapter._apply_target_model(
            font, current, target, diff_models(current, target)
        )

        self.assertIs(layer.components[0], component)
        self.assertEqual(component.componentName, "acute")
        self.assertEqual(tuple(component.transform), (1, 0, 0, 1, 37, 20))
        self.assertEqual((layer.begin_count, layer.end_count), (1, 1))

    def test_width_is_finalized_after_topology_compatible_outline_replay(self) -> None:
        log = []
        path = _OutlinePath([_LoggedNode(29, 0, log), _LoggedNode(129, 0, log)])
        layer = _LoggedMetricsLayer(log, path)
        glyph = SimpleNamespace(name="A", layers={"master-regular": layer})
        font = SimpleNamespace(glyphs={"A": glyph})
        before_paths = [
            {
                "closed": True,
                "nodes": [
                    {"x": 29, "y": 0, "type": "line", "smooth": False, "name": None},
                    {"x": 129, "y": 0, "type": "line", "smooth": False, "name": None},
                ],
            }
        ]
        target_paths = copy.deepcopy(before_paths)
        target_paths[0]["nodes"][0]["x"] = 0
        target_paths[0]["nodes"][1]["x"] = 100
        current_layer = {
            "width": 529,
            "LSB": 69,
            "RSB": 60,
            "leftMetricsKey": None,
            "rightMetricsKey": None,
            "widthMetricsKey": None,
            "paths": before_paths,
            "components": [],
            "anchors": {},
        }
        target_layer = copy.deepcopy(current_layer)
        target_layer.update({"width": 500, "LSB": 40, "paths": target_paths})
        current = {"glyphs": {"A": {"layers": {"master-regular": current_layer}}}}
        target = {"glyphs": {"A": {"layers": {"master-regular": target_layer}}}}

        log.clear()
        document_adapter._apply_target_model(
            font, current, target, diff_models(current, target)
        )

        self.assertEqual(log[-1], "width")
        self.assertNotIn("LSB", log)
        self.assertNotIn("RSB", log)
        self.assertEqual(layer.width, 500)
        self.assertEqual(path.nodes[0].position.x, 0)
        self.assertEqual(path.nodes[1].position.x, 100)

    def test_canonical_replay_hint_rebuilds_changed_paths_independent_of_cause(self) -> None:
        path = _OutlinePath([_OutlineNode(29, 0), _OutlineNode(129, 0)])
        layer = _ReadOnlyShapeProxyLayer([path])
        glyph = SimpleNamespace(name="L", layers={"master-regular": layer})
        font = SimpleNamespace(glyphs={"L": glyph})
        current_paths = [
            {
                "closed": True,
                "nodes": [
                    {"x": 29, "y": 0, "type": "line", "smooth": False, "name": None},
                    {"x": 129, "y": 0, "type": "line", "smooth": False, "name": None},
                ],
            }
        ]
        target_paths = copy.deepcopy(current_paths)
        target_paths[0]["nodes"][0]["x"] = 0
        target_paths[0]["nodes"][1]["x"] = 100
        current_layer = {
            "width": 529,
            "LSB": 69,
            "RSB": 60,
            "leftMetricsKey": None,
            "rightMetricsKey": None,
            "widthMetricsKey": None,
            "paths": current_paths,
            "components": [],
            "anchors": {},
        }
        target_layer = copy.deepcopy(current_layer)
        target_layer.update({"width": 500, "LSB": 40, "paths": target_paths})
        current = {"glyphs": {"L": {"layers": {"master-regular": current_layer}}}}
        target = {"glyphs": {"L": {"layers": {"master-regular": target_layer}}}}
        replacement = _OutlinePath([_OutlineNode(0, 0), _OutlineNode(100, 0)])

        with mock.patch.object(document_adapter, "_new_path", return_value=replacement):
            document_adapter._apply_target_model(
                font,
                current,
                target,
                diff_models(current, target),
                replay_replacements=(
                    ("glyphs", "L", "layers", "master-regular", "paths"),
                ),
            )

        self.assertIs(layer.paths[0], replacement)
        self.assertIsNot(layer.paths[0], path)

    def test_canonical_collection_replay_uses_ordered_shapes_not_read_only_proxies(self) -> None:
        original_component = _OutlineComponent("acute")
        original_path = _OutlinePath([_OutlineNode(29, 0), _OutlineNode(129, 0)])
        layer = _ReadOnlyShapeProxyLayer([original_component, original_path])
        glyph = SimpleNamespace(name="L", layers={"master-regular": layer})
        font = SimpleNamespace(glyphs={"L": glyph})
        current_layer = {
            "width": None,
            "LSB": None,
            "RSB": None,
            "leftMetricsKey": None,
            "rightMetricsKey": None,
            "widthMetricsKey": None,
            "anchors": {},
            "paths": [
                {
                    "closed": True,
                    "nodes": [
                        {"x": 29, "y": 0, "type": "line", "smooth": False, "name": None},
                        {"x": 129, "y": 0, "type": "line", "smooth": False, "name": None},
                    ],
                }
            ],
            "components": [
                {"name": "acute", "transform": [1, 0, 0, 1, 0, 0]}
            ],
        }
        target_layer = copy.deepcopy(current_layer)
        target_layer["paths"][0]["nodes"][0]["x"] = 0
        target_layer["paths"][0]["nodes"][1]["x"] = 100
        target_layer["components"][0]["transform"][4] = 20
        current = {"glyphs": {"L": {"layers": {"master-regular": current_layer}}}}
        target = {"glyphs": {"L": {"layers": {"master-regular": target_layer}}}}
        replacement_path = _OutlinePath([_OutlineNode(0, 0), _OutlineNode(100, 0)])
        replacement_component = _OutlineComponent("acute")
        replacement_component.transform = (1, 0, 0, 1, 20, 0)

        with mock.patch.object(document_adapter, "_new_path", return_value=replacement_path), mock.patch.object(
            document_adapter, "_new_component", return_value=replacement_component
        ):
            document_adapter._apply_target_model(
                font,
                current,
                target,
                diff_models(current, target),
                replay_replacements=(
                    ("glyphs", "L", "layers", "master-regular", "paths"),
                    ("glyphs", "L", "layers", "master-regular", "components"),
                ),
            )

        self.assertEqual(layer.shapes, [replacement_component, replacement_path])
        self.assertEqual(layer.components, (replacement_component,))
        self.assertEqual(layer.paths, (replacement_path,))

    def test_canonical_node_names_normalize_absent_and_empty_native_values(self) -> None:
        absent = _ReadOnlyShapeProxyLayer(
            [_OutlinePath([_OutlineNode(0, 0, name=None)])]
        )
        empty = _ReadOnlyShapeProxyLayer(
            [_OutlinePath([_OutlineNode(0, 0, name="")])]
        )

        absent_model = native_layer_to_model(absent)
        empty_model = native_layer_to_model(empty)

        self.assertEqual(absent_model, empty_model)
        self.assertIsNone(absent_model["paths"][0]["nodes"][0]["name"])

    def test_new_path_preserves_native_absence_instead_of_writing_none_sentinel(self) -> None:
        glyphs_module = SimpleNamespace(
            CURVE="curve",
            LINE="line",
            OFFCURVE="offcurve",
            QCURVE="qcurve",
            GSNode=_GlyphsOptionalNameNode,
            GSPath=lambda: _OutlinePath([]),
        )
        spec = {
            "closed": True,
            "nodes": [
                {"x": 0, "y": 0, "type": "line", "smooth": False, "name": None},
                {"x": 100, "y": 0, "type": "line", "smooth": False, "name": "corner"},
            ],
        }

        with mock.patch.dict(sys.modules, {"GlyphsApp": glyphs_module}):
            path = document_adapter._new_path(spec)

        self.assertIsNone(path.nodes[0].name)
        self.assertEqual(path.nodes[1].name, "corner")

    def test_remaining_tree_diff_selects_only_the_collection_that_still_differs(self) -> None:
        before = {
            "glyphs": {
                "L": {
                    "layers": {
                        "m0": {
                            "paths": [{"closed": True, "nodes": [{"x": 0, "y": 0}]}],
                            "components": [],
                            "width": 500,
                        }
                    }
                }
            }
        }
        target = copy.deepcopy(before)
        target["glyphs"]["L"]["layers"]["m0"]["paths"][0]["nodes"][0]["x"] = 20
        observed = copy.deepcopy(target)
        observed["glyphs"]["L"]["layers"]["m0"]["paths"][0]["nodes"][0]["x"] = 19

        roots = document_adapter._canonical_replacement_roots(
            before, target, observed
        )

        self.assertEqual(
            roots,
            (("glyphs", "L", "layers", "m0", "paths"),),
        )

    def test_scalar_residue_does_not_guess_at_unrelated_collection_replacement(self) -> None:
        before = {
            "glyphs": {
                "L": {
                    "layers": {
                        "m0": {
                            "paths": [{"closed": True, "nodes": [{"x": 0, "y": 0}]}],
                            "components": [{"name": "acute", "transform": [1, 0, 0, 1, 0, 0]}],
                            "width": 500,
                        }
                    }
                }
            }
        }
        target = copy.deepcopy(before)
        target["glyphs"]["L"]["layers"]["m0"]["paths"][0]["nodes"][0]["x"] = 20
        target["glyphs"]["L"]["layers"]["m0"]["components"][0]["transform"][4] = 20
        observed = copy.deepcopy(target)
        observed["glyphs"]["L"]["layers"]["m0"]["width"] = 501

        self.assertEqual(
            document_adapter._canonical_replacement_roots(before, target, observed),
            (),
        )

    def test_clone_generated_instance_ids_do_not_change_the_canonical_model(self) -> None:
        source = native_font_to_model(_InstanceFont("source-uuid", "source-pointer"))
        clone = native_font_to_model(_InstanceFont("clone-uuid", "clone-pointer"))

        self.assertEqual(source, clone)
        self.assertEqual(source["instances"][0]["id"], "instance_0")

    def test_serialized_fingerprint_normalizes_clone_generated_instance_ids(self) -> None:
        source = _ArchiveInstanceFont(
            "11111111-1111-4111-8111-111111111111", "source-pointer"
        )
        clone = _ArchiveInstanceFont(
            "22222222-2222-4222-8222-222222222222", "clone-pointer"
        )

        self.assertEqual(
            document_adapter._serialized_font_fingerprint(source),
            document_adapter._serialized_font_fingerprint(clone),
        )

    def test_serialized_fingerprint_keeps_other_native_fields_significant(self) -> None:
        source = _ArchiveInstanceFont(
            "11111111-1111-4111-8111-111111111111",
            "source-pointer",
            unsupported_native_value="before",
        )
        clone = _ArchiveInstanceFont(
            "22222222-2222-4222-8222-222222222222",
            "clone-pointer",
            unsupported_native_value="after",
        )

        self.assertNotEqual(
            document_adapter._serialized_font_fingerprint(source),
            document_adapter._serialized_font_fingerprint(clone),
        )

    def test_verified_transaction_marks_clean_document_dirty_and_inverse_clears_it(self) -> None:
        font = _TransactionalFont()
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        before = host.capture_model(document_id)
        after = copy.deepcopy(before)
        after["font"]["note"] = "reviewed edit"
        change_set = diff_models(before, after)

        host.apply_verified_change_set(
            document_id, change_set, operation_id="op_forward"
        )

        self.assertTrue(font.parent.isDocumentEdited)
        self.assertTrue(host.list_documents()[0].has_unsaved_changes)

        host.apply_verified_change_set(
            document_id,
            change_set.inverse(),
            operation_id="op_revert",
            removes_contribution_id="op_forward",
        )

        self.assertFalse(font.parent.isDocumentEdited)
        self.assertFalse(host.list_documents()[0].has_unsaved_changes)
        self.assertEqual(font.parent.change_counts, [0, 1])
        self.assertNotIn(2, font.parent.change_counts)

    def test_verified_transaction_overrides_stale_native_unsaved_signal(self) -> None:
        font = _TransactionalFont(stale_unsaved_signal=True)
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        before = host.capture_model(document_id)
        after = copy.deepcopy(before)
        after["font"]["note"] = "reviewed edit"
        change_set = diff_models(before, after)

        host.apply_verified_change_set(
            document_id, change_set, operation_id="op_forward"
        )

        self.assertFalse(font.parent.hasUnautosavedChanges)
        self.assertTrue(host.list_documents()[0].has_unsaved_changes)

        host.apply_verified_change_set(
            document_id,
            change_set.inverse(),
            operation_id="op_revert",
            removes_contribution_id="op_forward",
        )

        self.assertFalse(host.list_documents()[0].has_unsaved_changes)

    def test_inverse_preserves_dirty_state_that_predated_transaction(self) -> None:
        font = _TransactionalFont(edited=True)
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        before = host.capture_model(document_id)
        after = copy.deepcopy(before)
        after["font"]["note"] = "reviewed edit"
        change_set = diff_models(before, after)

        host.apply_verified_change_set(
            document_id, change_set, operation_id="op_forward"
        )
        host.apply_verified_change_set(
            document_id,
            change_set.inverse(),
            operation_id="op_revert",
            removes_contribution_id="op_forward",
        )

        self.assertTrue(font.parent.isDocumentEdited)
        self.assertNotIn(2, font.parent.change_counts)

    def test_exact_revert_overrides_sticky_native_dirty_without_hiding_later_manual_edits(self) -> None:
        font = _TransactionalFont(sticky_after_undo=True)
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        baseline = host.capture_model(document_id)
        after = copy.deepcopy(baseline)
        after["font"]["note"] = "verified edit"
        change_set = diff_models(baseline, after)

        host.apply_verified_change_set(
            document_id, change_set, operation_id="op_forward"
        )
        host.apply_verified_change_set(
            document_id,
            change_set.inverse(),
            operation_id="op_revert",
            removes_contribution_id="op_forward",
        )

        self.assertTrue(font.parent.isDocumentEdited)
        self.assertFalse(host.list_documents()[0].has_unsaved_changes)

        font.note = "manual later edit"
        self.assertTrue(host.list_documents()[0].has_unsaved_changes)

    def test_failed_transaction_restoration_balances_dirty_state_after_divergence(self) -> None:
        font = _TransactionalFont()
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        before = host.capture_model(document_id)
        after = copy.deepcopy(before)
        after["font"]["note"] = "reviewed edit"
        change_set = diff_models(before, after)

        host.apply_verified_change_set(
            document_id, change_set, operation_id="op_forward"
        )
        font.note = "divergent readback"
        host.restore_verified_attempt(
            document_id, before, operation_id="op_forward"
        )

        self.assertIsNone(font.note)
        self.assertFalse(font.parent.isDocumentEdited)
        self.assertEqual(font.parent.change_counts, [0, 1])

    def test_failed_rollback_restoration_reinstates_dirty_contribution(self) -> None:
        font = _TransactionalFont()
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        before = host.capture_model(document_id)
        after = copy.deepcopy(before)
        after["font"]["note"] = "reviewed edit"
        change_set = diff_models(before, after)

        host.apply_verified_change_set(
            document_id, change_set, operation_id="op_forward"
        )
        host.apply_verified_change_set(
            document_id,
            change_set.inverse(),
            operation_id="op_revert_1",
            removes_contribution_id="op_forward",
        )
        host.restore_verified_attempt(
            document_id,
            after,
            operation_id="op_revert_1",
            removes_contribution_id="op_forward",
        )

        self.assertEqual(font.note, "reviewed edit")
        self.assertTrue(font.parent.isDocumentEdited)
        self.assertEqual(font.parent.change_counts, [0, 1, 0])

        host.apply_verified_change_set(
            document_id,
            change_set.inverse(),
            operation_id="op_revert_2",
            removes_contribution_id="op_forward",
        )
        self.assertFalse(font.parent.isDocumentEdited)
        self.assertEqual(font.parent.change_counts, [0, 1, 0, 1])

    def test_non_linear_verified_reverts_remove_their_own_dirty_contributions(self) -> None:
        font = _TransactionalFont()
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        baseline = host.capture_model(document_id)

        after_a = copy.deepcopy(baseline)
        after_a["font"]["note"] = "A"
        change_a = diff_models(baseline, after_a)
        host.apply_verified_change_set(
            document_id, change_a, operation_id="op_A"
        )

        before_b = host.capture_model(document_id)
        after_b = copy.deepcopy(before_b)
        after_b["font"]["grid"] = 2
        change_b = diff_models(before_b, after_b)
        host.apply_verified_change_set(
            document_id, change_b, operation_id="op_B"
        )

        current = host.capture_model(document_id)
        target_without_a = copy.deepcopy(current)
        target_without_a["font"]["note"] = None
        host.apply_verified_change_set(
            document_id,
            diff_models(current, target_without_a),
            operation_id="op_revert_A",
            removes_contribution_id="op_A",
        )
        self.assertEqual(font.grid, 2)
        self.assertTrue(host.list_documents()[0].has_unsaved_changes)

        current = host.capture_model(document_id)
        host.apply_verified_change_set(
            document_id,
            diff_models(current, baseline),
            operation_id="op_revert_B",
            removes_contribution_id="op_B",
        )
        self.assertEqual(host.capture_model(document_id), baseline)
        self.assertFalse(host.list_documents()[0].has_unsaved_changes)
        self.assertEqual(font.parent.change_counts, [0, 0, 1, 1])

    def test_structured_native_archive_delta_reports_bounded_locations(self) -> None:
        direct_before = b"font = {\nvalue = 1;\nother = 2;\n};\n"
        direct_after = b"font = {\nvalue = 3;\nother = 2;\n};\n"
        replay_before = b"font = {\nvalue = 1;\nother = 2;\n};\n"
        replay_after = b"font = {\nvalue = 4;\nother = 2;\n};\n"

        result = document_adapter._compare_native_archive_deltas(
            direct_before,
            direct_after,
            replay_before,
            replay_after,
            limit=100,
        )

        self.assertFalse(result["equivalent"])
        self.assertGreater(result["mismatchCount"], 0)
        self.assertLessEqual(len(result["mismatchLocations"]), 100)
        self.assertIn("direct", result["mismatchLocations"][0])
        self.assertIn("replay", result["mismatchLocations"][0])

    def test_glyphs4_make_copy_fallback_restores_temp_data_and_native_format(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            destination = Path(root) / "checkpoint.glyphs"
            font = _Glyphs4SaveFont()
            foundation = SimpleNamespace(
                NSURL=SimpleNamespace(fileURLWithPath_=lambda value: value)
            )
            with mock.patch.dict(sys.modules, {"Foundation": foundation}):
                document_adapter._save_font_copy(font, destination)

            self.assertTrue(destination.is_file())
            self.assertEqual(font.tempData["filePath"], "original-temp-path")
            self.assertEqual(
                font.native_calls,
                [(str(destination), 1, 4, None, None)],
            )

    def test_glyphs4_make_copy_fallback_restores_temp_data_after_failure(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            destination = Path(root) / "checkpoint.glyphs"
            font = _Glyphs4SaveFont(native_failure=True)
            foundation = SimpleNamespace(
                NSURL=SimpleNamespace(fileURLWithPath_=lambda value: value)
            )
            with mock.patch.dict(sys.modules, {"Foundation": foundation}):
                with self.assertRaises(RuntimeError):
                    document_adapter._save_font_copy(font, destination)

            self.assertEqual(font.tempData["filePath"], "original-temp-path")

    def test_recovery_copy_is_private_bounded_and_does_not_change_live_path(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            font = _Font()
            app = _App(font)
            host = _RecoveryHost(app, Path(root) / "private")
            document_id = host.list_documents()[0].document_id
            original_path, original_dirty = font.filepath, font.dirty
            latest = None
            for index in range(12):
                latest = host.create_recovery_copy(document_id, "review_{:02d}".format(index))

            copies = list((Path(root) / "private").glob("*.glyphs"))
            self.assertEqual(len(copies), 10)
            self.assertTrue(all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in copies))
            self.assertTrue(all(call[2] is True for call in font.saved))
            self.assertEqual(font.filepath, original_path)
            self.assertEqual(font.dirty, original_dirty)

            host.open_recovery_copy(str(latest))
            self.assertEqual(len(app.opened), 1)
            self.assertEqual(font.filepath, original_path)
            self.assertEqual(font.dirty, original_dirty)


if __name__ == "__main__":
    unittest.main()
