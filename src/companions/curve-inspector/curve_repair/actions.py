"""Bounded native repair for the human panel; main-thread only.

Calculation stays detached. Commit uses exact native guards and per-glyph Undo.
The bound covers complete effective contours, not stored-node displacement.
No Save, interpolation/export claim or developer-checkout dependency.
"""
from dataclasses import dataclass, field
import math

from .geometry import RepairError, diagnose_join, certify_regular, add, sub, mul, dot, normalized, no_regression, check_pair, chain_deviation
from .joins import source_segments
from .native import value, identity, position, path_state, freeze, precision, effective, effective_chain
from .supertool import harmonize, balance


@dataclass
class Scope:
    font: object
    glyphs: tuple
    layer: object = None
    background: bool = False
    selection: tuple = ()
    description: str = ""


def resolve_scope(host, visible_layer, *, capture=True):
    font = value(host, "font")
    if font is None: raise RepairError("empty_scope", "Open a font first.")
    if value(font, "currentTab") is None:
        selected = value(font, "selection")
        if selected is None: raise RepairError("empty_scope", "Font selection is unavailable.")
        # UI notifications only need the count. Traverse the complete font
        # once when Apply captures its scope, never on refresh callbacks.
        glyphs = tuple(selected) or (tuple(font.glyphs) if capture else font.glyphs)
        return Scope(font, glyphs, description=("Selected glyphs" if selected else "Whole font") + " · " + str(len(glyphs)))
    layer = visible_layer(host)
    if layer is None: raise RepairError("empty_scope", "Place the cursor in a glyph first.")
    # Background.parent can be its foreground; bind through exact font ownership.
    parent = value(layer, "parent")
    glyph = value(parent, "parent") if hasattr(parent, "paths") else parent
    if glyph is None or not hasattr(glyph, "layers"):
        raise RepairError("empty_scope", "The active glyph is unavailable.")
    owner = next((l for l in glyph.layers if identity(l) == identity(layer)), None)
    background = False
    if owner is None:
        owner = next((l for l in glyph.layers if value(l, "hasBackground", False) and identity(l.background) == identity(layer)), None)
        background = True
    if owner is None or identity(value(glyph, "parent")) != identity(font):
        raise RepairError("stale", "The layer does not belong to the active font.")
    selected = tuple(value(layer, "selection", ()))
    text = str(glyph.name) + (" · selected outlines" if selected else " · whole glyph")
    if background: text += " · background"
    return Scope(font, (glyph,), owner, background, selected, text)


def topology(layer):
    return tuple((bool(p.closed), tuple(str(n.type) for n in p.nodes)) for p in layer.paths)


def selected_joins(path, selection, app):
    """Explicit on-curves, or both ends of a selected handle/segment/path.

    An off-curve denotes its complete segment. Adjacent corners are preserved
    unless the user selected the on-curve itself. Non-outline selections never
    expand into an empty-selection whole-glyph action.
    """
    edges = source_segments(path, app)
    incoming, outgoing = {e.end: e for e in edges}, {e.start: e for e in edges}
    selected = {identity(item) for item in selection}
    explicit = {i for i, n in enumerate(path.nodes) if n.type != app.OFFCURVE and identity(n) in selected}
    whole = not selection or identity(path) in selected
    candidates = set(range(len(path.nodes))) if whole else set(explicit)
    for e in edges:
        if any(identity(path.nodes[i]) in selected for i in e.indices[1:-1]):
            candidates.update((e.start, e.end))
        # Selecting both on-curves selects the connecting segment as well.
        if e.start in explicit and e.end in explicit: candidates.update((e.start, e.end))
    result, skipped = [], []
    for i in sorted(candidates):
        n = path.nodes[i]
        if n.type == app.OFFCURVE: continue
        if i not in explicit and int(n.connection) not in (app.GSSMOOTH, app.GSSUPERSMOOTH): continue
        left, right = incoming.get(i), outgoing.get(i)
        if left is None or right is None:
            if i in explicit: skipped.append((i, "Open endpoint"))
        elif left.kind == right.kind == "line":
            if i in explicit: skipped.append((i, "Two straight segments"))
        else: result.append(i)
    return tuple(result), skipped


