# encoding: utf-8

from __future__ import division, print_function, unicode_literals

"""HTTP bridge routes for clickable Glyphs show links.

Some LLM clients render Markdown links only for http(s) URLs. The MCP tools
still expose the native glyphsapp:// URL in showUrl, while showMarkdown points
to this local bridge route so the client can render it as a clickable link.
"""

import html
from urllib.parse import urlencode

from starlette.responses import HTMLResponse, PlainTextResponse

from mcp_runtime import mcp

try:
    from AppKit import NSWorkspace  # type: ignore[import-not-found]
    from Foundation import NSURL  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - only available inside Glyphs/macOS
    NSWorkspace = None
    NSURL = None

try:
    from GlyphsApp import Glyphs  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - only available inside Glyphs
    Glyphs = None

from mcp_tool_helpers import _open_fonts_from_glyphs, _open_tab_on_main_thread


_ALLOWED_SHOW_QUERY_KEYS = set(["path", "glyph", "production", "layer"])


def _query_items(query_params):
    try:
        return list(query_params.multi_items())
    except Exception:
        return list(query_params.items())


def _glyphs_show_target_from_request(request):
    params = []
    has_path = False
    has_target = False

    for key, value in _query_items(request.query_params):
        key = str(key)
        if key not in _ALLOWED_SHOW_QUERY_KEYS:
            continue
        if value is None:
            continue
        value = str(value).strip()
        if not value:
            continue
        if key == "path":
            has_path = True
        elif key in ("glyph", "production"):
            has_target = True
        params.append((key, value))

    if not has_path:
        return None, "Missing required path query parameter."
    if not has_target:
        return None, "Missing glyph or production query parameter."

    return "glyphsapp://show/?{}".format(urlencode(params)), None


def _show_request_parts(request):
    path = None
    glyph_names = []
    production_names = []
    layer_ids = []

    for key, value in _query_items(request.query_params):
        key = str(key)
        if key not in _ALLOWED_SHOW_QUERY_KEYS or value is None:
            continue
        value = str(value).strip()
        if not value:
            continue
        if key == "path" and path is None:
            path = value
        elif key == "glyph":
            glyph_names.append(value)
        elif key == "production":
            production_names.append(value)
        elif key == "layer":
            layer_ids.append(value)

    return path, glyph_names, production_names, layer_ids


def _font_for_path(path):
    if Glyphs is None or not path:
        return None
    try:
        wanted = str(path)
        for font in _open_fonts_from_glyphs(Glyphs):
            if str(getattr(font, "filepath", "") or "") == wanted:
                return font
    except Exception:
        return None
    return None


def _glyph_for_name_or_production(font, name):
    if not font or not name:
        return None

    try:
        glyph = font.glyphs[name]
        if glyph is not None:
            return glyph
    except Exception:
        pass

    try:
        for glyph in list(font.glyphs or []):
            if str(getattr(glyph, "productionName", "") or "") == name:
                return glyph
    except Exception:
        pass

    return None


def _layer_for_glyph(font, glyph, layer_ids):
    if glyph is None:
        return None

    for layer_id in layer_ids or []:
        try:
            layer = glyph.layers[layer_id]
            if layer is not None:
                return layer
        except Exception:
            pass

    try:
        master = getattr(font, "selectedFontMaster", None)
        master_id = getattr(master, "id", None)
        if master_id:
            layer = glyph.layers[master_id]
            if layer is not None:
                return layer
    except Exception:
        pass

    try:
        return glyph.layers[0]
    except Exception:
        return None


def _open_glyphs_in_current_document(request):
    path, glyph_names, production_names, layer_ids = _show_request_parts(request)
    font = _font_for_path(path)
    if font is None:
        return False, "No open font matched the requested path."

    layers = []
    missing = []

    for name in glyph_names:
        glyph = _glyph_for_name_or_production(font, name)
        layer = _layer_for_glyph(font, glyph, layer_ids)
        if layer is None:
            missing.append(name)
            continue
        layers.append(layer)

    for name in production_names:
        glyph = _glyph_for_name_or_production(font, name)
        layer = _layer_for_glyph(font, glyph, layer_ids)
        if layer is None:
            missing.append(name)
            continue
        layers.append(layer)

    if not layers:
        if missing:
            return False, "No requested glyphs were found: {}".format(", ".join(missing))
        return False, "No glyphs were requested."

    try:
        _open_tab_on_main_thread(font, layers)
        if missing:
            return True, "Opened tab, but skipped missing glyphs: {}".format(", ".join(missing))
        return True, None
    except Exception as e:
        return False, "Failed to open Glyphs tab: {}".format(e)


def _open_native_glyphs_url(target):
    if NSWorkspace is None or NSURL is None:
        return False, "NSWorkspace is unavailable in this runtime."

    try:
        url = NSURL.URLWithString_(target)
        if url is None:
            return False, "Could not build native Glyphs URL."
        ok = bool(NSWorkspace.sharedWorkspace().openURL_(url))
        if not ok:
            return False, "macOS declined to open the native Glyphs URL."
        return True, None
    except Exception as e:
        return False, str(e)


@mcp.custom_route("/glyphs-show/", methods=["GET"], include_in_schema=False)
async def glyphs_show_bridge(request):
    target, error = _glyphs_show_target_from_request(request)
    if error:
        return PlainTextResponse(error, status_code=400)

    opened, open_error = _open_glyphs_in_current_document(request)
    native_opened = False
    if not opened:
        native_opened, native_error = _open_native_glyphs_url(target)
        if native_opened:
            open_error = "The in-document tab fallback failed: {}; used native URL instead.".format(open_error)
        elif native_error:
            open_error = "{} Native URL fallback also failed: {}".format(open_error, native_error)

    escaped = html.escape(target, quote=True)
    if opened:
        heading = "Opening in Glyphs"
        message = "A new Glyphs Edit tab was opened for the requested glyph."
    elif native_opened:
        heading = "Opening in Glyphs"
        message = html.escape(open_error or "The native Glyphs URL was opened.", quote=True)
    else:
        heading = "Open in Glyphs"
        message = "The automatic open request failed: {}. Click the button below or copy the URL into Safari.".format(
            html.escape(open_error or "unknown error", quote=True)
        )

    body = """<!doctype html>
<meta charset="utf-8">
<title>{heading}</title>
<style>
body {{
  color: #202124;
  font: 16px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  margin: 48px;
}}
a.button {{
  background: #0b57d0;
  border-radius: 6px;
  color: white;
  display: inline-block;
  font-weight: 600;
  margin: 12px 0;
  padding: 10px 14px;
  text-decoration: none;
}}
code {{
  background: #f1f3f4;
  border-radius: 4px;
  display: block;
  margin-top: 16px;
  max-width: 960px;
  overflow-wrap: anywhere;
  padding: 12px;
  white-space: normal;
}}
</style>
<h1>{heading}</h1>
<p>{message}</p>
<p><a class="button" href="{url}">Open in Glyphs</a></p>
<p>If your browser blocks app links, copy this URL into Safari or Chrome:</p>
<code>{url}</code>
""".format(heading=heading, message=message, url=escaped)
    return HTMLResponse(body)
