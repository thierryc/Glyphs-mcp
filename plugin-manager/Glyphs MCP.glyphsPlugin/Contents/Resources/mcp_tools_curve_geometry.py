# encoding: utf-8

from __future__ import division, print_function, unicode_literals

"""Cleanroom cubic-geometry review and guarded mutation tools."""

import json
import math

from GlyphsApp import Glyphs  # type: ignore[import-not-found]

from mcp_runtime import mcp
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

import outline_geometry_engine


MAX_REVIEW_SEGMENTS = 512
POSITION_TOLERANCE = 1.0e-5
GRID_POLICIES = ("font", "continuous")


def _position_values(node):
    position = getattr(node, "position", None)
    return (float(getattr(position, "x", 0.0)), float(getattr(position, "y", 0.0)))


def _plain_nodes(path):
    out = []
    for index, node in enumerate(list(getattr(path, "nodes", []) or [])):
        x, y = _position_values(node)
        out.append(
            {
                "nodeIndex": int(index),
                "x": x,
                "y": y,
                "type": _normalized_node_type(node),
                "smooth": bool(getattr(node, "smooth", False)),
            }
        )
    return out


def _topology_signature(path):
    nodes = list(getattr(path, "nodes", []) or [])
    return {
        "closed": bool(getattr(path, "closed", True)),
        "nodeCount": len(nodes),
        "nodeTypes": tuple(_normalized_node_type(node) for node in nodes),
        "smooth": tuple(bool(getattr(node, "smooth", False)) for node in nodes),
    }


def _upm(font):
    try:
        value = float(getattr(font, "upm", 1000.0) or 1000.0)
    except (TypeError, ValueError):
        value = 1000.0
    return value if math.isfinite(value) and value > 0.0 else 1000.0


def _font_grid(font):
    try:
        grid_length = float(getattr(font, "gridLength"))
    except (AttributeError, TypeError, ValueError, OverflowError):
        grid_length = 1.0
    if not math.isfinite(grid_length) or grid_length <= 0.0:
        return None, "font.gridLength must be a finite positive number"
    try:
        subdivision = int(getattr(font, "gridSubDivision", 1) or 1)
    except (TypeError, ValueError, OverflowError):
        subdivision = 1
    return {
        "gridLength": grid_length,
        "gridSubDivision": max(1, subdivision),
    }, None


def _normalize_grid_policy(value):
    if not isinstance(value, str) or value not in GRID_POLICIES:
        return None, "grid_policy must be one of: {}".format(", ".join(GRID_POLICIES))
    return value, None


def _shape_index(layer, path):
    try:
        for index, shape in enumerate(list(getattr(layer, "shapes", None) or [])):
            if shape is path:
                return int(index)
    except Exception:
        pass
    return None


def _omitted_component_count(layer):
    try:
        components = list(getattr(layer, "components", None) or [])
    except Exception:
        components = []
    if components:
        return len(components)
    try:
        return sum(1 for shape in list(getattr(layer, "shapes", None) or []) if not hasattr(shape, "nodes"))
    except Exception:
        return 0


def _finite_float(value, name):
    if isinstance(value, bool):
        return None, "{} must be a finite number".format(name)
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None, "{} must be a finite number".format(name)
    if not math.isfinite(number):
        return None, "{} must be a finite number".format(name)
    return number, None


def _finite_sample_count(value):
    number, error = _finite_float(value, "samples_per_curve")
    if error:
        return None, error
    try:
        return int(number), None
    except (TypeError, ValueError, OverflowError):
        return None, "samples_per_curve must be a finite number"


def _normalize_indices(value, *, required):
    if value is None:
        if required:
            return None, "segment_end_node_indices is required"
        return None, None
    if not isinstance(value, list):
        return None, "segment_end_node_indices must be a list of unique integers"
    if required and not value:
        return None, "segment_end_node_indices must not be empty"
    if any(isinstance(index, bool) or not isinstance(index, int) for index in value):
        return None, "segment_end_node_indices must be a list of unique integers"
    indices = list(value)
    if len(indices) != len(set(indices)):
        return None, "segment_end_node_indices must not contain duplicates"
    if len(indices) > MAX_REVIEW_SEGMENTS:
        return None, "segment_end_node_indices exceeds the {}-segment limit".format(MAX_REVIEW_SEGMENTS)
    return indices, None


