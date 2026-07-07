# encoding: utf-8

from __future__ import division, print_function, unicode_literals

"""Visual review image generation for Glyphs MCP.

The tool in this module is intentionally read-only. It renders existing Glyphs
layers to an offscreen PNG so an MCP client can pass the visual proof to a
vision-capable model.
"""

import base64
import json
import math

from GlyphsApp import Glyphs  # type: ignore[import-not-found]

try:
    from fastmcp.utilities.types import Image  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - FastMCP is available in the plugin runtime
    try:
        from fastmcp import Image  # type: ignore[import-not-found]
    except Exception:  # pragma: no cover - unit tests can run without FastMCP
        Image = None

try:
    import objc  # type: ignore[import-not-found]
    from Foundation import (  # type: ignore[import-not-found]
        NSObject,
        NSThread,
        NSAffineTransform,
        NSMakePoint,
        NSMakeRect,
        NSMakeSize,
        NSString,
    )
    from AppKit import (  # type: ignore[import-not-found]
        NSBezierPath,
        NSBitmapImageRep,
        NSColor,
        NSFont,
        NSFontAttributeName,
        NSForegroundColorAttributeName,
        NSGraphicsContext,
        NSImage,
    )
    try:
        from AppKit import NSBitmapImageFileTypePNG as _PNG_FILE_TYPE  # type: ignore[import-not-found]
    except Exception:  # pragma: no cover - older PyObjC name
        from AppKit import NSPNGFileType as _PNG_FILE_TYPE  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - unit tests run without AppKit/Glyphs
    objc = None
    NSObject = None
    NSThread = None
    NSAffineTransform = None
    NSMakePoint = None
    NSMakeRect = None
    NSMakeSize = None
    NSString = None
    NSBezierPath = None
    NSBitmapImageRep = None
    NSColor = None
    NSFont = None
    NSFontAttributeName = "NSFont"
    NSForegroundColorAttributeName = "NSForegroundColor"
    NSGraphicsContext = None
    NSImage = None
    _PNG_FILE_TYPE = 4

from mcp_runtime import mcp
from mcp_tool_helpers import (
    _font_resolution_error,
    _get_layer_id,
    _get_left_sidebearing,
    _get_right_sidebearing,
    _layer_display_name,
    _resolve_font_by_index,
    _safe_json,
)


DEFAULT_OVERLAYS = ["metrics", "sidebearings", "bounds"]
SUPPORTED_OVERLAYS = set(["metrics", "sidebearings", "bounds", "nodes", "handles", "anchors", "guides"])
_OBJC_BRIDGE_ABI = 1
_OBJC_MAIN_THREAD_HELPER_CLASS_NAME = "GlyphsMCPVisualReviewMainThreadHelperV{}".format(_OBJC_BRIDGE_ABI)
_OBJC_MAIN_THREAD_HELPER_CLASS = None


def _unique_strings(values):
    out = []
    seen = set()
    for value in list(values or []):
        if value is None:
            continue
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _normalize_glyph_names(glyph_names):
    if glyph_names is None:
        return None
    if isinstance(glyph_names, str):
        text = glyph_names.replace(",", " ")
        return _unique_strings(text.split())
    try:
        return _unique_strings(glyph_names)
    except TypeError:
        return _unique_strings([glyph_names])


def _normalize_overlays(overlays):
    if overlays is None:
        requested = list(DEFAULT_OVERLAYS)
    elif isinstance(overlays, str):
        requested = overlays.replace(",", " ").split()
    else:
        try:
            requested = list(overlays)
        except TypeError:
            requested = [overlays]

    normalized = _unique_strings([str(o).strip().lower() for o in requested])
    invalid = [o for o in normalized if o not in SUPPORTED_OVERLAYS]
    return normalized, invalid