def line_handles(left, right):
    """Fixed join, zero curvature: align both adjacent cubic handles to line."""
    line, curve = (left, right) if left.kind == "line" else (right, left)
    join = right.curve[0]
    direction = sub(line.curve[-1], line.curve[0])
    length2 = dot(direction, direction)
    if length2 <= 1e-20: raise RepairError("undefined_curvature", "Zero-length straight segment")
    result = list(curve.curve)
    for i in (1, 2):
        t = dot(sub(result[i], join), direction)/length2
        if (t <= 0 if left.kind == "line" else t >= 0):
            raise RepairError("opposite_tangents", "Curve handles point against the line")
        result[i] = add(join, mul(direction, t))
    return (left.curve, tuple(result)) if left.kind == "line" else (tuple(result), right.curve)


def nodes_state(path):
    return tuple((position(n), int(n.connection)) for n in path.nodes)


def write_nodes(path, states):
    if len(path.nodes) != len(states): raise RepairError("stale", "Node topology changed")
    for node, (point, connection) in zip(path.nodes, states):
        if position(node) != point: node.position = point
        if int(node.connection) != connection: node.setConnection_(connection)


def default_limit(font):
    return .001 * float(font.upm)


def validate_limit(number):
    try: number = float(number)
    except (TypeError, ValueError): raise RepairError("invalid_tolerance", "Max change must be a positive number")
    if not math.isfinite(number) or number <= 0:
        raise RepairError("invalid_tolerance", "Max change must be positive and finite")
    return number


def path_guard(glyph, owner, layer, path):
    font = glyph.parent
    return (identity(font), identity(glyph), identity(owner), identity(layer), identity(path),
            str(owner.layerId), str(value(owner, "associatedMasterId", "")),
            freeze(float(font.upm)), freeze(float(value(font, "gridLength", 0))),
            freeze(float(layer.width)), bool(value(glyph, "locked", False)),
            bool(value(owner, "locked", False)), bool(value(layer, "locked", False)),
            bool(value(layer, "temporarilyDisableRounding", False)),
            freeze(value(glyph, "attributes", {})), freeze(value(layer, "attributes", {})),
            tuple((identity(h), freeze(value(h, "type")), freeze(value(h, "name")),
                   freeze(value(h, "options")), identity(value(h, "originNode")),
                   identity(value(h, "targetNode"))) for h in value(layer, "hints", ())), path_state(path))


def trial_fonts(font):
    """One baseline and candidate copy per Apply; no blanket glyph-state gates."""
    before = font.copy()
    after = before.copy()
    return before, after


def trial_layer(copied, glyph, owner, background):
    cg = copied.glyphs[str(glyph.name)]
    cl = cg.layers[str(owner.layerId)] if cg is not None else None
    if cl is None: raise RepairError("native_unqualified", "Native copying lost a layer")
    if background:
        if not value(cl, "hasBackground", False): raise RepairError("native_unqualified", "Native copying lost a background")
        for key in ("layerId", "associatedMasterId"):
            if value(cl.background, key) is None and value(owner.background, key) is not None:
                setattr(cl.background, key, value(owner.background, key))
        cl = cl.background
    return cl


def construction(layer, path, app):
    with precision(layer, True): return effective_chain(path, app)


def diagnostics(chain, upm):
    incoming = {e.end: e for e in chain.edges}
    outgoing = {e.start: e for e in chain.edges}
    result = {}
    for i in incoming.keys() & outgoing.keys():
        if incoming[i].kind == outgoing[i].kind == "line": continue
        left, right = chain.join(i)
        try: result[i] = diagnose_join(normalized(left, upm, left[-1]), normalized(right, upm, left[-1]))
        except RepairError: result[i] = None
    return result


def outline_bound(before, after, upm, limit):
    if tuple((e.start, e.end, e.kind) for e in before.edges) != tuple((e.start, e.end, e.kind) for e in after.edges):
        raise RepairError("incompatible_correspondence", "Effective segment roles cannot be matched")
    if before.curves == after.curves: return 0.
    if tuple((i, len(g)) for i, g in before.groups) == tuple((i, len(g)) for i, g in after.groups):
        maximum = 0.
        for a, b in zip(before.curves, after.curves):
            if a == b: continue
            maximum = max(maximum, check_pair(a, b, upm, limit/upm)["upper"] * upm)
        return maximum
    return chain_deviation(before.curves, after.curves, upm, limit/upm)["upper"] * upm


