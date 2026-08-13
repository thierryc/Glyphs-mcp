# encoding: utf-8

from __future__ import division, print_function, unicode_literals

"""Hybrid detached-preview, optional-layer, and guarded-promotion workflow."""

import copy
import json
import math
import time

from GlyphsApp import Glyphs  # type: ignore[import-not-found]

from mcp_runtime import mcp
from tool_registration import glyphs_tool
from mcp_tool_helpers import (
    _font_resolution_error,
    _get_layer_id,
    _glyphs_show_layer_link_fields,
    _layer_components,
    _layer_paths,
    _normalized_node_type,
    _resolve_font_by_index,
    _run_on_main_thread,
    _safe_json,
)

import mcp_tools_compensated_tuning
import mcp_tools_curve_geometry
import mcp_tools_italic
import outline_candidate_state
import outline_geometry_engine
import smoothness_engine
from versioning import get_plugin_version


CANDIDATE_DATA_VERSION = outline_candidate_state.CANDIDATE_DATA_VERSION
REPORTER_CLASS_NAME = "GlyphsMCPCandidateReporter"
REPORTER_MENU_PATH = "View > Show Glyphs MCP Candidate"
FONT_MANIFEST_KEY = "com.thierrycharbonnel.glyphs-mcp.outlineCandidates.v1"
LAYER_METADATA_KEY = "com.thierrycharbonnel.glyphs-mcp.outlineCandidate.v1"
MAX_DIFFS = 400
POSITION_TOLERANCE = 1.0e-5
TOOL_VERSION = get_plugin_version()


class _TopologyMismatchError(ValueError):
    def __init__(self, glyph_name, mismatch):
        self.glyph_name = str(glyph_name or "")
        self.mismatch = copy.deepcopy(mismatch or {"field": "topology"})
        super().__init__(
            "topology_change_blocked:{}:{}".format(
                self.glyph_name,
                self.mismatch.get("field") or "topology",
            )
        )


def _point_values(value):
    try:
        return float(value.x), float(value.y)
    except Exception:
        return float(value[0]), float(value[1])


def _record_candidate_proposal(proposals, proposal_key, point):
    previous = proposals.get(proposal_key)
    if previous is not None and (
        abs(float(previous["x"]) - float(point["x"])) > 1e-9
        or abs(float(previous["y"]) - float(point["y"])) > 1e-9
    ):
        raise ValueError("conflicting_candidate_proposals")
    proposals[proposal_key] = point


