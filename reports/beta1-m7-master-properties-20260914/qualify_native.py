"""M7 installed public workflow; independent native setup/proof, disposable fonts."""
from GlyphsApp import Glyphs, GSAxis
from pathlib import Path
from datetime import datetime, timezone
from threading import Thread
from urllib.request import Request, urlopen
import json,hashlib,re,time,os,sys,traceback
from glyphs_mcp_bridge.lifecycle import bridge_lifecycle as life
from glyphs_mcp_bridge.main_thread import CocoaMainThread
S=Path('/Users/thierryc/Dev/github/thierryc/Glyphs-mcp-worktrees/v2/build/milestone7/desktop')
OUT=S/'reports/beta1-m7-master-properties-20260914';T=Path('/private/tmp/glyphs-m7-20260914/live');T.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(OUT));import m7_oracle as oracle
import importlib;importlib.reload(oracle)  # Test helper revision only; no runtime reload.
fixtures=json.loads((OUT/'fixtures.json').read_text())['fixtures'];sources={r['label']:r for r in fixtures}
manifest=json.loads((OUT/'candidate-manifest.json').read_text());prior=json.loads((OUT/'documents-before.json').read_text())['data']
main=CocoaMainThread(timeout=60);fonts={};facts=dict(startedAt=datetime.now(timezone.utc).isoformat(),loadBefore=os.getloadavg(),checks=[],calls=[],callbacks=[],trials=[],fixtureSetup=[])
original_call=life.server.main_thread.call;original_read=life.adapter.read_entities;tags=[]
def measured_read(document,entities,fields):
    tags.append({'entities':entities,'fields':fields});return original_read(document,entities,fields)
def measured_call(callback):
    queued=time.perf_counter()
    def invoke():
        tags.clear();start=time.perf_counter()
        try:return callback()
        finally:facts['callbacks'].append(dict(queueMs=(start-queued)*1000,nativeMs=(time.perf_counter()-start)*1000,reads=list(tags)))
    return original_call(invoke)
life.adapter.read_entities=measured_read;life.server.main_thread.call=measured_call
def save(): (OUT/'native-facts.json').write_text(json.dumps(facts,indent=2))
def check(name,wanted,got):
    ok=wanted==got;facts['checks'].append(dict(name=name,expected=wanted,observed=got,passed=ok));save();assert ok,name
def rpc(method,params):
    req=Request('http://127.0.0.1:9680/mcp/',data=json.dumps(dict(jsonrpc='2.0',id=len(facts['calls'])+1,method=method,params=params)).encode(),headers={'Content-Type':'application/json','Accept':'application/json, text/event-stream','MCP-Protocol-Version':'2025-03-26'})
    with urlopen(req,timeout=40) as response:raw=response.read().decode()
    result=json.loads(next((line[6:] for line in raw.splitlines() if line.startswith('data: ')),raw))
    if 'error' in result:raise RuntimeError(result['error'])
    return result['result']
def call(tool,args=None,phase='control'):
    args={} if args is None else args;at=datetime.now(timezone.utc).isoformat();cb=len(facts['callbacks']);start=time.perf_counter()
    raw=rpc('tools/call',dict(name=tool,arguments=args));elapsed=(time.perf_counter()-start)*1000
    body=raw.get('structuredContent') or json.loads(next(x['text'] for x in raw['content'] if x['type']=='text'))
    facts['calls'].append(dict(at=at,tool=tool,arguments=args,phase=phase,httpMs=elapsed,result=body,callbacks=facts['callbacks'][cb:]));save();return body,elapsed
def discover(path):
    r,elapsed=call('list_documents');assert r['ok'];rows=[x for x in r['data'] if x['path']==path];assert len(rows)==1
    return rows[0]['id'],elapsed,len(r['data'])
def read(doc,entities,fields=oracle.FIELDS,phase='control'):
    return call('read_entities',dict(document_id=doc,entities=entities,fields=list(fields)),phase)
