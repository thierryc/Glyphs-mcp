"""Native KVC layer pages: exact targeting, no wrapper rescans or geometry."""
import base64
import json
from types import SimpleNamespace as NS
from pathlib import Path
import pytest
from test_simple_v2_glyphs_adapter import adapter
from glyphs_mcp_bridge.core import BridgeCore, BridgeError
from glyphs_mcp_bridge.layer_inventory import FIELDS
from glyphs_mcp_protocol.reads import READ_CAPABILITIES

ROOT=Path(__file__).resolve().parents[3]
class Glyph:
    def __init__(self,count):
        self.id='native-A';self.rows=[NS(layerId='layer-'+str(i),name='Duplicate',associatedMasterId='m1',isMasterLayer=i<3,isSpecialLayer=i==3,isBraceLayer=i==3,isBracketLayer=False) for i in range(count)]
        self.visits=[];self.counts=0
    @property
    def layers(self):raise AssertionError('wrapper layer collection used')
    def countOfLayers(self):self.counts+=1;return len(self.rows)
    def objectInLayersAtIndex_(self,i):self.visits.append(i);return self.rows[i]

def setup(count=101):
    bridge,_=adapter();font=bridge.glyphs.fonts[0];glyph=Glyph(count)
    font.glyphs={'A':glyph};font.parent=NS(isDocumentEdited=False,changeCount=7)
    doc=bridge.list_documents()[0]['id'];core=BridgeCore(bridge,lambda cb:cb())
    def page(selector=None,fields=None,entities=None):
        return core.read_entities(doc,entities or [{'kind':'layers','glyph':'A',**(selector or {})}],['id','name','associatedMasterId',*sorted(FIELDS-{'id','name','associatedMasterId'})] if fields is None else fields)[0]['values']
    return bridge,font,glyph,doc,page

@pytest.mark.parametrize('count',[0,1,3,100,101,1001])
@pytest.mark.parametrize('limit',[1,37,100])
def test_exact_native_inventory_and_bounded_visits(count,limit):
    _,_,g,_,page=setup(count);cursor=None;offset=0;items=[]
    while True:
        g.visits.clear();g.counts=0;p=page(dict(limit=limit,**({'cursor':cursor} if cursor else {})))
        expected=list(range(offset,min(offset+limit,count)))
        assert g.visits==([offset-1] if offset else [])+expected and g.counts==1
        assert p['total']==count and p['returned']==len(expected)
        assert p['items']==[{f:getattr(g.rows[i],'layerId' if f=='id' else f) for f in FIELDS} for i in expected]
        items.extend(p['items']);offset+=p['returned'];assert p['complete'] is (offset==count)
        if p['complete']:assert p['nextCursor'] is None;break
        cursor=p['nextCursor'];assert cursor.startswith('l1.')
    assert [x['id'] for x in items]==['layer-'+str(i) for i in range(count)]

def test_requested_fields_only_and_no_metadata_or_geometry_read():
    _,_,g,_,page=setup(1);attempts=[]
    class IDOnly:
        layerId='exact-id'
        def __getattr__(self,name):attempts.append(name);raise AssertionError('unrequested field '+name)
    g.rows=[IDOnly()];assert page(fields=['id'])['items']==[{'id':'exact-id'}]
    assert attempts==[]

def test_ten_thousand_layers_small_page_never_visits_omitted_layers():
    _,_,g,_,page=setup(10000)
    class Bad:
        def __getattribute__(self,name):raise AssertionError('omitted layer visited')
    g.rows[2:]=[Bad()]*9998;p=page({'limit':2})
    assert g.visits==[0,1] and p['returned']==2 and p['total']==10000 and not p['complete']

@pytest.mark.parametrize('field',['name','associatedMasterId','isMasterLayer','isSpecialLayer','isBraceLayer','isBracketLayer'])
def test_unavailable_optional_evidence_is_null_not_a_fabricated_classification(field):
    _,_,g,_,page=setup(1);delattr(g.rows[0],field);p=page(fields=['id',field])
    assert p['complete'] and p['items'][0]=={'id':'layer-0',field:None}

@pytest.mark.parametrize('change',['add','delete','rename-boundary','replace-boundary','observed-association','generation','dirty','glyph','document'])
def test_stale_rejection(change):
    _,font,g,_,page=setup();cursor=page()['nextCursor']
    if change=='add':g.rows.append(NS(layerId='new',name='new'))
    elif change=='delete':g.rows.pop(0)
    elif change=='rename-boundary':g.rows[99].name='Renamed'
    elif change=='replace-boundary':g.rows[99].layerId='new'
    elif change=='observed-association':g.rows[0].associatedMasterId='m2';font.parent.changeCount+=1
    elif change=='generation':font.parent.changeCount+=1
    elif change=='dirty':font.parent.isDocumentEdited=True
    elif change=='glyph':g.id='replacement'
    else:
        d=json.loads(base64.urlsafe_b64decode(cursor[3:]));d['document']='other';cursor='l1.'+base64.urlsafe_b64encode(json.dumps(d).encode()).decode()
    with pytest.raises(BridgeError) as e:page({'cursor':cursor})
    assert e.value.code=='stale_layer_cursor'