def _plain_value(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _plain_value(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_plain_value(item) for item in value]
    try:
        return [_plain_value(item) for item in list(value)]
    except Exception:
        return str(value)


def _collection_signature(items, fields):
    result = []
    for item in list(items or []):
        result.append({field: _plain_value(getattr(item, field, None)) for field in fields})
    return result


def _component_snapshot(component):
    transform = getattr(component, "transform", None)
    try:
        transform = [float(value) for value in list(transform)]
    except Exception:
        transform = None
    smart_values = getattr(component, "smartComponentValues", None)
    try:
        smart_values = {str(key): float(value) for key, value in dict(smart_values or {}).items()}
    except Exception:
        smart_values = _plain_value(smart_values)
    return {
        "name": str(getattr(component, "componentName", None) or getattr(component, "name", "") or ""),
        "transform": transform,
        "smartValues": smart_values,
        "alignment": _plain_value(getattr(component, "automaticAlignment", None)),
    }


def _anchor_snapshot(anchor):
    try:
        x, y = _point_values(getattr(anchor, "position", None))
    except Exception:
        x, y = 0.0, 0.0
    return {"name": str(getattr(anchor, "name", "") or ""), "x": x, "y": y}


def _user_data_signature(owner, ignored=()):
    try:
        values = dict(getattr(owner, "userData", None) or {})
    except Exception:
        return {}
    return {
        str(key): _plain_value(value)
        for key, value in sorted(values.items(), key=lambda pair: str(pair[0]))
        if str(key) not in set(str(item) for item in ignored)
    }


def _layer_snapshot(layer):
    paths = []
    for path in list(_layer_paths(layer)):
        nodes = []
        for node in list(getattr(path, "nodes", None) or []):
            x, y = _point_values(getattr(node, "position", None))
            if not math.isfinite(x) or not math.isfinite(y):
                raise ValueError("nonfinite_coordinate")
            nodes.append(
                {
                    "x": x,
                    "y": y,
                    "type": _normalized_node_type(node),
                    "smooth": bool(getattr(node, "smooth", False)),
                    "protected": {
                        "name": _plain_value(getattr(node, "name", None)),
                        "userData": _user_data_signature(node),
                    },
                }
            )
        paths.append(
            {
                "closed": bool(getattr(path, "closed", True)),
                "nodes": nodes,
                "protected": {
                    "attributes": _plain_value(getattr(path, "attributes", None)),
                    "userData": _user_data_signature(path),
                },
            }
        )
    components = [_component_snapshot(item) for item in list(_layer_components(layer))]
    anchors = [_anchor_snapshot(item) for item in list(getattr(layer, "anchors", None) or [])]
    shape_order = []
    path_index = 0
    component_index = 0
    for shape in list(getattr(layer, "shapes", None) or []):
        if hasattr(shape, "nodes"):
            shape_order.append({"kind": "path", "index": path_index})
            path_index += 1
        else:
            shape_order.append({"kind": "component", "index": component_index})
            component_index += 1
    if not shape_order:
        shape_order = ([{"kind": "path", "index": index} for index in range(len(paths))] +
                       [{"kind": "component", "index": index} for index in range(len(components))])
    try:
        width = float(getattr(layer, "width", 0.0) or 0.0)
    except Exception:
        width = 0.0
    if not math.isfinite(width):
        raise ValueError("nonfinite_width")
    return {
        "paths": paths,
        "components": components,
        "anchors": anchors,
        "shapeOrder": shape_order,
        "width": width,
        "protected": {
            "hints": _collection_signature(getattr(layer, "hints", None), ("name", "type", "horizontal")),
            "guides": _collection_signature(getattr(layer, "guides", None), ("name", "angle", "locked")),
            "annotations": _collection_signature(getattr(layer, "annotations", None), ("text", "type", "angle")),
            "userData": _user_data_signature(layer, ignored=(LAYER_METADATA_KEY,)),
        },
    }


def _path_direction(path):
    try:
        value = int(getattr(path, "direction"))
    except Exception:
        return None
    return value if value in (-1, 1) else None


def _display_paths_with_directions(layer, paths):
    result = copy.deepcopy(list(paths or []))
    for record, path in zip(result, list(_layer_paths(layer))):
        direction = _path_direction(path)
        if direction is not None:
            record["direction"] = direction
    return result


def _topology(snapshot):
    return {
        "paths": [
            {
                "closed": bool(path.get("closed")),
                "types": [node.get("type") for node in path.get("nodes") or []],
                "nodeProtected": [node.get("protected") or {} for node in path.get("nodes") or []],
                "pathProtected": path.get("protected") or {},
            }
            for path in snapshot.get("paths") or []
        ],
        "shapeOrder": snapshot.get("shapeOrder") or [],
        "componentNames": [item.get("name") for item in snapshot.get("components") or []],
        "anchorNames": [item.get("name") for item in snapshot.get("anchors") or []],
        "protected": snapshot.get("protected") or {},
    }


def _bounded_mismatch_value(value, depth=0):
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= 160 else value[:157] + "..."
    if depth >= 3:
        return "<{}>".format(type(value).__name__)
    if isinstance(value, dict):
        keys = sorted(value, key=str)
        result = {
            str(key): _bounded_mismatch_value(value[key], depth + 1)
            for key in keys[:8]
        }
        if len(keys) > 8:
            result["__omittedKeyCount"] = len(keys) - 8
        return result
    if isinstance(value, (list, tuple)):
        result = [_bounded_mismatch_value(item, depth + 1) for item in list(value)[:8]]
        if len(value) > 8:
            result.append({"__omittedItemCount": len(value) - 8})
        return result
    return _bounded_mismatch_value(str(value), depth + 1)


def _mismatch(field, source, candidate):
    return {
        "field": str(field),
        "source": _bounded_mismatch_value(source),
        "candidate": _bounded_mismatch_value(candidate),
    }


def _first_value_mismatch(source, candidate, field):
    if type(source) is not type(candidate):
        return _mismatch(field, source, candidate)
    if isinstance(source, dict):
        source_keys = set(source)
        candidate_keys = set(candidate)
        if source_keys != candidate_keys:
            missing = sorted(source_keys - candidate_keys, key=str)
            extra = sorted(candidate_keys - source_keys, key=str)
            key = missing[0] if missing else extra[0]
            return _mismatch(
                "{}.{}".format(field, key),
                source.get(key, "<missing>"),
                candidate.get(key, "<missing>"),
            )
        for key in sorted(source_keys, key=str):
            different = _first_value_mismatch(
                source[key],
                candidate[key],
                "{}.{}".format(field, key),
            )
            if different:
                return different
        return None
    if isinstance(source, (list, tuple)):
        if len(source) != len(candidate):
            return _mismatch("{}.length".format(field), len(source), len(candidate))
        for index, (source_item, candidate_item) in enumerate(zip(source, candidate)):
            different = _first_value_mismatch(
                source_item,
                candidate_item,
                "{}[{}]".format(field, index),
            )
            if different:
                return different
        return None
    if source != candidate:
        return _mismatch(field, source, candidate)
    return None


def _topology_mismatch(source, candidate):
    source_topology = _topology(source)
    candidate_topology = _topology(candidate)
    source_paths = source_topology["paths"]
    candidate_paths = candidate_topology["paths"]
    if len(source_paths) != len(candidate_paths):
        return _mismatch("paths.length", len(source_paths), len(candidate_paths))
    for path_index, (source_path, candidate_path) in enumerate(zip(source_paths, candidate_paths)):
        prefix = "paths[{}]".format(path_index)
        if source_path["closed"] != candidate_path["closed"]:
            return _mismatch(
                "{}.closed".format(prefix),
                source_path["closed"],
                candidate_path["closed"],
            )
        if len(source_path["types"]) != len(candidate_path["types"]):
            return _mismatch(
                "{}.types.length".format(prefix),
                len(source_path["types"]),
                len(candidate_path["types"]),
            )
        different = _first_value_mismatch(
            source_path["types"],
            candidate_path["types"],
            "{}.types".format(prefix),
        )
        if different:
            return different
        different = _first_value_mismatch(
            source_path["nodeProtected"],
            candidate_path["nodeProtected"],
            "{}.nodeProtected".format(prefix),
        )
        if different:
            return different
        different = _first_value_mismatch(
            source_path["pathProtected"],
            candidate_path["pathProtected"],
            "{}.pathProtected".format(prefix),
        )
        if different:
            return different
    for field in ("shapeOrder", "componentNames", "anchorNames", "protected"):
        different = _first_value_mismatch(
            source_topology[field],
            candidate_topology[field],
            field,
        )
        if different:
            return different
    return None


def _duplicate_name(names):
    seen = set()
    for name in names:
        if name in seen:
            return name
        seen.add(name)
    return None


def _align_italic_anchor_records(source, candidate):
    source_anchors = list(source.get("anchors") or [])
    candidate_anchors = list(candidate.get("anchors") or [])
    source_names = [str(item.get("name") or "") for item in source_anchors]
    candidate_names = [str(item.get("name") or "") for item in candidate_anchors]
    if len(source_names) != len(candidate_names):
        return candidate, _mismatch("anchorNames.length", len(source_names), len(candidate_names))
    source_duplicate = _duplicate_name(source_names)
    candidate_duplicate = _duplicate_name(candidate_names)
    if source_duplicate is not None or candidate_duplicate is not None:
        return candidate, _mismatch("anchorNames.unique", source_names, candidate_names)
    if set(source_names) != set(candidate_names):
        return candidate, _mismatch("anchorNames.identity", source_names, candidate_names)
    by_name = {str(item.get("name") or ""): item for item in candidate_anchors}
    aligned = copy.deepcopy(candidate)
    aligned["anchors"] = [copy.deepcopy(by_name[name]) for name in source_names]
    return aligned, None


def _italic_topology_mismatch(source, candidate):
    aligned, anchor_mismatch = _align_italic_anchor_records(source, candidate)
    return aligned, anchor_mismatch or _topology_mismatch(source, aligned)


def _raise_topology_mismatch(glyph_name, mismatch):
    raise _TopologyMismatchError(glyph_name, mismatch)


def _italic_preview_error_payload(error):
    payload = {
        "ok": False,
        "candidateDataVersion": CANDIDATE_DATA_VERSION,
        "error": str(error),
    }
    if isinstance(error, _TopologyMismatchError):
        mismatch = error.mismatch
        payload["errorType"] = "topology_change_blocked"
        payload["topologyMismatch"] = {
            "glyphName": error.glyph_name,
            "field": mismatch.get("field") or "topology",
            "source": _bounded_mismatch_value(mismatch.get("source")),
            "candidate": _bounded_mismatch_value(mismatch.get("candidate")),
        }
    return payload


def _fingerprint(snapshot):
    value = copy.deepcopy(snapshot)
    value.pop("displayPaths", None)
    return outline_candidate_state.fingerprint(value)


def _font_key(font):
    filepath = getattr(font, "filepath", None)
    return str(filepath) if filepath else "memory:{}".format(id(font))


def _layer_for_id(glyph, layer_id):
    try:
        layer = glyph.layers[str(layer_id)]
        if layer is not None:
            return layer
    except Exception:
        pass
    for layer in list(getattr(glyph, "layers", None) or []):
        if str(_get_layer_id(layer)) == str(layer_id):
            return layer
    return None


def _glyph_for_name(font, glyph_name):
    try:
        return font.glyphs[str(glyph_name)]
    except Exception:
        return None


def _target_value(target, snake, camel=None):
    if not isinstance(target, dict):
        return None
    if snake in target:
        return target.get(snake)
    return target.get(camel or snake)


def _strict_indices(value, name):
    if not isinstance(value, list) or not value:
        raise ValueError("{} must be a nonempty list of unique integers".format(name))
    if any(type(item) is not int for item in value) or len(value) != len(set(value)):
        raise ValueError("{} must be a nonempty list of unique integers".format(name))
    return list(value)


def _strict_targets(targets, *, indices_name, indices_camel):
    if not isinstance(targets, list) or not targets:
        raise ValueError("targets must be a nonempty list")
    normalized = []
    seen = set()
    for target in targets:
        master_id = _target_value(target, "master_id", "masterId")
        path_index = _target_value(target, "path_index", "pathIndex")
        indices = _strict_indices(_target_value(target, indices_name, indices_camel), indices_name)
        if not master_id:
            raise ValueError("each target requires master_id")
        if type(path_index) is not int:
            raise ValueError("each target path_index must be an integer")
        key = (str(master_id), int(path_index), tuple(indices))
        if key in seen:
            raise ValueError("targets must be unique")
        seen.add(key)
        normalized.append({"masterId": str(master_id), "pathIndex": int(path_index), indices_camel: indices})
    return normalized


def _grid_policy(value):
    normalized, error = mcp_tools_curve_geometry._normalize_grid_policy(value)
    if error:
        raise ValueError(error)
    return normalized


def _resolve_font(font_index):
    font, fonts = _resolve_font_by_index(Glyphs, font_index)
    if not font:
        raise ValueError((_font_resolution_error(font_index, fonts, ok_key="ok") or {}).get("error"))
    return font


def _entry_base(font, font_index, glyph, layer, operation, source, candidate, arguments, allowed):
    layer_id = _get_layer_id(layer)
    master_id = str(getattr(layer, "associatedMasterId", None) or layer_id)
    entry = {
        "entryId": outline_candidate_state.new_id("entry"),
        "fontKey": _font_key(font),
        "fontIndex": int(font_index),
        "glyphName": str(getattr(glyph, "name", "") or ""),
        "sourceLayerId": str(layer_id),
        "sourceMasterId": master_id,
        "operation": str(operation),
        "arguments": copy.deepcopy(arguments),
        "allowed": copy.deepcopy(allowed),
        "source": source,
        "candidate": candidate,
        "sourceFingerprint": _fingerprint(source),
        "generatedFingerprint": _fingerprint(candidate),
        "sourceTopologyFingerprint": _fingerprint(_topology(source)),
        "generatedTopologyFingerprint": _fingerprint(_topology(candidate)),
        "materializedLayerId": None,
        "materializedLayerName": None,
        "warnings": [],
    }
    source["displayPaths"] = _detached_display_paths(layer, source, None)
    candidate["displayPaths"] = _detached_display_paths(layer, candidate, entry)
    return entry


def _detached_display_paths(layer, desired, entry):
    if not desired.get("components"):
        return _display_paths_with_directions(layer, desired.get("paths") or [])
    try:
        detached = layer.copy()
        if entry is not None:
            _apply_allowed_snapshot(detached, desired, entry)
        decompose = getattr(detached, "decomposeComponents", None)
        if callable(decompose):
            decompose()
            return _display_paths_with_directions(
                detached,
                _layer_snapshot(detached).get("paths") or [],
            )
    except Exception:
        pass
    return _display_paths_with_directions(layer, desired.get("paths") or [])


def _session_payload(font, font_index, glyph_name, operation, entries):
    return {
        "sessionId": outline_candidate_state.new_id("candidate"),
        "operation": str(operation),
        "fontKey": _font_key(font),
        "fontIndex": int(font_index),
        "glyphName": str(glyph_name),
        "entries": entries,
        "expectedEntryCount": len(entries),
        "toolVersion": TOOL_VERSION,
        "createdAt": float(time.time()),
        "warnings": [],
    }


def _reporter_values(attribute):
    try:
        return list(getattr(Glyphs, attribute, None) or [])
    except Exception:
        return []


def _class_name(value):
    try:
        return str(value.__class__.__name__)
    except Exception:
        return ""


def _find_reporter():
    return next((item for item in _reporter_values("reporters") if _class_name(item) == REPORTER_CLASS_NAME), None)


def _reporter_active(reporter):
    return any(item is reporter or _class_name(item) == REPORTER_CLASS_NAME for item in _reporter_values("activeReporters"))


def _reporter_state():
    reporter = _find_reporter()
    snapshot = None
    try:
        method = getattr(reporter, "overlayStateSnapshot", None)
        snapshot = method() if callable(method) else None
    except Exception:
        snapshot = None
    return {
        "available": reporter is not None,
        "enabled": _reporter_active(reporter),
        "reporterClass": REPORTER_CLASS_NAME,
        "menuPath": REPORTER_MENU_PATH,
        "lastDraw": (snapshot or {}).get("lastDraw"),
        "lastError": (snapshot or {}).get("lastError"),
    }


def _set_reporter_state(enabled):
    reporter = _find_reporter()
    if reporter is None:
        return {**_reporter_state(), "ok": False, "error": "candidate_reporter_not_loaded"}
    action = getattr(Glyphs, "activateReporter" if enabled else "deactivateReporter", None)
    if not callable(action):
        return {**_reporter_state(), "ok": False, "error": "reporter_state_api_unavailable"}
    action(reporter)
    redraw = getattr(Glyphs, "redraw", None)
    if callable(redraw):
        redraw()
    state = _reporter_state()
    state["ok"] = bool(state.get("enabled")) is bool(enabled)
    return state


def _activate_and_store(session):
    stored = outline_candidate_state.STORE.put_session(session)
    reporter = _set_reporter_state(True)
    if not reporter.get("ok"):
        stored.setdefault("warnings", []).append(
            {
                "code": "candidate_reporter_activation_failed",
                "reason": reporter.get("error") or "reporter_state_verification_failed",
            }
        )
        outline_candidate_state.STORE.update_session(stored)
    return stored, reporter


def _preview_response(session, reporter, summaries):
    return {
        "ok": True,
        "candidateDataVersion": CANDIDATE_DATA_VERSION,
        "sessionId": session["sessionId"],
        "operation": session["operation"],
        "entryIds": [entry["entryId"] for entry in session.get("entries") or []],
        "fingerprints": [
            {
                "entryId": entry["entryId"],
                "source": entry["sourceFingerprint"],
                "generated": entry["generatedFingerprint"],
            }
            for entry in session.get("entries") or []
        ],
        "targets": summaries,
        "summary": {"entryCount": len(session.get("entries") or []), "fontChanged": False, "fontSaved": False},
        "warnings": list(session.get("warnings") or []),
        "reporter": reporter,
        "nextSteps": [
            "Review the localized golden-yellow difference regions directly in Glyphs.",
            "Use review_outline_candidate_session before acceptance.",
            "Materialize only when manual editing is desired.",
        ],
    }


def _preview_tunni_impl(font_index, glyph_name, targets, imbalance_threshold, min_handle_length, grid_policy):
    font = _resolve_font(font_index)
    glyph = _glyph_for_name(font, glyph_name)
    if glyph is None:
        raise ValueError("glyph_not_found")
    normalized = _strict_targets(
        targets,
        indices_name="segment_end_node_indices",
        indices_camel="segmentEndNodeIndices",
    )
    imbalance = float(imbalance_threshold)
    minimum = float(min_handle_length)
    if not math.isfinite(imbalance) or not 0.0 <= imbalance <= 1.0:
        raise ValueError("imbalance_threshold must be finite and between 0 and 1")
    if not math.isfinite(minimum) or minimum < 1.0:
        raise ValueError("min_handle_length must be finite and at least 1")
    policy = _grid_policy(grid_policy)
    groups = {}
    summaries = []
    for target in normalized:
        resolved, error = mcp_tools_curve_geometry._resolve_target(
            font_index, glyph_name, target["masterId"], target["pathIndex"]
        )
        if error:
            raise ValueError(error.get("error") or "target_resolution_failed")
        segments = outline_geometry_engine.analyze_tunni_path(
            resolved["nodes"],
            closed=resolved["closed"],
            upm=resolved["upm"],
            segment_end_node_indices=target["segmentEndNodeIndices"],
            imbalance_threshold=imbalance,
            min_handle_length=minimum,
            grid_step=mcp_tools_curve_geometry._grid_step(resolved, policy),
        )
        if any(not item.get("eligible") for item in segments):
            reasons = [item.get("reason") for item in segments if not item.get("eligible")]
            raise ValueError("candidate_target_not_eligible:{}".format(",".join(str(item) for item in reasons)))
        key = str(_get_layer_id(resolved["layer"]))
        group = groups.setdefault(
            key,
            {
                "layer": resolved["layer"],
                "source": _layer_snapshot(resolved["layer"]),
                "targets": [],
                "allowed": [],
                "proposals": {},
            },
        )
        group["targets"].append({**target, "segments": segments})
        candidate_path = group["source"]["paths"][target["pathIndex"]]
        for segment in segments:
            for role in ("handle1", "handle2"):
                node_index = int(segment["nodeIndices"][role])
                point = segment["proposed"][role]
                proposal_key = (target["pathIndex"], node_index)
                _record_candidate_proposal(group["proposals"], proposal_key, point)
                candidate_path["nodes"][node_index]["x"] = point["x"]
                candidate_path["nodes"][node_index]["y"] = point["y"]
                allowed = {"pathIndex": target["pathIndex"], "nodeIndex": node_index}
                if allowed not in group["allowed"]:
                    group["allowed"].append(allowed)
        summaries.append(
            {
                "masterId": target["masterId"],
                "pathIndex": target["pathIndex"],
                "segmentEndNodeIndices": target["segmentEndNodeIndices"],
                "eligibleCount": len(segments),
                "shapeIndex": resolved["target"].get("shapeIndex"),
            }
        )
    entries = []
    for group in groups.values():
        source = _layer_snapshot(group["layer"])
        candidate = group["source"]
        arguments = {
            "targets": [{key: value for key, value in item.items() if key != "segments"} for item in group["targets"]],
            "imbalanceThreshold": imbalance,
            "minHandleLength": minimum,
            "gridPolicy": policy,
            "gridLength": float(getattr(font, "gridLength", 0.0)),
            "gridSubDivision": int(getattr(font, "gridSubDivision", 1) or 1),
            "upm": float(getattr(font, "upm", 1000.0) or 1000.0),
        }
        entries.append(
            _entry_base(
                font, font_index, glyph, group["layer"], "tunni", source, candidate, arguments,
                {"nodeCoordinates": group["allowed"]},
            )
        )
    session = _session_payload(font, font_index, glyph_name, "tunni", entries)
    return session, summaries


@glyphs_tool()
async def preview_tunni_balance_candidate(
    font_index: int = 0,
    glyph_name: str = None,
    targets: list = None,
    imbalance_threshold: float = 0.05,
    min_handle_length: float = 1.0,
    grid_policy: str = "font",
) -> str:
    """Create and show a detached, grid-safe Tunni candidate across explicit targets.

    Each target requires ``master_id``, ``path_index``, and a nonempty unique
    ``segment_end_node_indices`` list. Preview never creates a layer or dirties
    or saves the font. It enables View > Show Glyphs MCP Candidate and returns
    a persistent session identifier for review, optional materialization, and
    guarded acceptance. The Reporter draws only the warm-yellow geometric
    difference over the normal Glyphs outline. Use the separate Curvature
    Reporter when curvature review is also needed. Use candidate sessions for
    every multi-master batch.
    """
    try:
        if not glyph_name:
            raise ValueError("glyph_name is required")
        session, summaries = _run_on_main_thread(
            lambda: _preview_tunni_impl(
                font_index, glyph_name, targets, imbalance_threshold, min_handle_length, grid_policy
            )
        )
        stored, reporter = _run_on_main_thread(lambda: _activate_and_store(session))
        return _safe_json(_preview_response(stored, reporter, summaries))
    except Exception as error:
        return _safe_json({"ok": False, "candidateDataVersion": CANDIDATE_DATA_VERSION, "error": str(error)})


def _preview_smooth_impl(font_index, glyph_name, targets, threshold_deg, min_handle_len):
    font = _resolve_font(font_index)
    glyph = _glyph_for_name(font, glyph_name)
    if glyph is None:
        raise ValueError("glyph_not_found")
    normalized = _strict_targets(targets, indices_name="node_indices", indices_camel="nodeIndices")
    threshold = float(threshold_deg)
    minimum = float(min_handle_len)
    if not math.isfinite(threshold) or threshold < 0.0:
        raise ValueError("threshold_deg must be finite and nonnegative")
    if not math.isfinite(minimum) or minimum < 1.0:
        raise ValueError("min_handle_len must be finite and at least 1")
    groups = {}
    summaries = []
    for target in normalized:
        resolved, error = mcp_tools_curve_geometry._resolve_target(
            font_index, glyph_name, target["masterId"], target["pathIndex"]
        )
        if error:
            raise ValueError(error.get("error") or "target_resolution_failed")
        candidates = []
        for node_index in target["nodeIndices"]:
            result = smoothness_engine.evaluate_collinear_handles_at_node(
                resolved["path"].nodes,
                node_index,
                closed=resolved["closed"],
                threshold_deg=threshold,
                min_handle_len=minimum,
                allowed_node_types=("curve",),
            )
            if not result.get("ok"):
                raise ValueError("candidate_target_not_eligible:{}".format(result.get("reason")))
            candidates.append(result)
        key = str(_get_layer_id(resolved["layer"]))
        group = groups.setdefault(
            key,
            {"layer": resolved["layer"], "candidate": _layer_snapshot(resolved["layer"]), "targets": [], "allowed": []},
        )
        for node_index in target["nodeIndices"]:
            group["candidate"]["paths"][target["pathIndex"]]["nodes"][node_index]["smooth"] = True
            group["allowed"].append({"pathIndex": target["pathIndex"], "nodeIndex": node_index})
        group["targets"].append(target)
        summaries.append({**target, "eligibleCount": len(candidates), "shapeIndex": resolved["target"].get("shapeIndex")})
    entries = []
    for group in groups.values():
        source = _layer_snapshot(group["layer"])
        entries.append(
            _entry_base(
                font, font_index, glyph, group["layer"], "collinear", source, group["candidate"],
                {"targets": group["targets"], "thresholdDeg": threshold, "minHandleLen": minimum},
                {"smoothFlags": group["allowed"]},
            )
        )
    return _session_payload(font, font_index, glyph_name, "collinear", entries), summaries


@glyphs_tool()
async def preview_collinear_handles_candidate(
    font_index: int = 0,
    glyph_name: str = None,
    targets: list = None,
    threshold_deg: float = 3.0,
    min_handle_len: float = 5.0,
) -> str:
    """Create and show a detached smooth-connection candidate for explicit nodes.

    Targets require master, path, and node indices. Only connection/smooth flags
    at approved nodes may later be promoted; preview itself is read-only. A
    flag-only proposal reports no visible outline difference because the
    Candidate Reporter never invents geometry or draws over the live outline.
    """
    try:
        if not glyph_name:
            raise ValueError("glyph_name is required")
        session, summaries = _run_on_main_thread(
            lambda: _preview_smooth_impl(font_index, glyph_name, targets, threshold_deg, min_handle_len)
        )
        stored, reporter = _run_on_main_thread(lambda: _activate_and_store(session))
        return _safe_json(_preview_response(stored, reporter, summaries))
    except Exception as error:
        return _safe_json({"ok": False, "candidateDataVersion": CANDIDATE_DATA_VERSION, "error": str(error)})


def _comp_preview_impl(font_index, glyph_names, base_master_id, ref_master_id, output_master_id, params):
    font = _resolve_font(font_index)
    if not isinstance(glyph_names, list) or not glyph_names:
        raise ValueError("glyph_names must be a nonempty list")
    if len(glyph_names) != len(set(str(name) for name in glyph_names)):
        raise ValueError("glyph_names must be unique")
    output_id = str(output_master_id or base_master_id or "")
    if not output_id or not base_master_id or not ref_master_id:
        raise ValueError("base_master_id, ref_master_id, and output_master_id are required")
    entries = []
    summaries = []
    for name in glyph_names:
        glyph = _glyph_for_name(font, name)
        layer = _layer_for_id(glyph, output_id) if glyph else None
        if layer is None:
            raise ValueError("target_layer_not_found:{}".format(name))
        if list(_layer_components(layer)):
            raise ValueError("components_blocked:{}".format(name))
        review = mcp_tools_compensated_tuning._review_compensated_tuning_impl(
            font_index=font_index,
            glyph_name=str(name),
            base_master_id=str(base_master_id),
            ref_master_id=str(ref_master_id),
            **params
        )
        if not isinstance(review, dict) or not review.get("gmcp", {}).get("ok"):
            raise ValueError("compensated_tuning_review_failed:{}".format(name))
        source = _layer_snapshot(layer)
        candidate = copy.deepcopy(source)
        proposed_paths = review.get("paths") or []
        if len(proposed_paths) != len(candidate["paths"]):
            raise ValueError("topology_change_blocked:{}".format(name))
        for path_index, path in enumerate(proposed_paths):
            nodes = path.get("nodes") or []
            if len(nodes) != len(candidate["paths"][path_index]["nodes"]):
                raise ValueError("topology_change_blocked:{}".format(name))
            for node_index, node in enumerate(nodes):
                target_node = candidate["paths"][path_index]["nodes"][node_index]
                if str(node.get("type")) != str(target_node.get("type")):
                    raise ValueError("topology_change_blocked:{}".format(name))
                target_node.update({"x": node.get("x"), "y": node.get("y"), "smooth": bool(node.get("smooth"))})
        candidate["width"] = float(review.get("width", source["width"]))
        arguments = {
            "glyphName": str(name), "baseMasterId": str(base_master_id), "refMasterId": str(ref_master_id),
            "outputMasterId": output_id, "params": copy.deepcopy(params),
        }
        entries.append(
            _entry_base(
                font, font_index, glyph, layer, "compensated_tuning", source, candidate, arguments,
                {"allNodeCoordinates": True, "allSmoothFlags": True, "width": True, "components": False},
            )
        )
        summaries.append({"glyphName": str(name), "masterId": output_id, "warnings": review.get("gmcp", {}).get("warnings") or []})
    return _session_payload(font, font_index, ",".join(str(name) for name in glyph_names), "compensated_tuning", entries), summaries


@glyphs_tool()
async def preview_compensated_tuning_candidate(
    font_index: int = 0,
    glyph_names: list = None,
    base_master_id: str = None,
    ref_master_id: str = None,
    output_master_id: str = None,
    sx: float = 1.0,
    sy: float = 1.0,
    keep_stroke: float = 0.9,
    stroke_exponent_a: float = None,
    q_x: float = None,
    q_y: float = None,
    italic_angle: float = None,
    translate_x: float = 0.0,
    translate_y: float = 0.0,
    extrapolation: str = "clamp",
    round_units: bool = True,
    stem_ratio_b: float = None,
    stem_measure: dict = None,
) -> str:
    """Create and show detached compensated-tuning candidates for explicit glyphs.

    Components remain blocked. Candidate sessions are the required default for
    multi-glyph work and do not change, dirty, or save the font. The Reporter
    draws only warm-yellow source/candidate difference regions.
    """
    params = {
        "sx": sx, "sy": sy, "keep_stroke": keep_stroke, "stroke_exponent_a": stroke_exponent_a,
        "q_x": q_x, "q_y": q_y, "italic_angle": italic_angle, "translate_x": translate_x,
        "translate_y": translate_y, "extrapolation": extrapolation, "round_units": round_units,
        "stem_ratio_b": stem_ratio_b, "stem_measure": stem_measure,
    }
    try:
        session, summaries = _run_on_main_thread(
            lambda: _comp_preview_impl(
                font_index, glyph_names, base_master_id, ref_master_id, output_master_id, params
            )
        )
        stored, reporter = _run_on_main_thread(lambda: _activate_and_store(session))
        return _safe_json(_preview_response(stored, reporter, summaries))
    except Exception as error:
        return _safe_json({"ok": False, "candidateDataVersion": CANDIDATE_DATA_VERSION, "error": str(error)})


def _italic_preview_impl(font_index, params):
    review = mcp_tools_italic._review_italic_first_pass_impl(font_index=font_index, **params)
    if not review.get("ok") or not review.get("readyToApply"):
        raise ValueError("italic_first_pass_review_blocked")
    source_font = mcp_tools_italic._get_font(review["sourceFontIndex"])
    target_font = mcp_tools_italic._get_font(review["targetFontIndex"])
    target_master = mcp_tools_italic._master_by_id(target_font, review["targetMasterId"])
    target_stems = mcp_tools_italic._stem_values(review.get("stemReview"), review["targetMasterId"])
    entries = []
    summaries = []
    for result in review.get("results") or []:
        if result.get("status") != "ok":
            continue
        name = result.get("glyphName")
        source_glyph = mcp_tools_italic._glyph_lookup(source_font, name)
        target_glyph = mcp_tools_italic._glyph_lookup(target_font, name)
        source_layer = mcp_tools_italic._layer_for_glyph(source_glyph, review["sourceMasterId"])
        target_layer = mcp_tools_italic._layer_for_glyph(target_glyph, review["targetMasterId"]) if target_glyph else None
        if source_layer is None or target_layer is None:
            raise ValueError("candidate_requires_existing_target_layer:{}".format(name))
        prepared = mcp_tools_italic._prepare_path_only_candidate(
            source_layer,
            target_layer,
            review["copyOptions"],
            angle=review["angle"],
            slant_mode=review["effectiveSlantMode"],
            origin=review["origin"],
            target_master=target_master,
            target_master_id=review["targetMasterId"],
            source_font=source_font,
            source_master_id=review["sourceMasterId"],
            source_glyph_name=name,
            upm=float(getattr(target_font, "upm", 1000) or 1000),
            stem_values=target_stems,
            curve_strength=review["curveStrength"],
            stem_compensation=review["stemCompensation"],
        )
        if not prepared.get("ok"):
            raise ValueError("italic_candidate_failed:{}:{}".format(name, prepared.get("reason")))
        source = _layer_snapshot(target_layer)
        candidate = _layer_snapshot(prepared["candidateLayer"])
        candidate, mismatch = _italic_topology_mismatch(source, candidate)
        if mismatch:
            _raise_topology_mismatch(name, mismatch)
        arguments = {
            "review": {
                "sourceFontIndex": review["sourceFontIndex"],
                "targetFontIndex": review["targetFontIndex"],
                "sourceMasterId": review["sourceMasterId"],
                "targetMasterId": review["targetMasterId"],
                "angle": review["angle"],
                "origin": review["origin"],
                "effectiveSlantMode": review["effectiveSlantMode"],
                "curveStrength": review["curveStrength"],
                "stemCompensation": review["stemCompensation"],
                "copyOptions": review["copyOptions"],
                "stemReview": review.get("stemReview"),
            },
            "glyphName": name,
        }
        entry = _entry_base(
            target_font,
            review["targetFontIndex"],
            target_glyph,
            target_layer,
            "italic_first_pass",
            source,
            candidate,
            arguments,
            {
                "allNodeCoordinates": True,
                "allSmoothFlags": True,
                "anchors": True,
                "componentTransforms": True,
                "width": True,
            },
        )
        entries.append(entry)
        summaries.append(
            {
                "glyphName": name,
                "masterId": review["targetMasterId"],
                "outcome": result.get("outcome"),
                "warnings": result.get("warnings") or [],
            }
        )
    if not entries:
        raise ValueError("italic_candidate_session_empty")
    return (
        _session_payload(
            target_font,
            review["targetFontIndex"],
            ",".join(item["glyphName"] for item in entries),
            "italic_first_pass",
            entries,
        ),
        summaries,
    )


@glyphs_tool()
async def preview_italic_first_pass_candidate(
    font_index: int = 0,
    source_font_index: int = None,
    target_font_index: int = None,
    source_master_id: str = None,
    target_master_id: str = None,
    scope: str = "selected_glyphs",
    glyph_names: list = None,
    angle: float = 12.0,
    slant_mode: str = "cursivy",
    stem_policy: str = "require_existing",
    compatibility_mode: str = "preserve_if_possible",
    copy_options: dict = None,
    protected_glyphs: list = None,
    skip_glyphs: list = None,
    origin: int = 3,
    curve_strength: float = 0.75,
    stem_compensation: float = 1.0,
) -> str:
    """Create detached italic-first-pass candidates and show them in Glyphs.

    Existing target glyph layers are required so promotion can preserve their
    topology and protected data. Multi-glyph work uses this candidate-session
    workflow by default. The Reporter draws only the warm-yellow geometric
    difference; curvature remains a separate View overlay. Preview does not
    dirty or save either font.
    """
    params = {
        "source_font_index": source_font_index,
        "target_font_index": target_font_index,
        "source_master_id": source_master_id,
        "target_master_id": target_master_id,
        "scope": scope,
        "glyph_names": glyph_names,
        "angle": angle,
        "slant_mode": slant_mode,
        "stem_policy": stem_policy,
        "compatibility_mode": compatibility_mode,
        "copy_options": copy_options,
        "protected_glyphs": protected_glyphs,
        "skip_glyphs": skip_glyphs,
        "origin": origin,
        "curve_strength": curve_strength,
        "stem_compensation": stem_compensation,
    }
    try:
        session, summaries = _run_on_main_thread(lambda: _italic_preview_impl(font_index, params))
        stored, reporter = _run_on_main_thread(lambda: _activate_and_store(session))
        return _safe_json(_preview_response(stored, reporter, summaries))
    except Exception as error:
        return _safe_json(_italic_preview_error_payload(error))


def _manifest_get(font):
    value = _manifest_raw(font)
    return copy.deepcopy(value) if isinstance(value, dict) else {"candidateDataVersion": 1, "sessions": {}}


def _manifest_raw(font):
    try:
        value = font.userData[FONT_MANIFEST_KEY]
    except Exception:
        value = None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            value = None
    return copy.deepcopy(value) if isinstance(value, dict) else None


def _manifest_set(font, manifest):
    user_data = getattr(font, "userData", None)
    if user_data is None:
        raise RuntimeError("font_userdata_unavailable")
    user_data[FONT_MANIFEST_KEY] = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )


