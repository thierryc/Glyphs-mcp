# encoding: utf-8

from __future__ import division, print_function, unicode_literals

import json

from GlyphsApp import Glyphs  # type: ignore[import-not-found]

from mcp_runtime import mcp
from tool_registration import glyphs_tool
from mcp_tool_helpers import (
    _font_resolution_error,
    _is_active_font,
    _resolve_font_by_index,
    _run_on_main_thread,
    _safe_json,
    _selected_glyph_names_for_font,
)

import unicode_assignment_engine


READ_ONLY_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}

APPLY_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": True,
    "idempotentHint": False,
    "openWorldHint": False,
}


def _glyph_unicodes(glyph):
    try:
        raw = getattr(glyph, "unicodes", None)
    except Exception:
        raw = None

    if raw is not None:
        try:
            values = list(raw)
        except Exception:
            values = [raw]
        if values:
            return values

    try:
        single = getattr(glyph, "unicode", None)
    except Exception:
        single = None
    return [single] if single not in (None, "") else []


def _set_glyph_unicodes(glyph, values):
    normalized = list(values or [])
    try:
        glyph.unicodes = normalized
        return
    except (AttributeError, TypeError):
        if len(normalized) > 1:
            raise
    glyph.unicode = normalized[0] if normalized else None


def _font_glyph_records(font):
    records = []
    for glyph in list(getattr(font, "glyphs", []) or []):
        name = getattr(glyph, "name", None)
        if not name:
            continue
        records.append(
            {
                "name": str(name),
                "unicodes": _glyph_unicodes(glyph),
                "export": bool(getattr(glyph, "export", True)),
            }
        )
    return records


def _font_payload(font, font_index):
    return {
        "fontIndex": int(font_index),
        "familyName": getattr(font, "familyName", "") or "",
        "filePath": getattr(font, "filepath", None),
    }


