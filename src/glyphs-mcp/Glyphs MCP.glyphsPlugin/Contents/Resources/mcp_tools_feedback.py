# encoding: utf-8

"""Structured MCP App feedback tools for bounded Glyphs review workflows."""

from __future__ import annotations

from collections import OrderedDict
import hashlib
import json
import logging
import secrets
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastmcp.tools.tool import ToolResult
from GlyphsApp import Glyphs  # type: ignore[import-not-found]

from mcp_app_ui import FEEDBACK_RESOURCE_URI
from mcp_runtime import mcp
from mcp_tool_helpers import (
    _font_summary,
    _get_layer_id,
    _get_left_sidebearing,
    _get_right_sidebearing,
    _is_style_set_tag,
    _layer_display_name,
    _open_fonts_from_glyphs,
    _open_tab_on_main_thread,
    _parse_style_set_substitutions,
    _resolve_font_by_index,
    _style_set_name_from_metadata,
)
from mcp_tools_kerning import apply_kerning_bumper
from mcp_tools_smoothness import apply_collinear_handles_smooth
from mcp_tools_spacing import apply_spacing
from versioning import get_runtime_info


logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0"
PLAN_TTL_SECONDS = 10 * 60
PLAN_CAPACITY = 64

FEEDBACK_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": [
        "schemaVersion",
        "kind",
        "status",
        "title",
        "summary",
        "target",
        "items",
        "warnings",
        "actions",
        "progress",
        "result",
    ],
    "properties": {
        "schemaVersion": {"type": "string", "const": SCHEMA_VERSION},
        "kind": {"type": "string"},
        "status": {"type": "string", "enum": ["ready", "warning", "working", "success", "partial", "error"]},
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "target": {"type": "object"},
        "items": {"type": "array", "items": {"type": "object"}},
        "warnings": {"type": "array", "items": {}},
        "actions": {"type": "array", "items": {"type": "object"}, "maxItems": 2},
        "progress": {"type": "object"},
        "result": {"type": "object"},
        "error": {"type": ["object", "null"]},
    },
    "additionalProperties": False,
}


def _tool_meta(*, app_only: bool = False) -> Dict[str, Any]:
    return {
        "ui": {
            "resourceUri": FEEDBACK_RESOURCE_URI,
            "visibility": ["app"] if app_only else ["model", "app"],
        }
    }


READ_ONLY_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}
OPEN_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": False,
}
APPLY_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": True,
    "idempotentHint": False,
    "openWorldHint": False,
}


def _counts(reviewed: int = 0, changed: int = 0, skipped: int = 0, failed: int = 0) -> Dict[str, int]:
    return {
        "reviewed": int(reviewed or 0),
        "changed": int(changed or 0),
        "skipped": int(skipped or 0),
        "failed": int(failed or 0),
    }


def _payload(
    *,
    kind: str,
    status: str,
    title: str,
    summary: str,
    target: Optional[Dict[str, Any]] = None,
    items: Optional[List[Dict[str, Any]]] = None,
    warnings: Optional[List[Any]] = None,
    actions: Optional[List[Dict[str, Any]]] = None,
    progress: Optional[Dict[str, int]] = None,
    result: Optional[Dict[str, int]] = None,
    error: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "kind": kind,
        "status": status,
        "title": title,
        "summary": summary,
        "target": target or {},
        "items": list(items or []),
        "warnings": list(warnings or []),
        "actions": list(actions or [])[:2],
        "progress": progress or _counts(),
        "result": result or _counts(),
    }
    if error is not None:
        data["error"] = error
    return data


def _tool_result(data: Dict[str, Any]) -> ToolResult:
    text = "{}: {}".format(data.get("title", "Glyphs MCP"), data.get("summary", ""))
    error = data.get("error")
    if isinstance(error, dict) and error.get("code"):
        text += " [{}]".format(error["code"])
    return ToolResult(content=text, structured_content=data)


def _action(label: str, tool: str, arguments: Optional[Dict[str, Any]] = None, **extra: Any) -> Dict[str, Any]:
    value = {"label": label, "tool": tool, "arguments": arguments or {}}
    value.update(extra)
    return value


def _error_code(message: str, fallback: str = "validation_failed") -> str:
    lower = (message or "").lower()
    if "no open font" in lower or "no font" in lower or "font is currently active" in lower:
        return "no_font_open"
    if any(token in lower for token in ("not found", "out of range", "no glyphs", "no active layer", "no requested glyph")):
        return "target_not_found"
    return fallback


