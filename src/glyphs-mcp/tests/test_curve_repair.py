"""Analytic repair controls and API-double trials; not native qualification."""
from __future__ import annotations
import copy
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src/companions/curve-inspector"))
from curve_repair.geometry import (RepairError, certify_regular, diagnose_join, normalized,
                                   deviation, integrated_difference)
from curve_repair.supertool import harmonize, balance, fit_grid
from curve_repair.coverage import locations
from curve_repair.native import NativeAdapter, glyph_state, freeze
from curve_repair.outline import drawing_outline


LEFT = ((-200., 100.), (-100., 40.), (-40., 0.), (0., 0.))
RIGHT = ((0., 0.), (39., 0.), (100., 40.), (200., 100.))


def test_signed_g2_reference_and_straight_limits():
    matching = (RIGHT[0], (40., 0.), *RIGHT[2:])
    assert diagnose_join(LEFT, matching)["g2"]
    opposite = (RIGHT[0], (40., 0.), (100., -40.), RIGHT[3])
    assert diagnose_join(LEFT, opposite)["g1"]
    assert not diagnose_join(LEFT, opposite)["g2"]
    straight = ((0., 0.), (1., 0.), (2., 0.), (3., 0.))
    certify_regular(straight)
    assert diagnose_join(straight, tuple((x+3, y) for x, y in straight))["g2"]


def test_undefined_curvature_and_interior_cusp_are_not_zero():
    collapsed = (LEFT[0], LEFT[1], LEFT[3], LEFT[3])
    with pytest.raises(RepairError, match="undefined"):
        diagnose_join(collapsed, RIGHT)
    with pytest.raises(RepairError):
        certify_regular(((-1., 0.), (1., 0.), (-1., 0.), (1., 0.)))


def test_harmonize_matches_independent_g2_control_and_preserves_join():
    left, right = harmonize(LEFT, RIGHT)
    assert left[-1] == right[0] == (0., 0.)
    assert left[2] == pytest.approx((-39.5, 0), abs=1e-10)
    assert right[1] == pytest.approx((39.5, 0), abs=1e-10)
    assert diagnose_join(left, right)["g2"]
    assert harmonize(left, right) == (left, right)


def test_explicit_handle_route_repairs_small_broken_g1():
    broken = (RIGHT[0], (39., .01), RIGHT[2], RIGHT[3])
    assert not diagnose_join(LEFT, broken)["g1"]
    left, right = harmonize(LEFT, broken)
    assert diagnose_join(left, right)["g2"]
    assert left[-1] == right[0] == LEFT[-1]


def test_supertool_refuses_sign_conflicts_parallel_and_reversed_tangents():
    with pytest.raises(RepairError):
        harmonize(LEFT, (RIGHT[0], RIGHT[1], (100., -40.), RIGHT[3]))
    with pytest.raises(RepairError):
        harmonize(LEFT, (RIGHT[0], (-39., 0.), RIGHT[2], RIGHT[3]))
    with pytest.raises(RepairError):
        balance(((0., 0.), (1., 0.), (2., 0.), (3., 0.)))


def test_grid_fitting_preserves_g2_and_oncurve_without_changing_grid():
    l, r = harmonize(LEFT, RIGHT)
    a, b = fit_grid(l, r, LEFT, RIGHT, 1.)
    assert diagnose_join(a, b)["g2"]
    assert a[-1] == b[0] == (0., 0.)
    assert all(v.is_integer() for point in (a[2], b[1]) for v in point)
    assert fit_grid(l, r, LEFT, RIGHT, 0.) == (l, r)


def test_configured_instances_do_not_create_extra_interpolation_cells():
    coverage = locations(((0.,), (1.,)), configured=((.5,),))
    assert coverage["requested"] == 9


def test_integral_and_continuous_bound_against_exact_single_handle_maximum():
    after = (LEFT[0], LEFT[1], (LEFT[2][0]+.5, LEFT[2][1]), LEFT[3])
    assert integrated_difference(LEFT, after) == pytest.approx(3/140)
    bound = deviation(LEFT, after, .23)
    assert bound["accepted"] and bound["lower"] <= 2/9 <= bound["upper"] <= .23
    assert not deviation(LEFT, after, .22)["accepted"]
    with pytest.raises(RepairError) as exc:
        deviation(LEFT, after, .23, max_depth=0)
    assert exc.value.code == "unresolved_deviation"


