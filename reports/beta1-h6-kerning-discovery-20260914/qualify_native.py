"""H6 installed qualification via public MCP; native setup and proofs separate."""
from GlyphsApp import Glyphs,GSFont,GSGlyph,GSFontMaster
import objc
from pathlib import Path
from threading import Thread
from datetime import datetime,timezone
from urllib.request import Request,urlopen
import json,hashlib,re,time,os,traceback,sys,builtins,gzip
from glyphs_mcp_bridge.lifecycle import bridge_lifecycle as life
from glyphs_mcp_bridge.main_thread import CocoaMainThread
from glyphs_mcp_bridge import kerning_inventory
S=Path('/Users/thierryc/Dev/github/thierryc/Glyphs-mcp-worktrees/v2/build/milestone7/desktop');OUT=S/'reports/beta1-h6-kerning-discovery-20260914'
sys.path.insert(0,str(OUT));import h6_oracle as oracle
T=Path('/private/tmp/glyphs-h6-20260914');TEMP=T/'live';TEMP.mkdir(exist_ok=True)
manifest=json.loads((S/'build/h6-kerning-discovery-candidate-20260914/Lean/manifest.json').read_text())
fixtures=json.loads((OUT/'fixtures.json').read_bytes() if (OUT/'fixtures.json').exists() else gzip.decompress((OUT/'fixtures.json.gz').read_bytes()))['fixtures'];sources={x['label']:x for x in fixtures}
ns={'__file__':str(S.parents[2]/'scripts/selection_fixture.py'),'__name__':'h5_selection'};exec(compile(Path(ns['__file__']).read_text(),ns['__file__'],'exec'),ns)
main=CocoaMainThread(timeout=60);fonts={};facts=dict(startedAt=datetime.now(timezone.utc).isoformat(),loadBefore=os.getloadavg(),checks=[],calls=[],trials=[],callbacks=[])
original_call=life.server.main_thread.call;original_count=kerning_inventory._count;original_side=kerning_inventory._side
counts=lookups=0
def counted_count(table):
 global counts
 counts+=1;return original_count(table)
def counted_side(font,key):
 global lookups
 lookups+=int(not key.startswith('@'));return original_side(font,key)
def measured_call(callback):
 queued=time.perf_counter()
 def measured():
  global counts,lookups
  started=time.perf_counter();counts=lookups=0
  try:return callback()
  finally:facts['callbacks'].append(dict(queueMs=(started-queued)*1000,nativeMs=(time.perf_counter()-started)*1000,countReads=counts,glyphLookups=lookups))
 return original_call(measured)
life.server.main_thread.call=measured_call;kerning_inventory._count=counted_count;kerning_inventory._side=counted_side
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
def page(doc,master,direction='LTR',cursor=None,limit=100,phase='control',fields=None,**filters):
 request=dict(kind='kerning_pairs',master=master,direction=direction,limit=limit,**filters)
 if cursor is not None:request['cursor']=cursor
 return call('read_entities',dict(document_id=doc,entities=[request],fields=['left','right','value'] if fields is None else fields),phase)
def inventory(name,doc,master,direction='LTR',phase='control',limit=100,roundtrip=True,**filters):
 before,expected=main.call(lambda:(proof(fonts[name]),oracle.rows(fonts[name],master,direction,filters.get('leftKey'),filters.get('rightKey'))))
 cursor=None;items=[];http=0;requests=0;cb_start=len(facts['callbacks']);call_start=len(facts['calls'])
 while True:
  body,ms=page(doc,master,direction,cursor,limit,phase,**filters);http+=ms;requests+=1;check(name+' '+direction+' page '+str(requests)+' ok',True,body.get('ok'))
  result=body['data'][0]['values'];check(name+' page bounds',True,result['returned']==len(result['items'])<=limit and result['total'] is None and result['scanned']<=256)
  check(name+' page exact rows',expected[len(items):len(items)+result['returned']],result['items']);items.extend(result['items']);cursor=result['nextCursor']
  cb=[c for c in facts['calls'][-1]['callbacks'] if c['countReads']];check(name+' bounded native counts',True,len(cb)==1 and cb[0]['countReads']<=result['scanned']+2 and cb[0]['glyphLookups']<=200)
  if result['complete']:check(name+' completion',None,cursor);break
  check(name+' incomplete cursor',True,isinstance(cursor,str) and cursor.startswith('k1.'));assert requests<100
 check(name+' all expected entries',expected,items);page_calls=list(range(call_start,len(facts['calls'])))
 if roundtrip:
  valid=[r for r in items if 'unresolved' not in (r['left']['kind'],r['right']['kind'])]
  for offset in range(0,len(valid),100):
   batch=valid[offset:offset+100];targets=[dict(kind='kerning',master=master,direction=direction,left=r['left']['key'] if r['left']['kind']=='group' else r['left']['glyph'],right=r['right']['key'] if r['right']['kind']=='group' else r['right']['glyph']) for r in batch]
   body,_=call('read_entities',dict(document_id=doc,entities=targets,fields=['value']),'roundtrip');check(name+' existing exact values '+str(offset),[r['value'] for r in batch],[r['values']['value'] for r in body['data']])
 check(name+' native preservation',before,main.call(lambda:proof(fonts[name])))
 return dict(readMs=http,requests=requests,total=len(items),callIndices=page_calls)
