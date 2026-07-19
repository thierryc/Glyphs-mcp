# encoding: utf-8

from __future__ import division, print_function, unicode_literals

"""Shared helpers for Glyphs MCP tools.

This module intentionally does not import GlyphsApp so it can be unit-tested in
normal Python environments.
"""

import json
import math
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

try:
    import objc  # type: ignore[import-not-found]
    from Foundation import NSObject, NSThread  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - PyObjC should be available inside Glyphs
    objc = None
    NSObject = None
    NSThread = None

_OBJC_BRIDGE_ABI = 1
_OBJC_MAIN_THREAD_HELPER_CLASS_NAME = "GlyphsMCPToolHelpersMainThreadHelperV{}".format(_OBJC_BRIDGE_ABI)
_OBJC_MAIN_THREAD_HELPER_CLASS = None


def _custom_parameter(obj, key, default=None):
    """Safely read a value from Glyphs' CustomParametersProxy.

    The proxy does not implement dict.get(). Iterate entries and match by name.
    """
    try:
        cp = getattr(obj, "customParameters", None)
        if cp is None:
            return default
        for item in cp:
            if getattr(item, "name", None) == key:
                return getattr(item, "value", default)
    except Exception:
        pass
    return default


def _sanitize_for_json(value):
    """Convert Glyphs/PyObjC objects to JSON-serializable primitives."""
    if value is None:
        return None

    if isinstance(value, (bool, int, float, str)):
        return value

    if isinstance(value, (list, tuple, set)):
        return [_sanitize_for_json(v) for v in value]

    if isinstance(value, dict):
        return {str(k): _sanitize_for_json(v) for k, v in value.items()}

    try:
        return float(value)
    except (TypeError, ValueError):
        pass

    try:
        return str(value)
    except Exception:
        return None


def _safe_json(data):
    return json.dumps(_sanitize_for_json(data))


def _maybe_call(value):
    try:
        if callable(value):
            return value()
    except Exception:
        return None
    return value


def _sequence_values(sequence):
    if sequence is None:
        return []

    values = []
    try:
        count = len(sequence)
    except Exception:
        count = None

    if count is not None:
        for index in range(count):
            try:
                values.append(sequence[index])
            except Exception:
                pass
        return values

    try:
        return list(sequence)
    except Exception:
        return []


def _font_identity(font):
    if font is None:
        return None
    try:
        path = str(getattr(font, "filepath", None) or "")
    except Exception:
        path = ""
    if path:
        return ("path", path)
    return ("object", id(font))


def _add_open_font(fonts, seen, font):
    if font is None:
        return
    key = _font_identity(font)
    if key is None or key in seen:
        return
    seen.add(key)
    fonts.append(font)


def _open_documents_from_appkit():
    """Return open GSDocument objects through Cocoa when Glyphs proxies fail."""
    try:
        from AppKit import NSDocumentController  # type: ignore[import-not-found]
    except Exception:
        return []

    try:
        controller = NSDocumentController.sharedDocumentController()
    except Exception:
        return []

    try:
        return _sequence_values(_maybe_call(getattr(controller, "documents", None)))
    except Exception:
        return []


def _active_font(Glyphs):
    try:
        return getattr(Glyphs, "font", None)
    except Exception:
        return None


def _is_active_font(Glyphs, font):
    active = _active_font(Glyphs)
    if active is None or font is None:
        return False
    if active is font:
        return True
    return _font_identity(active) == _font_identity(font)


def _open_fonts_from_glyphs(Glyphs):
    fonts = []
    seen = set()

    # Glyphs.fonts is public API, but some Glyphs 4 builds can expose a broken
    # private proxy before tool logic runs. Treat it as optional and fall back to
    # other documented application/document entry points.
    try:
        fonts_proxy = getattr(Glyphs, "fonts", None)
    except Exception:
        fonts_proxy = None
    for font in _sequence_values(fonts_proxy):
        _add_open_font(fonts, seen, font)

    try:
        documents = getattr(Glyphs, "documents", None)
    except Exception:
        documents = None
    for document in _sequence_values(documents):
        try:
            _add_open_font(fonts, seen, _maybe_call(getattr(document, "font", None)))
        except Exception:
            pass

    for document in _open_documents_from_appkit():
        try:
            _add_open_font(fonts, seen, _maybe_call(getattr(document, "font", None)))
        except Exception:
            pass

    try:
        current_document = getattr(Glyphs, "currentDocument", None)
    except Exception:
        current_document = None
    try:
        _add_open_font(fonts, seen, _maybe_call(getattr(current_document, "font", None)))
    except Exception:
        pass

    _add_open_font(fonts, seen, _active_font(Glyphs))
    return fonts


def _font_summary(font, font_index=None):
    if font is None:
        return None
    summary = {}
    if font_index is not None:
        summary["fontIndex"] = int(font_index)
    try:
        summary["familyName"] = getattr(font, "familyName", None) or ""
    except Exception:
        summary["familyName"] = ""
    try:
        summary["filePath"] = getattr(font, "filepath", None)
    except Exception:
        summary["filePath"] = None
    summary.update(_font_format_metadata(font))
    return summary


def _font_format_metadata(font):
    """Return additive, JSON-safe Glyphs source-format metadata."""
    format_version = None
    last_saved_app_version = None
    try:
        format_version = _maybe_call(getattr(font, "formatVersion", None))
        if format_version is not None:
            format_version = int(format_version)
    except Exception:
        format_version = None
    try:
        last_saved_app_version = _maybe_call(getattr(font, "appVersion", None))
        if last_saved_app_version is not None:
            last_saved_app_version = str(last_saved_app_version)
    except Exception:
        last_saved_app_version = None
    return {
        "formatVersion": format_version,
        "lastSavedAppVersion": last_saved_app_version,
    }


def _resolve_font_by_index(Glyphs, font_index):
    try:
        index = int(font_index)
    except Exception:
        index = -1

    fonts = _open_fonts_from_glyphs(Glyphs)
    if index < 0 or index >= len(fonts):
        return None, fonts
    return fonts[index], fonts


def _font_resolution_error(font_index, fonts=None, *, prefix=None, ok_key=None):
    fonts = list(fonts or [])
    try:
        index = int(font_index)
    except Exception:
        index = font_index

    if not fonts:
        message = "No open fonts found. Open a font in Glyphs and run list_open_fonts to choose a font_index."
    else:
        message = "Font index {} out of range. Available fonts: {}".format(index, len(fonts))
    if prefix:
        message = "{}: {}".format(prefix, message)

    payload = {
        "error": message,
        "fontIndex": index,
        "availableFontCount": len(fonts),
        "availableFonts": [_font_summary(font, i) for i, font in enumerate(fonts)],
    }
    if ok_key == "ok":
        payload["ok"] = False
    elif ok_key == "success":
        payload["success"] = False
    return payload


