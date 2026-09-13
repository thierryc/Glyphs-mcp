"""Tiny load-order-independent companion handshake for Glyphs plug-ins."""

from __future__ import annotations

import builtins
from typing import Any, Mapping


_SLOT = "_glyphs_mcp_companions_protocol_1"


def _state() -> dict[str, Any]:
    value = getattr(builtins, _SLOT, None)
    if not isinstance(value, dict):
        value = {"manifests": {}, "registry": None}
        setattr(builtins, _SLOT, value)
    return value


def publish(manifest: Mapping[str, Any]) -> bool:
    value = dict(manifest)
    identity = str(value.get("id") or "").strip()
    if not identity:
        return False
    state = _state()
    state["manifests"][identity] = value
    registry = state.get("registry")
    return bool(registry.register(value)) if registry is not None else True


def withdraw(companion_id: str) -> bool:
    identity = str(companion_id)
    state = _state()
    removed = state["manifests"].pop(identity, None) is not None
    registry = state.get("registry")
    if registry is not None:
        removed = bool(registry.unregister(identity)) or removed
    return removed


def attach_registry(registry: Any) -> None:
    state = _state()
    state["registry"] = registry
    for identity in sorted(state["manifests"]):
        registry.register(state["manifests"][identity])


def detach_registry(registry: Any) -> None:
    state = _state()
    if state.get("registry") is registry:
        state["registry"] = None


def _read(owner, name, default=None):
    try:
        value = getattr(owner, name)
        return value() if callable(value) else value
    except Exception:
        return default


def visible_layer(host):
    """Resolve one displayed layer, including a restored tab's text selection."""
    tab = _read(_read(host, "font"), "currentTab")
    view = _read(tab, "graphicView")
    layer = _read(tab, "activeLayer")
    if layer is None:
        layer = _read(view, "activeLayer")
    if layer is None:
        selected = _read(tab, "selectedLayers", [])
        if selected is not None and len(selected) == 1:
            layer = selected[0]
    return layer


def invalidate_view(host):
    """Invalidate the native canvas; never broadcast a cache-reset notification."""
    tab = _read(_read(host, "font"), "currentTab")
    view = _read(tab, "graphicView")
    if view is not None:
        view.setNeedsDisplay_(True)


def wake_reporter(reporter, main_loop):
    """One deferred wake after native controller/document/tab attachment."""
    if getattr(reporter, "_wake_scheduled", False):
        return
    reporter._wake_scheduled = True

    def ready():
        reporter._wake_scheduled = False
        reporter.update_(None)

    main_loop.callAfter(ready)
