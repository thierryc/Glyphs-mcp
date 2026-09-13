"""Retained landmark benefit and native-reorder bridge contracts."""

from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

ROOT=Path(__file__).resolve().parents[3]
for part in ('sidecar','bridge','protocol'):sys.path.insert(0,str(ROOT/'src'/part))
from glyphs_mcp_sidecar import correspondence, start_node_job, native_worker
from glyphs_mcp_sidecar.worker import WorkerError, WORKER_ERROR_PREFIX
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
from glyphs_mcp_bridge.core import BridgeCore
import test_cyclic_path_alignment_engine as legacy
from test_simple_v2_spacing import Collection


class TestRetainedLandmarkBenefit(legacy.CyclicPathAlignmentEngineTests):
    @classmethod
    def setUpClass(cls):cls.engine=correspondence


class PathModel:
    closed=True
    direction=1
    def __init__(self,points,rotation):
        nodes=[NS(position=NS(x=x,y=y),type='line',smooth=False,userData={'identity':i}) for i,(x,y) in enumerate(points)]
        self.nodes=nodes[rotation:]+nodes[:rotation]
    def makeNodeFirst_(self,node):
        i=next(i for i,n in enumerate(self.nodes) if n is node)+1
        self.nodes=self.nodes[i:]+self.nodes[:i]


class Layer:
    components=anchors=()
    width=600.125
    temporarilyDisableRounding=False
    def __init__(self,mid,points,rotation):
        self.layerId=self.associatedMasterId=mid
        self.paths=[PathModel(points,rotation)]
        self.hints=[NS(originNode=self.paths[0].nodes[1],targetNode=self.paths[0].nodes[2])]
    def copy(self):return deepcopy(self)
    def setTemporarilyDisableRounding_(self,v):self.temporarilyDisableRounding=v


def fixture():
    layers=Collection({mid:Layer(mid,pts,r) for mid,pts,r in [
        ('M1',[(0,0),(100,0),(100,100),(0,100)],0),
        ('M2',[(20,30),(220,30),(220,230),(20,230)],2),
        ('M3',[(0,0),(50,0),(50,150),(0,150)],1)]})
    return NS(glyphs=Collection(A=NS(name='A',layers=layers)),masters=Collection({m:NS(id=m) for m in layers.keys()}),
        filepath='/tmp/Start.glyphs',parent=NS(isDocumentEdited=lambda:False,changeCount=lambda:0,undoManager=lambda:None))


def test_worker_native_bridge_preserves_reference_phase_metadata_hints_and_discard(tmp_path,monkeypatch):
    font=fixture();layers=list(font.glyphs['A'].layers)
    before=[list(l.paths[0].nodes) for l in layers]
    hints=[(l.hints[0].originNode,l.hints[0].targetNode) for l in layers]
    request={'kind':'start_nodes','glyphs':['A'],'options':{'referenceMaster':'M1','referenceNode':0}}
    adapter=GlyphsAdapter(NS(fonts=[font]));doc=adapter.list_documents()[0]
    monkeypatch.setattr(native_worker,'_load_font',lambda path:font)
    patch=native_worker.build_patch({'request':request,'document':doc,'source':font.filepath,
        'sourceHash':'sha256:'+'a'*64,'jobId':'start-test','output':str(tmp_path/'patch.json')})
    assert [c['shift'] for c in patch['changes']]==[2,3]
    queue=[];core=BridgeCore(adapter,queue.append);core.begin_apply(patch)
    while queue:queue.pop(0)()
    assert core.operation(patch['jobId'])['status']=='applied'
    assert layers[0].paths[0].nodes==before[0]
    assert [[n.userData['identity'] for n in l.paths[0].nodes] for l in layers]==[[0,1,2,3]]*3
    for i,l in enumerate(layers):
        assert {id(n) for n in l.paths[0].nodes}=={id(n) for n in before[i]}
        assert (l.hints[0].originNode,l.hints[0].targetNode)==hints[i]
        assert not l.temporarilyDisableRounding and l.width==600.125
    assert start_node_job.prepare(font,request)[0]==[]
    core.discard(patch['jobId'])
    while queue:queue.pop(0)()
    assert core.operation(patch['jobId'])['status']=='discarded'
    assert [l.paths[0].nodes for l in layers]==before


