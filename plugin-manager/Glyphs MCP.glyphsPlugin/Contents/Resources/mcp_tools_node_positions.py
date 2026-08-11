# encoding: utf-8

from __future__ import annotations

"""Guarded coordinate-only edits for explicit outline nodes."""

from GlyphsApp import Glyphs  # type: ignore[import-not-found]

from mcp_tool_helpers import (
    _font_resolution_error,
    _get_layer_id,
    _glyphs_show_layer_link_fields,
    _layer_display_name,
    _layer_paths,
    _normalized_node_type,
    _resolve_font_by_index,
    _run_on_main_thread,
    _safe_json,
)
from tool_registration import glyphs_tool

import outline_node_patch_engine
import outline_node_transaction


def _point(position):
    try:
        return {"x": float(position.x), "y": float(position.y)}
    except Exception:
        return {"x": float(position[0]), "y": float(position[1])}


def _resolve_plan(font_index, glyph_name, master_id, updates, grid_policy):
    font, fonts = _resolve_font_by_index(Glyphs, font_index)
    if not font:
        return None, _font_resolution_error(font_index, fonts, ok_key="ok")
    if not glyph_name:
        return None, {"ok": False, "error": "glyph_name is required", "errorCode": "invalid_target"}
    if not master_id:
        return None, {"ok": False, "error": "master_id is required", "errorCode": "invalid_target"}
    try:
        glyph = font.glyphs[str(glyph_name)]
    except Exception:
        glyph = None
    if not glyph:
        return None, {
            "ok": False,
            "error": "Glyph '{}' not found".format(glyph_name),
            "errorCode": "glyph_not_found",
        }
    try:
        layer = glyph.layers[str(master_id)]
    except Exception:
        layer = None
    if not layer:
        return None, {
            "ok": False,
            "error": "Master ID '{}' not found".format(master_id),
            "errorCode": "master_not_found",
        }

    try:
        grid_length = getattr(font, "gridLength")
    except Exception:
        grid_length = None
    try:
        grid_subdivision = getattr(font, "gridSubDivision", 1)
    except Exception:
        grid_subdivision = 1
    prepared, error = outline_node_patch_engine.prepare_node_position_updates(
        updates,
        grid_policy=grid_policy,
        grid_length=grid_length,
        grid_subdivision=grid_subdivision,
    )
    if error:
        return None, {"ok": False, "error": error, "errorCode": "invalid_updates"}

    paths = list(_layer_paths(layer))
    snapshot = outline_node_transaction.snapshot_layer(
        layer,
        paths,
        node_type_getter=_normalized_node_type,
    )
    precondition_error, precondition_code = outline_node_transaction.validate_update_preconditions(
        snapshot,
        prepared["updates"],
    )
    if precondition_error:
        return None, {
            "ok": False,
            "error": precondition_error,
            "errorCode": precondition_code,
        }

    records = []
    for update in prepared["updates"]:
        path_index = int(update["pathIndex"])
        node_index = int(update["nodeIndex"])
        node_state = snapshot["paths"][path_index]["nodes"][node_index]
        record = dict(update)
        record["nodeType"] = node_state["type"]
        record["before"] = {
            "x": float(node_state["position"][0]),
            "y": float(node_state["position"][1]),
        }
        record["status"] = (
            "unchanged"
            if outline_node_patch_engine.positions_match(
                node_state["position"],
                (update["proposed"]["x"], update["proposed"]["y"]),
            )
            else "planned"
        )
        records.append(record)

    layer_id = _get_layer_id(layer)
    target = {
        "fontIndex": int(font_index),
        "glyphName": str(glyph_name),
        "masterId": str(master_id),
        "layerId": layer_id,
        "layerName": _layer_display_name(font, layer, getattr(layer, "associatedMasterId", None)),
        "pathIndices": sorted(set(record["pathIndex"] for record in records)),
    }
    return {
        "font": font,
        "layer": layer,
        "paths": paths,
        "target": target,
        "grid": prepared["grid"],
        "updates": records,
        "fontFilepath": getattr(font, "filepath", None),
    }, None


def _no_mutation_outcome():
    return {
        "ok": True,
        "changed": [],
        "verification": {
            "succeeded": True,
            "changedNodeCount": 0,
            "protectedStatePreserved": True,
            "untargetedNodesPreserved": True,
        },
        "rollback": {"attempted": False, "succeeded": True, "errors": []},
        "changeBatch": {"available": True, "began": False, "ended": False},
    }