def validate_candidate(before_layer, after_layer, before_path, after_path, requested, app, upm, limit):
    old = construction(before_layer, before_path, app)
    new = construction(after_layer, after_path, app)
    ds, dt = diagnostics(old, upm), diagnostics(new, upm)
    edges = source_segments(before_path, app)
    changed = {i for i, (a, b) in enumerate(zip(nodes_state(before_path), nodes_state(after_path))) if a != b}
    affected = {e.start for e in edges if changed.intersection(e.indices)} | {e.end for e in edges if changed.intersection(e.indices)}
    for i in requested:
        if dt.get(i) is None or not dt[i]["g2"]:
            raise RepairError("continuity_failed", "The repaired native join does not satisfy G2")
    # Expanded native segments must remain regular and tangent-continuous
    # internally; G2 at the requested source join alone does not prove that.
    touched_edges = {e.end for e in edges if e.start in requested or e.end in requested}
    for chain in (old, new):
        for end, group in chain.groups:
            if end not in touched_edges: continue
            for curve in group: certify_regular(normalized(curve, upm, curve[0]))
            for a, b in zip(group, group[1:]):
                if not diagnose_join(normalized(a, upm, a[-1]), normalized(b, upm, a[-1]))["g1"]:
                    raise RepairError("continuity_failed", "A generated native transition is not tangent-continuous")
    for i in affected-set(requested):
        if i not in ds or int(before_path.nodes[i].connection) == app.GSSHARP: continue
        if ds[i] is None or dt.get(i) is None or not no_regression(ds[i], dt[i]):
            raise RepairError("neighbor_regression", "A neighboring smooth join would regress")
    # Both construction and actual drawing must respect the limit. Precision
    # flags are restored before measuring the native drawing.
    upper = outline_bound(old, new, upm, limit)
    upper = max(upper, outline_bound(effective_chain(before_path, app), effective_chain(after_path, app), upm, limit))
    return upper


@dataclass
class PreparedPath:
    glyph: object
    owner: object
    layer: object
    path: object
    index: int
    guard: tuple
    before_nodes: tuple
    after_nodes: tuple
    expected: tuple
    baseline_layer: object
    baseline_path: object
    requested: tuple
    repaired: int
    converted: int
    already_smooth: int
    maximum: float
    notes: tuple = ()