def _manifest_restore(font, manifest):
    user_data = getattr(font, "userData", None)
    if user_data is None:
        raise RuntimeError("font_userdata_unavailable")
    if manifest is None:
        try:
            del user_data[FONT_MANIFEST_KEY]
        except Exception:
            pass
    else:
        _manifest_set(font, manifest)


def _manifest_delete_session(font, session_id):
    manifest = _manifest_get(font)
    sessions = manifest.setdefault("sessions", {})
    sessions.pop(str(session_id), None)
    if sessions:
        _manifest_set(font, manifest)
    else:
        _manifest_restore(font, None)


def _layer_metadata_get(layer):
    try:
        value = layer.userData[LAYER_METADATA_KEY]
        if isinstance(value, str):
            value = json.loads(value)
        return copy.deepcopy(value) if isinstance(value, dict) else None
    except Exception:
        return None


def _layer_metadata_set(layer, value):
    user_data = getattr(layer, "userData", None)
    if user_data is None:
        raise RuntimeError("layer_userdata_unavailable")
    user_data[LAYER_METADATA_KEY] = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )


def _materialized_session_from_manifest(font, session_id):
    record = (_manifest_get(font).get("sessions") or {}).get(str(session_id))
    if not isinstance(record, dict):
        return None
    entries = []
    for item in record.get("entries") or []:
        glyph = _glyph_for_name(font, item.get("glyphName"))
        candidate_layer = _layer_for_id(glyph, item.get("materializedLayerId")) if glyph else None
        metadata = _layer_metadata_get(candidate_layer) if candidate_layer else None
        if not metadata:
            return None
        entry = copy.deepcopy(metadata.get("entry") or {})
        entry["materializedLayerId"] = str(_get_layer_id(candidate_layer))
        entry["materializedLayerName"] = str(getattr(candidate_layer, "name", "") or "")
        entries.append(entry)
    session = copy.deepcopy(record.get("session") or {})
    session["entries"] = entries
    return session if entries else None


