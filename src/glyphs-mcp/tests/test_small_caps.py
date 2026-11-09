"""Behavior of the self-contained helper, independent of a Glyphs installation."""
import copy
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('derive_caps', ROOT/'skills/glyphs-mcp-small-caps/scripts/derive_caps.py')
caps = importlib.util.module_from_spec(spec); spec.loader.exec_module(caps)


class Named(list):
    def __getitem__(self, key):
        if isinstance(key, str):
            return next((v for v in self if getattr(v, 'name', getattr(v, 'id', None)) == key), None)
        return super().__getitem__(key)


class Layer:
    def __init__(self):
        self.shapes = [NS(nodes=[NS(position=NS(x=x,y=y), type='line', smooth=False, name=None)
                                for x,y in [(0,0),(100,0),(100,700),(0,700)]], closed=True)]
        self.anchors = [NS(name='top', position=NS(x=50,y=720))]
        self.width = 200.25; self.hints = []; self.guides = []; self.annotations = []
        self.leftMetricsKey = self.rightMetricsKey = self.widthMetricsKey = None
        self.rounding = False; self.background = None
    paths = property(lambda self: [s for s in self.shapes if hasattr(s,'nodes')])
    components = property(lambda self: [s for s in self.shapes if not hasattr(s,'nodes')])
    def copy(self): return copy.deepcopy(self)
    def temporarilyDisableRounding(self): return self.rounding
    def setTemporarilyDisableRounding_(self, flag): self.rounding = flag
    def applyTransform(self, matrix):
        a,b,c,d,tx,ty = matrix
        for item in [n for p in self.paths for n in p.nodes] + self.anchors:
            x,y = item.position.x,item.position.y
            item.position = NS(x=a*x+c*y+tx, y=b*x+d*y+ty)
    @property
    def bounds(self):
        points = [n.position for p in self.paths for n in p.nodes]
        xs,ys = [p.x for p in points],[p.y for p in points]
        return NS(origin=NS(x=min(xs),y=min(ys)), size=NS(width=max(xs)-min(xs),height=max(ys)-min(ys)))


class Glyph:
    def __init__(self,name):
        self.name=name; self.unicodes=[]; self.layers={}
        self.leftMetricsKey=self.rightMetricsKey=self.widthMetricsKey=None


@pytest.fixture
def setup(monkeypatch):
    api=NS(buildNumber=4202, filters=[])
    characters={'H':'H','AE':'Æ','Idotaccent':'İ','Germandbls':'ẞ','Aacute':'Á','Ldot':'Ŀ'}
    names={'h':'h','æ':'ae','á':'aacute','ŀ':'ldot'}
    api.glyphInfoForName=lambda name: NS(unicharString=lambda: characters[name]) if name in characters else None
    api.glyphInfoForUnicode=lambda code: NS(name=names.get(chr(int(code,16))))
    glyph=Glyph('H'); glyph.unicodes=['0048']; glyph.layers={'M1':Layer(),'M2':Layer()}
    font=NS(familyName='Test', upm=1000, glyphs=Named([glyph]), masters=Named([
        NS(id='M1',capHeight=700,xHeight=500),NS(id='M2',capHeight=700,xHeight=500)]), enabled=True)
    font.isUpdateInterfaceEnabled=lambda: font.enabled
    font.disableUpdateInterface=lambda: setattr(font,'enabled',False)
    font.enableUpdateInterface=lambda: setattr(font,'enabled',True)
    monkeypatch.setitem(sys.modules,'GlyphsApp',NS(Glyphs=api,GSGlyph=Glyph))
    request=dict(stage='inspect',masters=['M1','M2'],rows=[dict(source='H',kind='sc')],
        sets={'sc':{m:dict(height=550,scaleX=.825,offsetX=0,offsetY=0,tracking=4.25) for m in ['M1','M2']}})
    return font,api,request


def construct(setup):
    font,api,request=setup
    before=caps.run_caps(font,request,api)
    request.update(stage='construct',identity=before['identity'],expected=before['guards'])
    return caps.run_caps(font,request,api)


