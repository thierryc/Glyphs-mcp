"""Original generic Path Doctor fixtures; never private font data."""
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest
ROOT=Path(__file__).resolve().parents[3]
for part in ('protocol','bridge','sidecar'): sys.path.insert(0,str(ROOT/'src'/part))
from glyphs_mcp_protocol import outline, path_doctor
from glyphs_mcp_protocol.preparation import path_doctor as doctor, path_attributes, simple
from glyphs_mcp_bridge import outline_edit
from glyphs_mcp_bridge.core import BridgeCore, BridgeError
from test_simple_v2_outline_edit import Node, PathShape, Layer, Collection


class PenPoint:
    def __init__(self,t,width=24.125,height=20.25,angle=float.fromhex('0x1.fffffffffffffp+1023'),
                 strokePosition=.03123456789,progressionIn=.2,progressionOut=.3,isLocked=False):
        self.__dict__.update(locals());del self.__dict__['self']
    def copy(self): return deepcopy(self)


def fixture(cubic=False, profile=True):
    # Original triangle/curved triangle, with fractional coordinates and explicit return.
    nodes=[Node(.125,.25),Node(90.375,5.625),Node(45.875,80.125)]
    if cubic: nodes += [Node(20.25,60.125,'offcurve'),Node(-5.125,10.25,'offcurve')]
    nodes += [Node(.125,.25,'curve' if cubic else 'line')]
    path=PathShape(nodes,True);path.attributes={'strokeWidth':24.125,'fill':0}
    path.userData={}
    for n in nodes: n.userData={};n.attributes={}
    if profile:
        nodes[-1].attributes={'penPoints':[PenPoint(.375,width=32.123456789),PenPoint(1.0)]}
        nodes[0].attributes={'penPoints':[PenPoint(1.0)]}
    layer=Layer('M');layer.paths=Collection([path]);layer.shapes=list(layer.paths)
    return layer,path


def apply(layer,path):
    state=doctor.path_state(path)
    op={'op':'normalize_closed_seam','path':0,'stateHash':outline.path_hash(state)}
    outline_edit.apply_operation(layer,outline.validate_operation(op))
    return state


@pytest.mark.parametrize('cubic',[False,True])
def test_preserve_exact_real_segments_profiles_and_recovery(cubic):
    layer,path=fixture(cubic)
    before=doctor.path_state(path); snap=outline_edit.capture(layer)
    # Capture references independently, not only rendered appearance.
    objects=list(path.nodes); old_profiles=deepcopy(before['nodes'][-1]['attributeState'])
    apply(layer,path)
    after=doctor.path_state(path)
    assert path.nodes == objects[:-1]
    assert after['nodes'][0]['type']==before['nodes'][-1]['type']
    assert after['nodes'][0]['attributeState']==old_profiles
    assert after['nodes'][1:]==before['nodes'][1:-1]
    assert after['attributeState']==before['attributeState']
    doctor.validate_segments(after)
    assert not doctor.seam_pattern(after)
    assert not any(i['repair'] for i in doctor.inspect_path(after,glyph='generic',layer='M',path=0))
    outline_edit.restore(layer,snap)
    assert doctor.path_state(path)==before
    assert path.nodes==objects


@pytest.mark.parametrize('change',["profile","fill","inherited","smooth","xy"])
def test_stale_guard_covers_attributes_and_explicit_defaults(change):
    layer,path=fixture(); guard=outline.path_hash(doctor.path_state(path))
    if change=='profile':path.nodes[-1].attributes['penPoints'][0].width+=.0000000001
    if change=='fill':path.attributes['fill']=1
    if change=='inherited':del path.attributes['fill']
    if change=='smooth':path.nodes[-1].smooth=True
    if change=='xy':path.nodes[1].position=(90.375,5.62500001)
    with pytest.raises(ValueError,match='stale'):doctor.normalize(layer,path,guard)


def test_profile_conflict_and_inherited_sentinel_are_held():
    layer,path=fixture();path.nodes[0].attributes['penPoints'][0].angle=0.0
    state=doctor.path_state(path)
    assert any('conflicting seam profiles' in r for r in doctor.qualify(state))
    with pytest.raises(ValueError,match='held'):apply(layer,path)
    assert doctor.path_state(path)==state


