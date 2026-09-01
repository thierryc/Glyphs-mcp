"""Version-neutral invocation contract for Glyphs native exporters."""

from __future__ import annotations

import inspect
from typing import Any, Callable, Mapping


class NativeExportError(RuntimeError):
    """Glyphs reported a native export failure."""


def _capitalized_keyword(name: str) -> str:
    return name[:1].upper() + name[1:]


def exporter_keywords(
    exporter: Callable[..., Any], values: Mapping[str, Any]
) -> dict[str, Any]:
    """Select lowercase Glyphs 4 or legacy documented keyword spelling.

    Selection happens before invocation so a possibly side-effecting exporter
    is never retried merely because its Python wrapper rejected a keyword.
    """

    normalized = {str(name): value for name, value in values.items()}
    try:
        parameters = inspect.signature(exporter).parameters
    except (TypeError, ValueError):
        parameters = {}
    if not parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    ):
        return normalized
    if all(name in parameters for name in normalized):
        return normalized
    capitalized = {
        _capitalized_keyword(name): value for name, value in normalized.items()
    }
    if all(name in parameters for name in capitalized):
        return capitalized
    unsupported = sorted(
        name
        for name in normalized
        if name not in parameters and _capitalized_keyword(name) not in parameters
    )
    if unsupported:
        raise NativeExportError(
            "native exporter does not accept keyword(s): {}".format(
                ", ".join(unsupported)
            )
        )
    return {
        name if name in parameters else _capitalized_keyword(name): value
        for name, value in normalized.items()
    }


def normalize_export_result(result: Any) -> Mapping[str, Any]:
    """Treat documented True and native None success consistently."""

    if result is None or result is True:
        return {"success": True, "nativeResult": result}
    if isinstance(result, (list, tuple)):
        children = [normalize_export_result(value) for value in result]
        return {
            "success": True,
            "nativeResult": result,
            "resultCount": len(children),
        }
    if result is False:
        raise NativeExportError("native exporter returned false")
    if isinstance(result, str):
        raise NativeExportError(result or "native exporter returned an error")
    raise NativeExportError(
        "native exporter returned unsupported result type {}".format(
            type(result).__name__
        )
    )


def invoke_native_export(
    exporter: Callable[..., Any], **keywords: Any
) -> Mapping[str, Any]:
    """Invoke exactly once with version-aware keywords and normalize success."""

    if not callable(exporter):
        raise NativeExportError("native exporter is unavailable")
    selected = exporter_keywords(exporter, keywords)
    result = exporter(**selected)
    receipt = dict(normalize_export_result(result))
    receipt["keywordSpelling"] = (
        "lowercase"
        if set(selected) == set(keywords)
        else "legacy_capitalized"
    )
    return receipt


__all__ = [
    "NativeExportError",
    "exporter_keywords",
    "invoke_native_export",
    "normalize_export_result",
]
