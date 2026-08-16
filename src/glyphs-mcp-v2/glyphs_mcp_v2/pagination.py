"""Bounded, source-fingerprint-bound pagination for v2 results."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from typing import Any, Generic, Optional, Sequence, Tuple, TypeVar


T = TypeVar("T")
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 500
MAX_PAGE_BYTES = 40 * 1024
_CURSOR_SECRET = os.urandom(32)


class CursorError(ValueError):
    """A malformed, stale, or source-mismatched result cursor."""


def _encode_cursor(offset: int, fingerprint: str) -> str:
    payload = json.dumps(
        {"offset": offset, "fingerprint": fingerprint},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    signature = hmac.new(_CURSOR_SECRET, payload, hashlib.sha256).digest()[:16]
    return base64.urlsafe_b64encode(signature + payload).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str, fingerprint: str) -> int:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        signature, payload = raw[:16], raw[16:]
        expected = hmac.new(_CURSOR_SECRET, payload, hashlib.sha256).digest()[:16]
        if not hmac.compare_digest(signature, expected):
            raise CursorError("cursor signature is invalid")
        value = json.loads(payload.decode("utf-8"))
        if value.get("fingerprint") != fingerprint:
            raise CursorError("cursor source fingerprint is stale")
        offset = int(value["offset"])
        if offset < 0:
            raise CursorError("cursor offset is invalid")
        return offset
    except CursorError:
        raise
    except Exception as exc:
        raise CursorError("cursor is malformed") from exc


@dataclass(frozen=True)
class PageInfo:
    page_size: int
    total_items: int
    returned_items: int
    offset: int
    next_cursor: Optional[str]
    source_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "pageSize": self.page_size,
            "totalItems": self.total_items,
            "returnedItems": self.returned_items,
            "offset": self.offset,
            "nextCursor": self.next_cursor,
            "sourceFingerprint": self.source_fingerprint,
        }


@dataclass(frozen=True)
class Page(Generic[T]):
    items: Tuple[T, ...]
    page: PageInfo


def paginate(
    items: Sequence[T],
    *,
    source_fingerprint: str,
    page_size: int = DEFAULT_PAGE_SIZE,
    cursor: Optional[str] = None,
    max_page_bytes: int = MAX_PAGE_BYTES,
) -> Page[T]:
    if not source_fingerprint:
        raise ValueError("source_fingerprint is required")
    requested = int(page_size)
    bounded = max(1, min(requested, MAX_PAGE_SIZE))
    offset = _decode_cursor(cursor, source_fingerprint) if cursor else 0
    total = len(items)
    if offset > total:
        raise CursorError("cursor offset is outside the result")
    selected_values: list[T] = []
    encoded_bytes = 2
    for item in items[offset : offset + bounded]:
        item_bytes = len(
            json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        separator_bytes = 1 if selected_values else 0
        if item_bytes + 2 > max_page_bytes and not selected_values:
            raise ValueError("one result item exceeds the bounded response-page size")
        if encoded_bytes + separator_bytes + item_bytes > max_page_bytes:
            break
        selected_values.append(item)
        encoded_bytes += separator_bytes + item_bytes
    selected = tuple(selected_values)
    next_offset = offset + len(selected)
    next_cursor = _encode_cursor(next_offset, source_fingerprint) if next_offset < total else None
    return Page(
        items=selected,
        page=PageInfo(
            page_size=bounded,
            total_items=total,
            returned_items=len(selected),
            offset=offset,
            next_cursor=next_cursor,
            source_fingerprint=source_fingerprint,
        ),
    )


__all__ = [
    "CursorError",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "MAX_PAGE_BYTES",
    "Page",
    "PageInfo",
    "paginate",
]
