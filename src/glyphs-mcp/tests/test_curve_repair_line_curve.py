"""Line/curve controls and recorded 4108 drawing fixtures; not host emulation."""
import math
from types import SimpleNamespace

import pytest

from test_curve_repair import Font, Node, NativeAdapter, Instance
from curve_repair.geometry import RepairError, chain_deviation, split
from curve_repair.joins import source_join, drawing_chain, line_cubic
from curve_repair.native import glyph_state

APP = SimpleNamespace(__name__="double", LINE="line", CURVE="curve", OFFCURVE="offcurve",
                      GSSHARP=100, GSSMOOTH=101, GSSUPERSMOOTH=102, GSInstance=Instance)
GOLDEN = (((-36.69555850633359, 0.), (-8.009490419468618, 0.), (12.763179574468086, 0.), (34.77048970341374, 7.677176503131396)),
          ((34.77048970341374, 7.677176503131396), (72.55734041186345, 20.858992939874746), (126.28, 55.768), (200., 100.)))


class RaindropPath:
    def __init__(self, reverse=False, closed=False, length=200):
        self.reverse, self.closed = reverse, closed
        self.locked, self.attributes, self.omit, self.inert = False, {}, False, False
        pts = [(-length/10, 0.), (0., 0.), (4., 0.), (10., 4.), (20., 10.)]
        kinds = ["line", "line", "offcurve", "offcurve", "curve"]
        if reverse: pts.reverse(); kinds = ["line", "offcurve", "offcurve", "curve", "line"]
        self.nodes = [Node(p, k, 101 if p == (0., 0.) else 100) for p, k in zip(pts, kinds)]
        self.join = 3 if reverse else 1
    @property
    def bezierPath(self):
        points = [(n.position.x, n.position.y) for n in self.nodes]
        if self.reverse:
            edges = [("curve", tuple(points[:4])), ("line", line_cubic(*points[3:]))]
        else:
            edges = [("line", line_cubic(*points[:2])), ("curve", tuple(points[1:]))]
        if self.nodes[self.join].connection == 102 and not self.inert:
            curves = [tuple((x/10, y/10) for x, y in c) for c in GOLDEN]
            line = line_cubic(points[0], curves[0][0]) if not self.reverse else line_cubic(curves[0][0], points[-1])
            edges = [("line", line), *(("curve", c) for c in curves)] if not self.reverse else [*(("curve", tuple(reversed(c))) for c in reversed(curves)), ("line", line)]
        if self.omit: edges.pop(0)
        if self.closed: edges.insert(0, ("line", line_cubic(points[-1], points[0])))
        parent = getattr(self, "parent", None)
        step = getattr(getattr(getattr(parent, "parent", None), "parent", None), "gridLength", 0.)
        if parent is not None and parent.temporarilyDisableRounding: step = 0
        def native(p):
            if step: p = tuple(math.floor(v/step+.5)*step for v in p)
            return SimpleNamespace(x=p[0], y=p[1])
        elements = [(0, (native(edges[0][1][0]),))]
        for kind, curve in edges: elements.append((1 if kind == "line" else 2, tuple(native(p) for p in (curve[-1:] if kind == "line" else curve[1:]))))
        if self.closed: elements.extend(((3, ()), (0, elements[0][1])))
        return SimpleNamespace(elementCount=lambda: len(elements), elementAtIndex_associatedPoints_=lambda i: elements[i])


def fixture(reverse=False, closed=False, length=200, grid=0):
    font = Font(); font.gridLength = grid
    for layer in font.glyphs["test"].layers:
        path = RaindropPath(reverse, closed, length); path.parent = layer
        layer.paths = [path]; layer.selection = [path.nodes[path.join]]
    return NativeAdapter(APP), font, font.glyphs["test"].layers[0]


@pytest.mark.parametrize("reverse,closed", [(False, False), (True, False), (False, True), (True, True)])
def test_one_selected_node_resolves_both_segments_and_applies_raindrop(reverse, closed):
    adapter, font, layer = fixture(reverse, closed)
    path = layer.paths[0]
    left, right = source_join(path, path.join, APP)
    assert {left.kind, right.kind} == {"line", "curve"}
    assert adapter.selected_joins(layer) == ((0, path.join),)
    state = glyph_state(font, layer.parent)
    proposal = adapter.propose(font, layer, all_layers=True)
    assert glyph_state(font, layer.parent) == state
    assert proposal.report["storedCoordinatesPreserved"] and len(proposal.edits) == 2
    assert proposal.report["integratedDifferenceEm2"] is None
    assert proposal.report["coverage"]["evaluated"] == 9
    assert all(d["after"]["g2"] for d in proposal.report["diagnostics"])
    assert all(g["construction"]["g1"] for d in proposal.report["diagnostics"] for g in d["generatedJoins"])
    assert adapter.apply(proposal, active_font=font, active_owner=layer)["status"] == "verified"
    assert adapter.propose(font, layer, all_layers=True).report["status"] == "noop"
    assert not layer.temporarilyDisableRounding and font.undo_depth == 0