@pytest.mark.parametrize('variant',['path_lock','hint','metadata','node_attributes','pen_lock','smooth'])
def test_locks_references_and_unsupported_structures_hold_without_changes(variant):
    layer,path=fixture()
    if variant=='path_lock':path.locked=True
    if variant=='hint':layer.hints=[NS(originNode=path.nodes[1])]
    if variant=='metadata':path.nodes[1].userData={'indexReference':3}
    if variant=='node_attributes':path.nodes[1].attributes['unknownReference']=2
    if variant=='pen_lock':path.nodes[-1].attributes['penPoints'][0].isLocked=True
    if variant=='smooth':path.nodes[0].smooth=True
    before=doctor.path_state(path)
    with pytest.raises(ValueError):apply(layer,path)
    assert doctor.path_state(path)==before


def test_open_return_and_inactive_controls_are_valid():
    layer,path=fixture();path.closed=False
    path.nodes += [Node(0.125,-50.375)]
    state=doctor.path_state(path)
    issues=doctor.inspect_path(state,glyph='generic',layer='M',path=0)
    assert {'open_return','inactive_open_start_profiles'} <= {i['code'] for i in issues}
    assert all(i['repair'] is None and i['classification']=='drawing_convention' for i in issues)
    with pytest.raises(ValueError,match='qualified'):apply(layer,path)


def test_correct_closed_loop_and_independent_fill_smooth_findings():
    layer,path=fixture();del path.attributes['fill']
    issues=doctor.inspect_path(doctor.path_state(path),glyph='generic',layer='M',path=0)
    assert {'redundant_closed_seam','closed_stroke_fill_unset','corner_connections'}=={i['code'] for i in issues}
    apply(layer,path)
    issues=doctor.inspect_path(doctor.path_state(path),glyph='generic',layer='M',path=0)
    assert {'closed_stroke_fill_unset','corner_connections'}=={i['code'] for i in issues}
    assert 'fill' not in path.attributes


def test_missing_redundant_profile_and_interior_controls_survive():
    layer,path=fixture(cubic=True)
    del path.nodes[0].attributes['penPoints']
    original=deepcopy(doctor.path_state(path)['nodes'][-1]['attributeState'])
    apply(layer,path)
    assert doctor.path_state(path)['nodes'][0]['attributeState']==original


def test_unknown_native_attribute_refuses_instead_of_stringifying():
    layer,path=fixture();path.attributes['ref']=object()
    with pytest.raises(ValueError,match='unsupported native'):doctor.path_state(path)


def test_native_attribute_restore_builds_native_nested_metadata_containers(monkeypatch):
    class NativeDictionary(dict):
        @classmethod
        def dictionary(cls): return cls()
        def setObject_forKey_(self,value,key): self[key]=value
    class NativeArray(list):
        @classmethod
        def array(cls): return cls()
        def addObject_(self,value): self.append(value)
    monkeypatch.setitem(sys.modules,'Foundation',NS(NSMutableDictionary=NativeDictionary,NSMutableArray=NativeArray))
    class NativeOwner:
        def __init__(self): self.attributes={};self.pyobjc_instanceMethods=self
        def setAttributes_(self,value): self.attributes=value
    owner=NativeOwner()
    saved={'userData':{'note':'keep','nested':[{'index':2,'value':.123456789012345}]},
           'penPoints':[PenPoint(1.0,width=32.123456789)]}
    path_attributes.restore(owner,saved)
    assert isinstance(owner.attributes,NativeDictionary)
    assert isinstance(owner.attributes['userData'],NativeDictionary)
    assert isinstance(owner.attributes['userData']['nested'],NativeArray)
    assert isinstance(owner.attributes['userData']['nested'][0],NativeDictionary)
    assert isinstance(owner.attributes['penPoints'],NativeArray)
    assert owner.attributes['penPoints'][0] is not saved['penPoints'][0]
    assert path_attributes.plain(owner.attributes)==path_attributes.plain(saved)
    saved['userData']['nested'][0]['index']=7
    assert owner.attributes['userData']['nested'][0]['index']==2


def test_diagnostic_is_deterministic_and_excludes_other_surfaces():
    layer,path=fixture();glyph=NS(name='generic',layers=Collection([layer]),components=[])
    layer.components=[NS(componentName='unexpanded')]
    historical=deepcopy(layer);historical.layerId='backup';historical.paths=[]
    glyph.layers.append(historical)
    font=NS(glyphs=Collection([glyph]),masters=[NS(id='M')])
    request={'kind':'path_diagnostics','glyphs':[],'options':{'glyphs':'all','layers':'all_masters'}}
    from glyphs_mcp_protocol.preparation import consume
    a=consume(doctor.prepare_iter(font,request));b=consume(doctor.prepare_iter(font,request))
    assert a==b
    assert a[1]['coverage']['layers']==1 and a[1]['coverage']['componentReferences']==1
    assert a[1]['scope']['componentsExpanded'] is False
    assert simple.eligible(request)
    assert outline.validate_operation({'op':'normalize_closed_seam','path':0,'stateHash':outline.path_hash(doctor.path_state(path))})