def _load_session(font, session_id):
    session = outline_candidate_state.STORE.get_session(session_id)
    if session is not None:
        return session
    session = _materialized_session_from_manifest(font, session_id)
    if session is not None:
        return session
    raise ValueError("candidate_session_not_found")


def _public_session(session, include_entries=False):
    value = {
        "sessionId": session.get("sessionId"),
        "operation": session.get("operation"),
        "fontIndex": session.get("fontIndex"),
        "glyphName": session.get("glyphName"),
        "entryCount": len(session.get("entries") or []),
        "materializedEntryCount": sum(1 for entry in session.get("entries") or [] if entry.get("materializedLayerId")),
        "createdAt": session.get("createdAt"),
    }
    if include_entries:
        value["entries"] = [
            {
                "entryId": entry.get("entryId"),
                "glyphName": entry.get("glyphName"),
                "sourceLayerId": entry.get("sourceLayerId"),
                "sourceMasterId": entry.get("sourceMasterId"),
                "materializedLayerId": entry.get("materializedLayerId"),
                "materializedLayerName": entry.get("materializedLayerName"),
                "sourceFingerprint": entry.get("sourceFingerprint"),
                "generatedFingerprint": entry.get("generatedFingerprint"),
            }
            for entry in session.get("entries") or []
        ]
    return value