def _resolve_target(font_index, glyph_name, master_id, path_index):
    font, fonts = _resolve_font_by_index(Glyphs, font_index)
    if not font:
        return None, _font_resolution_error(font_index, fonts, ok_key="ok")
    if not glyph_name:
        return None, {"ok": False, "error": "glyph_name is required"}
    if not master_id:
        return None, {"ok": False, "error": "master_id is required"}
    if path_index is None:
        return None, {"ok": False, "error": "path_index is required"}
    if isinstance(path_index, bool) or not isinstance(path_index, int):
        return None, {"ok": False, "error": "path_index must be an integer"}
    path_index_value = path_index

    try:
        glyph = font.glyphs[glyph_name]
    except Exception:
        glyph = None
    if not glyph:
        return None, {"ok": False, "error": "Glyph '{}' not found".format(glyph_name)}
    try:
        layer = glyph.layers[str(master_id)]
    except Exception:
        layer = None
    if not layer:
        return None, {"ok": False, "error": "Master ID '{}' not found".format(master_id)}
    paths = list(_layer_paths(layer))
    if path_index_value < 0 or path_index_value >= len(paths):
        return None, {
            "ok": False,
            "error": "path_index {} out of range. Available paths: {}".format(path_index_value, len(paths)),
        }
    path = paths[path_index_value]
    plain_nodes = _plain_nodes(path)
    grid, grid_error = _font_grid(font)
    if grid_error:
        return None, {"ok": False, "error": grid_error}
    return {
        "font": font,
        "glyph": glyph,
        "layer": layer,
        "path": path,
        "nodes": plain_nodes,
        "closed": bool(getattr(path, "closed", True)),
        "upm": _upm(font),
        "grid": grid,
        "fontFilepath": getattr(font, "filepath", None),
        "target": {
            "fontIndex": int(font_index),
            "glyphName": str(glyph_name),
            "masterId": str(master_id),
            "layerId": _get_layer_id(layer),
            "layerName": _layer_display_name(font, layer, getattr(layer, "associatedMasterId", None)),
            "pathIndex": path_index_value,
            "shapeIndex": _shape_index(layer, path),
            "omittedComponentCount": _omitted_component_count(layer),
        },
    }, None


def _result_links(target_data):
    return _glyphs_show_layer_link_fields(
        target_data.get("fontFilepath"),
        glyph_name=target_data["target"]["glyphName"],
        layer_id=target_data["target"].get("layerId"),
        label="Open {} {} in Glyphs".format(
            target_data["target"]["glyphName"], target_data["target"].get("layerName") or "layer"
        ),
    )


def _bounded_segment_indices(target_data, requested_indices):
    if requested_indices is not None:
        return requested_indices, None
    indices = outline_geometry_engine.cubic_segment_end_indices(
        target_data["nodes"], closed=target_data["closed"]
    )
    if len(indices) > MAX_REVIEW_SEGMENTS:
        return None, (
            "Path has {} cubic segments, exceeding the {}-segment review limit. "
            "Pass segment_end_node_indices to narrow the request."
        ).format(len(indices), MAX_REVIEW_SEGMENTS)
    return indices, None