def test_readonly_job_uses_existing_registry_on_dirty_pathless_font():
    layer,path=fixture();layer.components=[]
    font=NS(glyphs=[NS(name='generic',layers=Collection([layer]))],masters=[NS(id='M')])
    class Adapter:
        def _font(self,identity):return font
        def document_state(self,identity):return {'id':identity,'path':None,'dirty':True,'generation':9}
    core=BridgeCore(Adapter(),lambda f: f())
    from glyphs_mcp_bridge import typed_preparation
    request={'jobId':'job_pd','documentId':'doc_pd','sourcePath':None,'sourceHash':'sha256:'+'0'*64,
             'generation':9,'request':{'kind':'path_diagnostics','glyphs':[],'options':{'glyphs':'all','layers':'all_masters'}}}
    typed_preparation.begin(core,request,BridgeError)
    result=typed_preparation.result(core,'job_pd',BridgeError)
    assert result['resultKind']=='diagnostic' and 'patch' not in result
    assert core.operation('job_pd')['status']=='completed'
    assert result['report']['document']['dirty']
    with pytest.raises(BridgeError,match='diagnostic'):
        core.begin_apply(core._operations['job_pd']['patch'])


def test_invalid_profile_progression_is_diagnosed_and_held():
    layer,path=fixture();path.nodes[-1].attributes['penPoints'][0].t=1.5
    state=doctor.path_state(path)
    issues=doctor.inspect_path(state,glyph='generic',layer='M',path=0)
    assert any(i['code']=='invalid_profiles' for i in issues)
    seam=next(i for i in issues if i['code']=='redundant_closed_seam')
    assert seam['repair'] is None and seam['heldReasons']
    with pytest.raises(ValueError,match='unordered'):apply(layer,path)
    assert doctor.path_state(path)==state


def test_corresponding_masters_and_multiple_strokes_are_preserved():
    from glyphs_mcp_protocol.preparation import consume
    layers=Collection();targets=[]
    for identity in ['M0','M1','M2']:
        layer,path=fixture(True);layer.layerId=layer.id=identity
        unrelated=PathShape([Node(200.125,0),Node(210.375,30)])
        unrelated.userData={};unrelated.attributes={'strokeWidth':8.0}
        layer.paths.append(unrelated);layer.shapes=list(layer.paths)
        layers.append(layer)
        h=outline.path_hash(doctor.path_state(path))
        targets.append({'glyph':'generic','referenceLayer':identity,'layers':{'scope':'ids','ids':[identity]},
                        'guards':[{'path':0,'hash':h}],
                        'operations':[{'op':'normalize_closed_seam','path':0,'stateHash':h}]})
    font=NS(glyphs={'generic':NS(name='generic',layers=layers)},masters=[NS(id=l.layerId) for l in layers])
    from glyphs_mcp_protocol.preparation import outline as preparation
    request={'kind':'outline_edit','glyphs':[],'options':{'targets':targets}}
    changes,report=consume(preparation.prepare_iter(font,request))
    assert len(changes)==3 and not report['compatibilityChanges']
    before=doctor.path_state(layers[0].paths[1])
    for change,layer in zip(changes,layers):edit=outline_edit.apply(layer,change)
    assert doctor.path_state(layers[0].paths[1])==before
    # A one-master normalization would alter correspondence and must refuse.
    for index, identity in enumerate(['M0','M1','M2']):
        layer,path=fixture(True);layer.layerId=layer.id=identity;layers[index]=layer
    with pytest.raises(Exception,match='compatibility'):
        consume(preparation.prepare_iter(font,{'options':{'targets':targets[:1]}}))


def test_near_coincidence_is_suspicion_without_repair():
    layer,path=fixture();path.nodes[-1].position=(.1250001,.25)
    issues=doctor.inspect_path(doctor.path_state(path),glyph='generic',layer='M',path=0)
    issue=next(i for i in issues if i['code']=='near_closed_seam')
    assert issue['classification']=='suspicious' and issue['repair'] is None


def test_native_attribute_lock_is_held_even_when_wrapper_flag_is_false():
    layer,path=fixture();path.attributes['locked']=True
    state=doctor.path_state(path)
    assert state['locked']
    with pytest.raises(ValueError,match='locked'):apply(layer,path)