def prepare_path(glyph, owner, layer, path, joins, app, method, max_change_units=None, *, trials=None, tunni_balance=True, seed=None):
    """Non-mutating calculation for one contour. All edits remain detached."""
    if method not in ("star", "default-node"): raise RepairError("unsupported_method")
    font = glyph.parent
    limit = validate_limit(default_limit(font) if max_change_units is None else max_change_units)
    if any(bool(value(x, "locked", False)) for x in (glyph, owner, layer, path)):
        raise RepairError("locked", "Locked outline")
    guard = path_guard(glyph, owner, layer, path)
    index = next((i for i, p in enumerate(layer.paths) if identity(p) == identity(path)), None)
    if index is None: raise RepairError("stale", "The path left its owning layer")
    background = identity(layer) != identity(owner)
    trials = trials or trial_fonts(font)
    before_layer, after_layer = (trial_layer(f, glyph, owner, background) for f in trials)
    before_path, after_path = before_layer.paths[index], after_layer.paths[index]
    if path_state(before_path) != path_state(path):
        raise RepairError("stale", "The detached baseline differs from the source")
    with precision(after_layer, True): write_nodes(after_path, seed.after_nodes if seed is not None else nodes_state(before_path))
    if effective_chain(before_path, app).curves != effective_chain(path, app).curves:
        raise RepairError("native_unqualified", "Native copying changed the effective outline")
    original = construction(before_layer, before_path, app)
    ds = diagnostics(original, float(font.upm))
    incoming, outgoing = {e.end: e for e in original.edges}, {e.start: e for e in original.edges}
    targets, repair, convert, healthy = [], 0, 0, 0
    for i in joins:
        is_star = int(path.nodes[i].connection) == app.GSSUPERSMOOTH
        if method == "star" and is_star:
            healthy += 1; continue
        if ds.get(i) is None: raise RepairError("undefined_curvature", "Curvature is undefined at a requested join")
        if ds[i]["g2"] and not is_star:
            healthy += 1; continue
        if is_star and method == "default-node": convert += 1
        else: repair += 1
        targets.append(i)
        affected = (i,) if method == "star" else (i, *incoming[i].indices[1:-1], *outgoing[i].indices[1:-1])
        if any(bool(value(path.nodes[j], "locked", False)) for j in affected):
            raise RepairError("locked", "Locked node or handle")
        if method == "default-node" and is_star and incoming[i].kind != outgoing[i].kind:
            raise RepairError("expanded_star", "Expanded raindrops cannot yet be converted to regular nodes")
    notes = list(seed.notes) if seed is not None else []
    if targets:
        if any(str(k).lower().startswith("stroke") for k in value(path, "attributes", {})):
            raise RepairError("coverage_incomplete", "Stroke expansion cannot be bounded for this contour")
        node_ids = {identity(n) for n in path.nodes}
        if any(bool(value(h, "isCorner", False)) and
               (value(h, "originNode") is None or identity(value(h, "originNode")) in node_ids)
               for h in value(layer, "hints", ())):
            raise RepairError("coverage_incomplete", "Corner/cap/brush expansion cannot be bounded for this contour")
    requested = tuple(sorted(set(targets) | set(seed.requested if seed is not None else ())))
    with precision(after_layer, True):
        for i in targets:
            if method == "star" or incoming[i].kind == outgoing[i].kind:
                after_path.nodes[i].setConnection_(app.GSSUPERSMOOTH)
        if method == "default-node":
            chain = effective_chain(after_path, app)
            groups = dict(chain.groups)
            updates = {}
            for i in targets:
                left, right = incoming[i], outgoing[i]
                if left.kind == right.kind:
                    a, b = groups[left.end], groups[right.end]
                    if len(a) != 1 or len(b) != 1:
                        raise RepairError("expanded_star", "An adjacent raindrop requires a topology change")
                    updates[i] = (a[0][-1], app.GSSMOOTH)
                    for j, point in zip(left.indices[1:-1], a[0][1:-1]): updates[j] = (point, int(before_path.nodes[j].connection))
                    for j, point in zip(right.indices[1:-1], b[0][1:-1]): updates[j] = (point, int(before_path.nodes[j].connection))
                else:
                    a, b = line_handles(left, right)
                    updates[i] = (position(before_path.nodes[i]), app.GSSMOOTH)
                    for edge, curve in ((left,a),(right,b)):
                        if edge.kind == "curve":
                            for j, point in zip(edge.indices[1:-1], curve[1:-1]): updates[j] = (point,int(before_path.nodes[j].connection))
            states = list(nodes_state(after_path))
            for i, state in updates.items(): states[i] = state
            write_nodes(after_path, states)
    upper = validate_candidate(before_layer, after_layer, before_path, after_path, requested, app, float(font.upm), limit) if requested else 0.
    base = nodes_state(after_path)
    if targets and method == "default-node" and tunni_balance:
        try:
            with precision(after_layer, True):
                raw = source_segments(after_path, app)
                li, ri = {e.end:e for e in raw}, {e.start:e for e in raw}
                curved = [i for i in targets if li[i].kind == ri[i].kind == "curve"]
                segments = {e.end:e for i in curved for e in (li[i],ri[i])}
                for edge in segments.values():
                    c = balance(edge.curve)
                    for j, point in zip(edge.indices[1:-1], c[1:-1]): after_path.nodes[j].position = point
                for i in curved:
                    raw = source_segments(after_path, app)
                    a = next(e for e in raw if e.end == i); b = next(e for e in raw if e.start == i)
                    ca, cb = harmonize(a.curve,b.curve)
                    after_path.nodes[a.indices[-2]].position = ca[2]
                    after_path.nodes[b.indices[1]].position = cb[1]
            upper = validate_candidate(before_layer, after_layer, before_path, after_path, requested, app, float(font.upm), limit)
        except RepairError as exc:
            with precision(after_layer, True): write_nodes(after_path, base)
            notes.append("Tunni omitted: " + str(exc))
            # The fallback is still measured, never exempted from the limit.
            upper = validate_candidate(before_layer, after_layer, before_path, after_path, requested, app, float(font.upm), limit)
    return PreparedPath(glyph, owner, layer, path, index, guard, nodes_state(path), nodes_state(after_path),
                        path_state(after_path), before_layer, before_path, requested, repair+(seed.repaired if seed else 0), convert+(seed.converted if seed else 0),
                        healthy+(seed.already_smooth if seed else 0), upper, tuple(notes))


