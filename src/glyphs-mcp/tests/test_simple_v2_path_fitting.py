"""Public synthetic polygon fixtures, coordinated reconstruction and recovery."""
import math
import sys
from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
from test_simple_v2_path_doctor import Collection, Node, PathShape
from test_simple_v2_outline_edit import Layer
from glyphs_mcp_protocol import path_fitting, outline, ProtocolError
from glyphs_mcp_protocol.polygon_fitting import fit_family_iter
from glyphs_mcp_protocol.preparation import consume, simple
from glyphs_mcp_protocol.preparation.path_doctor import path_state
from glyphs_mcp_protocol.preparation.path_fitting import prepare_iter
from glyphs_mcp_protocol.preparation.polygon_edit import project
from glyphs_mcp_bridge import outline_edit


def node(x=0,y=0):
    result=Node(x,y);result.userData={};result.attributes={}
    return result


def polygon(points):
    result=PathShape([node(x,y) for x,y in points],True)
    result.userData={};result.attributes={}
    return result


def circle(count=64,rx=100,ry=100,cx=0,clockwise=False):
    return polygon([(cx+rx*math.cos(t),ry*math.sin(t)) for t in
                    [(1 if not clockwise else -1)*i*math.tau/count for i in range(count)]])


class Glyphs(Collection):
    def __getitem__(self,key):
        if isinstance(key,str):return next((g for g in self if g.name==key),None)
        return super().__getitem__(key)


def font_fixture(factory=None):
    layers=Collection()
    for i in range(2):
        layer=Layer('M'+str(i));layer.width=500
        layer.paths=Collection(factory(i) if factory else [circle(64,ry=100+i*8)])
        layer.shapes=list(layer.paths);layers.append(layer)
    glyph=NS(name='fitTest',layers=layers)
    return NS(glyphs=Glyphs([glyph]),masters=[NS(id=l.layerId) for l in layers]),glyph


def request(**kwargs):
    return {'kind':'path_fitting','glyphs':[],'options':{
        'targets':[{'glyph':'fitTest','paths':[{'path':0}]}],**kwargs}}


@pytest.fixture(autouse=True)
def native_factory(monkeypatch):
    monkeypatch.setitem(sys.modules,'GlyphsApp',NS(GSNode=node))


def prepare(font,req=None,**kwargs):
    kwargs.setdefault('sample_validator',lambda *args:[{'genericFixture':True}])
    return consume(prepare_iter(font,req or request(),**kwargs))


def test_closed_circle_reduces_points_and_preserves_family_start_and_geometry():
    states=[path_state(circle(96)),path_state(circle(96,ry=120))]
    original=deepcopy(states)
    plans=consume(fit_family_iter(states,max_deviation=.5,keep_nodes=[24]))
    assert states==original
    assert [[(s['startNode'],s['endNode'],len(s['controls'])) for s in p['segments']] for p in plans][0]==[
        (s['startNode'],s['endNode'],len(s['controls'])) for s in plans[1]['segments']]
    for state,plan in zip(states,plans):
        assert plan['afterNodes']<plan['beforeNodes']
        assert plan['continuousSpanBound']<=.5
        op=outline.validate_operation(dict(op='fit_polygon',path=0,stateHash=outline.path_hash(state),
            segments=plan['segments'],cornerNodes=plan['cornerNodes'],maxDeviation=.5))
        result,sources=project(state,op)
        assert sources[0]==0 and 24 in sources
        assert result['nodes'][0]['x']==state['nodes'][0]['x']
        assert result['nodes'][0]['y']==state['nodes'][0]['y']
        # Independently sample each cubic against its known elliptical design.
        for segment in plan['segments']:
            a=state['nodes'][segment['startNode']];d=state['nodes'][segment['endNode']]
            if not segment['controls']:continue
            points=[(n['x'],n['y']) for n in [a,*segment['controls'],d]]
            ry=max(n['y'] for n in state['nodes'])
            for i in range(101):
                t=i/100;u=1-t
                p=[u**3*points[0][k]+3*u*u*t*points[1][k]+3*u*t*t*points[2][k]+t**3*points[3][k] for k in (0,1)]
                assert abs(math.hypot(p[0]/100,p[1]/ry)-1)<.01


def test_straight_sections_and_sharp_corners_remain_lines():
    points=[]
    for a,b in zip([(0,0),(100,0),(100,100),(0,100)],[(100,0),(100,100),(0,100),(0,0)]):
        points.extend((a[0]+(b[0]-a[0])*i/16,a[1]+(b[1]-a[1])*i/16) for i in range(16))
    state=path_state(polygon(points));plan=consume(fit_family_iter([state]))[0]
    assert plan['cornerNodes']==[0,16,32,48]
    assert plan['afterNodes']==4 and all(not s['controls'] for s in plan['segments'])


