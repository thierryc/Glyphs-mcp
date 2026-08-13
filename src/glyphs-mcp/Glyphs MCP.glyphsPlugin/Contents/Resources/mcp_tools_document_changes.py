# encoding: utf-8

"""One-document MCP mutation audit and public overview tool."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Iterable, Optional

from fastmcp.tools.tool import ToolResult
from GlyphsApp import Glyphs  # type: ignore[import-not-found]

from document_change_audit import DOCUMENT_CHANGE_LEDGER, overview_markdown
from mcp_tool_helpers import _font_object_id, _open_fonts_from_glyphs, _resolve_font_by_index
from tool_registration import glyphs_tool, register_tool_result_observer


logger = logging.getLogger(__name__)

AUDITED_EDIT_SAVE_TOOLS = {
    "accept_outline_candidate_session",
    "add_anchor_to_glyph",
    "add_component_to_glyph",
    "add_corner_to_all_masters",
    "add_glyph_annotation",
    "add_glyph_annotation_group",
    "apply_collinear_handles_smooth",
    "apply_feedback_plan",
    "apply_kerning_bumper",
    "apply_spacing",
    "apply_start_node_alignment",
    "apply_tunni_balance",
    "apply_unicode_assignments",
    "clear_glyph_annotations",
    "copy_glyph",
    "create_glyph",
    "delete_glyph",
    "delete_glyph_annotation",
    "discard_outline_candidate_session",
    "materialize_outline_candidate_session",
    "patch_litsquare_metadata",
    "reset_icon_grid_horizontal_center",
    "save_font",
    "set_custom_parameters",
    "set_glyph_paths",
    "set_kerning_pair",
    "set_litsquare_path_roles",
    "set_icon_grid_horizontal_center",
    "set_master_italic_angle",
    "set_master_stem_metrics",
    "set_spacing_guides",
    "set_spacing_params",
    "update_glyph_annotation",
    "update_glyph_metrics",
    "update_glyph_node_positions",
    "update_glyph_properties",
}
AUDITED_CODE_TOOLS = {"execute_code", "execute_code_with_context"}

_TARGET_ARGUMENTS = {
    "annotation_id": "annotationId",
    "annotation_index": "annotationIndex",
    "font_index": "fontIndex",
    "glyph_name": "glyphName",
    "glyph_names": "glyphNames",
    "left": "left",
    "layer_id": "layerId",
    "master_id": "masterId",
    "master_ids": "masterIds",
    "node_indices": "nodeIndices",
    "path_index": "pathIndex",
    "reference_master_id": "referenceMasterId",
    "reference_node_index": "referenceNodeIndex",
    "right": "right",
    "session_id": "candidateSessionId",
    "source_glyph": "sourceGlyph",
    "scope": "scope",
    "target_glyph": "targetGlyph",
    "target_master_ids": "targetMasterIds",
}
_PAYLOAD_TARGET_KEYS = set(_TARGET_ARGUMENTS.values()) | {
    "familyName",
    "filePath",
    "layerId",
    "layerName",
    "masterName",
    "pathCount",
    "scope",
}
_COUNT_KEYS = {
    "appliedCount",
    "changedCount",
    "changedPathCount",
    "createdCount",
    "deletedCount",
    "removedCount",
    "updatedCount",
}
_SUMMARY_KEYS = _COUNT_KEYS | {
    "applied",
    "changed",
    "failed",
    "message",
    "reviewed",
    "saved",
    "skipped",
    "status",
}
_NO_ACTION_ERROR_MARKERS = (
    "already exists",
    "does not exist",
    "is required",
    "must be",
    "no active layer",
    "no glyph",
    "not found",
    "out of range",
    "set exactly one",
)
_NO_ACTION_ERROR_CODES = {
    "duplicate_target",
    "glyph_not_found",
    "invalid_target",
    "invalid_updates",
    "master_not_found",
    "node_not_found",
    "path_locked",
    "path_not_found",
    "stale_target",
}


def _content_text(result: Any) -> Optional[str]:
    if isinstance(result, str):
        return result
    content = getattr(result, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            else:
                value = getattr(item, "text", None)
                if value:
                    parts.append(str(value))
        return "\n".join(parts) if parts else None
    return None


def _result_payload(result: Any) -> Dict[str, Any]:
    text = _content_text(result)
    if text:
        try:
            value = json.loads(text)
            if isinstance(value, dict):
                return value
        except Exception:
            pass
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return dict(structured)
    if isinstance(result, dict):
        return dict(result)
    return {}


def _payload_value(payload: Dict[str, Any], key: str) -> Any:
    if key in payload:
        return payload.get(key)
    data = payload.get("data")
    if isinstance(data, dict) and key in data:
        return data.get(key)
    summary = payload.get("summary")
    if isinstance(summary, dict) and key in summary:
        return summary.get(key)
    result = payload.get("result")
    if isinstance(result, dict) and key in result:
        return result.get(key)
    return None


def _known_counts(payload: Dict[str, Any]) -> Iterable[int]:
    values = []
    for container in (payload, payload.get("summary"), payload.get("result"), payload.get("data")):
        if not isinstance(container, dict):
            continue
        for key in _COUNT_KEYS:
            value = container.get(key)
            if isinstance(value, bool):
                continue
            try:
                values.append(int(value))
            except Exception:
                pass
        for generic_key in ("changed", "applied"):
            value = container.get(generic_key)
            if isinstance(value, list):
                values.append(len(value))
    return values


def _mutation_may_have_started(payload: Dict[str, Any]) -> bool:
    mutation_started = _payload_value(payload, "mutationStarted")
    if mutation_started is True:
        return True

    change_batch = _payload_value(payload, "changeBatch")
    if isinstance(change_batch, dict) and change_batch.get("began") is True:
        return True

    rollback = _payload_value(payload, "rollback")
    if isinstance(rollback, dict) and rollback.get("attempted") is True:
        return True
    return False


def _proved_no_action(payload: Dict[str, Any], error: Optional[BaseException]) -> bool:
    """Return true only when the result proves mutation never started."""

    if error is not None:
        # An exception can happen after a partial mutation, so retain it.
        return False

    if _mutation_may_have_started(payload):
        return False

    mutation_started = _payload_value(payload, "mutationStarted")
    if mutation_started is False:
        return True

    error_code = payload.get("errorCode")
    error_payload = payload.get("error")
    if not error_code and isinstance(error_payload, dict):
        error_code = error_payload.get("code")
    if str(error_code or "").strip().lower() in _NO_ACTION_ERROR_CODES:
        return True

    signals = list(_known_counts(payload))
    for key in ("changed", "applied"):
        value = _payload_value(payload, key)
        if isinstance(value, bool):
            signals.append(1 if value else 0)
    if signals:
        return not any(value > 0 for value in signals)

    error_value = payload.get("error") or payload.get("reason")
    if not error_value:
        return False
    error_text = _stringify(error_value, 500).lower()
    return any(marker in error_text for marker in _NO_ACTION_ERROR_MARKERS)


def _outcome(entry, payload: Dict[str, Any], error: Optional[BaseException]) -> str:
    if error is not None:
        return "failed"
    if entry.effect == "code":
        return "uncertain"
    status = str(payload.get("status") or "").lower()
    if payload.get("ok") is False or payload.get("success") is False or status == "error" or payload.get("error"):
        return "failed"
    if entry.effect == "save":
        if payload.get("success") is True or payload.get("ok") is True or status == "success":
            return "saved"
        return "uncertain"
    for key in ("changed", "applied"):
        value = _payload_value(payload, key)
        if isinstance(value, bool):
            return "changed" if value else "no_change"
    counts = list(_known_counts(payload))
    if counts:
        return "changed" if any(value > 0 for value in counts) else "no_change"
    if payload.get("ok") is True or payload.get("success") is True or status in {"success", "warning", "partial"}:
        return "succeeded"
    return "uncertain"


def _stringify(value: Any, limit: int = 300) -> str:
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
        except Exception:
            text = str(value)
    return text[:limit]


def _summary(entry, payload: Dict[str, Any], outcome: str, error: Optional[BaseException]) -> str:
    if entry.effect == "code":
        return "Opaque MCP code operation; document effects were not inspected."
    if error is not None:
        return "{} failed: {}".format(entry.title, str(error)[:360])
    summary = payload.get("summary")
    if isinstance(summary, str) and summary:
        return summary[:500]
    if isinstance(summary, dict) and summary:
        bounded_summary = {
            str(key): _bounded_value(value)
            for key, value in summary.items()
            if key in _SUMMARY_KEYS
        }
        if bounded_summary:
            return _stringify(bounded_summary, 500)
    for key in ("message", "error", "reason", "hint"):
        value = payload.get(key)
        if value:
            return _stringify(value, 500)
    return "{} reported {}.".format(entry.title, outcome.replace("_", " "))


def _warnings(payload: Dict[str, Any]) -> list:
    values = payload.get("warnings")
    if not isinstance(values, list):
        return []
    return [_stringify(value) for value in values[:8]]


def _bounded_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_bounded_value(item) for item in value[:64]]
    if isinstance(value, tuple):
        return [_bounded_value(item) for item in value[:64]]
    if isinstance(value, dict):
        return {str(key)[:80]: _bounded_value(item) for key, item in list(value.items())[:32]}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value[:160] if isinstance(value, str) else value
    return str(value)[:160]


def _event_target(arguments: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    payload_target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    target = {
        str(key): _bounded_value(value)
        for key, value in payload_target.items()
        if key in _PAYLOAD_TARGET_KEYS
    }
    for source, destination in _TARGET_ARGUMENTS.items():
        value = arguments.get(source)
        if value is not None and destination not in target:
            target[destination] = _bounded_value(value)
    return target


def _font_target(font: Any, font_index: int) -> Dict[str, Any]:
    filepath = getattr(font, "filepath", None)
    return {
        "objectId": _font_object_id(font),
        "fontIndex": int(font_index),
        "familyName": getattr(font, "familyName", None) or "Untitled font",
        "filePath": str(filepath) if filepath else None,
        "fileState": "Saved" if filepath else "Unsaved",
    }


def _font_index_from_payload(payload: Dict[str, Any]) -> Optional[int]:
    values = [payload.get("fontIndex")]
    target = payload.get("target")
    if isinstance(target, dict):
        values.append(target.get("fontIndex"))
    data = payload.get("data")
    if isinstance(data, dict):
        values.append(data.get("fontIndex"))
        nested_target = data.get("target")
        if isinstance(nested_target, dict):
            values.append(nested_target.get("fontIndex"))
    for value in values:
        try:
            return int(value)
        except Exception:
            continue
    return None


def _resolve_font(entry, arguments: Dict[str, Any], payload: Dict[str, Any]):
    fonts = list(_open_fonts_from_glyphs(Glyphs))
    if entry.name == "execute_code":
        tracked = DOCUMENT_CHANGE_LEDGER.tracked_object_id()
        if tracked is not None:
            for index, font in enumerate(fonts):
                if _font_object_id(font) == tracked:
                    return font, index
        if len(fonts) == 1:
            return fonts[0], 0
        return None, None

    value = arguments.get("font_index")
    if value is None:
        value = _font_index_from_payload(payload)
    if value is not None:
        try:
            index = int(value)
            if 0 <= index < len(fonts):
                return fonts[index], index
        except Exception:
            pass

    try:
        active = getattr(Glyphs, "font", None)
    except Exception:
        active = None
    if active is not None:
        for index, font in enumerate(fonts):
            if font is active or _font_object_id(font) == _font_object_id(active):
                return font, index
    if len(fonts) == 1:
        return fonts[0], 0
    return None, None


def _skip_call(entry, arguments: Dict[str, Any]) -> bool:
    if entry.effect not in {"edit", "save", "code"}:
        return True
    if arguments.get("dry_run") is True:
        return True
    if "confirm" in arguments and arguments.get("confirm") is not True:
        return True
    return False


def observe_document_change(*, entry, arguments, result=None, error=None) -> None:
    """Fail-open registration observer for one-document mutation activity."""

    if _skip_call(entry, arguments):
        return
    payload = _result_payload(result)
    if entry.effect != "code" and _proved_no_action(payload, error):
        return
    font, font_index = _resolve_font(entry, arguments, payload)
    if font is None:
        DOCUMENT_CHANGE_LEDGER.record_unattributed()
        return
    document_target = _font_target(font, font_index)
    outcome = _outcome(entry, payload, error)
    event = {
        "tool": entry.name,
        "title": entry.title,
        "effect": entry.effect,
        "outcome": outcome,
        "target": _event_target(arguments, payload),
        "summary": _summary(entry, payload, outcome, error),
        "warnings": _warnings(payload),
        "opaque": entry.effect == "code",
    }
    DOCUMENT_CHANGE_LEDGER.record(document_target, event)


register_tool_result_observer(observe_document_change)


@glyphs_tool()
async def get_document_change_overview(
    font_index: Optional[int] = None,
    include_entries: bool = True,
    limit: int = 50,
) -> ToolResult:
    """Read the bounded MCP mutation overview for one tracked open document."""

    snapshot = DOCUMENT_CHANGE_LEDGER.snapshot(include_entries=include_entries, limit=limit)
    if snapshot.get("status") == "idle":
        text = "Glyphs MCP Changes: no document changes are being tracked."
        return ToolResult(content=text, structured_content=snapshot)
    if font_index is None:
        font = None
        resolved_index = None
        tracked_object_id = DOCUMENT_CHANGE_LEDGER.tracked_object_id()
        for index, candidate in enumerate(_open_fonts_from_glyphs(Glyphs)):
            if _font_object_id(candidate) == tracked_object_id:
                font = candidate
                resolved_index = index
                break
    else:
        font, _fonts = _resolve_font_by_index(Glyphs, font_index)
        resolved_index = font_index
    if font is None:
        payload = dict(snapshot)
        payload.update(
            {
                "ok": False,
                "status": "error",
                "entries": [],
                "error": {
                    "code": "target_not_found",
                    "message": (
                        "The tracked document is no longer open in Glyphs."
                        if font_index is None
                        else "Font index {} is not currently open in Glyphs.".format(font_index)
                    ),
                    "recoverable": True,
                },
            }
        )
        return ToolResult(content="Glyphs MCP Changes: requested font is not open.", structured_content=payload)
    DOCUMENT_CHANGE_LEDGER.update_target(_font_target(font, resolved_index))
    if DOCUMENT_CHANGE_LEDGER.tracked_object_id() != _font_object_id(font):
        payload = DOCUMENT_CHANGE_LEDGER.snapshot(include_entries=False, limit=limit)
        payload.update(
            {
                "ok": False,
                "status": "error",
                "entries": [],
                "error": {
                    "code": "tracked_document_mismatch",
                    "message": "The requested font is not the document tracked by the current change session.",
                    "recoverable": True,
                },
            }
        )
        return ToolResult(content="Glyphs MCP Changes: requested font is not the tracked document.", structured_content=payload)
    snapshot = DOCUMENT_CHANGE_LEDGER.snapshot(include_entries=include_entries, limit=limit)
    counts = snapshot.get("counts") or {}
    text = "Glyphs MCP Changes: {} changed, {} succeeded, {} failed, {} uncertain, {} saves.".format(
        counts.get("changed", 0),
        counts.get("succeeded", 0),
        counts.get("failed", 0),
        counts.get("uncertain", 0),
        counts.get("saved", 0),
    )
    return ToolResult(content=text, structured_content=snapshot)


def current_change_overview(limit=100):
    return DOCUMENT_CHANGE_LEDGER.snapshot(include_entries=True, limit=limit)


def reset_document_change_overview():
    DOCUMENT_CHANGE_LEDGER.reset()


def document_change_markdown(limit=100):
    return overview_markdown(current_change_overview(limit=limit))


def clear_closed_document(object_id):
    return DOCUMENT_CHANGE_LEDGER.document_closed(object_id)


def tracked_document_object_id():
    """Return the private live-object identity for native panel coordination."""

    return DOCUMENT_CHANGE_LEDGER.tracked_object_id()


__all__ = [
    "AUDITED_CODE_TOOLS",
    "AUDITED_EDIT_SAVE_TOOLS",
    "clear_closed_document",
    "current_change_overview",
    "document_change_markdown",
    "get_document_change_overview",
    "observe_document_change",
    "reset_document_change_overview",
    "tracked_document_object_id",
]
