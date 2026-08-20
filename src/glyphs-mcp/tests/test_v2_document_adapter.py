"""Native-adapter recovery invariants exercised with disposable fakes."""

from __future__ import annotations

import copy
import stat
import sys
import tempfile
import unittest
from collections.abc import Mapping
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
from glyphs_mcp_v2.mutation import (  # noqa: E402
    LAYER_LIFECYCLE_CAPABILITY,
    MASTER_LIFECYCLE_CAPABILITY,
    MutationScope,
    classify_change_path,
)
from glyphs_mcp_v2.semantic import diff_models, fingerprint_model  # noqa: E402
from glyphs_mcp_v2.workflows import build_layer_updates, build_master_updates  # noqa: E402


def _model_layer(model, glyph_name, layer_id):
    layers = model["glyphs"][glyph_name]["layers"]
    if isinstance(layers, dict):
        return layers[layer_id]
    return next(layer for layer in layers if layer["id"] == layer_id)


def _remove_model_layer(model, glyph_name, layer_id):
    layers = model["glyphs"][glyph_name]["layers"]
    if isinstance(layers, dict):
        layers.pop(layer_id)
        return
    layers[:] = [layer for layer in layers if layer["id"] != layer_id]


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


class _ObjectiveCReadOnlyInstanceType:
    """Reproduce Glyphs 4's read-only Python ``GSInstance.type`` wrapper.

    The native Objective-C property remains writable through ``setType_``.
    Structural replay must therefore use the shared native-property boundary
    instead of assigning the Python descriptor directly.
    """

    def __init__(self, *, name=""):
        self.name = name
        self._type = 0
        self.active = True
        self.axes = []
        self.externalAxes = []

    @property
    def type(self):
        return self._type

    def setType_(self, value):
        self._type = int(value)


class _AtomicCollectionProxy:
    """Model a Glyphs list proxy whose slice setter replaces members."""

    def __init__(self, values):
        self.values = list(values)
        self.slice_assignment_count = 0
        self.atomic_assignment_count = 0

    def __len__(self):
        return len(self.values)

    def __getitem__(self, index):
        return self.values[index]

    def __setitem__(self, index, value):
        self.slice_assignment_count += 1
        self.values[index] = value

    def setter(self, values):
        self.atomic_assignment_count += 1
        self.values = list(values)


class _MasterLifecycleMaster:
    def __init__(self, master_id, name, coordinate, *, native_only):
        self.id = master_id
        self.name = name
        self.italicAngle = 0
        self.axes = [coordinate]
        self.native_only = native_only

    def copy(self):
        return copy.deepcopy(self)


class _MasterLifecycleLayer:
    def __init__(self, master_id, name, *, native_only):
        self.layerId = master_id
        self.associatedMasterId = master_id
        self.name = name
        self.isMasterLayer = True
        self.isSpecialLayer = False
        self.hasAlignedWidth = False
        self.width = 600
        self.LSB = 50
        self.RSB = 50
        self.leftMetricsKey = None
        self.rightMetricsKey = None
        self.widthMetricsKey = None
        self.anchors = {}
        self.paths = []
        self.components = []
        self.shapes = []
        self.native_only = native_only

    def copy(self):
        return copy.deepcopy(self)


class _MasterLayerCollection:
    def __init__(self, layers):
        self._values = {layer.layerId: layer for layer in layers}
        self.recalculate_bearings_on_attach = False
        self.preserved_native_objects = set()
        self.atomic_assignment_count = 0

    def __len__(self):
        return len(self._values)

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self._values.values())[key]
        return self._values[key]

    def __setitem__(self, key, value):
        if (
            self.recalculate_bearings_on_attach
            and id(value) not in self.preserved_native_objects
        ):
            # Glyphs may recompute derived sidebearings when a copied layer is
            # attached to a newly restored master. Structural replay must
            # reconcile the resulting native object to its canonical target.
            value.LSB += 7
            value.RSB -= 7
        self._values[str(key)] = value

    def __delitem__(self, key):
        del self._values[str(key)]

    def append(self, value):
        self._values[str(value.layerId)] = value

    def setter(self, values):
        self.atomic_assignment_count += 1
        self._values = {str(value.layerId): value for value in values}

    def values(self):
        return list(self._values.values())


class _MasterLifecycleGlyph:
    def __init__(self, name, layers):
        self.name = name
        self.id = "native-{}".format(name)
        self.lastChange = "revision"
        self.changeCount = lambda: 0
        self.mastersCompatible = True
        self.category = "Letter"
        self.subCategory = None
        self.unicode = None
        self.export = True
        self.leftKerningGroup = None
        self.rightKerningGroup = None
        self.layers = _MasterLayerCollection(layers)
        self.layer_array_remove_count = 0
        self.layer_array_insert_count = 0

    def countOfLayers(self):
        return len(self.layers)

    def objectInLayersAtIndex_(self, index):
        return self.layers[index]

    def removeObjectFromLayersArrayAtIndex_(self, index):
        self.layer_array_remove_count += 1
        values = list(self.layers._values.values())
        del values[index]
        self.layers._values = {str(value.layerId): value for value in values}

    def insertObject_inLayersArrayAtIndex_(self, value, index):
        self.layer_array_insert_count += 1
        values = list(self.layers._values.values())
        values.insert(index, value)
        self.layers._values = {str(item.layerId): item for item in values}