def restore_originals():
 prior=json.loads((T/'runtime-before.json').read_text())[-1]['response']['result']['structuredContent']['data']
 for row in prior:
  assert row['dirty'] is False
  if not any(str(f.filepath)==row['path'] for f in Glyphs.fonts):Glyphs.open(row['path'],True)
 first=next(r['path'] for r in prior if r['isCurrent']);next(f for f in Glyphs.fonts if str(f.filepath)==first).show()
def run():
 try:
  facts['initialize']=rpc('initialize',dict(protocolVersion='2025-03-26',capabilities={},clientInfo={'name':'H6 qualification','version':'1'}));facts['catalog']=rpc('tools/list',{})
  status,_=call('get_status');facts['runtime']=status['data']
  check('seven tools',sorted(manifest['tools']),sorted(t['name'] for t in facts['catalog']['tools']));check('five jobs',['kerning_collision','slant','spacing','start_nodes','width_delta'],sorted(status['data']['jobKinds']))
  for component in ('sidecar','bridge'):
   actual=status['data'] if component=='sidecar' else status['data']['bridge'];check(component+' running fingerprint',manifest[component]['codeHash'],actual['codeHash'])
  for cap in ('kerning.groups.v1','kerning.pairs.v1','layers.list.v1','glyphs.list.v1','document.context.v1','selection.context.v1'):check(cap+' negotiated',True,cap in status['data']['readCapabilities'])
  main.call(restore_originals);original=main.call(lambda:{str(f.filepath):proof(f) for f in Glyphs.fonts});facts['originalFiles']={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in original}
  path=main.call(lambda:open_copy('synthetic','unrelated'));unrelated_doc,_,_=discover(path);unrelated_before=main.call(lambda:proof(fonts['unrelated']))
  for label,source,mi in (('small','synthetic',0),('many','synthetic',1),('RobotoSlab','RobotoSlab',0)):
   for phase in ('first','warmup','rep1','rep2','rep3','rep4','rep5'):
    name=label+'-'+phase;path=main.call(lambda:open_copy(source,name));doc,discovery,docs=discover(path);master=main.call(lambda:fonts[name].masters[mi].id)
    result=inventory(name,doc,master,phase=phase);facts['trials'].append(dict(label=label,phase=phase,discoveryMs=discovery,initialTotalMs=discovery+result['readMs'],openDocuments=docs,hostLoad=os.getloadavg(),**result));save();main.call(lambda:close_copy(name))
  path=main.call(lambda:open_copy('synthetic','controls'));doc,_,_=discover(path);mids=main.call(lambda:[m.id for m in fonts['controls'].masters])
  main.call(lambda:fonts['unrelated'].show());inventory('controls',doc,mids[0],phase='background-target')
  for name in ('A','V','ungrouped'):
   body,_=call('read_entities',dict(document_id=doc,entities=[dict(kind='glyph',id=name)],fields=oracle.GROUP_FIELDS));expected=main.call(lambda:{k:getattr(fonts['controls'].glyphs[name],k) for k in oracle.GROUP_FIELDS});check(name+' native group/key values',expected,body['data'][0]['values'])
  for m in mids:
   for d in ('LTR','RTL','vertical'):inventory('controls',doc,m,d,limit=37,roundtrip=True)
  for filt in (dict(leftKey='@MMK_L_rightA'),dict(rightKey='@MMK_R_V'),dict(leftKey='@MMK_L_rightA',rightKey='@MMK_R_V'),dict(leftKey='absent'),dict(rightKey='absent')):inventory('controls',doc,mids[1],phase='filter',**filt)
  body,_=call('read_entities',dict(document_id=doc,entities=[dict(kind='kerning',master=mids[0],direction='LTR',left='A',right='A')],fields=['value']));check('exact absence',None,body['data'][0]['values']['value'])
  before=main.call(lambda:proof(fonts['controls']))
  for sel,fields,code in ((dict(kind='glyph',id='missing'),['leftKerningKey'],'target_not_found'),(dict(kind='kerning_pairs',master='missing',direction='LTR'),['value'],'target_not_found'),(dict(kind='kerning_pairs',master=mids[0],direction='ltr'),['value'],'invalid_request'),(dict(kind='kerning_pairs',master=mids[0],direction='LTR',limit=101),['value'],'invalid_request'),(dict(kind='kerning_pairs',master=mids[0],direction='LTR',cursor='bad'),['value'],'invalid_request'),(dict(kind='kerning_pairs',master=mids[0],direction='LTR'),['effective'],'unsupported_read')):
   body,_=call('read_entities',dict(document_id=doc,entities=[sel],fields=fields));check('invalid '+str(sel),code,body['error']['code'])
  check('invalid requests preserved',before,main.call(lambda:proof(fonts['controls'])))
  main.call(lambda:fonts['controls'].parent.updateChangeCount_(0));check('dirty precondition',True,main.call(lambda:bool(fonts['controls'].parent.isDocumentEdited())));inventory('controls',doc,mids[1],phase='dirty')
  # Create deliberate native storage edge cases only in this disposable copy.
  def edges():
   f=fonts['controls'];m=mids[0]
   for i in range(205):f.setKerningForPair(m,'@MMK_L_wide','@MMK_R_'+str(i),-.25-i)
   t=f.kerningLTR[m];t.setObject_forKey_(objc.lookUpClass('MGOrderedDictionary').new(),'@MMK_L_empty');t.objectForKey_('@MMK_L_wide').setObject_forKey_(-.75,'H6_UNKNOWN')
   f.kerningVertical.removeObjectForKey_(m)
  main.call(edges);inventory('controls',doc,mids[0],phase='native-wide-empty-unresolved',limit=37);inventory('controls',doc,mids[0],'vertical',phase='empty-table')
  # Value, insertion and deletion guards on fresh clean copies.
  main.call(lambda:close_copy('controls'))
  for mode in ('value','add','delete','group'):
   path=main.call(lambda:open_copy('synthetic',mode));doc,_,_=discover(path);m=mids[0];first,_=page(doc,m,limit=1);cursor=first['data'][0]['values']['nextCursor'];boundary=first['data'][0]['values']['items'][0]
   def mutate():
    f=fonts[mode];t=f.kerningLTR[m]
    if mode=='value':t.objectForKey_(boundary['left']['key']).setObject_forKey_(123.25,boundary['right']['key'])
    elif mode=='add':f.setKerningForPair(m,'@MMK_L_new','@MMK_R_new',-.25)
    elif mode=='delete':t.removeObjectForKey_(boundary['left']['key'])
    else:f.glyphs['A'].leftKerningGroup='Changed';f.parent.updateChangeCount_(0)
   main.call(mutate);body,_=page(doc,m,cursor=cursor,limit=1);check(mode+' stale rejection','stale_kerning_cursor',body['error']['code']);inventory(mode,doc,m,phase='recovery');main.call(lambda:close_copy(mode))
  path=main.call(lambda:open_copy('synthetic','lifetime'));doc,_,_=discover(path);first,_=page(doc,mids[0],limit=1);cursor=first['data'][0]['values']['nextCursor']
  body,_=page(doc,mids[0],'RTL',cursor=cursor);check('wrong direction cursor','stale_kerning_cursor',body['error']['code'])
  main.call(lambda:close_copy('lifetime'));body,_=page(doc,mids[0],cursor=cursor);check('closed ID','document_not_found',body['error']['code'])
  main.call(lambda:open_copy('synthetic','lifetime'));newdoc,_,_=discover(path);check('reopened new ID',True,doc!=newdoc);body,_=page(newdoc,mids[0],cursor=cursor);check('old cursor on replacement','stale_kerning_cursor',body['error']['code']);inventory('lifetime',newdoc,mids[0],phase='new-id-recovery');main.call(lambda:close_copy('lifetime'))
  check('unrelated exact preservation',unrelated_before,main.call(lambda:proof(fonts['unrelated'])))
  for p,before in original.items():check('original unchanged '+p,before,main.call(lambda:proof(next(f for f in Glyphs.fonts if str(f.filepath)==p))));check('original file unchanged '+p,facts['originalFiles'][p],hashlib.sha256(Path(p).read_bytes()).hexdigest())
  for fixture in fixtures:check(fixture['label']+' baseline unchanged',fixture['sourceSHA256'],hashlib.sha256(Path(fixture['path']).read_bytes()).hexdigest())
  facts['passed']=True
 except Exception:facts['passed']=False;facts['error']=traceback.format_exc()
 finally:
  def cleanup():
   life.server.main_thread.call=original_call;kerning_inventory._count=original_count;kerning_inventory._side=original_side
   for name in list(fonts):close_copy(name)
   prior=json.loads((T/'runtime-before.json').read_text())[-1]['response']['result']['structuredContent']['data'];p=next(r['path'] for r in prior if r['isCurrent']);f=next((f for f in Glyphs.fonts if str(f.filepath)==p),None)
   if f is not None:f.show()
  try:main.call(cleanup)
  except Exception:facts['cleanupError']=traceback.format_exc()
  facts['finishedAt']=datetime.now(timezone.utc).isoformat();facts['loadAfter']=os.getloadavg();save();print('H6 NATIVE FINISHED',facts.get('passed'),facts.get('error',''))
Thread(target=run,name='H6 bounded native qualification',daemon=True).start();print('H6 installed qualification started')
