# encoding: utf-8

from __future__ import division, print_function, unicode_literals

"""MCP controls for the native Glyphs curvature Reporter."""

from GlyphsApp import Glyphs  # type: ignore[import-not-found]

from glyphs_curve_reporter import (
    REPORTER_CLASS_NAME,
    REPORTER_MENU_PATH,
    SUPPORTED_OVERLAYS,
    overlay_features,
    set_overlay_features,
)
from mcp_runtime import mcp
from tool_registration import glyphs_tool
from mcp_tool_helpers import _run_on_main_thread, _safe_json


OVERLAY_DATA_VERSION = 1


def _class_name(value):
    try:
        name = value.__class__.__name__
        if name:
            return str(name)
    except Exception:
        pass
    try:
        return str(value.className())
    except Exception:
        return ""


def _reporter_values(attribute):
    try:
        return list(getattr(Glyphs, attribute, None) or [])
    except Exception:
        return []


def _find_reporter():
    for reporter in _reporter_values("reporters"):
        if _class_name(reporter) == REPORTER_CLASS_NAME:
            return reporter
    return None


def _reporter_is_active(reporter):
    if reporter is None:
        return False
    for active in _reporter_values("activeReporters"):
        if active is reporter or _class_name(active) == REPORTER_CLASS_NAME:
            return True
    return False


def _reporter_snapshot(reporter):
    if reporter is None:
        return None
    try:
        snapshot_method = getattr(reporter, "overlayStateSnapshot", None)
        if callable(snapshot_method):
            snapshot = snapshot_method()
            if isinstance(snapshot, dict):
                return snapshot
    except Exception:
        pass
    return None


def _state_on_main_thread():
    reporter = _find_reporter()
    enabled = _reporter_is_active(reporter)
    snapshot = _reporter_snapshot(reporter) or {}
    return {
        "ok": True,
        "overlayDataVersion": OVERLAY_DATA_VERSION,
        "available": reporter is not None,
        "enabled": bool(enabled),
        "reporterClass": REPORTER_CLASS_NAME,
        "menuPath": REPORTER_MENU_PATH,
        "lastDraw": snapshot.get("lastDraw"),
        "lastError": snapshot.get("lastError"),
        "overlays": list(snapshot.get("overlays") or overlay_features()),
        "fontChanged": False,
        "fontSaved": False,
        "uiOnly": True,
        "warnings": [],
    }


def _set_state_on_main_thread(enabled, overlays=None):
    before = _state_on_main_thread()
    reporter = _find_reporter()
    if reporter is None:
        return {
            "ok": False,
            "overlayDataVersion": OVERLAY_DATA_VERSION,
            "available": False,
            "enabledBefore": False,
            "enabledAfter": False,
            "reporterClass": REPORTER_CLASS_NAME,
            "menuPath": REPORTER_MENU_PATH,
            "fontChanged": False,
            "fontSaved": False,
            "uiOnly": True,
            "error": "The native curvature Reporter is not loaded. Restart Glyphs after installing this plug-in build.",
        }

    if overlays is not None:
        set_overlay_features(overlays)
    action_name = "activateReporter" if enabled else "deactivateReporter"
    action = getattr(Glyphs, action_name, None)
    if not callable(action):
        return {
            "ok": False,
            "overlayDataVersion": OVERLAY_DATA_VERSION,
            "available": True,
            "enabledBefore": bool(before.get("enabled")),
            "enabledAfter": bool(before.get("enabled")),
            "reporterClass": REPORTER_CLASS_NAME,
            "menuPath": REPORTER_MENU_PATH,
            "fontChanged": False,
            "fontSaved": False,
            "uiOnly": True,
            "error": "Glyphs does not expose the {} API in this runtime.".format(action_name),
        }

    action(reporter)
    redraw = getattr(Glyphs, "redraw", None)
    if callable(redraw):
        redraw()
    after = _state_on_main_thread()
    verified = bool(after.get("enabled")) is bool(enabled)
    return {
        "ok": bool(verified),
        "overlayDataVersion": OVERLAY_DATA_VERSION,
        "available": True,
        "enabledBefore": bool(before.get("enabled")),
        "enabledAfter": bool(after.get("enabled")),
        "reporterClass": REPORTER_CLASS_NAME,
        "menuPath": REPORTER_MENU_PATH,
        "lastDraw": after.get("lastDraw"),
        "lastError": after.get("lastError"),
        "overlays": list(after.get("overlays") or []),
        "fontChanged": False,
        "fontSaved": False,
        "uiOnly": True,
        "warnings": [] if verified else [
            {
                "code": "reporter_state_verification_failed",
                "requestedEnabled": bool(enabled),
                "actualEnabled": bool(after.get("enabled")),
            }
        ],
        **({} if verified else {"error": "Glyphs did not report the requested curvature overlay state."}),
    }