@glyphs_tool()
async def set_outline_candidate_overlay(
    enabled: bool = True,
    session_id: str = None,
    clear_session: bool = False,
) -> str:
    """Enable/disable the candidate Reporter or clear only ephemeral state.

    This is UI state only. ``clear_session=true`` never deletes materialized
    layers; use ``discard_outline_candidate_session`` for that explicit Edit
    operation. The font is never dirtied or saved by this tool.
    """
    try:
        if type(enabled) is not bool or type(clear_session) is not bool:
            raise ValueError("enabled and clear_session must be booleans")
        store_state = outline_candidate_state.STORE.set_overlay(enabled, session_id, clear_session)
        reporter = _run_on_main_thread(lambda: _set_reporter_state(bool(store_state.get("enabled"))))
        return _safe_json(
            {
                "ok": bool(reporter.get("ok")),
                "candidateDataVersion": CANDIDATE_DATA_VERSION,
                "state": store_state,
                "reporter": reporter,
                "fontChanged": False,
                "fontSaved": False,
                "uiOnly": True,
            }
        )
    except Exception as error:
        return _safe_json({"ok": False, "candidateDataVersion": CANDIDATE_DATA_VERSION, "error": str(error)})


@glyphs_tool()
async def get_outline_candidate_state(
    font_index: int = 0,
    session_id: str = None,
    include_entries: bool = False,
) -> str:
    """Return bounded ephemeral/materialized candidate and Reporter state."""
    try:
        if type(include_entries) is not bool:
            raise ValueError("include_entries must be a boolean")
        font = _run_on_main_thread(lambda: _resolve_font(font_index))
        ephemeral = outline_candidate_state.STORE.sessions()
        manifest = _run_on_main_thread(lambda: _manifest_get(font))
        materialized = list((manifest.get("sessions") or {}).values())
        if session_id is not None:
            ephemeral = [item for item in ephemeral if str(item.get("sessionId")) == str(session_id)]
            materialized = [
                item for item in materialized
                if str((item.get("session") or {}).get("sessionId")) == str(session_id)
            ]
        return _safe_json(
            {
                "ok": True,
                "candidateDataVersion": CANDIDATE_DATA_VERSION,
                "reporter": _run_on_main_thread(_reporter_state),
                "state": outline_candidate_state.STORE.state(),
                "ephemeralSessions": [_public_session(item, include_entries) for item in ephemeral[:16]],
                "materializedSessions": [
                    _public_session(item.get("session") or {}, include_entries) for item in materialized[:16]
                ],
                "fontChanged": False,
                "fontSaved": False,
            }
        )
    except Exception as error:
        return _safe_json({"ok": False, "candidateDataVersion": CANDIDATE_DATA_VERSION, "error": str(error)})


def _recompute_entry(entry):
    source = copy.deepcopy(entry["source"])
    operation = entry.get("operation")
    arguments = entry.get("arguments") or {}
    if operation == "tunni":
        proposals = {}
        for target in arguments.get("targets") or []:
            path_index = int(target["pathIndex"])
            path = source["paths"][path_index]
            segments = outline_geometry_engine.analyze_tunni_path(
                path["nodes"],
                closed=path["closed"],
                upm=float(arguments.get("upm", 1000.0)),
                segment_end_node_indices=target["segmentEndNodeIndices"],
                imbalance_threshold=float(arguments["imbalanceThreshold"]),
                min_handle_length=float(arguments["minHandleLength"]),
                grid_step=(
                    float(arguments["gridLength"])
                    if arguments.get("gridPolicy") == "font" and float(arguments["gridLength"]) > 0.0
                    else None
                ),
            )
            if any(not segment.get("eligible") for segment in segments):
                raise ValueError("recomputed_candidate_not_eligible")
            for segment in segments:
                for role in ("handle1", "handle2"):
                    node_index = int(segment["nodeIndices"][role])
                    point = segment["proposed"][role]
                    proposal_key = (path_index, node_index)
                    _record_candidate_proposal(proposals, proposal_key, point)
        for (path_index, node_index), point in proposals.items():
            node = source["paths"][path_index]["nodes"][node_index]
            node["x"], node["y"] = point["x"], point["y"]
        return source
    if operation == "collinear":
        for target in arguments.get("targets") or []:
            path = source["paths"][int(target["pathIndex"])]
            for node_index in target["nodeIndices"]:
                result = smoothness_engine.evaluate_collinear_handles_at_node(
                    path["nodes"],
                    int(node_index),
                    closed=path["closed"],
                    threshold_deg=float(arguments["thresholdDeg"]),
                    min_handle_len=float(arguments["minHandleLen"]),
                    allowed_node_types=("curve",),
                )
                if not result.get("ok"):
                    raise ValueError("recomputed_candidate_not_eligible")
                path["nodes"][int(node_index)]["smooth"] = True
        return source
    if operation == "compensated_tuning":
        params = copy.deepcopy(arguments.get("params") or {})
        review = mcp_tools_compensated_tuning._review_compensated_tuning_impl(
            font_index=int(entry["fontIndex"]),
            glyph_name=arguments["glyphName"],
            base_master_id=arguments["baseMasterId"],
            ref_master_id=arguments["refMasterId"],
            **params
        )
        if not isinstance(review, dict) or not review.get("gmcp", {}).get("ok"):
            raise ValueError("compensated_tuning_recompute_failed")
        paths = review.get("paths") or []
        if len(paths) != len(source.get("paths") or []):
            raise ValueError("topology_changed")
        for path_index, path in enumerate(paths):
            nodes = path.get("nodes") or []
            if len(nodes) != len(source["paths"][path_index]["nodes"]):
                raise ValueError("topology_changed")
            for node_index, node in enumerate(nodes):
                source["paths"][path_index]["nodes"][node_index].update(
                    {"x": node["x"], "y": node["y"], "smooth": bool(node.get("smooth"))}
                )
        source["width"] = float(review.get("width", source["width"]))
        return source
    if operation == "italic_first_pass":
        review = arguments.get("review") or {}
        source_font = mcp_tools_italic._get_font(review["sourceFontIndex"])
        target_font = mcp_tools_italic._get_font(review["targetFontIndex"])
        source_glyph = mcp_tools_italic._glyph_lookup(source_font, arguments["glyphName"])
        target_glyph = mcp_tools_italic._glyph_lookup(target_font, arguments["glyphName"])
        source_layer = mcp_tools_italic._layer_for_glyph(source_glyph, review["sourceMasterId"])
        target_layer = mcp_tools_italic._layer_for_glyph(target_glyph, review["targetMasterId"])
        target_master = mcp_tools_italic._master_by_id(target_font, review["targetMasterId"])
        prepared = mcp_tools_italic._prepare_path_only_candidate(
            source_layer,
            target_layer,
            review["copyOptions"],
            angle=review["angle"],
            slant_mode=review["effectiveSlantMode"],
            origin=review["origin"],
            target_master=target_master,
            target_master_id=review["targetMasterId"],
            source_font=source_font,
            source_master_id=review["sourceMasterId"],
            source_glyph_name=arguments["glyphName"],
            upm=float(getattr(target_font, "upm", 1000) or 1000),
            stem_values=mcp_tools_italic._stem_values(review.get("stemReview"), review["targetMasterId"]),
            curve_strength=review["curveStrength"],
            stem_compensation=review["stemCompensation"],
        )
        if not prepared.get("ok"):
            raise ValueError("italic_first_pass_recompute_failed")
        recomputed = _layer_snapshot(prepared["candidateLayer"])
        recomputed, mismatch = _italic_topology_mismatch(source, recomputed)
        if mismatch:
            _raise_topology_mismatch(arguments["glyphName"], mismatch)
        return recomputed
    raise ValueError("unsupported_candidate_operation")


def _source_context(font, entry):
    glyph = _glyph_for_name(font, entry.get("glyphName"))
    if glyph is None:
        raise ValueError("source_glyph_missing")
    layer = _layer_for_id(glyph, entry.get("sourceLayerId"))
    if layer is None:
        raise ValueError("source_layer_missing")
    return glyph, layer


def _assert_current_source(font, entry):
    glyph, layer = _source_context(font, entry)
    current = _layer_snapshot(layer)
    if _fingerprint(current) != str(entry.get("sourceFingerprint")):
        raise ValueError("stale_source")
    return glyph, layer, current


def _layer_name(font, entry, session_id):
    master_name = entry.get("sourceMasterId")
    try:
        for master in list(getattr(font, "masters", None) or []):
            if str(getattr(master, "id", "")) == str(entry.get("sourceMasterId")):
                master_name = str(getattr(master, "name", None) or master_name)
                break
    except Exception:
        pass
    labels = {
        "tunni": "Tunni",
        "collinear": "Collinear",
        "italic_first_pass": "Italic",
        "compensated_tuning": "Compensated Tuning",
    }
    suffix = outline_candidate_state.fingerprint(str(session_id))[:6].upper()
    return "GMCP Candidate — {} — {} — {}".format(labels.get(entry.get("operation"), "Outline"), master_name, suffix)


def _set_node_position(node, x, y):
    x_value, y_value = float(x), float(y)
    if not math.isfinite(x_value) or not math.isfinite(y_value):
        raise ValueError("nonfinite_coordinate")
    node.position = (x_value, y_value)


def _apply_allowed_snapshot(layer, desired, entry):
    operation = entry.get("operation")
    live_paths = list(_layer_paths(layer))
    desired_paths = desired.get("paths") or []
    if len(live_paths) != len(desired_paths):
        raise ValueError("topology_changed")
    if operation == "tunni":
        for target in entry.get("allowed", {}).get("nodeCoordinates") or []:
            path_index, node_index = int(target["pathIndex"]), int(target["nodeIndex"])
            node_data = desired_paths[path_index]["nodes"][node_index]
            node = list(live_paths[path_index].nodes)[node_index]
            _set_node_position(node, node_data["x"], node_data["y"])
    elif operation == "collinear":
        for target in entry.get("allowed", {}).get("smoothFlags") or []:
            path_index, node_index = int(target["pathIndex"]), int(target["nodeIndex"])
            node_data = desired_paths[path_index]["nodes"][node_index]
            node = list(live_paths[path_index].nodes)[node_index]
            node.smooth = bool(node_data.get("smooth"))
    elif operation in ("italic_first_pass", "compensated_tuning"):
        for path_index, live_path in enumerate(live_paths):
            live_nodes = list(getattr(live_path, "nodes", None) or [])
            desired_nodes = desired_paths[path_index].get("nodes") or []
            if len(live_nodes) != len(desired_nodes):
                raise ValueError("topology_changed")
            for node_index, node in enumerate(live_nodes):
                data = desired_nodes[node_index]
                _set_node_position(node, data["x"], data["y"])
                node.smooth = bool(data.get("smooth"))
        layer.width = float(desired.get("width", 0.0))
        if operation == "italic_first_pass":
            anchors = list(getattr(layer, "anchors", None) or [])
            desired_anchors = list(desired.get("anchors") or [])
            anchor_names = [str(getattr(anchor, "name", "") or "") for anchor in anchors]
            desired_anchor_names = [str(data.get("name") or "") for data in desired_anchors]
            if (
                len(anchors) != len(desired_anchors)
                or _duplicate_name(anchor_names) is not None
                or _duplicate_name(desired_anchor_names) is not None
                or set(anchor_names) != set(desired_anchor_names)
            ):
                raise ValueError("anchor_topology_changed")
            anchors_by_name = {str(getattr(anchor, "name", "") or ""): anchor for anchor in anchors}
            for data in desired_anchors:
                anchor = anchors_by_name[str(data.get("name") or "")]
                anchor.position = (float(data["x"]), float(data["y"]))
            components = list(_layer_components(layer))
            for index, data in enumerate(desired.get("components") or []):
                if index >= len(components):
                    raise ValueError("component_topology_changed")
                if data.get("transform") is not None:
                    components[index].transform = tuple(float(value) for value in data["transform"])
    else:
        raise ValueError("unsupported_candidate_operation")