@mcp.tool()
async def review_tunni_geometry(
    font_index: int = 0,
    glyph_name: str = None,
    master_id: str = None,
    path_index: int = None,
    segment_end_node_indices: list = None,
    imbalance_threshold: float = 0.05,
    min_handle_length: float = 1.0,
    grid_policy: str = "font",
) -> str:
    """Review Tunni geometry for cubic segments in one explicit glyph layer path.

    This tool is read-only. Segments are identified by their curve end-node
    index. Omitting ``segment_end_node_indices`` scans every cubic in the path.
    Results report the Tunni intersection, endpoint handle ratios, relative
    imbalance, eligibility or a stable rejection reason, and conservative
    proposed handle coordinates and deltas. With the default ``font`` grid
    policy, ``idealProposed`` retains the continuous solution while
    ``proposed`` is the authoritative deterministic grid-safe solution using
    ``font.gridLength``. Pass ``continuous`` only when fractional coordinates
    are explicitly desired. The review analyzes raw editable
    paths and reports components omitted from the path-targeted diagnostics.

    Use this review before ``apply_tunni_balance``. Eligibility is a geometry
    safety check, not an artistic quality verdict.
    """

    try:
        indices, index_error = _normalize_indices(segment_end_node_indices, required=False)
        if index_error:
            return _safe_json({"ok": False, "error": index_error})
        imbalance_value, value_error = _finite_float(imbalance_threshold, "imbalance_threshold")
        if value_error:
            return _safe_json({"ok": False, "error": value_error})
        min_handle_value, value_error = _finite_float(min_handle_length, "min_handle_length")
        if value_error:
            return _safe_json({"ok": False, "error": value_error})
        if not 0.0 <= imbalance_value <= 1.0:
            return _safe_json({"ok": False, "error": "imbalance_threshold must be between 0 and 1"})
        if min_handle_value < 1.0:
            return _safe_json({"ok": False, "error": "min_handle_length must be at least 1"})
        grid_policy_value, grid_error = _normalize_grid_policy(grid_policy)
        if grid_error:
            return _safe_json({"ok": False, "error": grid_error})
        target_data, error = _run_on_main_thread(
            lambda: _resolve_target(font_index, glyph_name, master_id, path_index)
        )
        if error:
            return _safe_json(error)
        indices, limit_error = _bounded_segment_indices(target_data, indices)
        if limit_error:
            return _safe_json({"ok": False, "error": limit_error, "target": target_data["target"]})

        segments = outline_geometry_engine.analyze_tunni_path(
            target_data["nodes"],
            closed=target_data["closed"],
            upm=target_data["upm"],
            segment_end_node_indices=indices,
            imbalance_threshold=imbalance_value,
            min_handle_length=min_handle_value,
            grid_step=(target_data["grid"]["gridLength"] if grid_policy_value == "font" else None),
        )
        reasons = {}
        for segment in segments:
            reason = segment.get("reason")
            if reason:
                reasons[str(reason)] = int(reasons.get(str(reason), 0)) + 1
        payload = {
            "ok": True,
            "geometryDataVersion": outline_geometry_engine.GEOMETRY_DATA_VERSION,
            "target": target_data["target"],
            "params": {
                "imbalanceThreshold": imbalance_value,
                "minHandleLength": min_handle_value,
                "upm": float(target_data["upm"]),
                "gridPolicy": grid_policy_value,
                "gridLength": float(target_data["grid"]["gridLength"]),
                "gridSubDivision": int(target_data["grid"]["gridSubDivision"]),
            },
            "segments": segments,
            "summary": {
                "reviewedSegmentCount": len(segments),
                "eligibleSegmentCount": sum(1 for segment in segments if segment.get("eligible")),
                "reasonCounts": reasons,
                "omittedComponentCount": target_data["target"]["omittedComponentCount"],
            },
            "notes": [
                "Read-only review; no node, layer, font, or file state was changed.",
                "Eligibility is a conservative geometry check, not an artistic quality verdict.",
            ],
        }
        payload.update(_result_links(target_data))
        return _safe_json(payload)
    except Exception as exc:
        return _safe_json({"ok": False, "error": str(exc), "errorType": type(exc).__name__})


def _point_payload(position):
    return {"x": float(position[0]), "y": float(position[1])}


def _positions_match(actual, expected):
    return (
        math.isfinite(actual[0])
        and math.isfinite(actual[1])
        and math.isfinite(expected[0])
        and math.isfinite(expected[1])
        and math.hypot(actual[0] - expected[0], actual[1] - expected[1]) <= POSITION_TOLERANCE
    )