def proof(f):
    doc=f.parent;undo=doc.undoManager()
    return dict(data=oracle.digest(oracle.snapshot(f)),dirty=bool(doc.isDocumentEdited()),
        selectedMaster=f.selectedFontMaster.id if f.selectedFontMaster else None,
        selection=[g.name for g in f.selection],tabs=len(f.tabs),
        undo=[bool(undo.canUndo()),bool(undo.canRedo()),str(undo.undoActionName()),str(undo.redoActionName()),undo.groupingLevel()])
def open_copy(label,name):
    source=Path(sources[label]['path']);assert hashlib.sha256(source.read_bytes()).hexdigest()==sources[label]['sourceSHA256']
    p=T/(name+'.glyphs');p.write_text(re.sub(r'(?m)^\.appVersion = .*?;','.appVersion = "4107";',source.read_text(),count=1))
    fonts[name]=Glyphs.open(str(p),True)
    facts['fixtureSetup'].append(dict(name=name,dirtyImmediately=bool(fonts[name].parent.isDocumentEdited())))
    return str(p)
def close_copy(name):fonts.pop(name).close(ignoreChanges=True)
def restore_originals():
    for row in prior:
        assert row['dirty'] is False
        if not any(str(f.filepath)==row['path'] for f in Glyphs.fonts):Glyphs.open(row['path'],True)
    next(f for f in Glyphs.fonts if str(f.filepath)==next(r['path'] for r in prior if r['isCurrent'])).show()
def inventory(name,doc,limit,phase):
    before,expected=main.call(lambda:(proof(fonts[name]),oracle.rows(fonts[name])))
    cursor=None;items=[];indices=[];elapsed=0
    while True:
        selector=dict(kind='masters',limit=limit)
        if cursor:selector['cursor']=cursor
        body,ms=read(doc,[selector],phase=phase);indices.append(len(facts['calls'])-1);elapsed+=ms
        check(name+' page successful',True,body.get('ok'));v=body['data'][0]['values'];items+=v['items']
        check(name+' page count',len(expected),v['total']);check(name+' page bound',True,len(v['items'])<=limit)
        check(name+' exact fields',True,all(set(row)==set(oracle.FIELDS) for row in v['items']))
        for row in v['items']:check(name+' axes completeness '+row['id'],dict(items=row['axes']['items'],total=len(row['axes']['items']),returned=len(row['axes']['items']),complete=True),row['axes'])
        if v['complete']:check(name+' terminal cursor',None,v['nextCursor']);break
        cursor=v['nextCursor'];check(name+' incomplete cursor',True,cursor is not None)
    check(name+' exact native values',expected,items)
    check(name+' object/data/history/dirty preservation',before,main.call(lambda:proof(fonts[name])))
    return dict(readMs=elapsed,callIndices=indices,requests=len(indices),masters=len(items),axisItems=sum(r['axes']['total'] for r in items))
