"""Bounded GlyphsApp access used only from the application main thread."""

from __future__ import annotations

from typing import Any, Mapping
from uuid import uuid4

from glyphs_mcp_protocol import outline_hash
from glyphs_mcp_protocol.reads import MASTER_PAGE_LIMIT

from .core import BridgeError
from .native_undo import NativeUndoScope, write_value
from . import context, coordinates, kerning, selection, start_node


_MISSING = object()


def _call(value: Any) -> Any:
    return value() if callable(value) else value


def _value(owner: Any, name: str, default: Any = None) -> Any:
    try:
        result = getattr(owner, name)
        return _call(result)
    except Exception:
        return default


def _point(value: Any) -> tuple[float, float]:
    x = _value(value, "x", None)
    y = _value(value, "y", None)
    if x is None or y is None:
        origin = _value(value, "origin", None)
        x = _value(origin, "x", 0)
        y = _value(origin, "y", 0)
    return float(x or 0), float(y or 0)


def _rect(value: Any) -> dict[str, float] | None:
    if value is None:
        return None
    origin = _value(value, "origin", None)
    size = _value(value, "size", None)
    return {
        "x": float(_value(origin, "x", 0) or 0),
        "y": float(_value(origin, "y", 0) or 0),
        "width": float(_value(size, "width", 0) or 0),
        "height": float(_value(size, "height", 0) or 0),
    }


