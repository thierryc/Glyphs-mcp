"""Font-unit comparisons for proposals and display, never exact restoration."""
from math import isclose

GEOMETRY_TOLERANCE = 0.001
MAX_PATH_ELEMENTS = 8192


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
        size = {0: 1, 1: 1, 2: 3, 3: 0}[int(kind)]
        result.append([int(kind), [[float(point.x), float(point.y)] for point in points[:size]]])
    return result


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
    old = segments(reference_outline) + segments(reference_open)
    new = segments(current_outline) + segments(current_open)
    closed_changed = not same_geometry(reference_outline, current_outline)
    changed = closed_changed or not same_geometry(reference_open, current_open)
    old_changed = [value for index, value in enumerate(old)
                   if index >= len(new) or not same_geometry(value, new[index])]
    new_changed = [value for index, value in enumerate(new)
                   if index >= len(old) or not same_geometry(value, old[index])]
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