def _snapshot_path(path):
    nodes = list(getattr(path, "nodes", []) or [])
    return {
        "nodes": nodes,
        "positions": tuple(_position_values(node) for node in nodes),
        "topology": _topology_signature(path),
    }


def _verify_path_state(path, snapshot, expected_positions):
    try:
        current_nodes = list(getattr(path, "nodes", []) or [])
    except Exception as exc:
        return "Path nodes could not be read back: {}".format(exc)
    try:
        current_topology = _topology_signature(path)
    except Exception as exc:
        return "Path topology could not be read back: {}".format(exc)
    if current_topology != snapshot["topology"]:
        return "Path topology, node types, smooth flags, or closure changed"
    for node_index, wanted in enumerate(expected_positions):
        try:
            current = _position_values(current_nodes[node_index])
        except Exception as exc:
            return "Node {} read-back failed: {}".format(node_index, exc)
        if not _positions_match(current, wanted):
            return "Node {} read-back did not match the expected position".format(node_index)
    return None


def _restore_positions(path, snapshot):
    errors = []
    for node_index, position in enumerate(snapshot["positions"]):
        try:
            snapshot["nodes"][node_index].position = (float(position[0]), float(position[1]))
        except Exception as exc:
            errors.append({"nodeIndex": int(node_index), "message": str(exc)})
    verification_error = _verify_path_state(path, snapshot, snapshot["positions"])
    if verification_error:
        errors.append({"message": verification_error})
    return errors


def _segment_disposition(segment, status):
    raw_index = segment.get("segmentEndNodeIndex")
    node_index = int(raw_index) if isinstance(raw_index, int) and not isinstance(raw_index, bool) else None
    return {
        "segmentEndNodeIndex": node_index,
        "status": str(status),
        "eligible": False,
        "reason": str(segment.get("reason") or ("not_eligible" if status == "skipped" else "invalid_segment")),
    }


def _classify_tunni_segments(reviewed):
    planned = [segment for segment in reviewed if segment.get("ok") and segment.get("eligible")]
    skipped = [
        _segment_disposition(segment, "skipped")
        for segment in reviewed
        if segment.get("ok") and not segment.get("eligible")
    ]
    rejected = [
        _segment_disposition(segment, "rejected")
        for segment in reviewed
        if not segment.get("ok")
    ]
    return planned, skipped, rejected


def _expected_handle_positions(planned, snapshot):
    expected = {}
    for segment in planned:
        indices = segment.get("nodeIndices") or {}
        proposal = segment.get("proposed") or {}
        for role in ("handle1", "handle2"):
            node_index = indices.get(role)
            point = proposal.get(role) or {}
            if isinstance(node_index, bool) or not isinstance(node_index, int):
                return None, "Invalid {} node index in current proposal".format(role)
            if node_index < 0 or node_index >= len(snapshot["nodes"]):
                return None, "Current proposal targets node {} outside the path snapshot".format(node_index)
            try:
                proposed_position = (float(point["x"]), float(point["y"]))
            except (KeyError, TypeError, ValueError, OverflowError):
                return None, "Current proposal contains an invalid {} position".format(role)
            if not all(math.isfinite(value) for value in proposed_position):
                return None, "Current proposal contains a nonfinite {} position".format(role)
            previous = expected.get(node_index)
            if previous is not None and not _positions_match(previous, proposed_position):
                return None, "Conflicting proposals target node {}".format(node_index)
            expected[node_index] = proposed_position
    return expected, None


def _applied_segment_records(planned, snapshot):
    records = []
    for segment in planned:
        handles = {}
        for role in ("handle1", "handle2"):
            node_index = int(segment["nodeIndices"][role])
            handles[role] = {
                "nodeIndex": node_index,
                "before": _point_payload(snapshot["positions"][node_index]),
                "after": _point_payload(_position_values(snapshot["nodes"][node_index])),
            }
        records.append(
            {
                "segmentEndNodeIndex": int(segment["segmentEndNodeIndex"]),
                "status": "applied",
                "handles": handles,
            }
        )
    return records


