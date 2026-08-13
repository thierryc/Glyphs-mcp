# encoding: utf-8

from __future__ import division, print_function, unicode_literals

"""Guarded Glyphs adapter for deterministic joint start-node alignment."""

import copy
import hashlib
import json
import math

from GlyphsApp import Glyphs  # type: ignore[import-not-found]

from tool_registration import glyphs_tool
from mcp_tool_helpers import (
    _font_resolution_error,
    _get_layer_id,
    _glyphs_show_layer_link_fields,
    _layer_display_name,
    _layer_paths,
    _native_object_id,
    _node_orientation,
    _node_raw_connection,
    _node_raw_type,
    _normalized_node_type,
    _resolve_font_by_index,
    _run_on_main_thread,
    _safe_json,
    _set_path_nodes,
)

import cyclic_path_alignment_engine


MAX_MASTER_COUNT = cyclic_path_alignment_engine.MAX_MASTER_COUNT
MAX_RESULT_MASTERS = 32


def _point_values(value):
    try:
        return float(value.x), float(value.y)
    except Exception:
        try:
            return float(value[0]), float(value[1])
        except Exception:
            return 0.0, 0.0


def _plain_value(value, depth=0):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if depth >= 8:
        return "<{}>".format(type(value).__name__)
    if isinstance(value, dict):
        return {
            str(key): _plain_value(item, depth + 1)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_plain_value(item, depth + 1) for item in value]
    try:
        return [_plain_value(item, depth + 1) for item in list(value)]
    except Exception:
        return str(value)


def _mapping_value(owner, name):
    try:
        return _plain_value(dict(getattr(owner, name, None) or {}))
    except Exception:
        return {}


def _identity_token(value):
    for attribute_name in ("identityToken", "identity"):
        try:
            candidate = getattr(value, attribute_name, None)
        except Exception:
            candidate = None
        if candidate is not None and not callable(candidate):
            return "declared:{}:{}".format(type(value).__name__, candidate)
    return "native:{}:{}".format(type(value).__name__, _native_object_id(value))


def _node_signature(node):
    x, y = _point_values(getattr(node, "position", None))
    orientation, raw_orientation = _node_orientation(node)
    return {
        "identity": _identity_token(node),
        "x": x,
        "y": y,
        "type": _normalized_node_type(node),
        "rawType": _node_raw_type(node),
        "smooth": bool(getattr(node, "smooth", False)),
        "rawConnection": _node_raw_connection(node),
        "orientation": orientation,
        "rawOrientation": raw_orientation,
        "name": getattr(node, "name", None),
        "selected": bool(getattr(node, "selected", False)),
        "attributes": _mapping_value(node, "attributes"),
        "userData": _mapping_value(node, "userData"),
    }


def _path_signature(path):
    try:
        direction = int(getattr(path, "direction"))
    except Exception:
        direction = None
    nodes = list(getattr(path, "nodes", None) or [])
    return {
        "identity": _identity_token(path),
        "closed": bool(getattr(path, "closed", True)),
        "locked": bool(getattr(path, "locked", False)),
        "direction": direction,
        "attributes": _mapping_value(path, "attributes"),
        "userData": _mapping_value(path, "userData"),
        "nodes": [_node_signature(node) for node in nodes],
    }


def _component_signature(component):
    transform = getattr(component, "transform", None)
    try:
        transform = [float(value) for value in list(transform)]
    except Exception:
        transform = None
    return {
        "identity": _identity_token(component),
        "name": str(getattr(component, "componentName", None) or getattr(component, "name", "") or ""),
        "transform": transform,
        "smartValues": _plain_value(getattr(component, "smartComponentValues", None)),
    }


def _anchor_signature(anchor):
    x, y = _point_values(getattr(anchor, "position", None))
    return {
        "identity": _identity_token(anchor),
        "name": str(getattr(anchor, "name", "") or ""),
        "x": x,
        "y": y,
    }


