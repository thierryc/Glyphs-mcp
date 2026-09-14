"""Bounded native-read doubles; native qualification is recorded separately."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'src/companions/curve-inspector/glyphs_curve_inspector/plugin.py'
NAMESPACE = dict(CURVE='curve', OFFCURVE='offcurve')
TREE = ast.parse(SOURCE.read_text())
FUNCTIONS = [n for n in TREE.body if isinstance(n, ast.FunctionDef)]
exec(compile(ast.Module(body=FUNCTIONS, type_ignores=[]), str(SOURCE), 'exec'), NAMESPACE)
extract = NAMESPACE['extract_visible_cubics']
notice = NAMESPACE['coverage_notice']


def node(x, y, kind):
    return NS(position=NS(x=x, y=y), type=kind)


def path():
    return NS(closed=False, nodes=[node(.125, .25, 'line'), node(.125, 90.5, 'offcurve'),
                                  node(90.75, 90.5, 'offcurve'), node(90.75, .25, 'curve')])


def layer(count, components=0):
    return NS(paths=[path() for _ in range(count)], components=[object() for _ in range(components)])


@pytest.mark.parametrize('count', [0, 1, 40, 127, 128, 129, 256])
def test_exact_and_exceeded_bound_preserve_native_values(count):
    l = layer(count, 2); before = repr(l)
    curves, c = extract(l)
    assert repr(l) == before
    assert len(curves) == min(count, 128)
    assert c['complete'] == (count <= 128)
    assert c['cubicCount'] == (count if count <= 128 else None)
    assert c['cubicCountLowerBound'] == min(count, 129)
    assert c['omittedComponentCount'] == 2
    assert c['limitReason'] == (None if count <= 128 else 'cubic_limit')
    if curves: assert curves[0] == ((.125, .25), (.125, 90.5), (90.75, 90.5), (90.75, .25))


def test_closed_wraparound_and_open_endpoint_semantics():
    a = node(.125, .25, 'curve'); b = node(80.5, 0, 'curve')
    p = NS(closed=True, nodes=[a, node(10, 70, 'offcurve'), node(70, 70, 'offcurve'), b,
                              node(70, -70, 'offcurve'), node(10, -70, 'offcurve')])
    curves, c = extract(NS(paths=[p], components=[]))
    assert curves == [((80.5, 0), (70., -70.), (10., -70.), (.125, .25)),
                      ((.125, .25), (10., 70.), (70., 70.), (80.5, 0))]
    assert c['complete']
    p.closed = False
    assert extract(NS(paths=[p], components=[]))[0] == [curves[1]]


def test_cubic_lookahead_does_not_visit_next_path():
    def paths():
        yield from [path() for _ in range(129)]
        raise AssertionError('Lookahead must stop at the 129th valid cubic')
    assert extract(NS(paths=paths(), components=[]))[1]['limitReason'] == 'cubic_limit'


def test_non_cubic_geometry_has_explicit_scan_limits():
    p = NS(closed=False, nodes=[node(i, 0, 'line') for i in range(8193)])
    curves, c = extract(NS(paths=[p], components=[]))
    assert not curves and c['limitReason'] == 'node_limit' and not c['complete']
    assert c['cubicCount'] is None and c['cubicCountLowerBound'] == 0
    curves, c = extract(NS(paths=[NS(closed=False, nodes=[]) for _ in range(513)], components=[]))
    assert c['limitReason'] == 'path_limit' and not c['complete']


def test_notices_distinguish_raw_coverage_components_and_rendering():
    _, c = extract(layer(128))
    assert notice(c, dict(samplesPerCurve=51)) == ''
    _, c = extract(layer(129, 1))
    text = notice(c, dict(samplesPerCurve=15))
    assert 'first 128 cubics; more exist' in text and '129' not in text
    assert '1 component omitted' in text and 'reduced sampling' in text and '0.12em' in text
    _, c = extract(layer(0, 2))
    assert '2 components omitted' in notice(c, {})
    assert 'partial' not in notice(c, {})  # Raw cubics complete; components explicitly omitted.
    c['omittedComponentCount'] = None
    assert 'unavailable' in notice(c, {})


def test_notice_drawing_has_no_extraction_mutation_or_full_font_access():
    method = next(n for n in ast.walk(TREE) if isinstance(n, ast.FunctionDef) and n.name=='foregroundInViewCoords')
    text = ast.unparse(method)
    for term in ('extract_visible_cubics(', 'build_curvature_comb(', '.paths', '.nodes', '.glyphs', '.save('):
        assert term not in text
    assert 'saveGraphicsState' in text and 'restoreGraphicsState' in text
    assert '_cache_layer_id' in text
    assert 'safeViewPort' in text


def test_focused_skill_metadata_and_packaged_reference():
    root = ROOT / 'skills/glyphs-mcp-outlines-docs'
    entry = (root / 'SKILL.md').read_text()
    assert 'references/curvature-display.md' in entry
    focused = (root / 'references/curvature-display.md').read_text()
    for phrase in ('Show Curve Inspector', '128 cubics', '2,000 teeth', '8,192 nodes', '512 paths',
                   '0.12em', 'Components are omitted', 'Undo/Redo', 'dirty indicator', 'text mode',
                   'Font View', 'Reuse the verified connection', 'needs updating'):
        assert phrase in focused
    meta = yaml.safe_load((root / 'agents/openai.yaml').read_text())
    assert '$glyphs-mcp-outlines-docs' in meta['interface']['default_prompt']
    assert meta['policy']['allow_implicit_invocation'] is True
    for p in root.rglob('*'):
        if p.is_file(): assert p.read_bytes() == (ROOT/'plugins/glyphs-mcp/skills'/root.name/p.relative_to(root)).read_bytes()