def _master_lifecycle_font():
    regular = _MasterLifecycleMaster(
        "master_regular", "Regular", 100, native_only="master-secret"
    )
    glyphs = [
        _MasterLifecycleGlyph(
            name,
            [
                _MasterLifecycleLayer(
                    "master_regular",
                    "Regular",
                    native_only="layer-secret-{}".format(name),
                )
            ],
        )
        for name in ("A", "B")
    ]
    font = _TransactionalFont()
    font.axes = [SimpleNamespace(axisId="axis-weight", name="Weight", axisTag="wght")]
    font.masters = [regular]
    font.glyphs = glyphs
    return font


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
    def test_future_collection_identity_is_not_required_in_source_capture(self) -> None:
        font = _TransactionalFont()
        font.glyphs = [
            SimpleNamespace(
                name="A",
                id="id-A",
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
        ]
        source = native_font_to_model(font)

        captured = document_adapter._scoped_font_model(
            font,
            source,
            MutationScope(("glyphs",), ("FutureGlyph",)),
        )

        self.assertEqual(captured, source)

    def test_glyph_and_kerning_identity_is_semantic_not_native(self) -> None:
        def glyph(name, native_id):
            return SimpleNamespace(
                name=name,
                id=native_id,
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

        font = _TransactionalFont()
        font.glyphs = [glyph("A", "native-A"), glyph("V", "native-V")]
        font.kerning = {"master-1": {"native-A": {"native-V": -80}}}

        model = native_font_to_model(font)

        self.assertEqual(model["glyphs"]["A"]["id"], "glyph_A")
        self.assertEqual(model["glyphs"]["V"]["id"], "glyph_V")
        self.assertEqual(
            model["kerning"],
            {"master-1": {"glyph_A": {"glyph_V": -80.0}}},
        )
        self.assertEqual(document_adapter._native_kerning_key(font, "glyph_A"), "A")

    def test_recreated_native_glyph_id_does_not_change_canonical_model(self) -> None:
        def model(native_prefix):
            font = _TransactionalFont()
            font.glyphs = []
            for name in ("A", "V"):
                font.glyphs.append(SimpleNamespace(
                    name=name,
                    id="{}-{}".format(native_prefix, name),
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
                ))
            font.kerning = {
                "master-1": {
                    "{}-A".format(native_prefix): {
                        "{}-V".format(native_prefix): -80
                    }
                }
            }
            return native_font_to_model(font)

        self.assertEqual(model("native-before"), model("native-after"))

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

    def test_structural_opentype_replay_preserves_entities_and_order(self) -> None:
        liga = SimpleNamespace(
            name="liga", code="sub f i by fi;", automatic=False, disabled=False
        )
        font = _TransactionalFont()
        font.features = [liga]
        before = native_font_to_model(font)
        after = copy.deepcopy(before)
        after["features"].append(
            {
                "id": "kern",
                "name": "kern",
                "code": "pos A V -80;",
                "automatic": False,
                "disabled": False,
            }
        )
        after["features"] = list(reversed(after["features"]))
        changes = diff_models(before, after)

        def construct(kind, name=""):
            self.assertEqual(kind, "features")
            return SimpleNamespace(
                name=name, code="", automatic=False, disabled=False
            )

        with mock.patch.object(
            document_adapter, "_construct_native_entity", side_effect=construct
        ):
            document_adapter._apply_target_model(font, before, after, changes)

        self.assertEqual([value.name for value in font.features], ["kern", "liga"])
        self.assertEqual(font.features[0].code, "pos A V -80;")
        self.assertIs(font.features[1], liga)

    def test_structural_instance_replay_uses_canonical_identity_order(self) -> None:
        font = _TransactionalFont()
        existing = SimpleNamespace(
            id=lambda: "native-regular",
            name="Regular",
            type=0,
            active=True,
            axes=[],
            externalAxes=[],
        )
        font.instances = [existing]
        before = native_font_to_model(font)
        after = copy.deepcopy(before)
        after["instances"].append(
            {
                "id": "instance_bold",
                "name": "Bold",
                "type": "static",
                "included": True,
                "inclusionReason": None,
                "interpolationSupported": True,
                "axes": [],
            }
        )
        changes = diff_models(before, after)

        with mock.patch.object(
            document_adapter,
            "_construct_native_entity",
            return_value=SimpleNamespace(
                id=lambda: "native-bold",
                name="",
                type=0,
                active=True,
                axes=[],
                externalAxes=[],
            ),
        ):
            document_adapter._apply_target_model(font, before, after, changes)

        self.assertEqual([value.name for value in font.instances], ["Regular", "Bold"])

    def test_structural_instance_replay_uses_native_setter_for_read_only_type(self) -> None:
        font = _TransactionalFont()
        before = native_font_to_model(font)
        after = copy.deepcopy(before)
        after["instances"].append(
            {
                "id": "instance_variable",
                "name": "Variable",
                "type": "variable",
                "included": True,
                "inclusionReason": None,
                "interpolationSupported": False,
                "axes": [],
            }
        )
        changes = diff_models(before, after)
        native = _ObjectiveCReadOnlyInstanceType()

        with mock.patch.object(
            document_adapter,
            "_construct_native_entity",
            return_value=native,
        ):
            document_adapter._apply_target_model(font, before, after, changes)

        self.assertEqual(native.name, "Variable")
        self.assertEqual(native.type, 1)

    def test_collection_reorder_prefers_one_atomic_proxy_setter(self) -> None:
        first = SimpleNamespace(name="First")
        second = SimpleNamespace(name="Second")
        collection = _AtomicCollectionProxy([first, second])

        document_adapter._replace_native_collection_order(
            collection, [second, first]
        )

        self.assertEqual(collection.values, [second, first])
        self.assertEqual(collection.atomic_assignment_count, 1)
        self.assertEqual(collection.slice_assignment_count, 0)

    def test_master_lifecycle_replay_preserves_native_only_master_and_layer_state(self) -> None:
        font = _master_lifecycle_font()
        before = native_font_to_model(font)
        build = build_master_updates(
            before,
            [
                {
                    "action": "duplicate",
                    "sourceMasterId": "master_regular",
                    "masterId": "master_text",
                    "name": "Text",
                    "axes": [{"tag": "wght", "internal": 125}],
                }
            ],
        )
        after = build.change_set.apply(before)

        document_adapter._apply_target_model(
            font,
            before,
            after,
            build.change_set,
            capabilities=build.capabilities,
            execution_context=build.execution_context,
        )

        copied_master = document_adapter._master_by_id(font, "master_text")
        self.assertEqual(copied_master.native_only, "master-secret")
        self.assertEqual(copied_master.name, "Text")
        self.assertEqual(copied_master.axes, [125.0])
        for glyph in font.glyphs:
            copied_layer = glyph.layers["master_text"]
            self.assertEqual(
                copied_layer.native_only,
                "layer-secret-{}".format(glyph.name),
            )
            self.assertEqual(copied_layer.layerId, "master_text")
            self.assertEqual(copied_layer.associatedMasterId, "master_text")
            self.assertEqual(copied_layer.name, "Text")

        templates = {
            "master_text": {
                "master": copied_master.copy(),
                "layers": {
                    glyph.name: glyph.layers["master_text"].copy()
                    for glyph in font.glyphs
                },
            }
        }
        deletion = build.change_set.inverse()
        document_adapter._apply_target_model(
            font,
            after,
            before,
            deletion,
            capabilities=(MASTER_LIFECYCLE_CAPABILITY,),
        )
        self.assertIsNone(document_adapter._master_by_id(font, "master_text"))

        document_adapter._apply_target_model(
            font,
            before,
            after,
            build.change_set,
            capabilities=(MASTER_LIFECYCLE_CAPABILITY,),
            master_restore_templates=templates,
        )
        restored_master = document_adapter._master_by_id(font, "master_text")
        self.assertEqual(restored_master.native_only, "master-secret")
        self.assertTrue(
            all(
                glyph.layers["master_text"].native_only
                == "layer-secret-{}".format(glyph.name)
                for glyph in font.glyphs
            )
        )

    def test_master_restore_reconciles_native_attachment_derived_state(self) -> None:
        font = _master_lifecycle_font()
        before = native_font_to_model(font)
        build = build_master_updates(
            before,
            [
                {
                    "action": "duplicate",
                    "sourceMasterId": "master_regular",
                    "masterId": "master_text",
                    "name": "Text",
                }
            ],
        )
        after = build.change_set.apply(before)
        document_adapter._apply_target_model(
            font,
            before,
            after,
            build.change_set,
            capabilities=build.capabilities,
            execution_context=build.execution_context,
        )
        templates = {
            "master_text": {
                "master": document_adapter._master_by_id(font, "master_text").copy(),
                "layers": {
                    glyph.name: glyph.layers["master_text"].copy()
                    for glyph in font.glyphs
                },
            }
        }
        document_adapter._apply_target_model(
            font,
            after,
            before,
            build.change_set.inverse(),
            capabilities=(MASTER_LIFECYCLE_CAPABILITY,),
        )
        for glyph in font.glyphs:
            glyph.layers.recalculate_bearings_on_attach = True

        document_adapter._apply_target_model(
            font,
            before,
            after,
            build.change_set,
            capabilities=(MASTER_LIFECYCLE_CAPABILITY,),
            master_restore_templates=templates,
        )

        self.assertEqual(native_font_to_model(font), after)

    def test_layer_reconciliation_does_not_chase_projected_sidebearings(self) -> None:
        target = {
            "width": 1062,
            "leftMetricsKey": None,
            "rightMetricsKey": None,
            "widthMetricsKey": None,
            "anchors": {},
            "paths": [{"closed": True, "nodes": []}],
            "components": [],
        }
        initial = copy.deepcopy(target)
        initial.update(
            paths=[{"closed": False, "nodes": []}],
        )
        layer = SimpleNamespace(
            width=1062,
            LSB=38,
            RSB=22,
            leftMetricsKey=None,
            rightMetricsKey=None,
            widthMetricsKey=None,
        )

        with mock.patch.object(
            document_adapter,
            "_update_paths_in_place",
            return_value=True,
        ), mock.patch.object(
            document_adapter,
            "_layer_model",
            return_value=target,
        ) as capture:
            document_adapter._reconcile_layer_to_canonical_target(
                layer,
                initial,
                target,
                layer_root=("glyphs", "A", "layers", "master_text"),
                max_passes=3,
            )

        self.assertEqual((layer.LSB, layer.RSB), (38, 22))
        self.assertEqual(capture.call_count, 1)

    def test_master_tombstone_reuses_exact_detached_native_objects(self) -> None:
        font = _master_lifecycle_font()
        before = native_font_to_model(font)
        build = build_master_updates(
            before,
            [
                {
                    "action": "duplicate",
                    "sourceMasterId": "master_regular",
                    "masterId": "master_text",
                    "name": "Text",
                }
            ],
        )
        after = build.change_set.apply(before)
        document_adapter._apply_target_model(
            font,
            before,
            after,
            build.change_set,
            capabilities=build.capabilities,
            execution_context=build.execution_context,
        )
        host = object.__new__(GlyphsDocumentHost)
        templates = host._capture_removed_master_templates(font, after, before)
        for glyph in font.glyphs:
            glyph.layers.preserved_native_objects.add(
                id(glyph.layers["master_text"])
            )
            glyph.layers.recalculate_bearings_on_attach = True

        document_adapter._apply_target_model(
            font,
            after,
            before,
            build.change_set.inverse(),
            capabilities=(MASTER_LIFECYCLE_CAPABILITY,),
        )
        document_adapter._apply_target_model(
            font,
            before,
            after,
            build.change_set,
            capabilities=(MASTER_LIFECYCLE_CAPABILITY,),
            master_restore_templates=templates,
            reuse_native_master_templates=True,
        )

        self.assertEqual(native_font_to_model(font), after)
        for glyph in font.glyphs:
            self.assertIs(
                glyph.layers["master_text"],
                templates["master_text"]["nativeLayers"][glyph.name],
            )

    def test_layer_tombstone_restores_the_exact_native_special_layer(self) -> None:
        font = _master_lifecycle_font()
        glyph = font.glyphs[0]
        layer = _MasterLifecycleLayer(
            "master_regular",
            "{125}",
            native_only="special-layer-private-state",
        )
        layer.layerId = "brace-125"
        layer.isMasterLayer = False
        layer.isSpecialLayer = True
        layer.isBraceLayer = True
        layer.isBracketLayer = False
        layer.isSmartComponentLayer = False
        layer.isColorPaletteLayer = False
        layer.isBackupLayer = False
        layer.attributes = {"coordinates": {"axis-weight": 125}}
        glyph.layers["brace-125"] = layer
        before = native_font_to_model(font)
        build = build_layer_updates(
            before,
            [{"action": "delete", "glyphName": "A", "layerId": "brace-125"}],
        )
        after = build.change_set.apply(before)
        host = object.__new__(GlyphsDocumentHost)
        captured = host._capture_removed_layer_templates(font, before, after)

        document_adapter._apply_target_model(
            font,
            before,
            after,
            build.change_set,
            capabilities=(LAYER_LIFECYCLE_CAPABILITY,),
        )
        self.assertIsNone(document_adapter._lookup_layer(glyph, "brace-125"))

        document_adapter._apply_target_model(
            font,
            after,
            before,
            build.change_set.inverse(),
            capabilities=(LAYER_LIFECYCLE_CAPABILITY,),
            layer_restore_templates={
                identity: value["native"] for identity, value in captured.items()
            },
            reuse_native_layer_templates=True,
        )

        self.assertEqual(native_font_to_model(font), before)
        self.assertIs(glyph.layers["brace-125"], layer)
        self.assertEqual(
            glyph.layers["brace-125"].native_only,
            "special-layer-private-state",
        )

    def test_layer_duplicate_attaches_by_identity_and_replays_exact_order(self) -> None:
        font = _master_lifecycle_font()
        glyph = font.glyphs[0]
        source = _MasterLifecycleLayer(
            "master_regular", "Backup", native_only="backup-private-state"
        )
        source.layerId = "backup-source"
        source.isMasterLayer = False
        source.isSpecialLayer = False
        source.isBraceLayer = False
        source.isBracketLayer = False
        source.isSmartComponentLayer = False
        source.isColorPaletteLayer = False
        source.isBackupLayer = True
        source.attributes = {"color": 3}
        glyph.layers["backup-source"] = source
        before = native_font_to_model(font)
        build = build_layer_updates(
            before,
            [
                {
                    "action": "duplicate",
                    "glyphName": "A",
                    "sourceLayerId": "backup-source",
                    "layerId": "brace-150",
                    "name": "{150}",
                    "interpolation": {
                        "kind": "intermediate",
                        "coordinates": {"wght": 150},
                    },
                    "index": 1,
                }
            ],
        )
        after = build.change_set.apply(before)

        document_adapter._apply_target_model(
            font,
            before,
            after,
            build.change_set,
            capabilities=build.capabilities,
            execution_context=build.execution_context,
        )

        self.assertEqual(native_font_to_model(font), after)
        self.assertEqual(glyph.layers[1].layerId, "brace-150")
        self.assertEqual(glyph.layers[1].native_only, "backup-private-state")
        self.assertGreater(glyph.layer_array_remove_count, 0)
        self.assertGreater(glyph.layer_array_insert_count, 0)
        self.assertEqual(glyph.layers.atomic_assignment_count, 0)
        document_adapter._apply_target_model(
            font,
            after,
            before,
            build.change_set.inverse(),
            capabilities=(LAYER_LIFECYCLE_CAPABILITY,),
        )
        self.assertEqual(native_font_to_model(font), before)

    def test_layer_capture_uses_proxy_index_order_not_mapping_values_order(self) -> None:
        class GlyphLayerProxyLike(Mapping):
            def __init__(self, values):
                self._ordered = list(values)
                self._by_id = {str(value.layerId): value for value in values}

            def __len__(self):
                return len(self._ordered)

            def __iter__(self):
                return iter(self._ordered)

            def __getitem__(self, key):
                if isinstance(key, int):
                    return self._ordered[key]
                return self._by_id[str(key)]

            def values(self):
                return list(reversed(self._ordered))

        font = _master_lifecycle_font()
        glyph = font.glyphs[0]
        first = glyph.layers[0]
        extra = _MasterLifecycleLayer(
            "master_regular", "Backup", native_only="backup-private-state"
        )
        extra.layerId = "backup-1"
        extra.isMasterLayer = False
        glyph.layers = GlyphLayerProxyLike([first, extra])

        captured = native_font_to_model(font)

        self.assertEqual(
            [layer["id"] for layer in captured["glyphs"]["A"]["layers"]],
            ["master_regular", "backup-1"],
        )

    def test_master_attachment_does_not_rewrite_equal_native_identities(self) -> None:
        class IdentitySensitiveLayer(_MasterLifecycleLayer):
            def __init__(self, master_id, name, *, native_only):
                self.equal_identity_writes = 0
                super().__init__(
                    master_id,
                    name,
                    native_only=native_only,
                )

            def __setattr__(self, name, value):
                if (
                    name in {"associatedMasterId", "layerId"}
                    and name in self.__dict__
                    and self.__dict__[name] == value
                    and "LSB" in self.__dict__
                ):
                    self.equal_identity_writes += 1
                    self.LSB += 8
                    self.RSB -= 8
                super().__setattr__(name, value)

        layer = IdentitySensitiveLayer(
            "master_text",
            "Text",
            native_only="layer-secret-A",
        )
        glyph = _MasterLifecycleGlyph("A", [layer])
        glyph.layers.preserved_native_objects.add(id(layer))

        document_adapter._set_glyph_master_layer(glyph, "master_text", layer)

        self.assertEqual(layer.equal_identity_writes, 0)
        self.assertEqual((layer.LSB, layer.RSB), (50, 50))
        self.assertIs(glyph.layers["master_text"], layer)

    def test_exact_master_restore_does_not_rewrite_equal_master_fields(self) -> None:
        class IdentitySensitiveMaster(_MasterLifecycleMaster):
            def __init__(self, master_id, name, coordinate, *, native_only):
                self.track_equal_writes = False
                self.equal_value_writes = 0
                super().__init__(
                    master_id,
                    name,
                    coordinate,
                    native_only=native_only,
                )
                self.track_equal_writes = True

            def __setattr__(self, name, value):
                if (
                    name in {"id", "name", "italicAngle", "axes"}
                    and self.__dict__.get("track_equal_writes", False)
                    and name in self.__dict__
                    and self.__dict__[name] == value
                ):
                    self.equal_value_writes += 1
                super().__setattr__(name, value)

        font = _master_lifecycle_font()
        font.masters[0] = IdentitySensitiveMaster(
            "master_regular",
            "Regular",
            100,
            native_only="master-secret",
        )
        before = native_font_to_model(font)
        build = build_master_updates(
            before,
            [
                {
                    "action": "duplicate",
                    "sourceMasterId": "master_regular",
                    "masterId": "master_text",
                    "name": "Text",
                }
            ],
        )
        after = build.change_set.apply(before)
        document_adapter._apply_target_model(
            font,
            before,
            after,
            build.change_set,
            capabilities=build.capabilities,
            execution_context=build.execution_context,
        )
        host = object.__new__(GlyphsDocumentHost)
        templates = host._capture_removed_master_templates(font, after, before)
        retained = templates["master_text"]["nativeMaster"]
        document_adapter._apply_target_model(
            font,
            after,
            before,
            build.change_set.inverse(),
            capabilities=(MASTER_LIFECYCLE_CAPABILITY,),
        )
        writes_before_restore = retained.equal_value_writes

        document_adapter._apply_target_model(
            font,
            before,
            after,
            build.change_set,
            capabilities=(MASTER_LIFECYCLE_CAPABILITY,),
            master_restore_templates=templates,
            reuse_native_master_templates=True,
        )

        self.assertEqual(retained.equal_value_writes, writes_before_restore)

    def test_master_lifecycle_paths_require_the_explicit_capability(self) -> None:
        font = _master_lifecycle_font()
        before = native_font_to_model(font)
        build = build_master_updates(
            before,
            [
                {
                    "action": "duplicate",
                    "sourceMasterId": "master_regular",
                    "masterId": "master_text",
                    "name": "Text",
                }
            ],
        )
        host = object.__new__(GlyphsDocumentHost)

        self.assertFalse(host.supports_change_set(build.change_set))
        self.assertTrue(
            host.supports_change_set(
                build.change_set,
                capabilities=(MASTER_LIFECYCLE_CAPABILITY,),
            )
        )

    def test_save_reset_releases_only_that_documents_master_tombstones(self) -> None:
        host = object.__new__(GlyphsDocumentHost)
        host._master_lifecycle_tombstones = {
            "op_a": {"documentId": "doc_a", "templates": {"m0": {}}},
            "op_b": {"documentId": "doc_b", "templates": {"m1": {}}},
        }

        host.reset_verified_change_tracking("doc_a")

        self.assertNotIn("op_a", host._master_lifecycle_tombstones)
        self.assertIn("op_b", host._master_lifecycle_tombstones)

    def test_structural_glyph_replay_adds_and_removes_through_one_boundary(self) -> None:
        font = _TransactionalFont()
        before = native_font_to_model(font)
        after = copy.deepcopy(before)
        after["glyphs"]["B"] = {
            "id": "glyph_B",
            "name": "B",
            "category": "Letter",
            "subCategory": "Uppercase",
            "unicode": "0042",
            "export": True,
            "leftKerningGroup": None,
            "rightKerningGroup": None,
            "mastersCompatible": True,
            "layers": {},
        }
        changes = diff_models(before, after)
        created = SimpleNamespace(
            name="",
            id="",
            category=None,
            subCategory=None,
            unicode=None,
            export=True,
            leftKerningGroup=None,
            rightKerningGroup=None,
            mastersCompatible=True,
            layers=[],
        )
        with mock.patch.object(
            document_adapter, "_construct_native_entity", return_value=created
        ):
            document_adapter._apply_target_model(font, before, after, changes)

        self.assertEqual([value.name for value in font.glyphs], ["B"])
        restored = native_font_to_model(font)
        removal = diff_models(restored, before)
        document_adapter._apply_target_model(font, restored, before, removal)
        self.assertEqual(font.glyphs, [])

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
            with mock.patch(
                "glyphs_mcp_v2.canonical_tree.fingerprint_model",
                side_effect=AssertionError("stable capture rehashed the full tree"),
            ):
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
            # Master order/identity is captured independently. A glyph is
            # reconstructed only when its own layer membership/revision token
            # changes, so adding a bare master cannot flush every glyph shard.
            self.assertEqual(capture_glyph.call_count, 3)

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

    def test_verified_snapshot_readback_reuses_expected_fingerprint_and_unaffected_shards(self) -> None:
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

        first_glyph = glyph("A")
        font.glyphs = [first_glyph, glyph("B")]
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        before = host.capture_snapshot(document_id)
        target = before.materialize()
        target["glyphs"]["A"]["export"] = False
        changes = diff_models(before, target)
        expected = before.store_verified_transition(target, changes)

        first_glyph.export = False
        first_glyph.lastChange = "revision-2"
        with mock.patch(
            "glyphs_mcp_v2.canonical_tree.fingerprint_model",
            side_effect=AssertionError("verified readback hashed the whole tree"),
        ):
            actual = host._executor.run(
                lambda: host._capture_cached_snapshot(
                    document_id, font, expected=expected
                )
            )

        self.assertEqual(actual.document_fingerprint, expected.document_fingerprint)
        self.assertIs(actual.glyph_shards["B"], before.glyph_shards["B"])
        self.assertEqual(actual.materialize(), target)

    def test_unexpected_revision_outside_predicted_snapshot_is_not_silently_reused(self) -> None:
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

        glyph_a = glyph("A")
        glyph_b = glyph("B")
        font.glyphs = [glyph_a, glyph_b]
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        before = host.capture_snapshot(document_id)
        target = before.materialize()
        target["glyphs"]["A"]["export"] = False
        expected = before.store_verified_transition(
            target, diff_models(before, target)
        )

        glyph_a.export = False
        glyph_a.lastChange = "revision-2"
        glyph_b.export = False
        glyph_b.lastChange = "unexpected-revision"
        actual = host._executor.run(
            lambda: host._capture_cached_snapshot(
                document_id, font, expected=expected
            )
        )

        self.assertNotEqual(actual.document_fingerprint, expected.document_fingerprint)
        self.assertFalse(actual["glyphs"]["B"]["export"])

    def test_verified_layer_impact_materializes_only_the_named_layer_fragment(self) -> None:
        font = _TransactionalFont()
        regular = _MetricsLayer()
        regular.layerId = "master-regular"
        regular.associatedMasterId = "master-regular"
        regular.name = "Regular"
        regular.isMasterLayer = True
        regular.isSpecialLayer = False
        regular.lastUpdate = lambda: 1.0
        bold = _MetricsLayer()
        bold.layerId = "master-bold"
        bold.associatedMasterId = "master-bold"
        bold.name = "Bold"
        bold.isMasterLayer = True
        bold.isSpecialLayer = False
        bold.lastUpdate = lambda: 1.0
        glyph = SimpleNamespace(
            name="A",
            id="id-A",
            lastChange="revision-1",
            changeCount=lambda: 0,
            mastersCompatible=True,
            layers=[regular, bold],
            category="Letter",
            subCategory="Uppercase",
            unicode=None,
            export=True,
            leftKerningGroup=None,
            rightKerningGroup=None,
        )
        font.glyphs = [glyph]
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        before = host.capture_snapshot(document_id)
        target = before.materialize()
        _model_layer(target, "A", "master-regular")["width"] = 520
        changes = diff_models(before, target)
        expected = before.store_verified_transition(target, changes)
        host._canonical_model_cache.invalidate_impact(
            document_id,
            document_adapter.CanonicalImpact.from_change_set(before, changes),
        )
        regular.width = 520
        glyph.lastChange = "revision-2"

        with mock.patch.object(
            document_adapter,
            "_glyph_model",
            wraps=document_adapter._glyph_model,
        ) as full_glyph, mock.patch.object(
            document_adapter,
            "_layer_model",
            wraps=document_adapter._layer_model,
        ) as layer_fragment:
            actual = host._executor.run(
                lambda: host._capture_cached_snapshot(
                    document_id, font, expected=expected
                )
            )

        self.assertEqual(actual.document_fingerprint, expected.document_fingerprint)
        self.assertEqual(full_glyph.call_count, 0)
        self.assertEqual(layer_fragment.call_count, 1)
        self.assertIs(
            _model_layer(actual, "A", "master-bold"),
            _model_layer(before, "A", "master-bold"),
        )

    def test_verified_layer_membership_uses_revision_evidence_without_rescanning_unaffected_layers(self) -> None:
        font = _TransactionalFont()
        regular = _MetricsLayer()
        regular.layerId = "master-regular"
        regular.associatedMasterId = "master-regular"
        regular.name = "Regular"
        regular.isMasterLayer = True
        regular.isSpecialLayer = False
        regular.lastUpdate = lambda: 1.0
        bold = _MetricsLayer()
        bold.layerId = "master-bold"
        bold.associatedMasterId = "master-bold"
        bold.name = "Bold"
        bold.isMasterLayer = True
        bold.isSpecialLayer = False
        bold.lastUpdate = lambda: 1.0
        glyph = SimpleNamespace(
            name="A",
            id="id-A",
            lastChange="revision-1",
            changeCount=lambda: 0,
            mastersCompatible=True,
            layers=[regular, bold],
            category="Letter",
            subCategory="Uppercase",
            unicode=None,
            export=True,
            leftKerningGroup=None,
            rightKerningGroup=None,
        )
        font.glyphs = [glyph]
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        before = host.capture_snapshot(document_id)
        target = before.materialize()
        _remove_model_layer(target, "A", "master-bold")
        changes = diff_models(before, target)
        expected = before.store_verified_transition(target, changes)
        host._canonical_model_cache.invalidate_impact(
            document_id,
            document_adapter.CanonicalImpact.from_change_set(before, changes),
        )
        glyph.layers = [regular]
        glyph.lastChange = "revision-2"

        with mock.patch.object(
            document_adapter,
            "_glyph_model",
            wraps=document_adapter._glyph_model,
        ) as full_glyph, mock.patch.object(
            document_adapter,
            "_layer_matches_model",
            wraps=document_adapter._layer_matches_model,
        ) as deep_layer_scan:
            actual = host._executor.run(
                lambda: host._capture_cached_snapshot(
                    document_id, font, expected=expected
                )
            )

        self.assertEqual(actual.document_fingerprint, expected.document_fingerprint)
        self.assertEqual(full_glyph.call_count, 0)
        self.assertEqual(deep_layer_scan.call_count, 0)
        self.assertIs(
            _model_layer(actual, "A", "master-regular"),
            _model_layer(before, "A", "master-regular"),
        )

    def test_unexpected_unaffected_layer_scalar_change_breaks_revision_proof(self) -> None:
        font = _TransactionalFont()
        regular = _MetricsLayer()
        regular.layerId = "master-regular"
        regular.associatedMasterId = "master-regular"
        regular.name = "Regular"
        regular.isMasterLayer = True
        regular.isSpecialLayer = False
        regular.lastUpdate = lambda: 1.0
        bold = _MetricsLayer()
        bold.layerId = "master-bold"
        bold.associatedMasterId = "master-bold"
        bold.name = "Bold"
        bold.isMasterLayer = True
        bold.isSpecialLayer = False
        bold.lastUpdate = lambda: 1.0
        glyph = SimpleNamespace(
            name="A",
            id="id-A",
            lastChange="revision-1",
            changeCount=lambda: 0,
            mastersCompatible=True,
            layers=[regular, bold],
            category="Letter",
            subCategory="Uppercase",
            unicode=None,
            export=True,
            leftKerningGroup=None,
            rightKerningGroup=None,
        )
        font.glyphs = [glyph]
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        before = host.capture_snapshot(document_id)
        target = before.materialize()
        _remove_model_layer(target, "A", "master-bold")
        changes = diff_models(before, target)
        expected = before.store_verified_transition(target, changes)
        host._canonical_model_cache.invalidate_impact(
            document_id,
            document_adapter.CanonicalImpact.from_change_set(before, changes),
        )
        glyph.layers = [regular]
        glyph.lastChange = "revision-2"
        regular.width = 777

        actual = host._executor.run(
            lambda: host._capture_cached_snapshot(
                document_id, font, expected=expected
            )
        )

        self.assertNotEqual(
            actual.document_fingerprint, expected.document_fingerprint
        )
        self.assertEqual(
            _model_layer(actual, "A", "master-regular")["width"],
            777,
        )

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

    def test_detached_reconciliation_recaptures_only_the_change_scope(self) -> None:
        font = _TransactionalFont()

        def glyph(index):
            name = "glyph{:04d}".format(index)
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

        font.glyphs = [glyph(index) for index in range(1000)]
        font.copy = lambda: copy.deepcopy(font)
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        before = host.capture_model(document_id)
        target = copy.deepcopy(before)
        target["glyphs"]["glyph0000"]["export"] = False
        changes = diff_models(before, target)

        with mock.patch.object(
            document_adapter,
            "_glyph_model",
            wraps=document_adapter._glyph_model,
        ) as capture_glyph, mock.patch.object(
            document_adapter,
            "native_font_to_model",
            wraps=document_adapter.native_font_to_model,
        ) as full_capture:
            reconciled = host.simulate_reconciliation(
                document_id,
                changes,
                target,
                before,
            )

        self.assertEqual(reconciled["afterModel"], target)
        self.assertEqual(reconciled["replayReplacements"], [])
        self.assertEqual(full_capture.call_count, 0)
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
            _model_layer(preview["afterModel"], "A", "master-regular")
            ["paths"][0]["nodes"][0]["x"],
            25,
        )
        self.assertTrue(preview["nativeArchiveComparison"]["equivalent"])
        self.assertEqual(
            preview["changeSet"].after_fingerprint,
            document_adapter.fingerprint_model(preview["afterModel"]),
        )
        self.assertEqual(
            preview["writableChangeSet"].after_fingerprint,
            document_adapter.fingerprint_model(preview["afterModel"]),
        )
        self.assertEqual(full_archive.call_count, 0)

    def test_canonical_layer_records_native_width_ownership(self) -> None:
        path = _OutlinePath([_OutlineNode(0, 0), _OutlineNode(100, 0)])
        component = _OutlineComponent("jdotless")
        layer = _OutlineLayer(path, component)

        model = native_layer_to_model(layer)

        self.assertTrue(model["hasAlignedWidth"])
        self.assertTrue(model["components"][0]["automaticAlignment"])

    def test_canonical_layer_excludes_projected_native_sidebearings(self) -> None:
        layer = _MasterLifecycleLayer(
            "master-regular",
            "Regular",
            native_only="layer-secret-A",
        )

        before = native_layer_to_model(layer)
        layer.LSB += 8
        layer.RSB -= 8
        after_projection_drift = native_layer_to_model(layer)

        self.assertNotIn("LSB", before)
        self.assertNotIn("RSB", before)
        self.assertEqual(after_projection_drift, before)
        self.assertEqual(
            fingerprint_model(after_projection_drift),
            fingerprint_model(before),
        )

        layer.width += 10
        after_authoritative_change = native_layer_to_model(layer)
        self.assertNotEqual(
            fingerprint_model(after_authoritative_change),
            fingerprint_model(before),
        )

    def test_legacy_sidebearing_paths_are_derived_not_writable_state(self) -> None:
        for field in ("LSB", "RSB"):
            self.assertEqual(
                classify_change_path(
                    ("glyphs", "A", "layers", "master-regular", field)
                ),
                "derived",
            )

    def test_canonical_paths_preserve_glyphs_precise_node_coordinates(self) -> None:
        node = _OutlineNode(383, 62)
        node.positionPrecise = lambda: SimpleNamespace(
            x=383.1785068235414,
            y=62.0,
        )
        layer = _OutlineLayer(_OutlinePath([node]), _OutlineComponent("acute"))

        model = native_layer_to_model(layer)

        self.assertEqual(
            model["paths"][0]["nodes"][0]["x"],
            383.1785068235414,
        )

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
        _model_layer(target, "L", "m0")["paths"][0]["nodes"][0]["x"] = 20
        observed = copy.deepcopy(target)
        _model_layer(observed, "L", "m0")["paths"][0]["nodes"][0]["x"] = 19

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
        _model_layer(target, "L", "m0")["paths"][0]["nodes"][0]["x"] = 20
        _model_layer(target, "L", "m0")["components"][0]["transform"][4] = 20
        observed = copy.deepcopy(target)
        _model_layer(observed, "L", "m0")["width"] = 501

        self.assertEqual(
            document_adapter._canonical_replacement_roots(before, target, observed),
            (),
        )

    def test_clone_generated_instance_ids_do_not_change_the_canonical_model(self) -> None:
        source = native_font_to_model(_InstanceFont("source-uuid", "source-pointer"))
        clone = native_font_to_model(_InstanceFont("clone-uuid", "clone-pointer"))

        self.assertEqual(source, clone)
        self.assertEqual(source["instances"][0]["id"], "instance_0")

    def test_document_host_keeps_process_local_instance_identity_after_reorder(self) -> None:
        font = _InstanceFont("native-uuid", "native-pointer")
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id

        first = host.capture_model(document_id)
        host._bind_instance_ids(document_id, font, ["instance_regular"])
        second = host.capture_model(document_id)

        self.assertEqual(first["instances"][0]["id"], "instance_0")
        self.assertEqual(second["instances"][0]["id"], "instance_regular")

    def test_document_host_does_not_use_unstable_native_instance_ids(self) -> None:
        class InstanceWithoutPureId:
            def __init__(self, pointer, name):
                self.pointer = pointer
                self.name = name
                self.type = 0
                self.active = True
                self.axes = [400]
                self.externalAxes = []

            @property
            def id(self):
                raise AssertionError("GSInstance.id is not a stable identity read")

        class FreshInstanceCollection:
            def __init__(self):
                self.items = [(101, "First"), (202, "Second")]

            def __iter__(self):
                return iter(
                    [InstanceWithoutPureId(pointer, name) for pointer, name in self.items]
                )

        instances = FreshInstanceCollection()
        font = _InstanceFont("unused", "unused")
        font.instances = instances
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        objc = SimpleNamespace(pyobjc_id=lambda value: value.pointer)

        with mock.patch.dict(sys.modules, {"objc": objc}):
            before = host.capture_model(document_id)
            instances.items.reverse()
            after = host.capture_model(document_id)

        self.assertEqual(
            [item["id"] for item in before["instances"]],
            ["instance_0", "instance_1"],
        )
        self.assertEqual(
            [item["id"] for item in after["instances"]],
            ["instance_1", "instance_0"],
        )

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