def _collection_signature(values, fields):
    return [
        {
            "identity": _identity_token(item),
            **{field: _plain_value(getattr(item, field, None)) for field in fields},
        }
        for item in list(values or [])
    ]


def _shape_kind(shape):
    if hasattr(shape, "nodes"):
        return "path"
    if hasattr(shape, "componentName") or hasattr(shape, "component"):
        return "component"
    return type(shape).__name__


def _layer_signature(layer):
    paths = list(_layer_paths(layer))
    try:
        shapes = list(getattr(layer, "shapes", None) or [])
    except Exception:
        shapes = []
    if not shapes:
        shapes = list(paths) + list(getattr(layer, "components", None) or [])
    return {
        "layerId": _get_layer_id(layer),
        "width": _plain_value(getattr(layer, "width", None)),
        "paths": [_path_signature(path) for path in paths],
        "pathOrder": [_identity_token(path) for path in paths],
        "shapeOrder": [
            {"identity": _identity_token(shape), "kind": _shape_kind(shape)}
            for shape in shapes
        ],
        "components": [_component_signature(item) for item in list(getattr(layer, "components", None) or [])],
        "anchors": [_anchor_signature(item) for item in list(getattr(layer, "anchors", None) or [])],
        "hints": _collection_signature(getattr(layer, "hints", None), ("name", "type", "horizontal")),
        "guides": _collection_signature(getattr(layer, "guides", None), ("name", "angle", "locked")),
        "annotations": _collection_signature(getattr(layer, "annotations", None), ("text", "type", "angle")),
        "userData": _mapping_value(layer, "userData"),
    }


def _post_rotation_signature(signature, path_index):
    """Ignore host-recreated node identity only on the rotated target path."""
    verification = copy.deepcopy(signature)
    for node in verification["paths"][path_index]["nodes"]:
        node.pop("identity", None)
    return verification


def _expected_layer_signature(signature, path_index, rotation_offset):
    expected = copy.deepcopy(signature)
    nodes = list(expected["paths"][path_index]["nodes"])
    if nodes:
        offset = int(rotation_offset) % len(nodes)
        # Glyphs stores a closed path's start node at nodes[-1]. The SDK's
        # makeNodeFirst() contract therefore reports the left-rotation needed
        # to move the chosen node to the end.
        expected["paths"][path_index]["nodes"] = nodes[offset:] + nodes[:offset]
        if offset:
            return _post_rotation_signature(expected, path_index)
    return expected


def _first_difference(expected, actual, field="layer"):
    if type(expected) is not type(actual):
        return field
    if isinstance(expected, dict):
        if set(expected) != set(actual):
            return field + ".keys"
        for key in sorted(expected, key=str):
            different = _first_difference(expected[key], actual[key], "{}.{}".format(field, key))
            if different:
                return different
        return None
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return field + ".length"
        for index, (left, right) in enumerate(zip(expected, actual)):
            different = _first_difference(left, right, "{}[{}]".format(field, index))
            if different:
                return different
        return None
    if isinstance(expected, float):
        try:
            if math.isfinite(expected) and math.isfinite(actual) and abs(expected - actual) <= 1.0e-9:
                return None
        except Exception:
            pass
    return None if expected == actual else field


def _normalize_master_ids(value):
    if not isinstance(value, list) or not value:
        return None, "target_master_ids must be a nonempty list of unique strings"
    if any(not isinstance(master_id, str) or not master_id for master_id in value):
        return None, "target_master_ids must be a nonempty list of unique strings"
    if len(value) != len(set(value)):
        return None, "target_master_ids must not contain duplicates"
    if len(value) > MAX_MASTER_COUNT:
        return None, "target_master_ids exceeds the {}-master limit".format(MAX_MASTER_COUNT)
    return sorted(value), None