def _selected_glyph_names_for_font(font):
    names = []
    try:
        selected_layers = list(getattr(font, "selectedLayers", []) or [])
    except Exception:
        selected_layers = []

    for layer in selected_layers:
        try:
            glyph = getattr(layer, "parent", None)
            name = getattr(glyph, "name", None)
            if name:
                names.append(name)
        except Exception:
            continue
    return _unique_strings(names)


def _get_master(font, master_id):
    masters = list(getattr(font, "masters", []) or [])
    if master_id:
        wanted = str(master_id)
        for master in masters:
            if str(getattr(master, "id", "")) == wanted:
                return master
        return None

    selected = getattr(font, "selectedFontMaster", None)
    if selected is not None:
        return selected
    if masters:
        return masters[0]
    return None


def _glyph_for_name(font, glyph_name):
    try:
        return font.glyphs[glyph_name]
    except Exception:
        return None


def _layer_for_glyph(glyph, master):
    if glyph is None or master is None:
        return None
    master_id = getattr(master, "id", None)
    if not master_id:
        return None
    try:
        return glyph.layers[master_id]
    except Exception:
        return None


def _coerce_float(value, default=None):
    if value is None:
        return default
    try:
        if callable(value):
            value = value()
    except Exception:
        return default
    try:
        return float(value)
    except Exception:
        return default


def _coerce_bool(value, default=False):
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in set(["0", "false", "no", "off", ""])
    return bool(value)


def _rect_dict(rect):
    if rect is None:
        return None
    try:
        origin = getattr(rect, "origin", None)
        size = getattr(rect, "size", None)
        x = _coerce_float(getattr(origin, "x", None), None)
        y = _coerce_float(getattr(origin, "y", None), None)
        w = _coerce_float(getattr(size, "width", None), None)
        h = _coerce_float(getattr(size, "height", None), None)
        if x is None or y is None or w is None or h is None:
            return None
        return {"x": x, "y": y, "width": w, "height": h, "minX": x, "maxX": x + w, "minY": y, "maxY": y + h}
    except Exception:
        return None


def _layer_bounds(layer):
    bounds = _rect_dict(getattr(layer, "bounds", None))
    if bounds is None:
        return None
    if abs(bounds.get("width", 0.0)) < 1e-6 and abs(bounds.get("height", 0.0)) < 1e-6:
        return None
    return bounds


def _master_metrics(master):
    ascender = _coerce_float(getattr(master, "ascender", None), None)
    descender = _coerce_float(getattr(master, "descender", None), None)
    x_height = _coerce_float(getattr(master, "xHeight", None), None)
    cap_height = _coerce_float(getattr(master, "capHeight", None), None)

    if ascender is None:
        ascender = 800.0
    if descender is None:
        descender = -200.0
    if x_height is None:
        x_height = ascender * 0.5
    if cap_height is None:
        cap_height = ascender * 0.875

    return {
        "ascender": ascender,
        "descender": descender,
        "xHeight": x_height,
        "capHeight": cap_height,
        "baseline": 0.0,
    }


def _lookup_objc_class(name):
    if objc is None:
        return None
    try:
        return objc.lookUpClass(name)
    except Exception:
        return None


def _validate_objc_helper_class(helper_class, class_name, required_methods):
    missing = [method_name for method_name in required_methods if not hasattr(helper_class, method_name)]
    if missing:
        raise RuntimeError(
            "Objective-C helper class '{}' is incompatible with this Glyphs MCP build "
            "(missing: {}). Restart Glyphs or bump _OBJC_BRIDGE_ABI when changing helper interfaces.".format(
                class_name, ", ".join(missing)
            )
        )
    return helper_class


def _get_or_create_objc_helper_class(cache_attr, class_name, required_methods, builder):
    helper_class = globals().get(cache_attr)
    if helper_class is not None:
        return _validate_objc_helper_class(helper_class, class_name, required_methods)

    existing = _lookup_objc_class(class_name)
    if existing is not None:
        helper_class = _validate_objc_helper_class(existing, class_name, required_methods)
        globals()[cache_attr] = helper_class
        return helper_class

    helper_class = _validate_objc_helper_class(builder(class_name), class_name, required_methods)
    globals()[cache_attr] = helper_class
    return helper_class


