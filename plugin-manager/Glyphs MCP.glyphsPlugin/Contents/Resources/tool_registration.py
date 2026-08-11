# encoding: utf-8

"""Catalog-driven FastMCP registration used by every public tool module."""

from __future__ import annotations

from functools import wraps
import inspect
import logging
from typing import Any, Callable, Dict, List, Set

from mcp_runtime import mcp
from tool_catalog import ACTIVE, APP_ONLY, TOOL_CATALOG
from tool_result_schemas import schema_for, workflow_tool_result


_REGISTERED: Set[str] = set()
_RESULT_OBSERVERS: List[Callable[..., None]] = []
logger = logging.getLogger(__name__)


def register_tool_result_observer(observer: Callable[..., None]) -> None:
    """Register a fail-open observer for completed or failed tool calls."""

    if observer not in _RESULT_OBSERVERS:
        _RESULT_OBSERVERS.append(observer)


def _bound_arguments(function: Callable[..., Any], args: tuple, kwargs: Dict[str, Any]) -> Dict[str, Any]:
    try:
        bound = inspect.signature(function).bind_partial(*args, **kwargs)
        bound.apply_defaults()
        return dict(bound.arguments)
    except Exception:
        return dict(kwargs)


def _notify_result_observers(entry, arguments, result=None, error=None) -> None:
    for observer in tuple(_RESULT_OBSERVERS):
        try:
            observer(entry=entry, arguments=dict(arguments), result=result, error=error)
        except Exception:
            logger.exception("Glyphs MCP tool-result observer failed for %s", entry.name)


def glyphs_tool() -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register a function using only its authoritative catalog metadata."""

    def decorate(function: Callable[..., Any]) -> Callable[..., Any]:
        name = function.__name__
        entry = TOOL_CATALOG.get(name)
        if entry is None:
            raise RuntimeError("Tool '{}' is missing from TOOL_CATALOG".format(name))
        if entry.state != ACTIVE:
            raise RuntimeError("Removed tool '{}' cannot be registered".format(name))
        if name in _REGISTERED:
            raise RuntimeError("Tool '{}' is registered more than once".format(name))

        @wraps(function)
        async def registered(*args: Any, **kwargs: Any) -> Any:
            arguments = _bound_arguments(function, args, kwargs)
            try:
                raw = await function(*args, **kwargs)
            except Exception as exc:
                _notify_result_observers(entry, arguments, error=exc)
                raise
            if entry.output_schema and entry.output_schema != "feedback":
                result = workflow_tool_result(name, entry.effect, raw, arguments)
            else:
                result = raw
            _notify_result_observers(entry, arguments, result=result)
            return result

        visibility = ["app"] if entry.visibility == APP_ONLY else ["model", "app"]
        meta: Dict[str, Any] = {"ui": {"visibility": visibility}}
        if entry.resource_uri:
            meta["ui"]["resourceUri"] = entry.resource_uri
        mcp.tool(
            name=entry.name,
            title=entry.title,
            description=entry.description,
            tags=set(entry.tags),
            output_schema=schema_for(entry.output_schema),
            annotations=dict(entry.annotations),
            meta=meta,
        )(registered)
        _REGISTERED.add(name)
        return function

    return decorate


def registered_catalog_names() -> Set[str]:
    return set(_REGISTERED)


__all__ = [
    "glyphs_tool",
    "register_tool_result_observer",
    "registered_catalog_names",
]
