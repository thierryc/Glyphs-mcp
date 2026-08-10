# encoding: utf-8

from __future__ import division, print_function, unicode_literals

"""Native drawing-only Reporter for detached Glyphs MCP outline candidates."""

import copy
import json
import traceback

import objc  # type: ignore[import-not-found]
from AppKit import NSBezierPath, NSColor, NSGraphicsContext, NSPoint  # type: ignore[import-not-found]
from GlyphsApp import Glyphs  # type: ignore[import-not-found]
from GlyphsApp.plugins import ReporterPlugin  # type: ignore[import-not-found]

import candidate_difference_model
import outline_candidate_state
from mcp_tool_helpers import _get_layer_id, _layer_paths, _normalized_node_type


REPORTER_CLASS_NAME = "GlyphsMCPCandidateReporter"
REPORTER_MENU_NAME = "Glyphs MCP Candidate"
REPORTER_MENU_PATH = "View > Show Glyphs MCP Candidate"
LAYER_METADATA_KEY = "com.thierrycharbonnel.glyphs-mcp.outlineCandidate.v1"
FONT_MANIFEST_KEY = "com.thierrycharbonnel.glyphs-mcp.outlineCandidates.v1"
CANDIDATE_DATA_VERSION = outline_candidate_state.CANDIDATE_DATA_VERSION

DISPLAY_MODE = "difference_only"
DIFFERENCE_COMPOSITOR = "appkit_topology_paired_contour_ribbons"
DIFFERENCE_RGBA = (1.0, 191.0 / 255.0, 31.0 / 255.0, 0.82)
STALE_DIFFERENCE_RGBA = (1.0, 90.0 / 255.0, 78.0 / 255.0, 0.82)
OPEN_PATH_STROKE_PIXELS = 1.5


def _point_values(node):
    position = getattr(node, "position", None)
    try:
        return float(position.x), float(position.y)
    except Exception:
        return float(position[0]), float(position[1])


def _plain_paths(layer):
    result = []
    for path in list(_layer_paths(layer)):
        record = {
            "closed": bool(getattr(path, "closed", True)),
            "nodes": [
                {
                    "x": _point_values(node)[0],
                    "y": _point_values(node)[1],
                    "type": _normalized_node_type(node),
                }
                for node in list(getattr(path, "nodes", None) or [])
            ],
        }
        result.append(record)
    return result


def _detached_display_paths(layer):
    """Return component-expanded paths without touching the live layer."""
    try:
        components = list(getattr(layer, "components", None) or [])
    except Exception as error:
        raise RuntimeError("candidate_component_expansion_failed") from error
    if not components:
        return _plain_paths(layer)
    try:
        detached = layer.copy()
        decompose = getattr(detached, "decomposeComponents", None)
        if not callable(decompose):
            raise AttributeError("decomposeComponents is unavailable")
        decompose()
        return _plain_paths(detached)
    except Exception as error:
        raise RuntimeError("candidate_component_expansion_failed") from error


def _path_signature(paths):
    return outline_candidate_state.fingerprint(
        [
            {
                "closed": bool(path.get("closed")),
                "nodes": [
                    {"x": float(node.get("x", 0.0)), "y": float(node.get("y", 0.0)), "type": node.get("type")}
                    for node in path.get("nodes") or []
                ],
            }
            for path in paths or []
        ]
    )


def _glyph_context(layer):
    glyph = getattr(layer, "parent", None)
    font = getattr(glyph, "parent", None)
    glyph_name = str(getattr(glyph, "name", "") or "")
    filepath = getattr(font, "filepath", None)
    font_key = str(filepath) if filepath else "memory:{}".format(id(font))
    return font, glyph, font_key, glyph_name


def _metadata_entry(layer):
    try:
        metadata = layer.userData[LAYER_METADATA_KEY]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        if isinstance(metadata, dict):
            return copy.deepcopy(metadata.get("entry") or {})
    except Exception:
        pass
    return None


