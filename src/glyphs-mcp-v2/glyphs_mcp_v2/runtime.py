"""Composition root for the live Glyphs MCP 2.0 runtime."""

from __future__ import annotations

from fastmcp import FastMCP

from .adapters.document import GlyphsDocumentHost
from .adapters.lifecycle import GlyphsDocumentLifecycleObserver
from .application import GlyphsMCPApplication
from .canonical_tree import CanonicalFontTree, MemoryObjectStore
from .change_history import ChangeHistory
from .transport.fastmcp import create_server


_ACTIVE_HOST: GlyphsDocumentHost | None = None
_ACTIVE_APPLICATION: GlyphsMCPApplication | None = None
_ACTIVE_LIFECYCLE_OBSERVER: GlyphsDocumentLifecycleObserver | None = None


def active_host() -> GlyphsDocumentHost | None:
    return _ACTIVE_HOST


def active_application() -> GlyphsMCPApplication | None:
    return _ACTIVE_APPLICATION


def active_history() -> ChangeHistory | None:
    application = active_application()
    return application.history if application is not None else None


def scripting_runtime_safety_status() -> dict[str, object] | None:
    host = active_host()
    reader = getattr(host, "scripting_runtime_safety_status", None)
    value = reader() if callable(reader) else None
    return dict(value) if isinstance(value, dict) else None


def automatic_repair_scripting_runtime(trigger: str) -> dict[str, object] | None:
    """Run one server/UI lifecycle repair without rebuilding application state."""

    host = active_host()
    repair = getattr(host, "repair_scripting_runtime", None)
    if not callable(repair):
        return None
    try:
        value = repair(trigger=str(trigger))
    except Exception as exc:
        return {
            "error": type(exc).__name__,
            "scriptingRuntimeSafety": scripting_runtime_safety_status(),
        }
    if isinstance(value, dict):
        application = active_application()
        audit = getattr(application, "_audit", None)
        record = getattr(audit, "record", None)
        if callable(record):
            repair_value = value.get("repair")
            status_value = value.get("scriptingRuntimeSafety")
            record(
                tool="repair_runtime",
                effect="code",
                status=(
                    "success"
                    if isinstance(status_value, dict)
                    and status_value.get("state") == "healthy"
                    else "error"
                ),
                document_id=None,
                details={
                    "trigger": str(trigger),
                    "repair": repair_value,
                    "scriptingRuntimeSafety": status_value,
                },
            )
        return dict(value)
    return None


def create_glyphs_server() -> FastMCP:
    global _ACTIVE_APPLICATION, _ACTIVE_HOST, _ACTIVE_LIFECYCLE_OBSERVER
    host = GlyphsDocumentHost.from_running_glyphs()
    # Content-addressed objects live only for the unsaved app session. They are
    # detached Python bytes, structurally shared, and pruned on save; no disk IO
    # or hashing happens in Reporter callbacks.
    history = ChangeHistory(CanonicalFontTree(MemoryObjectStore()))
    history.reset_for_schema_change(5, 6)
    application = GlyphsMCPApplication(host, history=history)
    observer = GlyphsDocumentLifecycleObserver.install_from_running_glyphs(
        host, application
    )
    previous_observer = _ACTIVE_LIFECYCLE_OBSERVER
    _ACTIVE_HOST = host
    _ACTIVE_APPLICATION = application
    _ACTIVE_LIFECYCLE_OBSERVER = observer
    if previous_observer is not None:
        previous_observer.close()
    return create_server(application)


__all__ = [
    "active_application",
    "active_history",
    "active_host",
    "automatic_repair_scripting_runtime",
    "create_glyphs_server",
    "scripting_runtime_safety_status",
]