def _font_context_source():
    """Return standalone source used by code execution snippets/wrappers."""
    return "\n".join(
        [
            "def __glyphs_mcp_maybe_call(value):",
            "    try:",
            "        if callable(value):",
            "            return value()",
            "    except Exception:",
            "        return None",
            "    return value",
            "",
            "def __glyphs_mcp_sequence_values(sequence):",
            "    if sequence is None:",
            "        return []",
            "    values = []",
            "    try:",
            "        count = len(sequence)",
            "    except Exception:",
            "        count = None",
            "    if count is not None:",
            "        for index in range(count):",
            "            try:",
            "                values.append(sequence[index])",
            "            except Exception:",
            "                pass",
            "        return values",
            "    try:",
            "        return list(sequence)",
            "    except Exception:",
            "        return []",
            "",
            "def __glyphs_mcp_font_identity(font):",
            "    if font is None:",
            "        return None",
            "    try:",
            "        path = str(getattr(font, 'filepath', None) or '')",
            "    except Exception:",
            "        path = ''",
            "    if path:",
            "        return ('path', path)",
            "    return ('object', id(font))",
            "",
            "def __glyphs_mcp_add_font(fonts, seen, font):",
            "    if font is None:",
            "        return",
            "    key = __glyphs_mcp_font_identity(font)",
            "    if key is None or key in seen:",
            "        return",
            "    seen.add(key)",
            "    fonts.append(font)",
            "",
            "def __glyphs_mcp_appkit_documents():",
            "    try:",
            "        from AppKit import NSDocumentController",
            "    except Exception:",
            "        return []",
            "    try:",
            "        controller = NSDocumentController.sharedDocumentController()",
            "    except Exception:",
            "        return []",
            "    try:",
            "        return __glyphs_mcp_sequence_values(__glyphs_mcp_maybe_call(getattr(controller, 'documents', None)))",
            "    except Exception:",
            "        return []",
            "",
            "def __glyphs_mcp_open_fonts(Glyphs):",
            "    fonts = []",
            "    seen = set()",
            "    try:",
            "        fonts_proxy = getattr(Glyphs, 'fonts', None)",
            "    except Exception:",
            "        fonts_proxy = None",
            "    for font in __glyphs_mcp_sequence_values(fonts_proxy):",
            "        __glyphs_mcp_add_font(fonts, seen, font)",
            "    try:",
            "        documents = getattr(Glyphs, 'documents', None)",
            "    except Exception:",
            "        documents = None",
            "    for document in __glyphs_mcp_sequence_values(documents):",
            "        try:",
            "            __glyphs_mcp_add_font(fonts, seen, __glyphs_mcp_maybe_call(getattr(document, 'font', None)))",
            "        except Exception:",
            "            pass",
            "    for document in __glyphs_mcp_appkit_documents():",
            "        try:",
            "            __glyphs_mcp_add_font(fonts, seen, __glyphs_mcp_maybe_call(getattr(document, 'font', None)))",
            "        except Exception:",
            "            pass",
            "    try:",
            "        current_document = getattr(Glyphs, 'currentDocument', None)",
            "    except Exception:",
            "        current_document = None",
            "    try:",
            "        __glyphs_mcp_add_font(fonts, seen, __glyphs_mcp_maybe_call(getattr(current_document, 'font', None)))",
            "    except Exception:",
            "        pass",
            "    try:",
            "        __glyphs_mcp_add_font(fonts, seen, getattr(Glyphs, 'font', None))",
            "    except Exception:",
            "        pass",
            "    return fonts",
            "",
            "def __glyphs_mcp_font_by_index(Glyphs, font_index):",
            "    try:",
            "        index = int(font_index)",
            "    except Exception:",
            "        index = -1",
            "    fonts = __glyphs_mcp_open_fonts(Glyphs)",
            "    if index < 0 or index >= len(fonts):",
            "        return None",
            "    return fonts[index]",
        ]
    )


def _markdown_link_label(text):
    """Escape Markdown link label characters without changing readable text."""
    try:
        value = str(text)
    except Exception:
        value = "Open in Glyphs"
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


GLYPHS_SHOW_BRIDGE_BASE_URL = "http://127.0.0.1:9680/glyphs-show/"


def _glyphs_show_bridge_url(native_url, bridge_base_url=GLYPHS_SHOW_BRIDGE_BASE_URL):
    """Build an HTTP bridge URL for renderers that block glyphsapp:// links."""
    if not native_url:
        return None

    try:
        parts = urlsplit(str(native_url))
    except Exception:
        return None

    if parts.scheme not in ("glyphsapp", "glyphsapp3") or parts.netloc != "show":
        return None

    params = parse_qsl(parts.query, keep_blank_values=False)
    if not params:
        return None

    base = str(bridge_base_url or GLYPHS_SHOW_BRIDGE_BASE_URL).rstrip("/") + "/"
    return "{}?{}".format(base, urlencode(params))


def _glyphs_show_url(file_path, glyph_name=None, production_name=None, layer_ids=None, scheme="glyphsapp"):
    """Build a Glyphs URL-scheme link for showing glyphs/layers.

    Glyphs' public URL scheme supports file, glyph/production, and layer
    selection. It does not deep-link to nodes, anchors, components, or paths.
    """
    if not file_path:
        return None, "Font has not been saved; Glyphs show URLs require an absolute file path."

    path = str(file_path).strip()
    if not path:
        return None, "Font has not been saved; Glyphs show URLs require an absolute file path."

    try:
        if not Path(path).is_absolute():
            return None, "Font path is not absolute; Glyphs show URLs require an absolute file path."
    except Exception:
        return None, "Font path is not usable; Glyphs show URLs require an absolute file path."

    production = str(production_name).strip() if production_name else None
    glyph = str(glyph_name).strip() if glyph_name else None
    if not production and not glyph:
        return None, "Glyphs show URLs require a glyph or production name."

    params = [("path", path)]
    if production:
        params.append(("production", production))
    else:
        params.append(("glyph", glyph))

    if isinstance(layer_ids, (str, bytes)):
        layer_values = [layer_ids]
    else:
        layer_values = list(layer_ids or [])

    for layer_id in layer_values:
        if layer_id is None:
            continue
        layer = str(layer_id).strip()
        if layer:
            params.append(("layer", layer))

    return "{}://show/?{}".format(scheme or "glyphsapp", urlencode(params)), None


def _glyphs_show_glyphs_url(file_path, glyph_names, scheme="glyphsapp"):
    """Build a Glyphs show URL for multiple glyph names in one tab."""
    names = []
    seen = set()
    for glyph_name in list(glyph_names or []):
        if glyph_name is None:
            continue
        name = str(glyph_name).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)

    if not names:
        return None, "Glyphs show URLs require at least one glyph name."

    url, reason = _glyphs_show_url(file_path, glyph_name=names[0], scheme=scheme)
    if not url:
        return None, reason

    params = [("path", str(file_path).strip())]
    for name in names:
        params.append(("glyph", name))
    return "{}://show/?{}".format(scheme or "glyphsapp", urlencode(params)), None


def _glyphs_show_glyphs_link_fields(file_path, glyph_names, label=None):
    """Return show link fields for multiple glyphs, or an unavailable reason."""
    url, reason = _glyphs_show_glyphs_url(file_path, glyph_names)
    if not url:
        return {"showUrlUnavailableReason": reason}
    link_label = label or "Open glyphs in Glyphs"
    bridge_url = _glyphs_show_bridge_url(url) or url
    return {
        "showUrl": url,
        "showHttpUrl": bridge_url,
        "showMarkdown": "[{}]({})".format(_markdown_link_label(link_label), bridge_url),
    }


def _glyphs_show_link_fields(file_path, glyph_name=None, production_name=None, layer_ids=None, label=None):
    """Return showUrl/showMarkdown fields, or showUrlUnavailableReason."""
    url, reason = _glyphs_show_url(
        file_path,
        glyph_name=glyph_name,
        production_name=production_name,
        layer_ids=layer_ids,
    )
    if not url:
        return {"showUrlUnavailableReason": reason}

    link_label = label
    if not link_label:
        if glyph_name:
            link_label = "Open {} in Glyphs".format(glyph_name)
        elif production_name:
            link_label = "Open {} in Glyphs".format(production_name)
        else:
            link_label = "Open in Glyphs"

    bridge_url = _glyphs_show_bridge_url(url) or url
    return {
        "showUrl": url,
        "showHttpUrl": bridge_url,
        "showMarkdown": "[{}]({})".format(_markdown_link_label(link_label), bridge_url),
    }


def _glyphs_show_layer_link_fields(file_path, glyph_name=None, production_name=None, layer_id=None, label=None):
    """Return show link fields for a specific glyph layer."""
    if not layer_id:
        return {"showUrlUnavailableReason": "Layer ID unavailable; Glyphs show layer URLs require a layer ID."}
    return _glyphs_show_link_fields(
        file_path,
        glyph_name=glyph_name,
        production_name=production_name,
        layer_ids=[layer_id],
        label=label,
    )


_STYLE_SET_TAG_RE = re.compile(r"^ss(?:0[1-9]|1[0-9]|20)$")
_SIMPLE_SUB_RE = re.compile(r"^sub\s+(.+?)\s+by\s+(.+?)$", re.S)


def _is_style_set_tag(tag):
    try:
        return bool(_STYLE_SET_TAG_RE.match(str(tag or "")))
    except Exception:
        return False


def _strip_feature_comments(code):
    lines = []
    for line in str(code or "").splitlines():
        lines.append(line.split("#", 1)[0])
    return "\n".join(lines)


def _parse_feature_glyph_list(text):
    value = str(text or "").strip()
    if not value:
        return None

    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1].strip()
    elif any(ch.isspace() for ch in value):
        return None

    glyphs = [part.strip() for part in value.split() if part.strip()]
    if not glyphs:
        return None

    for glyph in glyphs:
        if any(marker in glyph for marker in ("'", "\\", "@")):
            return None

    return glyphs


