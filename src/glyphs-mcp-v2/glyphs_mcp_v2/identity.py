"""Process-local stable identities independent of Glyphs and PyObjC."""

from __future__ import annotations

from threading import RLock
from typing import Callable, Dict, Hashable, Optional
from uuid import uuid4


class DocumentIdRegistry:
    """Bind native document identity keys to opaque process-local IDs."""

    def __init__(self, id_factory: Optional[Callable[[], str]] = None) -> None:
        self._id_factory = id_factory or (lambda: "doc_{}".format(uuid4().hex))
        self._ids: Dict[Hashable, str] = {}
        self._lock = RLock()

    def resolve(self, native_key: Hashable) -> str:
        if native_key is None:
            raise ValueError("native_key is required")
        with self._lock:
            current = self._ids.get(native_key)
            if current is not None:
                return current
            document_id = str(self._id_factory())
            if not document_id.startswith("doc_"):
                raise ValueError("document IDs must start with 'doc_'")
            if document_id in self._ids.values():
                raise RuntimeError("document ID factory returned a duplicate")
            self._ids[native_key] = document_id
            return document_id

    def discard(self, native_key: Hashable) -> bool:
        with self._lock:
            return self._ids.pop(native_key, None) is not None

    def __len__(self) -> int:
        with self._lock:
            return len(self._ids)


__all__ = ["DocumentIdRegistry"]