def _no_mutation_outcome():
    return {
        "ok": True,
        "applied": [],
        "verification": {
            "succeeded": True,
            "changedNodeCount": 0,
            "topologyPreserved": True,
            "untargetedNodesPreserved": True,
        },
        "rollback": {"attempted": False, "succeeded": True, "errors": []},
        "changeBatch": {"available": True, "began": False, "ended": False},
    }


def _apply_tunni_plans(target_data, planned, snapshot):
    path = target_data["path"]
    layer = target_data["layer"]
    begin_changes = getattr(layer, "beginChanges", None)
    end_changes = getattr(layer, "endChanges", None)
    if not callable(begin_changes) or not callable(end_changes):
        return {
            "ok": False,
            "error": "Confirmed mutation requires callable layer.beginChanges() and layer.endChanges().",
            "errorCode": "change_batch_unavailable",
            "applied": [],
            "verification": {"succeeded": False, "changedNodeCount": 0},
            "rollback": {"attempted": False, "succeeded": True, "errors": []},
            "changeBatch": {"available": False, "began": False, "ended": False},
        }

    expected, proposal_error = _expected_handle_positions(planned, snapshot)
    if proposal_error:
        return {
            "ok": False,
            "error": proposal_error,
            "errorCode": "invalid_current_proposal",
            "applied": [],
            "verification": {"succeeded": False, "changedNodeCount": 0},
            "rollback": {"attempted": False, "succeeded": True, "errors": []},
            "changeBatch": {"available": True, "began": False, "ended": False},
        }

    expected_positions = list(snapshot["positions"])
    for node_index, position in expected.items():
        expected_positions[node_index] = position

    began_changes = False
    ended_changes = False
    mutation_error = None
    verification_error = None
    end_changes_error = None
    rollback_attempted = False
    rollback_errors = []
    try:
        begin_changes()
        began_changes = True
    except Exception as exc:
        return {
            "ok": False,
            "error": "layer.beginChanges() failed: {}".format(exc),
            "errorCode": "begin_changes_failed",
            "applied": [],
            "verification": {"succeeded": False, "changedNodeCount": 0},
            "rollback": {"attempted": False, "succeeded": True, "errors": []},
            "changeBatch": {"available": True, "began": False, "ended": False},
        }

    try:
        try:
            for node_index, position in sorted(expected.items()):
                snapshot["nodes"][node_index].position = (float(position[0]), float(position[1]))
            verification_error = _verify_path_state(path, snapshot, expected_positions)
        except Exception as exc:
            mutation_error = str(exc)

        if mutation_error or verification_error:
            rollback_attempted = True
            rollback_errors = _restore_positions(path, snapshot)
    finally:
        try:
            end_changes()
            ended_changes = True
        except Exception as exc:
            end_changes_error = str(exc)

    if not mutation_error and not verification_error and not end_changes_error:
        verification_error = _verify_path_state(path, snapshot, expected_positions)

    if end_changes_error or verification_error:
        if not rollback_attempted:
            rollback_attempted = True
            rollback_errors = _restore_positions(path, snapshot)

    if rollback_attempted:
        rollback_verification_error = _verify_path_state(path, snapshot, snapshot["positions"])
        if rollback_verification_error:
            retry_errors = _restore_positions(path, snapshot)
            if retry_errors:
                rollback_errors.extend(retry_errors)

    failure = mutation_error or verification_error or end_changes_error
    if failure:
        if mutation_error:
            error_code = "mutation_failed"
            error_message = mutation_error
        elif end_changes_error:
            error_code = "end_changes_failed"
            error_message = "layer.endChanges() failed: {}".format(end_changes_error)
        else:
            error_code = "verification_failed"
            error_message = verification_error
        result = {
            "ok": False,
            "error": error_message,
            "errorCode": error_code,
            "applied": [],
            "verification": {"succeeded": False, "changedNodeCount": 0},
            "rollback": {
                "attempted": bool(rollback_attempted),
                "succeeded": bool(rollback_attempted) and not rollback_errors,
                "errors": rollback_errors,
            },
            "changeBatch": {"available": True, "began": began_changes, "ended": ended_changes},
        }
        if end_changes_error:
            result["endChangesError"] = end_changes_error
        return result

    changed_node_count = sum(
        1
        for node_index, position in expected.items()
        if not _positions_match(snapshot["positions"][node_index], position)
    )
    return {
        "ok": True,
        "applied": _applied_segment_records(planned, snapshot),
        "verification": {
            "succeeded": True,
            "changedNodeCount": changed_node_count,
            "topologyPreserved": True,
            "untargetedNodesPreserved": True,
        },
        "rollback": {"attempted": False, "succeeded": True, "errors": []},
        "changeBatch": {"available": True, "began": began_changes, "ended": ended_changes},
    }