def commit_paths(prepared, app, limit):
    """All layers in this corresponding contour transaction, or compensation."""
    changed = [p for p in prepared if p.before_nodes != p.after_nodes]
    if not changed: return
    for p in changed:
        if identity(p.layer.paths[p.index]) != identity(p.path) or path_guard(p.glyph,p.owner,p.layer,p.path) != p.guard:
            raise RepairError("stale", "Source changed before Apply")
        if effective_chain(p.path,app).curves != effective_chain(p.baseline_path,app).curves:
            raise RepairError("stale", "Effective source changed before Apply")
    glyph = changed[0].glyph
    manager = value(glyph,"undoManager")
    if manager is None or not bool(value(manager,"isUndoRegistrationEnabled",False)):
        raise RepairError("undo_unavailable", "Native Undo is unavailable")
    written = []
    glyph.beginUndo()
    try:
        for p in changed:
            written.append(p)
            with precision(p.layer,True): write_nodes(p.path,p.after_nodes)
            if path_state(p.path) != p.expected: raise RepairError("native_verification", "Native node edits did not match the validated repair")
            validate_candidate(p.baseline_layer,p.layer,p.baseline_path,p.path,p.requested,app,float(glyph.parent.upm),limit)
    except Exception:
        for p in reversed(written):
            with precision(p.layer,True): write_nodes(p.path,p.before_nodes)
        if any(path_state(p.path) != p.guard[-1] for p in written):
            raise RepairError("recovery_failed", "Could not restore the affected contour; use native Undo")
        raise
    finally: glyph.endUndo()


@dataclass
class Result:
    repaired: int = 0
    converted: int = 0
    already_smooth: int = 0
    threshold_rejected: int = 0
    unsupported: int = 0
    glyphs: int = 0
    max_outline_change_units: float = 0.
    reasons: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    @property
    def changed(self): return self.repaired+self.converted

    @property
    def skipped(self): return self.reasons

    def message(self):
        parts = []
        for count, text in ((self.repaired,"repaired"),(self.converted,"converted"),(self.already_smooth,"smooth"),
                            (self.threshold_rejected,"limit blocked"),(self.unsupported,"unsupported")):
            if count: parts.append(str(count)+" "+text)
        return " · ".join(parts) or "Nothing to change"

    def details(self):
        return self.message()+"\nCertified max outline change: {:.6g} units\n".format(self.max_outline_change_units)+"\n".join(self.reasons+self.notes)+"\nUndo is available per glyph. Font not saved; interpolation is not verified."


def apply_path(glyph, owner, layer, path, joins, app, method, max_change_units=None, *, tunni_balance=True):
    """Public one-contour action, using the same prepare/commit implementation."""
    p = prepare_path(glyph,owner,layer,path,joins,app,method,max_change_units,tunni_balance=tunni_balance)
    commit_paths([p],app,validate_limit(default_limit(glyph.parent) if max_change_units is None else max_change_units))
    return p.repaired+p.converted, list(p.notes)


