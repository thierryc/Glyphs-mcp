"""Explicit contour correspondence outside Glyphs; native cyclic reordering."""

import json
from .correspondence import MAX_NODE_COUNT, plan_joint_alignment
from .spacing import exact_copy, lookup
from .spacing_job import layer_hash
from .worker import WorkerError


def _fail(code, action, **target):
    location = {k: v if isinstance(v, int) else str(v)[:160] for k, v in target.items()}
    raise WorkerError("start_nodes." + code + ": " + json.dumps(location, ensure_ascii=False) + ". " + action)


def _validate_contour(nodes, closed, **target):
    if not closed:
        _fail("open_path", "Choose a closed contour; review open paths manually in Glyphs.", **target)
    if not 1 <= len(nodes) <= MAX_NODE_COUNT:
        _fail("invalid_node_count", "Choose a contour with 1-4096 nodes.", **target)
    if nodes[-1]["type"] == "offcurve":
        _fail("unsupported_native_boundary", "The native contour must end on-curve; inspect its start in Glyphs.", node=len(nodes)-1, **target)
    # The native last node is on-curve. Count controls from there through the
    # cyclic boundary, including contours beginning with off-curve nodes.
    controls = 0
    for index, node in enumerate(nodes):
        kind = node["type"]
        if kind not in ("line", "curve", "offcurve"):
            _fail("unsupported_node_type", "Only native line/cubic segments are verified; inspect this node in Glyphs.", node=index, **target)
        if kind == "offcurve":
            controls += 1
            continue
        if controls != (2 if kind == "curve" else 0):
            _fail("malformed_segment", "Inspect this segment in Glyphs: a cubic endpoint needs two incoming controls; a line needs none. Correct its node types before retrying.", node=index, **target)
        controls = 0


def validate_options(raw):
    defaults = {"masters": [], "referenceMaster": None, "referenceNode": None, "path": 0}
    if not isinstance(raw, dict) or set(raw) - set(defaults):
        raise ValueError("unknown start-node options")
    options = {**defaults, **raw}
    ids = options["masters"]
    if not isinstance(ids, list) or len(ids) > 32 or any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("masters must contain unique master IDs (maximum 32)")
    if options["referenceMaster"] is not None and (not isinstance(options["referenceMaster"], str) or not options["referenceMaster"]):
        raise ValueError("referenceMaster must be a master ID")
    for key, high in (("referenceNode", 4095), ("path", 255)):
        v = options[key]
        if key == "referenceNode" and v is None:
            continue
        if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= high:
            raise ValueError(key + " must be a bounded non-negative index")
    return options


def prepare(font, request):
    try:
        options = validate_options(request.get("options", {}))
    except ValueError as error:
        _fail("invalid_options", str(error))
    names = request.get("glyphs") or []
    if not 1 <= len(names) <= 100:
        _fail("invalid_glyph_count", "Select 1-100 explicit glyph names.")
    masters = [str(m.id) for m in font.masters if not options["masters"] or str(m.id) in options["masters"]]
    if not 2 <= len(masters) <= 32 or options["masters"] and set(masters) != set(options["masters"]):
        missing = next((mid for mid in options["masters"] if mid not in masters), "")
        _fail("invalid_master_ids", "Select 2-32 existing master IDs in this font; keep its document ID.", master=missing)
    reference = options["referenceMaster"] or masters[0]
    changes, rows = [], []
    for name in names:
        glyph = lookup(font.glyphs, name)
        if glyph is None:
            _fail("missing_glyph", "Correct the glyph name; keep this document ID and do not substitute another font.", glyph=name)
        layers = [lookup(glyph.layers, mid) for mid in masters]
        if any(layer is None for layer in layers) or len({len(layer.paths) for layer in layers}) != 1:
            _fail("path_topology_mismatch", "Compare the selected master layers and contour counts in Glyphs; repair structure manually.", glyph=name, path=options["path"])
        snapshots = []
        for mid, layer in zip(masters, layers):
            paths = list(layer.paths)
            if options["path"] >= len(paths):
                _fail("missing_path", "Choose an existing zero-based index in layer.paths, excluding components.", glyph=name, layer=mid, path=options["path"])
            path = paths[options["path"]]
            nodes = [{"x": float(n.position.x), "y": float(n.position.y), "type": str(n.type), "smooth": bool(n.smooth)} for n in path.nodes]
            _validate_contour(nodes, bool(path.closed), glyph=name, layer=mid, path=options["path"])
            snapshots.append({"masterId": mid, "closed": bool(path.closed), "direction": int(path.direction), "nodes": nodes})
        reference_path = next((p for p in snapshots if p["masterId"] == reference), None)
        if reference_path is None:
            _fail("reference_master_not_found", "Choose a reference master from the selected masters.", glyph=name, master=reference)
        reference_node = options["referenceNode"] if options["referenceNode"] is not None else len(reference_path["nodes"]) - 1
        plan = plan_joint_alignment(snapshots, reference_master_id=reference, reference_node_index=reference_node)
        if not plan["ok"]:
            code = plan["errorType"]
            action = ("Choose an existing on-curve referenceNode index (off-curves count in indexing)." if code.startswith("reference_node_") else
                      "Review contour direction in Glyphs; normalize separately, then reinspect." if code == "contour_direction_mismatch" else
                      "Compare this contour in the selected master layers in Glyphs; review ambiguous landmarks or structural differences manually.")
            _fail(code, action, glyph=name, path=options["path"], referenceMaster=reference)
        by_master = {m["masterId"]: m for m in plan["masters"]}
        for mid, layer in zip(masters, layers):
            item = by_master[mid]; shift = item["rotationOffset"]
            row = {"glyph": name, "layer": mid, "path": options["path"], "referenceMaster": reference,
                   "referenceNode": reference_node, "landmarkNode": item["proposedStartNodeIndex"],
                   "shift": shift, "status": "suggested" if shift else "unchanged"}
            if shift:
                candidate = exact_copy(layer)
                path = candidate.paths[options["path"]]
                path.makeNodeFirst_(path.nodes[shift - 1])
                changes.append({"kind": "start_node", "glyph": name, "layer": mid, "path": options["path"],
                                "shift": shift, "nodeCount": item["nodeCount"],
                                "beforeHash": layer_hash(layer), "afterHash": layer_hash(candidate)})
            rows.append(row)
    return changes, {"kind": "start_nodes", "layers": rows,
                    "claim": "Correspondence for supported unambiguous contours; reference phase retained, no arbitrary compatibility repair."}
