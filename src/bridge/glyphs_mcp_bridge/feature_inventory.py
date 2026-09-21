"""Bounded OpenType feature-block discovery using persistent native IDs."""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping
from typing import Any

from glyphs_mcp_protocol.reads import FEATURE_BLOCK_PAGE_LIMIT

from .context import value
from .core import BridgeError


BLOCK_COLLECTIONS = {
    "prefix": "featurePrefixes",
    "class": "classes",
    "feature": "features",
}
EXACT_FIELDS = frozenset({
    "id", "name", "code", "automatic", "disabled", "canBeAutomated",
    "notes", "labels", "errors", "errorType", "errorTooltip", "filePath",
})


def _invalid() -> BridgeError:
    return BridgeError(
        "invalid_request",
        "use the unmodified nextCursor from the previous feature-block page",
    )


def _decode(cursor: Any) -> dict[str, Any]:
    if not isinstance(cursor, str) or not cursor.startswith("f1.") or len(cursor) > 4096:
        raise _invalid()
    try:
        data = json.loads(base64.b64decode(cursor[3:], altchars=b"-_", validate=True))
        if (
            not isinstance(data, dict)
            or set(data) != {"document", "blockType", "offset", "total", "generation", "dirty", "after"}
            or not isinstance(data["document"], str)
            or data["blockType"] not in BLOCK_COLLECTIONS
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


def block_id(block: Any) -> str:
    identity = value(block, "identifier", None) or value(block, "id", None)
    if not isinstance(identity, str) or not identity:
        raise BridgeError("unsupported_read", "native feature-block identifier unavailable")
    return identity


def _collection(font: Any, block_type: Any) -> Any:
    if block_type not in BLOCK_COLLECTIONS:
        raise BridgeError("invalid_request", "blockType must be prefix, class or feature")
    result = value(font, BLOCK_COLLECTIONS[block_type], None)
    if result is None:
        raise BridgeError("unsupported_read", "native feature-block collection unavailable")
    return result

def find(font: Any, block_type: str, identity: str) -> Any:
    if not isinstance(identity, str) or not identity:
        raise BridgeError("invalid_request", "feature_block requires a nonempty exact id")
    for block in list(_collection(font, block_type) or []):
        if block_id(block) == identity:
            return block
    raise BridgeError("target_not_found", "feature block is unavailable")


def _boolean(block: Any, name: str) -> bool | None:
    result = value(block, name, None)
    if type(result) is bool:
        return result
    if type(result) is int and result in (0, 1):
        return bool(result)
    return None


def _strings(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    try:
        values = list(raw)
    except Exception:
        return [str(raw)]
    return [str(item) for item in values[:100]]


def _field(block: Any, name: str) -> Any:
    if name == "id":
        return block_id(block)
    if name in ("automatic", "disabled", "canBeAutomated"):
        return _boolean(block, name)
    if name in ("labels", "errors"):
        return _strings(value(block, name, []))
    result = value(block, name, None)
    if name == "errorType":
        return result if isinstance(result, (int, str)) and not isinstance(result, bool) else None
    return result if result is None or isinstance(result, (str, int, float, bool)) else str(result)


def _summary(block: Any) -> dict[str, Any]:
    code = value(block, "code", "")
    errors = _strings(value(block, "errors", []))
    return {
        "id": block_id(block),
        "name": str(value(block, "name", "") or ""),
        "automatic": _boolean(block, "automatic"),
        "disabled": _boolean(block, "disabled"),
        "canBeAutomated": _boolean(block, "canBeAutomated"),
        "codeLength": len(code) if isinstance(code, str) else 0,
        "errorCount": len(errors),
    }


def _page(adapter: Any, font: Any, document_id: str, request: Mapping[str, Any], fields: list[str]):
    if set(request) - {"kind", "blockType", "limit", "cursor"}:
        raise BridgeError("invalid_request", "feature-block pages accept only kind, blockType, limit and cursor")
    if fields != ["items"]:
        raise BridgeError("unsupported_read", "feature-block pages support only the items field")
    block_type = request.get("blockType")
    collection = _collection(font, block_type)
    limit = request.get("limit", FEATURE_BLOCK_PAGE_LIMIT)
    if type(limit) is not int or not 1 <= limit <= FEATURE_BLOCK_PAGE_LIMIT:
        raise BridgeError("invalid_request", "feature-block page limit must be an integer from 1 to 100")
    cursor = _decode(request["cursor"]) if "cursor" in request else None
    try:
        total = len(collection)
    except Exception as exc:
        raise BridgeError("unsupported_read", "native feature-block collection count unavailable") from exc
    generation, dirty = adapter._generation(font), adapter._dirty(font)
    offset = cursor["offset"] if cursor else 0
    if cursor and (
        cursor["document"] != document_id
        or cursor["blockType"] != block_type
        or cursor["total"] != total
        or cursor["generation"] != generation
        or cursor["dirty"] != dirty
        or offset >= total
    ):
        raise BridgeError("stale_feature_cursor", "feature-block collection changed; restart discovery")
    try:
        if cursor and cursor["after"] != block_id(collection[offset - 1]):
            raise BridgeError("stale_feature_cursor", "feature-block boundary changed; restart discovery")
        items = [_summary(collection[index]) for index in range(offset, min(total, offset + limit))]
        end = offset + len(items)
        next_cursor = None
        if end < total:
            payload = {
                "document": document_id,
                "blockType": block_type,
                "offset": end,
                "total": total,
                "generation": generation,
                "dirty": dirty,
                "after": block_id(collection[end - 1]),
            }
            next_cursor = "f1." + base64.urlsafe_b64encode(
                json.dumps(payload, separators=(",", ":")).encode()
            ).decode()
    except BridgeError:
        raise
    except Exception as exc:
        raise BridgeError("unsupported_read", "native indexed feature-block evidence unavailable") from exc
    return {"items": items, "total": total, "returned": len(items), "complete": end == total, "nextCursor": next_cursor}


def read(adapter: Any, font: Any, document_id: str, entities: list[Any], fields: list[str]):
    if any(isinstance(item, Mapping) and item.get("kind") == "feature_blocks" for item in entities):
        if len(entities) != 1:
            raise BridgeError("invalid_request", "a feature-block page must be the only entity selector")
        request = entities[0]
        return [{"entity": dict(request), "values": _page(adapter, font, document_id, request, fields)}]
    if not fields or set(fields) - EXACT_FIELDS:
        raise BridgeError("unsupported_read", "unsupported feature_block fields")
    result = []
    for request in entities:
        if not isinstance(request, Mapping) or request.get("kind") != "feature_block":
            raise BridgeError("invalid_request", "feature_block reads cannot mix selector kinds")
        if set(request) != {"kind", "blockType", "id"}:
            raise BridgeError("invalid_request", "feature_block selectors require kind, blockType and exact id")
        block = find(font, request.get("blockType"), request.get("id"))
        result.append({
            "entity": dict(request),
            "values": {field: _field(block, field) for field in dict.fromkeys(fields)},
        })
    return result