def _unique_names(values):
    names = []
    seen = set()
    for raw in list(values or []):
        name = str(raw or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def _resolve_target_names(font, scope, glyph_names):
    if glyph_names is not None:
        names = _unique_names(glyph_names)
        if not names:
            return None, {
                "ok": False,
                "error": "glyph_names was provided but contains no usable glyph names.",
            }
        return names, None

    scope_value = str(scope or "selected").strip().lower()
    if scope_value not in ("selected", "font"):
        return None, {
            "ok": False,
            "error": "scope must be 'selected' or 'font'.",
        }
    if scope_value == "font":
        names = [
            str(getattr(glyph, "name", ""))
            for glyph in list(getattr(font, "glyphs", []) or [])
            if getattr(glyph, "name", None)
        ]
    else:
        if not _is_active_font(Glyphs, font):
            return None, {
                "ok": False,
                "error": "Selected scope requires font_index to reference the active font.",
                "hint": "Activate the font, pass glyph_names, or use scope='font'.",
            }
        names = _selected_glyph_names_for_font(font)

    names = _unique_names(names)
    if not names:
        return None, {
            "ok": False,
            "error": "No glyphs to review.",
            "hint": "Select glyphs, pass glyph_names, or use scope='font'.",
        }
    return names, None


@glyphs_tool()
async def review_unicode_assignments(
    font_index: int = 0,
    scope: str = "selected",
    glyph_names: list = None,
    allocate_unencoded: bool = False,
    range_start: str = "E000",
    range_end: str = "F8FF",
    direction: str = "ascending",
    reserved_codepoints: list = None,
    previous_map: dict = None,
) -> str:
    """Review Unicode assignments and optionally propose deterministic allocations.

    The tool is font-generic. BMP PUA is only the default range; callers may
    provide any valid Unicode scalar range. Character semantics are never
    inferred from glyph names or outlines.
    """
    try:
        font, fonts = _resolve_font_by_index(Glyphs, font_index)
        if not font:
            return _safe_json(_font_resolution_error(font_index, fonts, ok_key="ok"))

        names, target_error = _resolve_target_names(font, scope, glyph_names)
        if target_error:
            target_error["font"] = _font_payload(font, font_index)
            return _safe_json(target_error)

        review = unicode_assignment_engine.review_assignments(
            _font_glyph_records(font),
            names,
            allocate_unencoded=bool(allocate_unencoded),
            range_start=range_start,
            range_end=range_end,
            direction=direction,
            reserved_codepoints=reserved_codepoints,
            previous_map=previous_map,
        )
        payload = {
            "ok": True,
            "font": _font_payload(font, font_index),
            "scope": "glyph_names" if glyph_names is not None else str(scope or "selected").strip().lower(),
            "targetGlyphs": sorted(names),
        }
        payload.update(review)
        return _safe_json(payload)
    except ValueError as exc:
        return _safe_json({"ok": False, "error": str(exc)})
    except Exception as exc:
        return _safe_json({"ok": False, "error": str(exc)})


def _mutation_outcome(font, actions):
    originals = {action["glyphName"]: list(action["before"]) for action in actions}
    changed_actions = [action for action in actions if action["changed"]]
    written = []

    try:
        for action in changed_actions:
            glyph = font.glyphs[action["glyphName"]]
            _set_glyph_unicodes(glyph, action["after"])
            written.append(action["glyphName"])

        mismatches = []
        for action in actions:
            glyph = font.glyphs[action["glyphName"]]
            actual = unicode_assignment_engine.normalize_codepoints(_glyph_unicodes(glyph))
            if actual != action["after"]:
                mismatches.append(
                    {
                        "glyphName": action["glyphName"],
                        "expectedUnicodes": list(action["after"]),
                        "actualUnicodes": actual,
                    }
                )
        if mismatches:
            raise RuntimeError("Unicode assignment verification failed: {}".format(json.dumps(mismatches)))

        return {
            "ok": True,
            "writtenGlyphNames": written,
            "verifiedGlyphNames": [action["glyphName"] for action in actions],
            "rollback": None,
        }
    except Exception as exc:
        rollback_errors = []
        for action in actions:
            name = action["glyphName"]
            try:
                _set_glyph_unicodes(font.glyphs[name], originals[name])
            except Exception as rollback_exc:
                rollback_errors.append(
                    {
                        "glyphName": name,
                        "message": str(rollback_exc),
                    }
                )

        for action in actions:
            name = action["glyphName"]
            try:
                actual = unicode_assignment_engine.normalize_codepoints(_glyph_unicodes(font.glyphs[name]))
            except Exception as verify_exc:
                rollback_errors.append(
                    {
                        "glyphName": name,
                        "message": "Rollback read-back failed: {}".format(verify_exc),
                    }
                )
                continue
            if actual != originals[name]:
                rollback_errors.append(
                    {
                        "glyphName": name,
                        "expectedUnicodes": originals[name],
                        "actualUnicodes": actual,
                        "message": "Rollback verification mismatch.",
                    }
                )

        return {
            "ok": False,
            "error": str(exc),
            "writtenGlyphNames": written,
            "verifiedGlyphNames": [],
            "rollback": {
                "attempted": True,
                "succeeded": not rollback_errors,
                "errors": rollback_errors,
            },
        }


@glyphs_tool()
async def apply_unicode_assignments(
    font_index: int = 0,
    assignments: list = None,
    dry_run: bool = False,
    confirm: bool = False,
) -> str:
    """Apply explicit Unicode assignments after full-font collision preflight.

    Use dry_run=true to preview. Mutation requires confirm=true, verifies every
    write, rolls back the batch on failure, and never saves the font.
    """
    try:
        font, fonts = _resolve_font_by_index(Glyphs, font_index)
        if not font:
            return _safe_json(_font_resolution_error(font_index, fonts, ok_key="ok"))

        preflight = unicode_assignment_engine.prepare_assignment_changes(
            _font_glyph_records(font),
            assignments,
        )
        base_payload = {
            "font": _font_payload(font, font_index),
            "dryRun": bool(dry_run),
            "confirmed": bool(confirm),
            "errors": preflight["errors"],
            "warnings": preflight["warnings"],
            "changes": preflight["actions"],
            "summary": {
                "requestedCount": len(assignments or []),
                "changedCount": sum(1 for action in preflight["actions"] if action["changed"]),
                "unchangedCount": sum(1 for action in preflight["actions"] if not action["changed"]),
                "errorCount": len(preflight["errors"]),
                "warningCount": len(preflight["warnings"]),
                "appliedCount": 0,
                "verifiedCount": 0,
            },
        }
        if not preflight["ok"]:
            base_payload["ok"] = False
            base_payload["error"] = "Unicode assignment preflight failed."
            return _safe_json(base_payload)

        if dry_run:
            base_payload["ok"] = True
            base_payload["applied"] = False
            return _safe_json(base_payload)

        if not confirm:
            base_payload["ok"] = False
            base_payload["error"] = "Refusing to apply Unicode assignments without confirm=true."
            base_payload["hint"] = "Run with dry_run=true to preview or set confirm=true to mutate."
            return _safe_json(base_payload)

        outcome = _run_on_main_thread(lambda: _mutation_outcome(font, preflight["actions"]))
        base_payload["ok"] = bool(outcome.get("ok"))
        base_payload["applied"] = bool(outcome.get("ok"))
        base_payload["writtenGlyphNames"] = outcome.get("writtenGlyphNames", [])
        base_payload["verifiedGlyphNames"] = outcome.get("verifiedGlyphNames", [])
        base_payload["rollback"] = outcome.get("rollback")
        base_payload["summary"]["appliedCount"] = len(outcome.get("writtenGlyphNames", [])) if outcome.get("ok") else 0
        base_payload["summary"]["verifiedCount"] = len(outcome.get("verifiedGlyphNames", []))
        if not outcome.get("ok"):
            base_payload["error"] = outcome.get("error") or "Unicode assignment mutation failed."
        return _safe_json(base_payload)
    except ValueError as exc:
        return _safe_json({"ok": False, "error": str(exc)})
    except Exception as exc:
        return _safe_json({"ok": False, "error": str(exc)})


__all__ = [
    "apply_unicode_assignments",
    "review_unicode_assignments",
]
