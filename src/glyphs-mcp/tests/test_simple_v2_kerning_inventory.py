"""H6 bounded storage discovery; no effective kerning or editing."""
import base64,json
from types import SimpleNamespace as NS
from pathlib import Path
import pytest
from test_simple_v2_glyphs_adapter import adapter
from glyphs_mcp_bridge.core import BridgeCore,BridgeError
from glyphs_mcp_bridge.kerning_inventory import GROUP_FIELDS
from glyphs_mcp_protocol.reads import READ_CAPABILITIES

class Table:
 def __init__(self,rows=()):self.rows=dict(rows);self.keys=list(self.rows);self.visits=[]
 def count(self):return len(self.keys)
 def keyAtIndex_(self,i):self.visits.append(i);assert 0<=i<len(self.keys);return self.keys[i]
 def objectForKey_(self,key):return self.rows.get(key)
 def __iter__(self):raise AssertionError('unbounded table traversal')
 def allKeys(self):raise AssertionError('unbounded keys copy')

def setup(groups=3,pairs=101):
 a,_=adapter();f=a.glyphs.fonts[0];f.masters={'m1':NS(id='m1'),'m2':NS(id='m2')};f.parent=NS(isDocumentEdited=False,changeCount=7)
 t=Table(('G'+str(i),Table(('R'+str(j),float(j)-0.25) for j in range(pairs))) for i in range(groups))
 f.kerningLTR=Table([('m1',t)]);f.kerningRTL=f.kerningLTR;f.kerningVertical=f.kerningLTR;f.lookups=[]
 def lookup(key):f.lookups.append(key);return NS(name='name'+key) if key!='unknown' else None
 f.glyphForId_=lookup;doc=a.list_documents()[0]['id'];core=BridgeCore(a,lambda cb:cb())
 def page(selector=None,fields=None,entities=None):return core.read_entities(doc,entities or [dict({'kind':'kerning_pairs','master':'m1','direction':'LTR'},**(selector or {}))],['left','right','value'] if fields is None else fields)[0]['values']
 return a,f,t,page

@pytest.mark.parametrize('groups,pairs',[(0,0),(1,0),(300,0),(1,1),(1,100),(1,101),(4,80),(1000,1)])
@pytest.mark.parametrize('limit',[1,37,100])
def test_pages_are_exact_bounded_and_do_not_rescan(groups,pairs,limit):
 _,f,t,page=setup(groups,pairs);items=[];cursor=None;last=-1
 while True:
  t.visits.clear();p=page(dict(limit=limit,**({'cursor':cursor} if cursor else {})))
  assert p['returned']==len(p['items'])<=limit and p['scanned']<=256 and p['total'] is None
  assert len(t.visits)<=257 and all(i>=max(0,last-1) for i in t.visits)
  items.extend(p['items']);cursor=p['nextCursor']
  if p['complete']:assert cursor is None;break
  assert cursor is not None;last=json.loads(base64.urlsafe_b64decode(cursor[3:]))['i']
 assert len(items)==groups*pairs
 assert [(r['left']['key'],r['right']['key'],r['value']) for r in items]==[('G'+str(i),'R'+str(j),j-.25) for i in range(groups) for j in range(pairs)]
 assert len(f.lookups)==len(items)*2

@pytest.mark.parametrize('filters,count',[(dict(leftKey='G1'),101),(dict(leftKey='missing'),0),(dict(rightKey='R3'),3),(dict(rightKey='absent'),0),(dict(leftKey='G2',rightKey='R0'),1)])
def test_exact_raw_filters(filters,count):
 _,_,_,page=setup();p=page(filters);items=p['items']
 while not p['complete']:p=page(dict(**filters,cursor=p['nextCursor']));items+=p['items']
 assert len(items)==count

def test_filtered_misses_and_empty_groups_cost_work_and_can_yield_empty_pages():
 _,_,t,page=setup(600,1);p=page(dict(rightKey='nope'));assert not p['complete'] and p['returned']==0 and p['scanned']==256
 p2=page(dict(rightKey='nope',cursor=p['nextCursor']));assert not p2['complete'] and p2['returned']==0
 p3=page(dict(rightKey='nope',cursor=p2['nextCursor']));assert p3['complete'] and p3['scanned']==88

@pytest.mark.parametrize('direction',['LTR','RTL','vertical'])
def test_direction_tables_and_stored_zero_unresolved_groups(direction):
 _,f,t,page=setup(1,1);table=Table([('@MMK_L_A',Table([('unknown',0),('R0',-.125)]))]);setattr(f,{'LTR':'kerningLTR','RTL':'kerningRTL','vertical':'kerningVertical'}[direction],Table([('m1',table)]))
 p=page(dict(direction=direction));assert p['items'][0]==dict(left=dict(key='@MMK_L_A',glyph=None,kind='group'),right=dict(key='unknown',glyph=None,kind='unresolved'),value=0)
 assert p['items'][1]['value']==-.125

