"""Bounded exact export-instance discovery."""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping
from typing import Any

from glyphs_mcp_protocol.reads import INSTANCE_PAGE_LIMIT

from .context import value
from .core import BridgeError


EXACT_FIELDS = frozenset({"id", "name", "type", "exports", "outlineFormat", "axisValues"})


def _invalid() -> BridgeError:
    return BridgeError("invalid_request", "use the unmodified nextCursor from the previous instance page")


def _decode(cursor: Any) -> dict[str, Any]:
    if not isinstance(cursor, str) or not cursor.startswith("i1.") or len(cursor) > 4096:
        raise _invalid()
    try:
        data = json.loads(base64.b64decode(cursor[3:], altchars=b"-_", validate=True))
        if (
            not isinstance(data, dict)
            or set(data) != {"document", "offset", "total", "generation", "dirty", "after"}
            or not isinstance(data["document"], str)
            or type(data["offset"]) is not int
            or data["offset"] < 1
            or type(data["total"]) is not int
            or data["total"] <= data["offset"]
            or type(data["generation"]) is not int
            or data["dirty"] is not None and type(data["dirty"]) is not bool
            or not isinstance(data["after"], str)
            or not data["after"]
        ):
            raise _invalid()
        return data
    except (ValueError, TypeError, binascii.Error, RecursionError) as exc:
        raise _invalid() from exc


def instance_id(instance: Any) -> str:
    result = value(instance, "id", None)
    if not isinstance(result, str) or not result:
        raise BridgeError("unsupported_read", "native instance ID unavailable")
    return result

def _instance_type(instance: Any) -> str:
    result = value(instance, "type", None)
    if result in (1, "variable", "variableTT", "variableCFF"):
        return "variable"
    if result in (0, "single", "static"):
        return "static"
    raise BridgeError("unsupported_read", "native instance type unavailable")


def _outline_format(instance: Any) -> str | None:
    result = value(instance, "outlineFormat", None)
    if result in (0, "CFF", "OTF", "otf", "variableCFF"):
        return "otf"
    if result in (1, "TT", "TTF", "ttf", "variableTT"):
        return "ttf"
    return None


def _exports(instance: Any) -> bool | None:
    result = value(instance, "exports", value(instance, "active", None))
    if type(result) is bool:
        return result
    if type(result) is int and result in (0, 1):
        return bool(result)
    return None


def find(font: Any, identity: str) -> Any:
    if not isinstance(identity, str) or not identity:
        raise BridgeError("invalid_request", "instance selectors require a nonempty exact id")
    for instance in list(value(font, "instances", []) or []):
        if instance_id(instance) == identity:
            return instance
    raise BridgeError("target_not_found", "instance is unavailable")


def _field(instance: Any, name: str) -> Any:
    if name == "id":
        return instance_id(instance)
    if name == "type":
        return _instance_type(instance)
    if name == "outlineFormat":
        return _outline_format(instance)
    if name == "exports":
        return _exports(instance)
    if name == "axisValues":
        raw = value(instance, "axes", []) or []
        try:
            values = list(raw)
        except Exception as exc:
            raise BridgeError("unsupported_read", "native instance axis values unavailable") from exc
        if len(values) > 32:
            raise BridgeError("unsupported_read", "native instance has more than 32 axis values")
        return [float(item) for item in values]
    result = value(instance, name, None)
    return result if result is None or isinstance(result, (str, int, float, bool)) else str(result)


def _summary(instance: Any) -> dict[str, Any]:
    return {name: _field(instance, name) for name in ("id", "name", "type", "exports", "outlineFormat")}


def _page(adapter: Any, font: Any, document_id: str, request: Mapping[str, Any], fields: list[str]):
    if set(request) - {"kind", "limit", "cursor"}:
        raise BridgeError("invalid_request", "instance pages accept only kind, limit and cursor")
    if fields != ["items"]:
        raise BridgeError("unsupported_read", "instance pages support only the items field")
    limit = request.get("limit", INSTANCE_PAGE_LIMIT)
    if type(limit) is not int or not 1 <= limit <= INSTANCE_PAGE_LIMIT:
        raise BridgeError("invalid_request", "instance page limit must be an integer from 1 to 100")
    instances = value(font, "instances", None)
    if instances is None:
        raise BridgeError("unsupported_read", "native instance collection unavailable")
    cursor = _decode(request["cursor"]) if "cursor" in request else None
    try:
        total = len(instances)
    except Exception as exc:
        raise BridgeError("unsupported_read", "native instance collection count unavailable") from exc
    generation, dirty = adapter._generation(font), adapter._dirty(font)
    offset = cursor["offset"] if cursor else 0
    if cursor and (
        cursor["document"] != document_id
        or cursor["total"] != total
        or cursor["generation"] != generation
        or cursor["dirty"] != dirty
        or offset >= total
    ):
        raise BridgeError("stale_instance_cursor", "instance collection changed; restart discovery")
    try:
        if cursor and cursor["after"] != instance_id(instances[offset - 1]):
            raise BridgeError("stale_instance_cursor", "instance boundary changed; restart discovery")
        items = [_summary(instances[index]) for index in range(offset, min(total, offset + limit))]
        end = offset + len(items)
        next_cursor = None
        if end < total:
            payload = {
                "document": document_id,
                "offset": end,
                "total": total,
                "generation": generation,
                "dirty": dirty,
                "after": instance_id(instances[end - 1]),
            }
            next_cursor = "i1." + base64.urlsafe_b64encode(
                json.dumps(payload, separators=(",", ":")).encode()
            ).decode()
    except BridgeError:
        raise
    except Exception as exc:
        raise BridgeError("unsupported_read", "native indexed instance evidence unavailable") from exc
    return {"items": items, "total": total, "returned": len(items), "complete": end == total, "nextCursor": next_cursor}


def read(adapter: Any, font: Any, document_id: str, entities: list[Any], fields: list[str]):
    if any(isinstance(item, Mapping) and item.get("kind") == "instances" for item in entities):
        if len(entities) != 1:
            raise BridgeError("invalid_request", "an instance page must be the only entity selector")
        request = entities[0]
        return [{"entity": dict(request), "values": _page(adapter, font, document_id, request, fields)}]
    if not fields or set(fields) - EXACT_FIELDS:
        raise BridgeError("unsupported_read", "unsupported instance fields")
    result = []
    for request in entities:
        if not isinstance(request, Mapping) or request.get("kind") != "instance":
            raise BridgeError("invalid_request", "instance reads cannot mix selector kinds")
        if set(request) != {"kind", "id"}:
            raise BridgeError("invalid_request", "instance selectors require kind and exact id")
        instance = find(font, request.get("id"))
        result.append({
            "entity": dict(request),
            "values": {field: _field(instance, field) for field in dict.fromkeys(fields)},
        })
    return result