def _parse_style_set_substitutions(code):
    """Parse simple AFDKO substitutions from stylistic-set feature code."""
    substitutions = []
    unsupported_rule_count = 0
    warnings = []
    clean_code = _strip_feature_comments(code)

    for statement in clean_code.split(";"):
        rule = " ".join(statement.strip().split())
        if not rule:
            continue

        if not rule.startswith("sub "):
            unsupported_rule_count += 1
            continue

        replacement_is_bracketed = " by [" in rule
        source_is_bracketed = "[" in rule.split(" by ", 1)[0]
        if (
            "'" in rule
            or " lookup " in rule
            or " from " in rule
            or (replacement_is_bracketed and not source_is_bracketed)
        ):
            unsupported_rule_count += 1
            continue

        match = _SIMPLE_SUB_RE.match(rule)
        if not match:
            unsupported_rule_count += 1
            continue

        source_glyphs = _parse_feature_glyph_list(match.group(1))
        replacement_glyphs = _parse_feature_glyph_list(match.group(2))
        if not source_glyphs or not replacement_glyphs or len(source_glyphs) != len(replacement_glyphs):
            unsupported_rule_count += 1
            continue

        for source, replacement in zip(source_glyphs, replacement_glyphs):
            substitutions.append(
                {
                    "source": source,
                    "replacement": replacement,
                }
            )

    if unsupported_rule_count:
        warnings.append(
            "{} unsupported or contextual feature rule(s) were skipped.".format(
                unsupported_rule_count
            )
        )

    return {
        "substitutions": substitutions,
        "unsupportedRuleCount": unsupported_rule_count,
        "warnings": warnings,
    }


def _style_set_name_from_metadata(tag, notes=None, labels=None):
    """Return a human-readable stylistic-set name from Glyphs metadata."""
    label_index = None
    try:
        label_index = int(str(tag)[2:]) - 1
    except Exception:
        label_index = None

    if labels is not None and label_index is not None:
        try:
            label = labels[label_index]
        except Exception:
            label = None
        if label:
            return str(label).strip()

    for line in str(notes or "").splitlines():
        line = line.strip()
        if not line:
            continue
        for prefix in ("Name:", "UI Name:", "Stylistic Set Name:", "Feature Name:"):
            if line.lower().startswith(prefix.lower()):
                candidate = line[len(prefix):].strip()
                if candidate:
                    return candidate
        if len(line) <= 80 and ";" not in line and "sub " not in line:
            return line

    return None


def _safe_attr(obj, attr_name, default=None):
    """Fetch an attribute without crashing on proxies or selectors."""
    try:
        value = getattr(obj, attr_name)
        if callable(value):
            return value()
        return value
    except AttributeError:
        return default
    except Exception:
        return default


def _coerce_numeric(value):
    """Convert Glyphs/AppKit objects or selectors to plain floats/ints."""
    if value is None:
        return None

    try:
        if callable(value):
            value = value()
    except Exception:
        return None

    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        pass

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _round_half_away_from_zero(x: float) -> int:
    xf = float(x)
    if xf >= 0.0:
        return int(math.floor(xf + 0.5))
    return -int(math.floor(abs(xf) + 0.5))


def _units_int(value):
    f = _coerce_numeric(value)
    if f is None:
        return None
    return _round_half_away_from_zero(float(f))


def _glyphs_major_version():
    try:
        from GlyphsApp import Glyphs  # type: ignore[import-not-found]

        version = getattr(Glyphs, "versionNumber", None)
    except Exception:
        return None
    try:
        return int(float(version))
    except Exception:
        return None


def _component_point_values(value):
    if value is None:
        return None, None

    x_value = _coerce_numeric(getattr(value, "x", None))
    y_value = _coerce_numeric(getattr(value, "y", None))
    if x_value is not None and y_value is not None:
        return float(x_value), float(y_value)

    if isinstance(value, (list, tuple)) and len(value) >= 2:
        x_value = _coerce_numeric(value[0])
        y_value = _coerce_numeric(value[1])
        if x_value is not None and y_value is not None:
            return float(x_value), float(y_value)

    return None, None


def _component_transform_from_public_attrs(component):
    position = getattr(component, "position", None)
    pos_x, pos_y = _component_point_values(position)
    scale = getattr(component, "scale", None)
    scale_x, scale_y = _component_point_values(scale)

    if pos_x is None or pos_y is None:
        return None

    if scale_x is None or scale_y is None:
        scale_x, scale_y = 1.0, 1.0

    rotation = _coerce_numeric(getattr(component, "rotation", 0.0))
    if not rotation:
        return [float(scale_x), 0.0, 0.0, float(scale_y), float(pos_x), float(pos_y)]

    radians = math.radians(float(rotation))
    sin_value = math.sin(radians)
    cos_value = math.cos(radians)
    return [
        float(scale_x) * cos_value,
        float(scale_x) * sin_value,
        -float(scale_y) * sin_value,
        float(scale_y) * cos_value,
        float(pos_x),
        float(pos_y),
    ]


def _component_transform_values(component_or_transform):
    """Return a six-value component transform without unsafe proxy iteration.

    Prefer documented GSComponent properties (`position`, `scale`, `rotation`).
    Some Glyphs 3/PyObjC transform proxies can hang when indexed, so only index
    plain Python lists/tuples after public component attributes and named matrix
    fields have failed.
    """
    public_values = _component_transform_from_public_attrs(component_or_transform)
    if public_values is not None:
        return public_values

    try:
        transform = getattr(component_or_transform, "transform", component_or_transform)
    except Exception:
        transform = component_or_transform
    if transform is None:
        return [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]

    public_values = _component_transform_from_public_attrs(transform)
    if public_values is not None:
        return public_values

    for attr_names in (
        ("m11", "m12", "m21", "m22", "tX", "tY"),
        ("a", "b", "c", "d", "tx", "ty"),
    ):
        values = []
        for attr_name in attr_names:
            try:
                values.append(_coerce_numeric(getattr(transform, attr_name, None)))
            except Exception:
                values.append(None)
        if all(value is not None for value in values):
            return [float(value) for value in values]

    defaults = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    if isinstance(transform, (list, tuple)):
        values = []
        for index, default in enumerate(defaults):
            try:
                value = _coerce_numeric(transform[index])
            except Exception:
                value = None
            values.append(default if value is None else float(value))
        return values

    return defaults


def _is_component_shape(shape):
    try:
        name = getattr(shape, "componentName", None)
    except Exception:
        name = None
    return name is not None


def _layer_components(layer, max_shapes=2000):
    """Return components from a layer without relying on GSLayer.components.

    Glyphs' documented mixed-shape collection is `GSLayer.shapes`. Glyphs 3 can
    expose `layer.components` as a proxy that is unsafe to iterate after some
    component writes, so production code prefers `layer.shapes` and only falls
    back to `layer.components` when shapes has no component data to report.
    """
    try:
        shapes = getattr(layer, "shapes", None)
    except Exception:
        shapes = None

    if shapes is not None:
        components = []
        try:
            for index, shape in enumerate(shapes):
                if index >= int(max_shapes):
                    break
                if _is_component_shape(shape):
                    components.append(shape)
        except Exception:
            return []
        if components:
            return components
        if _glyphs_major_version() == 3:
            return []

    try:
        components = getattr(layer, "components", None)
    except Exception:
        components = None

    values = _sequence_values(components)
    if values:
        return [component for component in values[: int(max_shapes)] if _is_component_shape(component)]

    return []


def _new_glyph(GSGlyph, glyph_name):
    """Create a GSGlyph without relying on version-specific constructors."""
    name = str(glyph_name)
    # Public Glyphs API: GSGlyph(name, autoName=True). Use autoName=False so
    # arbitrary MCP/test glyph names are not silently normalized in Glyphs 3.
    for args in ((name, False), (name,)):
        try:
            glyph = GSGlyph(*args)
            try:
                glyph.name = name
            except Exception:
                pass
            return glyph
        except Exception:
            pass
    try:
        glyph = GSGlyph()
        glyph.name = name
        return glyph
    except Exception:
        raise


def _call_noarg_method(obj, method_name):
    try:
        method = getattr(obj, method_name, None)
    except Exception:
        return False
    if not callable(method):
        return False
    try:
        method()
        return True
    except Exception:
        return False


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
    def initWithCallable_(self, callback):
        self = objc.super(type(self), self).init()
        if self is None:
            return None
        self._callback = callback
        self.result = None
        self.error = None
        return self

    def run_(self, _obj):
        try:
            self.result = self._callback()
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


def _run_on_main_thread(callback):
    """Run a small Glyphs mutation on the main thread when PyObjC is available."""
    if callback is None:
        return None
    if objc is None or NSObject is None:
        return callback()
    try:
        if NSThread is not None and NSThread.isMainThread():
            return callback()
    except Exception:
        pass

    helper_class = _get_main_thread_helper_class()
    helper = helper_class.alloc().initWithCallable_(callback)
    if helper is None:
        return callback()
    helper.performSelectorOnMainThread_withObject_waitUntilDone_("run:", None, True)
    if getattr(helper, "error", None) is not None:
        raise helper.error
    return getattr(helper, "result", None)