@glyphs_tool()
async def set_curve_review_overlay(enabled: bool = True, overlays: list = None) -> str:
    """Control native curvature and curve-event overlays in Glyphs Edit View.

    This changes only Glyphs' Reporter display state. It never changes, dirties,
    or saves a font. The same toggle is available at View > Show Glyphs MCP
    Curvature. After enabling it, inspect the glyph directly in Glyphs; teal
    teeth show positive signed curvature and pink teeth show negative signed
    curvature. Pass ``overlays=["curve_events"]`` for extrema, inflections,
    cusps, and continuity warnings, or include both supported values. Omitting
    ``overlays`` preserves the current selection and defaults to curvature.
    Raw editable paths are analyzed and components are reported as omitted.
    Use ``review_curve_quality`` for the corresponding JSON metrics.
    """

    if type(enabled) is not bool:
        return _safe_json(
            {
                "ok": False,
                "overlayDataVersion": OVERLAY_DATA_VERSION,
                "available": None,
                "reporterClass": REPORTER_CLASS_NAME,
                "menuPath": REPORTER_MENU_PATH,
                "fontChanged": False,
                "fontSaved": False,
                "uiOnly": True,
                "error": "enabled must be a boolean",
            }
        )
    if overlays is not None:
        if (
            not isinstance(overlays, list)
            or not overlays
            or len(overlays) != len(set(overlays))
            or any(not isinstance(value, str) or value not in SUPPORTED_OVERLAYS for value in overlays)
        ):
            return _safe_json(
                {
                    "ok": False,
                    "overlayDataVersion": OVERLAY_DATA_VERSION,
                    "available": None,
                    "reporterClass": REPORTER_CLASS_NAME,
                    "menuPath": REPORTER_MENU_PATH,
                    "fontChanged": False,
                    "fontSaved": False,
                    "uiOnly": True,
                    "error": "overlays must contain unique curvature and/or curve_events values",
                }
            )
    try:
        return _safe_json(
            _run_on_main_thread(lambda: _set_state_on_main_thread(enabled, overlays))
        )
    except Exception as error:
        return _safe_json(
            {
                "ok": False,
                "overlayDataVersion": OVERLAY_DATA_VERSION,
                "available": None,
                "reporterClass": REPORTER_CLASS_NAME,
                "menuPath": REPORTER_MENU_PATH,
                "fontChanged": False,
                "fontSaved": False,
                "uiOnly": True,
                "error": "Unable to update the native curvature overlay: {}".format(error),
            }
        )


@glyphs_tool()
async def get_curve_review_overlay_state() -> str:
    """Return native curvature Reporter availability, state, and last-draw data.

    The bounded last-draw record confirms the glyph/layer, cubic count, comb
    stroke count, clamp/cap state, and components omitted by the raw-path-only
    overlay. This tool is read-only and never changes or saves a font.
    """

    try:
        return _safe_json(_run_on_main_thread(_state_on_main_thread))
    except Exception as error:
        return _safe_json(
            {
                "ok": False,
                "overlayDataVersion": OVERLAY_DATA_VERSION,
                "available": None,
                "enabled": None,
                "reporterClass": REPORTER_CLASS_NAME,
                "menuPath": REPORTER_MENU_PATH,
                "fontChanged": False,
                "fontSaved": False,
                "uiOnly": True,
                "error": "Unable to inspect the native curvature overlay: {}".format(error),
            }
        )


__all__ = [
    "get_curve_review_overlay_state",
    "set_curve_review_overlay",
]
