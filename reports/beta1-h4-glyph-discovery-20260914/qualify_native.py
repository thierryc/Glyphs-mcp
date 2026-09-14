"""Installed H4 qualification. Native helpers prepare/prove disposable fonts;
MCP reads and IDs come only from public HTTP. No public result is supplied by an
oracle. Temporary bounded visit/timing instrumentation is restored in finally.
"""
from GlyphsApp import Glyphs,GSGlyph
from pathlib import Path
from threading import Thread
from datetime import datetime,timezone
from urllib.request import Request,urlopen
import json,hashlib,re,time,os,traceback,objc
from glyphs_mcp_bridge.lifecycle import bridge_lifecycle as life
from glyphs_mcp_bridge.main_thread import CocoaMainThread
from glyphs_mcp_bridge import glyph_inventory
S=Path('/Users/thierryc/Dev/github/thierryc/Glyphs-mcp-worktrees/v2/build/milestone7/desktop')
OUT=S/'reports/beta1-h4-glyph-discovery-20260914';TEMP=Path('/private/tmp/glyphs-h4-20260914/live');TEMP.mkdir(exist_ok=True)
manifest=json.loads((S/'build/h4-glyph-discovery-candidate-20260914/Lean/manifest.json').read_text())
fixtures=json.loads((OUT/'fixtures.json').read_text())['fixtures'];sources={x['label']:x for x in fixtures}
ns={'__file__':str(S.parents[2]/'scripts/selection_fixture.py'),'__name__':'h4_oracle'}
exec(compile(Path(ns['__file__']).read_text(),ns['__file__'],'exec'),ns)
main=CocoaMainThread(timeout=60);fonts={}
facts=dict(startedAt=datetime.now(timezone.utc).isoformat(),loadBefore=os.getloadavg(),checks=[],calls=[],trials=[],callbacks=[])
original_call=life.server.main_thread.call;original_value=glyph_inventory.value
visits=[];counts=0
class Counted:
 def __init__(self, collection):self.collection=collection
 def __len__(self):
  global counts
  counts+=1;return len(self.collection)
 def __getitem__(self,index):visits.append(index);return self.collection[index]
 def __iter__(self):raise AssertionError('candidate tried to traverse a full native collection')
def counted_value(owner,name,default=None):
 result=original_value(owner,name,default)
 return Counted(result) if name=='glyphs' and result is not None else result
def measured_call(callback):
 queued=time.perf_counter()
 def measured():
  global visits,counts
  started=time.perf_counter();visits=[];counts=0
  try:return callback()
  finally:
   if len(facts['callbacks'])<400:facts['callbacks'].append(dict(queueMs=(started-queued)*1000,nativeMs=(time.perf_counter()-started)*1000,indices=visits,countReads=counts))
 return original_call(measured)
life.server.main_thread.call=measured_call;glyph_inventory.value=counted_value

def save():(OUT/'native-facts.json').write_text(json.dumps(facts,indent=2))
def check(name,expected,observed):
 ok=expected==observed;facts['checks'].append(dict(name=name,expected=expected,observed=observed,passed=ok));save();assert ok,name

