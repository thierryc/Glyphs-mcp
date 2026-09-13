"""Native-adapter behavior with small Glyphs-shaped stand-ins."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


REPO = Path(__file__).resolve().parents[3]
for root in (REPO / "src" / "protocol", REPO / "src" / "bridge"):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter  # noqa: E402


class IndexedOnly:
    def __init__(self, values):
        self.values = values

    def __getitem__(self, key):
        return self.values[key]

    def __iter__(self):
        raise AssertionError("explicit glyph lookup must not scan the font")


class ListCollection(list):
    def __getitem__(self, key):
        if isinstance(key, str):
            for value in self:
                if getattr(value, "layerId", None) == key or getattr(value, "id", None) == key:
                    return value
            raise KeyError(key)
        return super().__getitem__(key)


class UndoManager:
    def __init__(self):
        self.events = []

    def beginUndoGrouping(self):
        self.events.append("begin")

    def setActionName_(self, name):
        self.events.append(name)

    def endUndoGrouping(self):
        self.events.append("end")


class PositionNode:
    type = 'line'

    def __init__(self, x=0, y=0): self.position = (x, y)

    @property
    def position(self): return self._position

    @position.setter
    def position(self, point): self._position = SimpleNamespace(x=point[0], y=point[1])


class Layer:
    def __init__(self):
        self.layerId = "M1"
        self.id = "M1"
        self.name = "Regular"
        self.width = 600
        self.paths = [
            SimpleNamespace(
                nodes=[PositionNode()]
            )
        ]
        self.components = []
        self.anchors = []
        self.events = []

    def beginChanges(self):
        self.events.append("begin")

    def endChanges(self):
        self.events.append("end")

    def applyTransform(self, transform):
        node = self.paths[0].nodes[0]
        node.position.x += transform[4]
        node.position.y += transform[5]


class FractionalLayer(Layer):
    def __init__(self):
        self._temporarily_disable_rounding = False
        self._width = 0.0
        super().__init__()
        self._width = 727.3

    @property
    def temporarilyDisableRounding(self):
        return self._temporarily_disable_rounding

    def setTemporarilyDisableRounding_(self, value):
        self._temporarily_disable_rounding = bool(value)

    @property
    def width(self):
        return self._width

    @width.setter
    def width(self, value):
        self._width = float(value) if self._temporarily_disable_rounding else round(float(value))


def adapter(layer=None) -> tuple[GlyphsAdapter, Layer]:
    layer = layer or Layer()
    glyph = SimpleNamespace(
        name="A",
        unicode="0041",
        category="Letter",
        subCategory="Uppercase",
        export=True,
        layers=ListCollection([layer]),
    )
    undo = UndoManager()
    document = SimpleNamespace(
        changeCount=lambda: 2,
        hasUnautosavedChanges=lambda: False,
        undoManager=lambda: undo,
    )
    font = SimpleNamespace(
        familyName="Disposable",
        filepath="/tmp/Disposable.glyphs",
        parent=document,
        glyphs=IndexedOnly({"A": glyph}),
        masters=ListCollection([]),
        currentTab=None,
    )
    return GlyphsAdapter(SimpleNamespace(fonts=[font])), layer


def test_explicit_read_does_not_scan_all_glyphs() -> None:
    value, _layer = adapter()
    document = value.list_documents()[0]
    result = value.read_entities(
        document["id"], [{"kind": "glyph", "id": "A"}], ["name", "unicode"]
    )
    assert result[0]["values"] == {"name": "A", "unicode": "0041"}


def test_document_id_uses_stable_native_identity_across_python_proxies(monkeypatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "objc",
        SimpleNamespace(pyobjc_id=lambda value: value.native_identity),
    )
    value = GlyphsAdapter(SimpleNamespace(fonts=[]))
    first = SimpleNamespace(native_identity=42)
    second = SimpleNamespace(native_identity=42)

    assert value._id(first) == value._id(second)


def test_set_and_translate_have_exact_target_readback() -> None:
    value, layer = adapter()
    document_id = value.list_documents()[0]["id"]
    set_change = {
        "kind": "set",
        "glyph": "A",
        "layer": "M1",
        "field": "width",
        "before": 600,
        "after": 608,
    }
    assert value.current_value(document_id, set_change) == 600
    value.apply_change(document_id, set_change)
    assert value.current_value(document_id, set_change) == 608
    assert layer.events == []

    before = value._outline_hash(layer)
    translate = {
        "kind": "translate",
        "glyph": "A",
        "layer": "M1",
        "dx": 3,
        "dy": 4,
        "beforeHash": before,
        "afterHash": "unused",
    }
    value.apply_change(document_id, translate)
    assert value._outline_hash(layer) != before
    value.apply_change(document_id, translate, reverse=True)
    assert value._outline_hash(layer) == before
    assert layer.events == ["begin", "end", "begin", "end"]


def test_operation_cache_and_rounding_guard_preserve_fractional_width() -> None:
    layer = FractionalLayer()
    value, _ = adapter(layer)
    document_id = value.list_documents()[0]["id"]
    change = {
        "kind": "set",
        "glyph": "A",
        "layer": "M1",
        "field": "width",
        "before": 727.3,
        "after": 735.3,
    }

    value.begin_undo(document_id)
    assert value.current_value(document_id, change) == 727.3
    value.apply_change(document_id, change)
    assert value.current_value(document_id, change) == 735.3
    value.apply_change(document_id, change, reverse=True)
    assert value.current_value(document_id, change) == 727.3
    assert layer.temporarilyDisableRounding is True
    value.end_undo(document_id, "Glyphs MCP: spacing")

    assert layer.width == 727.3
    assert layer.temporarilyDisableRounding is False


def test_native_undo_group_is_named_once() -> None:
    value, _layer = adapter()
    document_id = value.list_documents()[0]["id"]
    document = value._font(document_id).parent
    value.begin_undo(document_id)
    value.end_undo(document_id, "Glyphs MCP: spacing")
    assert document.undoManager().events == ["begin", "Glyphs MCP: spacing", "end"]


def test_native_integer_boolean_rounding_flag_preserves_fractional_values():
    class IntegerBooleanLayer(FractionalLayer):
        @property
        def temporarilyDisableRounding(self):
            return int(self._temporarily_disable_rounding)

    layer = IntegerBooleanLayer()
    value, _ = adapter(layer)
    document_id = value.list_documents()[0]["id"]
    change = dict(kind="set", glyph="A", layer="M1", field="width", before=727.3, after=735.3)
    # A standalone exact write and an operation scope use the same native flag guard.
    value._write_exact(layer, change, change["after"])
    assert layer.width == 735.3 and layer.temporarilyDisableRounding == 0
    value.begin_undo(document_id)
    value.apply_change(document_id, change, reverse=True)
    assert layer.width == 727.3 and layer.temporarilyDisableRounding == 1
    value.end_undo(document_id, "Fractional restore")
    assert layer.temporarilyDisableRounding == 0


def test_native_undo_and_redo_preserve_fractional_width_after_scope_closes() -> None:
    class NativeUndo(UndoManager):
        def __init__(self):
            super().__init__()
            self.actions = []
            self.enabled = True

        def disableUndoRegistration(self):
            self.enabled = False

        def enableUndoRegistration(self):
            self.enabled = True

        def registerUndoWithTarget_handler_(self, target, handler):
            assert self.enabled
            self.actions.append((target, handler))

        def undo(self):
            target, handler = self.actions.pop()
            handler(target)

    value, layer = adapter(FractionalLayer())
    document_id = value.list_documents()[0]["id"]
    manager = NativeUndo()
    value._font(document_id).parent.undoManager = lambda: manager
    change = {"kind": "set", "glyph": "A", "layer": "M1", "field": "width",
              "before": 727.3, "after": 735.3}
    value.begin_undo(document_id)
    value.apply_change(document_id, change)
    value.end_undo(document_id, "spacing")
    assert layer.width == 735.3 and not layer.temporarilyDisableRounding
    manager.undo()
    assert layer.width == 727.3 and not layer.temporarilyDisableRounding
    manager.undo()  # The inverse registered by Undo is native Redo.
    assert layer.width == 735.3 and not layer.temporarilyDisableRounding
    assert manager.enabled and len(manager.actions) == 1


def test_document_edited_state_is_authoritative() -> None:
    value, _layer = adapter()
    document_id = value.list_documents()[0]["id"]
    document = value._font(document_id).parent
    document.isDocumentEdited = lambda: True
    document.hasUnautosavedChanges = lambda: False

    assert value.document_state(document_id)["dirty"] is True


def test_clean_ui_updates_do_not_invalidate_prepared_jobs():
    document = SimpleNamespace(isDocumentEdited=False)
    font = SimpleNamespace(parent=document, filepath='/tmp/Test.glyphs', familyName='Test')
    adapter = GlyphsAdapter(SimpleNamespace(fonts=[font]))
    original = adapter.list_documents()[0]['generation']
    for _ in range(10):
        adapter.note_change()
    assert adapter.list_documents()[0]['generation'] == original
    document.isDocumentEdited = True
    adapter.note_change()
    assert adapter.list_documents()[0]['generation'] > original


def test_glyph_undo_managers_own_layer_edits_and_are_grouped_once():
    from glyphs_mcp_bridge.native_undo import NativeUndoScope
    document, first, second = UndoManager(), UndoManager(), UndoManager()
    scope = NativeUndoScope(document)
    a1 = SimpleNamespace(undoManager=lambda: first)
    a2 = SimpleNamespace(undoManager=lambda: first)
    b1 = SimpleNamespace(undoManager=lambda: second)
    assert scope.manager_for(a1) is first
    assert scope.manager_for(a2) is first
    assert scope.manager_for(b1) is second
    scope.finish('Glyphs MCP: spacing')
    for manager in (document,first,second):
        assert manager.events == ['begin','Glyphs MCP: spacing','end']


def test_native_undo_callback_does_not_retain_its_manager():
    import gc
    import weakref
    from glyphs_mcp_bridge.native_undo import write_scalar
    callbacks=[]
    class Manager:
        def disableUndoRegistration(self): pass
        def enableUndoRegistration(self): pass
        def registerUndoWithTarget_handler_(self,target,callback): callbacks.append(callback)
    manager=Manager()
    reference=weakref.ref(manager)
    layer=SimpleNamespace(width=727.3)
    write_scalar(manager,layer,'width',735.3,setattr)
    del manager
    gc.collect()
    assert callbacks and reference() is None


def test_fractional_translation_keeps_rounding_disabled_through_native_end_changes():
    class NativeLikeLayer(FractionalLayer):
        def endChanges(self):
            node = self.paths[0].nodes[0]
            if not self.temporarilyDisableRounding:
                node.position.x = round(node.position.x)
            self.events.append('end')

        def setNeedUpdateShapes(self):
            self.events.append('refresh-shapes')

    layer = NativeLikeLayer()
    value, _ = adapter(layer)
    document = value.list_documents()[0]['id']
    before = value._outline_hash(layer)
    change = {'kind':'translate','glyph':'A','layer':'M1','dx':0.375,'dy':0.125}
    value.begin_undo(document)
    value.apply_change(document,change)
    value.end_undo(document,'Fractional translation')
    assert layer.paths[0].nodes[0].position.x == 0.375
    assert layer.paths[0].nodes[0].position.y == 0.125
    assert not layer.temporarilyDisableRounding
    assert layer.events == ['begin','refresh-shapes','end']
    value.begin_undo(document)
    value.apply_change(document,change,reverse=True)
    value.end_undo(document,'Discard translation')
    assert value._outline_hash(layer) == before
    assert not layer.temporarilyDisableRounding
