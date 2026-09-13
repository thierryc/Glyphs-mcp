"""Native reordering of one explicit closed contour."""


def apply(layer, change, *, reverse=False):
    paths = list(layer.paths)
    if change["path"] >= len(paths):
        raise ValueError("start-node contour is unavailable")
    path = paths[change["path"]]
    nodes = list(path.nodes)
    if not path.closed or len(nodes) != change["nodeCount"]:
        raise ValueError("start-node contour topology changed")
    shift = (-change["shift"] if reverse else change["shift"]) % len(nodes)
    node = nodes[(shift - 1) % len(nodes)]
    if str(node.type) == "offcurve":
        raise ValueError("native start node must be on-curve")
    path.makeNodeFirst_(node)