def run():
    try:
        facts['initialize']=rpc('initialize',dict(protocolVersion='2025-03-26',capabilities={},clientInfo=dict(name='M7 native qualification',version='1')))
        facts['catalog']=rpc('tools/list',{});r,_=call('get_status');facts['runtime']=r['data']
        check('seven tools',sorted(manifest['tools']),sorted(t['name'] for t in facts['catalog']['tools']))
        check('five jobs',5,len(r['data']['jobKinds']))
        for part in ('sidecar','bridge'):
            actual=r['data'] if part=='sidecar' else r['data']['bridge'];check(part+' loaded fingerprint',manifest[part]['codeHash'],actual['codeHash'])
        check('negotiated new capability',True,'master.properties.v1' in r['data']['readCapabilities'])
        main.call(restore_originals);original=main.call(lambda:{str(f.filepath):proof(f) for f in Glyphs.fonts});facts['originalSnapshots']=original;save()
        main.call(lambda:open_copy('MasterPropertiesTest','unrelated'));unrelated_before=main.call(lambda:proof(fonts['unrelated']))
        for label,source,limit in [('small','MasterPropertiesTest',100),('bound','MasterPropertiesBound',8),('RobotoSlab','RobotoSlab',100)]:
            for phase in ('first','warmup','rep1','rep2','rep3','rep4','rep5'):
                name=label+'-'+phase;path=main.call(lambda:open_copy(source,name))
                # Host-only controls show delayed dirty marking on opening the 32-axis fixture.
                # Keep this setup time separate; do not clear its flag or filter read latency.
                settle=time.perf_counter();time.sleep(2)
                facts['fixtureSetup'][-1].update(settleMs=(time.perf_counter()-settle)*1000,
                    dirtyBeforeReads=main.call(lambda:bool(fonts[name].parent.isDocumentEdited())))
                doc,discovery,docs=discover(path)
                result=inventory(name,doc,limit,phase);facts['trials'].append(dict(label=label,phase=phase,discoveryMs=discovery,initialTotalMs=discovery+result['readMs'],openDocuments=docs,load=os.getloadavg(),**result));save()
                # Exact IDs come from the public result, not the native oracle.
                values=facts['calls'][result['callIndices'][0]]['result']['data'][0]['values']['items'];target=values[0]['id']
                before=main.call(lambda:proof(fonts[name]));body,_=read(doc,[dict(kind='master',id=target)],['id','italicAngle'],'compact')
                check(name+' compact exact read',{'id':target,'italicAngle':values[0]['italicAngle']},body['data'][0]['values']);check(name+' compact preserved',before,main.call(lambda:proof(fonts[name])))
                main.call(lambda:close_copy(name))
        path=main.call(lambda:open_copy('MasterPropertiesTest','controls'));doc,_,_=discover(path)
        body,_=read(doc,[dict(kind='masters')],['id','name']);mids=[r['id'] for r in body['data'][0]['values']['items']]
        main.call(lambda:fonts['unrelated'].show());inventory('controls',doc,100,'background-target')
        expected=main.call(lambda:{k:oracle.rows(fonts['controls'])[0][k] for k in oracle.METRICS})
        body,_=read(doc,[dict(kind='master',id=mids[0])]*100,oracle.METRICS,'scalar-budget')
        check('100 scalar target slots', [expected]*100, [r['values'] for r in body['data']])
        before=main.call(lambda:proof(fonts['controls']))
        for entities,fields,code in [([dict(kind='master',id='Regular')],['ascender'],'target_not_found'),
            ([dict(kind='master',id=mids[0]),dict(kind='master',id='missing')],['ascender'],'target_not_found'),
            ([dict(kind='master',id=mids[0])],['unsupportedMetric'],'unsupported_read'),
            ([dict(kind='masters',limit=101)],['axes'],'invalid_request'),
            ([dict(kind='masters')]*2,['axes'],'invalid_request')]:
            body,_=read(doc,entities,fields);check('input rejection '+str(entities),code,body['error']['code'])
        check('invalid input preserved',before,main.call(lambda:proof(fonts['controls'])))
        def dirty_change():
            f=fonts['controls'];f.masters[0].ascender=823.875;f.masters[0].italicAngle=-13.125
            f.masters[0].internalAxesValues[f.axes[0].axisId]=-7.125
            f.axes=list(reversed(list(f.axes)));f.parent.updateChangeCount_(0)
        main.call(dirty_change);check('dirty precondition',True,main.call(lambda:bool(fonts['controls'].parent.isDocumentEdited())))
        inventory('controls',doc,100,'dirty-reordered')
        probe=time.perf_counter()
        while time.perf_counter()-probe<2:
            body,_=read(doc,[dict(kind='master',id=mids[0])],['ascender','italicAngle'],'two-second-probe');check('fresh changed metric',823.875,body['data'][0]['values']['ascender']);time.sleep(.05)
        def zero_axes():fonts['controls'].axes=[]
        main.call(zero_axes);body,_=read(doc,[dict(kind='master',id=mids[0])],['axes']);check('native empty axes',dict(items=[],total=0,returned=0,complete=True),body['data'][0]['values']['axes'])
        def many_axes():
            for i in range(33):
                a=GSAxis();a.axisId='M7_LIMIT_'+str(i);a.name='Limit '+str(i);a.axisTag='L%03d'%i;fonts['controls'].axes.append(a)
        main.call(many_axes);body,_=read(doc,[dict(kind='master',id=mids[0])],['axes']);check('33 native axes rejected','invalid_request',body['error']['code'])
        body,_=read(doc,[dict(kind='master',id=mids[0])],['ascender']);check('scalar with many axes',823.875,body['data'][0]['values']['ascender'])
        main.call(lambda:close_copy('controls'));body,_=read(doc,[dict(kind='master',id=mids[0])],['ascender']);check('closed document stale ID','document_not_found',body['error']['code'])
        main.call(lambda:open_copy('MasterPropertiesTest','controls'));newdoc,_,_=discover(path);check('reopened document new ID',True,doc!=newdoc);inventory('controls',newdoc,100,'reopened');main.call(lambda:close_copy('controls'))
        path=main.call(lambda:open_copy('MasterPropertiesBound','limits'));doc,_,_=discover(path)
        body,_=read(doc,[dict(kind='masters')],['axes']);check('native aggregate limit','invalid_request',body['error']['code'])
        listed,_=read(doc,[dict(kind='masters')],['id']);ids=[r['id'] for r in listed['data'][0]['values']['items']]
        body,_=read(doc,[dict(kind='master',id=i) for i in ids]+[dict(kind='glyph',id='unused')],['axes'])
        check('mixed invalid selectors respect axis budget','invalid_request',body['error']['code'])
        first,_=read(doc,[dict(kind='masters',limit=8)],['id','axes']);cursor=first['data'][0]['values']['nextCursor']
        before=main.call(lambda:proof(fonts['limits']));main.call(lambda:fonts['limits'].masters.remove(fonts['limits'].masters[-1]))
        body,_=read(doc,[dict(kind='masters',cursor=cursor)],['axes']);check('native stale page','stale_master_cursor',body['error']['code']);inventory('limits',doc,8,'page-recovery');main.call(lambda:close_copy('limits'))
        # Unsaved native copy: source setup stays separate from public target discovery.
        def unsaved():
            from GlyphsApp import GSFont
            f=GSFont(sources['MasterPropertiesTest']['path']).copy()
            f.show();fonts['unsaved']=f
        main.call(unsaved);doc,_,_=discover(None);inventory('unsaved',doc,100,'unsaved');main.call(lambda:close_copy('unsaved'))
        for old in prior:
            body,_=read(old['id'],[dict(kind='masters')],['id']);check('pre-restart ID rejected','document_not_found',body['error']['code'])
        check('unrelated native preservation',unrelated_before,main.call(lambda:proof(fonts['unrelated'])))
        for path,before in original.items():check('original native preservation '+path,before,main.call(lambda:proof(next(f for f in Glyphs.fonts if str(f.filepath)==path))))
        for path,sha in json.loads((OUT/'original-file-hashes.json').read_text()).items():check('original file preserved '+path,sha,hashlib.sha256(Path(path).read_bytes()).hexdigest())
        for row in fixtures:check('baseline preserved '+row['label'],row['sourceSHA256'],hashlib.sha256(Path(row['path']).read_bytes()).hexdigest())
        facts['passed']=True
    except Exception:facts['passed']=False;facts['error']=traceback.format_exc()
    finally:
        def cleanup():
            life.server.main_thread.call=original_call;life.adapter.read_entities=original_read
            for name in list(fonts):close_copy(name)
            restore_originals()
        try:main.call(cleanup)
        except Exception:facts['cleanupError']=traceback.format_exc()
        facts['finishedAt']=datetime.now(timezone.utc).isoformat();facts['loadAfter']=os.getloadavg();save();print('M7 NATIVE FINISHED',facts.get('passed'),facts.get('error',''))
Thread(target=run,name='M7 native qualification',daemon=True).start();print('M7 qualification started')