def _build_main_thread_helper_class(class_name):
    def initWithCallable_(self, fn):
        self = objc.super(type(self), self).init()
        if self is None:
            return None
        self._fn = fn
        self.result = None
        self.error = None
        return self

    def run_(self, _obj):
        try:
            self.result = self._fn()
        except Exception as exc:  # pragma: no cover - bubbled to caller
            self.error = exc

    return type(
        class_name,
        (NSObject,),
        {
            "__module__": __name__,
            "initWithCallable_": initWithCallable_,
            "run_": run_,
        },
    )


def _get_main_thread_helper_class():
    return _get_or_create_objc_helper_class(
        cache_attr="_OBJC_MAIN_THREAD_HELPER_CLASS",
        class_name=_OBJC_MAIN_THREAD_HELPER_CLASS_NAME,
        required_methods=("initWithCallable_", "run_"),
        builder=_build_main_thread_helper_class,
    )


def _prepare_render_request(font_index, glyph_names, master_id, columns, image_width, include_components, overlays):
    try:
        font_index_i = int(font_index or 0)
    except Exception:
        return {"ok": False, "error": "Invalid font_index: {}".format(font_index)}

    font, fonts = _resolve_font_by_index(Glyphs, font_index_i)
    if not font:
        return _font_resolution_error(font_index_i, fonts, ok_key="ok")

    normalized_overlays, invalid = _normalize_overlays(overlays)
    if invalid:
        return {
            "ok": False,
            "error": "Unsupported overlay(s): {}".format(", ".join(invalid)),
            "supportedOverlays": sorted(SUPPORTED_OVERLAYS),
        }

    try:
        columns_i = int(columns or 4)
    except Exception:
        columns_i = 4
    if columns_i < 1:
        columns_i = 1
    if columns_i > 12:
        columns_i = 12

    try:
        image_width_i = int(image_width or 1600)
    except Exception:
        image_width_i = 1600
    if image_width_i < 320:
        image_width_i = 320
    if image_width_i > 4096:
        image_width_i = 4096

    master = _get_master(font, master_id)
    if master is None:
        return {"ok": False, "error": "No matching master found", "masterId": master_id}

    names = _normalize_glyph_names(glyph_names)
    if names is None:
        names = _selected_glyph_names_for_font(font)
    if not names:
        return {"ok": False, "error": "No glyph_names provided and no selected glyphs found."}

    render_items = []
    warnings = []
    for name in names:
        glyph = _glyph_for_name(font, name)
        if glyph is None:
            warnings.append("Glyph '{}' not found; skipped.".format(name))
            continue
        layer = _layer_for_glyph(glyph, master)
        if layer is None:
            warnings.append("Glyph '{}' has no layer for master {}; skipped.".format(name, getattr(master, "id", None)))
            continue

        bounds = _layer_bounds(layer)
        width = _coerce_float(getattr(layer, "width", None), 0.0) or 0.0
        layer_name = _layer_display_name(font, layer, getattr(master, "id", None))
        render_items.append(
            {
                "glyph": glyph,
                "glyphName": str(getattr(glyph, "name", name)),
                "layer": layer,
                "layerId": _get_layer_id(layer),
                "layerName": layer_name,
                "width": width,
                "leftSideBearing": _get_left_sidebearing(layer),
                "rightSideBearing": _get_right_sidebearing(layer),
                "bounds": bounds,
            }
        )

    if not render_items:
        return {"ok": False, "error": "No renderable glyph layers found.", "warnings": warnings}

    return {
        "ok": True,
        "font": font,
        "fontIndex": font_index_i,
        "familyName": getattr(font, "familyName", None),
        "master": master,
        "masterId": getattr(master, "id", None),
        "masterName": getattr(master, "name", None),
        "glyphNames": [item["glyphName"] for item in render_items],
        "renderItems": render_items,
        "columns": columns_i,
        "imageWidth": image_width_i,
        "includeComponents": _coerce_bool(include_components, True),
        "overlays": normalized_overlays,
        "warnings": warnings,
    }


