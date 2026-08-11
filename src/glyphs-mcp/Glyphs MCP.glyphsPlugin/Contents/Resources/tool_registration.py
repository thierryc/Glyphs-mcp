# encoding: utf-8

"""Catalog-driven FastMCP registration used by every public tool module."""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Dict, Set

from mcp_runtime import mcp
from tool_catalog import ACTIVE, APP_ONLY, TOOL_CATALOG
from tool_result_schemas import schema_for, workflow_tool_result


_REGISTERED: Set[str] = set()


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
            raw = await function(*args, **kwargs)
            if entry.output_schema and entry.output_schema != "feedback":
                return workflow_tool_result(name, entry.effect, raw, kwargs)
            return raw

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


__all__ = ["glyphs_tool", "registered_catalog_names"]
