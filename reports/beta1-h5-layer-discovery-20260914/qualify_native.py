"""H5 installed qualification via public MCP; native setup and proofs separate."""
from GlyphsApp import Glyphs,GSFont,GSGlyph,GSFontMaster
from pathlib import Path
from threading import Thread
from datetime import datetime,timezone
from urllib.request import Request,urlopen
import json,hashlib,re,time,os,traceback,sys,builtins
from glyphs_mcp_bridge.lifecycle import bridge_lifecycle as life
from glyphs_mcp_bridge.main_thread import CocoaMainThread
from glyphs_mcp_bridge import layer_inventory
S=Path('/Users/thierryc/Dev/github/thierryc/Glyphs-mcp-worktrees/v2/build/milestone7/desktop');OUT=S/'reports/beta1-h5-layer-discovery-20260914'
sys.path.insert(0,str(OUT));import h5_oracle as oracle
T=Path('/private/tmp/glyphs-h5-20260914');TEMP=T/'live';TEMP.mkdir(exist_ok=True)
manifest=json.loads((S/'build/h5-layer-discovery-candidate-20260914/Lean/manifest.json').read_text())
fixtures=json.loads((OUT/'fixtures.json').read_text())['fixtures'];sources={x['label']:x for x in fixtures}
ns={'__file__':str(S.parents[2]/'scripts/selection_fixture.py'),'__name__':'h5_selection'};exec(compile(Path(ns['__file__']).read_text(),ns['__file__'],'exec'),ns)
main=CocoaMainThread(timeout=60);fonts={};facts=dict(startedAt=datetime.now(timezone.utc).isoformat(),loadBefore=os.getloadavg(),checks=[],calls=[],trials=[],callbacks=[])
original_call=life.server.main_thread.call;original_value=layer_inventory.value
visits=[];counts=0
def counted_value(owner,name,default=None):
 global counts
 if name=='countOfLayers':counts+=1
 return original_value(owner,name,default)
def counted_getattr(owner,name,default=None):
 result=builtins.getattr(owner,name,default)
 if name!='objectInLayersAtIndex_' or not callable(result):return result
 def indexed(i):visits.append(i);return result(i)
 return indexed
def measured_call(callback):
 queued=time.perf_counter()
 def measured():
  global visits,counts
  started=time.perf_counter();visits=[];counts=0
  try:return callback()
  finally:
   if len(facts['callbacks'])<400:facts['callbacks'].append(dict(queueMs=(started-queued)*1000,nativeMs=(time.perf_counter()-started)*1000,indices=visits,countReads=counts))
 return original_call(measured)
life.server.main_thread.call=measured_call;layer_inventory.value=counted_value;layer_inventory.getattr=counted_getattr

def save():(OUT/'native-facts.json').write_text(json.dumps(facts,indent=2))
def check(name,expected,observed):
 ok=expected==observed;facts['checks'].append(dict(name=name,expected=expected,observed=observed,passed=ok));save();assert ok,name
def rpc(method,params):
 req=Request('http://127.0.0.1:9680/mcp/',data=json.dumps(dict(jsonrpc='2.0',id=len(facts['calls'])+1,method=method,params=params)).encode(),headers={'Content-Type':'application/json','Accept':'application/json, text/event-stream','MCP-Protocol-Version':'2025-03-26'})
 with urlopen(req,timeout=40) as response:raw=response.read().decode()
 result=json.loads(next(x[5:].strip() for x in raw.splitlines() if x.startswith('data:')) if raw.startswith(('event:','data:')) else raw)
 if 'error' in result:raise RuntimeError(result['error'])
 return result['result']
def call(name,args={},phase='control'):
 at=datetime.now(timezone.utc).isoformat();start=time.perf_counter();index=len(facts['callbacks']);raw=rpc('tools/call',dict(name=name,arguments=args));ms=(time.perf_counter()-start)*1000
 body=raw.get('structuredContent') or json.loads(next(x['text'] for x in raw['content'] if x['type']=='text'))
 facts['calls'].append(dict(at=at,tool=name,arguments=args,phase=phase,httpMs=ms,result=body,callbacks=facts['callbacks'][index:]));save();return body,ms
def discover(path,family=None):
 result,ms=call('list_documents');assert result['ok'];rows=[x for x in result['data'] if x['path']==path and (family is None or x['familyName']==family)];assert len(rows)==1;return rows[0]['id'],ms,len(result['data'])
def open_copy(label,name):
 source=Path(sources[label]['path']);assert hashlib.sha256(source.read_bytes()).hexdigest()==sources[label]['sourceSHA256']
 path=TEMP/(name+'.glyphs');path.write_text(re.sub(r'(?m)^\.appVersion = .*?;', '.appVersion = "4107";',source.read_text(),count=1));fonts[name]=Glyphs.open(str(path),True);return str(path)