class GlyphsAdapter:
    """Thin native adapter; no method intentionally walks a complete font."""

    GLYPH_FIELDS = frozenset({"name", "unicode", "category", "subCategory", "export"})
    LAYER_FIELDS = frozenset({"id", "name", "width", "vertWidth", "vertOrigin",
                              "leftMetricsKey", "rightMetricsKey", "widthMetricsKey", "bounds", "outlineHash"})
    MASTER_FIELDS = frozenset({"id", "name"})
    SELECTION_COUNTS = selection.COUNT_FIELDS
    SELECTION_FIELDS = frozenset({"glyph", "layer", "nodes", *SELECTION_COUNTS})

    def __init__(self, glyphs: Any) -> None:
        self.glyphs = glyphs
        self._ids: dict[tuple[str, int], tuple[Any, str]] = {}
        self._generations: dict[str, int] = {}
        self._undo_managers: dict[str, Any] = {}
        self._operation_fonts: dict[str, Any] = {}
        self._operation_layers: dict[str, dict[tuple[str, str], Any]] = {}
        self._rounding_states: dict[str, dict[int, tuple[Any, bool]]] = {}

    def note_change(self, _sender: Any = None) -> None:
        for document in self.list_documents():
            # UPDATEINTERFACE also fires for selection, zoom, and redraws.
            # A clean document must remain usable while its job is prepared.
            if document["dirty"] is not True:
                continue
            doc_id = document["id"]
            self._generations[doc_id] = self._generations.get(doc_id, 0) + 1

    def _fonts(self) -> list[Any]:
        values = _value(self.glyphs, "fonts", []) or []
        fonts = list(values)
        live = {self._native_identity(font) for font in fonts}
        for key in self._ids.keys() - live:
            _font, document_id = self._ids.pop(key)
            self._generations.pop(document_id, None)
        return fonts

    @staticmethod
    def _native_identity(font: Any) -> tuple[str, int]:
        """Identify the Objective-C object, not its short-lived Python proxy."""
        try:
            import objc  # type: ignore[import-not-found]

            return "objc", int(objc.pyobjc_id(font))
        except Exception:
            return "python", id(font)

    def _id(self, font: Any) -> str:
        key = self._native_identity(font)
        if key not in self._ids:
            # Retain the native object so its address cannot be recycled while
            # this binding exists. _fonts retires closed bindings; no data cache.
            self._ids[key] = (font, "doc_" + uuid4().hex)
        return self._ids[key][1]

    def _font(self, document_id: str) -> Any:
        for font in self._fonts():
            if self._id(font) == str(document_id):
                return font
        raise BridgeError("document_not_found", "the Glyphs document is no longer open")

    @classmethod
    def _dirty(cls, font: Any) -> bool | None:
        document = _value(font, "parent", None)
        for name in ("isDocumentEdited", "hasUnautosavedChanges"):
            value = _value(document, name, None)
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return bool(value)
        return None

    def _generation(self, font: Any) -> int:
        document = _value(font, "parent", None)
        native = _value(document, "changeCount", None)
        try:
            return int(native)
        except (TypeError, ValueError):
            return self._generations.get(self._id(font), 0)

    def list_documents(self) -> list[dict[str, Any]]:
        current = context.current_font(self.glyphs)
        return [dict(self._document_state(font),
                     isCurrent=context.is_current(font, current, self._native_identity),
                     familyName=str(_value(font, "familyName", "Untitled") or "Untitled"))
                for font in self._fonts()]

    def document_state(self, document_id: str) -> dict[str, Any]:
        return self._document_state(self._font(document_id))

    def _document_state(self, font: Any) -> dict[str, Any]:
        path = _value(font, "filepath", None)
        return {"id": self._id(font), "path": str(path) if path else None,
                "dirty": self._dirty(font), "generation": self._generation(font)}

    @staticmethod
    def _lookup(collection: Any, identity: str) -> Any:
        try:
            found = collection[identity]
            if found is not None:
                return found
        except Exception:
            pass
        for item in list(collection or []):
            if str(_value(item, "id", "")) == identity or str(
                _value(item, "layerId", "")
            ) == identity or str(_value(item, "name", "")) == identity:
                return item
        return None

    def _glyph(self, font: Any, name: str) -> Any:
        glyphs = _value(font, "glyphs", [])
        try:
            glyph = glyphs[str(name)]
        except Exception:
            glyph = None
        if glyph is None:
            raise BridgeError("target_not_found", f"glyph {name!r} is unavailable")
        return glyph

    def _layer(self, font: Any, glyph_name: str, layer_id: str) -> Any:
        glyph = self._glyph(font, glyph_name)
        layer = self._lookup(_value(glyph, "layers", []), str(layer_id))
        if layer is None:
            raise BridgeError(
                "target_not_found", f"layer {layer_id!r} in glyph {glyph_name!r} is unavailable"
            )
        return layer

    def _operation_font(self, document_id: str) -> Any:
        return self._operation_fonts.get(document_id) or self._font(document_id)

    def _target_layer(
        self, document_id: str, glyph_name: str, layer_id: str
    ) -> Any:
        cache = self._operation_layers.get(document_id)
        key = (str(glyph_name), str(layer_id))
        if cache is not None and key in cache:
            return cache[key]
        layer = self._layer(self._operation_font(document_id), *key)
        if cache is not None:
            cache[key] = layer
        return layer

    @staticmethod
    def _rounding_value(layer: Any) -> Any:
        try:
            value = getattr(layer, "temporarilyDisableRounding")
            return _call(value)
        except Exception:
            return _MISSING

    @classmethod
    def _set_rounding(cls, layer: Any, value: bool) -> bool:
        setter = getattr(layer, "setTemporarilyDisableRounding_", None)
        if callable(setter):
            try:
                setter(bool(value))
            except Exception:
                pass
            else:
                return cls._rounding_value(layer) == bool(value)
        try:
            setattr(layer, "temporarilyDisableRounding", bool(value))
        except Exception:
            return False
        return cls._rounding_value(layer) == bool(value)

    @staticmethod
    def _requires_fractional_precision(change: Mapping[str, Any]) -> bool:
        if change.get("kind") == "coordinates":
            return True
        for name in ("before", "after"):
            value = change.get(name)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if not float(value).is_integer():
                    return True
        return False

    def _protect_write(self, document_id: str, layer: Any, change: Mapping[str, Any]) -> None:
        """Disable native rounding once per target for the whole operation.

        The flag is transient host state. Keeping it active until the final
        read-back avoids both fractional-width loss and thousands of repeated
        setter calls during a large time-sliced job.
        """

        states = self._rounding_states.get(document_id)
        identity = id(layer)
        if states is not None and identity in states:
            return None
        original = self._rounding_value(layer)
        if original is _MISSING:
            if self._requires_fractional_precision(change):
                raise BridgeError(
                    "unsupported_change",
                    "this Glyphs layer cannot preserve fractional scalar values",
                )
            return None
        if states is not None:
            states[identity] = (layer, bool(original))
            if not bool(original) and not self._set_rounding(layer, True):
                raise BridgeError("native_write_failed", "Glyphs rejected temporary rounding suppression")

    def _clear_operation(self, document_id: str) -> None:
        states = self._rounding_states.pop(document_id, {})
        failures = []
        for layer, original in reversed(tuple(states.values())):
            if not self._set_rounding(layer, original):
                failures.append(str(_value(layer, "layerId", "unknown")))
        self._operation_layers.pop(document_id, None)
        self._operation_fonts.pop(document_id, None)
        if failures:
            raise BridgeError("native_write_failed", "Could not restore rounding flags", details={"layers": failures})

    def read_entities(self, document_id: str, entities: list[dict[str, Any]], fields: list[str]) -> list[dict[str, Any]]:
        font = self._font(document_id)
        if any(isinstance(item, Mapping) and item.get("kind") == "context" for item in entities):
            return context.read(font, entities, fields, self._native_identity)
        if "nodes" in fields and any(isinstance(item, Mapping) and item.get("kind") == "selection"
                                     for item in entities) and len(entities) != 1:
            raise BridgeError("invalid_request", "selection node details require one selection entity only")
        if any(isinstance(request, Mapping) and request.get("kind") == "masters" for request in entities):
            if len(entities) != 1:
                raise BridgeError("invalid_request", "a master page must be the only entity selector")
            request = entities[0]
            return [{"entity": dict(request), "values": self._master_page(font, document_id, request, fields)}]
        result = []
        for request in entities:
            if not isinstance(request, Mapping):
                raise BridgeError("invalid_request", "entity selectors must be objects")
            kind = str(request.get("kind") or "")
            if kind == "kerning" and fields == ["value"]:
                try:
                    result.append({"entity": dict(request), "values": {"value": kerning.read(font, request)}})
                except (KeyError, ValueError) as error:
                    raise BridgeError("invalid_request", str(error)) from error
                continue
            allowed = (
                self.GLYPH_FIELDS if kind == "glyph" else self.LAYER_FIELDS
                if kind == "layer" else self.MASTER_FIELDS
                if kind == "master" else self.SELECTION_FIELDS
                if kind == "selection" else frozenset()
            )
            unsupported = sorted(set(fields) - allowed)
            if not allowed or unsupported:
                raise BridgeError(
                    "unsupported_read",
                    "unsupported fields for {}: {}".format(kind or "entity", ", ".join(unsupported)),
                )
            owner = self._entity(font, kind, request)
            values = (self._selection_values(owner, request, fields) if kind == "selection" else
                      {field: self._read_field(owner, field, kind) for field in fields})
            result.append({"entity": dict(request), "values": values})
        return result

    @classmethod
    def _selection_values(cls, layer, request, fields):
        return selection.read(layer, request, fields, cls._native_identity)

    def _master_page(self, font: Any, document_id: str, request: Mapping[str, Any],
                     fields: list[str]) -> dict[str, Any]:
        if set(request) - {"kind", "limit", "cursor"}:
            raise BridgeError("invalid_request", "master pages accept only kind, limit and cursor")
        if not fields or set(fields) - self.MASTER_FIELDS:
            raise BridgeError("unsupported_read", "master pages support only id and name fields")
        limit = request.get("limit", MASTER_PAGE_LIMIT)
        if type(limit) is not int or not 1 <= limit <= MASTER_PAGE_LIMIT:
            raise BridgeError("invalid_request", "master page limit must be an integer from 1 to 100")
        masters = _value(font, "masters", None)
        if masters is None:
            raise BridgeError("unsupported_read", "native master collection is unavailable")
        total = len(masters)
        cursor = request.get("cursor")
        offset = 0
        if cursor is not None:
            if (not isinstance(cursor, Mapping) or set(cursor) != {"documentId", "offset", "total", "afterId"}
                    or type(cursor.get("offset")) is not int or cursor["offset"] < 1
                    or type(cursor.get("total")) is not int or cursor["total"] < 1
                    or not isinstance(cursor.get("afterId"), str) or not cursor["afterId"]
                    or not isinstance(cursor.get("documentId"), str)):
                raise BridgeError("invalid_request", "use the nextCursor returned by the previous master page")
            offset = cursor["offset"]
            if (cursor["documentId"] != document_id or cursor["total"] != total or offset >= total
                    or _value(masters[offset - 1], "id") != cursor["afterId"]):
                raise BridgeError("stale_master_cursor", "master page boundary changed; restart discovery without a cursor")
        # Native indexed access visits this page and at most one boundary master.
        # A cursor detects count/boundary changes, not an atomic multi-call snapshot.
        end = min(total, offset + limit)
        items = []
        for index in range(offset, end):
            master = masters[index]
            items.append({field: self._read_field(master, field, "master") for field in fields})
        next_cursor = None if end == total else {
            "documentId": document_id, "offset": end, "total": total,
            "afterId": _value(masters[end - 1], "id"),
        }
        return {"items": items, "total": total, "complete": end == total, "nextCursor": next_cursor}

    def _entity(self, font: Any, kind: str, request: Mapping[str, Any]) -> Any:
        if kind == "glyph":
            return self._glyph(font, str(request.get("id") or ""))
        if kind == "layer":
            name, identity = request.get("glyph"), request.get("id")
            if not isinstance(name, str) or not name or not isinstance(identity, str) or not identity:
                raise BridgeError("invalid_request", "layer selectors require a glyph name and nonempty exact native id")
            glyph = self._glyph(font, name)
            try:
                layer = glyph.layers[identity]
            except (KeyError, IndexError, TypeError):
                layer = None
            if layer is None or _value(layer, "layerId") != identity:
                raise BridgeError("target_not_found", f"layer {identity!r} in glyph {name!r} is unavailable")
            return layer
        if kind == "master":
            identity = request.get("id")
            if not isinstance(identity, str) or not identity:
                raise BridgeError("invalid_request", "master selectors require a nonempty exact native id")
            try:
                master = font.masters[identity]
            except (KeyError, IndexError, TypeError):
                master = None
            if master is None or _value(master, "id") != identity:
                raise BridgeError("target_not_found", "master is unavailable")
            return master
        if kind == "selection":
            return _value(_value(font, "currentTab", None), "activeLayer", None)
        raise BridgeError("unsupported_read", f"unsupported entity kind: {kind}")

    @classmethod
    def _read_field(cls, owner: Any, field: str, kind: str) -> Any:
        if kind == "layer" and field == "id":
            return _value(owner, "layerId", None)
        if field == "outlineHash":
            return cls._outline_hash(owner)
        if kind == "selection":
            return cls._selection_values(owner, {"kind": "selection"}, [field])[field]
        value = _value(owner, field, None)
        return _rect(value) if field == "bounds" else value

    def current_value(
        self, document_id: str, change: Mapping[str, Any], *, reverse: bool = False
    ) -> Any:
        if change["kind"] == "kerning":
            return kerning.read(self._operation_font(document_id), change)
        layer = self._target_layer(document_id, change["glyph"], change["layer"])
        if change["kind"] == "set":
            return _value(layer, change["field"], None)
        if change["kind"] == "coordinates":
            return coordinates.read(layer, change)
        return self._outline_hash(layer)

    def capture_state(self, document_id, change):
        return coordinates.read_state(self._target_layer(document_id, change["glyph"], change["layer"]), change)

    def apply_change(self, document_id, change, *, reverse=False):
        if change["kind"] == "kerning":
            kerning.write_undo(self._operation_font(document_id), self._undo_managers.get(document_id), change, reverse=reverse)
            return
        layer = self._target_layer(document_id, change["glyph"], change["layer"])
        scope = self._undo_managers.get(document_id)
        manager = scope.manager_for(layer) if scope is not None else None
        kind = change["kind"]
        key = {k: v for k, v in change.items()
               if k not in ("nativeBefore", "nativeAfter", "before", "after", "beforeHash", "afterHash")}
        if kind in ("set", "coordinates"):
            wanted = change["before"] if reverse else change["after"]
        elif ("nativeBefore" if reverse else "nativeAfter") in change:
            wanted = change["nativeBefore" if reverse else "nativeAfter"]
        elif kind == "start_node":
            wanted = lambda owner: start_node.apply(owner, key, reverse=reverse)
        else:
            factor = -1 if reverse else 1
            wanted = [(x + factor * key["dx"], y + factor * key["dy"])
                      for x, y in coordinates.read_state(layer, key)]
        precision = change if kind != "translate" else {"before": key["dx"], "after": key["dy"]}
        self._protect_write(document_id, layer, precision)
        write_value(manager, layer, key, wanted, coordinates.read_state, self._write_exact)

    @classmethod
    def _write_exact(cls, layer, change, value):
        original = cls._rounding_value(layer)
        protected = original is not _MISSING and not bool(original)
        begin = getattr(layer, "beginChanges", None) if change["kind"] != "set" else None
        end = getattr(layer, "endChanges", None) if callable(begin) else None
        try:
            if protected and not cls._set_rounding(layer, True):
                raise BridgeError("native_write_failed", "Glyphs rejected exact target write")
            try:
                if callable(begin):
                    begin()
                if callable(value):
                    value(layer)
                else:
                    coordinates.write_state(layer, change, value)
                refresh = getattr(layer, "setNeedUpdateShapes", None) if change["kind"] != "set" else None
                if callable(refresh):
                    refresh()
            finally:
                if callable(end):
                    end()
            if not callable(value) and coordinates.read_state(layer, change) != value:
                raise BridgeError("readback_failed", "Glyphs did not retain exact target values")
        finally:
            if protected and not cls._set_rounding(layer, False):
                raise BridgeError("native_write_failed", "Could not restore rounding flag")

    @staticmethod
    def _outline_hash(layer: Any) -> str:
        points: list[tuple[float, float, str]] = []
        for path_index, path in enumerate(list(_value(layer, "paths", []) or [])):
            for node_index, node in enumerate(list(_value(path, "nodes", []) or [])):
                x, y = _point(_value(node, "position", node))
                node_type = str(_value(node, "type", "node"))
                points.append((x, y, f"path:{path_index}:{node_index}:{node_type}"))
        for index, component in enumerate(list(_value(layer, "components", []) or [])):
            x, y = _point(_value(component, "position", component))
            name = str(_value(component, "componentName", "component"))
            points.append((x, y, f"component:{index}:{name}"))
        for index, anchor in enumerate(list(_value(layer, "anchors", []) or [])):
            x, y = _point(_value(anchor, "position", anchor))
            name = str(_value(anchor, "name", "anchor"))
            points.append((x, y, f"anchor:{index}:{name}"))
        return outline_hash(points)

    def begin_undo(self, document_id: str) -> None:
        font = self._font(document_id)
        self._operation_fonts[document_id] = font
        self._operation_layers[document_id] = {}
        self._rounding_states[document_id] = {}
        document = _value(font, "parent", None)
        manager = _value(document, "undoManager", None)
        try:
            self._undo_managers[document_id] = NativeUndoScope(manager)
        except Exception:
            self._clear_operation(document_id)
            raise

    def end_undo(self, document_id: str, name: str) -> None:
        manager = self._undo_managers.pop(document_id, None)
        try:
            if manager is None:
                return
            manager.finish(name)
        finally:
            self._clear_operation(document_id)
