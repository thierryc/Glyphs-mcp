"""Document context stays bounded, fresh and separate from node inspection."""
import sys
from pathlib import Path
from types import SimpleNamespace as NS
import pytest

ROOT = Path(__file__).resolve().parents[3]
for part in ('protocol', 'bridge'):
    sys.path.insert(0, str(ROOT/'src'/part))
from glyphs_mcp_bridge.core import BridgeError
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
from glyphs_mcp_protocol.reads import READ_CAPABILITIES

class Indexed:
    def __init__(self, items): self.items, self.visits = items, []
    def __len__(self): return len(self.items)
    def __iter__(self): raise AssertionError('unbounded iteration')
    def __getitem__(self, i):
        self.visits.append(i)
        return self.items[i]

def setup():
    bar = NS(selectedTabItem=None)
    font = NS(parent=NS(windowController=NS(tabBarControl=bar),isDocumentEdited=True),
              currentTab=None,fontView=object(),selection=Indexed([]),
              selectedFontMaster=NS(id='native-master',name='Light'))
    bar.selectedTabItem=font.fontView
    app=NS(fonts=[font],font=font)
    adapter=GlyphsAdapter(app)
    doc=adapter._id(font)
    def read(fields=('view','master','selectedGlyphs'), selector=None, entities=None):
        return adapter.read_entities(doc,entities or [selector or {'kind':'context'}],list(fields))[0]['values']
    return font,bar,app,adapter,doc,read

def test_font_view_empty_and_requested_fields():
    font,_,_,_,_,read=setup()
    expected={'view':'font','master':{'id':'native-master','name':'Light'},
              'selectedGlyphs':dict(source='font.selection',total=0,returned=0,limit=100,complete=True,items=[])}
    assert read()==expected
    for key in expected: assert read([key]) == {key:expected[key]}
    assert 'document.context.v1' in READ_CAPABILITIES
    assert 'selection.context.v1' in READ_CAPABILITIES

@pytest.mark.parametrize('count',[0,1,99,100,101,10000])
@pytest.mark.parametrize('limit',[1,50,100])
def test_bounded_indexed_native_selection(count,limit):
    font,_,_,_,_,read=setup()
    font.selection=Indexed([NS(name='g'+str(i)) for i in range(count)])
    result=read(['selectedGlyphs'],{'kind':'context','glyphLimit':limit})['selectedGlyphs']
    assert result == dict(source='font.selection',total=count,returned=min(count,limit),limit=limit,
                         complete=count<=limit,items=['g'+str(i) for i in range(min(count,limit))])
    assert font.selection.visits==list(range(min(count,limit)))

def test_edit_native_order_and_repeated_entries_are_not_deduplicated_by_bridge():
    font,bar,_,_,_,read=setup()
    font.currentTab=object();bar.selectedTabItem=font.currentTab
    font.selectedLayers=Indexed([NS(parent=NS(name=x)) for x in ('mixed','control','mixed')])
    result=read()
    assert result['view']=='edit'
    assert result['selectedGlyphs']['items']==['mixed','control','mixed']
    assert result['selectedGlyphs']['source']=='font.selectedLayers'
    assert not font.selection.visits

def test_master_only_does_not_read_views_or_selections_and_is_fresh():
    font,bar,_,_,_,read=setup()
    del font.parent.windowController
    for name in ('Light','Regular','Bold'):
        font.selectedFontMaster=NS(id='ID-'+name,name=name)
        assert read(['master'])==dict(master=dict(id='ID-'+name,name=name))
    assert not font.selection.visits
    font.selectedFontMaster=None
    assert read(['master'])=={'master':None}

@pytest.mark.parametrize('missing',['window','selected-tab','other-tab','selection','count','item','master'])
def test_unavailable_is_not_empty_or_complete(missing):
    font,bar,_,_,_,read=setup()
    if missing=='window': del font.parent.windowController
    elif missing=='selected-tab': bar.selectedTabItem=None
    elif missing=='other-tab': bar.selectedTabItem=object()
    elif missing=='selection': del font.selection
    elif missing=='count':
        class NoCount(Indexed):
            def __len__(self): raise RuntimeError('unavailable')
        font.selection=NoCount([NS(name='A')])
    elif missing=='item': font.selection=Indexed([NS(name='A'),NS()])
    else: del font.selectedFontMaster
    result=read()
    if missing=='master': assert result['master'] is None
    else:
        selected=result['selectedGlyphs']
        assert selected['complete'] is False and selected['unavailable']
        assert selected['total'] == (2 if missing=='item' else None)
        assert selected['returned'] == (1 if missing=='item' else 0)
    if missing in ('window','selected-tab','other-tab'): assert result['view']=='unavailable'

@pytest.mark.parametrize('limit',[None,True,False,0,-1,101,1.0,'1',[],{}])
def test_invalid_limits(limit):
    *_,read=setup()
    with pytest.raises(BridgeError,match='glyphLimit'):
        read(['selectedGlyphs'],{'kind':'context','glyphLimit':limit})

@pytest.mark.parametrize('fields,selector,entities,code',[
    (['nodes'],None,None,'unsupported_read'), ([],None,None,'unsupported_read'),
    (['view'],{'kind':'context','glyphLimit':1},None,'invalid_request'),
    (['view'],{'kind':'context','id':'other'},None,'invalid_request'),
    (['view'],{'kind':'context','cursor':1},None,'invalid_request'),
    (['view'],None,[{'kind':'context'},{'kind':'selection'}],'invalid_request'),
])
def test_explicit_contract(fields,selector,entities,code):
    *_,read=setup()
    with pytest.raises(BridgeError) as error: read(fields,selector,entities)
    assert error.value.code==code

def test_current_marker_and_retained_target_survive_foreground_switch():
    font,_,app,adapter,doc,read=setup()
    other=NS(familyName='Other');app.fonts.append(other);app.font=other
    documents=adapter.list_documents()
    assert [d['isCurrent'] for d in documents]==[False,True]
    assert read()['master']['id']=='native-master'
    font.selection=Indexed([NS(name='fresh')])
    assert read()['selectedGlyphs']['items']==['fresh']
    assert adapter.document_state(doc)['dirty'] is True
    app.fonts.remove(font)
    with pytest.raises(BridgeError) as error: read()
    assert error.value.code=='document_not_found'
    replacement=NS();app.fonts.append(replacement)
    assert adapter._id(replacement)!=doc

@pytest.mark.parametrize('native',[None,'missing'])
def test_no_current_and_unavailable_current_are_distinct(native):
    _,_,app,adapter,_,_=setup()
    if native is None: app.font=None
    else: del app.font
    assert adapter.list_documents()[0]['isCurrent'] is (False if native is None else None)

def test_routing_reference_and_mirrors():
    entry=(ROOT/'skills/glyphs/SKILL.md').read_text()
    assert 'context-reads.md' in entry
    ref=ROOT/'skills/glyphs/references/context-reads.md'
    for term in ('document.context.v1','100','selectedLayers','unavailable','complete:false',
                 'installation needs updating','repeated','no Save'):
        assert term in ' '.join(ref.read_text().split())
    for name in ('context-reads.md','selection-reads.md','document-targeting.md'):
        source=ROOT/'skills/glyphs/references'/name
        assert source.read_bytes()==(ROOT/'plugins/glyphs-mcp/skills/glyphs/references'/name).read_bytes()