def _run_on_main_thread(fn):
    if NSThread is not None:
        try:
            if bool(NSThread.isMainThread()):
                return fn()
        except Exception:
            pass

    if objc is None or NSObject is None:
        return fn()

    helper_class = _get_main_thread_helper_class()
    helper = helper_class.alloc().initWithCallable_(fn)
    helper.performSelectorOnMainThread_withObject_waitUntilDone_("run:", None, True)
    if getattr(helper, "error", None) is not None:
        raise helper.error
    return getattr(helper, "result", None)


def _draw_text(text, x, y, size=13.0, color=None):
    if NSString is None or NSFont is None or NSMakePoint is None:
        return
    try:
        attrs = {
            NSFontAttributeName: NSFont.systemFontOfSize_(float(size)),
            NSForegroundColorAttributeName: color or NSColor.blackColor(),
        }
        NSString.stringWithString_(str(text)).drawAtPoint_withAttributes_(NSMakePoint(float(x), float(y)), attrs)
    except Exception:
        pass


def _stroke_line(x1, y1, x2, y2, width):
    p = NSBezierPath.bezierPath()
    p.moveToPoint_(NSMakePoint(float(x1), float(y1)))
    p.lineToPoint_(NSMakePoint(float(x2), float(y2)))
    p.setLineWidth_(float(width))
    p.stroke()


def _stroke_rect(x, y, w, h, width):
    p = NSBezierPath.bezierPathWithRect_(NSMakeRect(float(x), float(y), float(w), float(h)))
    p.setLineWidth_(float(width))
    p.stroke()


def _fill_oval(cx, cy, radius):
    p = NSBezierPath.bezierPathWithOvalInRect_(
        NSMakeRect(float(cx - radius), float(cy - radius), float(radius * 2.0), float(radius * 2.0))
    )
    p.fill()


def _node_xy(node):
    pos = getattr(node, "position", None)
    x = _coerce_float(getattr(pos, "x", None), None)
    y = _coerce_float(getattr(pos, "y", None), None)
    if x is None or y is None:
        return None
    return x, y


def _draw_nodes_and_handles(layer, overlays, scale):
    if "nodes" not in overlays and "handles" not in overlays:
        return
    radius = max(2.25 / float(scale or 1.0), 1.0)
    line_width = max(1.0 / float(scale or 1.0), 0.5)

    for path in list(getattr(layer, "paths", []) or []):
        nodes = list(getattr(path, "nodes", []) or [])
        if not nodes:
            continue

        if "handles" in overlays:
            NSColor.colorWithDeviceRed_green_blue_alpha_(0.20, 0.45, 0.95, 0.45).set()
            for i, node in enumerate(nodes):
                node_type = str(getattr(node, "type", "")).lower()
                if node_type == "offcurve" or i < 2:
                    continue
                off2 = nodes[i - 1]
                off1 = nodes[i - 2]
                if str(getattr(off1, "type", "")).lower() != "offcurve" or str(getattr(off2, "type", "")).lower() != "offcurve":
                    continue
                prev_on = None
                for j in range(i - 3, -1, -1):
                    if str(getattr(nodes[j], "type", "")).lower() != "offcurve":
                        prev_on = nodes[j]
                        break
                if prev_on is None:
                    continue
                p0 = _node_xy(prev_on)
                p1 = _node_xy(off1)
                p2 = _node_xy(off2)
                p3 = _node_xy(node)
                if p0 and p1:
                    _stroke_line(p0[0], p0[1], p1[0], p1[1], line_width)
                if p2 and p3:
                    _stroke_line(p2[0], p2[1], p3[0], p3[1], line_width)

        if "nodes" in overlays:
            for node in nodes:
                xy = _node_xy(node)
                if not xy:
                    continue
                node_type = str(getattr(node, "type", "")).lower()
                if node_type == "offcurve":
                    NSColor.colorWithDeviceRed_green_blue_alpha_(0.15, 0.42, 0.90, 0.80).set()
                else:
                    NSColor.colorWithDeviceRed_green_blue_alpha_(0.92, 0.20, 0.12, 0.90).set()
                _fill_oval(xy[0], xy[1], radius)