def _show_notification(Glyphs, title, message):
    """Display a Glyphs notification on the main thread, best effort."""
    def _notify():
        try:
            Glyphs.showNotification(title, message)
        except Exception:
            pass

    _run_on_main_thread(_notify)


def _begin_font_update_block(font):
    # Public API: pause font UI updates around append/delete style mutations.
    return _call_noarg_method(font, "disableUpdateInterface")


def _end_font_update_block(font, update_open):
    if update_open:
        _call_noarg_method(font, "enableUpdateInterface")


def _layer_parent_glyph(layer):
    try:
        return _maybe_call(getattr(layer, "parent", None))
    except Exception:
        return None


def _begin_layer_mutation(layer):
    # Public API first: Glyphs documents beginChanges as the way to avoid undo
    # problems during bigger layer edits. Do not additionally open glyph undo
    # groups here; live Glyphs 4 testing showed beginUndo/endUndo can trigger
    # the "problem with undo" recovery dialog for MCP-driven batch writes.
    changes_open = _call_noarg_method(layer, "beginChanges")
    return changes_open


def _end_layer_mutation(layer, state):
    changes_open = state
    if changes_open:
        _call_noarg_method(layer, "endChanges")


def _append_font_glyph(font, glyph, glyph_name):
    """Append a glyph and return the verified glyph lookup, or None."""
    name = str(glyph_name)
    try:
        glyph.name = name
    except Exception:
        pass

    def _mutate():
        update_open = _begin_font_update_block(font)
        try:
            font.glyphs.append(glyph)
            return True
        except Exception:
            return False
        finally:
            _end_font_update_block(font, update_open)

    if not _run_on_main_thread(_mutate):
        return None
    try:
        return font.glyphs[name]
    except Exception:
        return None


def _delete_font_glyph(font, glyph_name):
    """Delete a glyph from font.glyphs using the documented collection API."""
    name = str(glyph_name)

    def _mutate():
        update_open = _begin_font_update_block(font)
        try:
            del font.glyphs[name]
            return True
        except Exception:
            return False
        finally:
            _end_font_update_block(font, update_open)

    if not _run_on_main_thread(_mutate):
        return False
    try:
        return font.glyphs[name] is None
    except Exception:
        return True


def _new_anchor(GSAnchor, anchor_name, x, y):
    """Create a GSAnchor with a Glyphs 3 compatible fallback."""
    try:
        return GSAnchor(anchor_name, (x, y))
    except Exception:
        anchor = GSAnchor()
        anchor.name = str(anchor_name)
        try:
            anchor.position = (float(x), float(y))
        except Exception:
            try:
                anchor.x = float(x)
                anchor.y = float(y)
            except Exception:
                pass
        return anchor


def _is_path_shape(shape):
    try:
        nodes = getattr(shape, "nodes", None)
    except Exception:
        return False
    return nodes is not None


def _mapping_keys(mapping):
    """Return stable string keys from dict-like Glyphs proxy objects."""
    if mapping is None:
        return []
    try:
        keys = list(mapping.keys())
    except Exception:
        try:
            keys = list(mapping)
        except Exception:
            return []
    return sorted({str(key) for key in keys})


def _mapping_value(mapping, key, default=None):
    if mapping is None:
        return default
    try:
        return mapping[key]
    except Exception:
        return default


def _shape_attribute_metadata(shape):
    try:
        attributes = getattr(shape, "attributes", None)
    except Exception:
        attributes = None
    try:
        user_data = getattr(shape, "userData", None)
    except Exception:
        user_data = None
    attribute_keys = _mapping_keys(attributes)
    group_id = _mapping_value(attributes, "group")
    return {
        "attributeKeys": attribute_keys,
        "groupId": str(group_id) if group_id not in (None, "") else None,
        "hasUserData": bool(_mapping_keys(user_data)),
    }


def _shape_kind(shape):
    if _is_path_shape(shape):
        return "path"
    if _is_component_shape(shape):
        return "component"

    class_name = ""
    try:
        class_name = str(shape.__class__.__name__)
    except Exception:
        pass
    try:
        objc_name = getattr(shape, "className", None)
        if callable(objc_name):
            objc_name = objc_name()
        if objc_name:
            class_name = "{} {}".format(class_name, objc_name)
    except Exception:
        pass
    normalized = class_name.lower()
    if "shapegroup" in normalized or "shape group" in normalized:
        return "shapeGroup"
    if "image" in normalized:
        return "image"
    try:
        if getattr(shape, "groupId", None) is not None:
            return "shapeGroup"
    except Exception:
        pass
    return "unknown"


def _layer_shape_summary(layer):
    try:
        shapes = _sequence_values(getattr(layer, "shapes", None))
    except Exception:
        shapes = []
    if not shapes:
        paths = _layer_paths(layer)
        try:
            components = _layer_components(layer)
        except Exception:
            components = []
        shapes = list(paths) + list(components)

    counts = {
        "path": 0,
        "component": 0,
        "image": 0,
        "shapeGroup": 0,
        "unknown": 0,
    }
    for shape in shapes:
        kind = _shape_kind(shape)
        counts[kind if kind in counts else "unknown"] += 1
    attribute_keys = set()
    grouped_shape_count = 0
    group_ids = set()
    styled_shape_count = 0
    for shape in shapes:
        metadata = _shape_attribute_metadata(shape)
        keys = set(metadata["attributeKeys"])
        attribute_keys.update(keys)
        if metadata["groupId"]:
            grouped_shape_count += 1
            group_ids.add(metadata["groupId"])
        if keys - {"group"}:
            styled_shape_count += 1

    compatibility_warnings = []
    if counts["shapeGroup"]:
        compatibility_warnings.append(
            "This layer contains Glyphs 4 shape groups. Outline edits preserve "
            "their identities and member relationships but do not author groups."
        )
    if counts["image"]:
        compatibility_warnings.append(
            "This layer contains image shapes. Outline edits preserve their "
            "identity and draw order but do not author images."
        )
    if grouped_shape_count or styled_shape_count:
        compatibility_warnings.append(
            "This layer contains grouped or styled shapes. Shape attributes are "
            "diagnostic-only and are preserved automatically."
        )
    return {
        "shapeCount": len(shapes),
        "shapeTypeCounts": counts,
        "nonPathShapeCounts": {
            key: value for key, value in counts.items() if key != "path"
        },
        "shapeAttributeKeys": sorted(attribute_keys),
        "groupedShapeCount": grouped_shape_count,
        "shapeGroupIds": sorted(group_ids),
        "styledShapeCount": styled_shape_count,
        "hasGlyphs4Shapes": bool(counts["image"] or counts["shapeGroup"]),
        "compatibilityWarnings": compatibility_warnings,
    }


def _raw_objc_value(obj, selector_name):
    """Read an Objective-C scalar without passing through lossy wrappers."""
    try:
        instance_methods = getattr(obj, "pyobjc_instanceMethods", None)
        selector = getattr(instance_methods, selector_name, None)
        if callable(selector):
            return selector()
    except Exception:
        pass
    return None


def _node_raw_type(node):
    value = _raw_objc_value(node, "type")
    if value is None:
        try:
            value = getattr(node, "rawType", None)
        except Exception:
            value = None
    try:
        return int(value) if value is not None else None
    except Exception:
        return None


def _node_raw_connection(node):
    value = _raw_objc_value(node, "connection")
    if value is None:
        try:
            value = getattr(node, "rawConnection", None)
        except Exception:
            value = None
    try:
        return int(value) if value is not None else None
    except Exception:
        return None


def _node_orientation(node):
    """Return the normalized and raw GSElementOrientation values."""
    value = _raw_objc_value(node, "orientation")
    if value is None:
        try:
            value = getattr(node, "orientation", None)
            if callable(value):
                value = value()
        except Exception:
            value = None

    try:
        raw_value = int(value) if value is not None else None
    except Exception:
        raw_value = None

    if raw_value is not None:
        # GSElementOrientation is shared with components: left=0, right=1,
        # center=2. The v4 node serialization spells these values as strings.
        normalized = {0: "left", 1: "right", 2: "center"}.get(
            raw_value, "unknown"
        )
        return normalized, raw_value

    normalized = str(value or "").strip().lower()
    if normalized not in {"left", "right", "center"}:
        normalized = None
    return normalized, None