def close_copy(name):fonts.pop(name).close(ignoreChanges=True)
def proof(f):return dict(data=oracle.digest(oracle.snapshot(f)),selection=ns['selection_state'](f),selectedGlyphs=[g.name for g in f.selection],dirty=bool(f.parent.isDocumentEdited()))
def page(doc,glyph,cursor=None,limit=100,phase='control',fields=None):
 return call('read_entities',dict(document_id=doc,entities=[dict(kind='layers',glyph=glyph,limit=limit,**({'cursor':cursor} if cursor else {}))],fields=list(oracle.FIELDS) if fields is None else fields),phase)
def inventory(name,doc,glyph,label,phase='control',limit=100):
 before,expected=main.call(lambda:(proof(fonts[name]),oracle.rows(fonts[name].glyphs[glyph])))
 cursor=None;items=[];http=0;requests=0
 while True:
  body,ms=page(doc,glyph,cursor,limit,phase);http+=ms;requests+=1;check(label+' page '+str(requests)+' ok',True,body.get('ok'))
  result=body['data'][0]['values'];offset=len(items);returned=min(limit,len(expected)-offset)
  check(label+' page '+str(requests)+' values',dict(items=expected[offset:offset+returned],total=len(expected),returned=returned,complete=offset+returned==len(expected)),{k:result[k] for k in ('items','total','returned','complete')})
  cb=facts['calls'][-1]['callbacks'];assert len(cb)==1
  check(label+' page '+str(requests)+' bounded indices',([offset-1] if offset else [])+list(range(offset,offset+returned)),cb[0]['indices']);check(label+' page '+str(requests)+' one native count',1,cb[0]['countReads'])
  items.extend(result['items']);cursor=result['nextCursor']
  if result['complete']:check(label+' terminal cursor',None,cursor);break
  assert requests<100
 check(label+' exact inventory',expected,items)
 # Exact-ID public round trips, independently measured after the inventory.
 for start in range(0,len(items),100):
  targets=[dict(kind='layer',glyph=glyph,id=row['id']) for row in items[start:start+100]]
  actual,_=call('read_entities',dict(document_id=doc,entities=targets,fields=['id','name','width']),phase='roundtrip')
  exp=main.call(lambda:[dict(id=t['id'],name=fonts[name].glyphs[glyph].layerForId_(t['id']).name,width=fonts[name].glyphs[glyph].layerForId_(t['id']).width) for t in targets])
  check(label+' exact-ID round trip '+str(start),exp,[r['values'] for r in actual['data']])
 check(label+' all-layer native preservation',before,main.call(lambda:proof(fonts[name])))
 return dict(readMs=http,requests=requests,total=len(items))
