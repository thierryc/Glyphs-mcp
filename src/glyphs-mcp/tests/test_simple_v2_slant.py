"""Independent straight-stem benefit and explicit native-coordinate contracts."""

from collections import namedtuple
from copy import deepcopy
import math
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

ROOT=Path(__file__).resolve().parents[3]
for part in ('sidecar','bridge','protocol'):sys.path.insert(0,str(ROOT/'src'/part))
from glyphs_mcp_sidecar import slant_job, straight_stems, native_worker
from glyphs_mcp_sidecar.service import SidecarService, ServiceError
from glyphs_mcp_sidecar.worker import WorkerError, WORKER_ERROR_PREFIX
from glyphs_mcp_bridge import coordinates
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
from glyphs_mcp_bridge.core import BridgeCore
from glyphs_mcp_protocol import ProtocolError, validate_patch
from test_simple_v2_spacing import Collection

Point=namedtuple('Point','x y')


class Node:
    type='line'
    smooth=False
    def __init__(self,x,y):self.position=(x,y);self.userData={'keep':'metadata'}
    @property
    def position(self):return self._position
    @position.setter
    def position(self,value):self._position=Point(*value)


class Layer:
    layerId=associatedMasterId='M1'
    temporarilyDisableRounding=False
    width=600.125
    def __init__(self,curved=False):
        self.paths=[NS(closed=True,nodes=[Node(x+.125,y+.25) for x,y in [(0,0),(100,0),(100,800),(0,800)]])]
        if curved:
            for n in self.paths[0].nodes:n.type='curve'
        anchor=Node(50.125,800.25);anchor.name='top'
        self.anchors=Collection(top=anchor);self.components=[]
        self.hints=[NS(originNode=self.paths[0].nodes[0],targetNode=self.paths[0].nodes[1])]
    def copy(self):return deepcopy(self)
    def setTemporarilyDisableRounding_(self,v):self.temporarilyDisableRounding=v
    def slantX_origin_doCorrection_checkSelection_(self,angle,pivot,correction,selection):
        assert not correction and not selection
        for node in [n for p in self.paths for n in p.nodes]+list(self.anchors):
            node.position=(node.position.x+math.tan(math.radians(angle))*(node.position.y-pivot),node.position.y)


def fixture():
    glyphs=Collection({name:NS(name=name,layers=Collection(M1=Layer(curved))) for name,curved in [('stem',False),('curved',True)]})
    for name,automatic in [('manual',False),('automatic',True)]:
        layer=Layer();layer.paths=[]
        layer.components=[NS(componentName='stem',automaticAlignment=automatic,transform=(1,0,0,1,50.125,100.25),position=Point(50.125,100.25))]
        glyphs[name]=NS(name=name,layers=Collection(M1=layer))
    return NS(glyphs=glyphs,masters=[NS(id='M1')],upm=1000,filepath='/tmp/Slant.glyphs',
        parent=NS(isDocumentEdited=lambda:False,changeCount=lambda:0,undoManager=lambda:None))


def width(points):
    a,b,q=points[0],points[3],points[1]
    vx,vy=b[0]-a[0],b[1]-a[1]
    return abs(vx*(q[1]-a[1])-vy*(q[0]-a[0]))/math.hypot(vx,vy)


@pytest.mark.parametrize('angle',[-30,-12,3,12,30])
def test_output_coordinates_restore_perpendicular_stem_width(angle):
    layer=Layer();source=slant_job.paths(layer)
    layer.slantX_origin_doCorrection_checkSelection_(angle,350.125,False,False)
    raw=slant_job.paths(layer)
    corrected=straight_stems.compensate_stems(source,raw)
    xy=lambda p:[(n['x'],n['y']) for n in p[0]['nodes']]
    assert width(xy(raw))==pytest.approx(100*math.cos(math.radians(angle)),abs=1e-9)
    assert width(xy(corrected['paths']))==pytest.approx(100,abs=1e-9)
    assert straight_stems.topology_matches(source,corrected['paths'])


def test_curved_stems_and_unsafe_corrections_are_skipped():
    source=slant_job.paths(Layer(curved=True));candidate=deepcopy(source)
    result=straight_stems.compensate_stems(source,candidate)
    assert result['paths']==candidate and result['diagnostics']['acceptedPairCount']==0
    source=slant_job.paths(Layer());candidate=deepcopy(source)
    for node in candidate[0]['nodes']:node['x']*=2
    result=straight_stems.compensate_stems(source,candidate)
    assert result['paths']==candidate
    assert 'unsafe_width_delta' in [r['reason'] for r in result['diagnostics']['skippedPairs']]


