"""Detached Glyphs trials and guarded application, shared by UI and agent.

Only invoke on Glyphs' main thread. There is no dependency on bridge internals,
no hidden font Save, and no global redraw. Native errors fail closed.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
import hashlib
import json
import math

from . import ENGINE_VERSION
from .coverage import locations
from .geometry import (RepairError, normalized, diagnose_join, check_pair,
                       no_regression, norm, sub, chain_deviation)
from .supertool import harmonize, balance, fit_grid
from .outline import drawing_outline
from .joins import source_join, source_segments, join_kind, has_line_join, drawing_chain


def value(owner, name, default=None):
    result = getattr(owner, name, default)
    return result() if callable(result) else result


def freeze(data):
    """Exact finite, deterministic native property-list state; never object repr."""
    if data is None or isinstance(data, (bool, str, int)):
        return data
    if isinstance(data, float):
        if not math.isfinite(data): raise RepairError("nonfinite_state")
        return ("float", data.hex())
    if hasattr(data, "keys"):
        return tuple(sorted((str(key), freeze(data[key])) for key in data.keys()))
    if isinstance(data, (list, tuple)) or hasattr(data, "objectAtIndex_"):
        return tuple(freeze(item) for item in data)
    if hasattr(data, "x") and hasattr(data, "y"):
        return ("point", freeze(float(data.x)), freeze(float(data.y)))
    raise RepairError("unsupported_attribute", "An attribute cannot be guarded exactly: " + type(data).__name__)


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@contextmanager
def precision(layer, needed):
    if not needed:
        yield
        return
    setter = getattr(layer, "setTemporarilyDisableRounding_", None)
    if not callable(setter) or not hasattr(layer, "temporarilyDisableRounding"):
        raise RepairError("native_unqualified", "Exact coordinate trials need the native precision API.")
    previous = bool(value(layer, "temporarilyDisableRounding"))
    setter(True)
    try:
        yield
    finally:
        setter(previous)
        if bool(value(layer, "temporarilyDisableRounding")) != previous:
            raise RepairError("precision_restore_failed")


def position(node):
    p = node.position
    return float(p.x), float(p.y)


def parameters(owner):
    items = value(owner, "customParameters", {})
    if isinstance(items, dict): return freeze(items)
    return tuple((str(item.name), freeze(item.value), bool(value(item, "disabled", False))) for item in items)


def identity(owner):
    try:
        import objc
        return int(objc.pyobjc_id(owner))
    except (ImportError, TypeError, AttributeError):
        return id(owner)


def identities(glyph):
    result = []
    for owner in glyph.layers:
        for layer in (owner, owner.background) if value(owner, "hasBackground", False) else (owner,):
            result.append((identity(layer), tuple((identity(p), tuple(identity(n) for n in p.nodes)) for p in layer.paths)))
    return tuple(result)


def path_state(path):
    return (bool(path.closed), bool(value(path, "locked", False)),
            freeze(value(path, "attributes", {})),
            tuple((freeze(position(n)), str(n.type), int(value(n, "connection")),
                   freeze(value(n, "attributes", {})), value(n, "name"),
                   bool(value(n, "locked", False)), freeze(value(n, "orientation")),
                   freeze(n.attributeForKey_("hoi") if hasattr(n, "attributeForKey_") else None)) for n in path.nodes))


def layer_state(layer):
    if list(value(layer, "hints", ())):
        raise RepairError("coverage_incomplete", "Hint-bearing layers require separate effective-outline qualification.")
    if list(value(layer, "components", ())):
        raise RepairError("coverage_incomplete", "Component outlines are not covered by this repair engine.")
    if any(not hasattr(shape, "nodes") for shape in value(layer, "shapes", layer.paths)):
        raise RepairError("coverage_incomplete", "A non-path shape is outside repair coverage.")
    if any(any(str(key).lower().startswith("stroke") for key in value(path, "attributes", {}).keys()) for path in layer.paths):
        raise RepairError("coverage_incomplete", "Stroke expansion requires separate outline correspondence.")
    return (str(layer.layerId), str(value(layer, "associatedMasterId", "")),
            freeze(value(layer, "attributes", {})), freeze(float(layer.width)),
            bool(value(layer, "locked", False)), tuple(path_state(p) for p in layer.paths),
            str(value(layer, "name", "")), bool(value(layer, "isSpecialLayer", False)),
            bool(value(layer, "temporarilyDisableRounding", False)))


def glyph_state(font, glyph):
    if sum(len(p.nodes) for layer in glyph.layers for p in layer.paths) > 200000:
        raise RepairError("coverage_incomplete", "Exact source guard budget exceeded; narrow the glyph scope.")
    layers = []
    for layer in glyph.layers:
        background = layer_state(layer.background) if value(layer, "hasBackground", False) else None
        layers.append((layer_state(layer), background))
    return (str(glyph.name), bool(value(glyph, "locked", False)),
            freeze(float(font.upm)), freeze(value(glyph, "attributes", {})),
            tuple((str(a.axisId), str(value(a, "name", ""))) for a in font.axes),
            tuple((str(m.id), freeze(tuple(float(v) for v in m.internalAxesValues)),
                   parameters(m)) for m in font.masters),
            tuple((freeze(tuple(float(v) for v in i.internalAxesValues)),
                   value(i, "type", 0),
                   bool(value(i, "manualInterpolation", False)),
                   freeze(value(i, "instanceInterpolations", {})),
                   parameters(i)) for i in font.instances),
            parameters(font), tuple(layers), freeze(float(value(font, "gridLength", 0))))


def detached_copy(font, glyph_name):
    """Restore copied background ownership, then require exact model equality.

    Glyphs 4108 drops background layerId/associatedMasterId during font.copy(),
    including empty backgrounds created by Edit View. Only detached ownership
    metadata is restored; coordinates, connections and attributes remain guarded.
    """
    copied = font.copy()
    source = font.glyphs[glyph_name]
    target = copied.glyphs[glyph_name]
    if target is None: raise RepairError("native_unqualified", "Native copying lost the glyph.")
    for owner in source.layers:
        trial = target.layers[str(owner.layerId)]
        if trial is None: raise RepairError("native_unqualified", "Native copying lost an owning layer.")
        if value(owner, "hasBackground", False) and value(trial, "hasBackground", False):
            for key in ("layerId", "associatedMasterId"):
                actual, expected = value(trial.background, key), value(owner.background, key)
                if actual is None and expected is not None:
                    setattr(trial.background, key, expected)
    if glyph_state(copied, target) != glyph_state(font, source):
        raise RepairError("native_unqualified", "Detached native copying does not preserve the exact source model.")
    return copied


def segments(path, curve_type, offcurve_type):
    nodes, result = list(path.nodes), {}
    count = len(nodes)
    for end, node in enumerate(nodes):
        if node.type != curve_type or count < 4 or (not path.closed and end < 3):
            continue
        indices = tuple((end-offset) % count for offset in (3, 2, 1, 0))
        if (nodes[indices[0]].type == offcurve_type or
                any(nodes[i].type != offcurve_type for i in indices[1:3])):
            raise RepairError("incompatible_correspondence", "Unsupported cubic node ordering.")
        result[end] = (indices, tuple(position(nodes[i]) for i in indices))
    return result


def join_curves(path, index, app):
    curves = segments(path, app.CURVE, app.OFFCURVE)
    incoming = curves.get(index)
    outgoing = next((item for item in curves.values() if item[0][0] == index), None)
    if incoming is None or outgoing is None:
        raise RepairError("unsupported_join", "Only cubic-to-cubic joins are supported; zero-handle extraction is deferred.")
    return incoming, outgoing


def effective(path, app):
    bezier = value(path, "bezierPath")
    if bezier is not None:
        layer = value(path, "parent")
        glyph = value(layer, "parent")
        font = value(glyph, "parent")
        step = 0 if value(layer, "temporarilyDisableRounding", False) else float(value(font, "gridLength", 0))
        return drawing_outline(path, bezier, star_connection=app.GSSUPERSMOOTH,
                               curve_type=app.CURVE, offcurve_type=app.OFFCURVE, line_type=app.LINE, grid_step=step)
    method = getattr(path, "primitiveRepresentation", None)
    if not callable(method):
        raise RepairError("native_unqualified", "Native effective-path extraction is unavailable.")
    primitive = method()
    if not hasattr(primitive, "nodes"):
        items = list(primitive or ())
        if len(items) != 1 or not hasattr(items[0], "nodes"):
            raise RepairError("incompatible_correspondence", "Native conversion changes the path correspondence.")
        primitive = items[0]
    if (bool(primitive.closed) != bool(path.closed) or
            tuple(n.type for n in primitive.nodes) != tuple(n.type for n in path.nodes)):
        raise RepairError("incompatible_correspondence", "Native primitive topology differs from source topology.")
    if any(int(value(n, "connection")) == app.GSSUPERSMOOTH for n in primitive.nodes):
        raise RepairError("native_unqualified", "Primitive representation retains stored star coordinates; native drawing extraction is required.")
    return primitive


def effective_chain(path, app):
    bezier = value(path, "bezierPath")
    if bezier is None: raise RepairError("native_unqualified", "Line/curve transitions need native drawing extraction.")
    layer = value(path, "parent")
    font = value(value(layer, "parent"), "parent")
    step = 0 if value(layer, "temporarilyDisableRounding", False) else float(value(font, "gridLength", 0))
    return drawing_chain(path, bezier, app, grid_step=step)


@dataclass(frozen=True)
class Edit:
    layer_id: str
    path: int
    node: int
    before_position: tuple
    after_position: tuple
    before_connection: int
    after_connection: int


@dataclass(frozen=True)
class Proposal:
    font: object
    glyph_name: str
    source_layer: object
    owner_id: str
    surface: str
    source_state: tuple
    source_identities: tuple
    expected_state: tuple
    fingerprint: str
    edits: tuple
    joins: tuple
    method: str
    tolerance_em: float
    upm: float
    baseline: object
    report: dict
    before_curves: tuple
    after_curves: tuple

    def summary(self):
        return {"engineVersion": ENGINE_VERSION, "sourceFingerprint": self.fingerprint,
                "glyph": self.glyph_name, "owningLayer": self.owner_id, "surface": self.surface,
                "method": self.method, "maxDeviationEm": self.tolerance_em,
                "editCount": len(self.edits), **self.report}


class NativeAdapter:
    def __init__(self, app=None, *, job_context=False):
        if app is None:
            import GlyphsApp as app
        self.app = app
        self.job_context = job_context

    def _thread(self):
        # Tests supply an API double; native operations always enforce this.
        if self.app.__name__ == "GlyphsApp":
            from Foundation import NSThread
            if not NSThread.isMainThread():
                raise RepairError("wrong_thread", "Native repair must run on Glyphs' main thread.")

    def _layer(self, font, name, identifier, surface):
        owner = font.glyphs[name].layers[identifier]
        if owner is None: raise RepairError("stale", "The owning layer no longer exists.")
        if surface == "background":
            if not value(owner, "hasBackground", False):
                raise RepairError("coverage_incomplete", "This layer has no existing background.")
            return owner.background
        return owner

    def selected_joins(self, layer, *, all_joins=False):
        selected = set(identity(n) for n in value(layer, "selection", ()))
        result, blocked = [], []
        for p, path in enumerate(layer.paths):
            for n, node in enumerate(path.nodes):
                if node.type == self.app.OFFCURVE or (not all_joins and identity(node) not in selected):
                    continue
                # Preserve deliberate corners even in an all-joins request.
                if int(value(node, "connection")) == self.app.GSSHARP:
                    if not all_joins: blocked.append((p, n, "deliberate_corner", "Deliberate corner; keep it sharp or explicitly make it smooth first."))
                    continue
                try: source_join(path, n, self.app)
                except RepairError as exc:
                    if all_joins and exc.code in ("open_endpoint", "line_line"): continue
                    blocked.append((p, n, exc.code, str(exc))); continue
                result.append((p, n))
        if blocked:
            p, n, code, reason = blocked[0]
            raise RepairError(code if not result and len(blocked) == 1 else "coverage_incomplete",
                "{} eligible, {} blocked. Path {}, node {}: {}".format(len(result), len(blocked), p, n, reason))
        if not result: raise RepairError("empty_scope", "Select a smooth on-curve node between two segments, then Preview.")
        return tuple(result)

    def _designspace(self, font, glyph, region):
        axes = tuple(str(a.axisId) for a in font.axes)
        masters = tuple(tuple(float(v) for v in m.internalAxesValues) for m in font.masters)
        specials, families, boundaries, family_layers = [], {"ordinary"}, [], {}
        master_ids = {str(m.id) for m in font.masters}
        for layer in glyph.layers:
            attrs = value(layer, "attributes", {})
            rules = attrs.get("axisRules")
            family = "ordinary"
            if rules:
                if not hasattr(rules, "keys"):
                    raise RepairError("native_unqualified", "Conditional layer rules are not classified on this host.")
                for axis, limits in rules.items():
                    if str(axis) not in axes or not hasattr(limits, "keys") or set(limits.keys()) - {"min", "max"}:
                        raise RepairError("native_unqualified", "Unsupported conditional-layer rule.")
                    for number in limits.values():
                        number = float(number)
                        if not math.isfinite(number): raise RepairError("invalid_designspace")
                        boundaries.append((axes.index(str(axis)), number))
                family = "alternate:" + digest(freeze(rules))[:12]
                families.add(family)
                if str(layer.associatedMasterId) not in master_ids:
                    raise RepairError("invalid_designspace")
            coordinates = attrs.get("coordinates")
            if coordinates:
                if hasattr(coordinates, "keys"):
                    master = next((m for m in font.masters if str(m.id) == str(layer.associatedMasterId)), None)
                    if master is None: raise RepairError("invalid_designspace")
                    specials.append(tuple(float(coordinates.get(axis, master.internalAxesValues[i])) for i, axis in enumerate(axes)))
                else:
                    specials.append(tuple(float(v) for v in coordinates))
            elif value(layer, "isSpecialLayer", False) and not rules:
                raise RepairError("native_unqualified", "An unclassified special-layer family prevents complete verification.")
            if str(layer.layerId) not in master_ids and not coordinates and not rules:
                continue  # Backup layers are not interpolation source layers.
            family_layers.setdefault(family, []).append(str(layer.layerId))
            if list(value(layer, "components", ())):
                raise RepairError("coverage_incomplete", "Components in a contributing layer are not covered.")
        configured = []
        for instance in font.instances:
            if value(instance, "manualInterpolation", False):
                raise RepairError("native_unqualified", "Manually weighted instances require separate qualification.")
            configured.append(tuple(float(v) for v in instance.internalAxesValues))
        coverage = locations(masters, special_locations=tuple(specials), configured=tuple(configured), boundaries=tuple(boundaries), region=region)
        coverage["families"] = tuple(sorted(families))
        coverage["axisIds"] = axes
        coverage["familyLayers"] = {family: tuple(ids) for family, ids in family_layers.items()}
        coverage["boundaries"] = tuple(boundaries)
        coverage["familySelection"] = "native GSInstance.interpolatedFont; no custom substitution or linear interpolation"
        coverage["configuredInstances"] = tuple(index for index, p in enumerate(configured)
                                                if all(low <= v <= high for v, (low, high) in zip(p, coverage["region"])))
        coverage["configuredEvaluated"] = 0
        if len(coverage["configuredInstances"]) > 4096:
            raise RepairError("location_budget_exceeded", "Too many configured instances in the declared region.")
        return coverage

    def _generated(self, font, name, location, instance_index=None):
        instance = font.instances[instance_index].copy() if instance_index is not None else self.app.GSInstance()
        font.instances.append(instance)
        try:
            instance.manualInterpolation = False
            instance.internalAxesValues = list(location)
            generated = instance.interpolatedFont
            if generated is None: raise RepairError("native_unqualified", "Native interpolation produced no font.")
            glyph = generated.glyphs[name]
            if glyph is None or len(generated.masters) != 1:
                raise RepairError("incompatible_correspondence")
            return generated, glyph.layers[generated.masters[0].id]
        finally:
            # Only the detached font receives this temporary native instance.
            del font.instances[-1]

    def _verify_layer(self, before, after, joins, upm, tolerance):
        if len(before.paths) != len(after.paths): raise RepairError("incompatible_correspondence")
        maximum, integral, before_curves, after_curves, diagnostics = 0., 0., [], [], []
        touched = {p for p, _ in joins}
        for p in sorted(touched):
            for path_index, node_index in (join for join in joins if join[0] == p):
                if p >= len(before.paths) or node_index >= len(before.paths[p].nodes):
                    raise RepairError("incompatible_correspondence", "An active family has no corresponding requested join.")
                if int(value(before.paths[p].nodes[node_index], "connection")) == self.app.GSSHARP:
                    raise RepairError("incompatible_correspondence", "An active family contains a deliberate corner at the requested join.")
            if has_line_join(before.paths[p], self.app):
                measured, old_curves, new_curves = self._verify_mixed_path(before, after, p, joins, upm, tolerance)
                maximum = max(maximum, measured["upper"])
                integral = None
                before_curves.extend(old_curves); after_curves.extend(new_curves)
                diagnostics.extend(measured["diagnostics"])
                continue
            original, trial = effective(before.paths[p], self.app), effective(after.paths[p], self.app)
            before_segments = segments(original, self.app.CURVE, self.app.OFFCURVE)
            after_segments = segments(trial, self.app.CURVE, self.app.OFFCURVE)
            if tuple(before_segments) != tuple(after_segments): raise RepairError("incompatible_correspondence")
            for key, (_, curve) in before_segments.items():
                following = after_segments[key][1]
                measurement = check_pair(curve, following, upm, tolerance)
                maximum = max(maximum, measurement["upper"])
                if integral is not None: integral += measurement["integral"]
                before_curves.append(curve); after_curves.append(following)
            for n, node in enumerate(before.paths[p].nodes):
                if node.type == self.app.OFFCURVE or int(value(node, "connection")) == self.app.GSSHARP:
                    continue
                left, right = join_curves(original, n, self.app)
                next_left, next_right = join_curves(trial, n, self.app)
                origin = left[1][-1]
                old = diagnose_join(normalized(left[1], upm, origin), normalized(right[1], upm, origin))
                new = diagnose_join(normalized(next_left[1], upm, origin), normalized(next_right[1], upm, origin))
                if (p, n) in joins and not new["g2"]:
                    raise RepairError("continuity_failed", "A requested native join does not satisfy G2.")
                if (p, n) not in joins and not no_regression(old, new):
                    raise RepairError("neighbor_regression", "An adjacent smooth join regressed.")
                diagnostics.append({"path": p, "node": n, "before": old, "after": new,
                                    "beforeEffectivePosition": left[1][-1],
                                    "afterEffectivePosition": next_left[1][-1],
                                    "storedPosition": position(after.paths[p].nodes[n]),
                                    "joinKind": "curve-curve", "generatedJoins": (),
                                    "afterConnection": int(value(after.paths[p].nodes[n], "connection")),
                                    "effectiveJoinMovementEm": norm(sub(next_left[1][-1], left[1][-1])) / upm})
        return {"maxDeviationEm": maximum, "integratedDifferenceEm2": integral,
                "diagnostics": diagnostics}, tuple(before_curves), tuple(after_curves)

    def _verify_mixed_path(self, before, after, p, joins, upm, tolerance):
        """Measure rounded drawing; diagnose the unrounded native construction.