def test_sidecar_live_diagnostic_never_saves_copies_source_or_invokes_worker(tmp_path):
    import time
    from glyphs_mcp_bridge import typed_preparation
    from glyphs_mcp_sidecar.service import SidecarService,ServiceError
    from glyphs_mcp_sidecar.jobs import JobStore
    layer,path=fixture();layer.components=[]
    font=NS(glyphs=[NS(name='generic',layers=Collection([layer]))],masters=[NS(id='M')])
    document={'id':'doc_pd','path':None,'dirty':True,'generation':7}
    class Adapter:
        def _font(self,identity):return font
        def document_state(self,identity):return document
    core=BridgeCore(Adapter(),lambda f:f())
    class Bridge:
        def status(self):return {'jobCapabilities':['path.diagnostics.v1',simple.CAPABILITY],'writeCapabilities':[]}
        def documents(self):return [document]
        def prepare_typed(self,request):return typed_preparation.begin(core,request,BridgeError)
        def prepared_typed(self,identity):return typed_preparation.result(core,identity,BridgeError)
        def operation(self,identity):return core.operation(identity)
    class Worker:
        def status(self):raise AssertionError('diagnostics must not consult external worker')
        def prepare(self,*args):raise AssertionError('diagnostics must not invoke external worker')
    service=SidecarService(Bridge(),jobs=JobStore(tmp_path/'jobs'),worker=Worker())
    try:
        job=service.start_job('doc_pd',kind='path_diagnostics',options={'glyphs':'all'})
        deadline=time.monotonic()+2
        while (job:=service.get_job(job['id']))['status']=='preparing' and time.monotonic()<deadline:time.sleep(.01)
        assert job['status']=='completed' and job['resultKind']=='diagnostic',job
        assert job['report']['coverage']['paths']==1
        with pytest.raises(ServiceError):service.apply_job(job['id'])
        with pytest.raises(ServiceError):service.accept_job(job['id'])
        assert document['dirty'] and document['path'] is None
    finally:service.close()


def test_same_document_stopped_recovery_does_not_block_readonly_diagnostic(tmp_path):
    from glyphs_mcp_sidecar.script_service import mutation_guard
    from glyphs_mcp_sidecar.jobs import JobStore
    from threading import RLock
    from glyphs_mcp_sidecar import script_service
    jobs=JobStore(tmp_path/'jobs')
    owner=jobs.create({'id':'doc_pd','path':None,'generation':0,'dirty':True},{'kind':'python_script'})
    jobs.update(owner['id'],status='applied',bridgeOperation={'scriptResult':{'executed':True}})
    service=NS(_script_dispatch_lock=RLock(),_lock=RLock(),jobs=jobs,
               _task_scoped_recovery=True,_task_bridge_session='session',
               bridge=NS(status=lambda:{'jobCapabilities':['tasks.document-recovery.v1'],'bridgeSessionId':'session'}))
    @mutation_guard
    def start_job(service,document_id,*,kind):return {'resultKind':'diagnostic'}
    assert start_job(service,'doc_pd',kind='path_diagnostics')['resultKind']=='diagnostic'
    assert jobs.get(owner['id'])['status']=='applied'


def test_host_qualification_is_fail_closed(monkeypatch):
    from glyphs_mcp_bridge import path_doctor_qualification as gate,identity
    monkeypatch.setattr(identity,'host_identity',lambda:{'identifier':'com.GeorgSeifert.Glyphs4','version':'4.2','build':'9999'})
    assert gate.repair_available() is False


def test_preparation_detaches_copied_layer_before_native_mutation():
    from glyphs_mcp_protocol.preparation.outline import _copy
    events=[]
    class NativeLayer:
        parent=object()
        def copy(self):return NativeLayer()
        def setParent_(self,value):events.append('detach');self.parent=value
        def setTemporarilyDisableRounding_(self,value):
            assert self.parent is None
            events.append('precision')
    clone=_copy(NativeLayer())
    assert clone.parent is None and events==['detach','precision']


def test_seam_repair_holds_unqualified_historical_surfaces():
    from glyphs_mcp_protocol.preparation import consume
    from glyphs_mcp_protocol.preparation.outline import prepare_iter
    layer,path=fixture();layer.layerId=layer.id='M'
    history=deepcopy(layer);history.layerId=history.id='backup'
    font=NS(glyphs={'generic':NS(name='generic',layers=Collection([layer,history]))},masters=[NS(id='M')])
    h=outline.path_hash(doctor.path_state(history.paths[0]))
    request={'options':{'targets':[{'glyph':'generic','referenceLayer':'backup',
        'layers':{'scope':'ids','ids':['backup']},'guards':[{'path':0,'hash':h}],
        'operations':[{'op':'normalize_closed_seam','path':0,'stateHash':h}]}]}}
    with pytest.raises(Exception,match='ordinary-master'):consume(prepare_iter(font,request))