def _resolve_entry(layer):
    font, glyph, font_key, glyph_name = _glyph_context(layer)
    session, entry, materialized = outline_candidate_state.STORE.matching_entry(
        font_key, glyph_name, _get_layer_id(layer)
    )
    if entry is not None:
        return session, entry, materialized
    metadata_entry = _metadata_entry(layer)
    if metadata_entry:
        return {"sessionId": "materialized", "persisted": True}, metadata_entry, True
    try:
        manifest = font.userData[FONT_MANIFEST_KEY]
        if isinstance(manifest, str):
            manifest = json.loads(manifest)
        for record in (manifest.get("sessions") or {}).values():
            persisted_session = copy.deepcopy(record.get("session") or {})
            for persisted_entry in persisted_session.get("entries") or []:
                if (
                    str(persisted_entry.get("glyphName")) == glyph_name
                    and str(persisted_entry.get("sourceLayerId")) == str(_get_layer_id(layer))
                ):
                    persisted_session["persisted"] = True
                    return persisted_session, persisted_entry, False
    except Exception:
        pass
    return None, None, False


def _node_point(node):
    return (float(node.get("x", 0.0)), float(node.get("y", 0.0)))


def _path_geometry_matches(source, candidate):
    source_nodes = list(source.get("nodes") or [])
    candidate_nodes = list(candidate.get("nodes") or [])
    return (
        bool(source.get("closed")) == bool(candidate.get("closed"))
        and len(source_nodes) == len(candidate_nodes)
        and all(
            before.get("type") == after.get("type")
            and _node_point(before) == _node_point(after)
            for before, after in zip(source_nodes, candidate_nodes)
        )
    )


def _path_segments(path_data):
    nodes = list(path_data.get("nodes") or [])
    oncurve_indices = [index for index, node in enumerate(nodes) if node.get("type") != "offcurve"]
    if not oncurve_indices:
        return []
    start_index = oncurve_indices[0]
    current = nodes[start_index]
    if bool(path_data.get("closed")):
        sequence = [nodes[(start_index + offset) % len(nodes)] for offset in range(1, len(nodes) + 1)]
    else:
        sequence = nodes[start_index + 1 :]
    result = []
    handles = []
    for node in sequence:
        if node.get("type") == "offcurve":
            handles.append(node)
            continue
        if node.get("type") == "curve" and len(handles) >= 2:
            result.append(
                (
                    "cubic",
                    (
                        _node_point(current),
                        _node_point(handles[-2]),
                        _node_point(handles[-1]),
                        _node_point(node),
                    ),
                )
            )
        else:
            result.append(("line", (_node_point(current), _node_point(node))))
        handles = []
        current = node
    return result


def _ns_point(point):
    return NSPoint(float(point[0]), float(point[1]))


def _append_segments(path, segments, reverse=False, move=True):
    if not segments:
        raise RuntimeError("candidate_difference_empty_path")
    start = segments[-1][1][-1] if reverse else segments[0][1][0]
    if move:
        path.moveToPoint_(_ns_point(start))
    ordered = reversed(segments) if reverse else segments
    for kind, points in ordered:
        if kind == "cubic":
            if reverse:
                start_point, control1, control2, _end = points
                path.curveToPoint_controlPoint1_controlPoint2_(
                    _ns_point(start_point),
                    _ns_point(control2),
                    _ns_point(control1),
                )
            else:
                _start, control1, control2, end = points
                path.curveToPoint_controlPoint1_controlPoint2_(
                    _ns_point(end),
                    _ns_point(control1),
                    _ns_point(control2),
                )
        else:
            end = points[0] if reverse else points[-1]
            path.lineToPoint_(_ns_point(end))


def _append_closed_difference(path, source_segments, candidate_segments):
    _append_segments(path, source_segments)
    path.closePath()
    _append_segments(path, candidate_segments, reverse=True)
    path.closePath()


def _append_open_difference(path, source_segments, candidate_segments):
    _append_segments(path, source_segments)
    candidate_end = candidate_segments[-1][1][-1]
    path.lineToPoint_(_ns_point(candidate_end))
    _append_segments(path, candidate_segments, reverse=True, move=False)
    path.closePath()