def test_detached_prepare_native_apply_exact_restore_and_stale_guard():
    font,glyph=font_fixture();before=[path_state(l.paths[0]) for l in glyph.layers]
    changes,report=prepare(font)
    assert len(changes)==2 and not report['held']
    assert report['beforeNodes']>report['afterNodes']
    assert [path_state(l.paths[0]) for l in glyph.layers]==before
    assert prepare(font)==(changes,report)
    for layer,change,state in zip(glyph.layers,changes,before):
        path=layer.paths[0];objects=list(path.nodes);snap=outline_edit.capture(layer)
        outline_edit.apply(layer,change)
        assert layer.paths[0] is path and path.nodes[0] is objects[0]
        assert outline.outline_state_hash(simple_state(layer))==change['afterHash']
        with pytest.raises(ValueError,match='stale|LINE'):outline_edit.apply(layer,change)
        outline_edit.restore(layer,snap)
        assert path_state(path)==state and list(path.nodes)==objects


def simple_state(layer):
    from glyphs_mcp_protocol.preparation.outline import _shape_state
    return _shape_state(layer)


@pytest.mark.stress
def test_infinity_like_outer_outline_preserves_two_counters():
    def shapes(i):
        outer=polygon([(180*math.cos(t),90*math.sin(t)*(.45+.55*math.cos(t)**2))
                       for t in [j*math.tau/128 for j in range(128)]])
        return [outer,circle(64,rx=32,ry=22,cx=-100,clockwise=True),circle(64,rx=32,ry=22,cx=100,clockwise=True)]
    font,glyph=font_fixture(shapes)
    req=request(targets=[{'glyph':'fitTest','paths':[{'path':i} for i in range(3)]}])
    changes,report=prepare(font,req)
    assert len(changes)==2 and not report['held'],report
    assert report['removedNodes']>0
    from glyphs_mcp_protocol.preparation.path_cleanup import topology
    for layer,change in zip(glyph.layers,changes):
        before=topology([path_state(p) for p in layer.paths],.002)
        outline_edit.apply(layer,change)
        assert topology([path_state(p) for p in layer.paths],.002)==before


@pytest.mark.parametrize('variant',['hint','lock','metadata','stroke','open','duplicate','curve','bad_landmark'])
def test_unsupported_one_master_holds_family_without_source_writes(variant):
    font,glyph=font_fixture();layer=glyph.layers[1];path=layer.paths[0];req=request()
    if variant=='hint':layer.hints=[NS(originNode=path.nodes[3])]
    if variant=='lock':path.locked=True
    if variant=='metadata':path.nodes[2].name='authored'
    if variant=='stroke':path.attributes={'strokeWidth':20}
    if variant=='open':path.closed=False
    if variant=='duplicate':path.nodes[2].position=path.nodes[1].position.x,path.nodes[1].position.y
    if variant=='curve':path.nodes[2].type='curve'
    if variant=='bad_landmark':req=request(targets=[{'glyph':'fitTest','paths':[{'path':0,'keepNodes':[999]}]}])
    before=[path_state(l.paths[0]) for l in glyph.layers]
    changes,report=prepare(font,req)
    assert not changes and report['held']
    assert [path_state(l.paths[0]) for l in glyph.layers]==before


def test_failed_intermediate_sample_holds_all_layers():
    font,glyph=font_fixture()
    def reject(*args):raise ValueError('native sample exceeds budget')
    changes,report=prepare(font,sample_validator=reject)
    assert not changes and 'sample exceeds' in report['held'][0]['reason']
    assert all(len(l.paths[0].nodes)==64 for l in glyph.layers)


def test_insufficient_tolerance_refuses_instead_of_relaxing_budget():
    state=path_state(circle(32))
    with pytest.raises(ValueError,match='no point reduction|deviation bound'):
        consume(fit_family_iter([state],max_deviation=.001))


def test_reconstruction_does_not_leave_short_polygon_edges_at_smooth_joins():
    state=path_state(circle(32))
    # A tempting partial simplification saves points by retaining seven short
    # polygon edges. Their endpoint tangents would leave visible kinks.
    try:
        plan=consume(fit_family_iter([state],max_deviation=1.))[0]
    except ValueError as exc:
        assert 'no point reduction' in str(exc)
    else:
        result,_=project(state,dict(stateHash=outline.path_hash(state),segments=plan['segments'],cornerNodes=plan['cornerNodes']))
        assert all(n['smooth'] for n in result['nodes'] if n['type']!='offcurve')


def test_extreme_precision_requests_hold_before_unbounded_sampling():
    from glyphs_mcp_protocol.path_measurements import flatten
    state=path_state(circle())
    with pytest.raises(ValueError,match='work limit'):flatten(state,step=1e-12)


def test_contract_is_explicit_closed_and_negotiated():
    from glyphs_mcp_protocol import recognized_job_capabilities
    from glyphs_mcp_sidecar.job_requests import validate
    from glyphs_mcp_sidecar.service import ServiceError
    req=request();options=path_fitting.validate_options(req['options'])
    assert path_fitting.validate_options(options)==options
    normalized=validate('path_fitting',None,None,req['options'],ServiceError)
    assert simple.eligible(normalized) and simple.validate_request(normalized)==normalized
    assert recognized_job_capabilities([path_fitting.CAPABILITY])==[path_fitting.CAPABILITY]
    for extra in ({'maxDeviation':float('nan')},{'layers':'all_masters'},{'targets':'all'},{'cornerAngle':0},{'unexpected':True}):
        with pytest.raises(ProtocolError):path_fitting.validate_options({**req['options'],**extra})