def _point_xy(obj):
    pos = getattr(obj, "position", None)
    if pos is not None:
        x = _coerce_float(getattr(pos, "x", None), None)
        y = _coerce_float(getattr(pos, "y", None), None)
        if x is not None and y is not None:
            return x, y
    x = _coerce_float(getattr(obj, "x", None), None)
    y = _coerce_float(getattr(obj, "y", None), None)
    if x is not None and y is not None:
        return x, y
    return None


def _draw_anchors(layer, scale):
    radius = max(4.0 / float(scale or 1.0), 1.5)
    width = max(1.1 / float(scale or 1.0), 0.5)
    NSColor.colorWithDeviceRed_green_blue_alpha_(0.0, 0.55, 0.28, 0.9).set()
    for anchor in list(getattr(layer, "anchors", []) or []):
        xy = _point_xy(anchor)
        if not xy:
            continue
        _stroke_line(xy[0] - radius, xy[1], xy[0] + radius, xy[1], width)
        _stroke_line(xy[0], xy[1] - radius, xy[0], xy[1] + radius, width)


def _draw_guides(layer, x_min, x_max, y_min, y_max, scale):
    line_width = max(1.0 / float(scale or 1.0), 0.5)
    span = max(float(x_max - x_min), float(y_max - y_min), 1.0) * 2.0
    NSColor.colorWithDeviceRed_green_blue_alpha_(0.62, 0.22, 0.82, 0.60).set()
    for guide in list(getattr(layer, "guides", []) or []):
        xy = _point_xy(guide)
        if not xy:
            continue
        angle = _coerce_float(getattr(guide, "angle", None), 0.0) or 0.0
        rad = math.radians(angle)
        dx = math.cos(rad) * span
        dy = math.sin(rad) * span
        _stroke_line(xy[0] - dx, xy[1] - dy, xy[0] + dx, xy[1] + dy, line_width)


