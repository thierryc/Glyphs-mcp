"""Font-unit comparisons for proposals and display, never exact restoration."""
from collections import Counter, defaultdict
from itertools import product
from math import floor, isclose

GEOMETRY_TOLERANCE = 0.001
MAX_PATH_ELEMENTS = 8192
GLYPH_DIFF_SCHEMA_VERSION = 3
GLYPH_DIFF_PROTOCOL_API_VERSION = 1
GLYPH_DIFF_WORKER_MODULE = "glyphs_mcp_sidecar.glyph_diff_worker"


def path_elements(path):
    """Serialize an NSBezierPath without retaining any editable Glyphs objects."""
    if path is None:
        return []
    count = path.elementCount()
    if count > MAX_PATH_ELEMENTS:
        raise ValueError("The glyph layer exceeds the visual diff display limit")
    result = []
    for index in range(count):
        kind, points = path.elementAtIndex_associatedPoints_(index)
        sizes = {0: 1, 1: 1, 2: 3, 3: 0, 4: 2}
        if int(kind) not in sizes:
            raise ValueError("Unsupported native path element kind {}".format(int(kind)))
        size = sizes[int(kind)]
        if len(points) < size:
            raise ValueError(
                "Native path element kind {} returned {} point(s); expected {}"
                .format(int(kind), len(points), size)
            )
        result.append([int(kind), [[float(point.x), float(point.y)] for point in points[:size]]])
    return result


def _value(obj, name, default=None):
    try:
        value = getattr(obj, name)
        return value() if callable(value) else value
    except Exception:
        return default


def _point(value):
    try:
        return [float(value.x), float(value.y)]
    except Exception as error:
        raise ValueError("Glyphs returned an invalid path point") from error


def _segment_type(segment):
    value = str(_value(segment, "type", "")).lower()
    if value.endswith("qcurve") or value == "qcurve":
        return "qcurve"
    if value.endswith("curve") or value == "curve":
        return "curve"
    if value.endswith("line") or value == "line":
        return "line"
    return value


def _segment_points(segment):
    """Read GSPathSegment points without relying on its unbounded iterator."""
    try:
        count = int(_value(segment, "countOfPoints"))
    except (AttributeError, TypeError, ValueError):
        return list(segment)
    return [segment[index] for index in range(count)]


def glyphs_path_elements(paths, context="glyph layer"):
    """Serialize copied GSPaths, including TrueType quadratic implied points."""
    result = []
    try:
        paths = list(paths or [])
    except Exception as error:
        raise ValueError("{} paths are unavailable".format(context)) from error
    for path_index, path in enumerate(paths):
        try:
            native_segments = list(_value(path, "segments", []) or [])
        except Exception as error:
            raise ValueError("{} path {} segments are unavailable".format(context, path_index)) from error
        if not native_segments:
            continue
        try:
            first_points = _segment_points(native_segments[0])
        except Exception as error:
            raise ValueError("{} path {} has an invalid first segment".format(context, path_index)) from error
        if len(first_points) < 2:
            raise ValueError("{} path {} has a segment with fewer than two points".format(context, path_index))
        result.append([0, [_point(first_points[0])]])
        for segment_index, segment in enumerate(native_segments):
            try:
                points = [_point(value) for value in _segment_points(segment)]
            except Exception as error:
                raise ValueError(
                    "{} path {} segment {} is invalid".format(context, path_index, segment_index)
                ) from error
            kind = _segment_type(segment)
            if kind == "line":
                if len(points) < 2:
                    raise ValueError("{} line segment is missing its endpoint".format(context))
                result.append([1, [points[-1]]])
            elif kind == "curve":
                if len(points) != 4:
                    raise ValueError("{} cubic segment has {} points; expected 4".format(context, len(points)))
                result.append([2, points[1:]])
            elif kind == "qcurve":
                if len(points) < 3:
                    raise ValueError("{} quadratic segment has {} points; expected at least 3".format(context, len(points)))
                controls, endpoint = points[1:-1], points[-1]
                for index, control in enumerate(controls):
                    target = endpoint if index + 1 == len(controls) else [
                        (control[0] + controls[index + 1][0]) / 2,
                        (control[1] + controls[index + 1][1]) / 2,
                    ]
                    result.append([4, [control, target]])
            else:
                raise ValueError(
                    "{} path {} uses unsupported segment type {!r}"
                    .format(context, path_index, kind or _value(segment, "type", None))
                )
            if len(result) > MAX_PATH_ELEMENTS:
                raise ValueError("The glyph layer exceeds the visual diff display limit")
        if bool(_value(path, "closed", False)):
            result.append([3, []])
            if len(result) > MAX_PATH_ELEMENTS:
                raise ValueError("The glyph layer exceeds the visual diff display limit")
    return result


