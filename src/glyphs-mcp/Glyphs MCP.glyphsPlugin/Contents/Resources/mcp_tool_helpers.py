# encoding: utf-8

from __future__ import division, print_function, unicode_literals

"""Shared helpers for Glyphs MCP tools.

This module intentionally does not import GlyphsApp so it can be unit-tested in
normal Python environments.
"""

import json
import math
from pathlib import Path

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

    if objc is None or NSObject is None:
        for left_name, right_name, value in pairs:
            font.setKerningForPair(master_id, left_name, right_name, int(value))
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
                for left_name, right_name, value in self._pairs:
                    self._font.setKerningForPair(self._master_id, left_name, right_name, int(value))
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
    "_get_left_sidebearing",
    "_get_right_sidebearing",
    "_glyph_unicode_char",
    "_load_andre_fuchs_relevant_pairs",
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
    "_units_int",
]