def apply_steps(scope, app, method="star", all_masters=False, max_change_units=None, *, tunni_balance=True):
    if method not in ("star","default-node"): raise RepairError("unsupported_method")
    limit = validate_limit(default_limit(scope.font) if max_change_units is None else max_change_units)
    master = value(scope.font,"selectedFontMaster")
    result = Result()
    trials = None
    for glyph in scope.glyphs:
        if identity(glyph.parent) != identity(scope.font): raise RepairError("stale","Glyph left the font")
        base = scope.layer if scope.layer is not None else glyph.layers[str(master.id)] if master is not None else None
        selected = scope.selection if scope.layer is not None else ()
        owners = [base]
        if all_masters:
            masters = [glyph.layers[str(m.id)] for m in scope.font.masters]
            owners = ([base] if any(identity(base)==identity(l) for l in masters) else [])
            owners += [l for l in masters if not owners or identity(l)!=identity(owners[0])]
        layers = [(o,o.background if scope.background and o is not None and value(o,"hasBackground",False) else o) for o in owners]
        if base is None or any(o is None or l is None or (scope.background and not value(o,"hasBackground",False)) for o,l in layers):
            result.unsupported += 1; result.reasons.append(str(glyph.name)+": Requested master/background missing"); yield result; continue
        source = base.background if scope.background else base
        if any(topology(l)!=topology(source) for _,l in layers):
            result.unsupported += 1; result.reasons.append(str(glyph.name)+": Master contours cannot be matched"); yield result; continue
        start = result.changed
        found = False
        accepted = []
        prior_reasons = len(result.reasons)
        selected_ids = {identity(n) for n in selected}
        for pi,path in enumerate(source.paths):
            joins = ()
            try:
                # Explicit selection maps exactly; whole-glyph scope uses the
                # union of smooth eligible joins across all requested masters.
                joins, misses = selected_joins(path,selected,app)
                if not selected:
                    joins = tuple(sorted({i for _,l in layers for i in selected_joins(l.paths[pi],(),app)[0]}))
                for i,reason in misses:
                    result.unsupported += 1; result.reasons.append(str(glyph.name)+": node "+str(i)+" · "+reason)
                if not joins: continue
                found = True
                if trials is None: trials = trial_fonts(scope.font)
                def build_plans(indices, seeds=None):
                    plans = []
                    for k,(o,l) in enumerate(layers):
                        try:
                            if any(int(l.paths[pi].nodes[i].connection) == app.GSSHARP and
                                   identity(path.nodes[i]) not in selected_ids for i in indices):
                                raise RepairError("deliberate_corner", "A corresponding master has a deliberate corner")
                            plans.append(prepare_path(glyph,o,l,l.paths[pi],indices,app,method,limit,trials=trials,
                                                      tunni_balance=tunni_balance,seed=seeds[k] if seeds else None))
                        except RepairError as exc:
                            raise RepairError(exc.code, str(value(l,"name",o.layerId))+" · "+str(exc)) from exc
                    return plans
                try:
                    plans = build_plans(joins)
                except RepairError as exc:
                    if exc.code == "stale": raise
                    # A rejected join must not block independent bounded repairs.
                    # Each cumulative candidate is checked against the ORIGINAL
                    # contour, and across every requested master before acceptance.
                    plans = [None]*len(layers)
                    for i in joins:
                        try: proposed = build_plans((i,),plans)
                        except RepairError as rejected:
                            if rejected.code == "stale": raise
                            if rejected.code in ("excess_deviation","unresolved_deviation"): result.threshold_rejected += 1
                            else: result.unsupported += 1
                            result.reasons.append(str(glyph.name)+" / path "+str(pi)+" / node "+str(i)+": "+str(rejected))
                        else: plans = proposed
                accepted.extend(p for p in plans if p is not None)
            except RepairError as exc:
                if exc.code in ("recovery_failed","undo_unavailable","stale"): raise
                count = max(1,len(joins))
                if exc.code in ("excess_deviation","unresolved_deviation"):
                    result.threshold_rejected += count
                else: result.unsupported += count
                result.reasons.append(str(glyph.name)+" / path "+str(pi)+": "+str(exc))
        commit_paths(accepted,app,limit)
        for p in accepted:
            result.repaired += p.repaired; result.converted += p.converted; result.already_smooth += p.already_smooth
            result.max_outline_change_units = max(result.max_outline_change_units,p.maximum)
            result.notes.extend(str(glyph.name)+" / "+str(value(p.layer,"name",p.owner.layerId))+": "+n for n in p.notes)
        if selected and not found and len(result.reasons)==prior_reasons:
            result.unsupported += 1; result.reasons.append(str(glyph.name)+": Select an on-curve, curve handle or path")
        result.glyphs += result.changed > start
        yield result
    return result