def test_worker_bridge_optional_correction_metadata_anchors_and_exact_discard(tmp_path,monkeypatch):
    font=fixture();adapter=GlyphsAdapter(NS(fonts=[font]));doc=adapter.list_documents()[0]
    request={'kind':'slant','glyphs':['stem','curved'],'options':{'angle':12,'pivotY':300.125,'preserveStraightStems':True}}
    monkeypatch.setattr(native_worker,'_load_font',lambda p:font)
    patch=native_worker.build_patch({'request':request,'document':doc,'source':font.filepath,
        'sourceHash':'sha256:'+'a'*64,'jobId':'slant-test','output':str(tmp_path/'patch.json')})
    assert len(patch['changes'])==2
    identities=[(n,n.userData.copy()) for g in font.glyphs for l in g.layers for p in l.paths for n in p.nodes]
    hints=[(l.hints[0].originNode,l.hints[0].targetNode) for g in font.glyphs for l in g.layers]
    queue=[];core=BridgeCore(adapter,queue.append);core.begin_apply(patch)
    while queue:queue.pop(0)()
    assert core.operation(patch['jobId'])['status']=='applied'
    for change in patch['changes']:assert adapter.current_value(doc['id'],change)==change['after']
    assert width([n.position for n in font.glyphs['stem'].layers['M1'].paths[0].nodes])==pytest.approx(100,abs=1e-9)
    assert width([n.position for n in font.glyphs['curved'].layers['M1'].paths[0].nodes])==pytest.approx(100*math.cos(math.radians(12)))
    assert all(n.userData==data for n,data in identities)
    assert [(l.hints[0].originNode,l.hints[0].targetNode) for g in font.glyphs for l in g.layers]==hints
    assert all(l.width==600.125 and not l.temporarilyDisableRounding for g in font.glyphs for l in g.layers)
    core.discard(patch['jobId'])
    while queue:queue.pop(0)()
    assert core.operation(patch['jobId'])['status']=='discarded'
    for change in patch['changes']:assert adapter.current_value(doc['id'],change)==change['before']


def test_components_avoid_double_shear_and_skip_automatic_alignment():
    font=fixture();t=math.tan(math.radians(12));before=[1,0,0,1,50.125,100.25]
    one,report=slant_job.prepare(font,{'glyphs':['manual','automatic']})
    assert one[0]['after'][-1]==pytest.approx([1,0,t,1,50.125+t*100.25,100.25])
    assert report['layers'][-1]['status']=='skipped'
    both,_=slant_job.prepare(font,{'glyphs':['manual','stem']})
    manual=next(c for c in both if c['glyph']=='manual')
    assert manual['before'][-1]==before
    assert manual['after'][-1]==pytest.approx([1,0,0,1,50.125+t*100.25,100.25])


@pytest.mark.parametrize('lossy_side',['before','after'])
def test_bridge_preflights_both_component_matrices_before_writing_any_anchor(lossy_side):
    class NativeMatrix:
        componentName='stem'
        automaticAlignment=False
        def __init__(self,matrix):self._matrix=matrix
        def copy(self):return deepcopy(self)
        @property
        def transform(self):return self._matrix
        @transform.setter
        def transform(self,value):
            self._matrix=tuple(value[:2])+(value[2]*.8,)+tuple(value[3:])
    font=fixture();layer=font.glyphs['manual'].layers['M1']
    stable=(1.125,0,0,.875,50.125,100.25)
    skewed=(1.125,0,.2,.875,50.125,100.25)
    before=skewed if lossy_side=='before' else stable
    after=stable if lossy_side=='before' else skewed
    layer.components=[NativeMatrix(before)]
    change=dict(anchors=['top'],nodes=[],components=[0],before=[list(layer.anchors['top'].position),list(before)],
        after=[[123.125,456.25],list(after)],topologyHash=coordinates.signature(layer))
    with pytest.raises(ValueError,match='applied and restored exactly'):coordinates.write(layer,change)
    assert coordinates.read(layer,change)==change['before']


@pytest.mark.parametrize('mutation',['topology','coordinate'])
def test_coordinate_conflicts_do_not_overwrite_live_edits(mutation):
    font=fixture();changes,_=slant_job.prepare(font,{'glyphs':['stem']})
    layer=font.glyphs['stem'].layers['M1'];change=changes[0]
    if mutation=='topology':layer.paths[0].nodes[0].type='curve'
    else:layer.paths[0].nodes[0].position=(3.125,5.25)
    adapter=GlyphsAdapter(NS(fonts=[font]));doc=adapter.list_documents()[0]
    patch=dict(version=1,jobId='conflict',documentId=doc['id'],sourcePath=font.filepath,sourceHash='sha256:'+'a'*64,generation=0,summary='Conflict',changes=changes)
    before=slant_job.paths(layer);queue=[];core=BridgeCore(adapter,queue.append);core.begin_apply(patch)
    while queue:queue.pop(0)()
    assert core.operation('conflict')['status']=='failed'
    assert slant_job.paths(layer)==before