def _error_payload(
    code: str,
    message: str,
    *,
    title: str = "Glyphs feedback unavailable",
    next_action: str = "Check the open font and try again.",
    retry: Optional[Tuple[str, Dict[str, Any]]] = None,
    technical: Optional[str] = None,
) -> Dict[str, Any]:
    actions: List[Dict[str, Any]] = []
    if retry:
        actions.append(_action("Retry", retry[0], retry[1]))
    error: Dict[str, Any] = {
        "code": code,
        "message": message,
        "recoverable": True,
        "nextAction": next_action,
    }
    if technical:
        error["technical"] = technical
    return _payload(
        kind="error",
        status="error",
        title=title,
        summary=message,
        actions=actions,
        error=error,
        result=_counts(failed=1),
    )


def _safe_number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except Exception:
        return None
    return int(number) if number.is_integer() else round(number, 2)


def _safe_len(value: Any) -> int:
    try:
        return len(value or [])
    except Exception:
        try:
            return len(list(value or []))
        except Exception:
            return 0


def _font_target(font: Any, font_index: int) -> Dict[str, Any]:
    return {
        "fontIndex": int(font_index),
        "familyName": getattr(font, "familyName", "") or "Untitled font",
        "fileState": "Saved" if getattr(font, "filepath", None) else "Unsaved",
    }