def test_short_line_inert_transition_and_unmapped_expansion_refuse():
    adapter, font, layer = fixture(length=2)
    with pytest.raises(RepairError) as exc: adapter.propose(font, layer)
    assert exc.value.code == "short_line"
    adapter, font, layer = fixture()
    layer.paths[0].inert = True
    with pytest.raises(RepairError) as exc: adapter.propose(font, layer)
    assert exc.value.code == "native_unqualified"
    path = RaindropPath(); path.omit = True
    with pytest.raises(RepairError): drawing_chain(path, path.bezierPath, APP)


def test_handle_method_and_mixed_incomplete_selection_are_explicit():
    adapter, font, layer = fixture()
    with pytest.raises(RepairError) as exc: adapter.propose(font, layer, method="supertool-handles")
    assert exc.value.code == "unsupported_method" and "Native super-smooth" in str(exc.value)
    endpoint = layer.paths[0].nodes[0]; endpoint.connection = 101
    layer.selection.append(endpoint)
    with pytest.raises(RepairError) as exc: adapter.selected_joins(layer)
    assert exc.value.code == "coverage_incomplete" and "1 eligible, 1 blocked" in str(exc.value)
    assert adapter.selected_joins(layer, all_joins=True) == ((0, 1),)


def test_chain_bound_accepts_exact_subdivision_and_rejects_translation():
    a = ((0., 0.), (1., 0.), (2., 1.), (3., 1.))
    bound = chain_deviation((a,), split(a), 1000, .001)
    assert bound["upper"] < .001
    shifted = tuple((x, y+2) for x, y in a)
    with pytest.raises(RepairError) as exc: chain_deviation((a,), (shifted,), 1000, .001)
    assert exc.value.code == "excess_deviation"
    with pytest.raises(RepairError) as exc: chain_deviation((a,), split(a), 1000, .001, budget=1)
    assert exc.value.code == "unresolved_deviation"


def test_implicit_close_line_is_counted_and_malformed_closures_still_refuse():
    class ImplicitClose(RaindropPath):
        @property
        def bezierPath(self):
            bp = super().bezierPath
            items = [bp.elementAtIndex_associatedPoints_(i) for i in range(bp.elementCount())]
            # Reverse closed fixture's final line is represented by AppKit close.
            assert items[-3][0] == 1
            del items[-3]
            return SimpleNamespace(elementCount=lambda: len(items), elementAtIndex_associatedPoints_=lambda i: items[i])
    path = ImplicitClose(reverse=True, closed=True)
    path.nodes[path.join].connection = 102
    chain = drawing_chain(path, path.bezierPath, APP)
    assert len(chain.curves) == 4 and chain.curves[-1][-1] == chain.curves[0][0]
    path.closed = False
    # A close operation never turns an explicitly open source into a closed one.
    with pytest.raises(RepairError): drawing_chain(path, chain_as_closed_bezier(chain), APP)


def chain_as_closed_bezier(chain):
    def p(xy): return SimpleNamespace(x=xy[0], y=xy[1])
    items = [(0, (p(chain.curves[0][0]),))]
    items += [(2, tuple(p(xy) for xy in c[1:])) for c in chain.curves]
    items.append((3, ()))
    return SimpleNamespace(elementCount=lambda: len(items), elementAtIndex_associatedPoints_=lambda i: items[i])


def test_corners_locks_and_quadratics_are_not_implicitly_converted():
    adapter, font, layer = fixture()
    node = layer.paths[0].nodes[1]
    node.connection = APP.GSSHARP
    with pytest.raises(RepairError) as exc: adapter.propose(font, layer)
    assert exc.value.code == "deliberate_corner" and node.connection == APP.GSSHARP
    node.connection = APP.GSSMOOTH; node.locked = True
    with pytest.raises(RepairError) as exc: adapter.propose(font, layer)
    assert exc.value.code == "locked_target"
    node.locked = False; layer.paths[0].nodes[-1].type = "qcurve"
    with pytest.raises(RepairError) as exc: adapter.propose(font, layer)
    assert exc.value.code == "unsupported_segment"


def test_source_and_drawing_precision_are_restored_on_failed_bound():
    adapter, font, layer = fixture(grid=1)
    before = glyph_state(font, layer.parent)
    with pytest.raises(RepairError): adapter.propose(font, layer, tolerance_em=.000001)
    assert glyph_state(font, layer.parent) == before and not layer.temporarilyDisableRounding