def _draw_difference(source_paths, candidate_paths, rgba, scale):
    if NSGraphicsContext.currentContext() is None:
        raise RuntimeError("difference_graphics_context_unavailable")
    _ = scale
    source_paths = list(source_paths or [])
    candidate_paths = list(candidate_paths or [])
    if len(source_paths) != len(candidate_paths):
        raise RuntimeError("candidate_difference_topology_incompatible")

    prepared = []
    closed_changed = False
    open_changed = False
    for source, candidate in zip(source_paths, candidate_paths):
        if _path_geometry_matches(source, candidate):
            continue
        if bool(source.get("closed")) != bool(candidate.get("closed")):
            raise RuntimeError("candidate_difference_topology_incompatible")
        source_segments = _path_segments(source)
        candidate_segments = _path_segments(candidate)
        if (
            not source_segments
            or len(source_segments) != len(candidate_segments)
            or [item[0] for item in source_segments] != [item[0] for item in candidate_segments]
        ):
            raise RuntimeError("candidate_difference_topology_incompatible")
        prepared.append((bool(source.get("closed")), source_segments, candidate_segments))
        if bool(source.get("closed")):
            closed_changed = True
        else:
            open_changed = True

    if not prepared:
        return 0

    difference_path = NSBezierPath.bezierPath()
    for closed, source_segments, candidate_segments in prepared:
        if closed:
            _append_closed_difference(difference_path, source_segments, candidate_segments)
        else:
            _append_open_difference(difference_path, source_segments, candidate_segments)
    NSColor.colorWithDeviceRed_green_blue_alpha_(
        float(rgba[0]),
        float(rgba[1]),
        float(rgba[2]),
        float(rgba[3]),
    ).set()
    difference_path.fill()
    return int(closed_changed) + int(open_changed)


def _changes(source, candidate):
    result = []
    for path_index, source_path in enumerate(source.get("paths") or []):
        try:
            candidate_nodes = candidate["paths"][path_index]["nodes"]
        except Exception:
            continue
        for node_index, before in enumerate(source_path.get("nodes") or []):
            try:
                after = candidate_nodes[node_index]
            except Exception:
                continue
            if float(before["x"]) != float(after["x"]) or float(before["y"]) != float(after["y"]):
                result.append(
                    {
                        "pathIndex": path_index,
                        "nodeIndex": node_index,
                        "start": (float(before["x"]), float(before["y"])),
                        "end": (float(after["x"]), float(after["y"])),
                    }
                )
    return result