def resolved_closed_layer_elements(layer, context="glyph layer"):
    """Resolve visible closed geometry without mutating a live layer."""
    try:
        closed_layer = layer.copy()
        closed_layer.flattenOutlines()
    except Exception as error:
        raise ValueError("{} outlines could not be flattened safely".format(context)) from error
    closed_paths = [path for path in list(_value(closed_layer, "paths", []) or [])
                    if bool(_value(path, "closed", False))]
    return glyphs_path_elements(closed_paths, context="{} closed outline".format(context))


def resolved_open_layer_elements(layer, context="glyph layer"):
    """Resolve open geometry without mutating a live layer."""
    try:
        decomposed_layer = layer.copyDecomposedLayer()
    except Exception as error:
        raise ValueError("{} open outlines could not be decomposed safely".format(context)) from error
    open_paths = [path for path in list(_value(decomposed_layer, "paths", []) or [])
                  if not bool(_value(path, "closed", False))]
    return glyphs_path_elements(open_paths, context="{} open outline".format(context))


def resolved_layer_elements(layer, context="glyph layer"):
    """Resolve visible closed geometry and preserve open paths without mutating a live layer."""
    return (
        resolved_closed_layer_elements(layer, context=context),
        resolved_open_layer_elements(layer, context=context),
    )


def component_path_elements(component, context="component"):
    """Serialize one transformed component as a single Non-Zero outline."""
    try:
        paths = component.decomposedPathsRemovingOverlap_(False)
    except Exception as error:
        raise ValueError("{} could not be decomposed safely".format(context)) from error
    closed = [path for path in list(paths or []) if bool(_value(path, "closed", False))]
    return glyphs_path_elements(closed, context=context)


def same_font_units(left, right):
    return isclose(left, right, rel_tol=0, abs_tol=GEOMETRY_TOLERANCE)


def same_geometry(left, right):
    """Compare nested geometry with the display-only font-unit tolerance."""
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return same_font_units(left, right)
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            same_geometry(left[key], right[key]) for key in left
        )
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(
            same_geometry(a, b) for a, b in zip(left, right)
        )
    return left == right


def _element(value):
    if isinstance(value, dict):
        return int(value["kind"]), value.get("points", [])
    return int(value[0]), value[1]


def normalized_elements(elements):
    return [[kind, points] for kind, points in (_element(value) for value in elements)]


def segments(elements):
    """Convert path elements into independently drawable line/curve segments."""
    result, start, cursor = [], None, None
    for kind, points in (_element(value) for value in elements):
        if kind == 0:
            start = cursor = points[0]
        elif kind == 3:
            if cursor is not None and start is not None:
                result.append([1, [cursor, start]])
                cursor = start
        elif cursor is not None:
            result.append([kind, [cursor, *points]])
            cursor = points[-1]
    return result


def _segment_key(segment):
    """Return an exact, direction-independent key for one visual segment."""
    kind, points = _element(segment)
    exact = tuple(tuple(float(value) for value in point[:2]) for point in points)
    if kind == 2 and len(exact) == 4:
        reverse = (exact[3], exact[2], exact[1], exact[0])
    elif kind == 4 and len(exact) == 3:
        reverse = (exact[2], exact[1], exact[0])
    else:
        reverse = tuple(reversed(exact))
    return kind, min(exact, reverse)


def _same_segment(left, right):
    left_kind, left_points = _element(left)
    right_kind, right_points = _element(right)
    return left_kind == right_kind and (
        same_geometry(left_points, right_points)
        or same_geometry(left_points, list(reversed(right_points)))
    )


def _segment_bucket(segment):
    kind, points = _element(segment)
    xs, ys = [point[0] for point in points], [point[1] for point in points]
    return (kind, len(points), *(floor(value / GEOMETRY_TOLERANCE) for value in
        (min(xs), min(ys), max(xs), max(ys))))


def _unmatched_segments(source, other):
    """Match exact segments first, then apply tolerance only near spatial peers."""
    shared = Counter(_segment_key(value) for value in source) & Counter(
        _segment_key(value) for value in other
    )
    source_quota, other_quota = shared.copy(), shared.copy()
    pending_source, pending_other = [], []
    for value in source:
        key = _segment_key(value)
        if source_quota[key]:
            source_quota[key] -= 1
        else:
            pending_source.append(value)
    for value in other:
        key = _segment_key(value)
        if other_quota[key]:
            other_quota[key] -= 1
        else:
            pending_other.append(value)

    buckets = defaultdict(list)
    for value in pending_other:
        buckets[_segment_bucket(value)].append(value)
    result = []
    for value in pending_source:
        base = _segment_bucket(value)
        matched = False
        for offsets in product((-1, 0, 1), repeat=4):
            key = (*base[:2], *(base[index + 2] + offsets[index] for index in range(4)))
            candidates = buckets.get(key, [])
            for index, candidate in enumerate(candidates):
                if _same_segment(value, candidate):
                    candidates.pop(index)
                    matched = True
                    break
            if matched:
                break
        if not matched:
            result.append(value)
    return result