def _response(plan, outcome, *, dry_run, confirm):
    applied_by_target = {
        (int(item["pathIndex"]), int(item["nodeIndex"])): item
        for item in outcome.get("changed") or []
    }
    records = []
    for planned in plan["updates"]:
        record = dict(planned)
        applied = applied_by_target.get((int(record["pathIndex"]), int(record["nodeIndex"])))
        if confirm:
            if outcome.get("ok"):
                record["actual"] = (
                    dict(applied["after"])
                    if applied is not None
                    else dict(record["before"])
                )
                record["status"] = "applied" if applied is not None else "unchanged"
            else:
                try:
                    node = plan["paths"][int(record["pathIndex"])].nodes[int(record["nodeIndex"])]
                    record["actual"] = _point(node.position)
                except Exception:
                    record["actual"] = None
                record["status"] = (
                    "rolled_back"
                    if (outcome.get("rollback") or {}).get("succeeded")
                    and (outcome.get("rollback") or {}).get("attempted")
                    else "failed"
                )
        else:
            record["actual"] = None
        records.append(record)

    snapped_count = sum(1 for record in records if record.get("snapped"))
    warnings = []
    if snapped_count:
        warnings.append(
            {
                "code": "coordinates_snapped_to_font_grid",
                "message": "{} requested node position(s) were snapped to the effective font grid.".format(
                    snapped_count
                ),
            }
        )
    payload = {
        "ok": bool(outcome.get("ok")),
        "target": plan["target"],
        "params": {"gridPolicy": plan["grid"]["requestedPolicy"]},
        "grid": dict(plan["grid"]),
        "dryRun": bool(dry_run),
        "confirmed": bool(confirm),
        "updates": records,
        "summary": {
            "requestedCount": len(records),
            "plannedChangeCount": sum(1 for record in plan["updates"] if record["status"] == "planned"),
            "unchangedCount": sum(1 for record in plan["updates"] if record["status"] == "unchanged"),
            "snappedCount": snapped_count,
            "changedCount": len(outcome.get("changed") or []) if outcome.get("ok") else 0,
            "appliedCount": len(outcome.get("changed") or []) if confirm and outcome.get("ok") else 0,
            "verifiedCount": len(records) if confirm and outcome.get("ok") else 0,
        },
        "verification": outcome.get("verification"),
        "rollback": outcome.get("rollback"),
        "changeBatch": outcome.get("changeBatch"),
        "warnings": warnings,
        "fontSaved": False,
    }
    if not outcome.get("ok"):
        error_code = outcome.get("errorCode") or "node_position_update_failed"
        if (
            error_code == "verification_failed"
            and plan["grid"].get("effectivePolicy") == "continuous"
            and "expected position" in str(outcome.get("error") or "")
        ):
            error_code = "continuous_coordinate_not_preserved"
        payload["error"] = outcome.get("error") or "Node-position update failed"
        payload["errorCode"] = error_code
    payload.update(
        _glyphs_show_layer_link_fields(
            plan.get("fontFilepath"),
            glyph_name=plan["target"]["glyphName"],
            layer_id=plan["target"].get("layerId"),
            label="Open {} {} in Glyphs".format(
                plan["target"]["glyphName"],
                plan["target"].get("layerName") or "layer",
            ),
        )
    )
    return payload


def _confirmed_update(font_index, glyph_name, master_id, updates, grid_policy):
    plan, error = _resolve_plan(font_index, glyph_name, master_id, updates, grid_policy)
    if error:
        return error
    outcome = outline_node_transaction.apply_position_updates(
        plan["layer"],
        plan["paths"],
        plan["updates"],
        node_type_getter=_normalized_node_type,
    )
    return _response(plan, outcome, dry_run=False, confirm=True)


@glyphs_tool()
async def update_glyph_node_positions(
    font_index: int = 0,
    glyph_name: str = None,
    master_id: str = None,
    updates: list = None,
    grid_policy: str = "font",
    dry_run: bool = False,
    confirm: bool = False,
) -> str:
    """Preview or atomically update explicit node coordinates on one glyph layer.

    Each update requires path_index, node_index, expected_x, expected_y,
    expected_type, x, and y. Set exactly one of dry_run=true or confirm=true.
    The default font grid policy snaps to the effective font.gridLength,
    including subdivision; a zero font grid preserves decimals. Continuous
    coordinates require grid_policy="continuous". The tool changes positions
    only, verifies the complete layer outline state, rolls back on failure, and
    never saves the font.
    """

    try:
        if type(dry_run) is not bool:
            return _safe_json({"ok": False, "error": "dry_run must be a boolean"})
        if type(confirm) is not bool:
            return _safe_json({"ok": False, "error": "confirm must be a boolean"})
        if dry_run == confirm:
            return _safe_json(
                {
                    "ok": False,
                    "error": "Set exactly one of dry_run=true or confirm=true.",
                    "hint": "Use dry_run=true to preview or confirm=true for a guarded direct apply.",
                }
            )
        if confirm:
            return _safe_json(
                _run_on_main_thread(
                    lambda: _confirmed_update(
                        font_index,
                        glyph_name,
                        master_id,
                        updates,
                        grid_policy,
                    )
                )
            )
        plan, error = _run_on_main_thread(
            lambda: _resolve_plan(font_index, glyph_name, master_id, updates, grid_policy)
        )
        if error:
            return _safe_json(error)
        return _safe_json(_response(plan, _no_mutation_outcome(), dry_run=True, confirm=False))
    except Exception as exc:
        return _safe_json(
            {
                "ok": False,
                "error": str(exc),
                "errorCode": "node_position_update_failed",
                "errorType": type(exc).__name__,
            }
        )


__all__ = ["update_glyph_node_positions"]
