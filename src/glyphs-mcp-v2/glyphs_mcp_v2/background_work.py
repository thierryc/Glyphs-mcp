"""Bounded non-blocking coordination for optional Glyphs background work.

Submission is deliberately wait-free from the caller's perspective: producers
append a small immutable command to a bounded deque and return.  A single
daemon worker owns coalescing, prioritisation, and execution so Glyphs drawing
and lifecycle callbacks never wait for a lock, queue slot, future, or worker.
"""

from __future__ import annotations

import itertools
import os
import select
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from threading import Thread, current_thread
from typing import Any, Callable, Hashable


WorkKey = tuple[str, Hashable]


@dataclass(frozen=True)
class WorkContext:
    """Cancellation view supplied to one optional background job."""

    coordinator: "BackgroundWorkCoordinator"
    kind: str
    key: Hashable
    generation: int

    def cancelled(self) -> bool:
        return not self.coordinator.is_current(
            self.kind, self.key, self.generation
        )


@dataclass(frozen=True)
class _WorkItem:
    kind: str
    key: Hashable
    generation: int
    work: Callable[[WorkContext], Any]
    completed: Callable[[Any], None] | None
    failed: Callable[[Exception], None] | None
    not_before: float

    @property
    def identity(self) -> WorkKey:
        return (self.kind, self.key)