def _padded_bounds(points, padding=24.0):
    if not points:
        return None
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    return [min(xs) - padding, min(ys) - padding,
            max(xs) - min(xs) + padding * 2,
            max(ys) - min(ys) + padding * 2]


def _intersects(left, right):
    return not (
        left[0] + left[2] < right[0] or right[0] + right[2] < left[0]
        or left[1] + left[3] < right[1] or right[1] + right[3] < left[1]
    )


def _union(left, right):
    min_x, min_y = min(left[0], right[0]), min(left[1], right[1])
    max_x = max(left[0] + left[2], right[0] + right[2])
    max_y = max(left[1] + left[3], right[1] + right[3])
    return [min_x, min_y, max_x - min_x, max_y - min_y]


def _merge_regions(regions):
    merged = []
    for region in regions:
        candidate = region
        index = 0
        while index < len(merged):
            if _intersects(candidate, merged[index]):
                candidate = _union(candidate, merged.pop(index))
                index = 0
            else:
                index += 1
        merged.append(candidate)
    return merged


def difference_regions(plan):
    """Return stable, localized focus regions for visible geometry changes."""
    geometry = []
    for segment in plan["referenceSegments"] + plan["currentSegments"]:
        bounds = _padded_bounds(segment[1])
        if bounds is not None:
            geometry.append(bounds)
    regions = [{"kind": "geometry", "bounds": bounds}
               for bounds in _merge_regions(geometry)]
    for anchor in plan["anchors"]:
        points = [point for point in (anchor["before"], anchor["after"])
                  if point is not None]
        bounds = _padded_bounds(points)
        if bounds is not None:
            regions.append({"kind": "anchor", "bounds": bounds})
    if plan["width"] is not None:
        widths = [value for value in plan["width"] if value is not None]
        if widths:
            bottom, top = plan["metricRange"]
            bounds = _padded_bounds([[min(widths), bottom], [max(widths), top]])
            regions.append({"kind": "width", "bounds": bounds})
    regions.sort(key=lambda value: (
        -(value["bounds"][1] + value["bounds"][3]), value["bounds"][0], value["kind"]
    ))
    return [dict(value, id="difference-{}".format(index + 1))
            for index, value in enumerate(regions)]


def comparison(reference, current):
    """Prepare the same difference model used by the native Reference Inspector."""
    reference_outline = normalized_elements(reference.get("outline", []))
    reference_open = normalized_elements(reference.get("openOutline", []))
    current_outline = normalized_elements(current.get("outline", []))
    current_open = normalized_elements(current.get("openOutline", []))
    old_closed, new_closed = segments(reference_outline), segments(current_outline)
    old_open, new_open = segments(reference_open), segments(current_open)
    old, new = old_closed + old_open, new_closed + new_open
    old_changed = _unmatched_segments(old, new)
    new_changed = _unmatched_segments(new, old)
    closed_changed = bool(
        _unmatched_segments(old_closed, new_closed)
        or _unmatched_segments(new_closed, old_closed)
    )
    changed = bool(old_changed or new_changed)
    anchors = []
    for name in sorted(set(reference.get("anchors", {})) | set(current.get("anchors", {}))):
        before = reference.get("anchors", {}).get(name)
        after = current.get("anchors", {}).get(name)
        if not same_geometry(before, after):
            anchors.append({"name": name, "before": before, "after": after})
    before_width, after_width = reference.get("width"), current.get("width")
    ys = [point[1] for segment in old + new for point in segment[1]]
    plan = {
        "outlineChanged": changed,
        "referenceSegments": old_changed,
        "currentSegments": new_changed,
        "referenceOutline": reference_outline if closed_changed else [],
        "currentOutline": current_outline if closed_changed else [],
        "metricRange": [min(ys, default=0) - 80, max(ys, default=820) + 80],
        "anchors": anchors,
        "width": None if same_geometry(before_width, after_width) else [before_width, after_width],
    }
    plan["regions"] = difference_regions(plan)
    plan["hasVisibleDifference"] = bool(
        changed or anchors or plan["width"] is not None
    )
    return plan