def _retry(tool: str, arguments: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [_action("Refresh", tool, arguments)]


def _font_or_error(font_index: int) -> Tuple[Any, Optional[Dict[str, Any]]]:
    font, fonts = _resolve_font_by_index(Glyphs, font_index)
    if font:
        return font, None
    if not fonts:
        message = "No font is open in Glyphs."
        code = "no_font_open"
    else:
        message = "Font index {} is not one of the {} open fonts.".format(font_index, len(fonts))
        code = "target_not_found"
    return None, _error_payload(code, message)


def _glyph_for_name(font: Any, name: str) -> Any:
    try:
        glyph = font.glyphs[name]
        if glyph is not None:
            return glyph
    except Exception:
        pass
    try:
        for glyph in list(font.glyphs or []):
            if str(getattr(glyph, "productionName", "") or "") == name:
                return glyph
    except Exception:
        pass
    return None


def _selected_glyph(font: Any) -> Any:
    try:
        layers = list(getattr(font, "selectedLayers", []) or [])
        return getattr(layers[0], "parent", None) if layers else None
    except Exception:
        return None


def _layer_for_glyph(font: Any, glyph: Any, master_id: Optional[str] = None) -> Any:
    if glyph is None:
        return None
    wanted = master_id
    if wanted is None:
        wanted = getattr(getattr(font, "selectedFontMaster", None), "id", None)
    if wanted:
        try:
            layer = glyph.layers[str(wanted)]
            if layer is not None:
                return layer
        except Exception:
            pass
    try:
        selected = list(getattr(font, "selectedLayers", []) or [])
        for layer in selected:
            if getattr(layer, "parent", None) is glyph:
                return layer
    except Exception:
        pass
    try:
        return glyph.layers[0]
    except Exception:
        return None


def _feature_line_count(code: str) -> int:
    return len(code.splitlines()) if code else 0


def _unique(values: Iterable[Any]) -> List[Any]:
    result: List[Any] = []
    seen = set()
    for value in values:
        marker = json.dumps(value, sort_keys=True, default=str)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(value)
    return result


@mcp.tool(
    output_schema=FEEDBACK_OUTPUT_SCHEMA,
    annotations=READ_ONLY_ANNOTATIONS,
    meta=_tool_meta(),
)
async def show_glyphs_status() -> ToolResult:
    """Show server, Glyphs, and open-font status in the shared feedback panel."""

    try:
        fonts = _open_fonts_from_glyphs(Glyphs)
        runtime = get_runtime_info()
        glyphs_version = getattr(Glyphs, "versionNumber", None)
        items = [
            {"label": "MCP server", "value": "Connected", "detail": runtime.get("runtimeId") or runtime.get("version")},
            {"label": "Glyphs", "value": glyphs_version or "Detected", "detail": "Currently serving this MCP endpoint"},
            {"label": "Open fonts", "value": len(fonts), "detail": ", ".join((getattr(font, "familyName", "") or "Untitled") for font in fonts) or "None"},
        ]
        warnings = [] if fonts else ["Open a font in Glyphs before requesting font or glyph feedback."]
        return _tool_result(
            _payload(
                kind="status",
                status="ready" if fonts else "warning",
                title="Glyphs MCP status",
                summary="The local MCP server is connected to Glyphs." if fonts else "The server is connected, but no font is open.",
                items=items,
                warnings=warnings,
                actions=_retry("show_glyphs_status", {}),
                progress=_counts(reviewed=len(items)),
            )
        )
    except Exception:
        logger.exception("Unable to build Glyphs status feedback")
        return _tool_result(
            _error_payload(
                "validation_failed",
                "Glyphs status could not be read safely.",
                retry=("show_glyphs_status", {}),
            )
        )


@mcp.tool(
    output_schema=FEEDBACK_OUTPUT_SCHEMA,
    annotations=READ_ONLY_ANNOTATIONS,
    meta=_tool_meta(),
)
async def show_font_feedback(font_index: int = 0) -> ToolResult:
    """Show read-only information about one currently open Glyphs font."""

    arguments = {"font_index": font_index}
    try:
        font, error = _font_or_error(font_index)
        if error:
            error["actions"] = _retry("show_font_feedback", arguments)
            return _tool_result(error)
        masters = list(getattr(font, "masters", []) or [])
        instances = list(getattr(font, "instances", []) or [])
        glyphs = getattr(font, "glyphs", []) or []
        selected_master = getattr(font, "selectedFontMaster", None)
        items = [
            {"label": "Glyphs", "value": _safe_len(glyphs)},
            {"label": "Masters", "value": len(masters), "detail": ", ".join(getattr(master, "name", "") or "Unnamed" for master in masters)},
            {"label": "Instances", "value": len(instances)},
            {"label": "Units per em", "value": getattr(font, "upm", None)},
            {"label": "Current master", "value": getattr(selected_master, "name", None) or "Not selected"},
            {"label": "OpenType features", "value": _safe_len(getattr(font, "features", []))},
        ]
        warnings = []
        if not getattr(font, "filepath", None):
            warnings.append("This font has not been saved yet. The panel will not save it.")
        return _tool_result(
            _payload(
                kind="font",
                status="warning" if warnings else "ready",
                title="Font information",
                summary="Read-only information for {}.".format(getattr(font, "familyName", "") or "the open font"),
                target=_font_target(font, font_index),
                items=items,
                warnings=warnings,
                actions=[
                    _action("OpenType Features", "show_opentype_features", {"font_index": font_index}),
                    _action("Refresh", "show_font_feedback", arguments),
                ],
                progress=_counts(reviewed=len(items)),
            )
        )
    except Exception:
        logger.exception("Unable to build font feedback")
        return _tool_result(_error_payload("validation_failed", "The open font could not be inspected.", retry=("show_font_feedback", arguments)))


@mcp.tool(
    output_schema=FEEDBACK_OUTPUT_SCHEMA,
    annotations=READ_ONLY_ANNOTATIONS,
    meta=_tool_meta(),
)
async def show_glyph_feedback(font_index: int = 0, glyph_name: str = "") -> ToolResult:
    """Show read-only metadata for a named glyph or the active Glyphs selection."""

    arguments = {"font_index": font_index, "glyph_name": glyph_name}
    try:
        font, error = _font_or_error(font_index)
        if error:
            error["actions"] = _retry("show_glyph_feedback", arguments)
            return _tool_result(error)
        glyph = _glyph_for_name(font, glyph_name) if glyph_name else _selected_glyph(font)
        if glyph is None:
            message = "Glyph '{}' was not found in the open font.".format(glyph_name) if glyph_name else "No glyph is selected in Glyphs."
            return _tool_result(
                _error_payload(
                    "target_not_found",
                    message,
                    next_action="Select a glyph in Glyphs or provide an existing glyph name.",
                    retry=("show_glyph_feedback", arguments),
                )
            )
        glyph_name = str(getattr(glyph, "name", "") or glyph_name)
        layer = _layer_for_glyph(font, glyph)
        if layer is None:
            return _tool_result(_error_payload("target_not_found", "The selected glyph has no readable layer."))

        bounds = getattr(layer, "bounds", None)
        size = getattr(bounds, "size", None)
        anchors = list(getattr(layer, "anchors", []) or [])
        components = list(getattr(layer, "components", []) or [])
        if not components:
            components = [shape for shape in list(getattr(layer, "shapes", []) or []) if hasattr(shape, "componentName")]
        layers = list(getattr(glyph, "layers", []) or [])
        anchor_names = [str(getattr(anchor, "name", "") or "") for anchor in anchors if getattr(anchor, "name", None)]
        component_names = [str(getattr(component, "componentName", "") or "") for component in components if getattr(component, "componentName", None)]
        metrics = {
            "Width": _safe_number(getattr(layer, "width", None)),
            "Left sidebearing": _safe_number(_get_left_sidebearing(layer)),
            "Right sidebearing": _safe_number(_get_right_sidebearing(layer)),
            "Bounds width": _safe_number(getattr(size, "width", None)),
            "Bounds height": _safe_number(getattr(size, "height", None)),
        }
        items = [
            {"label": "Metadata", "value": glyph_name, "detail": "{} · {} · Unicode {}".format(getattr(glyph, "category", "") or "Uncategorized", getattr(glyph, "subCategory", "") or "No subcategory", getattr(glyph, "unicode", None) or "—")},
            {"label": "Dimensions and spacing", "metrics": {key: value for key, value in metrics.items() if value is not None}},
            {"label": "Anchors", "value": len(anchors), "detail": ", ".join(anchor_names) or "None"},
            {"label": "Components", "value": len(components), "detail": ", ".join(component_names) or "None"},
            {"label": "Layers", "value": len(layers), "detail": _layer_display_name(font, layer)},
        ]
        warnings = []
        if getattr(layer, "width", 0) is None:
            warnings.append("The active layer has no readable width.")
        master = getattr(font, "selectedFontMaster", None)
        target = _font_target(font, font_index)
        target.update({
            "glyphName": glyph_name,
            "masterId": getattr(master, "id", None),
            "masterName": getattr(master, "name", None),
            "layerId": _get_layer_id(layer),
        })
        return _tool_result(
            _payload(
                kind="glyph",
                status="warning" if warnings else "ready",
                title="Glyph information",
                summary="Read-only feedback for {} in {}.".format(glyph_name, target["familyName"]),
                target=target,
                items=items,
                warnings=warnings,
                actions=[
                    _action("Open in Glyphs", "open_feedback_target", {"font_index": font_index, "glyph_names": [glyph_name], "master_id": target.get("masterId")}),
                    _action("Refresh", "show_glyph_feedback", {"font_index": font_index, "glyph_name": glyph_name}),
                ],
                progress=_counts(reviewed=len(items)),
            )
        )
    except Exception:
        logger.exception("Unable to build glyph feedback")
        return _tool_result(_error_payload("validation_failed", "The glyph could not be inspected safely.", retry=("show_glyph_feedback", arguments)))


@mcp.tool(
    output_schema=FEEDBACK_OUTPUT_SCHEMA,
    annotations=READ_ONLY_ANNOTATIONS,
    meta=_tool_meta(),
)
async def show_opentype_features(
    font_index: int = 0,
    include_inactive: bool = False,
    include_code: bool = False,
) -> ToolResult:
    """Show a read-only OpenType feature report with parsed stylistic sets."""

    arguments = {"font_index": font_index, "include_inactive": include_inactive, "include_code": include_code}
    try:
        font, error = _font_or_error(font_index)
        if error:
            error["actions"] = _retry("show_opentype_features", arguments)
            return _tool_result(error)
        items: List[Dict[str, Any]] = []
        warnings: List[str] = []
        open_names: List[str] = []
        all_features = list(getattr(font, "features", []) or [])
        for index, feature in enumerate(all_features):
            tag = str(getattr(feature, "name", "") or "")
            active = bool(getattr(feature, "active", True))
            if not active and not include_inactive:
                continue
            automatic = bool(getattr(feature, "automatic", False))
            code = str(getattr(feature, "code", "") or "")
            item: Dict[str, Any] = {
                "id": "feature-{}".format(index),
                "label": tag or "Unnamed feature",
                "value": "{} · {}".format("Active" if active else "Inactive", "Automatic" if automatic else "Manual"),
                "detail": "{} lines".format(_feature_line_count(code)),
            }
            if _is_style_set_tag(tag):
                parsed = _parse_style_set_substitutions(code)
                substitutions = list(parsed.get("substitutions", []) or [])
                replacements = _unique([entry.get("replacement") for entry in substitutions if entry.get("replacement")])
                open_names.extend(replacements)
                name = _style_set_name_from_metadata(tag, notes=getattr(feature, "notes", None), labels=getattr(feature, "labels", None))
                item["label"] = name or tag
                item["detail"] = "{} · {} substitutions · {} lines".format(tag, len(substitutions), _feature_line_count(code))
                item["metrics"] = {"Parsed substitutions": len(substitutions), "Unsupported rules": int(parsed.get("unsupportedRuleCount", 0) or 0)}
                for warning in parsed.get("warnings", []) or []:
                    warnings.append("{}: {}".format(tag, warning))
            if include_code:
                item["code"] = code
            items.append(item)

        target = _font_target(font, font_index)
        actions = []
        if open_names:
            actions.append(_action("Open in Glyphs", "open_feedback_target", {"font_index": font_index, "glyph_names": open_names[:64]}))
        actions.append(_action("Refresh", "show_opentype_features", arguments))
        hidden_count = sum(1 for feature in all_features if not bool(getattr(feature, "active", True))) if not include_inactive else 0
        if hidden_count:
            warnings.append("{} inactive features are hidden.".format(hidden_count))
        return _tool_result(
            _payload(
                kind="opentype",
                status="warning" if warnings else "ready",
                title="OpenType feature report",
                summary="{} features are shown for {}.".format(len(items), target["familyName"]),
                target=target,
                items=items,
                warnings=_unique(warnings)[:24],
                actions=actions,
                progress=_counts(reviewed=len(items)),
            )
        )
    except Exception:
        logger.exception("Unable to build OpenType feedback")
        return _tool_result(_error_payload("validation_failed", "OpenType features could not be inspected safely.", retry=("show_opentype_features", arguments)))


class _FeedbackPlan:
    def __init__(self, operation: str, arguments: Dict[str, Any], change_hash: str, created_at: float):
        self.operation = operation
        self.arguments = arguments
        self.change_hash = change_hash
        self.created_at = float(created_at)


_plans: "OrderedDict[str, _FeedbackPlan]" = OrderedDict()


def _purge_expired(now: Optional[float] = None) -> None:
    timestamp = time.monotonic() if now is None else float(now)
    expired = [plan_id for plan_id, plan in _plans.items() if timestamp - plan.created_at > PLAN_TTL_SECONDS]
    for plan_id in expired:
        _plans.pop(plan_id, None)


def _store_plan(operation: str, arguments: Dict[str, Any], change_hash: str) -> str:
    _purge_expired()
    while len(_plans) >= PLAN_CAPACITY:
        _plans.popitem(last=False)
    plan_id = secrets.token_urlsafe(18)
    normalized_arguments = json.loads(json.dumps(arguments, sort_keys=True, default=str))
    _plans[plan_id] = _FeedbackPlan(operation, normalized_arguments, change_hash, time.monotonic())
    return plan_id


def _reset_feedback_plans_for_tests() -> None:
    _plans.clear()


async def _invoke_existing(tool: Any, arguments: Dict[str, Any]) -> Dict[str, Any]:
    function = getattr(tool, "fn", tool)
    raw = await function(**arguments)
    if isinstance(raw, str):
        value = json.loads(raw)
    elif isinstance(raw, dict):
        value = raw
    else:
        raise ValueError("Unexpected tool response type")
    if not isinstance(value, dict):
        raise ValueError("Expected an object response")
    return value


def _canonical_change_set(operation: str, response: Dict[str, Any]) -> Any:
    if operation == "spacing":
        fields = ("glyphName", "masterId", "status", "reason", "current", "suggested", "delta")
        return [
            {key: item.get(key) for key in fields if key in item}
            for item in list(response.get("results", []) or [])
            if isinstance(item, dict)
        ]
    if operation == "kerning":
        return {
            "masterId": response.get("masterId"),
            "changes": list(response.get("changes", []) or []),
        }
    if operation == "smooth_handles":
        return {
            "target": response.get("target") or {},
            "candidates": list(response.get("applied", []) or []),
        }
    raise ValueError("Unknown feedback operation")


def _change_hash(operation: str, response: Dict[str, Any]) -> str:
    canonical = json.dumps(_canonical_change_set(operation, response), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _operation_tools(operation: str) -> Tuple[Any, str]:
    if operation == "spacing":
        return apply_spacing, "preview_spacing_feedback"
    if operation == "kerning":
        return apply_kerning_bumper, "preview_kerning_feedback"
    if operation == "smooth_handles":
        return apply_collinear_handles_smooth, "preview_handle_smoothing_feedback"
    raise ValueError("Unknown feedback operation")


def _preview_counts(operation: str, response: Dict[str, Any]) -> Dict[str, int]:
    if operation == "spacing":
        summary = response.get("summary") or {}
        return _counts(
            reviewed=int(summary.get("okCount", 0) or 0) + int(summary.get("skippedCount", 0) or 0) + int(summary.get("errorCount", 0) or 0),
            changed=int(summary.get("okCount", 0) or 0),
            skipped=int(summary.get("skippedCount", 0) or 0),
            failed=int(summary.get("errorCount", 0) or 0),
        )
    if operation == "kerning":
        counts = response.get("counts") or {}
        return _counts(
            reviewed=int(counts.get("pairsRequested", 0) or 0),
            changed=int(counts.get("pairsToApply", 0) or 0),
            skipped=int(counts.get("pairsSkippedMissing", 0) or 0) + int(counts.get("pairsSkippedAlreadySafe", 0) or 0),
        )
    summary = response.get("summary") or {}
    return _counts(
        reviewed=int(summary.get("analyzedNodes", 0) or 0),
        changed=int(summary.get("appliedCount", 0) or 0),
        skipped=int(summary.get("skippedCount", 0) or 0),
        failed=int((summary.get("skippedSummary") or {}).get("mutation_failed", 0) or 0),
    )


def _preview_items(operation: str, response: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if operation == "spacing":
        for item in list(response.get("results", []) or [])[:120]:
            if not isinstance(item, dict):
                continue
            delta = item.get("delta") or {}
            changes = ", ".join("{} {:+g}".format(key.upper(), float(value)) for key, value in delta.items() if value is not None)
            items.append({
                "label": "{} · {}".format(item.get("glyphName") or "Glyph", item.get("masterName") or item.get("masterId") or "Master"),
                "value": item.get("status") or "ready",
                "detail": changes or item.get("reason") or "No metric delta",
            })
    elif operation == "kerning":
        for item in list(response.get("changes", []) or [])[:120]:
            items.append({
                "label": "{} {}".format(item.get("left") or "?", item.get("right") or "?"),
                "value": "{:+g} units".format(float(item.get("delta", 0) or 0)),
                "detail": "{} → {}".format(item.get("oldKerningValue"), item.get("newKerningValue")),
            })
    else:
        target = response.get("target") or {}
        for node_index in list(response.get("applied", []) or [])[:120]:
            items.append({
                "label": "Node {}".format(node_index),
                "value": "Set smooth",
                "detail": "Path {} in {}".format(target.get("pathIndex"), target.get("glyphName")),
            })
    return items


def _preview_warnings(response: Dict[str, Any]) -> List[str]:
    warnings: List[str] = [str(value) for value in list(response.get("warnings", []) or []) if value]
    for item in list(response.get("results", []) or []):
        if isinstance(item, dict):
            warnings.extend(str(value) for value in list(item.get("warnings", []) or []) if value)
    return _unique(warnings)[:24]


def _target_from_arguments(arguments: Dict[str, Any]) -> Dict[str, Any]:
    target = {"fontIndex": int(arguments.get("font_index", 0) or 0)}
    if arguments.get("glyph_name"):
        target["glyphName"] = arguments["glyph_name"]
    if arguments.get("master_id"):
        target["masterId"] = arguments["master_id"]
    return target


async def _preview(operation: str, arguments: Dict[str, Any]) -> ToolResult:
    tool, preview_tool_name = _operation_tools(operation)
    try:
        response = await _invoke_existing(tool, dict(arguments, dry_run=True, confirm=False))
    except Exception:
        logger.exception("Feedback dry run failed for %s", operation)
        return _tool_result(
            _error_payload(
                "validation_failed",
                "The dry run could not be completed safely.",
                next_action="Review the open Glyphs target and retry the dry run.",
                retry=(preview_tool_name, arguments),
            )
        )
    if response.get("ok") is False or response.get("error"):
        message = str(response.get("error") or "The dry run was rejected.")
        return _tool_result(
            _error_payload(
                _error_code(message),
                message,
                next_action="Correct the target or arguments, then run a new dry run.",
                retry=(preview_tool_name, arguments),
            )
        )

    digest = _change_hash(operation, response)
    plan_id = _store_plan(operation, arguments, digest)
    counts = _preview_counts(operation, response)
    names = {
        "spacing": "Spacing dry run",
        "kerning": "Kerning dry run",
        "smooth_handles": "Handle smoothing dry run",
    }
    summary = "Reviewed {reviewed} items; {changed} changes are ready to apply in Glyphs.".format(**counts)
    if not counts["changed"]:
        summary = "Reviewed {reviewed} items; no changes are currently suggested.".format(**counts)
    apply_action = _action(
        "Apply in Glyphs",
        "apply_feedback_plan",
        {"plan_id": plan_id, "confirm": True},
        destructive=True,
        requiresConfirmation=True,
        confirmationTitle="Apply this reviewed {} plan?".format(operation.replace("_", " ")),
        confirmationSummary=summary,
    )
    actions = [apply_action, _action("Dry Run Again", preview_tool_name, arguments)] if counts["changed"] else [_action("Dry Run Again", preview_tool_name, arguments)]
    return _tool_result(
        _payload(
            kind="dry_run",
            status="warning" if _preview_warnings(response) else "ready",
            title=names[operation],
            summary=summary,
            target=_target_from_arguments(arguments),
            items=_preview_items(operation, response),
            warnings=_preview_warnings(response),
            actions=actions,
            progress=counts,
        )
    )


@mcp.tool(
    output_schema=FEEDBACK_OUTPUT_SCHEMA,
    annotations=READ_ONLY_ANNOTATIONS,
    meta=_tool_meta(),
)
async def preview_spacing_feedback(
    font_index: int = 0,
    glyph_names: list = None,
    master_id: str = None,
    rules: list = None,
    defaults: dict = None,
    clamp: dict = None,
) -> ToolResult:
    """Preview the exact spacing changes that may later be confirmed in the app."""

    return await _preview("spacing", {
        "font_index": font_index,
        "glyph_names": glyph_names,
        "master_id": master_id,
        "rules": rules,
        "defaults": defaults,
        "clamp": clamp,
    })


@mcp.tool(
    output_schema=FEEDBACK_OUTPUT_SCHEMA,
    annotations=READ_ONLY_ANNOTATIONS,
    meta=_tool_meta(),
)
async def preview_kerning_feedback(
    font_index: int = 0,
    master_id: str = None,
    relevant_limit: int = 2000,
    include_existing: bool = True,
    pair_limit: int = 3000,
    glyph_names: list = None,
    min_gap: float = 5.0,
    scan_mode: str = "two_pass",
    scan_heights: list = None,
    dense_step: float = 10.0,
    bands: int = 8,
    result_limit: int = 200,
    pairs: list = None,
    extra_gap: float = 0.0,
    max_delta: int = 200,
) -> ToolResult:
    """Preview the exact kerning-bumper changes that may later be confirmed."""

    # The underlying compatibility tool normally truncates returned changes for
    # compact JSON responses. Feedback plans must hash the complete change set,
    # so request at least the full analyzed/explicit pair bound internally. The
    # panel still renders a bounded item list.
    try:
        complete_result_limit = max(int(result_limit or 0), int(pair_limit or 0), len(pairs or []), 1)
    except Exception:
        complete_result_limit = int(result_limit or 200)
    return await _preview("kerning", {
        "font_index": font_index,
        "master_id": master_id,
        "relevant_limit": relevant_limit,
        "include_existing": include_existing,
        "pair_limit": pair_limit,
        "glyph_names": glyph_names,
        "min_gap": min_gap,
        "scan_mode": scan_mode,
        "scan_heights": scan_heights,
        "dense_step": dense_step,
        "bands": bands,
        "result_limit": complete_result_limit,
        "pairs": pairs,
        "extra_gap": extra_gap,
        "max_delta": max_delta,
    })


@mcp.tool(
    output_schema=FEEDBACK_OUTPUT_SCHEMA,
    annotations=READ_ONLY_ANNOTATIONS,
    meta=_tool_meta(),
)
async def preview_handle_smoothing_feedback(
    font_index: int = 0,
    glyph_name: str = None,
    master_id: str = None,
    path_index: int = None,
    node_indices: list = None,
    threshold_deg: float = 3.0,
    min_handle_len: float = 5.0,
) -> ToolResult:
    """Preview collinear-handle smoothing without changing the font."""

    return await _preview("smooth_handles", {
        "font_index": font_index,
        "glyph_name": glyph_name,
        "master_id": master_id,
        "path_index": path_index,
        "node_indices": node_indices,
        "threshold_deg": threshold_deg,
        "min_handle_len": min_handle_len,
    })


@mcp.tool(
    output_schema=FEEDBACK_OUTPUT_SCHEMA,
    annotations=APPLY_ANNOTATIONS,
    meta=_tool_meta(app_only=True),
)
async def apply_feedback_plan(plan_id: str, confirm: bool = False) -> ToolResult:
    """Apply one reviewed, unexpired feedback plan from the embedded app only."""

    _purge_expired()
    if not confirm:
        return _tool_result(
            _error_payload(
                "validation_failed",
                "The reviewed plan was not applied because confirmation was not provided.",
                title="Confirmation required",
                next_action="Review the preview in the panel and explicitly confirm Apply in Glyphs.",
            )
        )
    plan = _plans.pop(str(plan_id or ""), None)
    if plan is None:
        return _tool_result(
            _error_payload(
                "plan_expired",
                "This review plan is missing, expired, or was already used.",
                title="A new dry run is required",
                next_action="Run a new dry run and review the current Glyphs state.",
            )
        )

    tool, preview_tool_name = _operation_tools(plan.operation)
    new_preview_action = _action("New Dry Run", preview_tool_name, plan.arguments)
    try:
        current = await _invoke_existing(tool, dict(plan.arguments, dry_run=True, confirm=False))
        if current.get("ok") is False or current.get("error"):
            message = str(current.get("error") or "The current Glyphs state could not be reviewed.")
            return _tool_result(
                _error_payload(
                    _error_code(message, "stale_plan"),
                    message,
                    title="Plan could not be revalidated",
                    next_action="Run a new dry run before applying changes.",
                ) | {"actions": [new_preview_action]}
            )
        if _change_hash(plan.operation, current) != plan.change_hash:
            return _tool_result(
                _error_payload(
                    "stale_plan",
                    "The reviewed change set no longer matches the open Glyphs state.",
                    title="The plan is stale",
                    next_action="Refresh the target and run a new dry run.",
                ) | {"actions": [new_preview_action]}
            )
        applied = await _invoke_existing(tool, dict(plan.arguments, dry_run=False, confirm=True))
    except Exception:
        logger.exception("Feedback apply failed or transport outcome is uncertain for %s", plan.operation)
        data = _error_payload(
            "apply_failed",
            "Glyphs did not return a certain apply result.",
            title="Apply result is uncertain",
            next_action="Inspect the font in Glyphs, then refresh and run a new dry run. Do not repeat this plan.",
        )
        data["actions"] = [new_preview_action]
        return _tool_result(data)

    if applied.get("ok") is False or applied.get("error"):
        message = str(applied.get("error") or "Glyphs rejected the apply operation.")
        data = _error_payload(
            "apply_failed",
            message,
            title="Changes were not fully applied",
            next_action="Inspect Glyphs, then refresh and run a new dry run.",
        )
        data["actions"] = [new_preview_action]
        return _tool_result(data)

    counts = _preview_counts(plan.operation, applied)
    if plan.operation == "spacing":
        summary = applied.get("summary") or {}
        counts["changed"] = int(summary.get("appliedCount", 0) or 0)
    elif plan.operation == "kerning":
        counts["changed"] = int((applied.get("counts") or {}).get("pairsApplied", 0) or 0)
    failures = counts.get("failed", 0)
    status = "partial" if failures else "success"
    title = "Changes partially applied" if failures else "Changes applied in Glyphs"
    summary_text = "Applied {changed} reviewed changes; skipped {skipped}; failed {failed}. The font was not saved.".format(**counts)
    actions = [new_preview_action] if failures else []
    partial_error = None
    if failures:
        partial_error = {
            "code": "partial_failure",
            "message": "Some reviewed changes could not be applied.",
            "recoverable": True,
            "nextAction": "Inspect Glyphs, then refresh and run a new dry run for any remaining changes.",
        }
    return _tool_result(
        _payload(
            kind="result",
            status=status,
            title=title,
            summary=summary_text,
            target=_target_from_arguments(plan.arguments),
            items=_preview_items(plan.operation, applied),
            warnings=_preview_warnings(applied),
            actions=actions,
            result=counts,
            error=partial_error,
        )
    )


@mcp.tool(
    output_schema=FEEDBACK_OUTPUT_SCHEMA,
    annotations=OPEN_ANNOTATIONS,
    meta=_tool_meta(app_only=True),
)
async def open_feedback_target(
    font_index: int = 0,
    glyph_names: list = None,
    master_id: str = None,
) -> ToolResult:
    """Open only resolved objects from an already open Glyphs font in a new tab."""

    try:
        font, error = _font_or_error(font_index)
        if error:
            return _tool_result(error)
        if glyph_names is None:
            glyph_names = []
        if not isinstance(glyph_names, list) or len(glyph_names) > 64 or any(not isinstance(name, str) or not name for name in glyph_names):
            return _tool_result(_error_payload("validation_failed", "glyph_names must contain at most 64 non-empty glyph names."))
        if not glyph_names:
            return _tool_result(_error_payload("target_not_found", "No open Glyphs objects were selected for opening."))

        if master_id is not None:
            available_master_ids = {str(getattr(master, "id", "")) for master in list(getattr(font, "masters", []) or [])}
            if str(master_id) not in available_master_ids:
                return _tool_result(_error_payload("target_not_found", "The requested master is not part of the open font."))

        layers = []
        missing = []
        for name in glyph_names:
            glyph = _glyph_for_name(font, name)
            layer = _layer_for_glyph(font, glyph, master_id)
            if layer is None:
                missing.append(name)
            else:
                layers.append(layer)
        if missing:
            return _tool_result(
                _error_payload(
                    "target_not_found",
                    "These glyphs are not resolved in the open font: {}.".format(", ".join(missing)),
                    next_action="Refresh the feedback card from the current open font.",
                )
            )
        _open_tab_on_main_thread(font, layers)
        target = _font_target(font, font_index)
        target.update({"masterId": master_id})
        return _tool_result(
            _payload(
                kind="result",
                status="success",
                title="Opened in Glyphs",
                summary="Opened {} resolved glyph{} in a Glyphs Edit tab.".format(len(layers), "" if len(layers) == 1 else "s"),
                target=target,
                items=[{"label": name, "value": "Opened"} for name in glyph_names],
                result=_counts(reviewed=len(layers), changed=len(layers)),
            )
        )
    except Exception:
        logger.exception("Unable to open feedback target in Glyphs")
        return _tool_result(
            _error_payload(
                "open_in_glyphs_failed",
                "The resolved target could not be opened in Glyphs.",
                next_action="Return to Glyphs, verify the font is still open, and refresh the feedback.",
            )
        )


__all__ = [
    "FEEDBACK_OUTPUT_SCHEMA",
    "PLAN_CAPACITY",
    "PLAN_TTL_SECONDS",
    "SCHEMA_VERSION",
    "apply_feedback_plan",
    "open_feedback_target",
    "preview_handle_smoothing_feedback",
    "preview_kerning_feedback",
    "preview_spacing_feedback",
    "show_font_feedback",
    "show_glyph_feedback",
    "show_glyphs_status",
    "show_opentype_features",
]
