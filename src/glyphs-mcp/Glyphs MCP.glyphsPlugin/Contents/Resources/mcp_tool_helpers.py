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
    from Foundation import NSObject  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - PyObjC should be available inside Glyphs
    objc = None
    NSObject = None


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
    value = None
    try:
        value = getattr(layer, attr_name, None)
    except Exception:
        value = None

    value = _coerce_numeric(value)

    if value is None:
        fallback = getattr(layer, legacy_attr, None)
        value = _coerce_numeric(fallback)

    return value


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


def _save_font_on_main_thread(font, requested_path=None):
    """Invoke font.save(...) on the Glyphs main thread via NSObject helper."""
    if objc is None or NSObject is None:
        if requested_path:
            font.save(requested_path)
            return requested_path
        font.save()
        return getattr(font, "filepath", None)

    class _FontSaveHelper(NSObject):  # type: ignore[misc,valid-type]
        def init(self):
            self = objc.super(_FontSaveHelper, self).init()
            if self is None:
                return None
            self._font = font
            self._path = requested_path
            self.error = None
            self.saved_path = None
            return self

        def saveFont_(self, _obj):
            try:
                if self._path:
                    self._font.save(self._path)
                else:
                    self._font.save()
                self.saved_path = getattr(self._font, "filepath", None) or self._path
            except Exception as exc:  # pragma: no cover - bubbled to caller
                self.error = exc

    helper = _FontSaveHelper.alloc().init()
    helper.performSelectorOnMainThread_withObject_waitUntilDone_("saveFont:", None, True)

    if getattr(helper, "error", None) is not None:
        raise helper.error

    return getattr(helper, "saved_path", None) or getattr(font, "filepath", None) or requested_path


def _open_tab_on_main_thread(font, tab_text):
    """Open a new edit tab safely on the Glyphs main thread."""
    if objc is None or NSObject is None:
        return font.newTab(tab_text)

    class _FontTabHelper(NSObject):  # type: ignore[misc,valid-type]
        def init(self):
            self = objc.super(_FontTabHelper, self).init()
            if self is None:
                return None
            self._font = font
            self._text = tab_text
            self.error = None
            self.tab = None
            return self

        def openTab_(self, _obj):
            try:
                self.tab = self._font.newTab(self._text)
            except Exception as exc:  # pragma: no cover - bubbled to caller
                self.error = exc

    helper = _FontTabHelper.alloc().init()
    helper.performSelectorOnMainThread_withObject_waitUntilDone_("openTab:", None, True)

    if getattr(helper, "error", None) is not None:
        raise helper.error

    return getattr(helper, "tab", None)


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
            else:
                master_kerning[left_name][right_name] = int(value)

    if objc is None or NSObject is None:
        _apply_pairs(font, pairs)
        return

    class _KerningApplyHelper(NSObject):  # type: ignore[misc,valid-type]
        def init(self):
            self = objc.super(_KerningApplyHelper, self).init()
            if self is None:
                return None
            self._font = font
            self._master_id = master_id
            self._pairs = list(pairs or [])
            self.error = None
            return self

        def applyKerning_(self, _obj):
            try:
                _apply_pairs(self._font, self._pairs)
            except Exception as exc:  # pragma: no cover - bubbled to caller
                self.error = exc

    helper = _KerningApplyHelper.alloc().init()
    helper.performSelectorOnMainThread_withObject_waitUntilDone_("applyKerning:", None, True)

    if getattr(helper, "error", None) is not None:
        raise helper.error


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
    "_custom_parameter",
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
    "_load_andre_fuchs_relevant_pairs",
    "_parse_style_set_substitutions",
    "_selected_glyph_names_for_font",
    "_spacing_selected_glyph_names_for_font",
    "_open_tab_on_main_thread",
    "_round_half_away_from_zero",
    "_safe_attr",
    "_safe_json",
    "_sanitize_for_json",
    "_save_font_on_main_thread",
    "_set_kerning_pairs_on_main_thread",
    "_set_sidebearing",
    "_style_set_name_from_metadata",
    "_units_int",
]
