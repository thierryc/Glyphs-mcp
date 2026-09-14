"""Bounded glyph pages, strict opaque cursors and declared live-read limits."""
import base64
import json
from types import SimpleNamespace as NS
from pathlib import Path
import pytest
from test_simple_v2_glyphs_adapter import adapter
from glyphs_mcp_bridge.core import BridgeCore, BridgeError
from glyphs_mcp_protocol.reads import READ_CAPABILITIES

ROOT=Path(__file__).resolve().parents[3]
class Glyphs:
    def __init__(self,count):
        self.rows=[NS(id='native-id-'+str(i),name='g%05d'%i) for i in range(count)]
        self.visits=[];self.counts=0
    def __len__(self):self.counts+=1;return len(self.rows)
    def __iter__(self):raise AssertionError('whole-font traversal')
    def __getitem__(self,i):self.visits.append(i);return self.rows[i]

def setup(count=101):
    value,_=adapter();font=value.glyphs.fonts[0]
    font.glyphs=Glyphs(count);font.parent=NS(isDocumentEdited=False,changeCount=7)
    doc=value.list_documents()[0]['id'];core=BridgeCore(value,lambda cb:cb())
    def page(selector=None,fields=None,entities=None):
        return core.read_entities(doc,entities or [dict(kind='glyphs',**(selector or {}))],['name'] if fields is None else fields)[0]['values']
    return value,font,doc,page

@pytest.mark.parametrize('count',[0,1,99,100,101,1001])
@pytest.mark.parametrize('limit',[1,37,100])
def test_complete_native_order_in_bounded_pages(count,limit):
    _,font,_,page=setup(count);names=[];cursor=None;offset=0
    while True:
        font.glyphs.visits.clear();font.glyphs.counts=0
        p=page(dict(limit=limit,**({'cursor':cursor} if cursor else {})))
        assert p['total']==count and p['returned']==min(limit,count-offset)
        expected=list(range(offset,min(offset+limit,count)))
        assert font.glyphs.visits==([offset-1] if offset else [])+expected
        assert font.glyphs.counts==1
        assert p['items']==[dict(name=font.glyphs.rows[i].name) for i in expected]
        names.extend(x['name'] for x in p['items']);offset+=p['returned']
        assert p['complete'] is (offset==count)
        if p['complete']:
            assert p['nextCursor'] is None;break
        assert isinstance(p['nextCursor'],str);cursor=p['nextCursor']
    assert names==[r.name for r in font.glyphs.rows]

def test_small_page_does_not_touch_any_omitted_glyph_or_metadata():
    _,font,_,page=setup(10000)
    class Bad:
        def __getattribute__(self,name):raise AssertionError('omitted glyph visited')
    font.glyphs.rows[2:]=[Bad()]*9998
    result=page({'limit':2})
    assert result['returned']==2 and result['total']==10000 and not result['complete']
    assert font.glyphs.visits==[0,1]

@pytest.mark.parametrize('change',['add','delete','rename-boundary','replace-boundary','rename-earlier-observed','dirty','generation','document'])
def test_stale_conditions_rejected(change):
    _,font,doc,page=setup();cursor=page()['nextCursor']
    if change=='add':font.glyphs.rows.append(NS(id='new',name='new'))
    elif change=='delete':font.glyphs.rows.pop(0)
    elif change=='rename-boundary':font.glyphs.rows[99].name='renamed'
    elif change=='replace-boundary':font.glyphs.rows[99].id='replacement'
    elif change=='rename-earlier-observed':font.glyphs.rows[0].name='renamed';font.parent.changeCount+=1
    elif change=='dirty':font.parent.isDocumentEdited=True
    elif change=='generation':font.parent.changeCount+=1
    else:
        data=json.loads(base64.urlsafe_b64decode(cursor[3:]));data['document']='other-doc';cursor='g1.'+base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
    with pytest.raises(BridgeError) as error:page({'cursor':cursor})
    assert error.value.code=='stale_glyph_cursor'

