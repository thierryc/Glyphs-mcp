"""Native-adapter recovery invariants exercised with disposable fakes."""

from __future__ import annotations

import base64
import copy
import json
import os
import stat
import sys
import tempfile
import time
import unittest
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


# PyObjC extension modules cannot be unloaded and imported again.  Load the
# genuine bridge during collection, before reporter/startup tests temporarily
# substitute an ``objc`` module, so those patches always restore this exact
# package instead of leaving only ``objc._objc`` resident.
if sys.platform == "darwin":
    try:
        import objc as _PYOBJC_RUNTIME  # type: ignore[import-not-found]
        from AppKit import NSDocument as _NSDOCUMENT_RUNTIME  # type: ignore[import-not-found]
    except Exception:  # pragma: no cover - exercised by non-PyObjC hosts
        _PYOBJC_RUNTIME = None
        _NSDOCUMENT_RUNTIME = None
else:
    _PYOBJC_RUNTIME = None
    _NSDOCUMENT_RUNTIME = None


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
from glyphs_mcp_v2.python_execution import (  # noqa: E402
    ObservedLivePythonError,
    PythonExecutionRequest,
    PythonExecutionService,
    SourceSaveForbiddenError,
)
from glyphs_mcp_v2.audit import AuditLog  # noqa: E402
from glyphs_mcp_v2.operations import OperationStore  # noqa: E402
from glyphs_mcp_v2.ports import HostAccessError  # noqa: E402
from glyphs_mcp_v2.transactions import TransactionKernel  # noqa: E402
from glyphs_mcp_v2.mutation import (  # noqa: E402
    LAYER_LIFECYCLE_CAPABILITY,
    MASTER_LIFECYCLE_CAPABILITY,
    MutationScope,
    classify_change_path,
    unsupported_change_diagnostics,
)
from glyphs_mcp_v2.semantic import ChangeSet, diff_models, fingerprint_model  # noqa: E402
from glyphs_mcp_v2.canonical_views import layer_components, layer_paths  # noqa: E402
from glyphs_mcp_v2.canonical_schema import deterministic_occurrence_id  # noqa: E402
from glyphs_mcp_v2.canonical_tree import CanonicalSnapshot  # noqa: E402
from glyphs_mcp_v2.structural_registry import (  # noqa: E402
    build_layer_updates,
    build_master_updates,
)


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


class FontUpdateSuspensionTests(unittest.TestCase):
    def test_live_write_balances_interface_suspension(self) -> None:
        events = []
        font = SimpleNamespace(
            disableUpdateInterface=lambda: events.append("disable"),
            enableUpdateInterface=lambda: events.append("enable"),
        )

        result = document_adapter._run_with_font_updates_suspended(
            font, lambda: events.append("write") or "result"
        )

        self.assertEqual(result, "result")
        self.assertEqual(events, ["disable", "write", "enable"])

    def test_live_write_reenables_interface_after_failure(self) -> None:
        events = []
        font = SimpleNamespace(
            disableUpdateInterface=lambda: events.append("disable"),
            enableUpdateInterface=lambda: events.append("enable"),
        )

        with self.assertRaisesRegex(RuntimeError, "failed"):
            document_adapter._run_with_font_updates_suspended(
                font,
                lambda: (_ for _ in ()).throw(RuntimeError("failed")),
            )

        self.assertEqual(events, ["disable", "enable"])

    def test_transaction_gc_boundary_defers_collection_and_restoration(self) -> None:
        callbacks = []
        boundary = document_adapter._DeferredCyclicGC(
            scheduler=callbacks.append
        )
        events = []
        with mock.patch.object(document_adapter.gc, "isenabled", return_value=True), mock.patch.object(
            document_adapter.gc, "disable", side_effect=lambda: events.append("disable")
        ), mock.patch.object(
            document_adapter.gc,
            "collect",
            side_effect=lambda generation: events.append("collect:{}".format(generation)),
        ), mock.patch.object(
            document_adapter.gc, "enable", side_effect=lambda: events.append("enable")
        ):
            boundary.begin()
            boundary.begin()
            boundary.end()
            self.assertEqual(callbacks, [])
            boundary.end()
            self.assertEqual(events, ["disable"])
            self.assertEqual(len(callbacks), 1)
            callbacks.pop()()

        self.assertEqual(events, ["disable", "collect:0", "enable"])

    def test_native_image_replay_resolves_canonical_relative_path(self) -> None:
        glyphs_app = SimpleNamespace(
            GSBackgroundImage=type("GSBackgroundImage", (), {})
        )
        with mock.patch.dict(sys.modules, {"GlyphsApp": glyphs_app}):
            image = document_adapter._new_image(
                {"imagePath": "Images/reference.tif"},
                document_path="/fonts/Family.glyphspackage",
            )

        self.assertEqual(image.imagePath, "/fonts/Images/reference.tif")
        self.assertEqual(
            document_adapter.canonical_image_path(
                "fonts/Images/reference.tif",
                "/fonts/Family.glyphspackage",
            ),
            "Images/reference.tif",
        )
        self.assertEqual(
            document_adapter.canonical_image_path(
                "Images/reference.tif",
                "/fonts/Family.glyphspackage",
            ),
            "Images/reference.tif",
        )

    def test_native_image_capture_invokes_the_persistent_path_selector(self) -> None:
        image = SimpleNamespace(
            imagePath=lambda: "/fonts/Images/reference.tif",
            imageURL=None,
            position=(0, 0),
            scale=(1, 1),
            crop=None,
            angle=0,
            slant=0,
            alpha=1,
            locked=False,
            attributes={},
        )

        model = document_adapter._image_model(
            image,
            document_path="/fonts/Family.glyphspackage",
        )

        self.assertEqual(model["imagePath"], "Images/reference.tif")


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
        destination = Path(path)
        if destination.suffix == ".glyphspackage":
            destination.mkdir()
            destination = destination / "fontinfo.plist"
        destination.write_text(
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


class _CompileFont(_Font):
    def __init__(self, events=None, *, detached=False, preflight_error=None):
        super().__init__()
        self.events = events if events is not None else []
        self.detached = detached
        self.preflight_error = preflight_error

    def copy(self):
        return _CompileFont(
            self.events,
            detached=True,
            preflight_error=self.preflight_error,
        )

    def compileFeatures(self):
        self.events.append("detached" if self.detached else "live")
        if self.detached and self.preflight_error is not None:
            raise self.preflight_error


class OpenTypeDiagnosticsAdapterTests(unittest.TestCase):
    def test_diagnostics_compile_only_a_detached_copy(self) -> None:
        font = _CompileFont()
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())

        result = host.inspect_compilation_diagnostics(
            host.document_id_for_font(font)
        )

        self.assertEqual(font.events, ["detached"])
        self.assertTrue(result["succeeded"])
        self.assertFalse(result["liveAttempted"])

    def test_failed_detached_preflight_never_compiles_live_font(self) -> None:
        font = _CompileFont(preflight_error=RuntimeError("bad feature source"))
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())

        result = host.inspect_compilation_diagnostics(
            host.document_id_for_font(font)
        )

        self.assertEqual(font.events, ["detached"])
        self.assertFalse(result["succeeded"])
        self.assertFalse(result["liveAttempted"])


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


class VerifiedTransactionUpdateBoundaryTests(unittest.TestCase):
    def test_document_boundary_is_nested_and_balanced_on_the_host_executor(self) -> None:
        font = _TransactionalFont()
        events = []
        font.disableUpdateInterface = lambda: events.append("disable")
        font.enableUpdateInterface = lambda: events.append("enable")
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id

        gc_events = []
        gc_boundary = SimpleNamespace(
            begin=lambda: gc_events.append("begin"),
            end=lambda: gc_events.append("end"),
        )
        with mock.patch.object(
            document_adapter, "_VERIFIED_TRANSACTION_GC", gc_boundary
        ):
            host.begin_verified_transaction(document_id)
            host.begin_verified_transaction(document_id)
            self.assertEqual(events, ["disable"])

            host.end_verified_transaction(document_id)
            self.assertEqual(events, ["disable"])
            host.end_verified_transaction(document_id)
            self.assertEqual(events, ["disable", "enable"])
        self.assertEqual(host._verified_transaction_updates, {})
        self.assertEqual(gc_events, ["begin", "begin", "end", "end"])


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


class _MutableIdentityStorage:
    def __init__(self, values):
        self.values = list(values)
        self.exchanges = []

    def __len__(self):
        return len(self.values)

    def __getitem__(self, index):
        return self.values[index]

    def exchangeObjectAtIndex_withObjectAtIndex_(self, first, second):
        self.exchanges.append((first, second))
        self.values[first], self.values[second] = (
            self.values[second],
            self.values[first],
        )


class _CollectionChangeOwner:
    def __init__(self):
        self.notifications = []

    def willChangeValueForKey_(self, key):
        self.notifications.append(("will", key))

    def didChangeValueForKey_(self, key):
        self.notifications.append(("did", key))


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
        self._font = None
        self._stored_name = None
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

    @property
    def name(self):
        if self.isMasterLayer and self._font is not None:
            for master in self._font.masters:
                if str(master.id) == str(self.associatedMasterId):
                    return master.name
        return self._stored_name

    @name.setter
    def name(self, value):
        self._stored_name = value

    def copy(self):
        return copy.deepcopy(self)


class _MasterLayerCollection:
    def __init__(self, layers):
        self._values = {layer.layerId: layer for layer in layers}
        self.owner = None
        self.recalculate_bearings_on_attach = False
        self.preserved_native_objects = set()
        self.atomic_assignment_count = 0

    def __len__(self):
        ghosts = self.owner._ghost_layers if self.owner is not None else ()
        return len(self._values) + len(ghosts)

    def __getitem__(self, key):
        if isinstance(key, int):
            ghosts = self.owner._ghost_layers if self.owner is not None else ()
            return (list(self._values.values()) + list(ghosts))[key]
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
        font = getattr(self.owner, "font", None)
        if font is not None:
            # Glyphs derives master-layer names dynamically from the font.
            # The fixture carries the parent explicitly without invoking the
            # GSLayer.name setter.
            value._font = font
        self._values[str(key)] = value

    def __delitem__(self, key):
        del self._values[str(key)]

    def append(self, value):
        self._values[str(value.layerId)] = value

    def setter(self, values):
        self.atomic_assignment_count += 1
        font = getattr(self.owner, "font", None)
        if font is not None:
            for value in values:
                value._font = font
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
        self.layers.owner = self
        self.layer_array_remove_count = 0
        self.layer_array_insert_count = 0
        self.exact_layer_remove_count = 0
        self.exact_layer_set_count = 0
        self.undoManager = object()
        self.ghost_layer_reinsertions = False
        self.undo_disabled_layer_remove_count = 0
        self._undo_removed_layer = None
        self._ghost_layers = []

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

    def removeLayerForId_(self, layer_id):
        self.exact_layer_remove_count += 1
        if self.undoManager is None:
            self.undo_disabled_layer_remove_count += 1
        elif self.ghost_layer_reinsertions:
            self._undo_removed_layer = self.layers[str(layer_id)]
        del self.layers[str(layer_id)]

    def setLayer_forId_(self, value, layer_id):
        self.exact_layer_set_count += 1
        value.layerId = str(layer_id)
        self.layers[str(layer_id)] = value
        if (
            self.ghost_layer_reinsertions
            and self.undoManager is not None
            and self._undo_removed_layer is value
        ):
            self._ghost_layers.append(value)
        self._undo_removed_layer = None