def _remove_layer(glyph, layer):
    layers = getattr(glyph, "layers", None)
    try:
        layers.remove(layer)
        return
    except Exception:
        pass
    for index, item in enumerate(list(layers or [])):
        if item is layer or str(_get_layer_id(item)) == str(_get_layer_id(layer)):
            del layers[index]
            return
    raise RuntimeError("candidate_layer_remove_failed")


def _restore_removed_candidates(font, session, removed_candidates, manifest_before):
    """Reattach candidate layers and repair identities changed by Glyphs.

    Glyphs 4 assigns a fresh layer ID when a previously removed special layer
    is appended again.  A rollback must therefore refresh the layer metadata,
    process-local session, and persisted manifest instead of restoring stale
    identifiers captured before cleanup began.
    """
    for glyph, candidate_layer, entry in removed_candidates:
        glyph.layers.append(candidate_layer)
        layer_id = str(_get_layer_id(candidate_layer) or "")
        if not layer_id:
            raise RuntimeError("candidate_layer_restore_id_missing")
        entry["materializedLayerId"] = layer_id
        entry["materializedLayerName"] = str(getattr(candidate_layer, "name", "") or "")
        metadata = _layer_metadata_get(candidate_layer)
        if not metadata:
            raise RuntimeError("candidate_metadata_restore_failed")
        metadata["entry"] = copy.deepcopy(entry)
        _layer_metadata_set(candidate_layer, metadata)

    manifest = copy.deepcopy(manifest_before)
    if manifest is not None:
        record = (manifest.get("sessions") or {}).get(str(session.get("sessionId")))
        if not isinstance(record, dict):
            raise RuntimeError("candidate_manifest_restore_failed")
        record["session"] = copy.deepcopy(session)
        record["entries"] = [
            {
                "entryId": entry["entryId"],
                "glyphName": entry["glyphName"],
                "materializedLayerId": entry["materializedLayerId"],
            }
            for entry in session.get("entries") or []
            if entry.get("materializedLayerId")
        ]
    _manifest_restore(font, manifest)
    outline_candidate_state.STORE.update_session(session)


def _materialize_transaction(font_index, session_id, dry_run):
    font = _resolve_font(font_index)
    session = _load_session(font, session_id)
    if str(session.get("fontKey")) != _font_key(font):
        raise ValueError("candidate_font_mismatch")
    plans = []
    for entry in session.get("entries") or []:
        glyph, layer, _current = _assert_current_source(font, entry)
        recomputed = _recompute_entry(entry)
        if _fingerprint(recomputed) != str(entry.get("generatedFingerprint")):
            raise ValueError("generated_candidate_mismatch")
        plans.append((entry, glyph, layer, recomputed))
    if dry_run:
        return {
            "ok": True,
            "candidateDataVersion": CANDIDATE_DATA_VERSION,
            "sessionId": session_id,
            "dryRun": True,
            "planned": [
                {"entryId": entry["entryId"], "glyphName": entry["glyphName"], "layerName": _layer_name(font, entry, session_id)}
                for entry, _glyph, _layer, _candidate in plans
            ],
            "created": [],
            "fontChanged": False,
            "fontSaved": False,
        }
    manifest_before = _manifest_raw(font)
    created = []
    try:
        for entry, glyph, layer, desired in plans:
            candidate_layer = layer.copy()
            candidate_layer.name = _layer_name(font, entry, session_id)
            candidate_layer.associatedMasterId = str(entry["sourceMasterId"])
            _apply_allowed_snapshot(candidate_layer, desired, entry)
            metadata = {
                "sessionId": str(session_id),
                "entryId": entry["entryId"],
                "operation": entry["operation"],
                "entry": copy.deepcopy(entry),
                "createdAt": float(time.time()),
                "toolVersion": TOOL_VERSION,
            }
            _layer_metadata_set(candidate_layer, metadata)
            glyph.layers.append(candidate_layer)
            layer_id = str(_get_layer_id(candidate_layer))
            if not layer_id or layer_id == str(entry["sourceLayerId"]):
                raise RuntimeError("candidate_layer_id_not_unique")
            entry["materializedLayerId"] = layer_id
            entry["materializedLayerName"] = str(candidate_layer.name)
            metadata["entry"] = copy.deepcopy(entry)
            _layer_metadata_set(candidate_layer, metadata)
            created.append((glyph, candidate_layer, entry))
        manifest = _manifest_get(font)
        manifest.setdefault("sessions", {})[str(session_id)] = {
            "session": copy.deepcopy(session),
            "entries": [
                {
                    "entryId": entry["entryId"],
                    "glyphName": entry["glyphName"],
                    "materializedLayerId": entry["materializedLayerId"],
                }
                for _glyph, _layer, entry in created
            ],
            "expectedEntryCount": len(plans),
            "createdAt": float(time.time()),
            "toolVersion": TOOL_VERSION,
        }
        _manifest_set(font, manifest)
        outline_candidate_state.STORE.update_session(session)
    except Exception:
        for glyph, layer, _entry in reversed(created):
            try:
                _remove_layer(glyph, layer)
            except Exception:
                pass
        try:
            _manifest_restore(font, manifest_before)
        except Exception:
            pass
        raise
    links = []
    for _glyph, layer, entry in created:
        link = _glyphs_show_layer_link_fields(
            getattr(font, "filepath", None),
            glyph_name=entry["glyphName"],
            layer_id=_get_layer_id(layer),
            label="Open {} candidate in Glyphs".format(entry["glyphName"]),
        )
        links.append({"entryId": entry["entryId"], "layerId": _get_layer_id(layer), "layerName": layer.name, **link})
    return {
        "ok": True,
        "candidateDataVersion": CANDIDATE_DATA_VERSION,
        "sessionId": session_id,
        "dryRun": False,
        "planned": [],
        "created": links,
        "fontChanged": True,
        "fontSaved": False,
        "rollback": {"attempted": False, "succeeded": True},
    }


@glyphs_tool()
async def materialize_outline_candidate_session(
    font_index: int = 0,
    session_id: str = None,
    dry_run: bool = True,
    confirm: bool = False,
) -> str:
    """Create native editable candidate layers after a detached preview.

    Exactly one safety mode is required. Confirmed materialization performs a
    full ``GSLayer.copy()``, uses a new non-background layer associated with the
    source master, persists recovery metadata, verifies the generated proposal,
    and never saves the font. Cosmetic renaming remains allowed afterward.
    """
    try:
        if not session_id:
            raise ValueError("session_id is required")
        if type(dry_run) is not bool or type(confirm) is not bool or dry_run == confirm:
            raise ValueError("set exactly one of dry_run=true or confirm=true")
        return _safe_json(
            _run_on_main_thread(lambda: _materialize_transaction(font_index, session_id, dry_run))
        )
    except Exception as error:
        return _safe_json({"ok": False, "candidateDataVersion": CANDIDATE_DATA_VERSION, "error": str(error)})


def _snapshot_diffs(generated, current, align_italic_anchors=False):
    if align_italic_anchors:
        current, topology_mismatch = _italic_topology_mismatch(generated, current)
    else:
        topology_mismatch = _topology_mismatch(generated, current)
    if topology_mismatch:
        return None, "topology_changed"
    diffs = []
    for path_index, generated_path in enumerate(generated.get("paths") or []):
        current_path = current["paths"][path_index]
        for node_index, before in enumerate(generated_path.get("nodes") or []):
            after = current_path["nodes"][node_index]
            if not (
                math.isclose(float(before["x"]), float(after["x"]), abs_tol=POSITION_TOLERANCE)
                and math.isclose(float(before["y"]), float(after["y"]), abs_tol=POSITION_TOLERANCE)
            ):
                diffs.append(
                    {
                        "kind": "node_coordinate",
                        "pathIndex": path_index,
                        "nodeIndex": node_index,
                        "before": {"x": before["x"], "y": before["y"]},
                        "after": {"x": after["x"], "y": after["y"]},
                    }
                )
            if bool(before.get("smooth")) != bool(after.get("smooth")):
                diffs.append(
                    {
                        "kind": "node_smooth",
                        "pathIndex": path_index,
                        "nodeIndex": node_index,
                        "before": bool(before.get("smooth")),
                        "after": bool(after.get("smooth")),
                    }
                )
    if not math.isclose(float(generated.get("width", 0.0)), float(current.get("width", 0.0)), abs_tol=POSITION_TOLERANCE):
        diffs.append({"kind": "width", "before": generated.get("width"), "after": current.get("width")})
    for index, before in enumerate(generated.get("anchors") or []):
        after = current["anchors"][index]
        if not (
            math.isclose(float(before["x"]), float(after["x"]), abs_tol=POSITION_TOLERANCE)
            and math.isclose(float(before["y"]), float(after["y"]), abs_tol=POSITION_TOLERANCE)
        ):
            diffs.append(
                {"kind": "anchor_position", "anchorIndex": index, "name": before.get("name"), "before": before, "after": after}
            )
    for index, before in enumerate(generated.get("components") or []):
        after = current["components"][index]
        if before.get("transform") != after.get("transform"):
            diffs.append(
                {
                    "kind": "component_transform",
                    "componentIndex": index,
                    "name": before.get("name"),
                    "before": before.get("transform"),
                    "after": after.get("transform"),
                }
            )
        if before.get("smartValues") != after.get("smartValues"):
            diffs.append({"kind": "component_smart_values", "componentIndex": index})
        if before.get("alignment") != after.get("alignment"):
            diffs.append({"kind": "component_alignment", "componentIndex": index})
    return diffs, None