@pytest.mark.parametrize("shift,scale", [(1e6, 10), (-2000, .01), (0, 1000)])
def test_normalization_keeps_diagnostics_and_bounds(shift, scale):
    transform = lambda curve: tuple((x*scale+shift, y*scale-shift) for x, y in curve)
    left, right = transform(LEFT), transform(RIGHT)
    a, b = harmonize(normalized(left, 1000*scale, left[-1]), normalized(right, 1000*scale, left[-1]))
    assert diagnose_join(a, b)["g2"]


def test_coverage_counts_independent_lattices_and_refuses_silent_truncation():
    assert locations(((0.,), (1.,)))["requested"] == 9
    assert locations(((0., 0.), (1., 1.)))["requested"] == 41
    with pytest.raises(RepairError) as exc:
        locations(((0.,)*5, (1.,)*5))
    assert exc.value.code == "location_budget_exceeded"
    assert locations(((0.,)*5, (1.,)*5), region=((0., 1.), *((.5, .5),)*4))["requested"] == 9


def test_coverage_includes_specials_configured_instances_and_boundary_probes():
    coverage = locations(((0.,), (1.,)), special_locations=((.3,),), configured=((.7,),), boundaries=((0, .5),))
    points = coverage["locations"]
    assert (.3,) in points and (.7,) in points and (.5,) in points
    assert (.5-1e-6,) in points and (.5+1e-6,) in points


class Node:
    def __init__(self, point, kind, connection=100):
        self._position = SimpleNamespace(x=point[0], y=point[1])
        self.type, self.connection = kind, connection
        self.attributes, self.name, self.locked = {}, None, False
        self.write_failure = False
    @property
    def position(self): return self._position
    @position.setter
    def position(self, point):
        if self.write_failure:
            self.write_failure = False
            raise RuntimeError("injected setter failure")
        self._position = SimpleNamespace(x=point[0], y=point[1])
    def setConnection_(self, value): self.connection = value


class PathDouble:
    def __init__(self, outgoing=39):
        points = (*LEFT, (float(outgoing), 0.), RIGHT[2], RIGHT[3])
        self.nodes = [Node(p, kind, 101 if i == 3 else 100) for i, (p, kind) in enumerate(zip(points, ("line", "offcurve", "offcurve", "curve", "offcurve", "offcurve", "curve")))]
        self.closed, self.locked, self.attributes = False, False, {}
        self.inert = False
    def primitiveRepresentation(self):
        # This deliberately reproduces the primitive/stored distinction
        # observed on 4108, rather than inventing a native conversion.
        return copy.deepcopy(self)
    @property
    def bezierPath(self):
        points = [n.position for n in self.nodes]
        if self.nodes[3].connection == 102 and not self.inert:
            # Declared symmetric effective-join fixture, not a general star algorithm.
            points[3] = SimpleNamespace(x=(points[2].x+points[4].x)/2, y=0.)
        elements = [(0, (points[0],)), (2, tuple(points[1:4])), (2, tuple(points[4:7]))]
        if self.closed:
            elements = [(0, (points[6],)), (1, (points[0],)), *elements[1:], (3, ()), (0, (points[6],))]
        return SimpleNamespace(elementCount=lambda: len(elements), elementAtIndex_associatedPoints_=lambda i: elements[i])


def test_effective_drawing_correspondence_for_open_closed_and_unclassified_shift():
    path = PathDouble(); path.nodes[3].connection = 102
    def extract():
        return drawing_outline(path, path.bezierPath, star_connection=102, curve_type="curve", offcurve_type="offcurve", line_type="line")
    for closed in (False, True):
        path.closed = closed
        outline = extract()
        assert outline.nodes[3].position == (-.5, 0.)
        assert path.primitiveRepresentation().nodes[3].position.x == 0.
    original = path.bezierPath
    path.nodes[3].connection = 101
    with pytest.raises(RepairError) as exc:
        drawing_outline(path, original, star_connection=102, curve_type="curve", offcurve_type="offcurve", line_type="line")
    assert exc.value.code == "incompatible_correspondence"


