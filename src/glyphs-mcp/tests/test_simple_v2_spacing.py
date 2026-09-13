"""Lean spacing benefit tests and compact-patch integration."""

from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[3]
for part in ('sidecar', 'bridge', 'protocol'):
    sys.path.insert(0, str(ROOT / 'src' / part))
from glyphs_mcp_sidecar import spacing, spacing_job, native_worker
from glyphs_mcp_sidecar.service import SidecarService, ServiceError
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
from glyphs_mcp_bridge.core import BridgeCore
from test_simple_v2_glyphs_adapter import PositionNode


class Collection(dict):
    def __getitem__(self, key): return self.get(key)
    def __iter__(self): return iter(self.values())


class Layer:
    layerId = associatedMasterId = 'M1'
    components = anchors = ()
    isAligned = False
    leftMetricsKey = rightMetricsKey = widthMetricsKey = None

    def __init__(self, width=600.125, height=700, edge=None):
        self.width, self.height = width, height
        self.edge = edge or (lambda y: (0.0, width))
        self.paths = [NS(nodes=[PositionNode()])]
        self.temporarilyDisableRounding = False

    @property
    def offset(self): return self.paths[0].nodes[0].position.x

    @property
    def bounds(self):
        return NS(origin=NS(x=self.offset,y=0.0),size=NS(width=self.edge(self.height)[1],height=self.height))

    def intersectionsBetweenPoints(self, p1, p2, components=True):
        assert components
        if not 0 <= p1[1] <= self.height: return []
        a,b=self.edge(p1[1])
        return [NS(x=p1[0]), NS(x=a+self.offset), NS(x=b+self.offset), NS(x=p2[0])]

    def copy(self): return deepcopy(self)
    def applyTransform(self, transform):
        self.paths[0].nodes[0].position.x += transform[4]
    def setTemporarilyDisableRounding_(self,v): self.temporarilyDisableRounding=v


def glyph(name, **kwargs):
    layer=Layer(**kwargs)
    return NS(name=name, layers=Collection(M1=layer), category='', subCategory='', unicode=None,
              leftMetricsKey=None, rightMetricsKey=None, widthMetricsKey=None)


def font(*glyphs):
    return NS(glyphs=Collection({g.name:g for g in glyphs}), masters=Collection(M1=NS(xHeight=500)),
              upm=1000, customParameters={}, familyName='Disposable', filepath='/tmp/Disposable.glyphs',
              parent=NS(isDocumentEdited=lambda:False,changeCount=lambda:0,undoManager=lambda:None))


def options(**kw): return spacing.validate_options(kw)


@pytest.mark.parametrize('step', [5, 1, .5])
def test_outer_boundary_degeneracy_does_not_add_area_to_rectangle(step):
    g=glyph('A',width=600.125,height=700.5,edge=lambda y:(0,400.5))
    l=g.layers['M1']; original=l.intersectionsBetweenPoints; calls=[]
    def intersections(p1,p2,components=True):
        calls.append(p1[1])
        hits=original(p1,p2,components)
        return [hits[0],hits[1],hits[-1]] if p1[1] in (0,l.height) else hits
    l.intersectionsBetweenPoints=intersections
    f=font(g);r=spacing.suggest(f,g,l,options(reference='*',area=400.125,sampleStep=step))
    assert r['after']['lsb']==pytest.approx(80.025,abs=1e-9,rel=0)
    assert r['after']['rsb']==pytest.approx(80.025,abs=1e-9,rel=0)
    assert sum(y in (0.00001,l.height-0.00001) for y in calls)==2


def test_sampling_does_not_fill_interior_gaps_or_reference_margins():
    l=Layer(height=10);original=l.intersectionsBetweenPoints;calls=[]
    def intersections(p1,p2,components=True):
        calls.append(p1[1])
        return [] if 4<=p1[1]<=6 else original(p1,p2,components)
    l.intersectionsBetweenPoints=intersections
    ys,edges=spacing.sampled_edges(l,-5,15,5)
    assert ys==[-5,0,5,10,15] and edges[0] is None and edges[2] is None and edges[4] is None
    assert calls==ys


def test_unresolved_boundary_probe_remains_missing_evidence():
    l=Layer(height=10)
    l.intersectionsBetweenPoints=lambda *args,**kwargs: [NS(x=0),NS(x=1),NS(x=2)]
    _,edges=spacing.sampled_edges(l,0,10,5)
    assert edges==[None,None,None]


def test_detached_measurement_retains_glyph_context_without_inserting_a_layer():
    original=Layer();owner=NS(layers=[original]);original.parent=owner
    clone=Layer();clone.parent=None
    original.copy=lambda:clone
    assert spacing.exact_copy(original).parent is owner
    assert owner.layers==[original] and original.temporarilyDisableRounding is False


