"""Pure latest-wins quiet-window queue for Edit View projection requests."""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Callable, Hashable


class ProjectionRequestQueue:
    """Coalesce projection requests until Glyphs' interface has settled."""

    def __init__(
        self,
        *,
        delay_seconds: float,
        capacity: int = 1,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.delay_seconds = max(0.0, float(delay_seconds))
        self.capacity = max(1, int(capacity))
        self._clock = clock
        self.generation = 0
        self._not_before = 0.0
        self._pending: "OrderedDict[Hashable, tuple[Any, Any]]" = OrderedDict()

    def note_interface_change(self) -> int:
        """Start a new quiet window while retaining its latest candidate."""

        self.generation += 1
        self._not_before = self._clock() + self.delay_seconds
        return self.generation

    def defer(
        self,
        key: Hashable,
        *,
        version: Any,
        payload: Any,
    ) -> bool:
        """Keep only the newest request for ``key`` in this quiet window."""

        request = (version, payload)
        previous = self._pending.get(key)
        if previous is not None and previous[0] == request[0]:
            return False
        self._pending.pop(key, None)
        self._pending[key] = request
        while len(self._pending) > self.capacity:
            self._pending.popitem(last=False)
        return True

    def remaining_delay(self) -> float:
        return max(0.0, self._not_before - self._clock())

    def drain_ready(self) -> tuple[float, tuple[Any, ...]]:
        """Return current payloads, or the remaining quiet-window duration."""

        remaining = self.remaining_delay()
        if remaining > 0.0:
            return remaining, ()
        payloads = tuple(request[1] for request in self._pending.values())
        self._pending.clear()
        return 0.0, payloads

    def clear(self) -> None:
        self._pending.clear()


__all__ = ["ProjectionRequestQueue"]
