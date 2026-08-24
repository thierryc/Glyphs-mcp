"""Main-thread executors for tests and the live Glyphs host."""

from __future__ import annotations

from threading import Event, Lock, local
from typing import Callable, Optional, TypeVar

from ..ports import HostAccessError


T = TypeVar("T")


class DirectMainThreadExecutor:
    """Synchronous executor for deterministic host-adapter tests."""

    def run(self, callback: Callable[[], T]) -> T:
        return callback()


class GlyphsMainThreadExecutor:
    """Run one bounded snapshot callback on Glyphs' Cocoa main thread."""

    _execution_state = local()

    def __init__(self, timeout_seconds: float = 10.0) -> None:
        self._timeout_seconds = float(timeout_seconds)

    def run(self, callback: Callable[[], T]) -> T:
        if callback is None:
            raise ValueError("callback is required")

        # A callback already entered through Cocoa's main queue is an
        # authoritative execution context even if PyObjC transiently reports
        # ``NSThread.isMainThread()`` as false. Re-scheduling nested host work
        # would place it behind the callback that is waiting for it and can
        # deadlock until the bounded start timeout. The marker is shared by
        # executor instances but remains thread-local.
        if int(getattr(self._execution_state, "depth", 0) or 0) > 0:
            return callback()

        try:
            from Foundation import NSThread  # type: ignore[import-not-found]
            from PyObjCTools import AppHelper  # type: ignore[import-not-found]
        except Exception as exc:
            raise HostAccessError("Cocoa main-thread APIs are unavailable.") from exc

        try:
            if NSThread.isMainThread():
                return callback()
        except Exception:
            pass

        finished = Event()
        state_lock = Lock()
        state = {"started": False, "cancelled": False}
        result: list[T] = []
        failure: list[BaseException] = []

        def execute() -> None:
            with state_lock:
                if state["cancelled"]:
                    finished.set()
                    return
                state["started"] = True
            previous_depth = int(
                getattr(self._execution_state, "depth", 0) or 0
            )
            self._execution_state.depth = previous_depth + 1
            try:
                result.append(callback())
            except BaseException as exc:  # re-raised on the server thread
                failure.append(exc)
            finally:
                self._execution_state.depth = previous_depth
                finished.set()

        try:
            # PyObjC's message runner schedules asynchronously and returns
            # before Cocoa invokes the Python block. NSOperationQueue can let
            # the main queue enter the block while the scheduling selector is
            # still returning on the server thread, creating a GIL inversion:
            # the UI waits for Python while the server still owns Python.
            AppHelper.callAfter(execute)
        except Exception as exc:
            raise HostAccessError("Could not schedule work on Glyphs' main thread.") from exc

        if not finished.wait(self._timeout_seconds):
            with state_lock:
                if not state["started"]:
                    state["cancelled"] = True
                    raise HostAccessError(
                        "Timed out waiting for Glyphs' main thread before it started."
                    )
            # Cocoa/PyObjC work that has already started cannot be killed
            # safely. Returning here would let hidden document mutation
            # continue after the transaction reports failure, so wait for the
            # real result and let the caller verify it normally.
            finished.wait()
        if failure:
            raise failure[0]
        if not result:
            raise HostAccessError("Glyphs main-thread callback returned no result.")
        return result[0]


__all__ = ["DirectMainThreadExecutor", "GlyphsMainThreadExecutor"]