@pytest.mark.parametrize('name', ['V','W','Y'])
def test_uppercase_reference_avoids_the_demonstrated_diagonal_extremes(name):
    g=glyph(name,width=1000,edge=lambda y:(450*(1-y/700),550+450*y/700))
    f=font(g,glyph('H'),glyph('x',height=500))
    old=spacing.suggest(f,g,g.layers['M1'],options(reference='x'))
    new=spacing.suggest(f,g,g.layers['M1'],options())
    assert min(old['after']['lsb'],old['after']['rsb']) < -50
    assert min(new['after']['lsb'],new['after']['rsb']) > -50
    assert new['selectedReference']=='H' and new['fallback'] is None
    assert old['selectedReference']=='x'


def test_explicit_per_glyph_reference_overrides_default_and_missing_does_not_fallback():
    g=glyph('A');f=font(g,glyph('H'),glyph('x',height=500))
    row=spacing.suggest(f,g,g.layers['M1'],options(references={'A':'x'}))
    assert row['selectedReference']=='x' and row['requestedReference']=='x'
    with pytest.raises(ValueError,match='explicit reference'):
        spacing.suggest(f,g,g.layers['M1'],options(reference='Missing'))


def test_auto_reference_fallback_includes_the_selected_name_and_reason():
    g=glyph('A');f=font(g,glyph('x',height=500))
    row=spacing.suggest(f,g,g.layers['M1'],options())
    assert row['selectedReference']=='x'
    assert row['fallback']=={'preferred':'H','reason':'preferred_reference_unavailable'}


@pytest.mark.parametrize('mode', ['equal_figures','tabular_name','fixed_pitch','explicit'])
def test_preservation_retains_each_exact_fractional_width(mode):
    figures=[glyph(name,width=600.125+i/10) for i,name in enumerate(spacing.FIGURES)]
    f=font(*figures);g=figures[7]
    if mode=='tabular_name': g.name='seven.tf'
    if mode=='fixed_pitch': f.customParameters['isFixedPitch']=True
    row=spacing.suggest(f,g,g.layers['M1'],options(widthMode='preserve' if mode=='explicit' else 'auto'))
    assert row['after']['width']==g.layers['M1'].width
    assert row['after']['lsb']+spacing.bounds(g.layers['M1'])[2]+row['after']['rsb']==pytest.approx(g.layers['M1'].width)
    assert row['preservedWidthReason']


def test_zero_width_and_nonspacing_marks_generate_no_changes():
    g=glyph('acutecomb',width=0);other=glyph('mark',width=0.125);other.category='Mark'
    changes,report=spacing_job.prepare(font(g,other),{'kind':'spacing','options':{}})
    assert changes==[]
    assert all(row['status']=='preserved' for row in report['layers'])


def test_existing_metrics_keys_and_native_alignment_are_preserved_by_workflow():
    g=glyph('A');g.leftMetricsKey='H'
    c=glyph('Aacute');c.layers['M1'].isAligned=True
    changes,report=spacing_job.prepare(font(g,c),{'kind':'spacing','options':{}})
    assert changes==[]
    assert [r['reason'] for r in report['layers']]==['metrics_keys','native_component_alignment']


@pytest.mark.parametrize('effective', [2, 3])
def test_mixed_component_alignment_is_preserved_even_when_layer_is_not_aligned(effective):
    g = glyph('mixedAssembly')
    layer = g.layers['M1']
    layer.components = [NS(automaticAlignment=True, effectiveAlignment=lambda: effective),
                        NS(automaticAlignment=False, effectiveAlignment=-2)]
    assert not layer.isAligned
    changes, report = spacing_job.prepare(font(g, glyph('x')), {'kind': 'spacing', 'glyphs': [g.name]})
    assert changes == []
    assert report['layers'][0]['status'] == 'preserved'
    assert report['layers'][0]['reason'] == 'native_component_alignment'


def test_configured_alignment_without_native_positioning_does_not_exclude_spacing():
    g = glyph('mixedOutline')
    layer = g.layers['M1']
    layer.components = [NS(automaticAlignment=True, effectiveAlignment=-2)]
    row = spacing.suggest(font(g, glyph('x')), g, layer, options())
    assert row['status'] == 'suggested'


def test_alignment_falls_back_to_configuration_when_effective_api_is_unavailable():
    g = glyph('legacyAssembly')
    layer = g.layers['M1']
    layer.components = [NS(automaticAlignment=True)]
    row = spacing.suggest(font(g, glyph('x')), g, layer, options())
    assert row['reason'] == 'native_component_alignment'