def test_cursor_cannot_be_used_for_a_different_named_glyph():
    _,font,g,_,page=setup();cursor=page()['nextCursor'];font.glyphs['B']=g
    with pytest.raises(BridgeError) as e:page({'glyph':'B','cursor':cursor})
    assert e.value.code=='stale_layer_cursor'

def test_silent_nonboundary_edit_is_not_an_atomic_snapshot_guarantee():
    _,_,g,_,page=setup();cursor=page()['nextCursor'];g.rows[0].name='Silent'
    assert page({'cursor':cursor})['complete'];assert page()['items'][0]['name']=='Silent'

@pytest.mark.parametrize('limit',[0,-1,101,True,False,1.5,'100',None])
def test_invalid_limits(limit):
    *_,page=setup()
    with pytest.raises(BridgeError) as e:page({'limit':limit})
    assert e.value.code=='invalid_request'

@pytest.mark.parametrize('cursor',[None,0,{},'','nope','l1.!','l1.'+'a'*4096,'l1.W10=','g1.W10='])
def test_invalid_cursor(cursor):
    *_,page=setup()
    with pytest.raises(BridgeError) as e:page({'cursor':cursor})
    assert e.value.code=='invalid_request'

@pytest.mark.parametrize('key,value',[('offset',True),('offset',0),('offset',101),('total',-1),('generation','7'),('dirty',0),('after',[]),('after',['',None]),('after',['id',4]),('document',''),('glyph',[]),('glyph',['A',None])])
def test_strict_cursor_fields(key,value):
    *_,page=setup();d=json.loads(base64.urlsafe_b64decode(page()['nextCursor'][3:]));d[key]=value
    with pytest.raises(BridgeError) as e:page({'cursor':'l1.'+base64.urlsafe_b64encode(json.dumps(d).encode()).decode()})
    assert e.value.code=='invalid_request'

@pytest.mark.parametrize('selector',[{'glyph':''},{'glyph':None},{'glyph':1},{'id':'A'},{'offset':3}])
def test_bad_selectors(selector):
    *_,page=setup()
    with pytest.raises(BridgeError) as e:page(selector)
    assert e.value.code=='invalid_request'

@pytest.mark.parametrize('fields',[[],['width'],['id','bounds']])
def test_explicit_field_contract(fields):
    *_,page=setup()
    with pytest.raises(BridgeError) as e:page(fields=fields)
    assert e.value.code==('invalid_request' if not fields else 'unsupported_read')

def test_mixed_selectors_rejected():
    *_,page=setup()
    for other in ({'kind':'glyphs'},{'kind':'layers','glyph':'A'},{'kind':'glyph','id':'A'},{'kind':'context'},{'kind':'masters'}):
        with pytest.raises(BridgeError) as e:page(entities=[{'kind':'layers','glyph':'A'},other])
        assert e.value.code=='invalid_request'

@pytest.mark.parametrize('failure',['count','getter','index','id','glyph-id','missing-layer'])
def test_unavailable_identity_or_index_is_explicit(failure):
    _,_,g,_,page=setup(1)
    if failure=='count':g.countOfLayers=lambda:None
    elif failure=='getter':g.objectInLayersAtIndex_=None
    elif failure=='index':g.objectInLayersAtIndex_=lambda i:(_ for _ in ()).throw(RuntimeError('native exception'))
    elif failure=='glyph-id':g.id=None
    elif failure=='missing-layer':g.rows[0]=None
    else:del g.rows[0].layerId
    with pytest.raises(BridgeError) as e:page()
    assert e.value.code=='unsupported_read'

def test_missing_glyph_dirty_unsaved_and_stale_document():
    bridge,font,_,_,page=setup(1);font.filepath=None;font.parent.isDocumentEdited=True
    assert page()['complete']
    with pytest.raises(BridgeError) as e:page({'glyph':'missing'})
    assert e.value.code=='target_not_found'
    bridge.glyphs.fonts.clear()
    with pytest.raises(BridgeError) as e:page()
    assert e.value.code=='document_not_found'

def test_capability_and_focused_guidance():
    assert 'layers.list.v1' in READ_CAPABILITIES
    p=ROOT/'skills/glyphs/references/layer-discovery.md';text=' '.join(p.read_text().split())
    for phrase in ('layers.list.v1','stale_layer_cursor','1–100','native collection order','not atomic','installation needs updating','Unknown','isBraceLayer','No Save'):
        assert phrase in text
    assert p.read_bytes()==(ROOT/'plugins/glyphs-mcp/skills/glyphs/references/layer-discovery.md').read_bytes()
