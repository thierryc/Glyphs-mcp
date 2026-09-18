"""Produce read-only Glyphs geometry snapshots for the desktop Git diff browser."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from glyphs_mcp_protocol.geometry import (
    GLYPH_DIFF_PROTOCOL_API_VERSION,
    GLYPH_DIFF_SCHEMA_VERSION,
    comparison,
    component_path_elements,
    resolved_closed_layer_elements,
    resolved_open_layer_elements,
)

SCHEMA_VERSION = GLYPH_DIFF_SCHEMA_VERSION
PROTOCOL_API_VERSION = GLYPH_DIFF_PROTOCOL_API_VERSION


def _value(obj, name, default=None):
    try:
        value = getattr(obj, name)
        return value() if callable(value) else value
    except Exception:
        return default


def _elements(values):
    return [{"kind": kind, "points": points} for kind, points in values]


def _component_outlines(layer):
    """Return each referenced component as its own transformed closed outline."""
    components = []
    shapes = _value(layer, "shapes", None)
    if shapes is not None:
        try:
            components = [shape for shape in shapes if _value(shape, "componentName")]
        except Exception:
            components = []
    if not components:
        components = _value(layer, "components", []) or []
    try:
        components = list(components)
    except Exception:
        return [], [{"scope": "components", "message": "Component geometry is unavailable."}]
    outlines, warnings = [], []
    for index, component in enumerate(components):
        name = str(_value(component, "componentName", "") or index)
        try:
            values = component_path_elements(component, context="component {!r}".format(name))
        except ValueError as error:
            warnings.append({"scope": "component", "message": str(error)})
            continue
        if values:
            outlines.append(_elements(values))
    return outlines, warnings


def _glyph_name(path):
    from Foundation import NSData, NSPropertyListSerialization

    data = NSData.dataWithContentsOfFile_(str(path))
    if data is None:
        return None
    loaded = NSPropertyListSerialization.propertyListWithData_options_format_error_(data, 0, None, None)
    value = loaded[0] if isinstance(loaded, tuple) else loaded
    return str(value.get("glyphname")) if value and value.get("glyphname") else None


def _font(path):
    from Foundation import NSURL
    from GlyphsApp import GSFont

    loaded = GSFont.alloc().initWithURL_error_(NSURL.fileURLWithPath_(str(path)), None)
    value = loaded[0] if isinstance(loaded, tuple) else loaded
    if value is None:
        raise ValueError("Glyphs could not load a comparison package")
    return value


def _layer(layer):
    master = _value(layer, "master")
    master_name = str(_value(master, "name", "") or "")
    layer_name = str(_value(layer, "name", "") or "")
    is_master = bool(_value(layer, "isMasterLayer", False))
    label = master_name if is_master and master_name else (layer_name or master_name or str(layer.layerId))
    metrics = {
        "ascender": float(_value(master, "ascender", 800) or 800),
        "capHeight": float(_value(master, "capHeight", 700) or 700),
        "xHeight": float(_value(master, "xHeight", 500) or 500),
        "descender": float(_value(master, "descender", -200) or -200),
    }
    anchors = {}
    for anchor in layer.anchors:
        anchors[str(anchor.name)] = [float(anchor.position.x), float(anchor.position.y)]
    context = "layer {!r}".format(label)
    outline_values = resolved_closed_layer_elements(layer, context=context)
    warnings = []
    try:
        open_values = resolved_open_layer_elements(layer, context=context)
    except ValueError as error:
        open_values = []
        warnings.append({"scope": "openPaths", "message": str(error)})
    outline = _elements(outline_values)
    open_outline = _elements(open_values)
    component_outlines, component_warnings = _component_outlines(layer)
    warnings.extend(component_warnings)
    bounds = _value(layer, "bounds")
    try:
        serialized_bounds = [float(bounds.origin.x), float(bounds.origin.y),
                             float(bounds.size.width), float(bounds.size.height)]
    except Exception:
        points = [
            point
            for element in outline + open_outline + [item for path in component_outlines for item in path]
            for point in element["points"]
        ]
        if points:
            xs, ys = [point[0] for point in points], [point[1] for point in points]
            serialized_bounds = [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]
        else:
            serialized_bounds = [0.0, 0.0, 0.0, 0.0]
    return {
        "id": str(layer.layerId),
        "label": label,
        "isMaster": is_master,
        "outline": outline,
        "openOutline": open_outline,
        "componentOutlines": component_outlines,
        "warnings": warnings,
        "anchors": anchors,
        "width": float(layer.width),
        "metrics": metrics,
        "bounds": serialized_bounds,
    }


def _snapshot(package_path, glyph_file):
    if not package_path or not glyph_file or not Path(package_path).exists() or not Path(glyph_file).is_file():
        return {"missingGlyph": True, "glyphName": None, "layers": []}
    name = _glyph_name(Path(glyph_file))
    if not name:
        raise ValueError("The selected .glyph file has no glyph name")
    font = _font(Path(package_path))
    glyph = font.glyphs[name]
    if glyph is None:
        return {"missingGlyph": True, "glyphName": name, "layers": []}
    return {"missingGlyph": False, "glyphName": name, "layers": [_layer(layer) for layer in glyph.layers]}


def _difference_elements(values):
    return [{"kind": int(value[0]), "points": value[1]} for value in values]


def _difference(layer_id, label, before, after):
    empty = {"outline": [], "openOutline": [], "anchors": {}, "width": None}
    plan = comparison(before or empty, after or empty)
    return {
        "id": layer_id,
        "label": label,
        "outlineChanged": plan["outlineChanged"],
        "referenceOutline": _difference_elements(plan["referenceOutline"]),
        "currentOutline": _difference_elements(plan["currentOutline"]),
        "referenceSegments": _difference_elements(plan["referenceSegments"]),
        "currentSegments": _difference_elements(plan["currentSegments"]),
        "anchors": plan["anchors"],
        "width": plan["width"],
        "metricRange": plan["metricRange"],
        "regions": plan["regions"],
        "hasVisibleDifference": plan["hasVisibleDifference"],
    }


def run(payload):
    before = _snapshot(payload.get("beforePackage"), payload.get("beforeGlyph"))
    after = _snapshot(payload.get("afterPackage"), payload.get("afterGlyph"))
    unused_before = list(before["layers"])
    differences = []
    for layer in after["layers"]:
        match = next((value for value in unused_before if value["id"] == layer["id"]), None)
        if match is None:
            match = next((value for value in unused_before if value["label"] == layer["label"]), None)
        if match is not None:
            unused_before.remove(match)
        differences.append(_difference(layer["id"], layer["label"], match, layer))
    for layer in unused_before:
        differences.append(_difference(layer["id"], layer["label"], layer, None))
    changed = [value["id"] for value in differences if value["hasVisibleDifference"]]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "protocolAPIVersion": PROTOCOL_API_VERSION,
        "before": before,
        "after": after,
        "changedLayerIDs": changed,
        "differences": differences,
    }


def main():
    request_path = Path(sys.argv[-1])
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    try:
        result = {"ok": True, "data": run(payload)}
    except Exception as error:
        detail = str(error) or type(error).__name__
        result = {"ok": False, "error": (
            "Visual preview failed while reading Glyphs geometry ({}): {}. "
            "The Text diff remains available."
        ).format(type(error).__name__, detail)}
    Path(payload["output"]).write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    main()