def run():
 try:
  facts['initialize']=rpc('initialize',dict(protocolVersion='2025-03-26',capabilities={},clientInfo={'name':'H5 qualification','version':'1'}));facts['catalog']=rpc('tools/list',{})
  status,_=call('get_status');facts['runtime']=status['data']
  check('seven tools',sorted(manifest['tools']),sorted(t['name'] for t in facts['catalog']['tools']));check('five jobs',['kerning_collision','slant','spacing','start_nodes','width_delta'],sorted(status['data']['jobKinds']))
  for component in ('sidecar','bridge'):
   actual=status['data'] if component=='sidecar' else status['data']['bridge'];check(component+' running fingerprint',manifest[component]['codeHash'],actual['codeHash'])
  for cap in ('layers.list.v1','glyphs.list.v1','document.context.v1','selection.context.v1'):check(cap+' negotiated',True,cap in status['data']['readCapabilities'])
  original=main.call(lambda:{str(f.filepath):proof(f) for f in Glyphs.fonts})
  path=main.call(lambda:open_copy('synthetic','unrelated'));unrelated_doc,_,_=discover(path);unrelated_before=main.call(lambda:proof(fonts['unrelated']))
  for label,source,glyph in (('small','synthetic','a'),('many','synthetic','many'),('RobotoSlab','RobotoSlab','a')):
   for phase in ('first','warmup','rep1','rep2','rep3','rep4','rep5'):
    name=label+'-'+phase;path=main.call(lambda:open_copy(source,name));doc,discovery,docs=discover(path)
    result=inventory(name,doc,glyph,name,phase);facts['trials'].append(dict(label=label,phase=phase,glyph=glyph,discoveryMs=discovery,initialTotalMs=discovery+result['readMs'],openDocuments=docs,**result));save();main.call(lambda:close_copy(name))
  path=main.call(lambda:open_copy('synthetic','controls'));doc,_,_=discover(path)
  # A retained ID targets this copy while another font is foreground.
  main.call(lambda:fonts['unrelated'].show());inventory('controls',doc,'a','background target')
  result,_=call('read_entities',dict(document_id=doc,entities=[dict(kind='glyphs')],fields=['name']));check('H4 glyph inventory retained',['a','b','many'],[r['name'] for r in result['data'][0]['values']['items']])
  for mi in range(3):
   def select():
    f=fonts['controls'];f.masterIndex=mi;l=f.glyphs['a'].layerForId_(f.masters[mi].id)
    if f.currentTab is None:f.newTab([l])
    else:f.currentTab.layers=[l]
    l.clearSelection();l.addSelection_(l.paths[0].nodes[0]);return l.layerId
   layer_id=main.call(select)
   result,_=call('read_entities',dict(document_id=doc,entities=[dict(kind='selection')],fields=['glyph','layer','selectedNodeCount','nodes']))
   v=result['data'][0]['values'];check('master '+str(mi)+' H3 selection',['a',layer_id,1,1],[v['glyph'],v['layer'],v['selectedNodeCount'],v['nodes']['total']])
  main.call(lambda:fonts['controls'].parent.updateChangeCount_(0));check('dirty precondition',True,main.call(lambda:bool(fonts['controls'].parent.isDocumentEdited())))
  inventory('controls',doc,'a','dirty multi-page',limit=3)
  for selector,fields,code in ((dict(kind='layers',glyph='missing'),['id'],'target_not_found'),(dict(kind='layers',glyph='a',limit=0),['id'],'invalid_request'),(dict(kind='layers',glyph='a',limit=101),['id'],'invalid_request'),(dict(kind='layers',glyph='a',cursor='bad'),['id'],'invalid_request'),(dict(kind='layers',glyph='a'),['bounds'],'unsupported_read'),(dict(kind='layers',glyph='a'),[],'invalid_request'),(dict(kind='layers',glyph='a'),['id','classification'],'unsupported_read'),(dict(kind='layers'),['id'],'invalid_request'),(dict(kind='layer',glyph='a',id='Duplicate'),['id'],'target_not_found')):
   result,_=call('read_entities',dict(document_id=doc,entities=[selector],fields=fields));check('invalid '+str(selector)+str(fields),code,result['error']['code'])
  main.call(lambda:close_copy('controls'))
  for mode in ('add','delete','rename-boundary','observed-association'):
   path=main.call(lambda:open_copy('synthetic',mode));doc,_,_=discover(path);first,_=page(doc,'a',limit=6);cursor=first['data'][0]['values']['nextCursor']
   def mutate():
    f=fonts[mode];g=f.glyphs['a']
    if mode=='add':l=g.layerForId_('H5_BACKUP').copy();g.setLayer_forId_(l,'H5_ADDED')
    elif mode=='delete':g.removeLayerForId_('H5_BACKUP')
    elif mode=='rename-boundary':g.layerForId_('H5_BACKUP').name='Renamed'
    else:g.layerForId_('H5_BACKUP').associatedMasterId=f.masters[1].id;f.parent.updateChangeCount_(0)
   main.call(mutate);result,_=page(doc,'a',cursor,limit=6);check(mode+' stale rejection','stale_layer_cursor',result['error']['code']);inventory(mode,doc,'a',mode+' restarted');main.call(lambda:close_copy(mode))
  path=main.call(lambda:open_copy('synthetic','lifetime'));doc,_,_=discover(path);first,_=page(doc,'a',limit=6);cursor=first['data'][0]['values']['nextCursor']
  result,_=page(doc,'b',cursor,limit=6);check('cursor cannot change glyph','stale_layer_cursor',result['error']['code'])
  main.call(lambda:close_copy('lifetime'));result,_=page(doc,'a',cursor);check('closed ID','document_not_found',result['error']['code'])
  main.call(lambda:open_copy('synthetic','lifetime'));new_doc,_,_=discover(path);check('same path reopened new ID',True,new_doc!=doc)
  result,_=page(new_doc,'a',cursor);check('old cursor cannot target replacement','stale_layer_cursor',result['error']['code']);inventory('lifetime',new_doc,'a','fresh recovered');main.call(lambda:close_copy('lifetime'))
  check('unrelated document exact preservation',unrelated_before,main.call(lambda:proof(fonts['unrelated'])))
  for p,before in original.items():check('original font unchanged '+p,before,main.call(lambda:proof(next(f for f in Glyphs.fonts if str(f.filepath)==p))))
  for fixture in fixtures:check(fixture['label']+' baseline unchanged',fixture['sourceSHA256'],hashlib.sha256(Path(fixture['path']).read_bytes()).hexdigest())
  facts['passed']=True
 except Exception:facts['passed']=False;facts['error']=traceback.format_exc()
 finally:
  def cleanup():
   life.server.main_thread.call=original_call;layer_inventory.value=original_value;del layer_inventory.getattr
   for name in list(fonts):close_copy(name)
  try:main.call(cleanup)
  except Exception:facts['cleanupError']=traceback.format_exc()
  facts['finishedAt']=datetime.now(timezone.utc).isoformat();facts['loadAfter']=os.getloadavg();save();print('H5 NATIVE FINISHED',facts.get('passed'),facts.get('error',''))
Thread(target=run,name='H5 bounded native qualification',daemon=True).start();print('H5 installed qualification started')