def _set_node_raw_value(node, selector_name, value):
    """Set an Objective-C node enum without lossy wrapper normalization."""
    setter_name = "set{}_".format(selector_name[:1].upper() + selector_name[1:])
    try:
        instance_methods = getattr(node, "pyobjc_instanceMethods", None)
        setter = getattr(instance_methods, setter_name, None)
        if callable(setter):
            setter(int(value))
            return True
    except Exception:
        pass
    try:
        setter = getattr(node, setter_name, None)
        if callable(setter):
            setter(int(value))
            return True
    except Exception:
        pass
    try:
        setattr(node, selector_name, int(value))
        return True
    except Exception:
        return False


def _collection_contains_identity(collection, item):
    for value in _sequence_values(collection):
        if value is item:
            return True
    return False


def _set_layer_shapes(layer, shapes):
    shapes = list(shapes or [])
    try:
        layer.shapes = shapes
        return True
    except Exception:
        pass

    try:
        collection = getattr(layer, "shapes", None)
    except Exception:
        collection = None
    if collection is None:
        return False

    try:
        count = len(collection)
        for index in range(count - 1, -1, -1):
            del collection[index]
        for shape in shapes:
            collection.append(shape)
        return True
    except Exception:
        return False


def _append_to_collection(layer, attr_name, item):
    try:
        collection = getattr(layer, attr_name, None)
    except Exception:
        collection = None
    if collection is None:
        return False

    try:
        before = len(collection)
    except Exception:
        before = None

    try:
        collection.append(item)
    except Exception:
        return False

    try:
        if _collection_contains_identity(collection, item):
            return True
    except Exception:
        pass
    try:
        return before is None or len(collection) > before
    except Exception:
        return True


def _append_layer_shape(layer, shape, _manage_changes=True):
    """Append a GSShape through GSLayer.shapes, the documented mutable surface."""
    if shape is None:
        return False

    def _mutate():
        mutation_state = _begin_layer_mutation(layer) if _manage_changes else None
        try:
            return _append_layer_shape_unmanaged(layer, shape)
        finally:
            if mutation_state is not None:
                _end_layer_mutation(layer, mutation_state)

    if _manage_changes:
        return bool(_run_on_main_thread(_mutate))
    return _append_layer_shape_unmanaged(layer, shape)


def _append_layer_shape_unmanaged(layer, shape):
    """Append a GSShape through GSLayer.shapes without opening undo groups."""

    try:
        shapes = getattr(layer, "shapes", None)
    except Exception:
        shapes = None

    if shapes is not None:
        before = _sequence_values(shapes)
        try:
            shapes.append(shape)
            if _collection_contains_identity(getattr(layer, "shapes", None), shape):
                return True
            try:
                if len(getattr(layer, "shapes", []) or []) > len(before):
                    return True
            except Exception:
                pass
        except Exception:
            pass
        if _set_layer_shapes(layer, before + [shape]):
            if _collection_contains_identity(getattr(layer, "shapes", None), shape):
                return True
            try:
                if len(getattr(layer, "shapes", []) or []) >= len(before) + 1:
                    return True
            except Exception:
                pass

    if _is_path_shape(shape):
        try:
            if hasattr(layer, "addPath_"):
                layer.addPath_(shape)
                if _collection_contains_identity(getattr(layer, "paths", None), shape):
                    return True
                return True
        except Exception:
            pass
        return _append_to_collection(layer, "paths", shape)

    if _glyphs_major_version() == 3:
        return False
    return _append_to_collection(layer, "components", shape)


def _layer_paths(layer):
    try:
        paths = getattr(layer, "paths", None)
    except Exception:
        paths = None
    values = _sequence_values(paths)
    if values:
        return values

    try:
        shapes = getattr(layer, "shapes", None)
    except Exception:
        shapes = None
    return [shape for shape in _sequence_values(shapes) if _is_path_shape(shape)]


def _layer_path_summary(layer):
    paths = _layer_paths(layer)
    node_count = 0
    for path in paths:
        try:
            node_count += len(getattr(path, "nodes", []) or [])
        except Exception:
            pass
    return {"pathCount": len(paths), "nodeCount": node_count}


def _replace_layer_paths(layer, paths):
    """Replace paths while preserving non-path shapes such as components."""
    return _replace_layer_paths_and_metrics(layer, paths)


def _replace_layer_paths_and_metrics(
    layer,
    paths,
    width=None,
    left_sidebearing=None,
    right_sidebearing=None,
):
    """Replace paths and optional metrics in one main-thread layer change block."""
    new_paths = list(paths or [])

    def _mutate():
        mutation_state = _begin_layer_mutation(layer)
        try:
            result = _replace_layer_paths_unmanaged(layer, new_paths)
            if not result.get("ok"):
                return result
            if left_sidebearing is not None:
                _set_sidebearing(layer, "leftSideBearing", "LSB", left_sidebearing)
            if right_sidebearing is not None:
                _set_sidebearing(layer, "rightSideBearing", "RSB", right_sidebearing)
            if width is not None:
                layer.width = width
            return result
        finally:
            _end_layer_mutation(layer, mutation_state)

    return _run_on_main_thread(_mutate)


_KNOWN_NODE_TYPES = {
    "move",
    "line",
    "curve",
    "qcurve",
    "offcurve",
    "hobbycurve",
    "raphnewspiral",
}


def _point_values(point):
    if point is None:
        return (0.0, 0.0)
    try:
        return (float(point.x), float(point.y))
    except Exception:
        pass
    try:
        return (float(point[0]), float(point[1]))
    except Exception:
        return (0.0, 0.0)


def _copy_glyphs_object(value):
    try:
        copied = value.copy()
        if copied is not None:
            return copied
    except Exception:
        pass
    try:
        copied = value.mutableCopy()
        if copied is not None:
            return copied
    except Exception:
        pass
    return None


def _set_path_nodes(path, nodes):
    nodes = list(nodes or [])
    try:
        path.nodes = nodes
        return len(_sequence_values(getattr(path, "nodes", None))) == len(nodes)
    except Exception:
        pass
    try:
        collection = getattr(path, "nodes", None)
        for index in range(len(collection) - 1, -1, -1):
            del collection[index]
        for node in nodes:
            collection.append(node)
        return len(_sequence_values(collection)) == len(nodes)
    except Exception:
        return False


def _normalized_node_type(node):
    raw_type = _node_raw_type(node)
    raw_names = {
        17: "move",
        1: "line",
        35: "curve",
        36: "qcurve",
        37: "hobbycurve",
        39: "raphnewspiral",
        65: "offcurve",
    }
    if raw_type is not None:
        return raw_names.get(raw_type, "unknown")
    try:
        value = str(getattr(node, "type", "") or "").lower()
    except Exception:
        value = ""
    return value if value in _KNOWN_NODE_TYPES else "unknown"


def _path_specs_topology_matches(paths, path_specs):
    if len(paths) != len(path_specs):
        return False
    for path, spec in zip(paths, path_specs):
        if len(_sequence_values(getattr(path, "nodes", None))) != len(spec.get("nodes") or []):
            return False
    return True