def _analyze_tunni_target(
    target_data, indices, imbalance_threshold, min_handle_length, grid_policy
):
    return outline_geometry_engine.analyze_tunni_path(
        target_data["nodes"],
        closed=target_data["closed"],
        upm=target_data["upm"],
        segment_end_node_indices=indices,
        imbalance_threshold=imbalance_threshold,
        min_handle_length=min_handle_length,
        grid_step=(target_data["grid"]["gridLength"] if grid_policy == "font" else None),
    )


def _build_tunni_apply_payload(
    target_data,
    indices,
    imbalance_threshold,
    min_handle_length,
    grid_policy,
    dry_run,
    reviewed,
    outcome,
):
    planned, skipped, rejected = _classify_tunni_segments(reviewed)
    payload = {
        "ok": bool(outcome.get("ok")),
        "geometryDataVersion": outline_geometry_engine.GEOMETRY_DATA_VERSION,
        "target": target_data["target"],
        "params": {
            "imbalanceThreshold": imbalance_threshold,
            "minHandleLength": min_handle_length,
            "upm": float(target_data["upm"]),
            "gridPolicy": grid_policy,
            "gridLength": float(target_data["grid"]["gridLength"]),
            "gridSubDivision": int(target_data["grid"]["gridSubDivision"]),
        },
        "dryRun": bool(dry_run),
        "planned": planned,
        "applied": list(outcome.get("applied") or []),
        "skipped": skipped,
        "rejected": rejected,
        "verification": outcome.get("verification"),
        "rollback": outcome.get("rollback"),
        "changeBatch": outcome.get("changeBatch"),
        "summary": {
            "requestedSegmentCount": len(indices),
            "plannedSegmentCount": len(planned),
            "appliedSegmentCount": len(outcome.get("applied") or []),
            "skippedSegmentCount": len(skipped),
            "rejectedSegmentCount": len(rejected),
            "omittedComponentCount": target_data["target"]["omittedComponentCount"],
        },
        "notes": [
            "Only explicitly requested eligible segments are considered.",
            "The font was not saved.",
        ],
    }
    if not outcome.get("ok"):
        payload["error"] = outcome.get("error") or "Tunni balance mutation failed"
        if outcome.get("errorCode"):
            payload["errorCode"] = outcome["errorCode"]
        if outcome.get("endChangesError"):
            payload["endChangesError"] = outcome["endChangesError"]
    payload.update(_result_links(target_data))
    return payload


def _confirmed_tunni_transaction(
    font_index,
    glyph_name,
    master_id,
    path_index,
    indices,
    imbalance_threshold,
    min_handle_length,
    grid_policy,
):
    target_data, error = _resolve_target(font_index, glyph_name, master_id, path_index)
    if error:
        return error
    snapshot = _snapshot_path(target_data["path"])
    reviewed = _analyze_tunni_target(
        target_data,
        indices,
        imbalance_threshold,
        min_handle_length,
        grid_policy,
    )
    planned, _skipped, _rejected = _classify_tunni_segments(reviewed)
    outcome = _no_mutation_outcome()
    if planned:
        outcome = _apply_tunni_plans(target_data, planned, snapshot)
    return _build_tunni_apply_payload(
        target_data,
        indices,
        imbalance_threshold,
        min_handle_length,
        grid_policy,
        False,
        reviewed,
        outcome,
    )