def test_projection_refuses_reordered_segments_and_removed_corners():
    state=path_state(circle());plan=consume(fit_family_iter([state]))[0]
    op=dict(op='fit_polygon',path=0,stateHash=outline.path_hash(state),segments=plan['segments'],
            cornerNodes=plan['cornerNodes'],maxDeviation=.5)
    with pytest.raises(ValueError,match='contour order'):project(state,{**op,'segments':list(reversed(op['segments']))})
    with pytest.raises(ValueError,match='protected corner'):project(state,{**op,'cornerNodes':[63]})


def test_fitting_summary_reuses_workflow_card_and_reports_counts(tmp_path):
    from glyphs_mcp_sidecar.edit_workflow_state import WorkflowStore,public_workflow
    from glyphs_mcp_sidecar.job_preparation import _mutation_report
    font,_=font_fixture();_,report=prepare(font)
    summary=_mutation_report(report,tmp_path/'report.json')
    assert summary['beforeNodes']==128 and summary['afterNodes']<128
    req=request();req['options']=path_fitting.validate_options(req['options'])
    value=WorkflowStore(tmp_path).create({'id':'doc1'},dict(kind='path_fitting'),req,'preview','key')
    value.update(state='ready',job={'report':summary,'status':'ready'})
    result=public_workflow(value)
    assert result['pathDoctor']['mode']=='path_fitting'
    assert result['pathDoctor']['report']['removedNodes']>0
    assert any(a['label']=='Apply curve fitting' for a in result['actions'])


def test_sidecar_requires_both_capabilities_and_native_preparation(tmp_path):
    from test_simple_v2_sidecar import service
    from glyphs_mcp_sidecar.service import ServiceError
    value,bridge,_=service(tmp_path)
    status={'jobCapabilities':['edit.prepare.native.v1','path.fit-curves.v1'],
            'writeCapabilities':['outline.edit.v1','outline.fit-polygon.v1']}
    bridge.status=lambda:status
    try:
        normalized=value.validate_job_request('path_fitting',options=request()['options'])
        assert normalized['kind']=='path_fitting'
        value.status_cache.refresh()
        public=value.get_status()
        assert 'path_fitting' in public['jobKinds'] and 'outline.fit-polygon.v1' in public['writeCapabilities']
        status['writeCapabilities'].remove('outline.fit-polygon.v1')
        with pytest.raises(ServiceError,match='qualified native'):value.validate_job_request('path_fitting',options=request()['options'])
        status['writeCapabilities'].append('outline.fit-polygon.v1')
        status['jobCapabilities'].remove('edit.prepare.native.v1')
        with pytest.raises(ServiceError,match='qualified native'):value.validate_job_request('path_fitting',options=request()['options'])
    finally:value.close()


def test_unqualified_bridge_rejects_preparation_and_direct_patch(monkeypatch):
    from glyphs_mcp_bridge.core import BridgeCore,BridgeError
    from glyphs_mcp_bridge import typed_preparation,path_doctor_qualification
    monkeypatch.setattr(path_doctor_qualification,'fitting_available',lambda:False)
    font,_=font_fixture();changes,report=prepare(font)
    core=BridgeCore(NS(),lambda callback:callback())
    req=request();req['options']=path_fitting.validate_options(req['options'])
    envelope=dict(jobId='job_fit',documentId='doc_fit',sourcePath='/tmp/fixture.glyphs',
                  sourceHash='sha256:'+'0'*64,generation=1,request=req)
    with pytest.raises(BridgeError,match='not qualified'):typed_preparation.begin(core,envelope,BridgeError)
    patch=simple.patch('job_fit',{'id':'doc_fit','path':'/tmp/fixture.glyphs','generation':1},envelope['sourceHash'],req,changes,report)
    with pytest.raises(BridgeError,match='qualification'):core.begin_apply(patch)


def test_fitting_native_host_gate_is_independent(monkeypatch):
    from glyphs_mcp_bridge import path_doctor_qualification as qualification,identity
    monkeypatch.setattr(qualification,'repair_available',lambda:True)
    monkeypatch.setattr(identity,'host_identity',lambda:{'identifier':'com.GeorgSeifert.Glyphs4','version':'4.2','build':'4203'})
    assert qualification.fitting_available() is False


def test_direct_outline_intake_cannot_bypass_family_preparation():
    state=path_state(circle());plan=consume(fit_family_iter([state]))[0]
    op=dict(op='fit_polygon',path=0,stateHash=outline.path_hash(state),segments=plan['segments'],
            cornerNodes=plan['cornerNodes'],maxDeviation=.5)
    with pytest.raises(ProtocolError,match='coordinated path_fitting'):
        outline.validate_options({'targets':[{'glyph':'fitTest','referenceLayer':'M0','layers':{'scope':'all_masters'},
            'guards':[],'operations':[op]}]})