def _validate_path_specs(paths, path_specs):
    topology_matches = _path_specs_topology_matches(paths, path_specs)
    errors = []
    for path_index, spec in enumerate(path_specs):
        old_nodes = []
        if path_index < len(paths):
            old_nodes = _sequence_values(getattr(paths[path_index], "nodes", None))
        for node_index, node_spec in enumerate(spec.get("nodes") or []):
            try:
                x = float(node_spec.get("x", 0.0))
                y = float(node_spec.get("y", 0.0))
                if not math.isfinite(x) or not math.isfinite(y):
                    raise ValueError("coordinates must be finite")
            except Exception:
                errors.append(
                    "Path {} node {} has invalid coordinates".format(path_index, node_index)
                )
                continue

            requested_type = str(node_spec.get("type", "line") or "line").lower()
            requested_raw = node_spec.get("rawType")
            old_node = old_nodes[node_index] if node_index < len(old_nodes) else None
            old_type = _normalized_node_type(old_node) if old_node is not None else None
            old_raw = _node_raw_type(old_node) if old_node is not None else None

            if old_type == "unknown" and requested_raw is None:
                errors.append(
                    "Path {} node {} requires pathDataVersion 2 rawType metadata".format(
                        path_index, node_index
                    )
                )
                continue
            if requested_type == "unknown":
                if old_node is None or requested_raw is None:
                    errors.append(
                        "Path {} node {} uses an unknown type without a matching source node".format(
                            path_index, node_index
                        )
                    )
                    continue
                try:
                    if int(requested_raw) != int(old_raw):
                        raise ValueError
                except Exception:
                    errors.append(
                        "Path {} node {} changes an unknown raw type".format(
                            path_index, node_index
                        )
                    )
            elif requested_type not in _KNOWN_NODE_TYPES:
                errors.append(
                    "Path {} node {} has unsupported type '{}'".format(
                        path_index, node_index, requested_type
                    )
                )
            elif requested_raw is not None and old_node is None:
                errors.append(
                    "Path {} node {} supplies rawType for a new node".format(
                        path_index, node_index
                    )
                )
            elif (
                requested_raw is not None
                and old_node is not None
                and requested_type == old_type
            ):
                try:
                    if int(requested_raw) != int(old_raw):
                        raise ValueError
                except Exception:
                    errors.append(
                        "Path {} node {} changes rawType without a normalized type change".format(
                            path_index, node_index
                        )
                    )

            requested_connection = node_spec.get("rawConnection")
            if requested_connection is not None and old_node is None:
                errors.append(
                    "Path {} node {} supplies rawConnection for a new node".format(
                        path_index, node_index
                    )
                )
            elif requested_connection is not None and old_node is not None:
                try:
                    int(requested_connection)
                except Exception:
                    errors.append(
                        "Path {} node {} has invalid rawConnection".format(
                            path_index, node_index
                        )
                    )

    if not topology_matches:
        for path_index, old_path in enumerate(paths):
            old_nodes = _sequence_values(getattr(old_path, "nodes", None))
            requested_nodes = (
                path_specs[path_index].get("nodes") or []
                if path_index < len(path_specs)
                else []
            )
            for node_index, old_node in enumerate(old_nodes):
                if _normalized_node_type(old_node) != "unknown":
                    continue
                if node_index >= len(requested_nodes):
                    errors.append(
                        "Path {} node {} has an unknown raw type and cannot be "
                        "dropped by a topology rewrite".format(path_index, node_index)
                    )
                    continue
                requested_raw = requested_nodes[node_index].get("rawType")
                try:
                    raw_matches = int(requested_raw) == int(_node_raw_type(old_node))
                except Exception:
                    raw_matches = False
                if not raw_matches:
                    errors.append(
                        "Path {} node {} has an unknown raw type that cannot be "
                        "matched safely during a topology rewrite".format(
                            path_index, node_index
                        )
                    )
    return topology_matches, errors


def _apply_node_spec(node, spec, old_node=None):
    node.position = (float(spec.get("x", 0.0)), float(spec.get("y", 0.0)))

    requested_type = str(spec.get("type", "line") or "line").lower()
    old_type = _normalized_node_type(old_node) if old_node is not None else None
    if requested_type != "unknown" and (old_node is None or requested_type != old_type):
        node.type = requested_type

    if "rawConnection" in spec and old_node is not None:
        requested_raw_connection = spec.get("rawConnection")
        old_raw_connection = _node_raw_connection(old_node)
        if (
            requested_raw_connection is not None
            and old_raw_connection is not None
            and int(requested_raw_connection) != int(old_raw_connection)
        ):
            if not _set_node_raw_value(
                node, "connection", requested_raw_connection
            ):
                node.smooth = bool(spec.get("smooth", False))
    elif "smooth" in spec:
        node.smooth = bool(spec.get("smooth", False))

    if "orientation" in spec and spec.get("orientation") is not None:
        try:
            node.orientation = int(spec["orientation"])
        except Exception:
            pass
    if "name" in spec:
        try:
            node.name = spec.get("name")
        except Exception:
            pass


def _snapshot_existing_paths(paths):
    snapshot = []
    for path in paths:
        path_state = {
            "path": path,
            "closed": bool(getattr(path, "closed", True)),
            "locked": getattr(path, "locked", None),
            "nodes": [],
        }
        for node in _sequence_values(getattr(path, "nodes", None)):
            path_state["nodes"].append(
                {
                    "node": node,
                    "position": _point_values(getattr(node, "position", None)),
                    "rawType": _node_raw_type(node),
                    "type": _normalized_node_type(node),
                    "rawConnection": _node_raw_connection(node),
                    "smooth": bool(getattr(node, "smooth", False)),
                    "orientation": _node_orientation(node),
                    "name": getattr(node, "name", None),
                }
            )
        snapshot.append(path_state)
    return snapshot


def _restore_existing_paths(snapshot):
    restored = True
    for path_state in snapshot:
        path = path_state["path"]
        try:
            path.closed = path_state["closed"]
            if path_state["locked"] is not None:
                path.locked = path_state["locked"]
        except Exception:
            restored = False
        for node_state in path_state["nodes"]:
            node = node_state["node"]
            try:
                node.position = node_state["position"]
                raw_type = node_state["rawType"]
                if raw_type is not None:
                    if not _set_node_raw_value(node, "type", raw_type):
                        restored = False
                else:
                    node.type = node_state["type"]
                raw_connection = node_state["rawConnection"]
                if raw_connection is not None:
                    if not _set_node_raw_value(
                        node, "connection", raw_connection
                    ):
                        restored = False
                else:
                    node.smooth = node_state["smooth"]
                orientation, raw_orientation = node_state["orientation"]
                if raw_orientation is not None:
                    if not _set_node_raw_value(
                        node, "orientation", raw_orientation
                    ):
                        restored = False
                elif orientation is not None:
                    node.orientation = orientation
                node.name = node_state["name"]
            except Exception:
                restored = False
    return restored


def _build_path_from_spec(spec, old_path, GSPath, GSNode):
    if old_path is not None:
        path = _copy_glyphs_object(old_path)
        if path is None:
            return None, "Unable to copy an existing path while preserving metadata"
        old_nodes = _sequence_values(getattr(old_path, "nodes", None))
    else:
        path = GSPath()
        old_nodes = []

    new_nodes = []
    for node_index, node_spec in enumerate(spec.get("nodes") or []):
        old_node = old_nodes[node_index] if node_index < len(old_nodes) else None
        if old_node is not None:
            node = _copy_glyphs_object(old_node)
            if node is None:
                return None, "Unable to copy an existing node while preserving metadata"
        else:
            node = GSNode()
        _apply_node_spec(node, node_spec, old_node=old_node)
        new_nodes.append(node)

    if not _set_path_nodes(path, new_nodes):
        return None, "Unable to replace path nodes"
    path.closed = bool(spec.get("closed", True))
    if "locked" in spec:
        try:
            path.locked = bool(spec.get("locked"))
        except Exception:
            pass
    return path, None


def _merge_paths_into_shape_order(original_shapes, new_paths):
    merged = []
    path_index = 0
    insertion_index = None
    for shape in original_shapes:
        if _is_path_shape(shape):
            if path_index < len(new_paths):
                merged.append(new_paths[path_index])
                insertion_index = len(merged)
                path_index += 1
            continue
        merged.append(shape)

    if path_index < len(new_paths):
        if insertion_index is None:
            insertion_index = len(merged)
        merged[insertion_index:insertion_index] = new_paths[path_index:]
    return merged


def _verify_path_specs(layer, path_specs):
    paths = _layer_paths(layer)
    if len(paths) != len(path_specs):
        return False
    for path, spec in zip(paths, path_specs):
        nodes = _sequence_values(getattr(path, "nodes", None))
        expected_nodes = spec.get("nodes") or []
        if len(nodes) != len(expected_nodes):
            return False
        if bool(getattr(path, "closed", True)) != bool(spec.get("closed", True)):
            return False
        if "locked" in spec and bool(getattr(path, "locked", False)) != bool(
            spec.get("locked")
        ):
            return False
        for node, node_spec in zip(nodes, expected_nodes):
            x, y = _point_values(getattr(node, "position", None))
            if abs(x - float(node_spec.get("x", 0.0))) > 0.001:
                return False
            if abs(y - float(node_spec.get("y", 0.0))) > 0.001:
                return False
            expected_type = str(
                node_spec.get("type", "line") or "line"
            ).lower()
            if (
                expected_type != "unknown"
                and _normalized_node_type(node) != expected_type
            ):
                return False
            if node_spec.get("rawType") is not None:
                try:
                    if int(_node_raw_type(node)) != int(node_spec["rawType"]):
                        return False
                except Exception:
                    return False
            if node_spec.get("rawConnection") is not None:
                try:
                    if int(_node_raw_connection(node)) != int(
                        node_spec["rawConnection"]
                    ):
                        return False
                except Exception:
                    return False
    return True