Native grid quantization can break exact tangency at generated cubic joins.
Record it separately; do not label those generated joins G2. The requested
source join must be G2 in the unrounded construction. Only detached layers
receive temporary precision, and their flags are restored before returning.
        """
        old_path, new_path = before.paths[p], after.paths[p]
        with precision(before, True), precision(after, True):
            original, trial = effective_chain(old_path, self.app), effective_chain(new_path, self.app)
        old_drawing, new_drawing = effective_chain(old_path, self.app), effective_chain(new_path, self.app)
        measure = chain_deviation(old_drawing.curves, new_drawing.curves, upm, tolerance)
        # Certify the construction as well as the actual rounded drawing.
        construction_measure = chain_deviation(original.curves, trial.curves, upm, tolerance)
        measure["upper"] = max(measure["upper"], construction_measure["upper"])
        incoming = {s.end: s for s in original.edges}; outgoing = {s.start: s for s in original.edges}
        generated = []
        drawing_groups = dict(new_drawing.groups)
        original_groups = dict(original.groups)
        for end, group in trial.groups:
            for i, (a, b) in enumerate(zip(group, group[1:])):
                origin = a[-1]
                diagnostic = diagnose_join(normalized(a, upm, origin), normalized(b, upm, origin))
                if not diagnostic["g1"]:
                    raise RepairError("continuity_failed", "A generated native transition has a tangent break.")
                prior = original_groups[end]
                if len(prior) == len(group):
                    old = diagnose_join(normalized(prior[i], upm, origin), normalized(prior[i+1], upm, origin))
                    if not no_regression(old, diagnostic): raise RepairError("neighbor_regression", "An existing generated transition regressed.")
                rounded = drawing_groups[end]
                quantized = diagnose_join(normalized(rounded[i], upm, origin), normalized(rounded[i+1], upm, origin))
                generated.append({"sourceEndNode": end, "ordinal": i,
                                  "construction": diagnostic, "drawing": quantized})
        diagnostics = []
        for n in sorted(incoming.keys() & outgoing.keys()):
            node = old_path.nodes[n]
            if int(value(node, "connection")) == self.app.GSSHARP: continue
            left, right = original.join(n); nl, nr = trial.join(n)
            origin = left[-1]
            old = diagnose_join(normalized(left, upm, origin), normalized(right, upm, origin))
            new = diagnose_join(normalized(nl, upm, origin), normalized(nr, upm, origin))
            if (p, n) in joins and not new["g2"]:
                raise RepairError("continuity_failed", "Path {}, node {}: native transition did not achieve G2.".format(p, n))
            if (p, n) not in joins and not no_regression(old, new):
                raise RepairError("neighbor_regression", "Path {}, node {}: neighboring join regressed.".format(p, n))
            dl, dr = new_drawing.join(n)
            diagnostics.append({"path": p, "node": n, "before": old, "after": new,
                "beforeEffectivePosition": left[-1], "afterEffectivePosition": nl[-1],
                "storedPosition": position(new_path.nodes[n]),
                "afterConnection": int(value(new_path.nodes[n], "connection")),
                "joinKind": incoming[n].kind + "-" + outgoing[n].kind,
                "generatedJoins": tuple(generated),
                "drawingContinuity": diagnose_join(normalized(dl, upm, origin), normalized(dr, upm, origin)),
                "continuityBasis": "unrounded native construction; drawing grid quantization reported separately",
                "effectiveJoinMovementEm": norm(sub(nl[-1], left[-1])) / upm})
        return {**measure, "diagnostics": diagnostics}, old_drawing.curves, new_drawing.curves

    def propose(self, *args, **kwargs):
        task = self.propose_steps(*args, **kwargs)
        while True:
            try: next(task)
            except StopIteration as result: return result.value

    def propose_steps(self, font, owner, *, all_joins=False, all_layers=False, joins=None,
                surface="foreground", method="native-star", tolerance_em=.001,
                tunni_balance=False, region=None):
        self._thread()
        if method not in ("native-star", "supertool-handles") or surface not in ("foreground", "background"):
            raise RepairError("invalid_method")
        if not math.isfinite(tolerance_em) or tolerance_em <= 0:
            raise RepairError("invalid_tolerance")
        if method == "native-star" and tunni_balance: raise RepairError("invalid_method", "Tunni balancing requires the explicit handle method.")
        glyph = owner.parent
        if glyph.parent is not font: raise RepairError("stale", "The owning font changed.")
        if value(owner, "locked", False): raise RepairError("locked_target")
        layer = self._layer(font, glyph.name, str(owner.layerId), surface)
        joins = tuple(joins) if joins is not None else self.selected_joins(layer, all_joins=all_joins)
        if not joins: raise RepairError("empty_scope")
        if (len(set(joins)) != len(joins) or any(len(j) != 2 or any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in j) for j in joins)):
            raise RepairError("invalid_scope")
        state, source_ids = glyph_state(font, glyph), identities(glyph)
        coverage = self._designspace(font, glyph, region) if surface == "foreground" else {
            "locations": (), "region": (), "requested": 0, "evaluated": 0,
            "families": ("background-source-only",), "complete": True,
            "evidence": "background source layers; no interpolation trajectory claim"}
        master_ids = {str(m.id) for m in font.masters}
        identifiers = [str(owner.layerId)]
        if all_layers:
            identifiers = [str(item.layerId) for item in glyph.layers
                           if str(item.layerId) in master_ids or value(item, "attributes", {}).get("coordinates") or value(item, "attributes", {}).get("axisRules")]
        if str(owner.layerId) not in identifiers: raise RepairError("unsupported_layer", "This layer is not an interpolation source layer.")
        baseline, detached = detached_copy(font, glyph.name), detached_copy(font, glyph.name)
        if glyph_state(baseline, baseline.glyphs[glyph.name]) != state or glyph_state(detached, detached.glyphs[glyph.name]) != state:
            raise RepairError("native_unqualified", "Detached native copying does not preserve the exact source model.")
        edits, before_curves, after_curves, diagnostics = [], [], [], []
        maximum, integral = 0., 0.
        for identifier in identifiers:
            original = self._layer(baseline, glyph.name, identifier, surface)
            trial = self._layer(detached, glyph.name, identifier, surface)
            if layer_state(original)[4] or value(glyph, "locked", False): raise RepairError("locked_target")
            if tuple(tuple(n.type for n in p.nodes) for p in original.paths) != tuple(tuple(n.type for n in p.nodes) for p in layer.paths):
                raise RepairError("incompatible_correspondence", "A contributing layer has incompatible topology.")
            with precision(trial, method == "supertool-handles"):
                self._trial(trial, joins, method, tunni_balance, font.upm, float(value(font, "gridLength", 0)))
            # Validate the entire interacting block, not isolated greedy successes.
            measure, old_curves, new_curves = self._verify_layer(original, trial, joins, font.upm, tolerance_em)
            maximum = max(maximum, measure["maxDeviationEm"])
            if integral is None or measure["integratedDifferenceEm2"] is None: integral = None
            else: integral += measure["integratedDifferenceEm2"]
            diagnostics.extend({"layer": identifier, **d} for d in measure["diagnostics"])
            before_curves.extend(old_curves); after_curves.extend(new_curves)
            for p, (old_path, new_path) in enumerate(zip(original.paths, trial.paths)):
                for n, (old, new) in enumerate(zip(old_path.nodes, new_path.nodes)):
                    if position(old) != position(new) or int(value(old, "connection")) != int(value(new, "connection")):
                        edits.append(Edit(identifier, p, n, position(old), position(new), int(value(old, "connection")), int(value(new, "connection"))))
            yield "Source layer " + identifier
        for location in coverage["locations"]:
            before_font, old_layer = self._generated(baseline, glyph.name, location)
            after_font, new_layer = self._generated(detached, glyph.name, location)
            measure, _, _ = self._verify_layer(old_layer, new_layer, joins, font.upm, tolerance_em)
            maximum = max(maximum, measure["maxDeviationEm"])
            coverage["evaluated"] += 1
            del before_font, after_font
            yield "Native locations: {}/{}".format(coverage["evaluated"], coverage["requested"])
        for index in coverage.get("configuredInstances", ()):
            location = tuple(float(v) for v in font.instances[index].internalAxesValues)
            bf, bl = self._generated(baseline, glyph.name, location, index)
            af, al = self._generated(detached, glyph.name, location, index)
            measured, _, _ = self._verify_layer(bl, al, joins, font.upm, tolerance_em)
            maximum = max(maximum, measured["maxDeviationEm"])
            coverage["configuredEvaluated"] += 1
            del bf, af
            yield "Configured instance " + str(index)
        if glyph_state(font, glyph) != state or identities(glyph) != source_ids:
            raise RepairError("stale", "Source changed during detached analysis.")
        report = {"status": "ok" if edits else "noop", "coverage": coverage,
                  "layers": identifiers, "maxMeasuredDeviationEm": maximum,
                  "integratedDifferenceEm2": integral, "diagnostics": diagnostics,
                  "maxEffectiveJoinMovementEm": max((d["effectiveJoinMovementEm"] for d in diagnostics), default=0),
                  "storedCoordinatesPreserved": all(e.before_position == e.after_position for e in edits)}
        report["deviationMetric"] = "continuous native-chain chord correspondence" if integral is None else "continuous corresponding cubic parameters"
        report["selectionCoverage"] = {"requestedJoins": len(joins), "eligibleJoins": len(joins), "blockedJoins": 0, "complete": True,
                                       "segmentSelectionRequired": False}
        if integral is None:
            coverage["evidence"] = "sampled-native; continuous bounds apply at each checked outline, including generated segments"
        expected = glyph_state(detached, detached.glyphs[glyph.name])
        return Proposal(font, str(glyph.name), owner, str(owner.layerId), surface, state, source_ids, expected, digest(state),
                        tuple(edits), joins, method, tolerance_em, float(font.upm), baseline, report,
                        tuple(before_curves), tuple(after_curves))

    def _trial(self, trial, joins, method, tunni_balance, upm, grid_step):
        for p, n in joins:
            if p < 0 or p >= len(trial.paths) or n < 0 or n >= len(trial.paths[p].nodes): raise RepairError("invalid_scope")
            path = trial.paths[p]; node = path.nodes[n]
            if value(path, "locked", False) or value(node, "locked", False): raise RepairError("locked_target")
            if int(value(node, "connection")) == self.app.GSSHARP: raise RepairError("deliberate_corner")
            source_left, source_right = source_join(path, n, self.app)
            mixed_join = source_left.kind != source_right.kind
            if mixed_join and method != "native-star":
                raise RepairError("unsupported_method", "Path {}, node {}: line/curve repair requires Native super-smooth. Move handles supports curve/curve joins.".format(p, n))
            if has_line_join(path, self.app):
                with precision(trial, True): primitive = effective_chain(path, self.app)
                effective_left, effective_right = primitive.join(n)
            else:
                primitive = effective(path, self.app)
                effective_left, effective_right = (item[1] for item in join_curves(primitive, n, self.app))
            origin = effective_left[-1]
            diagnostic = diagnose_join(normalized(effective_left, upm, origin), normalized(effective_right, upm, origin))
            if diagnostic["g2"] and not tunni_balance: continue
            if method == "native-star":
                node.setConnection_(self.app.GSSUPERSMOOTH)
            else:
                left, right = join_curves(path, n, self.app)
                if int(value(node, "connection")) == self.app.GSSUPERSMOOTH:
                    raise RepairError("unsupported_join", "Handle repair of existing stars requires an explicit conversion policy.")
                l, r = harmonize(normalized(left[1], upm, left[1][-1]), normalized(right[1], upm, left[1][-1]))
                if tunni_balance: l, r = balance(l), balance(r)
                l, r = fit_grid(l, r, normalized(left[1], upm, left[1][-1]), normalized(right[1], upm, left[1][-1]),
                                grid_step/upm, tuple(v/upm for v in left[1][-1]))
                for indices, controls in ((left[0], l), (right[0], r)):
                    for index, point in zip(indices[1:3], controls[1:3]):
                        if value(path.nodes[index], "locked", False): raise RepairError("locked_target")
                        path.nodes[index].position = (point[0]*upm+left[1][-1][0], point[1]*upm+left[1][-1][1])

    def is_current(self, proposal, active_font, active_owner=None):
        if identity(active_font) != identity(proposal.font): return False
        if active_owner is not None and identity(active_owner) != identity(proposal.source_layer): return False
        try:
            glyph = proposal.font.glyphs[proposal.glyph_name]
            return glyph_state(proposal.font, glyph) == proposal.source_state and identities(glyph) == proposal.source_identities
        except Exception: return False

    def analyze(self, font, owner, *, all_joins=False, surface="foreground", joins=None):
        self._thread()
        name, identifier = str(owner.parent.name), str(owner.layerId)
        layer = self._layer(font, name, identifier, surface)
        joins = tuple(joins) if joins is not None else self.selected_joins(layer, all_joins=all_joins)
        state = glyph_state(font, owner.parent)
        detached = detached_copy(font, name)
        trial = self._layer(detached, name, identifier, surface)
        diagnostics = []
        for p, n in joins:
            try:
                path = trial.paths[p]
                if has_line_join(path, self.app):
                    with precision(trial, True): left, right = effective_chain(path, self.app).join(n)
                else: left, right = (item[1] for item in join_curves(effective(path, self.app), n, self.app))
                diagnostic = diagnose_join(normalized(left, font.upm, left[-1]), normalized(right, font.upm, left[-1]))
                diagnostics.append({"path": p, "node": n, "joinKind": join_kind(path, n, self.app), **diagnostic})
            except RepairError as exc:
                diagnostics.append({"path": p, "node": n, "status": "undefined", "reason": exc.code, "detail": exc.detail})
        if glyph_state(font, owner.parent) != state: raise RepairError("stale")
        return {"engineVersion": ENGINE_VERSION, "sourceFingerprint": digest(state),
                "glyph": name, "owningLayer": identifier, "surface": surface,
                "diagnostics": diagnostics, "coverage": {"requestedJoins": len(joins), "evaluatedJoins": len(diagnostics),
                                                          "evidence": "native effective source layer; no designspace verification claim"}}

    def verify(self, proposal, *, active_font):
        self._thread()
        if identity(active_font) != identity(proposal.font): raise RepairError("stale")
        glyph = proposal.font.glyphs[proposal.glyph_name]
        if glyph_state(proposal.font, glyph) != proposal.expected_state or identities(glyph) != proposal.source_identities:
            raise RepairError("native_write_mismatch", "Actual native state differs from the proposed edits.")
        actual = detached_copy(proposal.font, proposal.glyph_name)
        maximum = 0.0
        for identifier in proposal.report["layers"]:
            measured, _, _ = self._verify_layer(
                self._layer(proposal.baseline, proposal.glyph_name, identifier, proposal.surface),
                self._layer(actual, proposal.glyph_name, identifier, proposal.surface),
                proposal.joins, proposal.upm, proposal.tolerance_em)
            maximum = max(maximum, measured["maxDeviationEm"])
        for location in proposal.report["coverage"]["locations"]:
            bf, bl = self._generated(proposal.baseline, proposal.glyph_name, location)
            af, al = self._generated(actual, proposal.glyph_name, location)
            measured, _, _ = self._verify_layer(bl, al, proposal.joins, proposal.upm, proposal.tolerance_em)
            maximum = max(maximum, measured["maxDeviationEm"])
            del bf, af
        for index in proposal.report["coverage"].get("configuredInstances", ()):
            location = tuple(float(v) for v in proposal.font.instances[index].internalAxesValues)
            bf, bl = self._generated(proposal.baseline, proposal.glyph_name, location, index)
            af, al = self._generated(actual, proposal.glyph_name, location, index)
            measured, _, _ = self._verify_layer(bl, al, proposal.joins, proposal.upm, proposal.tolerance_em)
            maximum = max(maximum, measured["maxDeviationEm"])
            del bf, af
        return {"status": "verified", "editCount": len(proposal.edits),
                "maxMeasuredDeviationEm": maximum,
                "evaluatedLocations": proposal.report["coverage"]["evaluated"],
                "configuredInstances": proposal.report["coverage"].get("configuredEvaluated", 0)}

    def apply(self, proposal, *, active_font, active_owner=None):
        self._thread()
        if not self.is_current(proposal, active_font, active_owner):
            raise RepairError("stale", "Preview is stale; inspect again before applying.")
        if proposal.report["status"] not in ("ok", "noop") or not proposal.report["coverage"]["complete"]:
            raise RepairError("coverage_incomplete")
        if not proposal.edits: return {"status": "noop", "editCount": 0}
        glyph = proposal.font.glyphs[proposal.glyph_name]
        if not self.job_context and hasattr(glyph, "undoManager"):
            manager = glyph.undoManager()
            if manager is None or not value(manager, "isUndoRegistrationEnabled", False):
                raise RepairError("font_busy", "Finish the native operation that owns this font before applying a repair.")
        layers = {e.layer_id: self._layer(proposal.font, proposal.glyph_name, e.layer_id, proposal.surface) for e in proposal.edits}
        coordinate_edit = any(e.before_position != e.after_position for e in proposal.edits)
        if coordinate_edit and any(not hasattr(l, "temporarilyDisableRounding") or not callable(getattr(l, "setTemporarilyDisableRounding_", None)) for l in layers.values()):
            raise RepairError("native_unqualified", "Exact coordinate edits need the native precision API.")
        original_flags = {key: bool(value(layer, "temporarilyDisableRounding", False)) for key, layer in layers.items()}
        glyph.beginUndo()
        try:
            try:
                with ExitStack() as restore:
                    for layer in layers.values(): restore.enter_context(precision(layer, coordinate_edit))
                    for edit in proposal.edits:
                        node = layers[edit.layer_id].paths[edit.path].nodes[edit.node]
                        if edit.before_position != edit.after_position: node.position = edit.after_position
                        if edit.before_connection != edit.after_connection: node.setConnection_(edit.after_connection)
                    for edit in proposal.edits:
                        node = layers[edit.layer_id].paths[edit.path].nodes[edit.node]
                        if norm(sub(position(node), edit.after_position)) > 1e-8 or int(value(node, "connection")) != edit.after_connection:
                            raise RepairError("native_write_mismatch")
                # Verify after precision flags are restored: temporary precision
                # also affects native drawing on 4108, not just coordinate writes.
                result = self.verify(proposal, active_font=active_font)
            except Exception as failure:
                try:
                    with ExitStack() as restore:
                        for layer in layers.values(): restore.enter_context(precision(layer, coordinate_edit))
                        for edit in proposal.edits:
                            node = layers[edit.layer_id].paths[edit.path].nodes[edit.node]
                            if edit.before_position != edit.after_position: node.position = edit.before_position
                            if edit.before_connection != edit.after_connection: node.setConnection_(edit.before_connection)
                    if coordinate_edit:
                        for key, layer in layers.items(): layer.setTemporarilyDisableRounding_(original_flags[key])
                    if glyph_state(proposal.font, glyph) != proposal.source_state or identities(glyph) != proposal.source_identities:
                        raise RepairError("recovery_failed")
                except Exception as recovery:
                    raise RepairError("recovery_failed", "Native repair failed and exact restoration could not be verified. Inspect the native Undo group before further edits.") from recovery
                raise failure
        finally:
            glyph.endUndo()
        return {**result, "recovery": "native glyph Undo group; no font Save performed"}
