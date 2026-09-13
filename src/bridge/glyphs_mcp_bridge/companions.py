"""Failure-isolated registration for optional independent plug-ins."""

from __future__ import annotations

from threading import RLock
from typing import Any

from glyphs_mcp_protocol import ProtocolError, validate_companion_manifest


class CompanionRegistry:
    def __init__(self) -> None:
        self._items: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def register(self, manifest: Any) -> bool:
        """Register or refresh one companion; never raise into plug-in startup."""

        try:
            item = validate_companion_manifest(manifest)
        except (ProtocolError, TypeError, ValueError):
            return False
        with self._lock:
            changed = self._items.get(item["id"]) != item
            self._items[item["id"]] = item
        return changed

    def unregister(self, companion_id: str) -> bool:
        with self._lock:
            return self._items.pop(str(companion_id), None) is not None

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(self._items[key]) for key in sorted(self._items)]