def _apply_path_specs_and_metrics(
    layer,
    path_specs,
    GSPath,
    GSNode,
    width=None,
    left_sidebearing=None,
    right_sidebearing=None,
):
    """Apply path JSON while preserving Glyphs 3/4 shape metadata and order."""
    path_specs = list(path_specs or [])
    existing_paths = _layer_paths(layer)
    topology_matches, errors = _validate_path_specs(existing_paths, path_specs)
    if errors:
        return {
            "ok": False,
            "error": "Unsafe path rewrite rejected",
            "details": errors,
            "pathCount": len(existing_paths),
            "nodeCount": _layer_path_summary(layer)["nodeCount"],
            "rolledBack": True,
        }

    original_shapes = _sequence_values(getattr(layer, "shapes", None))
    has_shapes_surface = bool(original_shapes) or hasattr(layer, "shapes")
    original_non_paths = [shape for shape in original_shapes if not _is_path_shape(shape)]
    snapshot = _snapshot_existing_paths(existing_paths)
    original_metrics = {
        "width": getattr(layer, "width", None),
        "left": _get_left_sidebearing(layer),
        "right": _get_right_sidebearing(layer),
    }

    def _restore_metrics():
        try:
            if original_metrics["left"] is not None:
                _set_sidebearing(
                    layer, "leftSideBearing", "LSB", original_metrics["left"]
                )
            if original_metrics["right"] is not None:
                _set_sidebearing(
                    layer, "rightSideBearing", "RSB", original_metrics["right"]
                )
            if original_metrics["width"] is not None:
                layer.width = original_metrics["width"]
            return True
        except Exception:
            return False

    def _mutate():
        mutation_state = _begin_layer_mutation(layer)
        changed_shape_list = False
        try:
            if topology_matches:
                for path, spec in zip(existing_paths, path_specs):
                    path.closed = bool(spec.get("closed", True))
                    if "locked" in spec:
                        try:
                            path.locked = bool(spec.get("locked"))
                        except Exception:
                            pass
                    for node, node_spec in zip(
                        _sequence_values(getattr(path, "nodes", None)),
                        spec.get("nodes") or [],
                    ):
                        _apply_node_spec(node, node_spec, old_node=node)
            else:
                staged_paths = []
                for path_index, spec in enumerate(path_specs):
                    old_path = (
                        existing_paths[path_index]
                        if path_index < len(existing_paths)
                        else None
                    )
                    staged_path, error = _build_path_from_spec(
                        spec, old_path, GSPath, GSNode
                    )
                    if error:
                        return {
                            "ok": False,
                            "error": error,
                            "rolledBack": True,
                        }
                    staged_paths.append(staged_path)

                if has_shapes_surface:
                    merged = _merge_paths_into_shape_order(
                        original_shapes, staged_paths
                    )
                    if not _set_layer_shapes(layer, merged):
                        raise RuntimeError(
                            "Unable to replace paths through GSLayer.shapes"
                        )
                    changed_shape_list = True
                else:
                    changed_shape_list = True
                    _clear_layer_paths(layer)
                    for path in staged_paths:
                        if not _append_layer_shape(
                            layer, path, _manage_changes=False
                        ):
                            raise RuntimeError(
                                "Failed to append path through the documented layer API"
                            )
                    changed_shape_list = True

            if left_sidebearing is not None:
                _set_sidebearing(
                    layer, "leftSideBearing", "LSB", left_sidebearing
                )
            if right_sidebearing is not None:
                _set_sidebearing(
                    layer, "rightSideBearing", "RSB", right_sidebearing
                )
            if width is not None:
                layer.width = width

            current_shapes = _sequence_values(getattr(layer, "shapes", None))
            current_non_paths = [
                shape for shape in current_shapes if not _is_path_shape(shape)
            ]
            non_paths_preserved = (
                len(current_non_paths) == len(original_non_paths)
                and all(
                    current is original
                    for current, original in zip(
                        current_non_paths, original_non_paths
                    )
                )
            )
            if has_shapes_surface and not non_paths_preserved:
                raise RuntimeError("Non-path shape order or identity changed")
            if not _verify_path_specs(layer, path_specs):
                raise RuntimeError("Path write verification failed")

            summary = _layer_path_summary(layer)
            summary.update(
                {
                    "ok": True,
                    "pathEditMode": (
                        "inPlace" if topology_matches else "topologyRewrite"
                    ),
                    "metadataPolicy": "preserve",
                    "rolledBack": False,
                }
            )
            return summary
        except Exception as exc:
            restored = True
            if changed_shape_list and has_shapes_surface:
                restored = bool(_set_layer_shapes(layer, original_shapes))
            elif changed_shape_list:
                _clear_layer_paths(layer)
                for original_path in existing_paths:
                    restored = bool(
                        _append_layer_shape(
                            layer, original_path, _manage_changes=False
                        )
                    ) and restored
            elif topology_matches:
                restored = _restore_existing_paths(snapshot)
            restored = _restore_metrics() and restored
            summary = _layer_path_summary(layer)
            summary.update(
                {
                    "ok": False,
                    "error": str(exc) or "Path mutation failed",
                    "rolledBack": bool(restored),
                }
            )
            return summary
        finally:
            _end_layer_mutation(layer, mutation_state)

    return _run_on_main_thread(_mutate)


def _replace_layer_paths_unmanaged(layer, new_paths):
    new_paths = list(new_paths or [])

    try:
        shapes = getattr(layer, "shapes", None)
    except Exception:
        shapes = None

    if shapes is not None:
        original_shapes = _sequence_values(shapes)
        merged_shapes = _merge_paths_into_shape_order(original_shapes, new_paths)
        if _set_layer_shapes(layer, merged_shapes):
            summary = _layer_path_summary(layer)
            if summary["pathCount"] == len(new_paths):
                return {"ok": True, **summary}
            _set_layer_shapes(layer, original_shapes)

    _clear_layer_paths(layer)
    for path in new_paths:
        if not _append_layer_shape(layer, path, _manage_changes=False):
            summary = _layer_path_summary(layer)
            summary.update({"ok": False, "error": "Failed to append path through GSLayer.shapes"})
            return summary

    summary = _layer_path_summary(layer)
    if summary["pathCount"] != len(new_paths):
        summary.update(
            {
                "ok": False,
                "error": "Path write verification failed",
                "expectedPathCount": len(new_paths),
            }
        )
        return summary
    summary["ok"] = True
    return summary


def _append_layer_anchor(layer, anchor):
    name = str(getattr(anchor, "name", "") or "").strip()
    def _mutate():
        mutation_state = _begin_layer_mutation(layer)
        try:
            return _append_layer_anchor_unmanaged(layer, anchor, name)
        finally:
            _end_layer_mutation(layer, mutation_state)

    return bool(_run_on_main_thread(_mutate))


def _append_layer_anchor_unmanaged(layer, anchor, name):
    try:
        anchors = getattr(layer, "anchors", None)
    except Exception:
        anchors = None
    if anchors is None:
        try:
            layer.anchors = [anchor]
            return True
        except Exception:
            return False

    if name:
        try:
            anchors[name] = anchor
            return True
        except Exception:
            pass

    try:
        anchors.append(anchor)
        return True
    except Exception:
        pass

    try:
        layer.anchors = _sequence_values(anchors) + [anchor]
        return True
    except Exception:
        return False


def _master_display_name(font, master_id):
    if font is None or not master_id:
        return None
    for master in _sequence_values(getattr(font, "masters", None)):
        try:
            if str(getattr(master, "id", "")) == str(master_id):
                name = getattr(master, "name", None)
                return str(name) if name else str(master_id)
        except Exception:
            pass
    return None


def _layer_display_name(font, layer, master_id=None):
    name = _safe_attr(layer, "name", None)
    if name is not None and str(name).strip() and str(name) != "None":
        return str(name)
    layer_master_id = master_id or _safe_attr(layer, "associatedMasterId", None) or _get_layer_id(layer)
    master_name = _master_display_name(font, layer_master_id)
    if master_name:
        return master_name
    if layer_master_id:
        return str(layer_master_id)
    return "Unknown layer"


def _clear_layer_paths(layer):
    """Remove all paths from a layer without touching components/anchors."""
    try:
        shapes = list(getattr(layer, "shapes", []) or [])
    except Exception:
        shapes = None

    if shapes is not None:
        try:
            layer.shapes = [shape for shape in shapes if not hasattr(shape, "nodes")]
            return
        except Exception:
            pass

    try:
        existing = list(getattr(layer, "paths", []) or [])
    except Exception:
        existing = []

    for path in existing:
        removed = False
        try:
            if hasattr(layer, "removePath_"):
                layer.removePath_(path)
                removed = True
        except Exception:
            removed = False

        if not removed:
            try:
                layer.paths.remove(path)
                removed = True
            except Exception:
                pass

        if not removed:
            try:
                idx = layer.paths.index(path)
                del layer.paths[idx]
            except Exception:
                pass