def test_unobserved_nonboundary_changes_are_not_an_atomic_inventory_guarantee():
    _,font,_,page=setup();first=page();font.glyphs.rows[0].name='silent-rename'
    # No observed generation/count/boundary change: end-of-collection is still
    # true. The documented client must discard partial results after ANY edit
    # it observes; this endpoint does not promise a multi-call atomic snapshot.
    assert page({'cursor':first['nextCursor']})['complete'] is True
    assert page()['items'][0]['name']=='silent-rename'

def test_existing_dirty_update_signal_is_conservative_without_new_hook():
    bridge,font,doc,page=setup();del font.parent.changeCount;font.parent.isDocumentEdited=True
    cursor=page()['nextCursor'];bridge.note_change()
    with pytest.raises(BridgeError,match='change signal'):page({'cursor':cursor})
    assert bridge._generations[doc]==1

@pytest.mark.parametrize('limit',[0,-1,101,True,False,1.5,'100',None])
def test_invalid_limits(limit):
    *_,page=setup()
    with pytest.raises(BridgeError) as error:page({'limit':limit})
    assert error.value.code=='invalid_request'

@pytest.mark.parametrize('cursor',[None,0,{},'','nope','g1.!','g1.'+'a'*4096,'g1.W10='])
def test_invalid_opaque_cursor(cursor):
    *_,page=setup()
    with pytest.raises(BridgeError) as error:page({'cursor':cursor})
    assert error.value.code=='invalid_request'

@pytest.mark.parametrize('key,value',[('offset',True),('offset',0),('offset',101),('total',-1),('generation','7'),('dirty',0),('after',[]),('after',['id',None]),('document','')])
def test_strict_decoded_cursor_types(key,value):
    *_,page=setup();data=json.loads(base64.urlsafe_b64decode(page()['nextCursor'][3:]));data[key]=value
    cursor='g1.'+base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
    with pytest.raises(BridgeError) as error:page({'cursor':cursor})
    assert error.value.code=='invalid_request'

@pytest.mark.parametrize('fields',[[],['unicode'],['name','export']])
def test_fields_are_explicit_and_initially_names_only(fields):
    *_,page=setup()
    with pytest.raises(BridgeError) as error:page(fields=fields)
    assert error.value.code==('invalid_request' if fields==[] else 'unsupported_read')

@pytest.mark.parametrize('selector',[{'glyph':'A'},{'offset':3},{'id':'A'}])
def test_unknown_parameters(selector):
    *_,page=setup()
    with pytest.raises(BridgeError) as error:page(selector)
    assert error.value.code=='invalid_request'

def test_only_one_page_selector_and_no_mixed_reads():
    *_,page=setup()
    for other in ({'kind':'glyphs'},{'kind':'glyph','id':'A'},{'kind':'context'},{'kind':'masters'}):
        with pytest.raises(BridgeError) as error:page(entities=[{'kind':'glyphs'},other])
        assert error.value.code=='invalid_request'

def test_native_evidence_errors_never_become_complete_empty_inventory():
    _,font,_,page=setup()
    del font.glyphs.rows[0].name
    with pytest.raises(BridgeError,match='name unavailable'):page()
    font.glyphs=None
    with pytest.raises(BridgeError,match='count unavailable'):page()

def test_dirty_unsaved_and_stale_document_reads():
    bridge,font,doc,page=setup(1);font.filepath=None;font.parent.isDocumentEdited=True
    assert page()['complete'] is True
    bridge.glyphs.fonts.clear()
    with pytest.raises(BridgeError) as error:page()
    assert error.value.code=='document_not_found'

def test_capability_and_focused_guidance():
    assert 'glyphs.list.v1' in READ_CAPABILITIES
    entry=(ROOT/'skills/glyphs/SKILL.md').read_text();assert 'glyph-discovery.md' in entry
    path=ROOT/'skills/glyphs/references/glyph-discovery.md'
    text=' '.join(path.read_text().split())
    for phrase in ('glyphs.list.v1','stale_glyph_cursor','opaque','1–100','observed edit','not atomic','installation needs updating','no Save','Known glyph'):
        assert phrase in text
    assert path.read_bytes()==(ROOT/'plugins/glyphs-mcp/skills/glyphs/references/glyph-discovery.md').read_bytes()