@pytest.mark.parametrize('fields',[['left'],['right'],['value'],['value','left']])
def test_requested_fields_only(fields):
 _,f,_,page=setup(1,1);p=page(fields=fields);assert set(p['items'][0])==set(fields);assert len(f.lookups)==len(set(fields)-{'value'})

@pytest.mark.parametrize('change',['count','inner-count','boundary-value','generation','dirty','master','direction','leftKey','rightKey'])
def test_stale_cursor(change):
 _,f,t,page=setup();cursor=page()['nextCursor'];selector=dict(cursor=cursor)
 if change=='count':t.keys.pop()
 elif change=='inner-count':t.rows['G0'].keys.pop()
 elif change=='boundary-value':t.rows['G0'].rows['R99']=1000
 elif change=='generation':f.parent.changeCount+=1
 elif change=='dirty':f.parent.isDocumentEdited=True
 elif change=='master':selector['master']='m2'
 elif change=='direction':selector['direction']='RTL'
 else:selector[change]='G0'
 with pytest.raises(BridgeError) as e:page(selector)
 assert e.value.code=='stale_kerning_cursor'

@pytest.mark.parametrize('selector,code',[(dict(limit=v),'invalid_request') for v in (0,101,-1,True,'3',None)]+[(dict(direction=v),'invalid_request') for v in ('ltr',None,[],4)]+[(dict(master='missing'),'target_not_found'),(dict(master=''),'invalid_request'),(dict(leftKey=''),'invalid_request'),(dict(rightKey=[]),'invalid_request'),(dict(foo=1),'invalid_request')])
def test_bad_requests(selector,code):
 *_,page=setup()
 with pytest.raises(BridgeError) as e:page(selector)
 assert e.value.code==code

@pytest.mark.parametrize('cursor',[None,{},1,'','k1.!','g1.W10=','k1.W10=','k1.'+'a'*8192])
def test_bad_cursors(cursor):
 *_,page=setup()
 with pytest.raises(BridgeError) as e:page(dict(cursor=cursor))
 assert e.value.code=='invalid_request'

def test_bad_fields_mixed_selectors_and_unavailable_native_data():
 _,f,_,page=setup()
 for fields in (['effective'],['left','pairs']):
  with pytest.raises(BridgeError,match='fields'):page(fields=fields)
 with pytest.raises(BridgeError,match='only entity'):page(entities=[dict(kind='kerning_pairs'),dict(kind='glyph',id='A')])
 f.kerningLTR=Table([('m1',{})])
 with pytest.raises(BridgeError,match='indexed native'):page()

def test_group_fields_reuse_existing_named_reads():
 a,f,_,_=setup();g=NS(**{k:('A' if k.endswith('Key') else None) for k in GROUP_FIELDS});f.glyphs={'A':g};doc=a.list_documents()[0]['id']
 assert a.read_entities(doc,[dict(kind='glyph',id='A')],sorted(GROUP_FIELDS))[0]['values']==vars(g)

def test_dirty_fresh_reads_no_save_and_no_unrequested_lookup():
 _,f,t,page=setup(1,1);f.parent.isDocumentEdited=True
 assert page(fields=['value'])['items']==[dict(value=-.25)]
 t.rows['G0'].rows['R0']=0;assert page(fields=['value'])['items']==[dict(value=0)] and f.lookups==[]

def test_silent_nonboundary_edits_do_not_claim_an_atomic_snapshot():
 _,_,t,page=setup();cursor=page()['nextCursor'];t.rows['G0'].rows['R0']=123
 assert page(dict(cursor=cursor))['returned']==100

def test_capabilities_skill_mirrors_and_no_new_tool():
 root=Path(__file__).resolve().parents[3]
 assert {'kerning.groups.v1','kerning.pairs.v1'}<=set(READ_CAPABILITIES)
 for name in ('glyphs','glyphs-mcp-kerning'):
  for p in (root/'skills'/name).rglob('*'):
   if p.is_file() and '__pycache__' not in p.parts:assert p.read_bytes()==(root/'plugins/glyphs-mcp/skills'/name/p.relative_to(root/'skills'/name)).read_bytes()
 ref=(root/'skills/glyphs/references/kerning-discovery.md').read_text()
 for word in ('kerning.groups.v1','kerning.pairs.v1','leftKey','rightKey','256','100','unresolved','total','stale_kerning_cursor','update','not atomic'):assert word in ref

@pytest.mark.parametrize('amount',[True,'12',float('inf'),float('nan')])
def test_bad_native_amount_is_explicitly_unavailable(amount):
 _,_,t,page=setup(1,1);t.rows['G0'].rows['R0']=amount
 with pytest.raises(BridgeError,match='nonfinite'):page()

def test_native_numeric_subclasses_are_valid():
 class NativeFloat(float):pass
 _,_,t,page=setup(1,1);t.rows['G0'].rows['R0']=NativeFloat(-.125)
 assert page()['items'][0]['value']==-.125