def _snapshots_semantically_equal(expected, actual, align_italic_anchors=False):
    """Compare complete candidate snapshots without numeric JSON type noise.

    Glyphs reads integral point coordinates back as floats (for example,
    ``523.0``), while the grid-safe geometry engine deliberately serializes
    those same coordinates as JSON integers (``523``).  Fingerprints must stay
    type-sensitive for review-token binding, but recomputation and write-back
    verification need geometric snapshot equality instead.
    """
    diffs, reason = _snapshot_diffs(expected, actual, align_italic_anchors=align_italic_anchors)
    return reason is None and not diffs


def _on_grid(value, step):
    return math.isfinite(float(value)) and math.isclose(
        float(value) / float(step), round(float(value) / float(step)), rel_tol=0.0, abs_tol=1.0e-7
    )


def _vector_angle(a, b):
    length_a = math.hypot(a[0], a[1])
    length_b = math.hypot(b[0], b[1])
    if length_a <= 1.0e-12 or length_b <= 1.0e-12:
        return math.inf
    cosine = max(-1.0, min(1.0, (a[0] * b[0] + a[1] * b[1]) / (length_a * length_b)))
    return math.degrees(math.acos(cosine))


def _validate_tunni_geometry(entry, current):
    arguments = entry.get("arguments") or {}
    source = entry.get("source") or {}
    upm = float(arguments.get("upm", 1000.0))
    for target in arguments.get("targets") or []:
        path_index = int(target["pathIndex"])
        current_path = current["paths"][path_index]
        source_path = source["paths"][path_index]
        for end_index in target["segmentEndNodeIndices"]:
            segment = outline_geometry_engine.analyze_tunni_segment(
                current_path["nodes"],
                int(end_index),
                closed=bool(current_path.get("closed")),
                upm=upm,
                imbalance_threshold=0.0,
                min_handle_length=float(arguments["minHandleLength"]),
                grid_step=None,
            )
            if not segment.get("ok") or segment.get("reason") not in (None, "below_imbalance_threshold"):
                return "manual_tunni_geometry_ineligible"
            if float(segment.get("relativeImbalance", math.inf)) > float(arguments["imbalanceThreshold"]) + 1.0e-12:
                return "manual_tunni_imbalance_exceeded"
            indices = segment["nodeIndices"]
            for role, endpoint_role in (("handle1", "start"), ("handle2", "end")):
                node_index = int(indices[role])
                endpoint_index = int(indices[endpoint_role])
                before_handle = source_path["nodes"][node_index]
                after_handle = current_path["nodes"][node_index]
                endpoint = source_path["nodes"][endpoint_index]
                before_vector = (
                    float(before_handle["x"]) - float(endpoint["x"]),
                    float(before_handle["y"]) - float(endpoint["y"]),
                )
                after_vector = (
                    float(after_handle["x"]) - float(endpoint["x"]),
                    float(after_handle["y"]) - float(endpoint["y"]),
                )
                if before_vector[0] * after_vector[0] + before_vector[1] * after_vector[1] <= 0.0:
                    return "manual_tunni_wrong_ray_direction"
                if _vector_angle(before_vector, after_vector) > 0.25 + 1.0e-12:
                    return "manual_tunni_tangent_drift_exceeded"
                if math.hypot(
                    float(after_handle["x"]) - float(before_handle["x"]),
                    float(after_handle["y"]) - float(before_handle["y"]),
                ) > 0.25 * upm + 1.0e-12:
                    return "manual_tunni_movement_exceeded"
    return None


def _validate_candidate(entry, current, font):
    generated = entry["candidate"]
    operation = entry.get("operation")
    diffs, topology_error = _snapshot_diffs(
        generated,
        current,
        align_italic_anchors=operation == "italic_first_pass",
    )
    if topology_error:
        return None, topology_error
    allowed_coordinates = {
        (int(item["pathIndex"]), int(item["nodeIndex"]))
        for item in entry.get("allowed", {}).get("nodeCoordinates") or []
    }
    allowed_smooth = {
        (int(item["pathIndex"]), int(item["nodeIndex"]))
        for item in entry.get("allowed", {}).get("smoothFlags") or []
    }
    allowed_kinds = {
        "tunni": {"node_coordinate"},
        "collinear": {"node_smooth"},
        "italic_first_pass": {"node_coordinate", "node_smooth", "anchor_position", "component_transform", "width"},
        "compensated_tuning": {"node_coordinate", "node_smooth", "width"},
    }.get(operation, set())
    for diff in diffs:
        kind = diff["kind"]
        if kind not in allowed_kinds:
            return None, "operation_external_change"
        key = (int(diff.get("pathIndex", -1)), int(diff.get("nodeIndex", -1)))
        if operation == "tunni" and key not in allowed_coordinates:
            return None, "untargeted_handle_changed"
        if operation == "collinear" and key not in allowed_smooth:
            return None, "untargeted_connection_changed"
    grid_step = float(getattr(font, "gridLength", 1.0) or 1.0)
    if not math.isfinite(grid_step) or grid_step <= 0.0:
        return None, "invalid_font_grid"
    for path in current.get("paths") or []:
        for node in path.get("nodes") or []:
            if not math.isfinite(float(node["x"])) or not math.isfinite(float(node["y"])):
                return None, "nonfinite_coordinate"
    for diff in diffs:
        if diff["kind"] == "node_coordinate":
            if not _on_grid(diff["after"]["x"], grid_step) or not _on_grid(diff["after"]["y"], grid_step):
                return None, "coordinate_off_grid"
    if operation == "tunni":
        for target in entry.get("allowed", {}).get("nodeCoordinates") or []:
            node = current["paths"][int(target["pathIndex"])]["nodes"][int(target["nodeIndex"])]
            if not _on_grid(node["x"], grid_step) or not _on_grid(node["y"], grid_step):
                return None, "coordinate_off_grid"
        geometry_error = _validate_tunni_geometry(entry, current)
        if geometry_error:
            return None, geometry_error
    return diffs, None


def _candidate_current(font, entry):
    if not entry.get("materializedLayerId"):
        return copy.deepcopy(entry["candidate"]), None
    glyph = _glyph_for_name(font, entry.get("glyphName"))
    layer = _layer_for_id(glyph, entry.get("materializedLayerId")) if glyph else None
    if layer is None:
        raise ValueError("materialized_candidate_missing")
    metadata = _layer_metadata_get(layer)
    if not metadata or str(metadata.get("sessionId")) == "" or str(metadata.get("entryId")) != str(entry.get("entryId")):
        raise ValueError("candidate_metadata_missing_or_invalid")
    return _layer_snapshot(layer), layer


def _review_session_impl(font_index, session_id, include_diffs):
    font = _resolve_font(font_index)
    session = _load_session(font, session_id)
    source_fingerprints = {}
    candidate_fingerprints = {}
    records = []
    for entry in session.get("entries") or []:
        try:
            _glyph, _layer, source = _assert_current_source(font, entry)
            current, materialized_layer = _candidate_current(font, entry)
            diffs, reason = _validate_candidate(entry, current, font)
            if reason:
                raise ValueError(reason)
            source_fingerprint = _fingerprint(source)
            candidate_fingerprint = _fingerprint(current)
            source_fingerprints[entry["entryId"]] = source_fingerprint
            candidate_fingerprints[entry["entryId"]] = candidate_fingerprint
            record = {
                "entryId": entry["entryId"],
                "glyphName": entry["glyphName"],
                "status": "ready",
                "sourceStatus": "current",
                "candidateStatus": "manually_edited" if diffs else "generated_unchanged",
                "manualDeltaCount": len(diffs),
                "materializedLayerId": _get_layer_id(materialized_layer) if materialized_layer else None,
            }
            if include_diffs:
                record["manualDeltas"] = diffs[:MAX_DIFFS]
                record["manualDeltasTruncated"] = len(diffs) > MAX_DIFFS
            records.append(record)
        except Exception as error:
            records.append(
                {
                    "entryId": entry.get("entryId"),
                    "glyphName": entry.get("glyphName"),
                    "status": "blocked",
                    "reason": str(error),
                }
            )
    ready = all(record.get("status") == "ready" for record in records) and len(records) == len(session.get("entries") or [])
    return font, session, records, source_fingerprints, candidate_fingerprints, ready


@glyphs_tool()
async def review_outline_candidate_session(
    font_index: int = 0,
    session_id: str = None,
    include_diffs: bool = False,
) -> str:
    """Revalidate a generated or manually edited candidate and issue a token.

    The one-time five-minute token is bound to the exact source and candidate
    fingerprints. Layer renaming is cosmetic; topology changes, missing
    metadata, stale sources, off-grid coordinates, or operation-external edits
    block promotion. This review is read-only.
    """
    try:
        if not session_id:
            raise ValueError("session_id is required")
        if type(include_diffs) is not bool:
            raise ValueError("include_diffs must be a boolean")
        _font, session, records, source_fingerprints, candidate_fingerprints, ready = _run_on_main_thread(
            lambda: _review_session_impl(font_index, session_id, include_diffs)
        )
        token = None
        if ready:
            token = outline_candidate_state.STORE.issue_token(
                session_id, source_fingerprints, candidate_fingerprints
            )
        return _safe_json(
            {
                "ok": True,
                "candidateDataVersion": CANDIDATE_DATA_VERSION,
                "sessionId": session_id,
                "readyToAccept": ready,
                "entries": records,
                "reviewToken": token.get("token") if token else None,
                "reviewTokenExpiresAt": token.get("expiresAt") if token else None,
                "summary": {
                    "entryCount": len(records),
                    "readyCount": sum(1 for item in records if item.get("status") == "ready"),
                    "blockedCount": sum(1 for item in records if item.get("status") != "ready"),
                },
                "fontChanged": False,
                "fontSaved": False,
            }
        )
    except Exception as error:
        return _safe_json({"ok": False, "candidateDataVersion": CANDIDATE_DATA_VERSION, "error": str(error)})


def _token_matches(token, source_fingerprints, candidate_fingerprints):
    return (
        token.get("sourceFingerprints") == source_fingerprints
        and token.get("candidateFingerprints") == candidate_fingerprints
    )


def _backup_name(entry):
    operation = entry.get("operation")
    arguments = entry.get("arguments") or {}
    if operation == "italic_first_pass":
        angle = (arguments.get("review") or {}).get("angle", 12.0)
        return "GMCP Backup: Italic First Pass angle={}".format(float(angle))
    params = arguments.get("params") or {}
    return "GMCP Backup: CompTune (sx={} sy={} base={} ref={})".format(
        float(params.get("sx", 1.0)),
        float(params.get("sy", 1.0)),
        arguments.get("baseMasterId"),
        arguments.get("refMasterId"),
    )


def _end_change_batches(begun):
    """End batches without losing track of a layer whose end call failed."""
    while begun:
        layer = begun[-1]
        layer.endChanges()
        begun.pop()


