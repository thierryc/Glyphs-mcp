"""Plain geometry exchanged with the external reference reader."""

from glyphs_mcp_protocol.geometry import same_font_units


MAX_ELEMENTS = 8192


def path_elements(path):
    if path is None:
        return []
    count = path.elementCount()
    if count > MAX_ELEMENTS:
        raise ValueError("The visible layer exceeds the reference display limit")
    result = []
    for index in range(count):
        kind, points = path.elementAtIndex_associatedPoints_(index)
        size = {0: 1, 1: 1, 2: 3, 3: 0}[int(kind)]
        result.append([int(kind), [[float(p.x), float(p.y)] for p in points[:size]]])
    return result


def same_geometry(left, right):
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return same_font_units(left, right)
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(same_geometry(a, b) for a, b in zip(left, right))
    return left == right


def segments(elements):
    result, start, cursor = [], None, None
    for kind, points in elements:
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


def comparison(reference, current):
    old = segments(reference.get("outline", [])) + segments(reference.get("openOutline", []))
    new = segments(current.get("outline", [])) + segments(current.get("openOutline", []))
    closed_changed = not same_geometry(reference.get("outline", []), current.get("outline", []))
    changed = closed_changed or not same_geometry(reference.get("openOutline", []), current.get("openOutline", []))
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
    return {"outlineChanged": changed, "referenceSegments": old_changed, "currentSegments": new_changed,
            "referenceOutline": reference.get("outline", []) if closed_changed else [],
            "currentOutline": current.get("outline", []) if closed_changed else [],
            "metricRange": [min(ys, default=0)-80, max(ys, default=820)+80],
            "anchors": anchors,
            "width": None if same_geometry(before_width, after_width) else [before_width, after_width]}
