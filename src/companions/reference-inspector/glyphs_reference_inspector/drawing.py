"""Prepare Cocoa paths once; Reporter callbacks only paint the published plan."""

from AppKit import NSBezierPath, NSColor, NSEvenOddWindingRule, NSMakeRect, NSPoint


SAVED_RGBA = (63 / 255, 226 / 255, 166 / 255, .78)
DIFFERENCE_RGBA = (63 / 255, 209 / 255, 226 / 255, .26)


def append_elements(path, elements):
    for kind, points in elements:
        if kind == 0:
            path.moveToPoint_(NSPoint(*points[0]))
        elif kind == 1:
            path.lineToPoint_(NSPoint(*points[0]))
        elif kind == 2:
            path.curveToPoint_controlPoint1_controlPoint2_(NSPoint(*points[2]), NSPoint(*points[0]), NSPoint(*points[1]))
        else:
            path.closePath()


def prepare(plan):
    difference = NSBezierPath.bezierPath()
    append_elements(difference, plan["referenceOutline"])
    append_elements(difference, plan["currentOutline"])
    difference.setWindingRule_(NSEvenOddWindingRule)
    saved = segment_path(plan["referenceSegments"])
    current = segment_path(plan["currentSegments"])
    for anchor in plan["anchors"]:
        before, after = anchor["before"], anchor["after"]
        if before is not None:
            saved.appendBezierPathWithOvalInRect_(NSMakeRect(before[0]-4, before[1]-4, 8, 8))
            if after is not None:
                saved.moveToPoint_(NSPoint(*before)); saved.lineToPoint_(NSPoint(*after))
        if after is not None:
            current.appendBezierPathWithOvalInRect_(NSMakeRect(after[0]-3, after[1]-3, 6, 6))
    metrics = NSBezierPath.bezierPath()
    if plan["width"] is not None:
        before, after = plan["width"]
        if before is not None and after is not None:
            bottom, top = plan["metricRange"]
            metrics.appendBezierPathWithRect_(NSMakeRect(min(before, after), bottom, abs(after-before), top-bottom))
            saved.moveToPoint_(NSPoint(before, bottom)); saved.lineToPoint_(NSPoint(before, top))
    return {"difference": difference, "saved": saved, "current": current, "metrics": metrics}


def segment_path(segments):
    path = NSBezierPath.bezierPath()
    for kind, points in segments:
        path.moveToPoint_(NSPoint(*points[0]))
        if kind == 1:
            path.lineToPoint_(NSPoint(*points[-1]))
        elif kind == 2:
            path.curveToPoint_controlPoint1_controlPoint2_(NSPoint(*points[3]), NSPoint(*points[1]), NSPoint(*points[2]))
    return path


def paint(paths, scale):
    NSColor.colorWithDeviceRed_green_blue_alpha_(*DIFFERENCE_RGBA).set()
    paths["difference"].fill()
    paths["metrics"].fill()
    NSColor.colorWithDeviceRed_green_blue_alpha_(*SAVED_RGBA).set()
    paths["saved"].setLineWidth_(1.2 / max(scale, .01))
    paths["saved"].stroke()
    NSColor.colorWithDeviceRed_green_blue_alpha_(63/255, 209/255, 226/255, .85).set()
    paths["current"].setLineWidth_(1.0 / max(scale, .01))
    paths["current"].stroke()
