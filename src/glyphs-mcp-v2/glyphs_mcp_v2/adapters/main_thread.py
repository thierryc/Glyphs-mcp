"""Main-thread executors for tests and the live Glyphs host."""

from __future__ import annotations

from threading import Event
from typing import Callable, Optional, TypeVar

from ..ports import HostAccessError


T = TypeVar("T")


class DirectMainThreadExecutor:
    """Synchronous executor for deterministic host-adapter tests."""

    def run(self, callback: Callable[[], T]) -> T:
        return callback()


class GlyphsMainThreadExecutor:
    """Run one bounded snapshot callback on Glyphs' Cocoa main thread."""

    def __init__(self, timeout_seconds: float = 10.0) -> None:
        self._timeout_seconds = float(timeout_seconds)

    def run(self, callback: Callable[[], T]) -> T:
        if callback is None:
            raise ValueError("callback is required")

        try:
            from Foundation import NSOperationQueue, NSThread  # type: ignore[import-not-found]
        except Exception as exc:
            raise HostAccessError("Cocoa main-thread APIs are unavailable.") from exc

        try:
            if NSThread.isMainThread():
                return callback()
        except Exception:
            pass

        finished = Event()
        result: list[T] = []
        failure: list[BaseException] = []

        def execute() -> None:
            try:
                result.append(callback())
            except BaseException as exc:  # re-raised on the server thread
                failure.append(exc)
            finally:
                finished.set()

        try:
            NSOperationQueue.mainQueue().addOperationWithBlock_(execute)
        except Exception as exc:
            raise HostAccessError("Could not schedule work on Glyphs' main thread.") from exc

        if not finished.wait(self._timeout_seconds):
            raise HostAccessError("Timed out waiting for Glyphs' main thread.")
        if failure:
            raise failure[0]
        if not result:
            raise HostAccessError("Glyphs main-thread callback returned no result.")
        return result[0]


__all__ = ["DirectMainThreadExecutor", "GlyphsMainThreadExecutor"]
