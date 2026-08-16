"""Streamable HTTP construction and restart compatibility for v2."""

from __future__ import annotations

from typing import Any, Optional, Sequence

from fastmcp import FastMCP


def reset_event_stream_runtime() -> bool:
    """Detach sse-starlette state from a previously closed event loop."""
    try:
        from sse_starlette.sse import AppStatus
    except (ImportError, AttributeError):
        return False
    try:
        AppStatus.should_exit = False
        AppStatus.should_exit_event = None
    except Exception:
        return False
    return True


def create_http_app(
    server: FastMCP,
    *,
    middleware: Optional[Sequence[Any]] = None,
) -> Any:
    """Create one restart-safe `/mcp/` ASGI application."""
    reset_event_stream_runtime()
    return server.http_app(
        path="/mcp/",
        transport="http",
        middleware=list(middleware or ()),
    )


__all__ = ["create_http_app", "reset_event_stream_runtime"]