def _font_key(font):
    filepath = getattr(font, "filepath", None)
    if filepath:
        return str(filepath)
    return "memory:{}".format(_identity_token(font))


def _fingerprint(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _error(code, message, *, target=None, details=None, rollback=None):
    payload = {
        "ok": False,
        "alignmentDataVersion": cyclic_path_alignment_engine.ALIGNMENT_DATA_VERSION,
        "error": str(message),
        "errorType": str(code),
        "fontChanged": False,
        "fontSaved": False,
    }
    if isinstance(target, dict):
        payload["target"] = target
    if details is not None:
        payload["details"] = details
    if rollback is not None:
        payload["rollback"] = rollback
        payload["fontChanged"] = not bool(rollback.get("succeeded", False))
    return payload


def _target(font_index, glyph_name, path_index, reference_master_id, target_master_ids):
    return {
        "fontIndex": int(font_index),
        "glyphName": str(glyph_name or ""),
        "pathIndex": int(path_index) if isinstance(path_index, int) and not isinstance(path_index, bool) else None,
        "referenceMasterId": str(reference_master_id or ""),
        "targetMasterIds": list(target_master_ids or []),
    }


def _build_review_context(
    font_index,
    glyph_name,
    reference_master_id,
    path_index,
    reference_node_index,
    target_master_ids,
):
    master_ids, master_error = _normalize_master_ids(target_master_ids)
    target = _target(font_index, glyph_name, path_index, reference_master_id, master_ids or [])
    if master_error:
        return None, _error("invalid_target_master_ids", master_error, target=target)
    if not glyph_name:
        return None, _error("glyph_name_required", "glyph_name is required", target=target)
    if not reference_master_id or reference_master_id not in master_ids:
        return None, _error(
            "reference_master_not_found",
            "reference_master_id must be included in target_master_ids",
            target=target,
        )
    if isinstance(path_index, bool) or not isinstance(path_index, int):
        return None, _error("path_index_invalid", "path_index must be an integer", target=target)
    if isinstance(reference_node_index, bool) or not isinstance(reference_node_index, int):
        return None, _error(
            "reference_node_invalid",
            "reference_node_index must be an integer",
            target=target,
        )

    font, fonts = _resolve_font_by_index(Glyphs, font_index)
    if not font:
        error = _font_resolution_error(font_index, fonts, ok_key="ok")
        return None, _error("font_not_found", error.get("error") or "Font not found", target=target)
    try:
        glyph = font.glyphs[str(glyph_name)]
    except Exception:
        glyph = None
    if glyph is None:
        return None, _error("glyph_not_found", "Glyph '{}' not found".format(glyph_name), target=target)

    engine_paths = []
    layer_contexts = []
    public_masters = []
    for master_id in master_ids:
        try:
            layer = glyph.layers[str(master_id)]
        except Exception:
            layer = None
        if layer is None:
            return None, _error(
                "master_layer_not_found",
                "Master layer '{}' was not found".format(master_id),
                target=target,
            )
        paths = list(_layer_paths(layer))
        if path_index < 0 or path_index >= len(paths):
            return None, _error(
                "path_index_out_of_range",
                "path_index {} is out of range for master '{}'".format(path_index, master_id),
                target=target,
            )
        path = paths[path_index]
        node_objects = list(getattr(path, "nodes", None) or [])
        if not node_objects:
            return None, _error("invalid_node_count", "Target paths must contain nodes", target=target)
        if _normalized_node_type(node_objects[-1]) == "offcurve":
            return None, _error(
                "current_start_not_oncurve",
                "Every target path must currently start on an on-curve node for verified rollback.",
                target=target,
                details={"masterId": master_id},
            )
        layer_signature = _layer_signature(layer)
        path_signature = layer_signature["paths"][path_index]
        engine_nodes = [
            {
                "x": node["x"],
                "y": node["y"],
                "type": node["type"],
                "smooth": node["smooth"],
            }
            for node in path_signature["nodes"]
        ]
        engine_paths.append(
            {
                "masterId": master_id,
                "closed": path_signature["closed"],
                "direction": path_signature["direction"],
                "nodes": engine_nodes,
            }
        )
        layer_contexts.append(
            {
                "masterId": master_id,
                "layer": layer,
                "path": path,
                "nodeObjects": node_objects,
                "originalStartNode": node_objects[-1],
                "signature": layer_signature,
            }
        )
        public_masters.append(
            {
                "masterId": master_id,
                "layerId": _get_layer_id(layer),
                "layerName": _layer_display_name(font, layer, master_id),
                "nodeCount": len(node_objects),
            }
        )

    reference_context = next(item for item in layer_contexts if item["masterId"] == reference_master_id)
    reference_nodes = reference_context["nodeObjects"]
    if reference_node_index < 0 or reference_node_index >= len(reference_nodes):
        return None, _error(
            "reference_node_out_of_range",
            "reference_node_index is out of range",
            target=target,
        )
    reference_node = reference_nodes[reference_node_index]
    if _normalized_node_type(reference_node) == "offcurve":
        return None, _error(
            "reference_node_not_oncurve",
            "The reference node must be on-curve",
            target=target,
        )
    if not bool(getattr(reference_node, "selected", False)):
        return None, _error(
            "reference_node_not_selected",
            "The explicit reference node must be selected in Glyphs",
            target=target,
        )

    plan = cyclic_path_alignment_engine.plan_joint_alignment(
        engine_paths,
        reference_master_id=reference_master_id,
        reference_node_index=reference_node_index,
    )
    if not plan.get("ok"):
        return None, _error(
            plan.get("errorType") or "alignment_blocked",
            plan.get("error") or "Joint start-node alignment requires manual review.",
            target=target,
            details=plan.get("details"),
        )
    by_master_plan = {item["masterId"]: item for item in plan["masters"]}
    for context in layer_contexts:
        item = by_master_plan[context["masterId"]]
        context["plan"] = item
        context["targetNode"] = context["nodeObjects"][int(item["proposedStartNodeIndex"])]
        context["expectedSignature"] = _expected_layer_signature(
            context["signature"], path_index, int(item["rotationOffset"])
        )

    fingerprint_payload = {
        "fontKey": _font_key(font),
        "glyphName": str(glyph_name),
        "pathIndex": int(path_index),
        "referenceMasterId": str(reference_master_id),
        "referenceNodeIndex": int(reference_node_index),
        "targetMasterIds": master_ids,
        "layers": [
            {"masterId": item["masterId"], "signature": item["signature"]}
            for item in layer_contexts
        ],
        "plan": plan,
    }
    plan_fingerprint = _fingerprint(fingerprint_payload)
    target["targetMasterIds"] = master_ids
    result = {
        "ok": True,
        "alignmentDataVersion": cyclic_path_alignment_engine.ALIGNMENT_DATA_VERSION,
        "status": plan["status"],
        "target": target,
        "reference": plan["reference"],
        "masters": plan["masters"][:MAX_RESULT_MASTERS],
        "planFingerprint": plan_fingerprint,
        "summary": dict(plan["summary"]),
        "fontChanged": False,
        "fontSaved": False,
        "warnings": [],
    }
    result["summary"]["readyToApply"] = True
    if len(plan["masters"]) > MAX_RESULT_MASTERS:
        result["summary"]["omittedMasterCount"] = len(plan["masters"]) - MAX_RESULT_MASTERS
    result.update(
        _glyphs_show_layer_link_fields(
            getattr(font, "filepath", None),
            glyph_name=str(glyph_name),
            layer_id=reference_context["signature"]["layerId"],
            label="Open {} {} in Glyphs".format(
                glyph_name,
                next(item["layerName"] for item in public_masters if item["masterId"] == reference_master_id),
            ),
        )
    )
    return {
        "font": font,
        "glyph": glyph,
        "pathIndex": int(path_index),
        "contexts": layer_contexts,
        "result": result,
    }, None


def _end_batches(begun):
    errors = []
    while begun:
        context = begun.pop()
        try:
            context["layer"].endChanges()
        except Exception as exc:
            errors.append({"masterId": context["masterId"], "message": str(exc)})
    return errors


def _restore_context(context, path_index):
    errors = []
    path = context["path"]
    original_start = context["originalStartNode"]
    try:
        original_start.makeNodeFirst()
    except Exception as exc:
        if not _set_path_nodes(path, context["nodeObjects"]):
            errors.append({"masterId": context["masterId"], "message": str(exc)})
    actual = _layer_signature(context["layer"])
    difference = _first_difference(context["signature"], actual)
    if difference:
        if _set_path_nodes(path, context["nodeObjects"]):
            actual = _layer_signature(context["layer"])
            difference = _first_difference(context["signature"], actual)
        if difference:
            errors.append({"masterId": context["masterId"], "field": difference})
    return errors


def _apply_context(review_context):
    contexts = list(review_context["contexts"])
    path_index = int(review_context["pathIndex"])
    begun = []
    applied = []
    mutation_error = None
    try:
        for context in contexts:
            begin = getattr(context["layer"], "beginChanges", None)
            end = getattr(context["layer"], "endChanges", None)
            if not callable(begin) or not callable(end):
                raise RuntimeError("change_batch_unavailable:{}".format(context["masterId"]))
            begin()
            begun.append(context)
        for context in contexts:
            rotation = int(context["plan"]["rotationOffset"])
            if rotation:
                context["targetNode"].makeNodeFirst()
                applied.append(
                    {
                        "masterId": context["masterId"],
                        "pathIndex": path_index,
                        "sourceNodeIndex": int(context["plan"]["proposedStartNodeIndex"]),
                        "resultNodeIndex": len(context["nodeObjects"]) - 1,
                    }
                )
        for context in contexts:
            actual = _layer_signature(context["layer"])
            if int(context["plan"]["rotationOffset"]):
                actual = _post_rotation_signature(actual, path_index)
            difference = _first_difference(context["expectedSignature"], actual)
            if difference:
                raise RuntimeError("verification_failed:{}:{}".format(context["masterId"], difference))
    except Exception as exc:
        mutation_error = str(exc)

    if mutation_error:
        rollback_errors = []
        for context in reversed(contexts):
            rollback_errors.extend(_restore_context(context, path_index))
        end_errors = _end_batches(begun)
        rollback_errors.extend(end_errors)
        rollback = {
            "attempted": True,
            "succeeded": not rollback_errors,
            "errors": rollback_errors,
        }
        code = "rollback_failed" if rollback_errors else (
            "verification_failed" if mutation_error.startswith("verification_failed") else "mutation_failed"
        )
        return _error(code, mutation_error, target=review_context["result"]["target"], rollback=rollback)

    end_errors = _end_batches(begun)
    if end_errors:
        rollback_errors = []
        for context in reversed(contexts):
            rollback_errors.extend(_restore_context(context, path_index))
        rollback_errors.extend(end_errors)
        rollback = {
            "attempted": True,
            "succeeded": not rollback_errors,
            "errors": rollback_errors,
        }
        return _error(
            "rollback_failed" if rollback_errors else "end_changes_failed",
            "One or more layer change batches could not be closed.",
            target=review_context["result"]["target"],
            rollback=rollback,
        )

    # Verify again after every batch has closed.
    for context in contexts:
        actual = _layer_signature(context["layer"])
        if int(context["plan"]["rotationOffset"]):
            actual = _post_rotation_signature(actual, path_index)
        difference = _first_difference(context["expectedSignature"], actual)
        if difference:
            rollback_errors = []
            for restore_context in reversed(contexts):
                rollback_errors.extend(_restore_context(restore_context, path_index))
            rollback = {
                "attempted": True,
                "succeeded": not rollback_errors,
                "errors": rollback_errors,
            }
            return _error(
                "rollback_failed" if rollback_errors else "verification_failed",
                "Post-batch verification failed at {}.".format(difference),
                target=review_context["result"]["target"],
                rollback=rollback,
            )
    return {
        "applied": applied,
        "verification": {
            "succeeded": True,
            "coordinatesPreserved": True,
            "nodeFieldsPreserved": True,
            "contourDirectionPreserved": True,
            "pathAndShapeOrderPreserved": True,
            "openPathsPreserved": True,
            "compatibilityPreserved": True,
        },
        "rollback": {"attempted": False, "succeeded": True, "errors": []},
        "changeBatch": {"layerCount": len(contexts), "completed": True},
    }


@glyphs_tool()
async def review_start_node_alignment(
    font_index: int = 0,
    glyph_name: str = None,
    reference_master_id: str = None,
    path_index: int = None,
    reference_node_index: int = None,
    target_master_ids: list = None,
) -> str:
    """Review one joint start-node phase across explicit compatible masters."""

    try:
        context, error = _run_on_main_thread(
            lambda: _build_review_context(
                font_index,
                glyph_name,
                reference_master_id,
                path_index,
                reference_node_index,
                target_master_ids,
            )
        )
        return _safe_json(error or context["result"])
    except Exception as exc:
        return _safe_json(_error("review_failed", str(exc)))


@glyphs_tool()
async def apply_start_node_alignment(
    font_index: int = 0,
    glyph_name: str = None,
    reference_master_id: str = None,
    path_index: int = None,
    reference_node_index: int = None,
    target_master_ids: list = None,
    expected_plan_fingerprint: str = None,
    dry_run: bool = False,
    confirm: bool = False,
) -> str:
    """Dry-run or atomically apply one fingerprint-bound joint start-node plan."""

    try:
        if type(dry_run) is not bool or type(confirm) is not bool or dry_run == confirm:
            return _safe_json(
                _error(
                    "confirmation_required",
                    "Set exactly one of dry_run=true or confirm=true.",
                )
            )
        if not isinstance(expected_plan_fingerprint, str) or not expected_plan_fingerprint:
            return _safe_json(
                _error(
                    "plan_fingerprint_required",
                    "expected_plan_fingerprint is required.",
                )
            )

        def action():
            context, error = _build_review_context(
                font_index,
                glyph_name,
                reference_master_id,
                path_index,
                reference_node_index,
                target_master_ids,
            )
            if error:
                return error
            result = context["result"]
            if result["planFingerprint"] != expected_plan_fingerprint:
                return _error(
                    "stale_plan",
                    "The reviewed start-node plan is stale; review it again.",
                    target=result["target"],
                    details={
                        "expectedPlanFingerprint": expected_plan_fingerprint,
                        "currentPlanFingerprint": result["planFingerprint"],
                    },
                )
            if dry_run:
                output = copy.deepcopy(result)
                output.update(
                    {
                        "dryRun": True,
                        "applied": [],
                        "verification": {"succeeded": True, "planCurrent": True},
                    }
                )
                return output
            mutation = _apply_context(context)
            if not mutation.get("applied") and mutation.get("ok") is False:
                return mutation
            output = copy.deepcopy(result)
            output.update(mutation)
            output["ok"] = True
            output["status"] = "applied" if mutation["applied"] else "already_aligned"
            output["fontChanged"] = bool(mutation["applied"])
            output["fontSaved"] = False
            output["summary"]["appliedCount"] = len(mutation["applied"])
            return output

        return _safe_json(_run_on_main_thread(action))
    except Exception as exc:
        return _safe_json(_error("apply_failed", str(exc)))


__all__ = ["apply_start_node_alignment", "review_start_node_alignment"]