@pytest.mark.parametrize('bad',[{'angle':0},{'angle':31},{'angle':True},{'angle':float('nan')},{'pivotY':10001},
    {'preserveStraightStems':1},{'masters':['M1','M1']},{'unknown':True}])
def test_closed_job_options(bad):
    with pytest.raises(ServiceError):SidecarService._job_request('slant',None,['stem'],bad)


@pytest.mark.parametrize('bad',['nan','vector','duplicate','empty','index','unknown','noop'])
def test_closed_bounded_coordinate_patch(bad):
    changes,_=slant_job.prepare(fixture(),{'glyphs':['stem']});change=changes[0]
    if bad=='nan':change['after'][0][0]=float('nan')
    elif bad=='vector':change['after'][0].append(3)
    elif bad=='duplicate':change['nodes'][1]=change['nodes'][0]
    elif bad=='empty':change['before']=[]
    elif bad=='index':change['nodes'][0][0]=True
    elif bad=='unknown':change['repair']=True
    elif bad=='noop':change['after']=change['before']
    with pytest.raises(ProtocolError):
        validate_patch(dict(version=1,jobId='bad',documentId='doc',sourcePath='/tmp/Bad.glyphs',sourceHash='sha256:'+'a'*64,generation=0,summary='Bad',changes=changes))


@pytest.mark.parametrize('job_request,code,target', [
    ({'glyphs':['missing','stem']}, 'missing_glyph', '"glyph": "missing"'),
    ({'glyphs':['stem'],'options':{'masters':['unknown']}}, 'missing_master', '"master": "unknown"'),
])
def test_expected_missing_targets_are_bounded_and_leave_source_unchanged(job_request,code,target):
    font=fixture();before=deepcopy(slant_job.paths(font.glyphs['stem'].layers['M1']))
    with pytest.raises(WorkerError) as error:slant_job.prepare(font,job_request)
    message=str(error.value)
    assert 'slant.'+code in message and target in message and len(message)<500
    assert slant_job.paths(font.glyphs['stem'].layers['M1'])==before


@pytest.mark.parametrize('stage',['source','slanted'])
def test_lossy_component_is_located_and_external_worker_emits_no_partial_result(stage,tmp_path,monkeypatch,capsys):
    import json
    class LossyComponent:
        componentName='stem';automaticAlignment=False
        def __init__(self):self._transform=(1,0,.2 if stage=='source' else 0,1,50.125,100.25)
        @property
        def transform(self):return self._transform
        @transform.setter
        def transform(self,value):self._transform=tuple(value[:2])+(value[2]*.8,)+tuple(value[3:])
    font=fixture();font.glyphs['manual'].layers['M1'].components=[LossyComponent()]
    before=deepcopy({g.name:[(slant_job.paths(l),list(l.anchors['top'].position),[list(c.transform) for c in l.components]) for l in g.layers] for g in font.glyphs})
    monkeypatch.setattr(native_worker,'_load_font',lambda p:font)
    payload={'request':{'kind':'slant','glyphs':['curved','manual']},'source':'unused','output':str(tmp_path/'patch.json')}
    path=tmp_path/'request.json';path.write_text(json.dumps(payload))
    assert native_worker.main([str(path)])==1
    message=capsys.readouterr().err
    assert message.startswith(WORKER_ERROR_PREFIX) and 'Traceback' not in message
    text=json.loads(message[len(WORKER_ERROR_PREFIX):])
    assert 'slant.unsupported_component_transform' in text and '"glyph": "manual"' in text
    assert '"component": 0' in text and '"layer": "M1"' in text and f'"stage": "{stage}"' in text
    assert not (tmp_path/'patch.json').exists() and not (tmp_path/'report.json').exists()
    assert {g.name:[(slant_job.paths(l),list(l.anchors['top'].position),[list(c.transform) for c in l.components]) for l in g.layers] for g in font.glyphs}==before


def test_unexpected_slant_exception_is_not_mislabeled_as_expected(tmp_path,monkeypatch):
    import json
    font=fixture();font.glyphs['stem'].layers['M1'].paths[0].nodes[0]._position=None
    monkeypatch.setattr(native_worker,'_load_font',lambda p:font)
    path=tmp_path/'request.json';path.write_text(json.dumps({'request':{'kind':'slant','glyphs':['stem']},'source':'unused','output':str(tmp_path/'patch.json')}))
    with pytest.raises(AttributeError):native_worker.main([str(path)])
    assert not (tmp_path/'patch.json').exists()