def _draw_layer_in_cell(item, master_metrics, overlays, include_components, cell_x, cell_y, cell_w, cell_h):
    label_h = 28.0
    pad = 18.0
    width = float(item.get("width") or 0.0)
    bounds = item.get("bounds") or {}

    descender = float(master_metrics["descender"])
    ascender = float(master_metrics["ascender"])
    x_min = min(0.0, float(bounds.get("minX", 0.0)))
    x_max = max(width, float(bounds.get("maxX", width)))
    y_min = min(descender, float(bounds.get("minY", descender)))
    y_max = max(ascender, float(bounds.get("maxY", ascender)))

    if abs(x_max - x_min) < 1e-6:
        x_max = x_min + max(width, 500.0, 1.0)
    if abs(y_max - y_min) < 1e-6:
        y_max = y_min + 1000.0

    draw_w = max(float(cell_w) - pad * 2.0, 1.0)
    draw_h = max(float(cell_h) - label_h - pad * 2.0, 1.0)
    scale = min(draw_w / (x_max - x_min), draw_h / (y_max - y_min))
    if not math.isfinite(scale) or scale <= 0:
        scale = 1.0

    _draw_text(item.get("glyphName", ""), cell_x + pad, cell_y + cell_h - 21.0, 13.0)

    context = NSGraphicsContext.currentContext()
    context.saveGraphicsState()
    try:
        transform = NSAffineTransform.transform()
        transform.translateXBy_yBy_(float(cell_x + pad - x_min * scale), float(cell_y + pad - y_min * scale))
        transform.scaleXBy_yBy_(float(scale), float(scale))
        transform.concat()

        line_w = max(1.0 / scale, 0.5)

        if "metrics" in overlays:
            metric_lines = [
                ("baseline", master_metrics["baseline"], (0.92, 0.18, 0.15, 0.65)),
                ("xHeight", master_metrics["xHeight"], (0.95, 0.58, 0.12, 0.55)),
                ("capHeight", master_metrics["capHeight"], (0.95, 0.58, 0.12, 0.55)),
                ("ascender", master_metrics["ascender"], (0.55, 0.55, 0.55, 0.50)),
                ("descender", master_metrics["descender"], (0.55, 0.55, 0.55, 0.50)),
            ]
            for _name, y, rgba in metric_lines:
                NSColor.colorWithDeviceRed_green_blue_alpha_(*rgba).set()
                _stroke_line(x_min, y, x_max, y, line_w)

        if "sidebearings" in overlays:
            NSColor.colorWithDeviceRed_green_blue_alpha_(0.08, 0.48, 0.80, 0.55).set()
            _stroke_line(0.0, y_min, 0.0, y_max, line_w)
            _stroke_line(width, y_min, width, y_max, line_w)

        if "bounds" in overlays and item.get("bounds"):
            b = item["bounds"]
            NSColor.colorWithDeviceRed_green_blue_alpha_(0.32, 0.32, 0.32, 0.50).set()
            _stroke_rect(b["minX"], b["minY"], b["width"], b["height"], line_w)

        layer = item["layer"]
        path = None
        if include_components:
            path = getattr(layer, "completeBezierPath", None)
        if path is None:
            path = getattr(layer, "bezierPath", None)
        if path is not None:
            NSColor.blackColor().set()
            path.fill()

        _draw_nodes_and_handles(layer, overlays, scale)
        if "anchors" in overlays:
            _draw_anchors(layer, scale)
        if "guides" in overlays:
            _draw_guides(layer, x_min, x_max, y_min, y_max, scale)
    finally:
        context.restoreGraphicsState()


def _render_contact_sheet_png(render_items, master, columns, image_width, include_components, overlays):
    if NSImage is None or NSBitmapImageRep is None or NSGraphicsContext is None:
        raise RuntimeError("AppKit drawing APIs are unavailable in this runtime.")

    count = len(render_items)
    columns = max(1, int(columns or 1))
    columns = min(columns, count)
    rows = int(math.ceil(count / float(columns)))

    margin = 32.0
    gap = 24.0
    cell_w = (float(image_width) - margin * 2.0 - gap * float(columns - 1)) / float(columns)
    cell_w = max(cell_w, 120.0)
    cell_h = cell_w * 1.12
    image_h = int(math.ceil(margin * 2.0 + cell_h * rows + gap * max(rows - 1, 0)))

    image = NSImage.alloc().initWithSize_(NSMakeSize(float(image_width), float(image_h)))
    image.lockFocus()
    try:
        NSColor.whiteColor().set()
        NSBezierPath.bezierPathWithRect_(NSMakeRect(0.0, 0.0, float(image_width), float(image_h))).fill()

        master_metrics = _master_metrics(master)
        for index, item in enumerate(render_items):
            row = index // columns
            col = index % columns
            x = margin + col * (cell_w + gap)
            y = float(image_h) - margin - float(row + 1) * cell_h - float(row) * gap

            NSColor.colorWithDeviceWhite_alpha_(0.94, 1.0).set()
            NSBezierPath.bezierPathWithRect_(NSMakeRect(x, y, cell_w, cell_h)).fill()
            NSColor.colorWithDeviceWhite_alpha_(0.82, 1.0).set()
            border = NSBezierPath.bezierPathWithRect_(NSMakeRect(x, y, cell_w, cell_h))
            border.setLineWidth_(1.0)
            border.stroke()

            _draw_layer_in_cell(item, master_metrics, overlays, include_components, x, y, cell_w, cell_h)
    finally:
        image.unlockFocus()

    tiff = image.TIFFRepresentation()
    rep = NSBitmapImageRep.imageRepWithData_(tiff)
    data = rep.representationUsingType_properties_(_PNG_FILE_TYPE, {})
    return bytes(data), {"imageWidth": int(image_width), "imageHeight": int(image_h), "rowCount": rows, "columnCount": columns}