@mcp.tool()
async def apply_tunni_balance(
    font_index: int = 0,
    glyph_name: str = None,
    master_id: str = None,
    path_index: int = None,
    segment_end_node_indices: list = None,
    imbalance_threshold: float = 0.05,
    min_handle_length: float = 1.0,
    grid_policy: str = "font",
    dry_run: bool = False,
    confirm: bool = False,
) -> str:
    """Preview or apply conservative Tunni balancing to explicit cubic segments.

    Pass a nonempty unique list of curve end-node indices and exactly one of
    ``dry_run=true`` or ``confirm=true``. The tool resolves the current path and
    recomputes every proposal instead of trusting earlier or caller-supplied
    coordinates. Confirmed changes move only the two intended handles per
    eligible segment, verify actual read-back coordinates and preserved
    topology, grid alignment, and roll back the complete path snapshot on
    failure. The default ``font`` policy uses ``font.gridLength``;
    ``continuous`` is an explicit opt-in.

    Use the sequence: ``review_tunni_geometry``, dry run the approved indices,
    obtain user approval, then confirm those same explicit indices. Results
    include planned, applied, skipped, and rejected records; actual before/after
    handle coordinates; verification; rollback; and change-batch status. The
    tool never saves the font.
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
                    "hint": "Use dry_run=true first; use confirm=true only after reviewing the current proposal.",
                }
            )
        indices, index_error = _normalize_indices(segment_end_node_indices, required=True)
        if index_error:
            return _safe_json({"ok": False, "error": index_error})
        imbalance_value, value_error = _finite_float(imbalance_threshold, "imbalance_threshold")
        if value_error:
            return _safe_json({"ok": False, "error": value_error})
        min_handle_value, value_error = _finite_float(min_handle_length, "min_handle_length")
        if value_error:
            return _safe_json({"ok": False, "error": value_error})
        if not 0.0 <= imbalance_value <= 1.0:
            return _safe_json({"ok": False, "error": "imbalance_threshold must be between 0 and 1"})
        if min_handle_value < 1.0:
            return _safe_json({"ok": False, "error": "min_handle_length must be at least 1"})
        grid_policy_value, grid_error = _normalize_grid_policy(grid_policy)
        if grid_error:
            return _safe_json({"ok": False, "error": grid_error})

        if confirm:
            payload = _run_on_main_thread(
                lambda: _confirmed_tunni_transaction(
                    font_index,
                    glyph_name,
                    master_id,
                    path_index,
                    indices,
                    imbalance_value,
                    min_handle_value,
                    grid_policy_value,
                )
            )
            return _safe_json(payload)

        target_data, error = _run_on_main_thread(
            lambda: _resolve_target(font_index, glyph_name, master_id, path_index)
        )
        if error:
            return _safe_json(error)
        reviewed = _analyze_tunni_target(
            target_data,
            indices,
            imbalance_value,
            min_handle_value,
            grid_policy_value,
        )
        return _safe_json(
            _build_tunni_apply_payload(
                target_data,
                indices,
                imbalance_value,
                min_handle_value,
                grid_policy_value,
                True,
                reviewed,
                _no_mutation_outcome(),
            )
        )
    except Exception as exc:
        return _safe_json({"ok": False, "error": str(exc), "errorType": type(exc).__name__})


@mcp.tool()
async def review_curve_quality(
    font_index: int = 0,
    glyph_name: str = None,
    master_id: str = None,
    path_index: int = None,
    segment_end_node_indices: list = None,
    samples_per_curve: int = 51,
    discontinuity_threshold: float = 0.25,
    spike_ratio_threshold: float = 4.0,
    include_samples: bool = False,
) -> str:
    """Review sampled signed cubic curvature for one explicit raw editable path.

    This read-only tool reports per-segment minimum, maximum, and median
    absolute curvature; signed and UPM-normalized metrics; inflection or sign
    changes; degenerate tangents; endpoint measurements; smooth-join curvature
    discontinuities; and exact maximum/median spike ratios with a JSON-safe
    infinite-ratio marker. Components omitted from path-targeted diagnostics
    are reported explicitly.

    The odd sample count is clamped to 9–257. Detailed samples are limited to
    64 selected segments, so narrow ``segment_end_node_indices`` when requesting
    ``include_samples=true`` on a larger path. Results are measurements and
    conservative threshold warnings, never an artistic score or pass/fail
    verdict. The tool does not mutate or save the font.
    """

    try:
        indices, index_error = _normalize_indices(segment_end_node_indices, required=False)
        if index_error:
            return _safe_json({"ok": False, "error": index_error})
        sample_count_value, value_error = _finite_sample_count(samples_per_curve)
        if value_error:
            return _safe_json({"ok": False, "error": value_error})
        discontinuity_value, value_error = _finite_float(discontinuity_threshold, "discontinuity_threshold")
        if value_error:
            return _safe_json({"ok": False, "error": value_error})
        spike_value, value_error = _finite_float(spike_ratio_threshold, "spike_ratio_threshold")
        if value_error:
            return _safe_json({"ok": False, "error": value_error})
        if discontinuity_value < 0.0:
            return _safe_json({"ok": False, "error": "discontinuity_threshold must be non-negative"})
        if spike_value <= 0.0:
            return _safe_json({"ok": False, "error": "spike_ratio_threshold must be greater than zero"})
        target_data, error = _run_on_main_thread(
            lambda: _resolve_target(font_index, glyph_name, master_id, path_index)
        )
        if error:
            return _safe_json(error)
        indices, limit_error = _bounded_segment_indices(target_data, indices)
        if limit_error:
            return _safe_json({"ok": False, "error": limit_error, "target": target_data["target"]})
        if include_samples and len(indices) > outline_geometry_engine.MAX_SAMPLE_DETAIL_SEGMENTS:
            return _safe_json(
                {
                    "ok": False,
                    "error": "include_samples is limited to {} selected segments".format(
                        outline_geometry_engine.MAX_SAMPLE_DETAIL_SEGMENTS
                    ),
                    "hint": "Pass a narrower segment_end_node_indices list or set include_samples=false.",
                    "target": target_data["target"],
                }
            )

        review = outline_geometry_engine.analyze_curve_quality_path(
            target_data["nodes"],
            closed=target_data["closed"],
            upm=target_data["upm"],
            segment_end_node_indices=indices,
            samples_per_curve=sample_count_value,
            discontinuity_threshold=discontinuity_value,
            spike_ratio_threshold=spike_value,
            include_samples=bool(include_samples),
        )
        payload = {
            "ok": True,
            "geometryDataVersion": review["geometryDataVersion"],
            "target": target_data["target"],
            "params": {
                "samplesPerCurve": review["samplesPerCurve"],
                "discontinuityThreshold": discontinuity_value,
                "spikeRatioThreshold": spike_value,
                "includeSamples": bool(include_samples),
                "upm": float(target_data["upm"]),
            },
            "segments": review["segments"],
            "joins": review["joins"],
            "summary": dict(
                review["summary"],
                omittedComponentCount=target_data["target"]["omittedComponentCount"],
            ),
            "notes": [
                "Read-only measurements and conservative threshold warnings; no artistic pass/fail verdict.",
                "No node, layer, font, or file state was changed.",
            ],
        }
        payload.update(_result_links(target_data))
        return _safe_json(payload)
    except Exception as exc:
        return _safe_json({"ok": False, "error": str(exc), "errorType": type(exc).__name__})


__all__ = ["review_tunni_geometry", "apply_tunni_balance", "review_curve_quality"]