def rpc(method,params):
 payload=dict(jsonrpc='2.0',id=len(facts['calls'])+1,method=method,params=params)
 req=Request('http://127.0.0.1:9680/mcp/',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Accept':'application/json, text/event-stream','MCP-Protocol-Version':'2025-03-26'})
 with urlopen(req,timeout=40) as response:
  text=response.read().decode()
  result=json.loads(next(line[5:].strip() for line in text.splitlines() if line.startswith('data:'))) if text.startswith(('event:','data:')) else json.loads(text)
 if 'error' in result:raise RuntimeError(result['error'])
 return result['result']
def call(name,args={},phase='control'):
 at=datetime.now(timezone.utc).isoformat();start=time.perf_counter();index=len(facts['callbacks'])
 raw=rpc('tools/call',dict(name=name,arguments=args));ms=(time.perf_counter()-start)*1000
 body=raw.get('structuredContent') or json.loads(next(c['text'] for c in raw['content'] if c['type']=='text'))
 facts['calls'].append(dict(at=at,tool=name,arguments=args,phase=phase,httpMs=ms,result=body,callbacks=facts['callbacks'][index:]));save()
 return body,ms

def discover(path):
 result,ms=call('list_documents');assert result['ok'],result
 rows=[d for d in result['data'] if d['path']==path];assert len(rows)==1
 return rows[0]['id'],ms,len(result['data'])
def page(doc,cursor=None,limit=100,phase='control'):
 selector=dict(kind='glyphs',limit=limit,**({'cursor':cursor} if cursor else {}))
 return call('read_entities',dict(document_id=doc,entities=[selector],fields=['name']),phase)
def digest(obj):return hashlib.sha256(json.dumps(obj,sort_keys=True,default=str).encode()).hexdigest()
def proof(font):
 # Independent full-font oracle, outside measured public callbacks.
 return dict(data=digest(ns['snapshot'](font)),glyphObjects=digest([int(objc.pyobjc_id(g)) for g in font.glyphs]),
             selection=ns['selection_state'](font),selectedGlyphs=[g.name for g in font.selection],dirty=bool(font.parent.isDocumentEdited()))
def names(font):return [g.name for g in font.pyobjc_instanceMethods.glyphs()]
def open_copy(label,name):
 source=Path(sources[label]['path']);assert hashlib.sha256(source.read_bytes()).hexdigest()==sources[label]['sourceSHA256']
 path=TEMP/(name+'.glyphs');path.write_text(re.sub(r'(?m)^\.appVersion = .*?;', '.appVersion = "4107";',source.read_text(),count=1))
 fonts[name]=Glyphs.open(str(path),True);return str(path)
def close_copy(name):fonts.pop(name).close(ignoreChanges=True)

def inventory(name,doc,label,phase='control',limit=100):
 before,expected=main.call(lambda:(proof(fonts[name]),names(fonts[name])))
 cursor=None;observed=[];http=0;requests=0
 while True:
  body,ms=page(doc,cursor,limit,phase);http+=ms;requests+=1
  check(label+' page '+str(requests)+' ok',True,body.get('ok'))
  result=body['data'][0]['values'];offset=len(observed);returned=min(limit,len(expected)-offset)
  check(label+' page '+str(requests)+' values',dict(items=[dict(name=n) for n in expected[offset:offset+returned]],total=len(expected),returned=returned,complete=offset+returned==len(expected)),{k:result[k] for k in ('items','total','returned','complete')})
  callbacks=facts['calls'][-1]['callbacks'];assert len(callbacks)==1
  check(label+' page '+str(requests)+' bounded native indices',([offset-1] if offset else [])+list(range(offset,offset+returned)),callbacks[0]['indices'])
  check(label+' page '+str(requests)+' native count reads',1,callbacks[0]['countReads'])
  observed.extend(x['name'] for x in result['items']);cursor=result['nextCursor']
  if result['complete']:
   check(label+' terminal cursor',None,cursor);break
  assert isinstance(cursor,str)
  assert requests<100,'bounded qualification loop'
 check(label+' complete inventory',expected,observed)
 check(label+' native preservation',before,main.call(lambda:proof(fonts[name])))
 return dict(readMs=http,requests=requests,total=len(observed))

def run():
 try:
  facts['initialize']=rpc('initialize',dict(protocolVersion='2025-03-26',capabilities={},clientInfo={'name':'H4 qualification','version':'1'}))
  facts['catalog']=rpc('tools/list',{})
  status,_=call('get_status');facts['runtime']=status['data']
  check('seven tools',sorted(manifest['tools']),sorted(t['name'] for t in facts['catalog']['tools']))
  check('five jobs',['kerning_collision','slant','spacing','start_nodes','width_delta'],sorted(status['data']['jobKinds']))
  for component in ('sidecar','bridge'):
   actual=status['data'] if component=='sidecar' else status['data']['bridge']
   check(component+' running fingerprint',manifest[component]['codeHash'],actual['codeHash'])
  check('new capability',True,'glyphs.list.v1' in status['data']['readCapabilities'])
  check('H3 preserved',True,'document.context.v1' in status['data']['readCapabilities'])
  protected=main.call(lambda:{str(f.filepath):proof(f) for f in Glyphs.fonts})
  for label in ('0','1'):
   path=main.call(lambda:open_copy(label,'count'+label));doc,_,_=discover(path)
   inventory('count'+label,doc,'count '+label);main.call(lambda:close_copy('count'+label))
  for label in ('100','101','RobotoSlab'):
   for phase in ('first','warmup','rep1','rep2','rep3','rep4','rep5'):
    name=label+'-'+phase;path=main.call(lambda:open_copy(label,name));doc,discovery_ms,documents=discover(path)
    result=inventory(name,doc,name,phase)
    facts['trials'].append(dict(label=label,phase=phase,discoveryMs=discovery_ms,initialTotalMs=discovery_ms+result['readMs'],openDocuments=documents,**result));save()
    main.call(lambda:close_copy(name))
  path=main.call(lambda:open_copy('101','dirty'));doc,_,_=discover(path)
  def make_dirty():
   fonts['dirty'].parent.updateChangeCount_(0)
  main.call(make_dirty)
  check('dirty precondition',True,main.call(lambda:bool(fonts['dirty'].parent.isDocumentEdited())))
  inventory('dirty',doc,'dirty font',limit=100)
  main.call(lambda:close_copy('dirty'))
  # Verify current H3 context and optional node details on a single fresh copy.
  path=main.call(lambda:open_copy('101','h3'));doc,_,_=discover(path)
  def select_layer():
   f=fonts['h3'];layer=f.glyphs[0].layers[f.masters[1].id];f.newTab([layer]);layer.clearSelection();layer.addSelection_(layer.paths[0].nodes[0])
   return layer.parent.name,layer.layerId
  expected_name,expected_layer=main.call(select_layer)
  context,_=call('read_entities',dict(document_id=doc,entities=[dict(kind='context')],fields=['view','master','selectedGlyphs']))
  check('H3 Edit View preserved','edit',context['data'][0]['values']['view'])
  selection,_=call('read_entities',dict(document_id=doc,entities=[dict(kind='selection')],fields=['glyph','layer','selectedNodeCount','nodes']))
  values=selection['data'][0]['values'];check('H3 node context preserved',(expected_name,expected_layer,1,1),(values['glyph'],values['layer'],values['selectedNodeCount'],values['nodes']['total']))
  main.call(lambda:close_copy('h3'))
  for mode in ('add','delete','rename-boundary','rename-earlier-observed'):
   path=main.call(lambda:open_copy('101',mode));doc,_,_=discover(path);first,_=page(doc);cursor=first['data'][0]['values']['nextCursor']
   def mutate():
    f=fonts[mode]
    if mode=='add':f.glyphs.append(GSGlyph('h4added'))
    elif mode=='delete':del f.glyphs[0]
    elif mode=='rename-boundary':f.glyphs[99].name='h4renamedBoundary'
    else:f.glyphs[0].name='h4renamedEarlier';f.parent.updateChangeCount_(0)
   main.call(mutate)
   result,_=page(doc,cursor);check(mode+' stale rejection','stale_glyph_cursor',result['error']['code'])
   inventory(mode,doc,mode+' restarted')
   main.call(lambda:close_copy(mode))
  path=main.call(lambda:open_copy('101','lifetime'));doc,_,_=discover(path);first,_=page(doc);cursor=first['data'][0]['values']['nextCursor']
  for selector,fields,code in ((dict(kind='glyphs',limit=0),['name'],'invalid_request'),(dict(kind='glyphs',limit=101),['name'],'invalid_request'),(dict(kind='glyphs',cursor='bad'),['name'],'invalid_request'),(dict(kind='glyphs'),[],'invalid_request'),(dict(kind='glyphs'),['unicode'],'unsupported_read')):
   result,_=call('read_entities',dict(document_id=doc,entities=[selector],fields=fields));check('invalid '+str(selector)+str(fields),code,result['error']['code'])
  main.call(lambda:close_copy('lifetime'))
  result,_=page(doc,cursor);check('closed ID','document_not_found',result['error']['code'])
  main.call(lambda:open_copy('101','lifetime'));new_doc,_,_=discover(path);check('reopened same path has new ID',True,new_doc!=doc)
  result,_=page(new_doc,cursor);check('cursor cannot move to replacement document','stale_glyph_cursor',result['error']['code'])
  inventory('lifetime',new_doc,'fresh recovered document');main.call(lambda:close_copy('lifetime'))
  for path,expected in protected.items():check('protected native contents '+path,expected,main.call(lambda:proof(next(f for f in Glyphs.fonts if str(f.filepath)==path))))
  for row in json.loads(Path('/private/tmp/glyphs-h4-20260914/protected-before-install.json').read_text()):
   check('protected disk across install',row['sha256'],hashlib.sha256(Path(row['path']).read_bytes()).hexdigest())
   check('protected data across install',digest(row['data']),main.call(lambda:digest(ns['snapshot'](next(f for f in Glyphs.fonts if str(f.filepath)==row['path'])))))
  for fixture in fixtures:check(fixture['label']+' source immutable',fixture['sourceSHA256'],hashlib.sha256(Path(fixture['path']).read_bytes()).hexdigest())
  facts['passed']=True
 except Exception:facts['passed']=False;facts['error']=traceback.format_exc()
 finally:
  def cleanup():
   life.server.main_thread.call=original_call;glyph_inventory.value=original_value
   for name in list(fonts):close_copy(name)
   if Glyphs.fonts:Glyphs.fonts[0].show()
  try:main.call(cleanup)
  except Exception:facts['cleanupError']=traceback.format_exc()
  facts['loadAfter']=os.getloadavg();facts['finishedAt']=datetime.now(timezone.utc).isoformat();save()
  print('H4 NATIVE FINISHED',facts.get('passed'),facts.get('error',''))
Thread(target=run,name='H4 bounded native qualification',daemon=True).start()
print('H4 installed qualification started')