class GlyphsMCPCandidateReporter(ReporterPlugin):

    @objc.python_method
    def settings(self):
        self.menuName = REPORTER_MENU_NAME
        self.keyboardShortcut = None
        self._last_draw = None
        self._last_error = None
        try:
            outline_candidate_state.STORE.set_redraw_callback(getattr(Glyphs, "redraw", None))
        except Exception:
            pass

    @objc.python_method
    def background(self, layer):
        # Difference rendering belongs entirely in foreground(). Drawing a
        # source or candidate outline behind the live layer would obscure the
        # normal Glyphs comparison and violate the difference-only contract.
        return

    @objc.python_method
    def foreground(self, layer):
        if layer is None:
            return
        self._last_draw = None
        try:
            session, entry, materialized = _resolve_entry(layer)
            if entry is None:
                return
            if (
                not materialized
                and not (session or {}).get("persisted")
                and not outline_candidate_state.STORE.state().get("enabled", False)
            ):
                return
            candidate = entry.get("candidate") or {}
            source = entry.get("source") or {}
            source_layer = layer if not materialized else None
            if materialized:
                # The native layer is the editable candidate. Draw its current
                # detached geometry, not the generated snapshot stored in the
                # manifest, so manual edits are visible immediately.
                candidate = copy.deepcopy(candidate)
                candidate["paths"] = _plain_paths(layer)
                candidate["displayPaths"] = _detached_display_paths(layer)
                _font, glyph, _font_key, _glyph_name = _glyph_context(layer)
                for possible_source in list(getattr(glyph, "layers", None) or []):
                    if str(_get_layer_id(possible_source)) == str(entry.get("sourceLayerId")):
                        source_layer = possible_source
                        break
            if source_layer is None:
                raise RuntimeError("candidate_source_layer_not_found")
            live_source_paths = _plain_paths(source_layer)
            stale = _path_signature(live_source_paths) != _path_signature(source.get("paths"))
            source_display_paths = _detached_display_paths(source_layer)
            candidate_display_paths = candidate.get("displayPaths") or candidate.get("paths") or []
            difference = candidate_difference_model.analyze_difference(
                source_display_paths,
                candidate_display_paths,
            )
            difference_group_count = 0
            if difference.get("geometryDifferencePresent"):
                difference_group_count = _draw_difference(
                    source_display_paths,
                    candidate_display_paths,
                    STALE_DIFFERENCE_RGBA if stale else DIFFERENCE_RGBA,
                    self.getScale(),
                )
            changes = _changes(source, candidate)
            self._last_draw = {
                "candidateDataVersion": CANDIDATE_DATA_VERSION,
                "candidateDifferenceDataVersion": difference.get("candidateDifferenceDataVersion"),
                "displayMode": DISPLAY_MODE,
                "differenceCompositor": DIFFERENCE_COMPOSITOR,
                "sessionId": (session or {}).get("sessionId"),
                "entryId": entry.get("entryId"),
                "glyphName": entry.get("glyphName"),
                "sourceLayerId": entry.get("sourceLayerId"),
                "operation": (session or {}).get("operation") or entry.get("operation"),
                "materialized": bool(materialized),
                "stale": bool(stale),
                "changedNodeCount": len(changes),
                "curvatureStrokeCount": 0,
                "geometryDifferencePresent": bool(difference.get("geometryDifferencePresent")),
                "topologyCompatible": bool(difference.get("topologyCompatible")),
                "changedPathCount": int(difference.get("changedPathCount") or 0),
                "maxNodeMovement": difference.get("maxNodeMovement"),
                "maxOutlineDisplacement": difference.get("maxOutlineDisplacement"),
                "differenceGroupCount": int(difference_group_count),
                "samplingTruncated": bool(difference.get("samplingTruncated")),
            }
            self._last_error = None
        except Exception as error:
            message = str(error)
            if message == "difference_graphics_context_unavailable":
                code = message
            elif message == "candidate_source_layer_not_found":
                code = message
            elif message == "candidate_component_expansion_failed":
                code = message
            elif message in (
                "candidate_difference_empty_path",
                "candidate_difference_topology_incompatible",
            ):
                code = message
            else:
                code = "candidate_difference_draw_failed"
            self._last_error = {"code": code, "message": message}
            try:
                print("[Glyphs MCP][Candidate Reporter] {}".format(traceback.format_exc()))
            except Exception:
                pass

    @objc.python_method
    def foregroundInViewCoords(self):
        if not self._last_draw:
            return
        try:
            font = getattr(Glyphs, "font", None)
            tab = getattr(font, "currentTab", None)
            viewport = getattr(tab, "viewPort", None)
            if tab is None or viewport is None:
                return
            scale = max(float(getattr(tab, "scale", None) or self.getScale() or 1.0), 1.0e-6)
            origin = viewport.origin
            stale = bool(self._last_draw.get("stale"))
            if stale:
                label = "STALE — regenerate Glyphs MCP candidate"
            elif not self._last_draw.get("geometryDifferencePresent"):
                label = "No visible outline difference"
            else:
                operation = str(self._last_draw.get("operation") or "candidate").replace("_", " ").title()
                changed_paths = int(self._last_draw.get("changedPathCount") or 0)
                displacement = self._last_draw.get("maxOutlineDisplacement")
                displacement_text = "unknown" if displacement is None else "{:.2f}u".format(float(displacement))
                label = "{} candidate · {} path{} · max Δ {}".format(
                    operation,
                    changed_paths,
                    "" if changed_paths == 1 else "s",
                    displacement_text,
                )
            color = NSColor.colorWithDeviceRed_green_blue_alpha_(
                *(STALE_DIFFERENCE_RGBA if stale else DIFFERENCE_RGBA)
            )
            self.drawTextAtPoint(
                label,
                NSPoint(float(origin.x) + 12.0 * scale, float(origin.y) + 12.0 * scale),
                fontSize=10.0 * scale,
                fontColor=color,
            )
        except Exception:
            pass

    @objc.python_method
    def overlayStateSnapshot(self):
        return {
            "candidateDataVersion": CANDIDATE_DATA_VERSION,
            "displayMode": DISPLAY_MODE,
            "differenceCompositor": DIFFERENCE_COMPOSITOR,
            "reporterClass": REPORTER_CLASS_NAME,
            "menuPath": REPORTER_MENU_PATH,
            "colors": {
                "difference": DIFFERENCE_RGBA,
                "staleDifference": STALE_DIFFERENCE_RGBA,
            },
            "lastDraw": dict(self._last_draw) if self._last_draw else None,
            "lastError": dict(self._last_error) if self._last_error else None,
        }

    @objc.python_method
    def __file__(self):
        return __file__


__all__ = [
    "DIFFERENCE_RGBA",
    "DIFFERENCE_COMPOSITOR",
    "DISPLAY_MODE",
    "GlyphsMCPCandidateReporter",
    "OPEN_PATH_STROKE_PIXELS",
    "REPORTER_CLASS_NAME",
    "REPORTER_MENU_NAME",
    "REPORTER_MENU_PATH",
    "STALE_DIFFERENCE_RGBA",
]