def _accept_transaction(font_index, session_id, token, dry_run):
    font, session, records, source_fingerprints, candidate_fingerprints, ready = _review_session_impl(
        font_index, session_id, False
    )
    if not ready:
        raise ValueError("candidate_session_not_ready")
    if not _token_matches(token, source_fingerprints, candidate_fingerprints):
        raise ValueError("review_token_fingerprint_mismatch")
    plans = []
    for entry in session.get("entries") or []:
        glyph, layer, source = _assert_current_source(font, entry)
        desired, candidate_layer = _candidate_current(font, entry)
        diffs, reason = _validate_candidate(entry, desired, font)
        if reason:
            raise ValueError(reason)
        if not diffs:
            recomputed = _recompute_entry(entry)
            if not _snapshots_semantically_equal(
                recomputed,
                desired,
                align_italic_anchors=entry.get("operation") == "italic_first_pass",
            ):
                raise ValueError("generated_candidate_recompute_mismatch")
        plans.append((entry, glyph, layer, source, desired, candidate_layer))
    if dry_run:
        return {
            "ok": True,
            "candidateDataVersion": CANDIDATE_DATA_VERSION,
            "sessionId": session_id,
            "dryRun": True,
            "planned": [
                {
                    "entryId": entry["entryId"],
                    "glyphName": entry["glyphName"],
                    "operation": entry["operation"],
                    "materialized": candidate_layer is not None,
                }
                for entry, _glyph, _layer, _source, _desired, candidate_layer in plans
            ],
            "applied": [],
            "fontChanged": False,
            "fontSaved": False,
        }
    manifest_before = _manifest_raw(font)
    backups = []
    removed_candidates = []
    begun = []
    applied = []
    try:
        for entry, glyph, layer, _source, _desired, _candidate_layer in plans:
            begin = getattr(layer, "beginChanges", None)
            end = getattr(layer, "endChanges", None)
            if not callable(begin) or not callable(end):
                raise RuntimeError("change_batch_unavailable")
            begin()
            begun.append(layer)
        for entry, glyph, layer, source, desired, candidate_layer in plans:
            if entry["operation"] in ("italic_first_pass", "compensated_tuning"):
                backup = layer.copy()
                backup.name = _backup_name(entry)
                backup.associatedMasterId = str(entry["sourceMasterId"])
                glyph.layers.append(backup)
                backups.append((glyph, backup))
            _apply_allowed_snapshot(layer, desired, entry)
            actual = _layer_snapshot(layer)
            if not _snapshots_semantically_equal(
                desired,
                actual,
                align_italic_anchors=entry.get("operation") == "italic_first_pass",
            ):
                raise RuntimeError("source_readback_verification_failed")
            applied.append(entry["entryId"])
        _end_change_batches(begun)
        for entry, glyph, _layer, _source, _desired, candidate_layer in plans:
            if candidate_layer is not None:
                _remove_layer(glyph, candidate_layer)
                removed_candidates.append((glyph, candidate_layer, entry))
        _manifest_delete_session(font, session_id)
    except Exception as error:
        rollback_errors = []
        for layer in reversed(begun):
            try:
                layer.endChanges()
            except Exception as rollback_error:
                rollback_errors.append(str(rollback_error))
        for entry, _glyph, layer, source, _desired, _candidate_layer in plans:
            try:
                _apply_allowed_snapshot(layer, source, entry)
            except Exception as rollback_error:
                rollback_errors.append(str(rollback_error))
        if removed_candidates:
            try:
                _restore_removed_candidates(font, session, removed_candidates, manifest_before)
            except Exception as rollback_error:
                rollback_errors.append(str(rollback_error))
        for glyph, backup in reversed(backups):
            try:
                _remove_layer(glyph, backup)
            except Exception as rollback_error:
                rollback_errors.append(str(rollback_error))
        if not removed_candidates:
            try:
                _manifest_restore(font, manifest_before)
            except Exception as rollback_error:
                rollback_errors.append(str(rollback_error))
        return {
            "ok": False,
            "candidateDataVersion": CANDIDATE_DATA_VERSION,
            "sessionId": session_id,
            "dryRun": False,
            "error": str(error),
            "applied": [],
            "rollback": {"attempted": True, "succeeded": not rollback_errors, "errors": rollback_errors},
            "fontSaved": False,
        }
    try:
        outline_candidate_state.STORE.set_overlay(
            outline_candidate_state.STORE.state().get("sessionCount", 0) > 1,
            session_id,
            True,
        )
    except Exception:
        pass
    return {
        "ok": True,
        "candidateDataVersion": CANDIDATE_DATA_VERSION,
        "sessionId": session_id,
        "dryRun": False,
        "applied": [
            {"entryId": entry["entryId"], "glyphName": entry["glyphName"], "operation": entry["operation"]}
            for entry, _glyph, _layer, _source, _desired, _candidate_layer in plans
        ],
        "candidateLayersRemoved": len(removed_candidates),
        "backupLayersCreated": len(backups),
        "verification": {"succeeded": True, "entryCount": len(plans)},
        "rollback": {"attempted": False, "succeeded": True, "errors": []},
        "fontChanged": True,
        "fontSaved": False,
    }


@glyphs_tool()
async def accept_outline_candidate_session(
    font_index: int = 0,
    session_id: str = None,
    review_token: str = None,
    dry_run: bool = True,
    confirm: bool = False,
) -> str:
    """Promote the exact reviewed candidate state through operation-safe fields.

    Exactly one safety mode is required. A confirmed call consumes the one-time
    token before mutation, rechecks both fingerprints on the main thread,
    writes only operation-approved fields, verifies all read-back state,
    removes candidate layers after complete success, preserves required italic
    or tuning backups, rolls back failures, and never saves the font.
    """
    try:
        if not session_id or not review_token:
            raise ValueError("session_id and review_token are required")
        if type(dry_run) is not bool or type(confirm) is not bool or dry_run == confirm:
            raise ValueError("set exactly one of dry_run=true or confirm=true")
        if confirm:
            token, token_error = outline_candidate_state.STORE.consume_token(review_token, session_id)
        else:
            token, token_error = outline_candidate_state.STORE.get_token(review_token, session_id)
        if token_error:
            raise ValueError(token_error)
        return _safe_json(
            _run_on_main_thread(lambda: _accept_transaction(font_index, session_id, token, dry_run))
        )
    except Exception as error:
        return _safe_json({"ok": False, "candidateDataVersion": CANDIDATE_DATA_VERSION, "error": str(error)})


def _discard_transaction(font_index, session_id, dry_run):
    font = _resolve_font(font_index)
    session = _load_session(font, session_id)
    plans = []
    for entry in session.get("entries") or []:
        if not entry.get("materializedLayerId"):
            continue
        glyph = _glyph_for_name(font, entry.get("glyphName"))
        layer = _layer_for_id(glyph, entry.get("materializedLayerId")) if glyph else None
        metadata = _layer_metadata_get(layer) if layer else None
        if layer is None or not metadata:
            raise ValueError("materialized_candidate_missing_or_unowned")
        if str(metadata.get("sessionId")) != str(session_id) or str(metadata.get("entryId")) != str(entry.get("entryId")):
            raise ValueError("candidate_ownership_mismatch")
        plans.append((glyph, layer, entry))
    if dry_run:
        return {
            "ok": True,
            "candidateDataVersion": CANDIDATE_DATA_VERSION,
            "sessionId": session_id,
            "dryRun": True,
            "planned": [
                {"entryId": entry["entryId"], "glyphName": entry["glyphName"], "layerId": _get_layer_id(layer)}
                for _glyph, layer, entry in plans
            ],
            "deleted": [],
            "fontChanged": False,
            "fontSaved": False,
        }
    manifest_before = _manifest_raw(font)
    if not plans and not ((_manifest_get(font).get("sessions") or {}).get(str(session_id))):
        try:
            outline_candidate_state.STORE.set_overlay(
                outline_candidate_state.STORE.state().get("sessionCount", 0) > 1,
                session_id,
                True,
            )
        except Exception:
            pass
        return {
            "ok": True,
            "candidateDataVersion": CANDIDATE_DATA_VERSION,
            "sessionId": session_id,
            "dryRun": False,
            "deleted": [],
            "fontChanged": False,
            "fontSaved": False,
            "rollback": {"attempted": False, "succeeded": True, "errors": []},
        }
    removed = []
    try:
        for glyph, layer, entry in plans:
            _remove_layer(glyph, layer)
            removed.append((glyph, layer, entry))
        _manifest_delete_session(font, session_id)
    except Exception as error:
        rollback_errors = []
        for glyph, layer, _entry in removed:
            try:
                glyph.layers.append(layer)
            except Exception as rollback_error:
                rollback_errors.append(str(rollback_error))
        try:
            _manifest_restore(font, manifest_before)
        except Exception as rollback_error:
            rollback_errors.append(str(rollback_error))
        return {
            "ok": False,
            "candidateDataVersion": CANDIDATE_DATA_VERSION,
            "sessionId": session_id,
            "dryRun": False,
            "error": str(error),
            "rollback": {"attempted": True, "succeeded": not rollback_errors, "errors": rollback_errors},
            "fontSaved": False,
        }
    try:
        outline_candidate_state.STORE.set_overlay(
            outline_candidate_state.STORE.state().get("sessionCount", 0) > 1,
            session_id,
            True,
        )
    except Exception:
        pass
    return {
        "ok": True,
        "candidateDataVersion": CANDIDATE_DATA_VERSION,
        "sessionId": session_id,
        "dryRun": False,
        "deleted": [
            {"entryId": entry["entryId"], "glyphName": entry["glyphName"], "layerId": _get_layer_id(layer)}
            for _glyph, layer, entry in removed
        ],
        "fontChanged": bool(removed),
        "fontSaved": False,
        "rollback": {"attempted": False, "succeeded": True, "errors": []},
    }


@glyphs_tool()
async def discard_outline_candidate_session(
    font_index: int = 0,
    session_id: str = None,
    dry_run: bool = True,
    confirm: bool = False,
) -> str:
    """Delete only materialized layers owned by one candidate session.

    Exactly one safety mode is required. Ephemeral-only sessions can be cleared
    with ``set_outline_candidate_overlay``; confirmed discard verifies layer
    ownership metadata, rolls back partial deletion, and never saves the font.
    """
    try:
        if not session_id:
            raise ValueError("session_id is required")
        if type(dry_run) is not bool or type(confirm) is not bool or dry_run == confirm:
            raise ValueError("set exactly one of dry_run=true or confirm=true")
        return _safe_json(
            _run_on_main_thread(lambda: _discard_transaction(font_index, session_id, dry_run))
        )
    except Exception as error:
        return _safe_json({"ok": False, "candidateDataVersion": CANDIDATE_DATA_VERSION, "error": str(error)})


__all__ = [
    "accept_outline_candidate_session",
    "discard_outline_candidate_session",
    "get_outline_candidate_state",
    "materialize_outline_candidate_session",
    "preview_collinear_handles_candidate",
    "preview_compensated_tuning_candidate",
    "preview_italic_first_pass_candidate",
    "preview_tunni_balance_candidate",
    "review_outline_candidate_session",
    "set_outline_candidate_overlay",
]
