"""Tiny main-thread boundary for HTTP requests and chunk continuation."""

from __future__ import annotations

from threading import Event, Lock
from typing import Any, Callable


class DispatchTimeout(TimeoutError):
    def __init__(self, execution):
        self.execution = execution
        super().__init__("Queued Glyphs call cancelled" if execution == "cancelled" else
                         "Glyphs call started; outcome uncertain. Reconcile the existing job before retrying.")


class CocoaMainThread:
    def __init__(self, *, timeout: float = 10.0, yield_seconds: float = 0.002) -> None:
        from PyObjCTools import AppHelper  # type: ignore[import-not-found]

        self._call_later = AppHelper.callLater
        self.timeout = max(0.1, float(timeout))
        self.yield_seconds = max(0.001, min(float(yield_seconds), 0.02))

    def schedule(self, callback: Callable[[], None]) -> None:
        # An immediate callAfter chain can monopolize Cocoa's run loop even
        # when every callback is individually short. A tiny timer boundary
        # lets drawing and input run between bridge chunks.
        self._call_later(self.yield_seconds, callback)

    def call(self, callback: Callable[[], Any]) -> Any:
        done = Event()
        lock = Lock()
        state = "pending"
        outcome: dict[str, Any] = {}

        def execute() -> None:
            nonlocal state
            with lock:
                if state != "pending":
                    return
                state = "running"
            try:
                outcome["value"] = callback()
            except BaseException as exc:
                outcome["error"] = exc
            finally:
                with lock:
                    state = "completed"
                    done.set()

        self.schedule(execute)
        done.wait(self.timeout)
        with lock:
            if state == "pending":
                state = "cancelled"
            if state != "completed":
                raise DispatchTimeout("cancelled" if state == "cancelled" else "uncertain")
        if "error" in outcome:
            raise outcome["error"]
        return outcome.get("value")