class Layers(list):
    def __getitem__(self, key):
        if isinstance(key, str): return next((l for l in self if l.layerId == key), None)
        return super().__getitem__(key)


class Layer:
    def __init__(self, identifier, outgoing=39):
        self.layerId = self.associatedMasterId = identifier
        self.paths = [PathDouble(outgoing)]
        self.attributes, self.components = {}, []
        self.width, self.locked = 500., False
        self.hasBackground, self.isSpecialLayer = False, False
        self.temporarilyDisableRounding = False
        self.selection = [self.paths[0].nodes[3]]
    @property
    def shapes(self): return self.paths
    def setTemporarilyDisableRounding_(self, flag): self.temporarilyDisableRounding = flag


class Instances(list):
    def __init__(self, font): super().__init__(); self.font = font
    def append(self, instance): instance.font = self.font; super().append(instance)


class Instance:
    def __init__(self):
        self.internalAxesValues = []
        self.manualInterpolation = False
        self.instanceInterpolations = self.customParameters = {}
    @property
    def interpolatedFont(self):
        result = self.font.copy()
        # Native interpolation is deliberately not emulated. Assert dispatch
        # and guard coverage against a static reference geometry only.
        result.masters = [result.masters[0]]
        result.glyphs["test"].layers = Layers([result.glyphs["test"].layers[0]])
        return result


class Font:
    def __init__(self, axes=1):
        self.upm, self.customParameters = 1000., {}
        self.axes = [SimpleNamespace(axisId=str(i), name=str(i)) for i in range(axes)]
        self.masters = [SimpleNamespace(id="m0", internalAxesValues=[0.]*axes, customParameters={}),
                        SimpleNamespace(id="m1", internalAxesValues=[1.]*axes, customParameters={})]
        layers = Layers([Layer("m0"), Layer("m1")])
        glyph = SimpleNamespace(name="test", locked=False, attributes={}, parent=self, layers=layers,
                                beginUndo=self.beginUndo, endUndo=self.endUndo)
        for layer in layers: layer.parent = glyph
        self.glyphs = {"test": glyph}
        self.instances = Instances(self)
        self.undo_depth = 0
    def beginUndo(self): self.undo_depth += 1
    def endUndo(self): self.undo_depth -= 1
    def copy(self): return copy.deepcopy(self)


def test_detached_copy_restores_only_missing_background_ownership():
    from curve_repair.native import detached_copy
    class LostBackgroundOwners(Font):
        def copy(self):
            result = super().copy()
            result.glyphs["test"].layers[0].background.layerId = None
            result.glyphs["test"].layers[0].background.associatedMasterId = None
            return result
    font = LostBackgroundOwners()
    owner = font.glyphs["test"].layers[0]
    owner.hasBackground = True
    owner.background = Layer(owner.layerId)
    before = glyph_state(font, owner.parent)
    detached = detached_copy(font, "test")
    assert glyph_state(detached, detached.glyphs["test"]) == before
    assert glyph_state(font, owner.parent) == before
    # Losing actual geometry remains a refusal, even with ownership normalized.
    original_copy = font.copy
    def damaged_copy():
        result = original_copy()
        result.glyphs["test"].layers[0].background.paths.clear()
        return result
    font.copy = damaged_copy
    with pytest.raises(RepairError): detached_copy(font, "test")


@pytest.fixture
def native():
    app = SimpleNamespace(__name__="test-double", LINE="line", CURVE="curve", OFFCURVE="offcurve", GSSHARP=100, GSSMOOTH=101, GSSUPERSMOOTH=102, GSInstance=Instance)
    font = Font()
    return NativeAdapter(app), font, font.glyphs["test"].layers[0]


def test_native_preview_detached_star_and_verified_guarded_application(native):
    adapter, font, owner = native
    before = glyph_state(font, owner.parent)
    proposal = adapter.propose(font, owner, all_layers=True)
    assert glyph_state(font, owner.parent) == before
    assert len(proposal.edits) == 2
    assert proposal.report["storedCoordinatesPreserved"]
    assert proposal.report["coverage"]["evaluated"] == 9
    assert adapter.apply(proposal, active_font=font, active_owner=owner)["status"] == "verified"
    assert font.undo_depth == 0
    assert owner.paths[0].nodes[3].connection == 102
    assert adapter.propose(font, owner, all_layers=True).report["status"] == "noop"


