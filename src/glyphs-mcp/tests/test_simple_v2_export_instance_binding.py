"""Behavioral checks for live/saved instance identity drift without a font Save."""
import copy
import sys
from pathlib import Path
from types import SimpleNamespace as NS
import pytest

ROOT = Path(__file__).resolve().parents[3]
for part in ('protocol', 'bridge', 'sidecar'):
    sys.path.insert(0, str(ROOT/'src'/part))
from glyphs_mcp_sidecar import export_instance_binding as binding
from glyphs_mcp_sidecar.worker import WorkerError
from glyphs_mcp_sidecar import font_export_job

HASH = 'sha256:'+'a'*64

def row(identity='live-regular', name='Regular', axis=400, **values):
    return dict(id=identity,name=name,type='static',exports=True,outlineFormat='otf',axisValues=[float(axis)],**values)

def fixture():
    live=[row(),row('live-bold','Bold',700)]
    bound=dict(version=1,sourceHash=HASH,instanceId='live-regular',index=0,instances=live)
    saved=copy.deepcopy(live);saved[0]['id']='saved-regular';saved[1]['id']='saved-bold'
    return live,bound,saved

def test_regenerated_ids_bind_the_exact_slot_without_mutating_records():
    live,bound,saved=fixture();original=copy.deepcopy((live,bound,saved))
    index,evidence=binding.resolve(saved,bound,'live-regular',HASH)
    assert index==0 and evidence==dict(method='source-bound-slot',requestedId='live-regular',savedId='saved-regular',index=0)
    assert (live,bound,saved)==original

def test_exact_ids_are_still_preferred():
    live,bound,_=fixture();assert binding.resolve(live,bound,'live-regular',HASH)[1]['method']=='exact-id'

@pytest.mark.parametrize('field,value', [('name','Other'),('type','variable'),('axisValues',[500.0]),('exports',False),('outlineFormat','ttf')])
def test_saved_metadata_drift_is_not_a_name_or_index_fallback(field,value):
    _,bound,saved=fixture();saved[0][field]=value
    with pytest.raises(WorkerError,match='differs'):binding.resolve(saved,bound,'live-regular',HASH)

def test_unselected_metadata_and_order_are_bound_too():
    _,bound,saved=fixture();saved[1]['axisValues']=[650.0]
    with pytest.raises(WorkerError):binding.resolve(saved,bound,'live-regular',HASH)
    _,bound,saved=fixture();saved.reverse()
    with pytest.raises(WorkerError):binding.resolve(saved,bound,'live-regular',HASH)

@pytest.mark.parametrize('change', ['hash','request','count','collision','duplicate-id','ambiguous'])
def test_stale_and_ambiguous_bindings_fail_closed(change):
    _,bound,saved=fixture();identity='live-regular';fingerprint=HASH
    if change=='hash':fingerprint='sha256:'+'b'*64
    if change=='request':identity='other'
    if change=='count':saved.pop()
    if change=='collision':saved[1]['id']='live-regular'
    if change=='duplicate-id':saved[1]['id']=saved[0]['id']
    if change=='ambiguous':
        bound['instances'][1]=row('live-other');saved[1]=row('saved-other')
    with pytest.raises(WorkerError):binding.resolve(saved,bound,identity,fingerprint)

def test_unbound_worker_never_guesses_an_instance():
    font=NS(instances=[NS(id='stored',name='Regular',exports=True)])
    with pytest.raises(WorkerError,match='unavailable'):font_export_job._instance(font,'live')

def service_fixture(monkeypatch):
    live,_,_=fixture();state=dict(id='doc',path='/tmp/source.glyphspackage',generation=7,dirty=False)
    calls=[]
    class Bridge:
        def read_entities(self,document,entities,fields):
            calls.append((document,copy.deepcopy(entities),list(fields)))
            if entities[0]['kind']=='instances':
                return [dict(values=dict(items=[{k:v for k,v in r.items()if k!='axisValues'}for r in live],total=2,complete=True,nextCursor=None))]
            return [dict(entity=e,values=copy.deepcopy(next(r for r in live if r['id']==e['id'])))for e in entities]
    service=NS(bridge=Bridge(),_document=lambda identity:dict(state))
    monkeypatch.setattr(binding,'source_hash',lambda path:HASH)
    return service,state,live,calls

def test_capture_uses_exact_id_and_reads_without_saving(monkeypatch):
    service,state,live,calls=service_fixture(monkeypatch)
    result=binding.capture(service,state,'live-bold',HASH)
    assert result['index']==1 and result['instances']==live and len(calls)==2
    assert calls[1][1]==[{'kind':'instance','id':'live-regular'},{'kind':'instance','id':'live-bold'}]

def test_capture_rejects_source_or_document_changes(monkeypatch):
    service,state,_,_=service_fixture(monkeypatch);baseline=dict(state);state['generation']+=1
    with pytest.raises(WorkerError,match='document changed'):binding.capture(service,baseline,'live-regular',HASH)
    state.update(baseline);monkeypatch.setattr(binding,'source_hash',lambda path:'changed')
    with pytest.raises(WorkerError,match='source changed'):binding.capture(service,baseline,'live-regular',HASH)

def test_capture_rejects_disabled_target(monkeypatch):
    service,state,live,_=service_fixture(monkeypatch);live[0]['exports']=False
    with pytest.raises(WorkerError,match='not enabled'):binding.capture(service,state,'live-regular',HASH)

def test_native_records_call_objc_selectors():
    font=NS(instances=[NS(id=lambda:'saved',name=lambda:'Regular',type=lambda:0,exports=lambda:True,outlineFormat=lambda:0,axes=lambda:[400.0])])
    assert binding.native_records(font)==[row('saved')]