class _CascadingMasterCollection(list):
    """Model Glyphs' ownership cascade from masters to master layers."""

    def __init__(self, values, font):
        super().__init__(values)
        self.font = font

    def __delitem__(self, index):
        master_id = str(self[index].id)
        for glyph in self.font.glyphs:
            if document_adapter._lookup_layer(glyph, master_id) is not None:
                del glyph.layers[master_id]
        super().__delitem__(index)


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
    font.masters = _CascadingMasterCollection([regular], font)
    font.glyphs = glyphs
    for glyph in glyphs:
        glyph.font = font
        for layer in glyph.layers.values():
            layer._font = font
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
        self.position = (0, 0)
        self.scale = (1, 1)
        self.rotation = 0
        self.slant = (0, 0)
        self.alignment = 0
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
    def test_open_edit_tab_resolves_all_layers_before_main_thread_open(self) -> None:
        font = _TransactionalFont()
        master = SimpleNamespace(id="m1")
        layer = SimpleNamespace(
            layerId="m1", associatedMasterId="m1", parent=None
        )
        glyph = SimpleNamespace(name="A", id="gA", layers=[layer])
        layer.parent = glyph
        font.masters = [master]
        font.selectedFontMaster = master
        font.selectedLayers = []
        font.glyphs = [glyph]
        opened = []

        class TrackingExecutor:
            def __init__(self) -> None:
                self.in_callback = False

            def run(self, callback):
                self.in_callback = True
                try:
                    return callback()
                finally:
                    self.in_callback = False

        executor = TrackingExecutor()

        def new_tab(layers):
            self.assertTrue(executor.in_callback)
            opened.append(list(layers))

        font.newTab = new_tab
        host = GlyphsDocumentHost(_App(font), executor=executor)
        document_id = host.list_documents()[0].document_id

        with self.assertRaisesRegex(HostAccessError, "Missing"):
            host.open_edit_tab(
                document_id, ("A", "Missing"), master_id="m1"
            )
        self.assertEqual(opened, [])

        result = host.open_edit_tab(document_id, ("A",), master_id="m1")
        self.assertEqual(opened, [[layer]])
        self.assertEqual(result["glyphNames"], ["A"])
        self.assertEqual(result["masterId"], "m1")

    def test_master_value_stores_follow_root_definition_identity(self) -> None:
        class NativeStore(dict):
            """Model Glyphs' NSDictionary-backed master value stores."""

            def __getitem__(self, key):
                if isinstance(key, int):
                    return list(self.keys())[key]
                return super().__getitem__(key)

        metric = SimpleNamespace(
            id="native-metric",
            type=1,
            name=None,
            horizontal=False,
            filter=None,
        )
        stem = SimpleNamespace(
            id="native-stem",
            type=None,
            name="Primary Vertical Stem",
            horizontal=False,
            filter=None,
        )
        number = SimpleNamespace(
            id="native-number",
            type=None,
            name="Overshoot Amount",
            horizontal=False,
            filter=None,
        )
        metric_value = SimpleNamespace(position=700, overshoot=12)
        stem_store = NativeStore({stem.id: 86})
        number_store = NativeStore({number.id: 14})
        master = SimpleNamespace(
            id="master-regular",
            name="Regular",
            italicAngle=0,
            axes=[],
            metricValues=NativeStore({metric.id: metric_value}),
            stemValues=lambda: stem_store,
            numberValues=lambda: number_store,
        )
        master.setStemValueValue_forId_ = (
            lambda value, identity: stem_store.__setitem__(identity, value)
        )
        master.setNumberValueValue_forId_ = (
            lambda value, identity: number_store.__setitem__(identity, value)
        )
        font = SimpleNamespace(
            axes=[],
            masters=[master],
            metrics=[metric],
            stems=[stem],
            numbers=[number],
        )

        model = document_adapter._master_models(font)[0]
        metric_id = document_adapter._metric_models(font, "metrics")[0]["id"]
        stem_id = document_adapter._metric_models(font, "stems")[0]["id"]
        number_id = document_adapter._metric_models(font, "numbers")[0]["id"]

        self.assertEqual(
            model["metricValues"],
            [{"id": metric_id, "pos": 700, "over": 12}],
        )
        self.assertEqual(model["stemValues"], [{"id": stem_id, "value": 86}])
        self.assertEqual(
            model["numberValues"], [{"id": number_id, "value": 14}]
        )

        document_adapter._apply_master_store_models(
            font,
            master,
            "metricValues",
            [{"id": metric_id, "pos": 710, "over": 16}],
        )
        document_adapter._apply_master_store_models(
            font, master, "stemValues", [{"id": stem_id, "value": 92}]
        )
        document_adapter._apply_master_store_models(
            font, master, "numberValues", [{"id": number_id, "value": 18}]
        )

        self.assertEqual((metric_value.position, metric_value.overshoot), (710, 16))
        self.assertEqual(stem_store[stem.id], 92)
        self.assertEqual(number_store[number.id], 18)

    def test_change_set_routes_only_semantically_affected_identities(self) -> None:
        before = {
            "glyphs": {
                "A": {"export": True, "layers": []},
                "B": {"export": True, "layers": []},
            }
        }
        after = copy.deepcopy(before)
        after["glyphs"]["A"]["export"] = False
        changes = diff_models(before, after)

        self.assertEqual(changes.affected_identities(("glyphs",)), ("A",))
        self.assertEqual(
            tuple(change.path for change in changes.changes_under(("glyphs", "A"))),
            (("glyphs", "A", "export"),),
        )
        self.assertEqual(
            changes.affected_identities(("glyphs", "A", "layers")),
            (),
        )

        whole_collection = ChangeSet.from_changes(
            before_fingerprint=changes.before_fingerprint,
            after_fingerprint=changes.after_fingerprint,
            changes=(
                {
                    "path": ["glyphs"],
                    "before": before["glyphs"],
                    "after": after["glyphs"],
                },
            ),
        )
        self.assertIsNone(whole_collection.affected_identities(("glyphs",)))

    def test_glyph_scalar_replay_never_descends_into_unaffected_layers_or_roots(
        self,
    ) -> None:
        glyph_a = SimpleNamespace(name="A", export=True, layers=[])
        glyph_b = SimpleNamespace(name="B", export=True, layers=[])
        font = SimpleNamespace(glyphs=[glyph_a, glyph_b])
        before = {
            "glyphs": {
                "A": {"export": True, "layers": []},
                "B": {"export": True, "layers": []},
            }
        }
        after = copy.deepcopy(before)
        after["glyphs"]["A"]["export"] = False

        with mock.patch.object(
            document_adapter,
            "_apply_layer_collection",
            side_effect=AssertionError("scalar replay descended into layers"),
        ), mock.patch.object(
            document_adapter,
            "_apply_font_record_roots",
            side_effect=AssertionError("scalar replay compared unrelated roots"),
        ):
            document_adapter._apply_target_model(
                font,
                before,
                after,
                diff_models(before, after),
            )

        self.assertFalse(glyph_a.export)
        self.assertTrue(glyph_b.export)

    def test_native_constructor_fields_preserve_defaults_for_canonical_nulls(self) -> None:
        calls = []

        class Native:
            def setOrientation_(self, value):
                if value is None:
                    raise ValueError("native char fields cannot accept None")
                calls.append(("orientation", value))

            def setLocked_(self, value):
                calls.append(("locked", value))

            def setAttributes_(self, value):
                calls.append(("attributes", value))

        document_adapter._apply_native_constructor_fields(
            Native(),
            {"orientation": None, "locked": False, "attributes": {}},
            ("orientation", "locked", "attributes"),
        )

        self.assertEqual(calls, [("locked", False), ("attributes", {})])

    def test_component_capture_uses_registry_owned_native_aliases(self) -> None:
        component = SimpleNamespace(
            componentName="A",
            position=(0, 0),
            scale=(1, 1),
            rotation=0,
            slant=(0, 0),
            transform=(1, 0, 0, 1, 0, 0),
            automaticAlignment=True,
            alignment=0,
            anchor=None,
            locked=False,
            componentMasterId="master-2",
            orientation=lambda: 0,
            keepWeight=False,
            traverseAnchors=True,
            attributes={},
            smartComponentValues={"Width": 75},
        )

        captured = document_adapter._component_model(component)

        self.assertEqual(captured["masterId"], "master-2")
        self.assertEqual(captured["piece"], {"Width": 75})

    def test_component_capture_keeps_only_authoritative_saved_fields(self) -> None:
        component = SimpleNamespace(
            componentName="A",
            position=(0, 0),
            scale=(1, 1),
            rotation=0,
            slant=(0, 0),
            # GSFont.copy() can temporarily expose a false getter even though
            # the saved alignment value still requests automatic alignment.
            automaticAlignment=False,
            alignment=0,
            anchor=None,
            locked=False,
            componentMasterId=None,
            orientation=0,
            keepWeight=0,
            traverseAnchors=True,
            attributes={},
            smartComponentValues={},
        )

        captured = document_adapter._component_model(component)

        self.assertEqual(captured["alignment"], 0)
        self.assertNotIn("automaticAlignment", captured)
        self.assertNotIn("transform", captured)

    def test_registered_mapping_field_replays_through_read_only_native_proxy(self) -> None:
        class Component:
            def __init__(self):
                self._values = {"Width": 25, "Height": 50}

            @property
            def smartComponentValues(self):
                return self._values

        component = Component()
        document_adapter._set_registered_native_field(
            component,
            "definition.component",
            "piece",
            {"Width": 75},
        )

        self.assertEqual(component.smartComponentValues, {"Width": 75})

    def test_bulk_capture_gc_guard_restores_the_prior_state(self) -> None:
        import gc

        initial = gc.isenabled()
        with mock.patch.object(
            document_adapter.gc,
            "collect",
            wraps=document_adapter.gc.collect,
        ) as collect:
            with document_adapter._suspend_cyclic_gc_for_bulk_capture():
                self.assertFalse(gc.isenabled())
        self.assertEqual(gc.isenabled(), initial)
        if initial:
            collect.assert_called_once_with(0)
        else:
            collect.assert_not_called()

    def test_custom_parameter_capture_uses_persistent_value_not_native_description(self) -> None:
        class NativeArray:
            def __init__(self, values):
                self.values = list(values)

            def count(self):
                return len(self.values)

            def objectAtIndex_(self, index):
                return self.values[index]

        class NativeStem:
            def __init__(self, address):
                self.address = address

            def __str__(self):
                return "<GSTTStem {}> h 86:86".format(self.address)

        class Parameter:
            name = "TTFStems"
            disabled = False

            def __init__(self, address):
                # A copied GSFont can expose the rich value as an ordinary
                # Objective-C description string even though its official
                # persistent representation remains structured data.
                self.value = str(NativeStem(address))

            def propertyListValueFormat_error_(self, format_version, error):
                self.seen = (format_version, error)
                return ({
                    "name": self.name,
                    "value": NativeArray([{
                        "horizontal": 1,
                        # Glyphs' native serializer can return NSNumber here
                        # even though the v4 file field is textual.
                        "name": 86,
                        "width": 86,
                    }]),
                }, None)

        def captured(address):
            font = _TransactionalFont()
            master = SimpleNamespace(
                id="master-regular",
                name="Regular",
                italicAngle=0,
                axes=[],
                customParameters=[Parameter(address)],
                properties=[],
                userData={},
                guides=[],
                alignmentZones=[],
                metrics=[],
                stems=[],
                numbers=[],
            )
            font.masters = [master]
            return native_font_to_model(font)

        before = captured("0x111111")
        after = captured("0x999999")

        self.assertEqual(before, after)
        parameter = before["masters"][0]["customParameters"][0]
        self.assertEqual(
            parameter["value"],
            [{"horizontal": 1, "name": "86", "width": 86}],
        )
        self.assertNotIn("GSTTStem", repr(parameter))

    def test_live_guide_omitted_defaults_match_the_serialized_schema(self) -> None:
        guide = SimpleNamespace(attributes=None, slope=0)

        captured = document_adapter._generic_record_model(
            guide, document_adapter._GUIDE_FIELDS, kind="guide"
        )

        self.assertEqual(captured["attr"], {})
        self.assertIs(captured["slope"], False)
        self.assertEqual(captured["angle"], 0)
        self.assertEqual(captured["orientation"], 0)

    def test_live_guide_native_point_matches_serialized_position(self) -> None:
        point = SimpleNamespace(x=229.0, y=1480.0)
        guide = SimpleNamespace(position=point, attributes=None, slope=0)

        captured = document_adapter._generic_record_model(
            guide, document_adapter._GUIDE_FIELDS, kind="guide"
        )

        self.assertEqual(captured["pos"], [229, 1480])

    def test_axis_localized_names_use_the_persistent_record_boundary(self) -> None:
        class BrokenWrapperValue:
            def __str__(self):
                raise AssertionError("the wrapper description is not canonical")

        axis = SimpleNamespace(
            axisTag="wght",
            name="Weight",
            names=BrokenWrapperValue(),
            default=400,
            hidden=False,
            userData={},
        )
        font = SimpleNamespace(axes=[axis])
        font.propertyListValueFormat_error_ = lambda _format, _error: (
            {"axes": [axis]},
            None,
        )

        with mock.patch.object(
            document_adapter,
            "_native_serialized_property_tree",
            return_value={
                "axes": [{
                    "tag": "wght",
                    "name": "Weight",
                    "names": [{"language": "de", "value": "Gewicht"}],
                }],
            },
        ) as flatten:
            captured = document_adapter._axis_models(font)

        self.assertEqual(
            captured[0]["names"],
            [{"language": "de", "value": "Gewicht"}],
        )
        flatten.assert_called_once()

    def test_persisted_axis_omission_uses_the_schema_default_not_the_ui_wrapper(self) -> None:
        class UnsafeWrapperValue:
            def __str__(self):
                raise AssertionError("an omitted persisted field probed the UI wrapper")

        axis = SimpleNamespace(
            axisTag="wght",
            name="Weight",
            names=[UnsafeWrapperValue()],
            default=400,
            hidden=False,
            userData={},
        )
        font = SimpleNamespace(axes=[axis])
        font.propertyListValueFormat_error_ = lambda _format, _error: (
            {"axes": [axis]},
            None,
        )

        with mock.patch.object(
            document_adapter,
            "_native_serialized_property_tree",
            return_value={"axes": [{"tag": "wght", "name": "Weight"}]},
        ):
            captured = document_adapter._axis_models(font)

        self.assertEqual(captured[0]["names"], [])

    def test_live_full_capture_uses_the_source_neutral_persistent_mapping(self) -> None:
        font = _TransactionalFont()
        expected = native_font_to_model(font)
        calls = []

        def persistent(format_version, error):
            calls.append((format_version, error))
            return (copy.deepcopy(expected), None)

        font.propertyListValueFormat_error_ = persistent
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id

        with mock.patch.dict(
            os.environ, {"GLYPHS_MCP_VERIFY_SERIALIZED_SOURCE": "1"}
        ), mock.patch.object(
            document_adapter,
            "_master_models",
            side_effect=AssertionError("manual master traversal was used"),
        ), mock.patch.object(
            document_adapter,
            "_font_model_with_glyphs",
            side_effect=AssertionError("manual root traversal was used"),
        ):
            snapshot = host.capture_snapshot(document_id)

        self.assertEqual(snapshot.materialize(), expected)
        self.assertEqual(calls, [(4, None)])

    def test_live_full_capture_flattens_shallow_native_property_tree_once(self) -> None:
        font = _TransactionalFont()
        expected = native_font_to_model(font)
        shallow = {"glyphs": [object()]}
        flattened = copy.deepcopy(expected)
        font.propertyListValueFormat_error_ = lambda _format, _error: (
            shallow,
            None,
        )
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id

        with mock.patch.dict(
            os.environ, {"GLYPHS_MCP_VERIFY_SERIALIZED_SOURCE": "1"}
        ), mock.patch.object(
            document_adapter.SerializedMappingSource,
            "capture",
            return_value=flattened,
        ) as capture, mock.patch.object(
            document_adapter,
            "_native_serialized_property_tree",
            return_value=flattened,
        ) as native_flatten:
            snapshot = host.capture_snapshot(document_id)

        self.assertEqual(snapshot.materialize(), expected)
        self.assertEqual(capture.call_count, 1)
        native_flatten.assert_called_once_with(shallow)

    def test_canonical_looking_persistent_tree_flattens_native_children(self) -> None:
        font = _TransactionalFont()
        expected = native_font_to_model(font)
        shallow = copy.deepcopy(expected)
        shallow["axes"] = [object()]
        font.propertyListValueFormat_error_ = lambda _format, _error: (
            shallow,
            None,
        )

        with mock.patch.object(
            document_adapter,
            "_native_serialized_property_tree",
            return_value=copy.deepcopy(expected),
        ) as native_flatten:
            captured = document_adapter._native_persistent_font_model(font)

        self.assertEqual(captured, expected)
        native_flatten.assert_called_once_with(shallow)

    def test_persistent_model_refuses_a_native_child_after_bulk_flatten(self) -> None:
        font = _TransactionalFont()
        expected = native_font_to_model(font)
        shallow = copy.deepcopy(expected)
        shallow["axes"] = [object()]
        font.propertyListValueFormat_error_ = lambda _format, _error: (
            {"glyphs": [object()]},
            None,
        )

        with mock.patch.object(
            document_adapter,
            "_native_serialized_property_tree",
            return_value=shallow,
        ):
            captured = document_adapter._native_persistent_font_model(font)

        self.assertIsNone(captured)

    def test_native_serialized_tree_refuses_a_native_child_after_flattening(self) -> None:
        native_axis = object()

        with mock.patch.object(
            document_adapter,
            "_native_property_list_flattener",
            return_value=lambda _persistent, _format, _error: {
                "axes": [native_axis],
            },
        ):
            flattened = document_adapter._native_serialized_property_tree(
                {"axes": [native_axis]}
            )

        self.assertIsNone(flattened)

    def test_strict_property_list_guard_never_introspects_mapping_like_native_objects(self) -> None:
        class NativeMapping(Mapping):
            def __getitem__(self, key):
                raise AssertionError("native mapping was introspected")

            def __iter__(self):
                raise AssertionError("native mapping was iterated")

            def __len__(self):
                raise AssertionError("native mapping was counted")

        plain, is_plain = document_adapter._strict_plain_property_list_value(
            {"axes": [NativeMapping()]}
        )

        self.assertIsNone(plain)
        self.assertFalse(is_plain)

    def test_strict_property_list_predicate_never_introspects_native_objects(self) -> None:
        class NativeMapping(Mapping):
            def __getitem__(self, key):
                raise AssertionError("native mapping was introspected")

            def __iter__(self):
                raise AssertionError("native mapping was iterated")

            def __len__(self):
                raise AssertionError("native mapping was counted")

        self.assertTrue(
            document_adapter._is_strict_plain_property_list_value(
                {"axes": [{"tag": "wght"}]}
            )
        )
        self.assertFalse(
            document_adapter._is_strict_plain_property_list_value(
                {"axes": [NativeMapping()]}
            )
        )

    def test_property_list_probe_never_iterates_mapping_shaped_native_objects(self) -> None:
        class NativeMapping(Mapping):
            def __getitem__(self, key):
                raise AssertionError("native mapping was introspected")

            def __iter__(self):
                raise AssertionError("native mapping was iterated")

            def __len__(self):
                raise AssertionError("native mapping was counted")

        plain, is_plain = document_adapter._plain_property_list_value(
            {"axes": [NativeMapping()]}
        )

        self.assertIsNone(plain)
        self.assertFalse(is_plain)

    def test_attribute_probe_never_iterates_mapping_shaped_native_objects(self) -> None:
        class NativeMapping(Mapping):
            def __getitem__(self, key):
                raise AssertionError("native mapping was introspected")

            def __iter__(self):
                raise AssertionError("native mapping was iterated")

            def __len__(self):
                raise AssertionError("native mapping was counted")

        value = NativeMapping()

        self.assertEqual(
            document_adapter._plain_attribute_value(value), str(value)
        )

    def test_native_property_list_containers_use_explicit_foundation_boundaries(self) -> None:
        class NativeDictionary:
            def __init__(self, values):
                self.values = values

            def allKeys(self):
                return list(self.values)

            def objectForKey_(self, key):
                return self.values[key]

        class NativeArray:
            def __init__(self, values):
                self.values = values

            def count(self):
                return len(self.values)

            def objectAtIndex_(self, index):
                return self.values[index]

        value = NativeDictionary(
            {"axes": NativeArray([NativeDictionary({"tag": "wght"})])}
        )

        plain, is_plain = document_adapter._plain_property_list_value(value)

        self.assertTrue(is_plain)
        self.assertEqual(plain, {"axes": [{"tag": "wght"}]})

    def test_live_glyph_order_uses_the_official_serializer_not_the_editor_proxy(self) -> None:
        font = _TransactionalFont()

        def glyph(name):
            return SimpleNamespace(
                name=name,
                id="id-{}".format(name),
                lastChange=None,
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
        canonical = native_font_to_model(font)
        serializer_view = copy.deepcopy(canonical)
        serializer_view["glyphs"] = {
            "B": serializer_view["glyphs"]["B"],
            "A": serializer_view["glyphs"]["A"],
        }
        serializer_view["glyphOrder"] = ["B", "A"]
        font.propertyListValueFormat_error_ = lambda _format, _error: (
            serializer_view,
            None,
        )

        captured = document_adapter._native_persistent_font_model(font)

        self.assertIsNotNone(captured)
        self.assertEqual(captured["glyphOrder"], ["B", "A"])

    def test_saved_package_mapping_uses_record_identity_and_external_feature_code(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            package = Path(root) / "Fixture.glyphspackage"
            (package / "glyphs").mkdir(parents=True)
            (package / "features").mkdir()
            for relative in (
                "fontinfo.plist",
                "order.plist",
                "kerning.plist",
                "glyphs/A_.glyph",
                "glyphs/amacron.glyph",
            ):
                (package / relative).touch()
            (package / "features" / "liga.fea").write_text(
                "sub f i by fi;\n", encoding="utf-8"
            )
            decoded = {
                "fontinfo.plist": {
                    "features": [{"tag": "liga", "file": "liga.fea"}]
                },
                "order.plist": ["A", "amacron"],
                "kerning.plist": {},
                "A_.glyph": {"glyphname": "A", "unicode": 65},
                "amacron.glyph": {"glyphname": "amacron", "unicode": 257},
            }

            captured = document_adapter._saved_package_mapping(
                package,
                decoder=lambda path: copy.deepcopy(decoded[path.name]),
            )

        self.assertIsNotNone(captured)
        self.assertEqual(captured["glyphs"]["A"]["unicode"], 65)
        self.assertEqual(captured["glyphs"]["amacron"]["unicode"], 257)
        self.assertEqual(
            captured["fontinfo.plist"]["features"][0]["code"],
            "sub f i by fi;\n",
        )

    def test_runtime_openstep_decoder_preserves_v4_numeric_atoms(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "A_.glyph"
            path.write_text(
                "{ glyphname = A; unicode = 65; width = 2048; note = \"001\"; }",
                encoding="utf-8",
            )

            decoded = document_adapter._native_openstep_property_list(path)

        self.assertEqual(decoded["glyphname"], "A")
        self.assertEqual(decoded["unicode"], 65)
        self.assertEqual(decoded["width"], 2048)
        self.assertEqual(decoded["note"], "001")

    def test_clean_saved_document_bootstraps_from_qualified_saved_source(self) -> None:
        font = _TransactionalFont()
        glyph = SimpleNamespace(
            name="A",
            unicode="0041",
            export=True,
            mastersCompatible=True,
            layers=[],
            lastChange=None,
            changeCount=lambda: 0,
        )
        font.glyphs = [glyph]
        cache = document_adapter._RevisionBoundGlyphModelCache()

        expected = native_font_to_model(font)
        font.filepath = "/tmp/Fixture.glyphspackage"
        with mock.patch.object(
            document_adapter,
            "_saved_document_canonical_model",
            return_value=expected,
        ) as saved, mock.patch.object(
            document_adapter,
            "_native_persistent_font_model",
            side_effect=AssertionError(
                "ordinary interaction used the opt-in serialized audit source"
            ),
        ) as live:
            snapshot = cache.capture_snapshot("saved-doc", font)

        self.assertEqual(snapshot.materialize(), expected)
        saved.assert_called_once_with(font, instance_ids=None)
        live.assert_not_called()

    def test_post_notification_reuses_unchanged_saved_source_roots(self) -> None:
        font = _TransactionalFont()
        expected = native_font_to_model(font)
        expected["font"]["familyName"] = "Saved spelling"
        cache = document_adapter._RevisionBoundGlyphModelCache()
        revision = [1]

        with mock.patch.object(
            document_adapter,
            "_saved_document_canonical_model",
            return_value=expected,
        ):
            first = cache.capture_snapshot(
                "saved-notification",
                font,
                revision_provider=lambda: ("revision", revision[0]),
            )
        revision[0] += 1
        with mock.patch.object(
            document_adapter,
            "_font_model_with_glyphs",
            side_effect=AssertionError("unchanged saved roots were re-materialized"),
        ):
            second = cache.capture_snapshot(
                "saved-notification",
                font,
                revision_provider=lambda: ("revision", revision[0]),
            )

        self.assertEqual(second.document_fingerprint, first.document_fingerprint)
        self.assertEqual(second["font"]["familyName"], "Saved spelling")

    def test_saved_document_rejects_falsely_clean_restored_identity(self) -> None:
        native = SimpleNamespace(name="A", unicode="0101", export=False)
        saved = {"A": {"name": "A", "unicode": "0041", "export": True}}

        self.assertFalse(
            document_adapter._saved_model_matches_live_identity(
                {"A": native}, saved
            )
        )

    def test_scoped_scalar_capture_preserves_canonical_order_when_proxy_regroups(self) -> None:
        font = _TransactionalFont()

        def glyph(name):
            return SimpleNamespace(
                name=name,
                id="id-{}".format(name),
                lastChange=None,
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
        source = native_font_to_model(font)
        glyph_a.export = False
        font.glyphs = [glyph_b, glyph_a]
        impact = document_adapter.CanonicalImpact.from_paths(
            source, [("glyphs", "A", "export")]
        )

        with mock.patch.object(
            document_adapter,
            "_native_persistent_font_model",
            side_effect=AssertionError(
                "a scalar fragment must not materialize document order"
            ),
        ):
            captured = document_adapter._scoped_font_model(
                font,
                source,
                MutationScope(impact.roots, impact.glyph_names),
                impact=impact,
                expected_model=source,
            )

        self.assertEqual(captured["glyphOrder"], ["A", "B"])
        self.assertFalse(captured["glyphs"]["A"]["export"])

    def test_structural_capture_preserves_the_baseline_canonical_source(self) -> None:
        regular = _MasterLifecycleLayer(
            "master-regular", "Regular", native_only="regular"
        )
        glyph = _MasterLifecycleGlyph("A", [regular])
        font = _TransactionalFont()
        font.axes = []
        font.masters = []
        font.glyphs = [glyph]
        glyph.font = font

        before = native_font_to_model(font)
        source = document_adapter.CanonicalSnapshot.from_model(
            before,
            native_revision_evidence={"capture": "saved_format_v4_mapping"},
        )
        added = _MasterLifecycleLayer(
            "master-added", "Added", native_only="added"
        )
        glyph.layers[added.layerId] = added
        target = copy.deepcopy(before)
        target["glyphs"]["A"]["layers"].append(
            document_adapter._layer_model(added)
        )
        paths = (
            ("glyphs", "A", "layers", "$order"),
            ("glyphs", "A", "layers", "master-added"),
        )
        impact = document_adapter.CanonicalImpact.from_paths(source, paths)

        with mock.patch.object(
            document_adapter,
            "_native_persistent_font_model",
            return_value=target,
        ) as persistent, mock.patch.object(
            document_adapter,
            "_glyph_fragment_model",
            side_effect=AssertionError(
                "structural capture mixed ObjectWrapper and saved-source spellings"
            ),
        ):
            captured = document_adapter._scoped_font_model(
                font,
                source,
                MutationScope(impact.roots, impact.glyph_names),
                impact=impact,
                expected_model=target,
            )

        self.assertEqual(captured["glyphs"]["A"], target["glyphs"]["A"])
        persistent.assert_called_once_with(
            font, instance_ids=None, document_path=None
        )

    def test_nested_layer_capture_preserves_the_baseline_canonical_source(self) -> None:
        regular = _MasterLifecycleLayer(
            "master-regular", "Regular", native_only="regular"
        )
        glyph = _MasterLifecycleGlyph("A", [regular])
        font = _TransactionalFont()
        font.axes = []
        font.masters = []
        font.glyphs = [glyph]
        glyph.font = font
        before = native_font_to_model(font)
        source = document_adapter.CanonicalSnapshot.from_model(
            before,
            native_revision_evidence={"capture": "saved_format_v4_mapping"},
        )
        paths = ((
            "glyphs", "A", "layers", "master-regular",
            "background", "hints", "hint:corner:0", "origin",
        ),)
        impact = document_adapter.CanonicalImpact.from_paths(source, paths)

        with mock.patch.object(
            document_adapter,
            "_native_persistent_font_model",
            return_value=before,
        ) as persistent, mock.patch.object(
            document_adapter,
            "_glyph_fragment_model",
            side_effect=AssertionError(
                "nested layer capture mixed ObjectWrapper and saved-source spellings"
            ),
        ):
            captured = document_adapter._scoped_font_model(
                font,
                source,
                MutationScope(impact.roots, impact.glyph_names),
                impact=impact,
                expected_model=source,
            )

        self.assertEqual(captured["glyphs"]["A"], before["glyphs"]["A"])
        persistent.assert_called_once_with(
            font, instance_ids=None, document_path=None
        )

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

    def test_cold_live_capture_bootstraps_from_registry_then_reuses_snapshot(self) -> None:
        font = _TransactionalFont()
        expected = native_font_to_model(font)
        cache = document_adapter._RevisionBoundGlyphModelCache()

        with mock.patch.dict(
            os.environ, {"GLYPHS_MCP_VERIFY_SERIALIZED_SOURCE": ""}
        ), mock.patch.object(
            document_adapter,
            "_native_persistent_font_model",
            return_value=expected,
        ) as persistent:
            snapshot = cache.capture_snapshot(
                "doc-cold",
                font,
                revision_provider=lambda: ("stable", 1),
            )
            repeated = cache.capture_snapshot(
                "doc-cold",
                font,
                revision_provider=lambda: ("stable", 1),
            )

        self.assertEqual(snapshot["font"]["familyName"], font.familyName)
        self.assertIs(repeated, snapshot)
        persistent.assert_not_called()

    def test_cold_registry_capture_seeds_native_layer_proof(self) -> None:
        font = _TransactionalFont()
        glyphs = []
        for index in range(383):
            layer = _MetricsLayer()
            layer.layerId = "master-regular"
            layer.associatedMasterId = "master-regular"
            layer.name = "Regular"
            layer.isMasterLayer = True
            layer.isSpecialLayer = False
            layer.lastUpdate = lambda: 1.0
            glyphs.append(
                SimpleNamespace(
                    name="glyph{:03d}".format(index),
                    id="native-{:03d}".format(index),
                    unicode=None,
                    export=True,
                    mastersCompatible=True,
                    layers=[layer],
                    lastChange=None,
                    changeCount=lambda: 0,
                )
            )
        font.glyphs = glyphs
        cache = document_adapter._RevisionBoundGlyphModelCache()

        with mock.patch.object(
            document_adapter,
            "_native_persistent_font_model",
            side_effect=AssertionError("ordinary capture used serialized audit source"),
        ):
            snapshot = cache.capture_snapshot(
                "doc-cold-lazy-evidence",
                font,
                revision_provider=lambda: ("stable", 1),
            )

        self.assertEqual(len(snapshot.glyph_shards), 383)
        cached = cache._documents["doc-cold-lazy-evidence"]["glyphs"]
        self.assertTrue(all(value.get("layerTokens") is not None for value in cached.values()))

    def test_large_glyph_impact_selects_one_bulk_verification_boundary(self) -> None:
        font = _TransactionalFont()
        font.glyphs = [
            SimpleNamespace(
                name="g{:03d}".format(index),
                id="native-{:03d}".format(index),
                unicode=None,
                export=True,
                mastersCompatible=True,
                layers=[],
                lastChange=None,
                changeCount=lambda: 0,
            )
            for index in range(40)
        ]
        before = native_font_to_model(font)
        cache = document_adapter._RevisionBoundGlyphModelCache()
        with mock.patch.dict(
            os.environ, {"GLYPHS_MCP_VERIFY_SERIALIZED_SOURCE": "1"}
        ), mock.patch.object(
            document_adapter, "_native_persistent_font_model", return_value=before
        ):
            cache.capture_snapshot(
                "doc-large-impact",
                font,
                revision_provider=lambda: ("stable", 1),
            )
        impact = document_adapter.CanonicalImpact.from_paths(
            before,
            (("glyphs", glyph.name, "export") for glyph in font.glyphs),
        )

        with mock.patch.object(
            document_adapter,
            "_layer_revision_index",
            side_effect=AssertionError("large impact seeded per-glyph evidence"),
        ):
            cache.invalidate_impact(
                "doc-large-impact", impact, font=font
            )

        self.assertTrue(
            cache._documents["doc-large-impact"]["forcePersistentVerification"]
        )
        expected = document_adapter.CanonicalSnapshot.from_model(before)
        with mock.patch.object(
            document_adapter,
            "_native_persistent_font_model",
            return_value=before,
        ) as persistent:
            captured = cache.capture_snapshot(
                "doc-large-impact",
                font,
                expected=expected,
                revision_provider=lambda: ("stable", 2),
            )
        persistent.assert_called_once()
        self.assertEqual(
            captured.document_fingerprint, expected.document_fingerprint
        )

    def test_bulk_verification_never_switches_source_while_expected_state_mismatches(self) -> None:
        font = _TransactionalFont()
        before = native_font_to_model(font)
        expected_model = copy.deepcopy(before)
        expected_model["font"]["familyName"] = "Expected after state"
        expected = document_adapter.CanonicalSnapshot.from_model(expected_model)
        cache = document_adapter._RevisionBoundGlyphModelCache()

        with mock.patch.dict(
            os.environ, {"GLYPHS_MCP_VERIFY_SERIALIZED_SOURCE": "1"}
        ), mock.patch.object(
            document_adapter,
            "_native_persistent_font_model",
            return_value=before,
        ) as persistent, mock.patch.object(
            document_adapter,
            "_native_canonical_root",
            side_effect=AssertionError(
                "bulk verification switched to the registry live adapter"
            ),
        ):
            cache.capture_snapshot(
                "doc-persistent-fixed-point",
                font,
                revision_provider=lambda: ("stable", 1),
            )
            cache.invalidate_impact(
                "doc-persistent-fixed-point",
                document_adapter.CanonicalImpact.from_paths(
                    before, [("glyphs",)]
                ),
                font=font,
            )
            first = cache.capture_snapshot(
                "doc-persistent-fixed-point",
                font,
                expected=expected,
                revision_provider=lambda: ("stable", 2),
            )
            second = cache.capture_snapshot(
                "doc-persistent-fixed-point",
                font,
                expected=expected,
                revision_provider=lambda: ("stable", 2),
            )

        self.assertNotEqual(
            first.document_fingerprint, expected.document_fingerprint
        )
        self.assertEqual(
            second.document_fingerprint, first.document_fingerprint
        )
        self.assertEqual(persistent.call_count, 3)

    def test_bulk_verification_keeps_its_source_until_native_revision_settles(self) -> None:
        font = _TransactionalFont()
        model = native_font_to_model(font)
        expected = document_adapter.CanonicalSnapshot.from_model(model)
        cache = document_adapter._RevisionBoundGlyphModelCache()

        with mock.patch.dict(
            os.environ, {"GLYPHS_MCP_VERIFY_SERIALIZED_SOURCE": "1"}
        ), mock.patch.object(
            document_adapter,
            "_native_persistent_font_model",
            return_value=model,
        ) as persistent, mock.patch.object(
            document_adapter,
            "_native_canonical_root",
            side_effect=AssertionError(
                "an unsettled bulk capture switched canonical sources"
            ),
        ):
            cache.capture_snapshot(
                "doc-persistent-settle",
                font,
                revision_provider=lambda: ("stable", 1),
            )
            cache.invalidate_impact(
                "doc-persistent-settle",
                document_adapter.CanonicalImpact.from_paths(
                    model, [("glyphs",)]
                ),
                font=font,
            )
            revisions = iter(
                [
                    ("changing", 1),
                    ("changing", 2),
                    ("stable", 2),
                    ("stable", 2),
                ]
            )
            first = cache.capture_snapshot(
                "doc-persistent-settle",
                font,
                expected=expected,
                revision_provider=lambda: next(revisions),
            )
            second = cache.capture_snapshot(
                "doc-persistent-settle",
                font,
                expected=expected,
                revision_provider=lambda: next(revisions),
            )

        self.assertEqual(
            first.document_fingerprint, expected.document_fingerprint
        )
        self.assertEqual(
            second.document_fingerprint, expected.document_fingerprint
        )
        self.assertEqual(persistent.call_count, 3)

    def test_exact_bulk_verification_keeps_its_source_for_the_agreement_read(self) -> None:
        font = _TransactionalFont()
        model = native_font_to_model(font)
        expected = document_adapter.CanonicalSnapshot.from_model(model)
        cache = document_adapter._RevisionBoundGlyphModelCache()

        with mock.patch.dict(
            os.environ, {"GLYPHS_MCP_VERIFY_SERIALIZED_SOURCE": "1"}
        ), mock.patch.object(
            document_adapter,
            "_native_persistent_font_model",
            return_value=model,
        ) as persistent, mock.patch.object(
            document_adapter,
            "_font_model_with_glyphs",
            side_effect=AssertionError(
                "the exact agreement read switched canonical sources"
            ),
        ):
            cache.capture_snapshot(
                "doc-persistent-exact-pair",
                font,
                revision_provider=lambda: ("stable", 1),
            )
            cache.invalidate_impact(
                "doc-persistent-exact-pair",
                document_adapter.CanonicalImpact.from_paths(
                    model, [("glyphs",)]
                ),
                font=font,
            )
            first = cache.capture_snapshot(
                "doc-persistent-exact-pair",
                font,
                expected=expected,
                revision_provider=lambda: ("stable", 2),
            )
            second = cache.capture_snapshot(
                "doc-persistent-exact-pair",
                font,
                expected=expected,
                revision_provider=lambda: ("stable", 2),
            )

        self.assertEqual(first.document_fingerprint, expected.document_fingerprint)
        self.assertEqual(second.document_fingerprint, expected.document_fingerprint)
        # The second read may reuse the first result when identical native
        # revision evidence proves no intervening change. It must never switch
        # to another canonical source.
        self.assertEqual(persistent.call_count, 2)

    def test_unscoped_refresh_preserves_the_serialized_source_family(self) -> None:
        font = _TransactionalFont()
        model = native_font_to_model(font)
        cache = document_adapter._RevisionBoundGlyphModelCache()

        with mock.patch.dict(
            os.environ, {"GLYPHS_MCP_VERIFY_SERIALIZED_SOURCE": "1"}
        ), mock.patch.object(
            document_adapter, "_native_persistent_font_model", return_value=model
        ):
            first = cache.capture_snapshot(
                "doc-serialized-refresh",
                font,
                revision_provider=lambda: ("stable", 1),
            )

        with mock.patch.dict(
            os.environ, {"GLYPHS_MCP_VERIFY_SERIALIZED_SOURCE": "0"}
        ), mock.patch.object(
            document_adapter, "_native_persistent_font_model", return_value=model
        ) as persistent, mock.patch.object(
            document_adapter,
            "_font_model_with_glyphs",
            side_effect=AssertionError(
                "an unscoped refresh switched away from serialized canonical state"
            ),
        ):
            second = cache.capture_snapshot(
                "doc-serialized-refresh",
                font,
                revision_provider=lambda: ("stable", 2),
            )

        persistent.assert_called_once()
        self.assertEqual(
            second.document_fingerprint, first.document_fingerprint
        )

    def test_host_finalizes_bulk_snapshot_after_main_thread_callback_returns(self) -> None:
        class TrackingExecutor:
            def __init__(self):
                self.active = False

            def run(self, callback):
                self.active = True
                try:
                    return callback()
                finally:
                    self.active = False

        font = _TransactionalFont()
        expected = native_font_to_model(font)
        executor = TrackingExecutor()
        host = GlyphsDocumentHost(_App(font), executor=executor)
        document_id = host.list_documents()[0].document_id
        original = host._canonical_model_cache.finalize_persistent_capture

        def finalize(draft):
            self.assertFalse(executor.active)
            return original(draft)

        with mock.patch.dict(
            os.environ, {"GLYPHS_MCP_VERIFY_SERIALIZED_SOURCE": "1"}
        ), mock.patch.object(
            document_adapter,
            "_native_persistent_font_model",
            return_value=expected,
        ), mock.patch.object(
            host._canonical_model_cache,
            "finalize_persistent_capture",
            side_effect=finalize,
        ) as finalized:
            snapshot = host.capture_snapshot(document_id)

        self.assertEqual(snapshot.document_fingerprint, fingerprint_model(expected))
        finalized.assert_called_once()

    def test_invalidated_live_capture_streams_the_predicted_impact(self) -> None:
        font = _TransactionalFont()
        glyph = SimpleNamespace(
            name="A",
            export=True,
            mastersCompatible=True,
            layers=[],
            lastChange="revision-1",
            changeCount=lambda: 0,
        )
        font.glyphs = [glyph]
        before = native_font_to_model(font)
        expected_model = copy.deepcopy(before)
        expected_model["glyphs"]["A"]["export"] = False
        expected = document_adapter.CanonicalSnapshot.from_model(expected_model)
        changes = diff_models(before, expected_model)
        cache = document_adapter._RevisionBoundGlyphModelCache()
        revision = [1]

        with mock.patch.object(
            document_adapter,
            "_native_persistent_font_model",
            side_effect=AssertionError("ordinary capture used serialized audit source"),
        ):
            cache.capture_snapshot(
                "doc-stream",
                font,
                revision_provider=lambda: ("revision", revision[0]),
            )
        glyph.export = False
        revision[0] += 1
        cache.invalidate_impact(
            "doc-stream",
            document_adapter.CanonicalImpact.from_change_set(before, changes),
        )

        with mock.patch.object(
            document_adapter,
            "_native_persistent_font_model",
            side_effect=AssertionError("warm verification used serialized audit source"),
        ) as persistent, mock.patch.object(
            document_adapter,
            "_font_model_with_glyphs",
            side_effect=AssertionError("warm verification rebuilt every root"),
        ):
            captured = cache.capture_snapshot(
                "doc-stream",
                font,
                expected=expected,
                revision_provider=lambda: ("revision", revision[0]),
            )

        self.assertEqual(captured.document_fingerprint, expected.document_fingerprint)
        persistent.assert_not_called()

    def test_streaming_fallback_detects_an_unexpected_live_glyph_change(self) -> None:
        font = _TransactionalFont()
        glyph = SimpleNamespace(
            name="A",
            unicode="0041",
            export=True,
            mastersCompatible=True,
            layers=[],
            lastChange="revision-1",
            changeCount=lambda: 0,
        )
        font.glyphs = [glyph]
        before = native_font_to_model(font)
        expected_model = copy.deepcopy(before)
        expected_model["glyphs"]["A"]["export"] = False
        expected = document_adapter.CanonicalSnapshot.from_model(expected_model)
        changes = diff_models(before, expected_model)
        cache = document_adapter._RevisionBoundGlyphModelCache()
        revision = [1]

        with mock.patch.object(
            document_adapter,
            "_native_persistent_font_model",
            side_effect=AssertionError("ordinary capture used serialized audit source"),
        ) as persistent:
            cache.capture_snapshot(
                "doc-stream-authoritative",
                font,
                revision_provider=lambda: ("revision", revision[0]),
            )
            # Simulate an unexpected sibling field mutation accompanying the
            # requested export edit.
            glyph.export = False
            glyph.unicode = "0065"
            revision[0] += 1
            cache.invalidate_impact(
                "doc-stream-authoritative",
                document_adapter.CanonicalImpact.from_change_set(before, changes),
            )
            captured = cache.capture_snapshot(
                "doc-stream-authoritative",
                font,
                expected=expected,
                revision_provider=lambda: ("revision", revision[0]),
            )

        self.assertNotEqual(captured.document_fingerprint, expected.document_fingerprint)
        self.assertEqual(captured.glyph_shards["A"]["unicode"], "0065")
        persistent.assert_not_called()

    def test_authoritative_glyph_resolver_reuses_one_font_serializer_capture(self) -> None:
        font = _TransactionalFont()
        glyph_a = SimpleNamespace(name="A")
        glyph_b = SimpleNamespace(name="B")
        expected_a = {"name": "A", "layers": [], "export": False}
        expected_b = {"name": "B", "layers": [], "export": True}

        with mock.patch.dict(
            os.environ, {"GLYPHS_MCP_VERIFY_SERIALIZED_SOURCE": "1"}
        ), mock.patch.object(
            document_adapter,
            "_native_persistent_font_model",
            return_value={"glyphs": {"A": expected_a, "B": expected_b}},
        ) as complete, mock.patch.object(
            document_adapter,
            "_glyph_model",
            side_effect=AssertionError("projected getters are not authoritative"),
        ):
            resolver = document_adapter._AuthoritativeGlyphShardResolver(font)
            captured_a = resolver.capture(
                glyph_a, layer_order_reference=expected_a
            )
            captured_b = resolver.capture(
                glyph_b, layer_order_reference=expected_b
            )

        self.assertEqual(captured_a, expected_a)
        self.assertEqual(captured_b, expected_b)
        self.assertIsNot(captured_a, expected_a)
        self.assertIsNot(captured_b, expected_b)
        complete.assert_called_once_with(
            font, instance_ids=None, document_path=None
        )

    def test_glyph_metadata_impact_does_not_expand_component_dependencies(self) -> None:
        model = {
            "glyphs": {
                "A": {"layers": {"M1": {"components": []}}},
                "Aacute": {
                    "layers": {"M1": {"components": [{"name": "A"}]}}
                },
            }
        }

        impact = document_adapter.CanonicalImpact.from_paths(
            model, [("glyphs", "A", "export")]
        )

        self.assertEqual(impact.glyph_names, ("A",))

    def test_layer_geometry_impact_retains_transitive_component_dependencies(self) -> None:
        model = {
            "glyphs": {
                "A": {"layers": {"M1": {"components": []}}},
                "Aacute": {
                    "layers": {"M1": {"components": [{"name": "A"}]}}
                },
            }
        }

        impact = document_adapter.CanonicalImpact.from_paths(
            model, [("glyphs", "A", "layers", "M1", "shapes")]
        )

        self.assertEqual(impact.glyph_names, ("A", "Aacute"))

    def test_native_data_bridge_uses_the_bounded_buffer_not_object_iteration(self) -> None:
        payload = b'{"glyphs":{}}'

        class Pointer:
            def as_buffer(self, length):
                self.length = length
                return memoryview(payload)

        class NativeData:
            def __init__(self):
                self.pointer = Pointer()

            def length(self):
                return len(payload)

            def bytes(self):
                return self.pointer

            def __bytes__(self):
                raise AssertionError("unbounded NSData iteration was used")

        data = NativeData()
        self.assertEqual(document_adapter._native_data_bytes(data), payload)
        self.assertEqual(data.pointer.length, len(payload))

    def test_settings_replay_uses_the_owned_font_mapping_setter(self) -> None:
        class Font:
            def __init__(self):
                self._settings = {}
                self.read_calls = []

            def readSettingDict_(self, value):
                self.read_calls.append(copy.deepcopy(value))
                self._settings = copy.deepcopy(value)

        font = Font()
        target = {"colorSpace": "apple-rgb", "dependencies": {}}
        document_adapter._apply_settings_model(font, {}, target)

        self.assertEqual(font._settings, target)
        self.assertEqual(font.read_calls, [target])

    def test_detached_scoped_capture_streams_impact_and_reuses_unchanged_shards(self) -> None:
        source = {
            "font": {"familyName": "Persistent"},
            "features": [{"id": "liga", "name": "liga", "code": "sub f i by fi;"}],
            "glyphs": {
                "A": {"id": "glyph:A", "name": "A", "export": True, "layers": []},
                "B": {"id": "glyph:B", "name": "B", "export": True, "layers": []},
            },
            "glyphOrder": ["A", "B"],
        }
        glyph_a = SimpleNamespace(name="A", export=False, mastersCompatible=True, layers=[])
        glyph_b = SimpleNamespace(name="B", export=True, mastersCompatible=True, layers=[])
        font = SimpleNamespace(glyphs=[glyph_a, glyph_b])
        impact = document_adapter.CanonicalImpact.from_paths(
            source, [("glyphs", "A", "export")]
        )

        with mock.patch.object(
            document_adapter,
            "_native_persistent_font_model",
            side_effect=AssertionError("scoped verification rebuilt the full tree"),
        ):
            captured = document_adapter._scoped_font_model(
                font,
                source,
                MutationScope(("glyphs",), ("A",)),
                impact=impact,
                expected_model=source,
            )

        self.assertFalse(captured["glyphs"]["A"]["export"])
        self.assertIs(captured["glyphs"]["B"], source["glyphs"]["B"])
        self.assertIs(captured["features"], source["features"])

    def test_detached_scoped_capture_returns_a_streamed_snapshot_for_snapshot_source(self) -> None:
        source_model = {
            "font": {"familyName": "Persistent"},
            "features": [{"id": "liga", "name": "liga", "code": "sub f i by fi;"}],
            "glyphs": {
                "A": {"id": "glyph:A", "name": "A", "export": True, "layers": []},
                "B": {"id": "glyph:B", "name": "B", "export": True, "layers": []},
            },
            "glyphOrder": ["A", "B"],
        }
        source = document_adapter.CanonicalSnapshot.from_shards(
            {name: value for name, value in source_model.items() if name != "glyphs"},
            source_model["glyphs"],
        )
        glyph_a = SimpleNamespace(name="A", export=False, mastersCompatible=True, layers=[])
        glyph_b = SimpleNamespace(name="B", export=True, mastersCompatible=True, layers=[])
        font = SimpleNamespace(glyphs=[glyph_a, glyph_b])
        impact = document_adapter.CanonicalImpact.from_paths(
            source, [("glyphs", "A", "export")]
        )

        with mock.patch.object(
            document_adapter,
            "_native_persistent_font_model",
            side_effect=AssertionError("scoped verification rebuilt the full tree"),
        ):
            captured = document_adapter._scoped_font_model(
                font,
                source,
                MutationScope(("glyphs",), ("A",)),
                impact=impact,
                expected_model=source,
            )

        self.assertIsInstance(captured, document_adapter.CanonicalSnapshot)
        self.assertEqual(fingerprint_model(captured), captured.document_fingerprint)
        self.assertIs(captured.glyph_shards["B"], source.glyph_shards["B"])

    def test_detached_clone_normalization_projects_copy_drift_without_native_replay(self) -> None:
        font = _TransactionalFont()
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        observed = {
            "settings": {},
            "kerning": {"context": {}},
            "masters": [{"id": "M1", "visible": False}],
            "glyphs": {},
        }
        source = {
            "settings": {"colorSpace": 1},
            "kerning": {"context": {"M1": {}}},
            "masters": [{"id": "M1", "visible": True}],
            "glyphs": {},
        }

        with mock.patch.object(
            document_adapter,
            "_apply_target_model",
            side_effect=AssertionError("clone normalization must be projection-only"),
        ):
            reconciled, projection = host._reconcile_detached_clone(
                font,
                source,
                observed,
            )

        self.assertIs(reconciled, source)
        self.assertEqual(
            projection.normalize(observed),
            source,
        )

    def test_detached_clone_projection_preserves_requested_and_unexpected_values(self) -> None:
        font = _TransactionalFont()
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        source = {"settings": {"colorSpace": 0}, "glyphs": {}}
        observed = {"settings": {"colorSpace": 1}, "glyphs": {}}

        _, projection = host._reconcile_detached_clone(font, source, observed)

        self.assertEqual(
            projection.normalize(
                observed,
                protected_paths=(("settings", "colorSpace"),),
            ),
            observed,
        )
        unexpected = {"settings": {"colorSpace": 2}, "glyphs": {}}
        self.assertEqual(projection.normalize(unexpected), unexpected)

    def test_detached_clone_normalization_never_replays_derived_diagnostics(self) -> None:
        font = _TransactionalFont()
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        observed = {
            "settings": {},
            "glyphs": {
                "A": {
                    "name": "A",
                    "layers": [{"id": "M1"}],
                }
            },
        }
        source = {
            "settings": {"colorSpace": "apple-rgb"},
            "glyphs": {
                "A": {
                    "name": "A",
                    "layers": [{"id": "M1"}],
                }
            },
        }

        with mock.patch.object(
            document_adapter,
            "_apply_target_model",
            side_effect=AssertionError("derived normalization must be projection-only"),
        ):
            reconciled, projection = host._reconcile_detached_clone(
                font, source, observed
            )

        self.assertIs(reconciled, source)
        self.assertEqual(
            [change.path for change in projection.artifacts.changes],
            [("settings", "colorSpace")],
        )

    def test_snapshot_clone_reconciliation_reuses_shards_without_whole_tree_projection(self) -> None:
        font = _TransactionalFont()
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        source = CanonicalSnapshot.from_model(
            {
                "settings": {"colorSpace": "apple-rgb"},
                "glyphs": {
                    "A": {
                        "name": "A",
                        "mastersCompatible": True,
                        "layers": [{"id": "M1"}],
                    },
                    "B": {"name": "B", "layers": []},
                },
            }
        )
        observed = source.materialize()
        observed["settings"] = {}
        observed["glyphs"]["A"]["mastersCompatible"] = False

        with mock.patch.object(
            document_adapter,
            "semantic_identity_document",
            side_effect=AssertionError("snapshot reconciliation projected the whole tree"),
        ):
            reconciled, projection = host._reconcile_detached_clone(
                font, source, observed
            )

        self.assertIs(reconciled, source)
        self.assertEqual(
            [change.path for change in projection.artifacts.changes],
            [("settings", "colorSpace")],
        )

    def test_snapshot_clone_reconciliation_learns_hidden_artifacts_once_per_source(self) -> None:
        font = _TransactionalFont()
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        source = CanonicalSnapshot.from_model(
            {
                "settings": {"colorSpace": "apple-rgb"},
                "glyphs": {
                    "A": {
                        "name": "A",
                        "layers": [{
                            "id": "M1",
                            "background": {
                                "hints": [{"id": "hint:corner:0", "origin": None}]
                            },
                        }],
                    },
                },
            }
        )
        scoped_observed = source
        complete_clone = source.materialize()
        complete_clone["glyphs"]["A"]["layers"][0]["background"]["hints"][0][
            "origin"
        ] = [1, 1]

        with mock.patch.object(
            document_adapter,
            "_native_persistent_font_model",
            return_value=complete_clone,
        ) as persistent:
            reconciled, projection = host._reconcile_detached_clone(
                font,
                source,
                scoped_observed,
                document_id="doc-clone-artifacts",
            )
            _again, cached = host._reconcile_detached_clone(
                font,
                source,
                scoped_observed,
                document_id="doc-clone-artifacts",
            )

        self.assertIs(reconciled, source)
        self.assertEqual(
            [change.path for change in projection.artifacts.changes],
            [
                (
                    "glyphs",
                    "A",
                    "layers",
                    "M1",
                    "background",
                    "hints",
                    "hint:corner:0",
                    "origin",
                )
            ],
        )
        self.assertIs(cached, projection)
        persistent.assert_called_once()

    def test_complete_clone_capture_is_not_recaptured_during_reconciliation(self) -> None:
        font = _TransactionalFont()
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        source = CanonicalSnapshot.from_model(
            {
                "settings": {"colorSpace": "apple-rgb"},
                "glyphs": {"A": {"name": "A", "layers": []}},
            }
        )
        complete_observed = source.materialize()
        complete_observed["settings"] = {}

        with mock.patch.object(
            document_adapter,
            "_native_persistent_font_model",
            side_effect=AssertionError("complete clone capture was repeated"),
        ):
            reconciled, projection = host._reconcile_detached_clone(
                font,
                source,
                complete_observed,
                document_id="doc-complete-clone",
                observed_is_complete=True,
            )

        self.assertIs(reconciled, source)
        self.assertEqual(
            [change.path for change in projection.artifacts.changes],
            [("settings", "colorSpace")],
        )

    def test_master_order_does_not_protect_unmodified_copy_userdata_artifacts(self) -> None:
        font = _TransactionalFont()
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        source = CanonicalSnapshot.from_model(
            {
                "masters": [{"id": "M1", "userData": {}}],
                "glyphs": {},
            }
        )
        complete_observed = source.materialize()
        complete_observed["masters"][0]["userData"] = {
            "GSCornerRadius": 15,
            "GSExtrudeAngle": 30,
            "GSExtrudeOffset": 15,
        }

        reconciled, projection = host._reconcile_detached_clone(
            font,
            source,
            complete_observed,
            document_id="doc-copy-userdata",
            observed_is_complete=True,
        )
        normalized = projection.normalize(
            complete_observed,
            protected_paths=(("masters", "$order"),),
        )

        self.assertIs(reconciled, source)
        self.assertEqual(normalized["masters"][0]["userData"], {})
        self.assertEqual(
            [change.path for change in projection.artifacts.changes],
            [
                ("masters", "M1", "userData", "GSCornerRadius"),
                ("masters", "M1", "userData", "GSExtrudeAngle"),
                ("masters", "M1", "userData", "GSExtrudeOffset"),
            ],
        )

    def test_userdata_capture_bypasses_broken_dict_proxy_overrides(self) -> None:
        class GlyphsDictionaryProxy(dict):
            def keys(self):
                raise AttributeError("dict proxy has no Foundation allKeys")

            def get(self, key, default=None):
                raise AttributeError("dict proxy has no Foundation objectForKey")

            def __iter__(self):
                raise AttributeError("dict proxy iteration is unavailable")

        owner = SimpleNamespace(
            userData=GlyphsDictionaryProxy(
                {
                    "GSCornerRadius": 15,
                    "nested": GlyphsDictionaryProxy({"value": 30}),
                }
            )
        )

        self.assertEqual(
            document_adapter._user_data_model(owner),
            {"GSCornerRadius": 15, "nested": {"value": 30}},
        )

    def test_userdata_capture_prefers_the_native_persistent_selector(self) -> None:
        wrapper_projection = {}
        native_persistent_value = {"GSCornerRadius": 15}
        owner = SimpleNamespace(
            userData=wrapper_projection,
            pyobjc_instanceMethods=SimpleNamespace(
                userData=lambda: native_persistent_value
            ),
        )

        self.assertEqual(
            document_adapter._user_data_model(owner),
            native_persistent_value,
        )

    def test_snapshot_clone_reconciliation_projects_serialized_master_layer_order(self) -> None:
        font = _TransactionalFont()
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        source = CanonicalSnapshot.from_model(
            {
                "masters": [{"id": "M1"}, {"id": "M2"}],
                "glyphs": {
                    "A": {
                        "name": "A",
                        "layers": [
                            {"id": "M2", "isMasterLayer": True},
                            {"id": "M1", "isMasterLayer": True},
                            {"id": "special", "isMasterLayer": False},
                        ],
                    },
                },
            }
        )
        serialized_clone = source.materialize()
        serialized_clone["glyphs"]["A"]["layers"] = [
            serialized_clone["glyphs"]["A"]["layers"][1],
            serialized_clone["glyphs"]["A"]["layers"][0],
            serialized_clone["glyphs"]["A"]["layers"][2],
        ]

        with mock.patch.object(
            document_adapter,
            "_native_persistent_font_model",
            return_value=serialized_clone,
        ):
            reconciled, projection = host._reconcile_detached_clone(
                font,
                source,
                source,
                document_id="doc-serialized-order",
            )

        self.assertIs(reconciled, source)
        self.assertEqual(projection.artifacts.changes, ())

    def test_reconciliation_retains_an_immutable_expected_snapshot(self) -> None:
        snapshot = CanonicalSnapshot.from_model(
            {
                "font": {"familyName": "Snapshot"},
                "glyphs": {
                    "A": {"name": "A", "layers": [{"id": "M1"}]},
                },
            }
        )

        with mock.patch(
            "glyphs_mcp_v2.adapters.document.copy.deepcopy",
            side_effect=AssertionError("immutable expected snapshot was copied"),
        ):
            retained = document_adapter._retain_canonical_model(snapshot)

        self.assertIs(retained, snapshot)

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
            {
                "ltr": {"master-1": {"glyph_A": {"glyph_V": -80.0}}},
                "rtl": {},
                "vertical": {},
                "context": {},
            },
        )
        self.assertEqual(document_adapter._native_kerning_key(font, "glyph_A"), "A")

    def test_objc_kerning_dictionary_uses_the_same_semantic_boundary(self) -> None:
        class ObjCMapping:
            def __init__(self, values):
                self.values = values

            def keys(self):
                return list(self.values)

            def objectForKey_(self, key):
                return self.values[key]

        glyphs = [
            SimpleNamespace(name="A", id="native-A"),
            SimpleNamespace(name="V", id="native-V"),
        ]
        font = SimpleNamespace(
            glyphs=glyphs,
            kerning=ObjCMapping(
                {
                    "M1": ObjCMapping(
                        {
                            "native-A": ObjCMapping({"native-V": -80}),
                            "@MMK_L_A": ObjCMapping({"@MMK_R_V": -70}),
                        }
                    )
                }
            ),
        )

        self.assertEqual(
            document_adapter._kerning_domain_model(font, "kerning"),
            {
                "M1": {
                    "glyph_A": {"glyph_V": -80.0},
                    "@MMK_L_A": {"@MMK_R_V": -70.0},
                }
            },
        )

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
            name="liga",
            tag="liga",
            code="sub f i by fi;",
            automatic=False,
            disabled=False,
            notes="before",
            labels=[{"language": "en", "value": "Ligatures"}],
        )
        font = _TransactionalFont()
        font.features = [feature]
        before = native_font_to_model(font)
        after = copy.deepcopy(before)
        after["features"][0]["code"] = "sub f f i by ffi;"
        after["features"][0]["disabled"] = True
        after["features"][0]["notes"] = "after"
        after["features"][0]["labels"] = [
            {"language": "fr", "value": "Ligatures"}
        ]
        changes = diff_models(before, after)
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())

        self.assertTrue(host.supports_change_set(changes))
        document_adapter._apply_target_model(font, before, after, changes)

        self.assertIs(font.features[0], feature)
        self.assertEqual(feature.code, "sub f f i by ffi;")
        self.assertTrue(feature.disabled)
        self.assertEqual(feature.notes, "after")
        self.assertEqual(feature.labels[0]["language"], "fr")

    def test_feature_labels_use_the_glyphs4_singular_info_value_contract(self) -> None:
        class Value:
            def __init__(self, language="dflt", value=""):
                self.languageTag = language
                self.value = value

        class Localized:
            def __init__(self):
                self.key = ""
                self.value = None
                self.values = []

        class Single:
            def __init__(self):
                self.key = ""
                self.value = None

        class Feature:
            def __init__(self):
                self.name = "ss01"
                self.code = "sub a by a.ss01;"
                self.automatic = False
                self.disabled = False
                self.notes = ""
                self._label = Localized()
                self._label.values = [Value("dflt", "First")]

            def label(self):
                return self._label

            def setLabel_(self, value):
                self._label = value

        feature = Feature()
        font = _TransactionalFont()
        font.features = [feature]
        before = native_font_to_model(font)
        self.assertEqual(
            before["features"][0]["labels"],
            [{"language": "dflt", "value": "First"}],
        )
        after = copy.deepcopy(before)
        after["features"][0]["labels"] = [
            {"language": "FRA", "value": "Première"}
        ]
        glyphs_module = SimpleNamespace(
            GSInfoValue=Value,
            GSInfoValueLocalized=Localized,
            GSInfoValueSingle=Single,
        )

        with mock.patch.dict(sys.modules, {"GlyphsApp": glyphs_module}):
            document_adapter._apply_target_model(
                font, before, after, diff_models(before, after)
            )

        self.assertEqual(len(feature._label.values), 1)
        self.assertEqual(feature._label.values[0].languageTag, "FRA")
        self.assertEqual(feature._label.values[0].value, "Première")

    def test_opentype_replay_uses_each_registered_native_field_set(self) -> None:
        class NativeClass:
            def __init__(self):
                self.name = "MCP_A"
                self.code = "A"
                self.automatic = False
                self.disabled = False
                self.notes = None

            @property
            def tag(self):
                raise AssertionError("GSClass has no feature tag")

            @tag.setter
            def tag(self, value):
                raise AssertionError("GSClass must never receive a feature tag")

        native = NativeClass()
        font = _TransactionalFont()
        font.classes = [native]
        before = native_font_to_model(font)
        after = copy.deepcopy(before)
        after["classes"][0]["code"] = "A A"
        after["classes"][0]["notes"] = "reviewed"

        document_adapter._apply_target_model(
            font, before, after, diff_models(before, after)
        )

        self.assertIs(font.classes[0], native)
        self.assertEqual(native.code, "A A")
        self.assertEqual(native.notes, "reviewed")

    def test_registered_v6_root_records_replay_through_one_target_model_path(self) -> None:
        font = _TransactionalFont()
        font.customParameters = []
        font.properties = []
        font.userData = {}
        font.settings = {}
        font.metrics = []
        font.stems = []
        font.numbers = []
        before = native_font_to_model(font)
        after = copy.deepcopy(before)
        after["axes"] = [{
            "id": "wght",
            "tag": "wght",
            "name": "Weight",
            "names": [],
            "default": 400,
            "hidden": False,
            "userData": {"source": "v6"},
        }]
        for root, kind, name, metric_type in (
            ("metrics", "metric", "Cap Height", 2),
            ("stems", "stem", "Vertical", None),
            ("numbers", "number", "Overshoot", None),
        ):
            semantic = "{}:{}:False:".format(metric_type, name)
            after[root] = [{
                "id": deterministic_occurrence_id(kind, semantic, 0),
                "type": metric_type,
                "name": name,
                "horizontal": False,
                "filter": None,
            }]
        after["font"]["customParameters"] = [{
            "id": deterministic_occurrence_id(
                "parameter", "Use Typo Metrics", 0
            ),
            "name": "Use Typo Metrics",
            "value": True,
            "disabled": False,
        }]
        after["font"]["userData"] = {"com.example.v6": {"enabled": True}}
        after["settings"] = {
            **before["settings"],
            "disablesNiceNames": True,
            "keyboardIncrement": 2,
        }

        def construct(kind, name=""):
            if kind == "axis":
                return SimpleNamespace(
                    axisTag="", name="", names=[], default=None,
                    hidden=False, userData={},
                )
            if kind in {"metric", "stem", "number"}:
                return SimpleNamespace(
                    name="", type=None, horizontal=False, filter=None
                )
            if kind == "customParameter":
                return SimpleNamespace(name="", value=None, disabled=False)
            self.fail("unexpected v6 entity kind {}".format(kind))

        with mock.patch.object(
            document_adapter, "_construct_native_entity", side_effect=construct
        ):
            document_adapter._apply_target_model(
                font, before, after, diff_models(before, after)
            )

        self.assertEqual(native_font_to_model(font), after)

    def test_directional_and_contextual_kerning_replay_exactly(self) -> None:
        def glyph(name):
            return SimpleNamespace(
                name=name,
                id="native-{}".format(name),
                lastChange="revision-1",
                changeCount=lambda: 0,
                mastersCompatible=True,
                layers=[],
            )

        font = _TransactionalFont()
        font.glyphs = [glyph("A"), glyph("V")]
        font.kerning = {}
        font.kerningRTL = {}
        font.kerningVertical = {}
        font.kerningContext = {}
        context_calls = []

        def set_pair(master, left, right, value, direction=0):
            domain = {0: font.kerning, 1: font.kerningRTL, 2: font.kerningVertical}[direction]
            domain.setdefault(master, {}).setdefault(left, {})[right] = value

        font.setKerningForPair = set_pair
        def set_context(context_key, master_id, value):
            context_calls.append(("set", context_key, master_id, value))
            font.kerningContext.setdefault(context_key, {})[master_id] = value

        def remove_context(context_key, master_id):
            context_calls.append(("remove", context_key, master_id))
            values = font.kerningContext.get(context_key, {})
            values.pop(master_id, None)
            if not values:
                font.kerningContext.pop(context_key, None)

        font.setContextKerningForKey = set_context
        font.removeContextKerningForKey = remove_context
        target = {
            "ltr": {"M1": {"glyph_A": {"glyph_V": -80}}},
            "rtl": {"M1": {"glyph_V": {"glyph_A": -40}}},
            "vertical": {"M1": {"glyph_A": {"glyph_V": -20}}},
            "context": {"A * V A": {"M1": -10}},
        }

        document_adapter._replace_kerning(font, target)

        self.assertEqual(document_adapter._kerning_model(font), target)
        self.assertEqual(
            context_calls, [("set", "A * V A", "M1", -10.0)]
        )

        document_adapter._replace_kerning(
            font,
            {
                **target,
                "context": {"A V * A": {"M1": 0}},
            },
        )
        self.assertEqual(
            context_calls[-2:],
            [
                ("remove", "A * V A", "M1"),
                ("set", "A V * A", "M1", 0.0),
            ],
        )

    def test_absent_native_kerning_context_matches_the_empty_serialized_domain(self) -> None:
        font = SimpleNamespace(
            glyphs=[],
            kerning={},
            kerningRTL={},
            kerningVertical={},
            kerningContext=None,
        )

        self.assertEqual(document_adapter._kerning_model(font)["context"], {})

    def test_context_selector_support_is_checked_before_pair_mutation(self) -> None:
        calls = []
        font = SimpleNamespace(
            glyphs=[],
            kerning={},
            kerningRTL={},
            kerningVertical={},
            kerningContext={},
            setKerningForPair=lambda *arguments: calls.append(arguments),
            removeKerningForPair=lambda *arguments: calls.append(arguments),
        )
        target = {
            "ltr": {"M1": {"A": {"V": -80}}},
            "rtl": {},
            "vertical": {},
            "context": {"L * quoteright A": {"M1": -40}},
        }

        with self.assertRaisesRegex(
            HostAccessError, "contextual kerning assignment"
        ):
            document_adapter._replace_kerning(font, target)

        self.assertEqual(calls, [])

    def test_guide_attributes_have_one_canonical_capture_and_replay_name(self) -> None:
        guide = SimpleNamespace(
            name="cap",
            type=0,
            position=(0, 700),
            hasSlope=False,
            attributes={"color": [1, 0, 0, 1]},
        )
        captured = document_adapter._ordered_records(
            SimpleNamespace(guides=[guide]),
            "guides",
            kind="guide",
            fields=("attr", "name", "pos", "slope", "type"),
        )
        self.assertEqual(captured[0]["attr"], {"color": [1, 0, 0, 1]})
        self.assertFalse(captured[0]["slope"])
        target = copy.deepcopy(captured)
        target[0]["attr"] = {"color": [0, 1, 0, 1]}
        target[0]["slope"] = True
        document_adapter._apply_ordered_record_collection(
            SimpleNamespace(guides=[guide]),
            "guides",
            captured,
            target,
            kind="guide",
            fields={
                "attr": "attributes",
                "name": "name",
                "pos": "position",
                "slope": "hasSlope",
                "type": "type",
            },
        )
        self.assertEqual(guide.attributes, {"color": [0, 1, 0, 1]})
        self.assertTrue(guide.hasSlope)

    def test_nested_glyph_replay_does_not_rewrite_canonical_parent_order(self) -> None:
        glyph = SimpleNamespace(name="A", export=True)
        font = SimpleNamespace(glyphs=[glyph])
        before = {
            "glyphs": {"A": {"name": "A", "export": True}},
            "glyphOrder": ["A"],
        }
        after = copy.deepcopy(before)
        after["glyphs"]["A"]["export"] = False
        changes = diff_models(before, after)

        with mock.patch.object(document_adapter, "_apply_glyph_order") as apply_order:
            document_adapter._apply_target_model(
                font,
                before,
                after,
                changes,
            )

        self.assertFalse(glyph.export)
        apply_order.assert_not_called()

    def test_layer_replay_uses_one_canonical_source_and_one_outer_verifier(self) -> None:
        native = SimpleNamespace(
            layerId="L1",
            associatedMasterId="M1",
            name="Regular",
            isMasterLayer=True,
        )
        glyph = SimpleNamespace(layers=[native])
        font = SimpleNamespace(axes=[])
        before_layer = {
            "id": "L1",
            "masterId": "M1",
            "name": "Regular",
            "visible": True,
        }
        after_layer = {**before_layer, "visible": False}
        current = {"layers": [before_layer]}
        target = {"layers": [after_layer]}

        with mock.patch.object(
            document_adapter, "_apply_layer_canonical_pass"
        ) as apply_pass, mock.patch.object(
            document_adapter,
            "_layer_model",
            side_effect=AssertionError("ordinary replay must not recapture a second model"),
        ):
            document_adapter._apply_layer_collection(
                font,
                glyph,
                "A",
                current,
                target,
            )

        apply_pass.assert_called_once_with(
            native,
            before_layer,
            after_layer,
            layer_root=("glyphs", "A", "layers", "L1"),
            replacement_roots=(),
        )

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

    def test_collection_reorder_can_permute_identity_storage_in_one_notification(self) -> None:
        first = SimpleNamespace(name="First")
        second = SimpleNamespace(name="Second")
        third = SimpleNamespace(name="Third")
        collection = _AtomicCollectionProxy([first, second, third])
        storage = _MutableIdentityStorage([first, second, third])
        owner = _CollectionChangeOwner()

        document_adapter._replace_native_collection_order(
            collection,
            [third, first, second],
            identity_storage=storage,
            notification_owner=owner,
            notification_key="fontMasters",
        )

        self.assertEqual(storage.values, [third, first, second])
        self.assertEqual(storage.exchanges, [(0, 2), (1, 2)])
        self.assertEqual(
            owner.notifications,
            [("will", "fontMasters"), ("did", "fontMasters")],
        )
        self.assertEqual(collection.atomic_assignment_count, 0)
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
                    "index": 0,
                }
            ],
        )
        after = build.change_set.apply(before)

        with mock.patch.object(
            document_adapter,
            "_replace_glyph_layer_collection",
            wraps=document_adapter._replace_glyph_layer_collection,
        ) as replace_layers:
            document_adapter._apply_target_model(
                font,
                before,
                after,
                build.change_set,
                capabilities=build.capabilities,
                execution_context=build.execution_context,
            )

        # The master lifecycle attachment already established membership.
        # Layer replay must not perform a second whole-collection assignment
        # when only Glyphs' root-owned master prefix presentation differs.
        replace_layers.assert_not_called()

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

    def test_layer_field_replay_does_not_reassign_unchanged_collection_order(self) -> None:
        font = _master_lifecycle_font()
        glyph = font.glyphs[0]
        current = document_adapter._glyph_model(glyph)
        target = copy.deepcopy(current)
        target["layers"][0]["visible"] = not bool(
            target["layers"][0].get("visible")
        )

        with mock.patch.object(
            document_adapter,
            "_replace_glyph_layer_collection",
            side_effect=AssertionError("unchanged layer order was reassigned"),
        ) as replace_layers, mock.patch.object(
            document_adapter,
            "_reconcile_layer_to_canonical_target",
        ):
            document_adapter._apply_layer_collection(
                font,
                glyph,
                glyph.name,
                current,
                target,
            )

        replace_layers.assert_not_called()

    def test_layer_field_replay_does_not_claim_host_master_order(self) -> None:
        regular = _MasterLifecycleLayer(
            "master-regular", "Regular", native_only="regular"
        )
        condensed = _MasterLifecycleLayer(
            "master-condensed", "Condensed", native_only="condensed"
        )
        special = _MasterLifecycleLayer(
            "special-layer", "Special", native_only="special"
        )
        special.isMasterLayer = False
        special.isSpecialLayer = True
        special.isBackupLayer = True
        special.associatedMasterId = "master-regular"
        glyph = _MasterLifecycleGlyph(
            "A", [condensed, regular, special]
        )
        font = SimpleNamespace(axes=[], glyphs=[glyph], masters=[])
        glyph.font = font
        current = {
            "layers": [
                document_adapter._layer_model(regular),
                document_adapter._layer_model(condensed),
                document_adapter._layer_model(special),
            ]
        }
        target = copy.deepcopy(current)
        target["layers"][2]["visible"] = True

        with mock.patch.object(
            document_adapter,
            "_replace_glyph_layer_collection",
            side_effect=AssertionError(
                "a scalar replay attempted to own master-layer order"
            ),
        ) as replace_layers:
            document_adapter._apply_layer_collection(
                font,
                glyph,
                glyph.name,
                current,
                target,
            )

        replace_layers.assert_not_called()
        self.assertTrue(special.visible)

    def test_layer_membership_replay_preserves_host_master_prefix_order(self) -> None:
        regular = _MasterLifecycleLayer(
            "master-regular", "Regular", native_only="regular"
        )
        condensed = _MasterLifecycleLayer(
            "master-condensed", "Condensed", native_only="condensed"
        )
        special = _MasterLifecycleLayer(
            "special-layer", "Special", native_only="special"
        )
        special.isMasterLayer = False
        special.isSpecialLayer = True
        special.isBackupLayer = True
        special.associatedMasterId = "master-regular"
        glyph = _MasterLifecycleGlyph("A", [condensed, regular, special])
        font = SimpleNamespace(axes=[], glyphs=[glyph], masters=[])
        glyph.font = font

        current = {
            "layers": [
                document_adapter._layer_model(regular),
                document_adapter._layer_model(condensed),
                document_adapter._layer_model(special),
            ]
        }
        duplicate = special.copy()
        duplicate.layerId = "special-duplicate"
        duplicate.name = "Duplicate"
        target = copy.deepcopy(current)
        target["layers"].insert(
            2, document_adapter._layer_model(duplicate)
        )

        document_adapter._apply_layer_collection(
            font,
            glyph,
            "A",
            current,
            target,
            execution_context={
                "layerSources": {"A/special-duplicate": "special-layer"}
            },
        )

        self.assertEqual(
            [layer.layerId for layer in glyph.layers.values()],
            [
                "master-condensed",
                "master-regular",
                "special-duplicate",
                "special-layer",
            ],
        )

    def test_layer_lifecycle_refuses_master_membership_change_before_native_write(self) -> None:
        font = _master_lifecycle_font()
        glyph = font.glyphs[0]
        current = document_adapter._glyph_model(glyph)
        target = copy.deepcopy(current)
        target["layers"] = [
            layer
            for layer in target["layers"]
            if layer["id"] != "master_regular"
        ]

        with self.assertRaisesRegex(
            HostAccessError, "cannot change master-layer membership"
        ):
            document_adapter._apply_layer_collection(
                font,
                glyph,
                glyph.name,
                current,
                target,
            )

    def test_master_lifecycle_preserves_host_owned_master_layer_order(self) -> None:
        regular = _MasterLifecycleLayer(
            "master-regular", "Regular", native_only="regular"
        )
        condensed = _MasterLifecycleLayer(
            "master-condensed", "Condensed", native_only="condensed"
        )
        added = _MasterLifecycleLayer(
            "master-added", "Added", native_only="added"
        )
        special = _MasterLifecycleLayer(
            "special-layer", "Special", native_only="special"
        )
        special.isMasterLayer = False
        special.isSpecialLayer = True
        special.associatedMasterId = "master-regular"
        special.isBackupLayer = True

        glyph = _MasterLifecycleGlyph(
            "A", [condensed, added, regular, special]
        )
        font = SimpleNamespace(axes=[], glyphs=[glyph], masters=[])
        glyph.font = font

        current = {
            "layers": [
                document_adapter._layer_model(regular),
                document_adapter._layer_model(condensed),
                document_adapter._layer_model(special),
            ]
        }
        target = {
            "layers": [
                document_adapter._layer_model(regular),
                document_adapter._layer_model(added),
                document_adapter._layer_model(condensed),
                document_adapter._layer_model(special),
            ]
        }

        with mock.patch.object(
            document_adapter,
            "_replace_glyph_layer_collection",
            wraps=document_adapter._replace_glyph_layer_collection,
        ) as replace_layers:
            document_adapter._apply_layer_collection(
                font,
                glyph,
                "A",
                current,
                target,
                excluded_ids=("master-added",),
                allow_master_membership_change=True,
            )

        self.assertEqual(
            [layer.layerId for layer in glyph.layers.values()],
            ["master-condensed", "master-added", "master-regular", "special-layer"],
        )
        replace_layers.assert_not_called()

    def test_master_deletion_uses_the_native_owned_layer_cascade(self) -> None:
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
        assignments_before_delete = {
            glyph.name: glyph.layers.atomic_assignment_count
            for glyph in font.glyphs
        }

        document_adapter._apply_target_model(
            font,
            after,
            before,
            build.change_set.inverse(),
            capabilities=(MASTER_LIFECYCLE_CAPABILITY,),
        )

        self.assertEqual(native_font_to_model(font), before)
        for glyph in font.glyphs:
            self.assertNotIn("master_text", glyph.layers._values)
            self.assertEqual(
                glyph.layers.atomic_assignment_count,
                assignments_before_delete[glyph.name],
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

    def test_overlapping_glyph_and_master_tombstones_compose_by_ownership(self) -> None:
        """A parent lifecycle must not mutate a retained child tombstone.

        A removed glyph owns its detached native payload while a removed
        master owns the corresponding layers of glyphs that remain attached.
        Replaying the two lifecycles in one transaction must preserve both
        pieces of evidence and restore the exact canonical tree.
        """

        font = _master_lifecycle_font()
        added_master = _MasterLifecycleMaster(
            "master_text", "Text", 125, native_only="master-text-secret"
        )
        font.masters.append(added_master)
        for glyph in font.glyphs:
            glyph.layers["master_text"] = _MasterLifecycleLayer(
                "master_text",
                "Text",
                native_only="text-layer-secret-{}".format(glyph.name),
            )
        removed_glyph = _MasterLifecycleGlyph(
            "C",
            [
                _MasterLifecycleLayer(
                    "master_regular",
                    "Regular",
                    native_only="regular-layer-secret-C",
                ),
                _MasterLifecycleLayer(
                    "master_text",
                    "Text",
                    native_only="text-layer-secret-C",
                ),
            ],
        )
        removed_glyph.font = font
        for layer in removed_glyph.layers.values():
            layer._font = font
        font.glyphs.append(removed_glyph)

        expanded = native_font_to_model(font)
        reduced = copy.deepcopy(expanded)
        reduced["masters"] = [
            master
            for master in reduced["masters"]
            if master["id"] != "master_text"
        ]
        del reduced["glyphs"]["C"]
        for glyph in reduced["glyphs"].values():
            glyph["layers"] = [
                layer
                for layer in glyph["layers"]
                if layer["id"] != "master_text"
            ]

        host = object.__new__(GlyphsDocumentHost)
        tombstones = host._capture_removed_native_templates(font, expanded, reduced)
        glyph_tombstone = tombstones[("glyphs", "C")]["native"]
        self.assertIs(glyph_tombstone, removed_glyph)
        self.assertIsNotNone(
            document_adapter._lookup_layer(glyph_tombstone, "master_text")
        )

        removal = diff_models(expanded, reduced)
        document_adapter._apply_target_model(
            font,
            expanded,
            reduced,
            removal,
            capabilities=(MASTER_LIFECYCLE_CAPABILITY,),
        )

        # The glyph was detached before Glyphs cascaded master-layer deletion
        # through the remaining font, so the exact rollback evidence is intact.
        self.assertIsNotNone(
            document_adapter._lookup_layer(glyph_tombstone, "master_text")
        )

        document_adapter._apply_target_model(
            font,
            reduced,
            expanded,
            removal.inverse(),
            capabilities=(MASTER_LIFECYCLE_CAPABILITY,),
            execution_context={
                "nativeReplayTemplates": {
                    path: value["native"] for path, value in tombstones.items()
                },
                "reuseNativeReplayTemplates": True,
            },
        )

        self.assertEqual(native_font_to_model(font), expanded)
        self.assertIs(
            next(glyph for glyph in font.glyphs if glyph.name == "C"),
            removed_glyph,
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
        self.assertEqual(glyph.exact_layer_remove_count, 0)
        self.assertEqual(glyph.exact_layer_set_count, 0)
        self.assertEqual(glyph.layer_array_remove_count, 0)
        self.assertEqual(glyph.layer_array_insert_count, 0)
        self.assertGreater(glyph.layers.atomic_assignment_count, 0)
        self.assertEqual(
            len({layer.layerId for layer in glyph.layers.values()}),
            len(glyph.layers),
        )
        document_adapter._apply_target_model(
            font,
            after,
            before,
            build.change_set.inverse(),
            capabilities=(LAYER_LIFECYCLE_CAPABILITY,),
        )
        self.assertEqual(native_font_to_model(font), before)
        self.assertEqual(glyph.exact_layer_remove_count, 0)
        self.assertEqual(glyph.layer_array_remove_count, 0)
        self.assertGreaterEqual(glyph.layers.atomic_assignment_count, 2)

    def test_live_layer_reorder_uses_one_atomic_identity_preserving_setter(self) -> None:
        font = _master_lifecycle_font()
        glyph = font.glyphs[0]
        original_undo_manager = glyph.undoManager
        source = glyph.layers[0]
        first = source.copy()
        first.layerId = "special-first"
        first.isMasterLayer = False
        second = source.copy()
        second.layerId = "special-second"
        second.isMasterLayer = False
        glyph.layers["special-first"] = first
        glyph.layers["special-second"] = second
        glyph.ghost_layer_reinsertions = True

        document_adapter._replace_glyph_layer_order(
            glyph,
            [source, second, first],
        )

        self.assertIs(glyph.undoManager, original_undo_manager)
        self.assertEqual(glyph.undo_disabled_layer_remove_count, 0)
        self.assertEqual(glyph.exact_layer_remove_count, 0)
        self.assertEqual(glyph.exact_layer_set_count, 0)
        self.assertEqual(glyph.layers.atomic_assignment_count, 1)
        self.assertEqual(glyph._ghost_layers, [])
        self.assertEqual(
            [
                glyph.objectInLayersAtIndex_(index).layerId
                for index in range(glyph.countOfLayers())
            ],
            ["master_regular", "special-second", "special-first"],
        )

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

    def test_master_duplication_does_not_persist_a_redundant_layer_name(self) -> None:
        class NameSensitiveLayer(_MasterLifecycleLayer):
            def __init__(self, master_id, name, *, native_only):
                self.track_name_writes = False
                self.explicit_name_writes = 0
                super().__init__(master_id, name, native_only=native_only)
                self.track_name_writes = True

            def __setattr__(self, name, value):
                if name == "name" and self.__dict__.get("track_name_writes", False):
                    self.explicit_name_writes += 1
                super().__setattr__(name, value)

        font = _master_lifecycle_font()
        source = NameSensitiveLayer(
            "master_regular",
            "Regular",
            native_only="layer-secret-A",
        )
        font.glyphs[0].layers["master_regular"] = source
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

        document_adapter._apply_target_model(
            font,
            before,
            build.change_set.apply(before),
            build.change_set,
            capabilities=build.capabilities,
            execution_context=build.execution_context,
        )

        duplicated = font.glyphs[0].layers["master_text"]
        self.assertEqual(duplicated.name, "Text")
        self.assertEqual(duplicated.explicit_name_writes, 0)

    def test_master_duplication_uses_the_native_template_as_its_write_baseline(self) -> None:
        font = _master_lifecycle_font()
        parameter = SimpleNamespace(
            name="Keep Glyphs Only",
            value=True,
            disabled=False,
        )
        parameter.propertyListValueFormat_error_ = lambda _format, _error: (
            {"name": parameter.name, "value": True},
            None,
        )
        font.masters[0].customParameters = [parameter]
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

        document_adapter._apply_target_model(
            font,
            before,
            build.change_set.apply(before),
            build.change_set,
            capabilities=build.capabilities,
            execution_context=build.execution_context,
        )

        duplicate = next(master for master in font.masters if master.id == "master_text")
        self.assertEqual(len(duplicate.customParameters), 1)
        self.assertEqual(duplicate.customParameters[0].name, "Keep Glyphs Only")

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

    def test_exact_master_restore_uses_its_populated_metadata_as_baseline(self) -> None:
        font = _master_lifecycle_font()
        parameter = SimpleNamespace(
            name="Keep Glyphs Only",
            value=True,
            disabled=False,
        )
        parameter.propertyListValueFormat_error_ = lambda _format, _error: (
            {"name": parameter.name, "value": True},
            None,
        )
        font.masters[0].customParameters = [parameter]
        before = native_font_to_model(font)
        build = build_master_updates(
            before,
            [{
                "action": "duplicate",
                "sourceMasterId": "master_regular",
                "masterId": "master_text",
                "name": "Text",
            }],
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
        tombstones = host._capture_removed_native_templates(font, after, before)
        retained = tombstones[("masters", "master_text")]["native"]["master"]
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
            execution_context={
                "nativeReplayTemplates": {
                    path: value["native"] for path, value in tombstones.items()
                },
                "reuseNativeReplayTemplates": True,
            },
        )

        restored = next(master for master in font.masters if master.id == "master_text")
        self.assertIs(restored, retained)
        self.assertEqual(len(restored.customParameters), 1)
        self.assertEqual(restored.customParameters[0].name, "Keep Glyphs Only")

        # Detached revert simulation receives the verifier-safe copies from
        # the same path-keyed evidence store. They also already embody the
        # canonical target and must not be replayed as empty entities.
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
            execution_context={
                "nativeReplayTemplates": {
                    path: value["copy"] for path, value in tombstones.items()
                }
            },
        )
        simulated = next(master for master in font.masters if master.id == "master_text")
        self.assertEqual(len(simulated.customParameters), 1)
        self.assertEqual(simulated.customParameters[0].name, "Keep Glyphs Only")

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
                    "index": 0,
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

        unrelated_order = next(
            change
            for change in build.change_set.changes
            if change.path[-1] == "$order"
        )
        unrelated_order = type(unrelated_order)(
            path=unrelated_order.path,
            before=unrelated_order.before,
            after=list(reversed(unrelated_order.after)),
            before_present=unrelated_order.before_present,
            after_present=unrelated_order.after_present,
        )
        unsupported = ChangeSet.from_changes(
            before_fingerprint=build.change_set.before_fingerprint,
            after_fingerprint=build.change_set.after_fingerprint,
            changes=[
                change
                if change.path != unrelated_order.path
                else unrelated_order
                for change in build.change_set.changes
            ],
        )
        self.assertFalse(
            host.supports_change_set(
                unsupported,
                capabilities=(MASTER_LIFECYCLE_CAPABILITY,),
            )
        )
        self.assertEqual(
            unsupported_change_diagnostics(
                unsupported,
                capabilities=(MASTER_LIFECYCLE_CAPABILITY,),
            )["unsupportedPaths"],
            [["glyphs", "A", "layers", "$order"]],
        )

    def test_save_reset_releases_only_that_documents_master_tombstones(self) -> None:
        host = object.__new__(GlyphsDocumentHost)
        # Runtime-owned save cleanup is serialized through the adapter's native
        # executor; keep this deliberately minimal fixture faithful to that
        # production invariant.
        host._executor = _Immediate()
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

    def test_sparse_glyph_create_preserves_host_defaults_for_absent_fields(self) -> None:
        class NativeGlyph:
            def __init__(self):
                self.name = ""
                self.id = ""
                self.category = None
                self.subCategory = None
                self.unicode = None
                self.export = True
                self.leftKerningGroup = None
                self.rightKerningGroup = None
                self.mastersCompatible = True
                self.layers = []
                self._direction = 0
                self._case = 0

            @property
            def direction(self):
                return self._direction

            @direction.setter
            def direction(self, value):
                if value is None:
                    raise TypeError("unsigned char cannot receive None")
                self._direction = int(value)

            @property
            def case(self):
                return self._case

            @case.setter
            def case(self, value):
                if value is None:
                    raise TypeError("unsigned char cannot receive None")
                self._case = int(value)

        font = _TransactionalFont()
        before = native_font_to_model(font)
        after = copy.deepcopy(before)
        after["glyphs"]["B"] = {
            "id": "glyph_B",
            "name": "B",
            "category": None,
            "subCategory": None,
            "unicode": None,
            "export": True,
            "leftKerningGroup": None,
            "rightKerningGroup": None,
            "layers": [],
        }

        created = NativeGlyph()
        with mock.patch.object(
            document_adapter, "_construct_native_entity", return_value=created
        ):
            document_adapter._apply_target_model(
                font, before, after, diff_models(before, after)
            )

        self.assertEqual(created.name, "B")
        self.assertEqual(created.direction, 0)
        self.assertEqual(created.case, 0)

    def test_native_template_only_glyph_field_is_not_assigned_directly(self) -> None:
        class NativeGlyph:
            def __init__(self):
                self.name = "A"
                self.layers = []

            @property
            def partsSettings(self):
                return None

        glyph = NativeGlyph()
        font = SimpleNamespace(glyphs=[glyph])
        before = {
            "glyphs": {
                "A": {
                    "id": "glyph_A",
                    "name": "A",
                    "partsSettings": None,
                    "layers": [],
                }
            }
        }
        after = copy.deepcopy(before)
        after["glyphs"]["A"]["partsSettings"] = []

        # Glyphs 4 exposes no GSGlyph.partsSettings setter. The official
        # serialized field is preserved by a structural native template and
        # verified through recapture; it must never be assigned as a scalar.
        document_adapter._apply_target_model(
            font, before, after, diff_models(before, after)
        )

        self.assertIsNone(glyph.partsSettings)
        self.assertEqual(
            document_adapter._glyph_native_template_field_value(
                glyph, "partsSettings"
            ),
            [],
        )

    def test_glyph_override_presence_round_trips_without_writing_none_to_enums(self) -> None:
        class NativeGlyph:
            def __init__(self):
                self.name = "A"
                self.id = "native-A"
                self.layers = []
                self.mastersCompatible = True
                self._case = 1
                self._direction = 0
                self.storeCase = False
                self.storeDirection = False

            @property
            def case(self):
                return self._case

            @case.setter
            def case(self, value):
                if value is None:
                    raise TypeError("unsigned char cannot receive None")
                self._case = int(value)

            @property
            def direction(self):
                return self._direction

            @direction.setter
            def direction(self, value):
                if value is None:
                    raise TypeError("unsigned char cannot receive None")
                self._direction = int(value)

        glyph = NativeGlyph()
        inherited = document_adapter._glyph_model(glyph)
        self.assertIsNone(inherited["case"])
        self.assertIsNone(inherited["direction"])

        explicit = copy.deepcopy(inherited)
        explicit["case"] = 2
        explicit["direction"] = 2
        document_adapter._apply_glyph_scalar_updates(
            glyph,
            inherited,
            explicit,
            whole_glyph=True,
            changed_fields=set(),
        )
        self.assertTrue(glyph.storeCase)
        self.assertTrue(glyph.storeDirection)
        self.assertEqual(document_adapter._glyph_model(glyph)["case"], 2)
        self.assertEqual(document_adapter._glyph_model(glyph)["direction"], 2)

        document_adapter._apply_glyph_scalar_updates(
            glyph,
            explicit,
            inherited,
            whole_glyph=True,
            changed_fields=set(),
        )
        self.assertFalse(glyph.storeCase)
        self.assertFalse(glyph.storeDirection)
        self.assertIsNone(document_adapter._glyph_model(glyph)["case"])
        self.assertIsNone(document_adapter._glyph_model(glyph)["direction"])

    def test_shared_sort_name_presence_is_decided_from_complete_target(self) -> None:
        glyph = SimpleNamespace(
            sortName="alpha",
            sortNameKeep="alpha.keep",
            storeSortName=True,
        )
        current = {"sortName": "alpha", "sortNameKeep": "alpha.keep"}
        target = {"sortName": "beta", "sortNameKeep": None}

        document_adapter._apply_glyph_scalar_updates(
            glyph,
            current,
            target,
            whole_glyph=True,
            changed_fields=set(),
        )

        self.assertTrue(glyph.storeSortName)
        self.assertEqual(glyph.sortName, "beta")
        self.assertIsNone(glyph.sortNameKeep)

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

    def test_live_snapshot_reuses_the_complete_tree_only_with_stable_document_revision_evidence(self) -> None:
        font = _TransactionalFont()
        revision = {"value": 7}
        font.parent.changeCount = lambda: revision["value"]
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id

        first = host.capture_snapshot(document_id)
        with mock.patch.object(
            document_adapter,
            "_font_model_with_glyphs",
            side_effect=AssertionError("unchanged document roots were rebuilt"),
        ):
            second = host.capture_snapshot(document_id)

        self.assertIs(second, first)

        revision["value"] += 1
        with mock.patch.object(
            document_adapter,
            "_native_root_evidence",
            wraps=document_adapter._native_root_evidence,
        ) as capture_evidence:
            third = host.capture_snapshot(document_id)

        self.assertEqual(capture_evidence.call_count, 1)
        self.assertEqual(third.document_fingerprint, first.document_fingerprint)

    def test_glyphs_notification_generation_reuses_and_invalidates_snapshot(self) -> None:
        class Evidence:
            def __init__(self):
                self.value = 0

            def current(self):
                return self.value

        font = _TransactionalFont()
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        evidence = Evidence()
        host._glyphs_change_generation = evidence
        document_id = host.list_documents()[0].document_id

        first = host.capture_snapshot(document_id)
        with mock.patch.object(
            document_adapter,
            "_font_model_with_glyphs",
            side_effect=AssertionError("unchanged notified roots were rebuilt"),
        ):
            second = host.capture_snapshot(document_id)
        self.assertIs(second, first)

        evidence.value += 1
        with mock.patch.object(
            document_adapter,
            "_native_root_evidence",
            wraps=document_adapter._native_root_evidence,
        ) as capture_evidence:
            third = host.capture_snapshot(document_id)
        self.assertEqual(capture_evidence.call_count, 1)
        self.assertEqual(third.document_fingerprint, first.document_fingerprint)

    def test_document_revision_ignores_ephemeral_pyobjc_proxy_identity(self) -> None:
        class NativeDocumentProxy:
            def changeCount(self):
                return None

            def isDocumentEdited(self):
                return False

        class FontWithEphemeralParentProxy:
            @property
            def parent(self):
                return NativeDocumentProxy()

        font = FontWithEphemeralParentProxy()

        first = document_adapter._document_revision_token(
            font, notification_generation=12
        )
        second = document_adapter._document_revision_token(
            font, notification_generation=12
        )

        self.assertEqual(
            first,
            ("glyphs_update_interface", 12, False),
        )
        self.assertEqual(second, first)

    def test_glyphs_change_listener_only_advances_passive_generation(self) -> None:
        class App:
            def __init__(self):
                self.callbacks = []
                self.removed = []

            def addCallback(self, callback, event):
                self.callbacks.append((callback, event))

            def removeCallback(self, callback, event=None):
                self.removed.append((callback, event))

        app = App()
        glyphs_module = SimpleNamespace(
            Glyphs=app,
            UPDATEINTERFACE="update",
            DOCUMENTOPENED="opened",
            DOCUMENTCLOSED="closed",
            DOCUMENTWASSAVED="saved",
        )
        with mock.patch.dict(sys.modules, {"GlyphsApp": glyphs_module}):
            listener = document_adapter._GlyphsChangeGeneration.install(app)

        self.assertIsNotNone(listener)
        self.assertEqual(listener.current(), 0)
        callback = next(
            callback for callback, event in app.callbacks if event == "update"
        )
        callback(None)
        self.assertEqual(listener.current(), 1)
        listener.close()
        self.assertEqual({event for _callback, event in app.removed}, {
            "update", "opened", "closed", "saved",
        })

    def test_mcp_impact_bypasses_unchanged_document_revision_shortcut(self) -> None:
        font = _TransactionalFont()
        font.parent.changeCount = lambda: 7
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        before = host.capture_snapshot(document_id)
        target = before.materialize()
        target["font"]["note"] = "planned"
        changes = diff_models(before, target)
        host._canonical_model_cache.invalidate_impact(
            document_id,
            document_adapter.CanonicalImpact.from_change_set(before, changes),
        )

        with mock.patch.object(
            document_adapter,
            "_native_canonical_root",
            wraps=document_adapter._native_canonical_root,
        ) as capture_root:
            host.capture_snapshot(document_id)

        capture_root.assert_any_call(font, "font", instance_ids=[])

    def test_master_only_readback_proves_broad_glyph_marker_without_full_capture(self) -> None:
        font = _TransactionalFont()
        master = SimpleNamespace(
            id="master-regular", name="Regular", italicAngle=0, axes=[]
        )
        layer = _MetricsLayer()
        layer.name = "Regular"
        layer.isMasterLayer = True
        layer.isSpecialLayer = False
        layer.lastUpdate = lambda: 1.0
        glyph = SimpleNamespace(
            name="A",
            id="native-A",
            lastChange="revision-1",
            changeCount=lambda: 0,
            mastersCompatible=True,
            layers=[layer],
            category="Letter",
            subCategory="Uppercase",
            unicode=None,
            export=True,
            leftKerningGroup=None,
            rightKerningGroup=None,
        )
        font.masters = [master]
        font.glyphs = [glyph]
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        before = host.capture_snapshot(document_id)
        target = before.materialize()
        target["masters"][0]["italicAngle"] = 12
        changes = diff_models(before, target)
        expected = before.store_verified_transition(target, changes)
        host._canonical_model_cache.invalidate_impact(
            document_id,
            document_adapter.CanonicalImpact.from_change_set(before, changes),
        )
        master.italicAngle = 12
        glyph.lastChange = "broad-master-notification"

        with mock.patch.object(
            document_adapter,
            "_glyph_model",
            wraps=document_adapter._glyph_model,
        ) as full_glyph:
            actual = host._executor.run(
                lambda: host._capture_cached_snapshot(
                    document_id, font, expected=expected
                )
            )
            glyph.lastChange = "late-master-notification"
            recaptured = host.capture_snapshot(document_id)

        self.assertEqual(actual.document_fingerprint, expected.document_fingerprint)
        self.assertEqual(
            recaptured.document_fingerprint, expected.document_fingerprint
        )
        self.assertEqual(full_glyph.call_count, 0)
        self.assertIs(actual.glyph_shards["A"], before.glyph_shards["A"])

    def test_layer_revision_token_never_traverses_geometry(self) -> None:
        layer = _MetricsLayer()
        layer.name = "Regular"
        layer.isMasterLayer = True
        layer.isSpecialLayer = False
        layer.lastUpdate = lambda: 1.0

        with mock.patch.object(
            document_adapter,
            "_layer_paths",
            side_effect=AssertionError("revision token traversed paths"),
        ), mock.patch.object(
            document_adapter,
            "_layer_components",
            side_effect=AssertionError("revision token traversed components"),
        ), mock.patch.object(
            document_adapter,
            "_anchor_model",
            side_effect=AssertionError("revision token traversed anchors"),
        ):
            before = document_adapter._layer_revision_token(layer)
            layer.lastUpdate = lambda: 2.0
            after = document_adapter._layer_revision_token(layer)

        self.assertNotEqual(before, after)

    def test_detached_unexpected_revision_requires_layer_proof(self) -> None:
        font = _TransactionalFont()
        master = SimpleNamespace(
            id="master-regular", name="Regular", italicAngle=0, axes=[]
        )
        layer = _MetricsLayer()
        layer.name = "Regular"
        layer.isMasterLayer = True
        layer.isSpecialLayer = False
        layer.lastUpdate = lambda: 1.0
        glyph = SimpleNamespace(
            name="A",
            id="native-A",
            lastChange="revision-1",
            changeCount=lambda: 0,
            mastersCompatible=True,
            layers=[layer],
            category="Letter",
            subCategory="Uppercase",
            unicode=None,
            export=True,
            leftKerningGroup=None,
            rightKerningGroup=None,
        )
        font.masters = [master]
        font.glyphs = [glyph]
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        before = host.capture_snapshot(document_id)
        target = before.materialize()
        target["masters"][0]["italicAngle"] = 12
        changes = diff_models(before, target)
        impact = document_adapter.CanonicalImpact.from_change_set(before, changes)
        glyph.lastChange = "broad-master-notification"

        self.assertEqual(
            document_adapter._unproved_revision_glyphs(
                font, before, target, impact, ("A",)
            ),
            (),
        )
        layer.width = 777
        self.assertEqual(
            document_adapter._unproved_revision_glyphs(
                font, before, target, impact, ("A",)
            ),
            ("A",),
        )

    def test_revision_proof_ignores_master_order_but_preserves_special_order(self) -> None:
        def layer(identity, *, master):
            value = _MetricsLayer()
            value.layerId = identity
            value.associatedMasterId = identity if master else "master-a"
            value.name = identity
            value.isMasterLayer = master
            value.isSpecialLayer = not master
            value.lastUpdate = lambda: 1.0
            return value

        master_a = layer("master-a", master=True)
        special_a = layer("special-a", master=False)
        master_b = layer("master-b", master=True)
        special_b = layer("special-b", master=False)
        glyph = SimpleNamespace(
            name="A",
            id="native-A",
            mastersCompatible=True,
            layers=[master_a, special_a, master_b, special_b],
            category="Letter",
            subCategory="Uppercase",
            unicode=None,
            export=True,
            leftKerningGroup=None,
            rightKerningGroup=None,
        )
        expected = document_adapter._glyph_model(glyph)
        before_tokens = document_adapter._layer_revision_index(glyph)

        glyph.layers = [master_b, special_a, master_a, special_b]
        self.assertTrue(
            document_adapter._verified_glyph_fragment_matches(
                glyph,
                expected,
                expected,
                (),
                before_layer_tokens=before_tokens,
                current_layer_tokens=document_adapter._layer_revision_index(glyph),
            )
        )
        glyph.layers = [master_b, special_b, master_a, special_a]
        self.assertFalse(
            document_adapter._verified_glyph_fragment_matches(
                glyph,
                expected,
                expected,
                (),
                before_layer_tokens=before_tokens,
                current_layer_tokens=document_adapter._layer_revision_index(glyph),
            )
        )

    def test_fragment_verification_uses_source_neutral_root_evidence(self) -> None:
        glyph = SimpleNamespace(
            name="A",
            id="native-A",
            mastersCompatible=True,
            layers=[],
            category="Letter",
            subCategory="Uppercase",
            unicode="0041",
            export=True,
            leftKerningGroup=None,
            rightKerningGroup=None,
        )
        expected = document_adapter._glyph_model(glyph)
        # The serialized source owns saved semantics and may omit a projected
        # native default. That pre-existing source/native representation gap
        # must not invalidate an unrelated verified edit.
        expected["category"] = None
        modeled = copy.deepcopy(expected)
        modeled["export"] = False
        glyph.export = False
        before_root = document_adapter._glyph_root_revision_evidence(glyph)
        before_root["export"] = True

        self.assertTrue(
            document_adapter._verified_glyph_fragment_matches(
                glyph,
                modeled,
                modeled,
                (("glyphs", "A", "export"),),
                before_root_evidence=before_root,
                current_root_evidence=document_adapter._glyph_root_revision_evidence(glyph),
                before_layer_tokens={},
                current_layer_tokens={},
            )
        )

        glyph.category = "Mark"
        self.assertFalse(
            document_adapter._verified_glyph_fragment_matches(
                glyph,
                modeled,
                modeled,
                (("glyphs", "A", "export"),),
                before_root_evidence=before_root,
                current_root_evidence=document_adapter._glyph_root_revision_evidence(glyph),
                before_layer_tokens={},
                current_layer_tokens={},
            )
        )

    def test_root_verification_compares_native_delta_not_source_spelling(self) -> None:
        before_evidence = [
            {
                "id": "master-a",
                "name": "A",
                "italicAngle": 0,
                "customParameters": [{"name": "legacy", "value": 1}],
            },
            {
                "id": "master-b",
                "name": "B",
                "italicAngle": 0,
                "customParameters": [{"name": "legacy", "value": 2}],
            },
        ]
        current_evidence = [before_evidence[1], before_evidence[0]]
        expected = [
            {
                "id": "master-b",
                "name": "B",
                "italicAngle": 0,
                "customParameters": [],
            },
            {
                "id": "master-a",
                "name": "A",
                "italicAngle": 0,
                "customParameters": [],
            },
        ]

        verified, unexpected = (
            document_adapter._verified_root_evidence_transition(
                "masters",
                before_evidence,
                current_evidence,
                expected,
                (("$order",),),
            )
        )
        self.assertTrue(verified)
        self.assertEqual(unexpected, ())

        converged = copy.deepcopy(current_evidence)
        converged[0]["italicAngle"] = 12
        converged_expected = copy.deepcopy(expected)
        converged_expected[0]["italicAngle"] = 12
        verified, unexpected = (
            document_adapter._verified_root_evidence_transition(
                "masters",
                before_evidence,
                converged,
                converged_expected,
                (("$order",),),
            )
        )
        self.assertTrue(verified)
        self.assertEqual(unexpected, ())

        changed = copy.deepcopy(current_evidence)
        changed[0]["name"] = "Unexpected"
        verified, unexpected = (
            document_adapter._verified_root_evidence_transition(
                "masters",
                before_evidence,
                changed,
                expected,
                (("$order",),),
            )
        )
        self.assertFalse(verified)
        self.assertIn(("master-b", "name"), unexpected)

    def test_scoped_root_verification_accepts_exact_record_level_fallback(self) -> None:
        source_model = {
            "masters": [
                {"id": "master-a", "name": "A"},
                {"id": "master-b", "name": "B"},
            ],
            "glyphs": {},
            "glyphOrder": [],
        }
        source = document_adapter.CanonicalSnapshot.from_model(
            source_model,
            native_revision_evidence={"capture": "saved_format_v4_mapping"},
        )
        expected_model = copy.deepcopy(source_model)
        expected_model["masters"] = list(reversed(expected_model["masters"]))
        expected = document_adapter.CanonicalSnapshot.from_model(
            expected_model,
            native_revision_evidence={"capture": "saved_format_v4_mapping"},
        )
        impact = document_adapter.CanonicalImpact.from_paths(
            source, [("masters", "$order")]
        )
        font = SimpleNamespace(glyphs=[], axes=[], masters=[])

        with mock.patch.object(
            document_adapter,
            "_native_root_evidence_value",
            return_value=[{"id": "master-b", "metricValues": [{"pos": 0}]}],
        ), mock.patch.object(
            document_adapter,
            "_persistent_canonical_record_root",
            return_value=expected["masters"],
        ) as record_fallback:
            captured = document_adapter._scoped_font_model(
                font,
                source,
                MutationScope(impact.roots, impact.glyph_names),
                impact=impact,
                expected_model=expected,
                before_root_evidence={
                    "masters": [
                        {"id": "master-a", "metricValues": [{"pos": 0}]},
                        {"id": "master-b", "metricValues": [{"pos": 1}]},
                    ]
                },
            )

        self.assertEqual(captured["masters"], expected["masters"])
        record_fallback.assert_called_once_with(font, "masters", expected)

    def test_scoped_root_verification_rejects_divergent_record_level_fallback(self) -> None:
        source_model = {
            "masters": [
                {"id": "master-a", "name": "A"},
                {"id": "master-b", "name": "B"},
            ],
            "glyphs": {},
            "glyphOrder": [],
        }
        source = document_adapter.CanonicalSnapshot.from_model(
            source_model,
            native_revision_evidence={"capture": "saved_format_v4_mapping"},
        )
        expected_model = copy.deepcopy(source_model)
        expected_model["masters"] = list(reversed(expected_model["masters"]))
        expected = document_adapter.CanonicalSnapshot.from_model(
            expected_model,
            native_revision_evidence={"capture": "saved_format_v4_mapping"},
        )
        impact = document_adapter.CanonicalImpact.from_paths(
            source, [("masters", "$order")]
        )
        font = SimpleNamespace(glyphs=[], axes=[], masters=[])

        with mock.patch.object(
            document_adapter,
            "_native_root_evidence_value",
            return_value=[{"id": "master-b", "metricValues": [{"pos": 0}]}],
        ), mock.patch.object(
            document_adapter,
            "_persistent_canonical_record_root",
            return_value=[{"id": "master-b", "name": "Wrong"}],
        ):
            with self.assertRaisesRegex(
                document_adapter.HostAccessError,
                "escaped the predicted canonical impact",
            ):
                document_adapter._scoped_font_model(
                    font,
                    source,
                    MutationScope(impact.roots, impact.glyph_names),
                    impact=impact,
                    expected_model=expected,
                    before_root_evidence={
                        "masters": [
                            {"id": "master-a", "metricValues": [{"pos": 0}]},
                            {"id": "master-b", "metricValues": [{"pos": 1}]},
                        ]
                    },
                )

    def test_scoped_root_discovery_records_authoritative_derived_effects(self) -> None:
        source_model = {
            "masters": [
                {
                    "id": "master-a",
                    "name": "A",
                    "metricValues": [{"id": "metric-a", "pos": 1}],
                },
                {
                    "id": "master-b",
                    "name": "B",
                    "metricValues": [{"id": "metric-a", "pos": 1}],
                },
            ],
            "glyphs": {},
            "glyphOrder": [],
        }
        source = document_adapter.CanonicalSnapshot.from_model(
            source_model,
            native_revision_evidence={"capture": "saved_format_v4_mapping"},
        )
        requested_model = copy.deepcopy(source_model)
        requested_model["masters"] = list(reversed(requested_model["masters"]))
        requested = document_adapter.CanonicalSnapshot.from_model(
            requested_model,
            native_revision_evidence={"capture": "saved_format_v4_mapping"},
        )
        observed_root = copy.deepcopy(requested_model["masters"])
        observed_root[0]["metricValues"][0]["pos"] = 0
        impact = document_adapter.CanonicalImpact.from_paths(
            source, [("masters", "$order")]
        )
        font = SimpleNamespace(glyphs=[], axes=[], masters=[])

        with mock.patch.object(
            document_adapter,
            "_native_root_evidence_value",
            return_value=[{"id": "master-b", "metricValues": [{"pos": 0}]}],
        ), mock.patch.object(
            document_adapter,
            "_persistent_canonical_record_root",
            return_value=observed_root,
        ):
            captured = document_adapter._scoped_font_model(
                font,
                source,
                MutationScope(impact.roots, impact.glyph_names),
                impact=impact,
                expected_model=requested,
                before_root_evidence={
                    "masters": [
                        {"id": "master-a", "metricValues": [{"pos": 1}]},
                        {"id": "master-b", "metricValues": [{"pos": 1}]},
                    ]
                },
                allow_observed_root_expansion=True,
            )

        self.assertEqual(captured["masters"], observed_root)

    def test_expected_capture_normalizes_only_root_owned_master_layer_order(self) -> None:
        def layer(identity, *, master):
            value = _MetricsLayer()
            value.layerId = identity
            value.associatedMasterId = identity if master else "master-a"
            value.name = identity
            value.isMasterLayer = master
            value.isSpecialLayer = not master
            value.lastUpdate = lambda: 1.0
            return value

        master_a = layer("master-a", master=True)
        master_b = layer("master-b", master=True)
        special_a = layer("special-a", master=False)
        special_b = layer("special-b", master=False)
        glyph = SimpleNamespace(
            name="A",
            id="native-A",
            mastersCompatible=True,
            layers=[master_a, master_b, special_a, special_b],
            category="Letter",
            subCategory="Uppercase",
            unicode=None,
            export=True,
            leftKerningGroup=None,
            rightKerningGroup=None,
        )
        reference = document_adapter._glyph_model(glyph)

        # Glyphs projects the master prefix from the root master order. That
        # host presentation must not rewrite the canonical nested collection;
        # the native non-master order remains independently authoritative.
        glyph.layers = [master_b, master_a, special_b, special_a]
        captured = document_adapter._glyph_model(
            glyph,
            layer_order_reference=reference,
        )

        self.assertEqual(
            [layer["id"] for layer in captured["layers"]],
            ["master-a", "master-b", "special-b", "special-a"],
        )

    def test_expected_capture_places_new_master_without_reordering_retained_layers(self) -> None:
        def layer(identity):
            value = _MetricsLayer()
            value.layerId = identity
            value.associatedMasterId = identity
            value.name = identity
            value.isMasterLayer = True
            value.isSpecialLayer = False
            value.lastUpdate = lambda: 1.0
            return value

        master_a = layer("master-a")
        master_b = layer("master-b")
        master_new = layer("master-new")
        glyph = SimpleNamespace(
            name="A",
            id="native-A",
            mastersCompatible=True,
            layers=[master_a, master_b],
            category="Letter",
            subCategory="Uppercase",
            unicode=None,
            export=True,
            leftKerningGroup=None,
            rightKerningGroup=None,
        )
        reference = document_adapter._glyph_model(glyph)

        # The root projection moved B ahead of A and inserted the new master
        # between them. Canonically, retained A/B order stays stable while the
        # new identity is inserted at its root-owned position.
        glyph.layers = [master_b, master_new, master_a]
        captured = document_adapter._glyph_model(
            glyph,
            layer_order_reference=reference,
        )

        self.assertEqual(
            [layer["id"] for layer in captured["layers"]],
            ["master-a", "master-new", "master-b"],
        )

    def test_master_move_then_delete_keeps_one_canonical_order_owner(self) -> None:
        font = _TransactionalFont()

        def master(identity):
            return SimpleNamespace(
                id=identity,
                name=identity,
                italicAngle=0,
                axes=[],
            )

        def layer(identity):
            value = _MetricsLayer()
            value.layerId = identity
            value.associatedMasterId = identity
            value.name = identity
            value.isMasterLayer = True
            value.isSpecialLayer = False
            value.lastUpdate = lambda: 1.0
            return value

        master_a = master("master-a")
        master_b = master("master-b")
        layer_a = layer("master-a")
        layer_b = layer("master-b")
        glyph = SimpleNamespace(
            name="A",
            id="native-A",
            lastChange="revision-1",
            changeCount=lambda: 0,
            mastersCompatible=True,
            layers=[layer_a, layer_b],
            category="Letter",
            subCategory="Uppercase",
            unicode=None,
            export=True,
            leftKerningGroup=None,
            rightKerningGroup=None,
        )
        font.masters = [master_a, master_b]
        font.glyphs = [glyph]
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        before = host.capture_snapshot(document_id)

        moved_model = before.materialize()
        moved_model["masters"].reverse()
        move = diff_models(before, moved_model)
        moved_expected = before.store_verified_transition(moved_model, move)
        host._canonical_model_cache.invalidate_impact(
            document_id,
            document_adapter.CanonicalImpact.from_change_set(before, move),
        )
        font.masters = [master_b, master_a]
        glyph.layers = [layer_b, layer_a]
        glyph.lastChange = "revision-2"
        moved = host._executor.run(
            lambda: host._capture_cached_snapshot(
                document_id,
                font,
                expected=moved_expected,
            )
        )
        self.assertEqual(moved.document_fingerprint, moved_expected.document_fingerprint)
        self.assertEqual(
            [item["id"] for item in moved["glyphs"]["A"]["layers"]],
            ["master-a", "master-b"],
        )

        deletion = build_master_updates(
            moved,
            [{"action": "delete", "masterId": "master-a"}],
        )
        deleted_model = deletion.change_set.apply(moved)
        deleted_expected = moved.store_verified_transition(
            deleted_model,
            deletion.change_set,
        )
        host._canonical_model_cache.invalidate_impact(
            document_id,
            document_adapter.CanonicalImpact.from_change_set(
                moved,
                deletion.change_set,
            ),
        )
        font.masters = [master_b]
        glyph.layers = [layer_b]
        glyph.lastChange = "revision-3"
        deleted = host._executor.run(
            lambda: host._capture_cached_snapshot(
                document_id,
                font,
                expected=deleted_expected,
            )
        )

        self.assertEqual(
            deleted.document_fingerprint,
            deleted_expected.document_fingerprint,
        )
        self.assertEqual(
            [item["id"] for item in deleted["glyphs"]["A"]["layers"]],
            ["master-b"],
        )

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

    def test_detached_simulation_reconciles_clone_omissions_generically(self) -> None:
        font = _TransactionalFont()
        font.note = "Saved canonical note"
        glyph = SimpleNamespace(
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
        font.glyphs = [glyph]

        def copy_with_native_omission():
            clone = copy.deepcopy(font)
            clone.note = None
            return clone

        font.copy = copy_with_native_omission
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        before = host.capture_model(document_id)
        target = copy.deepcopy(before)
        target["glyphs"]["A"]["export"] = False
        changes = diff_models(before, target)

        simulated = host.simulate_change_set(document_id, changes)

        self.assertEqual(simulated, target)
        self.assertEqual(font.note, "Saved canonical note")
        self.assertTrue(glyph.export)

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
        ) as full_capture, mock.patch.object(
            host._canonical_model_cache,
            "invalidate_unscoped",
            wraps=host._canonical_model_cache.invalidate_unscoped,
        ) as invalidate_unscoped:
            result = host.run_live_python(request)

        self.assertIn("Transaction Test", result["stdout"])
        self.assertEqual(full_capture.call_count, 0)
        self.assertEqual(invalidate_unscoped.call_count, 1)

    def test_live_python_runtime_guard_blocks_dynamic_working_source_saves(self) -> None:
        class SaveCapableDocument(_EditableDocument):
            def __init__(self):
                super().__init__(edited=True)
                self.save_calls = []

            def saveDocument_(self, sender):
                self.save_calls.append(("saveDocument_", sender))

            def saveToURL_ofType_forSaveOperation_error_(
                self, url, type_name, operation, error
            ):
                self.save_calls.append(
                    ("saveToURL", url, type_name, operation, error)
                )
                return True, None

            def performSelector_(self, selector):
                name = str(selector).replace(":", "_")
                return getattr(self, name)(None)

            def methodForSelector_(self, selector):
                name = str(selector).replace(":", "_")
                return getattr(self, name)

        class SaveCapableFont(_TransactionalFont):
            def __init__(self):
                super().__init__(edited=True)
                self.parent = SaveCapableDocument()
                self.font_save_calls = []

            def save(self, *args, **kwargs):
                self.font_save_calls.append((args, kwargs))

        cases = (
            (
                "dynamic getattr",
                "name = ''.join(['save', 'Document_']); "
                "getattr(font.parent, name)(None)",
            ),
            (
                "unbound reflection",
                "name = ''.join(['save', 'Document_']); "
                "vars(type(font.parent))[name](font.parent, None)",
            ),
            (
                "perform selector",
                "bridge = getattr(font.parent, "
                "''.join(['perform', 'Selector_'])); "
                "bridge(''.join(['save', 'Document:']))",
            ),
            (
                "method for selector",
                "resolver = getattr(font.parent, "
                "''.join(['methodFor', 'Selector_'])); "
                "method = resolver(''.join(['save', 'Document:'])); "
                "method(None)",
            ),
            (
                "dynamic GSFont convenience",
                "getattr(font, ''.join(['sa', 've']))()",
            ),
            (
                "caught and retried",
                "method = getattr(font.parent, "
                "''.join(['save', 'Document_']))\n"
                "for attempt in range(2):\n"
                "    try:\n"
                "        method(None)\n"
                "    except BaseException:\n"
                "        pass\n",
            ),
        )
        for label, code in cases:
            with self.subTest(label=label):
                font = SaveCapableFont()
                host = GlyphsDocumentHost(_App(font), executor=_Immediate())
                document_id = host.list_documents()[0].document_id
                request = PythonExecutionRequest(
                    code=code,
                    reason="adversarial runtime source-save check",
                    intended_effect="files_or_external",
                    execution_mode="live_open_world",
                    document_id=document_id,
                )

                with self.assertRaises(ObservedLivePythonError) as blocked:
                    host.run_live_python(request)

                self.assertIsInstance(
                    blocked.exception.cause, SourceSaveForbiddenError
                )
                self.assertEqual(font.parent.save_calls, [])
                self.assertEqual(font.font_save_calls, [])

    def test_live_python_runtime_guard_preserves_unrelated_save_methods(self) -> None:
        font = _TransactionalFont()
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        request = PythonExecutionRequest(
            code=(
                "class ExternalArtifact:\n"
                "    def __init__(self):\n"
                "        self.saved = False\n"
                "    def save(self):\n"
                "        self.saved = True\n"
                "artifact = ExternalArtifact()\n"
                "artifact.save()\n"
                "print(artifact.saved)\n"
            ),
            reason="preserve unrelated open-world save methods",
            intended_effect="files_or_external",
            execution_mode="live_open_world",
            document_id=document_id,
        )

        result = host.run_live_python(request)

        self.assertEqual(result["stdout"].strip(), "True")

    def test_live_python_runtime_guard_allows_detached_font_save(self) -> None:
        saved = []

        class CopyableFont(_TransactionalFont):
            def copy(self):
                return CopyableFont()

            def save(self, destination):
                saved.append((self, destination))

        font = CopyableFont()
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        request = PythonExecutionRequest(
            code=(
                "detached = font.copy()\n"
                "detached.save('/tmp/Detached.glyphs')\n"
            ),
            reason="preserve detached external save semantics",
            intended_effect="files_or_external",
            execution_mode="live_open_world",
            document_id=document_id,
        )

        host.run_live_python(request)

        self.assertEqual(len(saved), 1)
        self.assertIsNot(saved[0][0], font)

    @unittest.skipUnless(
        _PYOBJC_RUNTIME is not None and _NSDOCUMENT_RUNTIME is not None,
        "PyObjC host boundary",
    )
    def test_runtime_guard_interposes_and_restores_objective_c_selector(self) -> None:
        objc = _PYOBJC_RUNTIME
        NSDocument = _NSDOCUMENT_RUNTIME
        assert objc is not None and NSDocument is not None
        document = NSDocument.alloc().init()
        original_selector = NSDocument.writeToURL_ofType_
        self.assertIsInstance(original_selector, objc.native_selector)
        original_descriptor = vars(NSDocument)["writeToURL_ofType_"]
        self.assertIsInstance(original_descriptor, objc.native_selector)
        runtime = document_adapter._objective_c_runtime()
        before = runtime.capture(
            NSDocument,
            "writeToURL_ofType_",
            original_selector.selector,
            class_method=False,
            require_owned=True,
        )
        self.assertIsNotNone(before)
        guard = document_adapter._WorkingSourceSaveRuntimeGuard(
            [document],
            native_identity=lambda value: ("python", id(value)),
        )

        with self.assertRaisesRegex(ValueError, "script failed"):
            with guard:
                during = runtime.capture(
                    NSDocument,
                    "writeToURL_ofType_",
                    original_selector.selector,
                    class_method=False,
                    require_owned=True,
                )
                self.assertIsNotNone(during)
                self.assertEqual(during.class_pointer, before.class_pointer)
                self.assertEqual(during.method_pointer, before.method_pointer)
                self.assertEqual(during.type_encoding, before.type_encoding)
                self.assertNotEqual(
                    during.implementation_pointer,
                    before.implementation_pointer,
                )
                self.assertIs(
                    vars(NSDocument)["writeToURL_ofType_"], original_descriptor
                )
                with self.assertRaises(SourceSaveForbiddenError):
                    getattr(document, "".join(["writeTo", "URL_ofType_"]))(
                        None, None
                    )
                raise ValueError("script failed")

        after = runtime.capture(
            NSDocument,
            "writeToURL_ofType_",
            original_selector.selector,
            class_method=False,
            require_owned=True,
        )
        self.assertEqual(after, before)
        self.assertIs(
            vars(NSDocument)["writeToURL_ofType_"], original_descriptor
        )
        self.assertEqual(
            document_adapter._LIVE_SOURCE_SAVE_GUARD_MANAGER.snapshot().state,
            "healthy",
        )

        # Exact IMP restoration is the primary proof. This genuine native call
        # additionally proves the Python guard wrapper is no longer reachable;
        # NSDocument itself rejects the deliberately invalid URL.
        try:
            document.writeToURL_ofType_(None, None)
        except SourceSaveForbiddenError as exc:  # pragma: no cover - safety
            self.fail("native save selector remained interposed: {!r}".format(exc))
        except Exception:
            pass

    @unittest.skipUnless(
        _PYOBJC_RUNTIME is not None and _NSDOCUMENT_RUNTIME is not None,
        "PyObjC host boundary",
    )
    def test_runtime_guard_restores_pyobjc_python_method_descriptor(self) -> None:
        objc = _PYOBJC_RUNTIME
        NSDocument = _NSDOCUMENT_RUNTIME
        assert objc is not None and NSDocument is not None
        save_calls = []

        class ManagedPythonSaveFixture(NSDocument):
            @objc.python_method
            def save(self):
                save_calls.append(self)

        document = ManagedPythonSaveFixture.alloc().init()
        original = vars(ManagedPythonSaveFixture)["save"]
        self.assertIsInstance(original, type(lambda: None))

        manager = document_adapter._WorkingSourceSaveGuardManager()
        with mock.patch.object(
            document_adapter, "_LIVE_SOURCE_SAVE_GUARD_MANAGER", manager
        ):
            guard = document_adapter._WorkingSourceSaveRuntimeGuard(
                [document],
                native_identity=lambda value: ("python", id(value)),
            )
            with self.assertRaises(SourceSaveForbiddenError):
                with guard:
                    installed = vars(ManagedPythonSaveFixture)["save"]
                    self.assertIsInstance(installed, type(lambda: None))
                    self.assertIsNot(installed, original)
                    # The descriptor wrapper remains the primary interlock
                    # even if open-world code disables the profile callback.
                    sys.setprofile(None)
                    document.save()

            self.assertIs(
                vars(ManagedPythonSaveFixture)["save"], original
            )
            self.assertEqual(save_calls, [])
            self.assertEqual(manager.snapshot().state, "healthy")

            # A verified teardown must permit the next execution instead of
            # leaving process-wide degraded state behind in Glyphs 4.
            with document_adapter._WorkingSourceSaveRuntimeGuard(
                [document],
                native_identity=lambda value: ("python", id(value)),
            ):
                pass
            self.assertIs(
                vars(ManagedPythonSaveFixture)["save"], original
            )
            self.assertEqual(manager.snapshot().state, "healthy")

    def test_runtime_guard_fails_closed_when_restoration_cannot_verify(self) -> None:
        class RefuseRestore(type):
            writes = 0

            def __setattr__(owner, name, value):
                if name == "saveDocument_":
                    writes = type.__getattribute__(owner, "writes")
                    type.__setattr__(owner, "writes", writes + 1)
                    if writes >= 1:
                        raise RuntimeError("restoration refused")
                type.__setattr__(owner, name, value)

        class SaveDocument(metaclass=RefuseRestore):
            def saveDocument_(self, sender):
                return sender

        original = vars(SaveDocument)["saveDocument_"]
        document = SaveDocument()
        manager = document_adapter._WorkingSourceSaveGuardManager()
        with mock.patch.object(
            document_adapter, "_LIVE_SOURCE_SAVE_GUARD_MANAGER", manager
        ):
            guard = document_adapter._WorkingSourceSaveRuntimeGuard(
                [document],
                native_identity=lambda value: ("python", id(value)),
            )
            incident = None
            try:
                with self.assertRaises(
                    document_adapter.ScriptingRuntimeUnavailableError
                ) as failed:
                    with guard:
                        pass
                self.assertIn("requires repair", str(failed.exception))
                incident = manager.snapshot().current_incident
                self.assertEqual(manager.snapshot().state, "recovery_required")
                self.assertIsNotNone(incident)
                recovery_guard = document_adapter._WorkingSourceSaveRuntimeGuard(
                    [document],
                    native_identity=lambda value: ("python", id(value)),
                )
                with self.assertRaisesRegex(
                    document_adapter.ScriptingRuntimeUnavailableError,
                    "repair the current incident",
                ):
                    with recovery_guard:
                        pass
            finally:
                # Bypass the intentionally hostile metaclass so this
                # regression cannot leak its interposition into later tests.
                type.__setattr__(SaveDocument, "saveDocument_", original)
                manager.repair(
                    trigger="test_cleanup",
                    expected_incident_id=(
                        incident.incident_id if incident is not None else None
                    ),
                )

        type.__setattr__(SaveDocument, "writes", 0)
        manager = document_adapter._WorkingSourceSaveGuardManager()
        with mock.patch.object(
            document_adapter, "_LIVE_SOURCE_SAVE_GUARD_MANAGER", manager
        ):
            active_guard = document_adapter._WorkingSourceSaveRuntimeGuard(
                [document],
                native_identity=lambda value: ("python", id(value)),
            )
            try:
                with self.assertRaisesRegex(ValueError, "active execution error"):
                    with active_guard:
                        raise ValueError("active execution error")
                self.assertEqual(manager.snapshot().state, "recovery_required")
            finally:
                type.__setattr__(SaveDocument, "saveDocument_", original)
                incident = manager.snapshot().current_incident
                manager.repair(
                    trigger="test_cleanup",
                    expected_incident_id=(
                        incident.incident_id if incident is not None else None
                    ),
                )

    def test_live_python_after_model_is_captured_after_main_queue_yields(self) -> None:
        font = _TransactionalFont()

        class SettlingExecutor:
            def run(self, callback):
                result = callback()
                if font.familyName == "Intermediate":
                    font.familyName = "Settled"
                return result

        host = GlyphsDocumentHost(_App(font), executor=SettlingExecutor())
        document_id = host.list_documents()[0].document_id
        request = PythonExecutionRequest(
            code="font.familyName = 'Intermediate'",
            reason="prove post-main-queue settlement",
            intended_effect="document_edit",
            execution_mode="live_open_world",
            document_id=document_id,
        )

        with mock.patch.object(
            document_adapter,
            "_native_persistent_font_model",
            side_effect=lambda value, **options: native_font_to_model(
                value, instance_ids=options.get("instance_ids")
            ),
        ) as persistent_capture:
            result = host.run_live_python(request)

        self.assertEqual(
            result["beforeModel"]["font"]["familyName"], "Transaction Test"
        )
        self.assertEqual(result["afterModel"]["font"]["familyName"], "Settled")
        self.assertEqual(font.familyName, "Settled")
        self.assertGreaterEqual(persistent_capture.call_count, 1)

    def test_stable_capture_settlement_window_starts_after_initial_capture(self) -> None:
        font = _TransactionalFont()
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        snapshot = host.capture_snapshot(document_id)
        clock = [0.0]
        capture_count = [0]

        def slow_initial_capture(*_args, **_kwargs):
            capture_count[0] += 1
            if capture_count[0] == 1:
                clock[0] = 1.0
            return snapshot

        def advance(seconds):
            clock[0] += seconds

        with mock.patch.object(
            host,
            "_capture_snapshot_coordinated",
            side_effect=slow_initial_capture,
        ), mock.patch.object(
            document_adapter.time,
            "monotonic",
            side_effect=lambda: clock[0],
        ), mock.patch.object(
            document_adapter.time,
            "sleep",
            side_effect=advance,
        ):
            observed = host.capture_stable_snapshot(document_id)

        self.assertIs(observed, snapshot)
        self.assertEqual(capture_count[0], 2)

    def test_complete_staged_clone_capture_prefers_format_v4_source(self) -> None:
        font = _TransactionalFont()
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        source = host.capture_snapshot(document_id)
        persistent = source.materialize()

        with mock.patch.object(
            document_adapter,
            "_native_persistent_font_model",
            return_value=persistent,
        ) as persistent_capture, mock.patch.object(
            document_adapter,
            "native_font_to_model",
            wraps=document_adapter.native_font_to_model,
        ) as getter_capture:
            observed = host._capture_detached_model(
                font,
                source,
                document_path="/fonts/Canonical.glyphspackage",
            )

        self.assertEqual(fingerprint_model(observed), fingerprint_model(source))
        persistent_capture.assert_called_once()
        self.assertEqual(
            persistent_capture.call_args.kwargs["document_path"],
            "/fonts/Canonical.glyphspackage",
        )
        getter_capture.assert_not_called()

    def test_staged_review_scope_uses_clone_stable_full_font_archive(self) -> None:
        font = _TransactionalFont()
        request = PythonExecutionRequest(
            code="layer.width += 10",
            reason="clone-stable archive proof",
            intended_effect="document_edit",
            execution_mode="staged_document",
            document_id="doc-1",
            glyph_name="A",
            layer_id="master-regular",
        )

        with mock.patch.object(
            document_adapter,
            "_serialized_font_archive",
            return_value=b"normalized-full-font-archive",
        ) as full_archive:
            archive = document_adapter._serialized_review_scope(font, request)

        self.assertEqual(archive, b"normalized-full-font-archive")
        full_archive.assert_called_once_with(font)

    def test_native_archive_uses_complete_sharded_package_manifest(self) -> None:
        requested_paths = []

        def save_package(_font, path):
            requested_paths.append(path)
            path.mkdir()
            (path / "fontinfo.plist").write_text(
                '{"familyName":"Test","privateRoot":"root-state"}',
                encoding="utf-8",
            )
            glyphs = path / "glyphs"
            glyphs.mkdir()
            (glyphs / "B.glyph").write_text(
                '{"glyphname":"B","privateGlyph":2}', encoding="utf-8"
            )
            (glyphs / "A.glyph").write_text(
                '{"glyphname":"A","privateGlyph":1}', encoding="utf-8"
            )

        with mock.patch.object(
            document_adapter,
            "_save_font_copy",
            side_effect=save_package,
        ):
            archive = document_adapter._serialized_font_archive(object())

        self.assertEqual(len(requested_paths), 1)
        self.assertEqual(requested_paths[0].suffix, ".glyphspackage")
        manifest = document_adapter._decoded_native_archive_tree(archive)
        self.assertEqual(manifest["format"], "glyphspackage-v1")
        self.assertEqual(
            [entry["path"] for entry in manifest["files"]],
            ["fontinfo.plist", "glyphs/A.glyph", "glyphs/B.glyph"],
        )
        self.assertEqual(
            manifest["files"][0]["value"]["privateRoot"], "root-state"
        )
        self.assertEqual(
            manifest["files"][1]["value"]["privateGlyph"], 1
        )

    def test_native_archive_excludes_package_ui_session_state(self) -> None:
        def save_package(_font, path):
            path.mkdir()
            (path / "fontinfo.plist").write_text(
                '{"familyName":"Test"}', encoding="utf-8"
            )
            (path / "UIState.plist").write_text(
                '{"tabs":["A","B"]}', encoding="utf-8"
            )

        with mock.patch.object(
            document_adapter,
            "_save_font_copy",
            side_effect=save_package,
        ):
            archive = document_adapter._serialized_font_archive(object())

        manifest = document_adapter._decoded_native_archive_tree(archive)
        self.assertEqual(
            [entry["path"] for entry in manifest["files"]],
            ["fontinfo.plist"],
        )

    def test_native_package_manifest_detects_private_file_changes(self) -> None:
        before = {
            "format": "glyphspackage-v1",
            "files": [
                {
                    "path": "glyphs/A.glyph",
                    "value": {"glyphname": "A", "privateGlyph": 1},
                }
            ],
        }
        after = copy.deepcopy(before)
        after["files"][0]["value"]["privateGlyph"] = 2
        encode = lambda value: document_adapter.json.dumps(
            value, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

        result = document_adapter._compare_native_archive_deltas(
            encode(before), encode(after), encode(before), encode(before)
        )

        self.assertFalse(result["equivalent"])
        self.assertEqual(
            result["mismatchLocations"][0]["path"],
            ["files", "@path=glyphs/A.glyph", "value", "privateGlyph"],
        )

    def test_native_package_normalizes_clone_instance_ids_before_encoding(self) -> None:
        identifier = "11111111-1111-4111-8111-111111111111"

        def save_package(_font, path):
            path.mkdir()
            (path / "fontinfo.plist").write_text(
                'instances = ({ id = "' + identifier + '"; });',
                encoding="utf-8",
            )

        font = SimpleNamespace(instances=[SimpleNamespace(id=identifier)])
        with mock.patch.object(
            document_adapter, "_save_font_copy", side_effect=save_package
        ):
            archive = document_adapter._serialized_font_archive(font)

        manifest = document_adapter._decoded_native_archive_tree(archive)
        encoded = manifest["files"][0]["value"]["$data"]
        decoded = document_adapter.base64.b64decode(encoded)
        self.assertNotIn(identifier.encode("ascii"), decoded)
        self.assertIn(b"__GLYPHS_MCP_INSTANCE_0000__", decoded)

    def test_staged_layer_python_compares_native_archive_deltas(self) -> None:
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
        class TrackingExecutor:
            def __init__(self):
                self.in_callback = False

            def run(self, callback):
                self.in_callback = True
                try:
                    return callback()
                finally:
                    self.in_callback = False

        executor = TrackingExecutor()
        host = GlyphsDocumentHost(_App(font), executor=executor)
        document_id = host.list_documents()[0].document_id
        before = host.capture_model(document_id)
        phases = []
        checkpoints = []
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
            progress_callback=lambda phase, _message, _cancellable: phases.append(
                phase
            ),
            checkpoint_callback=lambda: checkpoints.append(True),
        )

        def scoped_archive(candidate, scoped_request):
            candidate_glyph = document_adapter._lookup_by_name(
                candidate.glyphs, scoped_request.glyph_name
            )
            candidate_layer = document_adapter._lookup_layer(
                candidate_glyph, scoped_request.layer_id
            )
            return repr(native_layer_to_model(candidate_layer)).encode("utf-8")

        real_compare = document_adapter._compare_native_archive_deltas

        def compare_off_main(*args, **kwargs):
            self.assertFalse(executor.in_callback)
            return real_compare(*args, **kwargs)

        with mock.patch.object(
            document_adapter,
            "_serialized_review_scope",
            side_effect=scoped_archive,
            create=True,
        ), mock.patch.object(
            document_adapter,
            "_compare_native_archive_deltas",
            side_effect=compare_off_main,
        ):
            preview = host.preview_python(request, before)

        self.assertEqual(
            layer_paths(
                _model_layer(preview["afterModel"], "A", "master-regular")
            )[0]["nodes"][0]["x"],
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
        self.assertEqual(
            phases,
            [
                "stabilizing",
                "cloning",
                "executing",
                "comparing",
                "replaying",
                "verifying",
                "checking_scope",
            ],
        )
        self.assertGreaterEqual(len(checkpoints), 6)
        self.assertIn("cloneCaptureMs", preview["stageTimings"])
        self.assertIn("evaluationCaptureMs", preview["stageTimings"])
        self.assertIn("replayCaptureMs", preview["stageTimings"])
        self.assertIn("maxNativePhaseMs", preview["stageTimings"])
    def test_canonical_layer_excludes_native_alignment_observations(self) -> None:
        path = _OutlinePath([_OutlineNode(0, 0), _OutlineNode(100, 0)])
        component = _OutlineComponent("jdotless")
        layer = _OutlineLayer(path, component)

        model = native_layer_to_model(layer)

        self.assertNotIn("hasAlignedWidth", model)
        self.assertEqual(layer_components(model)[0]["alignment"], 0)
        self.assertNotIn("automaticAlignment", layer_components(model)[0])

    def test_layer_observation_reports_native_effective_alignment(self) -> None:
        path = _OutlinePath([_OutlineNode(0, 0), _OutlineNode(100, 0)])
        component = _OutlineComponent("acute")
        layer = _OutlineLayer(path, component)
        layer.isAligned = True
        glyph = SimpleNamespace(name="Aacute", layers=[layer])
        font = _TransactionalFont()
        font.glyphs = [glyph]
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id

        observations = host.inspect_layers(document_id, ("Aacute",))

        self.assertTrue(observations[("Aacute", "master-regular")]["isAligned"])
        self.assertTrue(
            observations[("Aacute", "master-regular")]["hasAlignedWidth"]
        )

    def test_staged_feature_addition_uses_opaque_native_replay_evidence(self) -> None:
        class Feature:
            def __init__(self, name, code, native_only):
                self.name = name
                self.code = code
                self.automatic = False
                self.disabled = False
                self.nativeOnly = native_only

            def copy(self):
                return copy.copy(self)

        font = _TransactionalFont()
        font.features = [
            Feature("liga", "sub f i by fi;", "private-feature-state")
        ]
        font.copy = lambda: copy.deepcopy(font)
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        before = host.capture_model(document_id)
        request = PythonExecutionRequest(
            code=(
                "feature = font.features[0].copy()\n"
                "feature.name = 'kern'\n"
                "feature.code = 'pos A V -80;'\n"
                "font.features.append(feature)"
            ),
            reason="staged feature membership",
            intended_effect="document_edit",
            execution_mode="staged_document",
            document_id=document_id,
            expected_document_fingerprint=fingerprint_model(before),
        )

        def archive(candidate, _request):
            return repr(
                [
                    (item.name, item.code, item.nativeOnly)
                    for item in candidate.features
                ]
            ).encode("utf-8")

        with mock.patch.object(
            document_adapter,
            "_serialized_review_scope",
            side_effect=archive,
        ):
            preview = host.preview_python(request, before)

        self.assertTrue(preview["nativeArchiveComparison"]["equivalent"])
        self.assertEqual(
            [item["id"] for item in preview["afterModel"]["features"]],
            ["liga", "kern"],
        )
        context = preview["executionContext"]
        self.assertEqual(set(context), {"nativeReplayEvidenceId"})
        self.assertTrue(
            host.validate_staged_replay_evidence(
                document_id,
                context,
                before_fingerprint=fingerprint_model(before),
                after_fingerprint=fingerprint_model(preview["afterModel"]),
                capabilities=preview["capabilities"],
            )
        )
        host.release_staged_replay_evidence(
            context["nativeReplayEvidenceId"]
        )
        self.assertFalse(
            host.validate_staged_replay_evidence(
                document_id,
                context,
                before_fingerprint=fingerprint_model(before),
                after_fingerprint=fingerprint_model(preview["afterModel"]),
                capabilities=preview["capabilities"],
            )
        )

    def test_staged_feature_deletion_rolls_back_the_exact_native_entity(self) -> None:
        class Feature:
            def __init__(self):
                self.name = "liga"
                self.code = "sub f i by fi;"
                self.automatic = False
                self.disabled = False
                self.nativeOnly = "private-feature-state"

            def copy(self):
                return copy.copy(self)

        original = Feature()
        font = _TransactionalFont()
        font.features = [original]
        font.copy = lambda: copy.deepcopy(font)
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        service = PythonExecutionService(
            host=host,
            transactions=TransactionKernel(host),
            reviews=OperationStore(),
            checkpoints=OperationStore(),
            audit=AuditLog(),
        )
        document_id = host.list_documents()[0].document_id
        baseline = host.capture_model(document_id)
        request = PythonExecutionRequest(
            code="del font.features[0]",
            reason="delete feature through staged replay",
            intended_effect="document_edit",
            execution_mode="staged_document",
            document_id=document_id,
            expected_document_fingerprint=fingerprint_model(baseline),
        )

        def archive(candidate, _request):
            return repr(
                [
                    (item.name, item.code, item.nativeOnly)
                    for item in candidate.features
                ]
            ).encode("utf-8")

        with mock.patch.object(
            document_adapter,
            "_serialized_review_scope",
            side_effect=archive,
        ):
            preview = service.execute(request).to_dict()
        preview_id = preview["data"]["previewId"]
        confirmed = service.apply_staged_preview(
            service._reviews.get(preview_id),
            operation_id="op_feature_delete",
            reason="apply exact staged feature deletion",
        ).to_dict()

        self.assertTrue(confirmed["ok"])
        self.assertEqual(font.features, [])
        rolled_back = service.recover_checkpoint(
            execution_id=confirmed["data"]["executionId"],
            expected_after_fingerprint=confirmed["data"]["afterFingerprint"],
            confirm=True,
        ).to_dict()

        self.assertTrue(rolled_back["ok"])
        self.assertIs(font.features[0], original)
        self.assertEqual(host.capture_model(document_id), baseline)

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
            layer_paths(model)[0]["nodes"][0]["x"],
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

    def test_topology_compatible_component_delta_updates_position_in_place(self) -> None:
        path = _OutlinePath([_OutlineNode(0, 0), _OutlineNode(100, 0)])
        component = _OutlineComponent("acute")
        layer = _OutlineLayer(path, component)
        glyph = SimpleNamespace(name="Aacute", layers={"master-regular": layer})
        font = SimpleNamespace(glyphs={"Aacute": glyph})
        before_component = {
            "name": "acute",
            "position": [12, 20],
        }
        component.position = tuple(before_component["position"])
        after_component = copy.deepcopy(before_component)
        after_component["position"][0] = 37
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
        self.assertEqual(tuple(component.position), (37, 20))
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
        current_layer = native_layer_to_model(layer)
        current_layer["width"] = 529
        target_layer = copy.deepcopy(current_layer)
        target_layer["width"] = 500
        layer_paths(target_layer)[0]["nodes"][0]["x"] = 0
        layer_paths(target_layer)[0]["nodes"][1]["x"] = 100
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
                    ("glyphs", "L", "layers", "master-regular", "shapes"),
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
        current_layer = native_layer_to_model(layer)
        target_layer = copy.deepcopy(current_layer)
        layer_paths(target_layer)[0]["nodes"][0]["x"] = 0
        layer_paths(target_layer)[0]["nodes"][1]["x"] = 100
        layer_components(target_layer)[0]["position"][0] = 20
        current = {"glyphs": {"L": {"layers": {"master-regular": current_layer}}}}
        target = {"glyphs": {"L": {"layers": {"master-regular": target_layer}}}}
        replacement_path = _OutlinePath([_OutlineNode(0, 0), _OutlineNode(100, 0)])
        replacement_component = _OutlineComponent("acute")
        replacement_component.position = (20, 0)

        with mock.patch.object(document_adapter, "_new_path", return_value=replacement_path), mock.patch.object(
            document_adapter, "_new_component", return_value=replacement_component
        ):
            document_adapter._apply_target_model(
                font,
                current,
                target,
                diff_models(current, target),
                replay_replacements=(
                    ("glyphs", "L", "layers", "master-regular", "shapes"),
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
        self.assertIsNone(layer_paths(absent_model)[0]["nodes"][0]["name"])

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
                            "shapes": [{
                                "id": "shape:path:0",
                                "kind": "path",
                                "value": {"closed": True, "nodes": [{"x": 0, "y": 0}]},
                            }],
                            "width": 500,
                        }
                    }
                }
            }
        }
        target = copy.deepcopy(before)
        layer_paths(_model_layer(target, "L", "m0"))[0]["nodes"][0]["x"] = 20
        observed = copy.deepcopy(target)
        layer_paths(_model_layer(observed, "L", "m0"))[0]["nodes"][0]["x"] = 19

        roots = document_adapter._canonical_replacement_roots(
            before, target, observed
        )

        self.assertEqual(
            roots,
            (("glyphs", "L", "layers", "m0", "shapes"),),
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

    def test_instance_without_external_mapping_uses_internal_coordinates(self) -> None:
        font = SimpleNamespace(
            axes=[SimpleNamespace(axisTag="wght"), SimpleNamespace(axisTag="wdth")],
            instances=[
                SimpleNamespace(
                    name="Semibold Condensed",
                    type=0,
                    active=True,
                    axes=[650, 82],
                    externalAxes=[],
                    customParameters=[],
                    properties=[],
                    userData={},
                )
            ],
        )

        instances = document_adapter._instance_models(font)

        self.assertEqual(
            instances[0]["axes"],
            [
                {"tag": "wght", "internal": 650, "external": 650},
                {"tag": "wdth", "internal": 82, "external": 82},
            ],
        )

    def test_instance_external_coordinates_fall_back_per_axis(self) -> None:
        font = SimpleNamespace(
            axes=[SimpleNamespace(axisTag="wght"), SimpleNamespace(axisTag="wdth")],
            instances=[
                SimpleNamespace(
                    name="Semibold Condensed",
                    type=0,
                    active=True,
                    axes=[650, 82],
                    externalAxes=[None, 70],
                    customParameters=[],
                    properties=[],
                    userData={},
                )
            ],
        )

        instances = document_adapter._instance_models(font)

        self.assertEqual(
            instances[0]["axes"],
            [
                {"tag": "wght", "internal": 650, "external": 650},
                {"tag": "wdth", "internal": 82, "external": 70},
            ],
        )

    def test_instance_replay_treats_style_names_as_the_authoritative_name(self) -> None:
        old_property = {
            "id": "property:styleNames:0",
            "key": "styleNames",
            "value": None,
            "values": [{"language": "dflt", "value": "Old"}],
        }
        new_property = copy.deepcopy(old_property)
        new_property["values"][0]["value"] = "New"
        native = SimpleNamespace(
            name="New",
            properties=[
                SimpleNamespace(
                    key="styleNames",
                    value=None,
                    values=[SimpleNamespace(language="dflt", value="New")],
                )
            ],
            customParameters=[],
            userData={},
        )
        font = SimpleNamespace(instances=[native])

        document_adapter._apply_instance_collection(
            font,
            [{"id": "instance_0", "name": "Old", "properties": [old_property]}],
            [{"id": "instance_0", "name": "New", "properties": [new_property]}],
        )

        self.assertEqual(native.name, "New")
        self.assertEqual(document_adapter._property_models(native), [new_property])

    def test_native_localized_property_collapses_to_official_v4_spelling(self) -> None:
        owner = SimpleNamespace(
            properties=[
                SimpleNamespace(
                    key="styleNames",
                    value="Regular",
                    values=[SimpleNamespace(language="", value="Regular")],
                )
            ]
        )

        self.assertEqual(
            document_adapter._property_models(owner),
            [
                {
                    "id": "property:styleNames:0",
                    "key": "styleNames",
                    "value": None,
                    "values": [{"language": "dflt", "value": "Regular"}],
                }
            ],
        )

    def test_new_instance_is_constructed_without_the_convenience_name(self) -> None:
        collection = []
        native = SimpleNamespace(name="")

        with mock.patch.object(
            document_adapter,
            "_construct_native_entity",
            return_value=native,
        ) as constructor:
            result = document_adapter._sync_native_entities(
                collection,
                [],
                [{"id": "instance_new", "name": "Bold"}],
                kind="instance",
            )

        constructor.assert_called_once_with("instance", "")
        self.assertIs(result["instance_new"], native)
        self.assertEqual(collection, [native])

    def test_exact_instance_evidence_is_attached_without_default_replay(self) -> None:
        native = SimpleNamespace(name="Exact")
        font = SimpleNamespace(instances=[])
        target = {
            "id": "instance_new",
            "name": "Exact",
            "properties": [],
            "customParameters": [],
            "instanceInterpolations": {"master": 1.0},
        }

        with mock.patch.object(
            document_adapter, "_set_native_property"
        ) as set_property, mock.patch.object(
            document_adapter, "_apply_owned_metadata"
        ) as apply_metadata:
            document_adapter._apply_instance_collection(
                font,
                [],
                [target],
                templates={"instance_new": native},
                reuse_native_templates=True,
            )

        self.assertEqual(font.instances, [native])
        set_property.assert_not_called()
        apply_metadata.assert_called_once_with(native, target, target)

    def test_new_owner_replays_over_registered_native_constructor_defaults(self) -> None:
        class Localized:
            def __init__(self):
                self.key = ""
                self.value = None
                self.values = []

        class Single:
            def __init__(self):
                self.key = ""
                self.value = None

        class Value:
            def __init__(self):
                self.languageTag = ""
                self.value = None

        glyphs_module = SimpleNamespace(
            GSInfoValue=Value,
            GSInfoValueLocalized=Localized,
            GSInfoValueSingle=Single,
        )
        native = SimpleNamespace(
            properties=[
                SimpleNamespace(
                    key="styleNames",
                    value=None,
                    values=[SimpleNamespace(language="dflt", value="Regular")],
                )
            ],
            customParameters=[],
            userData={},
        )
        target = {
            "properties": [
                {
                    "id": "property:styleNames:0",
                    "key": "styleNames",
                    "value": None,
                    "values": [{"language": "dflt", "value": "Bold"}],
                }
            ],
            "customParameters": [],
            "userData": {},
        }

        with mock.patch.dict(sys.modules, {"GlyphsApp": glyphs_module}):
            document_adapter._apply_owned_metadata(native, {}, target)

        self.assertIsInstance(native.properties[0], Localized)
        self.assertEqual(
            document_adapter._property_models(native), target["properties"]
        )
        self.assertIsInstance(native.properties[0].values[0], Value)

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

        # Keep this identity-mapping test independent of PyObjC module state.
        # Removing a synthetic ``objc`` entry after Foundation has loaded the
        # real extension makes a later import attempt an unsupported extension
        # reload in a full-suite process.
        with mock.patch.object(
            host,
            "_native_instance_key",
            side_effect=lambda value: "objc:{}".format(value.pointer),
        ):
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

        # Native dirty accounting remains pending until settled verification.
        self.assertFalse(font.parent.isDocumentEdited)
        self.assertTrue(host.list_documents()[0].has_unsaved_changes)
        host.commit_verified_change("op_forward")

        self.assertTrue(font.parent.isDocumentEdited)
        self.assertTrue(host.list_documents()[0].has_unsaved_changes)

        host.apply_verified_change_set(
            document_id,
            change_set.inverse(),
            operation_id="op_revert",
            removes_contribution_id="op_forward",
        )
        host.commit_verified_change("op_revert")

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
        host.commit_verified_change("op_forward")

        self.assertFalse(font.parent.hasUnautosavedChanges)
        self.assertTrue(host.list_documents()[0].has_unsaved_changes)

        host.apply_verified_change_set(
            document_id,
            change_set.inverse(),
            operation_id="op_revert",
            removes_contribution_id="op_forward",
        )
        host.commit_verified_change("op_revert")

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
        host.commit_verified_change("op_forward")
        host.apply_verified_change_set(
            document_id,
            change_set.inverse(),
            operation_id="op_revert",
            removes_contribution_id="op_forward",
        )
        host.commit_verified_change("op_revert")

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
        host.commit_verified_change("op_forward")
        host.apply_verified_change_set(
            document_id,
            change_set.inverse(),
            operation_id="op_revert",
            removes_contribution_id="op_forward",
        )
        host.commit_verified_change("op_revert")

        self.assertTrue(font.parent.isDocumentEdited)
        self.assertFalse(host.list_documents()[0].has_unsaved_changes)

        font.note = "manual later edit"
        self.assertTrue(host.list_documents()[0].has_unsaved_changes)

    def test_compensating_verified_change_back_to_baseline_is_not_phantom_dirty(self) -> None:
        font = _TransactionalFont(sticky_after_undo=True)
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        baseline = host.capture_model(document_id)
        changed = copy.deepcopy(baseline)
        changed["font"]["note"] = "temporary qualification change"

        forward = diff_models(baseline, changed)
        host.apply_verified_change_set(
            document_id, forward, operation_id="op_forward"
        )
        host.commit_verified_change("op_forward")
        host.apply_verified_change_set(
            document_id, forward.inverse(), operation_id="op_compensation"
        )
        host.commit_verified_change("op_compensation")

        self.assertEqual(host.capture_model(document_id), baseline)
        self.assertFalse(host.list_documents()[0].has_unsaved_changes)

        font.note = "manual later edit"
        self.assertTrue(host.list_documents()[0].has_unsaved_changes)

    def test_sequential_exact_reverts_preserve_the_verified_clean_baseline(self) -> None:
        font = _TransactionalFont(sticky_after_undo=True)
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        baseline = host.capture_model(document_id)

        for suffix in ("A", "B"):
            current = host.capture_model(document_id)
            changed = copy.deepcopy(current)
            changed["font"]["note"] = suffix
            change_set = diff_models(current, changed)
            host.apply_verified_change_set(
                document_id,
                change_set,
                operation_id="op_forward_{}".format(suffix),
            )
            host.commit_verified_change("op_forward_{}".format(suffix))
            host.apply_verified_change_set(
                document_id,
                diff_models(host.capture_model(document_id), baseline),
                operation_id="op_revert_{}".format(suffix),
                removes_contribution_id="op_forward_{}".format(suffix),
            )
            host.commit_verified_change("op_revert_{}".format(suffix))

            self.assertTrue(font.parent.isDocumentEdited)
            self.assertFalse(
                host.list_documents()[0].has_unsaved_changes,
                "verified cycle {} inherited a sticky native dirty bit".format(suffix),
            )

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
        host.finalize_verified_failure(
            "op_forward",
            rollback_succeeded=True,
            observed_fingerprint=fingerprint_model(before),
        )

        self.assertIsNone(font.note)
        self.assertFalse(font.parent.isDocumentEdited)
        self.assertEqual(font.parent.change_counts, [])

    def test_unverifiable_failed_attempt_forces_dirty_and_never_exposes_clean(self) -> None:
        font = _TransactionalFont()
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        before = host.capture_model(document_id)
        after = copy.deepcopy(before)
        after["font"]["note"] = "attempted edit"

        host.apply_verified_change_set(
            document_id,
            diff_models(before, after),
            operation_id="op_unverified",
        )
        font.note = "unrestored divergence"
        observed = fingerprint_model(host.capture_model(document_id))
        host.finalize_verified_failure(
            "op_unverified",
            rollback_succeeded=False,
            observed_fingerprint=observed,
        )

        self.assertTrue(font.parent.isDocumentEdited)
        self.assertTrue(host.list_documents()[0].has_unsaved_changes)
        self.assertEqual(font.parent.change_counts, [0])
        self.assertTrue(
            host._document_mcp_contributions[document_id]["op_unverified"][
                "failedVerification"
            ]
        )

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
        host.commit_verified_change("op_forward")
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
        host.finalize_verified_failure(
            "op_revert_1",
            rollback_succeeded=True,
            observed_fingerprint=fingerprint_model(after),
        )

        self.assertEqual(font.note, "reviewed edit")
        self.assertTrue(font.parent.isDocumentEdited)
        self.assertEqual(font.parent.change_counts, [0])

        host.apply_verified_change_set(
            document_id,
            change_set.inverse(),
            operation_id="op_revert_2",
            removes_contribution_id="op_forward",
        )
        host.commit_verified_change("op_revert_2")
        self.assertFalse(font.parent.isDocumentEdited)
        self.assertEqual(font.parent.change_counts, [0, 1])

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
        host.commit_verified_change("op_A")

        before_b = host.capture_model(document_id)
        after_b = copy.deepcopy(before_b)
        after_b["font"]["grid"] = 2
        change_b = diff_models(before_b, after_b)
        host.apply_verified_change_set(
            document_id, change_b, operation_id="op_B"
        )
        host.commit_verified_change("op_B")

        current = host.capture_model(document_id)
        target_without_a = copy.deepcopy(current)
        target_without_a["font"]["note"] = None
        host.apply_verified_change_set(
            document_id,
            diff_models(current, target_without_a),
            operation_id="op_revert_A",
            removes_contribution_id="op_A",
        )
        host.commit_verified_change("op_revert_A")
        self.assertEqual(font.grid, 2)
        self.assertTrue(host.list_documents()[0].has_unsaved_changes)

        current = host.capture_model(document_id)
        host.apply_verified_change_set(
            document_id,
            diff_models(current, baseline),
            operation_id="op_revert_B",
            removes_contribution_id="op_B",
        )
        host.commit_verified_change("op_revert_B")
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

    def test_canonical_native_archive_mismatch_reports_semantic_path(self) -> None:
        direct_before = b'{"font":{"glyphs":[{"name":"A","private":1}]}}'
        replay_before = b'{"font":{"glyphs":[{"name":"A","private":1}]}}'
        direct_after = b'{"font":{"glyphs":[{"name":"A","private":2}]}}'
        replay_after = b'{"font":{"glyphs":[{"name":"A","private":3}]}}'

        result = document_adapter._compare_native_archive_deltas(
            direct_before,
            direct_after,
            replay_before,
            replay_after,
        )

        self.assertFalse(result["equivalent"])
        self.assertEqual(result["mismatchCount"], 1)
        self.assertEqual(
            result["mismatchLocations"][0]["path"],
            ["font", "glyphs", 0, "private"],
        )
        self.assertEqual(result["mismatchLocations"][0]["direct"], 2)
        self.assertEqual(result["mismatchLocations"][0]["replay"], 3)

    def test_native_package_mismatch_reports_file_and_decoded_openstep_path(self) -> None:
        def archive(value: int) -> bytes:
            data = base64.b64encode(
                "glyphs = ({ glyphname = A; private = %d; });".encode("utf-8")
                % value
            ).decode("ascii")
            return json.dumps(
                {
                    "format": "glyphspackage-v1",
                    "files": [
                        {"path": "glyphs/A.glyph", "value": {"$data": data}}
                    ],
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")

        before = archive(1)
        result = document_adapter._compare_native_archive_deltas(
            before,
            archive(2),
            before,
            archive(3),
        )

        self.assertFalse(result["equivalent"])
        self.assertEqual(result["mismatchCount"], 1)
        self.assertEqual(
            result["mismatchLocations"][0]["path"],
            [
                "files",
                "@path=glyphs/A.glyph",
                "value",
                "$decoded",
                "glyphs",
                0,
                "private",
            ],
        )
        self.assertEqual(result["mismatchLocations"][0]["direct"], 2)
        self.assertEqual(result["mismatchLocations"][0]["replay"], 3)

    def test_native_package_byte_difference_remains_strict_when_decoded_equal(self) -> None:
        def archive(data: bytes) -> bytes:
            return json.dumps(
                {
                    "format": "glyphspackage-v1",
                    "files": [
                        {
                            "path": "fontinfo.plist",
                            "value": {
                                "$data": base64.b64encode(data).decode("ascii")
                            },
                        }
                    ],
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")

        compact = archive(b"font = { value = 1; };")
        spaced = archive(b"font = {\nvalue = 1;\n};\n")
        result = document_adapter._compare_native_archive_deltas(
            compact,
            compact,
            compact,
            spaced,
        )

        self.assertFalse(result["equivalent"])
        self.assertEqual(result["mismatchCount"], 1)
        self.assertEqual(
            result["mismatchLocations"][0]["path"],
            ["files", "@path=fontinfo.plist", "value", "$data"],
        )

    def test_native_archive_proof_normalizes_only_registered_omitted_defaults(self) -> None:
        direct = {
            "files": [
                {
                    "path": "glyphs/A.glyph",
                    "value": {"layers": [{"layerId": "special"}]},
                }
            ]
        }
        replay = copy.deepcopy(direct)
        replay["files"][0]["value"]["layers"][0]["vertWidth"] = 0
        encode = lambda value: json.dumps(
            value, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

        equivalent = document_adapter._compare_native_archive_deltas(
            encode(direct), encode(direct), encode(direct), encode(replay)
        )
        self.assertTrue(equivalent["equivalent"])

        replay["files"][0]["value"]["layers"][0]["vertWidth"] = 1
        meaningful = document_adapter._compare_native_archive_deltas(
            encode(direct), encode(direct), encode(direct), encode(replay)
        )
        self.assertFalse(meaningful["equivalent"])
        self.assertEqual(
            meaningful["mismatchLocations"][0]["path"],
            ["files", "@path=glyphs/A.glyph", "value", "layers", 0, "vertWidth"],
        )

        direct_master = {
            "files": [
                {
                    "path": "fontinfo.plist",
                    "value": {"fontMaster": [{"id": "M1"}]},
                }
            ]
        }
        explicit_master_default = copy.deepcopy(direct_master)
        explicit_master_default["files"][0]["value"]["fontMaster"][0][
            "visible"
        ] = 1
        equivalent_master = document_adapter._compare_native_archive_deltas(
            encode(direct_master),
            encode(direct_master),
            encode(direct_master),
            encode(explicit_master_default),
        )
        self.assertTrue(equivalent_master["equivalent"])
        self.assertEqual(
            document_adapter._native_archive_fingerprint(encode(direct_master)),
            document_adapter._native_archive_fingerprint(
                encode(explicit_master_default)
            ),
        )

        explicit_master_default["files"][0]["value"]["fontMaster"][0][
            "visible"
        ] = 0
        meaningful_master = document_adapter._compare_native_archive_deltas(
            encode(direct_master),
            encode(direct_master),
            encode(direct_master),
            encode(explicit_master_default),
        )
        self.assertFalse(meaningful_master["equivalent"])

    def test_native_archive_equivalence_is_pairwise_for_wrapped_omission_defaults(
        self,
    ) -> None:
        def wrapped(text):
            return {
                "$data": base64.b64encode(text.encode("utf-8")).decode("ascii")
            }

        omitted = {
            "format": "glyphspackage-v1",
            "files": [
                {
                    "path": "fontinfo.plist",
                    "value": wrapped(
                        'fontMaster = ({ id = "MASTER"; name = Regular; });'
                    ),
                }
            ],
        }
        explicit = copy.deepcopy(omitted)
        explicit["files"][0]["value"] = wrapped(
            'fontMaster = ({ id = "MASTER"; name = Regular; visible = 1; });'
        )
        formatting_only = copy.deepcopy(omitted)
        formatting_only["files"][0]["value"] = wrapped(
            'fontMaster=({id="MASTER";name=Regular;});'
        )
        encode = lambda value: json.dumps(
            value, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

        accepted = document_adapter._compare_native_archives(
            encode(omitted), encode(explicit)
        )
        strict = document_adapter._compare_native_archives(
            encode(omitted), encode(formatting_only)
        )

        self.assertTrue(accepted["equivalent"])
        self.assertEqual(accepted["mismatchLocations"], [])
        self.assertFalse(strict["equivalent"])
        self.assertEqual(
            strict["mismatchLocations"][0]["path"],
            ["files", "@path=fontinfo.plist", "value", "$data"],
        )

    def test_native_clone_archive_mismatches_require_exact_canonical_artifacts(
        self,
    ) -> None:
        direct = {
            "format": "glyphspackage-v1",
            "files": [
                {
                    "path": "fontinfo.plist",
                    "value": {"settings": {"colorSpace": "apple-rgb"}},
                },
                {
                    "path": "glyphs/H_.glyph",
                    "value": {
                        "glyphname": "H",
                        "layers": [{"layerId": "L", "visible": 1}],
                    },
                },
            ],
        }
        clone = copy.deepcopy(direct)
        del clone["files"][0]["value"]["settings"]
        del clone["files"][1]["value"]["layers"][0]["visible"]
        encode = lambda value: json.dumps(
            value, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        comparison = document_adapter._compare_native_archives(
            encode(direct), encode(clone)
        )
        artifact_paths = (
            ("settings", "colorSpace"),
            ("glyphs", "H", "layers", "L", "visible"),
        )

        coverage = document_adapter._classify_native_clone_archive_mismatches(
            comparison["mismatchLocations"],
            artifact_paths=artifact_paths,
            direct_tree=direct,
            replay_tree=clone,
        )

        self.assertTrue(coverage["complete"])
        self.assertEqual(coverage["coveredCount"], 2)
        self.assertEqual(coverage["uncoveredLocations"], [])

        direct["files"][1]["value"]["privateState"] = 1
        comparison = document_adapter._compare_native_archives(
            encode(direct), encode(clone)
        )
        coverage = document_adapter._classify_native_clone_archive_mismatches(
            comparison["mismatchLocations"],
            artifact_paths=artifact_paths,
            direct_tree=direct,
            replay_tree=clone,
        )

        self.assertFalse(coverage["complete"])
        self.assertEqual(coverage["coveredCount"], 2)
        self.assertEqual(
            coverage["uncoveredLocations"][0]["path"],
            ["files", "@path=glyphs/H_.glyph", "value", "privateState"],
        )

    def test_native_archive_proof_aligns_identity_addressed_collections(self) -> None:
        before = b'{"layers":[{"layerId":"A","private":1},{"layerId":"B","private":2}]}'
        direct_after = b'{"layers":[{"layerId":"B","private":2},{"layerId":"A","private":1}]}'
        replay_after = b'{"layers":[{"layerId":"A","private":1},{"layerId":"B","private":2}]}'

        result = document_adapter._compare_native_archive_deltas(
            before,
            direct_after,
            before,
            replay_after,
        )

        self.assertTrue(result["equivalent"])
        self.assertTrue(result["finalEquivalent"])
        self.assertEqual(result["mismatchLocations"], [])

    def test_native_archive_fingerprint_normalizes_only_identity_storage_order(self) -> None:
        first = {
            "layers": [
                {"layerId": "B", "private": 2},
                {"layerId": "A", "private": 1},
            ],
            "nodes": [[0, 0], [10, 0]],
        }
        reordered_layers = {
            "layers": list(reversed(first["layers"])),
            "nodes": list(first["nodes"]),
        }
        reordered_nodes = {
            "layers": list(first["layers"]),
            "nodes": list(reversed(first["nodes"])),
        }

        self.assertEqual(
            document_adapter._normalized_native_archive_tree(first),
            document_adapter._normalized_native_archive_tree(reordered_layers),
        )
        self.assertNotEqual(
            document_adapter._normalized_native_archive_tree(first),
            document_adapter._normalized_native_archive_tree(reordered_nodes),
        )

    def test_native_archive_proof_preserves_positional_collection_order(self) -> None:
        before = b'{"nodes":[[0,0],[10,0]]}'
        direct_after = b'{"nodes":[[10,0],[0,0]]}'

        result = document_adapter._compare_native_archive_deltas(
            before,
            direct_after,
            before,
            before,
        )

        self.assertFalse(result["equivalent"])
        self.assertFalse(result["finalEquivalent"])
        self.assertEqual(result["mismatchLocations"][0]["path"], ["nodes", 0, 0])

    def test_native_archive_proof_normalizes_only_clone_baseline_uuids(self) -> None:
        direct_id = b"11111111-1111-4111-8111-111111111111"
        replay_id = b"22222222-2222-4222-8222-222222222222"
        direct_before = b"font = {\nprivateId = " + direct_id + b";\nvalue = 1;\n};\n"
        replay_before = b"font = {\nprivateId = " + replay_id + b";\nvalue = 1;\n};\n"
        direct_after = direct_before.replace(b"value = 1", b"value = 2")
        replay_after = replay_before.replace(b"value = 1", b"value = 2")

        result = document_adapter._compare_native_archive_deltas(
            direct_before,
            direct_after,
            replay_before,
            replay_after,
        )

        self.assertTrue(result["equivalent"])
        self.assertTrue(result["baselineEquivalent"])
        self.assertTrue(result["finalEquivalent"])
        self.assertEqual(result["normalizedCloneUuidCount"], 1)

    def test_native_archive_uuid_normalization_handles_repeated_ids_once(self) -> None:
        direct_id = b"11111111-1111-4111-8111-111111111111"
        replay_id = b"22222222-2222-4222-8222-222222222222"
        direct_before = b"{" + direct_id + b":" + direct_id + b"}"
        replay_before = b"{" + replay_id + b":" + replay_id + b"}"

        normalized = document_adapter._normalize_independent_clone_archives(
            direct_before,
            direct_before,
            replay_before,
            replay_before,
        )

        self.assertEqual(normalized[0], normalized[2])
        self.assertEqual(normalized[1], normalized[3])
        self.assertEqual(normalized[4], 1)

    def test_native_archive_proof_rejects_new_private_uuid_changes(self) -> None:
        direct_id = b"11111111-1111-4111-8111-111111111111"
        replay_id = b"22222222-2222-4222-8222-222222222222"
        unexpected_id = b"33333333-3333-4333-8333-333333333333"
        direct_before = b"privateId = " + direct_id + b";\n"
        replay_before = b"privateId = " + replay_id + b";\n"
        direct_after = b"privateId = " + unexpected_id + b";\n"

        result = document_adapter._compare_native_archive_deltas(
            direct_before,
            direct_after,
            replay_before,
            replay_before,
        )

        self.assertFalse(result["equivalent"])
        self.assertTrue(result["baselineEquivalent"])
        self.assertFalse(result["finalEquivalent"])

    def test_archive_delta_is_linear_enough_for_repeated_glyphs_lines(self) -> None:
        before = b"\n".join([b"layer = {" for _ in range(20_000)])
        after_lines = before.splitlines()
        after_lines.insert(10_000, b"name = staged;")

        started = time.perf_counter()
        delta = document_adapter._archive_delta(before, b"\n".join(after_lines))
        duration = time.perf_counter() - started

        self.assertTrue(delta)
        self.assertLess(duration, 1.0)

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