@pytest.mark.parametrize("change", ["connection", "hoi", "coordinate", "lock", "axes", "special"])
def test_native_proposal_rejects_stale_exact_state_without_writes(native, change):
    adapter, font, owner = native
    proposal = adapter.propose(font, owner)
    node = owner.paths[0].nodes[3]
    if change == "connection": node.connection = 102
    elif change == "hoi": node.attributes["hoi"] = {"0": {"ip": [3., 4.]}}
    elif change == "coordinate": node.position = (0., .01)
    elif change == "lock": owner.locked = True
    elif change == "axes": font.masters[1].internalAxesValues[0] = 2.
    else: owner.attributes["coordinates"] = {"0": .4}
    changed = glyph_state(font, owner.parent)
    with pytest.raises(RepairError) as exc: adapter.apply(proposal, active_font=font, active_owner=owner)
    assert exc.value.code == "stale"
    assert glyph_state(font, owner.parent) == changed
    assert font.undo_depth == 0


def test_native_switching_documents_and_layers_rejects_proposals(native):
    adapter, font, owner = native
    proposal = adapter.propose(font, owner)
    with pytest.raises(RepairError): adapter.apply(proposal, active_font=font.copy(), active_owner=owner)
    with pytest.raises(RepairError): adapter.apply(proposal, active_font=font, active_owner=font.glyphs["test"].layers[1])


def test_native_inert_star_excess_deviation_and_alternate_families_refuse(native):
    adapter, font, owner = native
    owner.paths[0].inert = True
    with pytest.raises(RepairError) as exc: adapter.propose(font, owner)
    assert exc.value.code == "continuity_failed"
    owner.paths[0].inert = False
    owner.paths[0].nodes[4].position = (20., 0.)
    with pytest.raises(RepairError) as exc: adapter.propose(font, owner)
    assert exc.value.code == "excess_deviation"
    owner.attributes["axisRules"] = {"unknown-axis": {"min": .5}}
    with pytest.raises(RepairError) as exc: adapter.propose(font, owner)
    assert exc.value.code == "native_unqualified"


def test_native_partial_coordinate_failure_restores_exact_state_and_precision(native):
    adapter, font, owner = native
    proposal = adapter.propose(font, owner, method="supertool-handles", all_layers=True)
    before = glyph_state(font, owner.parent)
    owner.paths[0].nodes[4].write_failure = True
    with pytest.raises(RuntimeError, match="injected"):
        adapter.apply(proposal, active_font=font, active_owner=owner)
    assert glyph_state(font, owner.parent) == before
    assert font.undo_depth == 0
    assert not any(l.temporarilyDisableRounding for l in owner.parent.layers)


def test_native_multi_axis_coverage_and_cancelled_preview_do_not_mutate_source(native):
    adapter, _, _ = native
    font = Font(axes=2); owner = font.glyphs["test"].layers[0]
    before = glyph_state(font, owner.parent)
    task = adapter.propose_steps(font, owner, all_layers=True)
    next(task); task.close()
    assert glyph_state(font, owner.parent) == before
    assert adapter.propose(font, owner, all_layers=True).report["coverage"]["evaluated"] == 41


def test_exact_attributes_are_order_independent_and_unknown_objects_refused():
    assert freeze({"b": [1., 2.], "a": True}) == freeze({"a": True, "b": [1., 2.]})
    with pytest.raises(RepairError): freeze({"hoi": object()})


def test_alternate_source_layers_and_boundary_locations_are_not_omitted(native):
    adapter, font, owner = native
    glyph = owner.parent
    for master in font.masters:
        alt = Layer("alternate-" + master.id)
        alt.associatedMasterId = master.id
        alt.attributes["axisRules"] = {"0": {"min": .5}}
        alt.isSpecialLayer = True; alt.parent = glyph
        glyph.layers.append(alt)
    proposal = adapter.propose(font, owner, all_layers=True)
    assert len(proposal.edits) == 4
    coverage = proposal.report["coverage"]
    assert len(coverage["families"]) == 2
    assert (.5-1e-6,) in coverage["locations"] and (.5+1e-6,) in coverage["locations"]
    assert sum(map(len, coverage["familyLayers"].values())) == 4
