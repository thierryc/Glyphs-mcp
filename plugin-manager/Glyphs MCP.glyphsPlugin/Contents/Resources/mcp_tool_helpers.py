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
    return summary


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


def _replace_layer_paths_unmanaged(layer, new_paths):
    new_paths = list(new_paths or [])

    try:
        shapes = getattr(layer, "shapes", None)
    except Exception:
        shapes = None

    if shapes is not None:
        preserved = [shape for shape in _sequence_values(shapes) if not _is_path_shape(shape)]
        if _set_layer_shapes(layer, preserved + new_paths):
            summary = _layer_path_summary(layer)
            if summary["pathCount"] == len(new_paths):
                return {"ok": True, **summary}

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