@mcp.tool()
async def render_glyph_review_image(
    font_index: int = 0,
    glyph_names: list = None,
    master_id: str = None,
    columns: int = 4,
    image_width: int = 1600,
    include_components: bool = True,
    overlays: list = None,
    include_base64: bool = False,
):
    """Render selected or named Glyphs layers to a PNG visual review image.

    This tool is read-only. It does not write guides, edit glyphs, create files,
    or save the font.

    Args:
        font_index: Index of the open font.
        glyph_names: Optional list of glyph names. If omitted, uses selected glyphs.
        master_id: Optional master ID. If omitted, uses the selected master.
        columns: Number of contact-sheet columns.
        image_width: PNG width in pixels, clamped to a safe range.
        include_components: Use ``layer.completeBezierPath`` when true.
        overlays: Any of metrics, sidebearings, bounds, nodes, handles, anchors, guides.
        include_base64: Include a data URI fallback in the JSON metadata.

    Returns:
        A list containing JSON metadata text and, on success, MCP image content.
    """
    try:
        request = _prepare_render_request(
            font_index=font_index,
            glyph_names=glyph_names,
            master_id=master_id,
            columns=columns,
            image_width=image_width,
            include_components=include_components,
            overlays=overlays,
        )
        if not request.get("ok"):
            return [_safe_json(request)]

        png_bytes, image_info = _run_on_main_thread(
            lambda: _render_contact_sheet_png(
                request["renderItems"],
                request["master"],
                request["columns"],
                request["imageWidth"],
                request["includeComponents"],
                request["overlays"],
            )
        )

        glyphs_meta = []
        for item in request["renderItems"]:
            glyphs_meta.append(
                {
                    "glyphName": item.get("glyphName"),
                    "layerId": item.get("layerId"),
                    "layerName": item.get("layerName"),
                    "width": item.get("width"),
                    "leftSideBearing": item.get("leftSideBearing"),
                    "rightSideBearing": item.get("rightSideBearing"),
                    "bounds": item.get("bounds"),
                }
            )

        metadata = {
            "ok": True,
            "fontIndex": request["fontIndex"],
            "familyName": request.get("familyName"),
            "masterId": request.get("masterId"),
            "masterName": request.get("masterName"),
            "glyphNames": request.get("glyphNames"),
            "glyphs": glyphs_meta,
            "overlays": request.get("overlays"),
            "includeComponents": request.get("includeComponents"),
            "image": {
                "mimeType": "image/png",
                "width": image_info.get("imageWidth"),
                "height": image_info.get("imageHeight"),
                "columns": image_info.get("columnCount"),
                "rows": image_info.get("rowCount"),
                "byteLength": len(png_bytes),
            },
            "warnings": request.get("warnings") or [],
            "notes": [
                "Read-only render; no guides, glyph data, files, or font state were changed.",
                "This visual proof is intended for review assistance, not final typographic approval.",
            ],
        }

        if include_base64 or Image is None:
            metadata["dataUri"] = "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")

        metadata_text = _safe_json(metadata)

        if Image is None:
            metadata["warnings"].append("FastMCP Image helper unavailable; returned dataUri only.")
            return [_safe_json(metadata)]

        return [metadata_text, Image(data=png_bytes, format="png")]
    except Exception as exc:
        return [_safe_json({"ok": False, "error": str(exc), "errorType": type(exc).__name__})]