def test_native_position_readback_cannot_be_hidden_by_outline_hash_precision(monkeypatch):
    class NativePosition(PositionNode):
        @PositionNode.position.setter
        def position(self, point):
            if hasattr(self, '_position') and abs(point[0] - self._position.x) < .003:
                return
            self._position = NS(x=point[0], y=point[1])
    g = glyph('fractionalPosition')
    layer = g.layers['M1']
    layer.paths[0].nodes = [NativePosition(100, 0)]
    monkeypatch.setattr(spacing, 'suggest', lambda *_: {
        'glyph': g.name, 'layer': 'M1', 'status': 'suggested', 'dx': .002,
        'before': {'width': layer.width}, 'after': {'width': layer.width + 10}})
    changes, report = spacing_job.prepare(font(g), {'kind': 'spacing'})
    assert changes == []  # Do not publish a width write after translation failed.
    assert report['layers'][0]['status'] == 'unavailable'
    assert 'exact' in report['layers'][0]['reason']


def test_spacing_patch_applies_fractional_bearings_and_discards_exact_geometry(monkeypatch,tmp_path):
    g=glyph('V',width=1000,edge=lambda y:(450*(1-y/700),550+450*y/700))
    f=font(g,glyph('H'),glyph('x',height=500));layer=g.layers['M1']
    adapter=GlyphsAdapter(NS(fonts=[f]));doc=adapter.list_documents()[0]
    monkeypatch.setattr(native_worker,'_load_font',lambda _:f)
    patch=native_worker.build_patch({'request':{'kind':'spacing','glyphs':['V'],'options':{'area':400.125}},
        'source':f.filepath,'sourceHash':'sha256:'+'a'*64,'jobId':'job_spacing','document':doc,'output':str(tmp_path/'patch.json')})
    baseline=(layer.width,adapter._outline_hash(layer));pending=[]
    bridge=BridgeCore(adapter,schedule=pending.append)
    bridge.begin_apply(patch)
    while pending: pending.pop(0)()
    assert bridge.operation('job_spacing')['status']=='applied'
    report=__import__('json').loads((tmp_path/'report.json').read_text())['layers'][0]
    assert layer.bounds.origin.x==pytest.approx(report['after']['lsb'],abs=1e-12)
    assert layer.width-layer.bounds.origin.x-layer.bounds.size.width==pytest.approx(report['after']['rsb'],abs=1e-12)
    assert not layer.width.is_integer() and not layer.bounds.origin.x.is_integer()
    bridge.discard('job_spacing')
    while pending: pending.pop(0)()
    assert bridge.operation('job_spacing')['status']=='discarded'
    assert (layer.width,adapter._outline_hash(layer))==baseline


@pytest.mark.parametrize('bad',[{'reference':''},{'references':{'A':3}},{'area':float('nan')},{'sampleStep':0},{'masters':'M1'},{'arbitrary':True}])
def test_spacing_options_rejected_before_worker_creation(bad):
    with pytest.raises(ServiceError): SidecarService._job_request('spacing',None,['V'],bad)


@pytest.mark.parametrize('shift,translated', [(0.000999, False), (0.001, False), (0.001001, True), (-0.001, False), (-0.001001, True)])
def test_spacing_tolerance_keeps_material_width_independent(monkeypatch, shift, translated):
    g = glyph('tolerance')
    layer = g.layers['M1']
    monkeypatch.setattr(spacing, 'suggest', lambda *_: {
        'glyph': g.name, 'layer': 'M1', 'status': 'suggested', 'dx': shift,
        'before': {'width': layer.width, 'lsb': 0, 'rsb': 0},
        'after': {'width': layer.width + 10, 'lsb': shift, 'rsb': 10-shift}})
    changes, report = spacing_job.prepare(font(g), {'kind': 'spacing'})
    assert [c['kind'] for c in changes] == (['translate', 'set'] if translated else ['set'])
    assert changes[-1]['after'] == layer.width + 10
    row = report['layers'][0]
    assert row['dx'] == (shift if translated else 0)
    assert row['after']['lsb'] == (shift if translated else 0)
    assert row['after']['rsb'] == (10-shift if translated else 10)


def test_insignificant_spacing_is_a_noop_without_native_setters(monkeypatch):
    g = glyph('noEffectiveChange')
    monkeypatch.setattr(spacing, 'suggest', lambda *_: {
        'glyph': g.name, 'layer': 'M1', 'status': 'suggested', 'dx': 1e-13,
        'before': {'width': 0, 'lsb': 0, 'rsb': 0},
        'after': {'width': .001, 'lsb': 1e-13, 'rsb': .001-1e-13}})
    changes, report = spacing_job.prepare(font(g), {'kind': 'spacing'})
    assert changes == []
    assert report['layers'][0]['status'] == 'preserved'
    assert report['layers'][0]['reason'] == 'below_tolerance'
    assert report['layers'][0]['after'] == report['layers'][0]['before']