class BackgroundWorkCoordinator:
    """Run latest-wins convenience work on one bounded daemon lane.

    The implementation intentionally avoids ``ThreadPoolExecutor`` because its
    submission path takes internal locks and its default queue is unbounded.
    Obsolete commands may be dropped under pressure; their generations remain
    stale, so they can never publish a result later.
    """

    _KIND_PRIORITY = {
        "source": 0,
        "cleanup": 0,
        "history": 1,
        "projection": 2,
        "diff": 3,
    }

    def __init__(
        self,
        *,
        capacity: int = 32,
        clock: Callable[[], float] = time.monotonic,
        thread_name: str = "glyphs-mcp-convenience",
        autostart: bool = True,
    ) -> None:
        if capacity < 1:
            raise ValueError("background capacity must be positive")
        self.capacity = int(capacity)
        self._clock = clock
        self._source_commands: deque[_WorkItem] = deque(
            maxlen=max(4, capacity)
        )
        self._visual_commands: deque[_WorkItem] = deque(
            maxlen=max(4, capacity * 2)
        )
        self._latest: dict[WorkKey, int | None] = {}
        self._counter = itertools.count(1)
        self._wake_read, self._wake_write = os.pipe()
        os.set_blocking(self._wake_read, False)
        os.set_blocking(self._wake_write, False)
        self._pipe_closed = False
        self._closed = False
        self._pause_until: dict[Hashable, float] = {}
        self._thread = Thread(target=self._run, name=thread_name, daemon=True)
        if autostart:
            self._thread.start()

    @property
    def worker(self) -> Thread:
        return self._thread

    def submit(
        self,
        kind: str,
        key: Hashable,
        work: Callable[[WorkContext], Any],
        *,
        completed: Callable[[Any], None] | None = None,
        failed: Callable[[Exception], None] | None = None,
        delay: float = 0.0,
    ) -> int | None:
        """Append one job without waiting; return its generation if accepted."""

        if self._closed:
            return None
        generation = next(self._counter)
        identity = (str(kind), key)
        self._latest[identity] = generation
        item = _WorkItem(
            kind=str(kind),
            key=key,
            generation=generation,
            work=work,
            completed=completed,
            failed=failed,
            not_before=self._clock() + max(0.0, float(delay)),
        )
        lane = (
            self._source_commands
            if item.kind in {"source", "cleanup", "history"}
            else self._visual_commands
        )
        if lane.maxlen is not None and len(lane) == lane.maxlen:
            dropped = lane[0]
            if self._latest.get(dropped.identity) == dropped.generation:
                self._latest.pop(dropped.identity, None)
        lane.append(item)
        self._notify()
        return generation

    def _notify(self) -> None:
        try:
            os.write(self._wake_write, b"1")
        except (BlockingIOError, OSError):
            # A full pipe already means the worker has a wake-up pending.
            pass

    def _drain_notifications(self) -> None:
        while True:
            try:
                if not os.read(self._wake_read, 4096):
                    return
            except (BlockingIOError, OSError):
                return

    def invalidate(self, key: Hashable, *, kind: str | None = None) -> None:
        """Make queued/running results stale without waiting for their worker."""

        if kind is not None:
            self._latest[(str(kind), key)] = None
            return
        for identity in tuple(self._latest):
            work_key = identity[1]
            if work_key == key or (
                isinstance(work_key, tuple)
                and work_key
                and work_key[0] == key
            ):
                self._latest[identity] = None

    def pause_for_save(self, key: Hashable, *, timeout: float = 2.0) -> None:
        """Cancel current convenience results and defer work during a save."""

        self.invalidate(key)
        self._pause_until[key] = self._clock() + max(0.0, float(timeout))
        self._notify()

    def resume_after_save(self, key: Hashable, *, delay: float = 0.25) -> None:
        """Retain a short quiet window after the native save callback returns."""

        self._pause_until[key] = self._clock() + max(0.0, float(delay))
        self._notify()

    def is_current(self, kind: str, key: Hashable, generation: int) -> bool:
        if self._closed:
            return False
        identity = (str(kind), key)
        if self._latest.get(identity) != int(generation):
            return False
        return self._clock() >= self._pause_deadline(key)

    def _pause_deadline(self, key: Hashable) -> float:
        direct = self._pause_until.get(key, 0.0)
        if isinstance(key, tuple) and key:
            return max(direct, self._pause_until.get(key[0], 0.0))
        return direct

    def close(self, *, wait: bool = False) -> None:
        """Invalidate all work; waiting is opt-in and forbidden on the worker."""

        if self._closed:
            return
        self._closed = True
        self._latest.clear()
        self._source_commands.clear()
        self._visual_commands.clear()
        self._notify()
        if wait and self._thread.is_alive() and current_thread() is not self._thread:
            self._thread.join(timeout=2.0)
        if not self._thread.is_alive():
            self._close_wake_pipe()

    def _close_wake_pipe(self) -> None:
        if self._pipe_closed:
            return
        self._pipe_closed = True
        for descriptor in (self._wake_read, self._wake_write):
            try:
                os.close(descriptor)
            except OSError:
                pass

    def _drain(self, pending: "OrderedDict[WorkKey, _WorkItem]") -> None:
        for lane in (self._source_commands, self._visual_commands):
            while True:
                try:
                    item = lane.popleft()
                except IndexError:
                    break
                pending.pop(item.identity, None)
                pending[item.identity] = item
        while len(pending) > self.capacity:
            # Prefer retaining source refreshes over visual convenience work.
            victim = max(
                pending,
                key=lambda identity: (
                    self._KIND_PRIORITY.get(identity[0], 99),
                    list(pending).index(identity),
                ),
            )
            removed = pending.pop(victim, None)
            if (
                removed is not None
                and self._latest.get(victim) == removed.generation
            ):
                self._latest.pop(victim, None)

    def _retire(self, item: _WorkItem) -> None:
        current = self._latest.get(item.identity)
        if current is None or current == item.generation:
            self._latest.pop(item.identity, None)

    def _next_ready(
        self, pending: "OrderedDict[WorkKey, _WorkItem]"
    ) -> tuple[_WorkItem | None, float]:
        now = self._clock()
        ready: list[_WorkItem] = []
        next_time: float | None = None
        for item in pending.values():
            available = max(item.not_before, self._pause_deadline(item.key))
            if available <= now:
                ready.append(item)
            elif next_time is None or available < next_time:
                next_time = available
        if ready:
            ready.sort(
                key=lambda item: (
                    self._KIND_PRIORITY.get(item.kind, 99),
                    item.generation,
                )
            )
            return ready[0], 0.0
        return None, max(0.001, (next_time - now) if next_time is not None else 60.0)

    def _run(self) -> None:
        pending: "OrderedDict[WorkKey, _WorkItem]" = OrderedDict()
        try:
            while not self._closed:
                self._drain(pending)
                item, wait_for = self._next_ready(pending)
                if item is None:
                    try:
                        select.select([self._wake_read], [], [], wait_for)
                    except (OSError, ValueError):
                        if self._closed:
                            return
                    self._drain_notifications()
                    continue
                pending.pop(item.identity, None)
                context = WorkContext(self, item.kind, item.key, item.generation)
                if context.cancelled():
                    self._retire(item)
                    continue
                try:
                    result = item.work(context)
                except Exception as error:
                    if not context.cancelled() and item.failed is not None:
                        try:
                            item.failed(error)
                        except Exception:
                            pass
                    self._retire(item)
                    continue
                if context.cancelled() or item.completed is None:
                    self._retire(item)
                    continue
                try:
                    item.completed(result)
                except Exception:
                    pass
                self._retire(item)
        finally:
            self._close_wake_pipe()


__all__ = ["BackgroundWorkCoordinator", "WorkContext"]