def test_fractional_coordinates_anchors_source_preservation_and_repeated_run(setup):
    font,api,request=setup
    source=copy.deepcopy(caps.glyph_state(font.glyphs['H'],request['masters']))
    result=construct(setup)
    assert result['created']==['h.sc'] and result['changesVerified']
    g=font.glyphs['h.sc']; layer=g.layers['M1']
    assert g.unicodes==[] and layer.width==pytest.approx(200.25*.825+8.5)
    assert layer.paths[0].nodes[1].position.x==pytest.approx(86.75)
    assert layer.anchors[0].position.y==pytest.approx(720*550/700)
    assert not layer.rounding and font.enabled
    assert caps.glyph_state(font.glyphs['H'],request['masters'])==source
    request['stage']='inspect'; inspected=caps.run_caps(font,request,api)
    request.update(stage='construct',expected=inspected['guards'])
    again=caps.run_caps(font,request,api)
    assert again['created']==[] and again['preserved']==['h.sc'] and len(font.glyphs)==2


@pytest.mark.parametrize('source,dest',[('AE','ae.sc'),('Idotaccent','idotaccent.sc'),
    ('Germandbls','germandbls.sc'),('Ldot','ldot.sc'),('Aacute','aacute.sc')])
def test_case_relationships_use_character_metadata(setup,source,dest):
    assert caps.target_name(source,'sc',setup[1])==dest


def test_unknown_or_alternate_case_requires_explicit_mapping(setup):
    with pytest.raises(ValueError): caps.target_name('A.ss01','sc',setup[1])


def test_native_empty_smart_proxy_is_not_a_smart_component():
    class EmptyProxy:
        def values(self): return None
        def __len__(self): raise TypeError('native nil collection')
    component=NS(smartComponentValues=EmptyProxy(),component=NS(axes=[]))
    assert not caps.smart_component(component)
    component.component.axes=[NS(name='Width')]
    assert caps.smart_component(component)


def test_late_stale_source_rejects_all_writes(setup):
    font,api,request=setup
    inspected=caps.run_caps(font,request,api)
    request.update(stage='construct',identity=inspected['identity'],expected=inspected['guards'])
    font.glyphs['H'].layers['M2'].paths[0].nodes[1].position.x+=1
    with pytest.raises(ValueError,match='changed'): caps.run_caps(font,request,api)
    assert len(font.glyphs)==1


def test_duplicate_destination_and_missing_master_are_preflight_failures(setup):
    font,api,request=setup
    request['rows']*=2
    with pytest.raises(ValueError,match='duplicate destination'): caps.run_caps(font,request,api)
    request['rows']=request['rows'][:1]; request['masters']=['MISSING']
    with pytest.raises(ValueError,match='master'): caps.run_caps(font,request,api)
    assert len(font.glyphs)==1


def test_missing_dependency_fails_before_construction(setup):
    font,api,request=setup
    font.glyphs['H'].layers['M2'].shapes=[NS(componentName='missing', transform=(1,0,0,1,0,0),automaticAlignment=True)]
    with pytest.raises(ValueError,match='Missing component dependency'): caps.run_caps(font,request,api)
    assert len(font.glyphs)==1


def test_incompatible_and_irregular_open_outlines_request_human_work(setup):
    font,api,request=setup
    font.glyphs['H'].layers['M2'].paths[0].closed=False
    result=construct(setup)
    assert not result['created'] and result['skipped']==['h.sc']
    assert result['needsReview'] and len(font.glyphs)==1


def test_compensation_needs_exact_build_qualification_and_is_atomic(setup):
    font,api,request=setup
    request['sets']['sc']['M2']['offsetX']=2
    with pytest.raises(ValueError,match='qualification'): construct(setup)
    assert len(font.glyphs)==1 and font.enabled


def test_existing_manual_outline_is_preserved_and_reported_as_changed(setup):
    font,api,request=setup
    result=construct(setup)
    font.glyphs['h.sc'].layers['M1'].paths[0].nodes[0].position.x+=3
    request.update(stage='verify',expected=result['resultGuards'])
    report=caps.run_caps(font,request,api)
    assert report['changedSinceReview']==['h.sc'] and not report['changesVerified']
    assert font.glyphs['h.sc'].layers['M1'].paths[0].nodes[0].position.x==7.25


def test_report_is_task_local_create_only_and_inspection_is_non_mutating(setup,tmp_path):
    font,api,request=setup
    request['reportPath']=str(tmp_path/'handoff.json')
    result=caps.run_caps(font,request,api)
    assert Path(request['reportPath']).exists() and len(font.glyphs)==1
    with pytest.raises(ValueError,match='new absolute file'): caps.run_caps(font,request,api)
    assert not result['changesVerified']