def _get_sidebearing(layer, attr_name, legacy_attr):
    """Return a sidebearing value even for proxy layers lacking modern attrs."""
    # Glyphs 3.5 can deadlock inside GSLayer LSB/RSB after component writes,
    # even when the getter is called from the main thread. Prefer returning an
    # explicit unknown metric over hanging the MCP server.
    if _glyphs_major_version() == 3:
        return None

    def _read():
        value = None
        try:
            value = getattr(layer, attr_name, None)
        except Exception:
            value = None

        value = _coerce_numeric(value)

        if value is None:
            try:
                fallback = getattr(layer, legacy_attr, None)
            except Exception:
                fallback = None
            value = _coerce_numeric(fallback)

        return value

    # Glyphs 3 can block background threads while resolving GSLayer LSB/RSB
    # after component edits. Read these documented layer metrics on the main
    # thread through the shared bridge.
    return _run_on_main_thread(_read)


def _get_left_sidebearing(layer):
    return _get_sidebearing(layer, "leftSideBearing", "LSB")


def _get_right_sidebearing(layer):
    return _get_sidebearing(layer, "rightSideBearing", "RSB")


def _get_component_automatic(component):
    """Return component "automatic alignment" flag if exposed by this Glyphs build.

    Glyphs API compatibility notes:
    - Some versions expose `GSComponent.automaticAlignment`.
    - Some environments (or older wrappers) may expose `GSComponent.automatic`.
    - Some versions expose neither; return None in that case.
    """

    for attr in ("automatic", "automaticAlignment"):
        try:
            value = getattr(component, attr, None)
        except Exception:
            value = None
        if value is None:
            continue
        try:
            return bool(value)
        except Exception:
            return None

    return None


def _get_layer_id(layer):
    """Return the Glyphs layer ID used by the show URL scheme, if available."""
    for attr in ("layerId", "id", "associatedMasterId"):
        try:
            value = getattr(layer, attr, None)
        except Exception:
            value = None
        if value is None:
            continue
        value = str(value).strip()
        if value:
            return value
    return None


def _set_sidebearing(layer, attr_name, legacy_attr, value):
    """Attempt to set a sidebearing using both modern and legacy attributes."""
    if value is None:
        return False
    # Glyphs 3.5 can deadlock in GSLayer setLSB:/setRSB: after component
    # edits. Width updates remain allowed; sidebearing requests are surfaced as
    # readback warnings by callers instead of risking a hung server.
    if _glyphs_major_version() == 3:
        return False

    try:
        setattr(layer, attr_name, value)
        return True
    except Exception:
        pass

    try:
        setattr(layer, legacy_attr, value)
        return True
    except Exception:
        return False


def _set_layer_metrics(
    layer,
    width=None,
    left_sidebearing=None,
    right_sidebearing=None,
):
    """Set layer metrics in one main-thread layer change block."""
    def _mutate():
        mutation_state = _begin_layer_mutation(layer)
        try:
            if left_sidebearing is not None:
                _set_sidebearing(layer, "leftSideBearing", "LSB", left_sidebearing)
            if right_sidebearing is not None:
                _set_sidebearing(layer, "rightSideBearing", "RSB", right_sidebearing)
            if width is not None:
                layer.width = width
            return True
        finally:
            _end_layer_mutation(layer, mutation_state)

    return bool(_run_on_main_thread(_mutate))


def _save_font_on_main_thread(font, requested_path=None):
    """Invoke font.save(...) on the Glyphs main thread via NSObject helper."""
    def _save():
        if requested_path:
            font.save(requested_path)
        else:
            font.save()
        return getattr(font, "filepath", None) or requested_path

    return _run_on_main_thread(_save)


def _open_tab_on_main_thread(font, tab_text):
    """Open a new edit tab safely on the Glyphs main thread."""
    return _run_on_main_thread(lambda: font.newTab(tab_text))


def _set_kerning_pairs_on_main_thread(font, master_id, pairs):
    """Apply multiple glyph–glyph kerning exceptions safely on the Glyphs main thread.

    pairs: iterable of (left_name, right_name, value_int)
    """

    def _apply_pairs(target_font, target_pairs):
        if master_id not in target_font.kerning:
            target_font.kerning[master_id] = {}

        master_kerning = target_font.kerning[master_id]
        for left_name, right_name, value in target_pairs:
            if left_name not in master_kerning:
                master_kerning[left_name] = {}

            if int(value) == 0:
                if right_name in master_kerning[left_name]:
                    del master_kerning[left_name][right_name]
                if not master_kerning[left_name]:
                    del master_kerning[left_name]
            else:
                master_kerning[left_name][right_name] = int(value)

    _run_on_main_thread(lambda: _apply_pairs(font, list(pairs or [])))


def _glyph_unicode_char(glyph):
    """Return the single-character Unicode string for a glyph, if available."""
    uni = getattr(glyph, "unicode", None)
    if not uni:
        return None
    try:
        return chr(int(str(uni), 16))
    except Exception:
        return None


def _load_andre_fuchs_relevant_pairs():
    """Load the bundled Andre Fuchs relevant-pairs dataset.

    Returns (dataset_meta, pairs, warnings) where pairs is a list of (left_char, right_char).
    """
    warnings = []
    dataset_path = (
        Path(__file__).resolve().parent
        / "kerning_data"
        / "andre_fuchs"
        / "relevant_pairs.v1.json"
    )

    if not dataset_path.exists():
        warnings.append("Andre-Fuchs dataset not found at {}".format(dataset_path))
        return (
            {"id": "andre_fuchs_relevant_pairs", "pairCount": 0},
            [],
            warnings,
        )

    try:
        raw = json.loads(dataset_path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        warnings.append("Failed to parse Andre-Fuchs dataset: {}".format(exc))
        return (
            {"id": "andre_fuchs_relevant_pairs", "pairCount": 0},
            [],
            warnings,
        )

    dataset_id = raw.get("id") if isinstance(raw, dict) else None
    if not isinstance(dataset_id, str) or not dataset_id.strip():
        dataset_id = "andre_fuchs_relevant_pairs"

    pairs = []
    raw_pairs = raw.get("pairs") if isinstance(raw, dict) else None
    if not isinstance(raw_pairs, list):
        warnings.append("Andre-Fuchs dataset has no 'pairs' list.")
        raw_pairs = []

    for item in raw_pairs:
        if not isinstance(item, dict):
            continue
        left = item.get("left")
        right = item.get("right")
        if not isinstance(left, str) or not isinstance(right, str):
            continue
        left = left.strip()
        right = right.strip()
        if len(left) != 1 or len(right) != 1:
            continue
        pairs.append((left, right))

    meta = {"id": dataset_id, "pairCount": len(pairs)}
    if len(pairs) < 200:
        warnings.append(
            "Andre-Fuchs dataset snapshot is small ({} pairs). Run vendor_andre_fuchs_pairs.py to update.".format(
                len(pairs)
            )
        )
    return meta, pairs, warnings


def _selected_glyph_names_for_font(font):
    if not font:
        return []
    try:
        layers = list(font.selectedLayers or [])
    except Exception:
        layers = []
    names = []
    for layer in layers:
        try:
            g = layer.parent
            if g and g.name:
                names.append(g.name)
        except Exception:
            continue
    # stable unique
    out = []
    seen = set()
    for n in names:
        if n in seen:
            continue
        seen.add(n)
        out.append(n)
    return out


# Backwards-compatible name for call sites that originally lived in spacing tools.
_spacing_selected_glyph_names_for_font = _selected_glyph_names_for_font


__all__ = [
    "_clear_layer_paths",
    "_coerce_numeric",
    "_component_transform_values",
    "_custom_parameter",
    "_delete_font_glyph",
    "_get_component_automatic",
    "_get_layer_id",
    "_get_left_sidebearing",
    "_get_right_sidebearing",
    "_glyphs_show_glyphs_link_fields",
    "_glyphs_show_glyphs_url",
    "_glyphs_show_bridge_url",
    "_glyphs_show_layer_link_fields",
    "_glyphs_show_link_fields",
    "_glyphs_show_url",
    "_glyph_unicode_char",
    "_is_style_set_tag",
    "_layer_components",
    "_load_andre_fuchs_relevant_pairs",
    "_parse_style_set_substitutions",
    "_selected_glyph_names_for_font",
    "_spacing_selected_glyph_names_for_font",
    "_open_tab_on_main_thread",
    "_replace_layer_paths_and_metrics",
    "_round_half_away_from_zero",
    "_run_on_main_thread",
    "_safe_attr",
    "_safe_json",
    "_sanitize_for_json",
    "_save_font_on_main_thread",
    "_set_kerning_pairs_on_main_thread",
    "_set_layer_metrics",
    "_set_sidebearing",
    "_show_notification",
    "_style_set_name_from_metadata",
    "_units_int",
]