@pytest.mark.parametrize('failure',['ambiguous','incompatible','open'])
def test_rejected_correspondence_produces_no_partial_patch(failure):
    font=fixture();g=font.glyphs['A']
    if failure=='ambiguous':
        for l in g.layers:l.paths[0].nodes+=deepcopy(l.paths[0].nodes)
    elif failure=='incompatible':g.layers['M3'].paths[0].nodes.pop()
    else:g.layers['M3'].paths[0].closed=False
    before=deepcopy([[vars(n.position) for n in l.paths[0].nodes] for l in g.layers])
    with pytest.raises(WorkerError):start_node_job.prepare(font,{'glyphs':['A']})
    assert [[vars(n.position) for n in l.paths[0].nodes] for l in g.layers]==before


@pytest.mark.parametrize('types,code,index', [
    (['curve','line','line'], 'malformed_segment', 0),
    (['line','offcurve','curve'], 'malformed_segment', 2),
    (['offcurve','offcurve','offcurve','curve','line'], 'malformed_segment', 3),
    (['line','offcurve','line'], 'malformed_segment', 2),
    (['qcurve','line'], 'unsupported_node_type', 0),
    (['line','offcurve'], 'unsupported_native_boundary', 1),
])
def test_malformed_native_segments_are_located_before_correspondence(types,code,index,monkeypatch):
    font=fixture()
    for layer in font.glyphs['A'].layers:
        layer.paths[0].nodes=[NS(position=NS(x=i,y=i*i),type=t,smooth=False) for i,t in enumerate(types)]
    monkeypatch.setattr(start_node_job,'plan_joint_alignment',lambda *a,**k:pytest.fail('must reject before correspondence, even an aligned no-op'))
    with pytest.raises(WorkerError) as error:start_node_job.prepare(font,{'glyphs':['A']})
    message=str(error.value)
    assert f'start_nodes.{code}' in message and '"glyph": "A"' in message
    assert '"layer": "M1"' in message and '"path": 0' in message and f'"node": {index}' in message
    assert len(message)<600


@pytest.mark.parametrize('types',[
    ['line','line','line'],
    ['line','offcurve','offcurve','curve','line'],
    ['offcurve','offcurve','curve','line','line'],
    ['offcurve','offcurve','curve','offcurve','offcurve','curve'],
])
def test_valid_native_segment_boundaries(types):
    start_node_job._validate_contour([{'type':t} for t in types],True,glyph='A',layer='M1',path=0)


def test_late_malformed_glyph_never_emits_an_applicable_patch(tmp_path,monkeypatch,capsys):
    import json
    font=fixture();font.glyphs['B']=deepcopy(font.glyphs['A']);font.glyphs['B'].name='B'
    font.glyphs['B'].layers['M3'].paths[0].nodes[0].type='curve'
    monkeypatch.setattr(native_worker,'_load_font',lambda path:font)
    before=deepcopy([[vars(n) for n in l.paths[0].nodes] for g in font.glyphs for l in g.layers])
    payload={'request':{'kind':'start_nodes','glyphs':['A','B']},'source':'unused','output':str(tmp_path/'patch.json')}
    request=tmp_path/'request.json';request.write_text(json.dumps(payload))
    assert native_worker.main([str(request)])==1
    error=capsys.readouterr().err
    assert error.startswith(WORKER_ERROR_PREFIX) and 'Traceback' not in error
    assert 'malformed_segment' in error and 'M3' in error
    assert not (tmp_path/'patch.json').exists() and not (tmp_path/'report.json').exists()
    assert [[vars(n) for n in l.paths[0].nodes] for g in font.glyphs for l in g.layers]==before


def test_unexpected_native_failure_retains_diagnostic_path(tmp_path,monkeypatch):
    import json
    font=fixture();font.glyphs['A'].layers['M1'].paths[0].nodes[0].position=None
    monkeypatch.setattr(native_worker,'_load_font',lambda path:font)
    p=tmp_path/'request.json';p.write_text(json.dumps({'request':{'kind':'start_nodes','glyphs':['A']},'source':'unused','output':str(tmp_path/'patch.json')}))
    with pytest.raises(AttributeError):native_worker.main([str(p)])
    assert not (tmp_path/'patch.json').exists()
