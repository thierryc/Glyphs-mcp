"""Run via a dedicated Glyphs scripting macro. Test-only native setup/oracle;
public reads use HTTP MCP. No native helper supplies a document ID or read result.
Temporary timing instrumentation is restored in finally. No font is saved.
"""
from GlyphsApp import Glyphs, GSNode, GSAnchor, GSComponent, GSGuide
from Foundation import NSMakeRange
from pathlib import Path
from threading import Thread
from datetime import datetime, timezone
from urllib.request import Request, urlopen
import json, hashlib, shutil, time, os, traceback, objc
from glyphs_mcp_bridge.lifecycle import bridge_lifecycle as life
from glyphs_mcp_bridge.main_thread import CocoaMainThread

S=Path('/Users/thierryc/Dev/github/thierryc/Glyphs-mcp-worktrees/v2/build/milestone7/desktop')
OUT=S/'reports/beta1-h3-context-20260914'
TEMP=Path('/private/tmp/glyphs-h3-20260914/live');TEMP.mkdir(exist_ok=True)
BASE=OUT/'ContextTest.glyphs'
ns={'__file__':str(S.parents[2]/'scripts/selection_fixture.py'),'__name__':'h3_oracle'}
exec(compile(Path(ns['__file__']).read_text(),ns['__file__'],'exec'),ns)
main=CocoaMainThread(timeout=30)
facts=dict(startedAt=datetime.now(timezone.utc).isoformat(),loadBefore=os.getloadavg(),checks=[],calls=[],timings=[],nativeCallbacks=[])
fonts={}
original_call=life.server.main_thread.call

def measured_call(callback):
    queued=time.perf_counter()
    def measured():
        started=time.perf_counter()
        try:return callback()
        finally:
            if len(facts['nativeCallbacks'])<300:
                facts['nativeCallbacks'].append(dict(queueMs=(started-queued)*1000,callbackMs=(time.perf_counter()-started)*1000))
    return original_call(measured)
life.server.main_thread.call=measured_call

def save():
    (OUT/'native-facts.json').write_text(json.dumps(facts,indent=2,default=str))

def check(name,expected,observed):
    facts['checks'].append(dict(name=name,expected=expected,observed=observed,passed=expected==observed))
    save()
    assert expected==observed, name

def rpc(method,params):
    payload=dict(jsonrpc='2.0',id=len(facts['calls'])+1,method=method,params=params)
    req=Request('http://127.0.0.1:9680/mcp/',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Accept':'application/json, text/event-stream','MCP-Protocol-Version':'2025-03-26'})
    with urlopen(req,timeout=40) as response:
        text=response.read().decode()
        if text.startswith('event:') or text.startswith('data:'):
            result=json.loads(next(line[5:].strip() for line in text.splitlines() if line.startswith('data:')))
        else:result=json.loads(text)
    if 'error' in result:raise RuntimeError(result['error'])
    return result['result']

def call(name,args={},phase='control'):
    at=datetime.now(timezone.utc).isoformat(); start=time.perf_counter(); index=len(facts['nativeCallbacks'])
    raw=rpc('tools/call',dict(name=name,arguments=args));ms=(time.perf_counter()-start)*1000
    body=raw.get('structuredContent') or json.loads(next(x['text'] for x in raw['content'] if x['type']=='text'))
    facts['calls'].append(dict(at=at,tool=name,arguments=args,phase=phase,httpMs=ms,result=body,nativeCallbacks=facts['nativeCallbacks'][index:]))
    save();return body,ms

def discover(path):
    body,ms=call('list_documents');assert body['ok'],body
    matching=[x for x in body['data'] if x['path']==str(path)]
    assert len(matching)==1
    return matching[0]['id'],body['data'],ms

def read(doc,fields=('view','master','selectedGlyphs'),selector=None,phase='control'):
    return call('read_entities',dict(document_id=doc,entities=[selector or {'kind':'context'}],fields=list(fields)),phase)

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()

def proof(font):
    identities=[]
    for glyph in font.glyphs:
        identities.append(int(objc.pyobjc_id(glyph)))
        for layer in glyph.layers:
            identities.extend([int(objc.pyobjc_id(layer)),*[int(objc.pyobjc_id(x)) for x in layer.shapes],
                               *[int(objc.pyobjc_id(n)) for p in layer.paths for n in p.nodes],
                               *[int(objc.pyobjc_id(x)) for x in layer.anchors],*[int(objc.pyobjc_id(x)) for x in layer.guides]])
    return dict(data=digest(ns['snapshot'](font)),objects=digest(identities),selection=ns['selection_state'](font),fontSelection=[g.name for g in font.selection],dirty=bool(font.parent.isDocumentEdited()))

def oracle(font,limit=100):
    # Separate native enumeration, deliberately exhaustive within the fixture.
    edit=font.currentTab is not None
    native=font.selectedLayers if edit else font.selection
    names=[item.parent.name if edit else item.name for item in native]
    m=font.selectedFontMaster
    return dict(view='edit' if edit else 'font',master=dict(id=m.id,name=m.name),
                selectedGlyphs=dict(source='font.selectedLayers' if edit else 'font.selection',total=len(names),returned=min(len(names),limit),limit=limit,complete=len(names)<=limit,items=names[:limit]))

def open_copy(name):
    path=TEMP/(name+'.glyphs');shutil.copyfile(BASE,path)
    font=Glyphs.open(str(path),True);fonts[name]=font
    return str(path)

def close_copy(name):
    fonts.pop(name).close(ignoreChanges=True)

def font_selection(name,count=2,master=1):
    f=fonts[name];f.show();f.currentTab=f.fontView;f.masterIndex=master
    f.selection=[f.glyphs[i] for i in range(count)]

def edit_selection(name,mode='mixed',master=1):
    f=fonts[name];f.show();f.masterIndex=master
    layer=f.glyphs['many' if mode=='256' else 'mixed'].layers[f.masters[master].id]
    tab=f.currentTab or f.newTab([layer]);f.currentTab=tab;tab.layers=[layer];tab.masterIndex=master;tab.textCursor=0
    layer.clearSelection()
    nodes=[n for p in layer.paths for n in p.nodes]
    chosen=nodes if mode=='256' else nodes[:3] if mode=='nodes' else []
    if mode=='mixed':chosen=nodes[:3]+[layer.anchors['top'],layer.components[0],layer.guides[0]]
    for obj in chosen: layer.addSelection_(obj)

def inspect(name,doc,label,limit=100,phase='control'):
    before,expected=main.call(lambda:(proof(fonts[name]),oracle(fonts[name],limit)))
    selector={'kind':'context'} if limit==100 else {'kind':'context','glyphLimit':limit}
    body,ms=read(doc,selector=selector,phase=phase)
    check(label+' context',{'ok':True,'data':[dict(entity=selector,values=expected)]},body)
    after=main.call(lambda:proof(fonts[name]));check(label+' exact preservation',before,after)
    return ms

def run():
    try:
        facts['initialize']=rpc('initialize',dict(protocolVersion='2025-03-26',capabilities={},clientInfo={'name':'H3 qualification','version':'1'}))
        facts['catalog']=rpc('tools/list',{})
        status,_=call('get_status');facts['runtime']=status['data']
        manifest=json.loads((S/'build/h3-context-candidate-20260914/Lean/manifest.json').read_text())
        for part in ('sidecar','bridge'):
            runtime=status['data'] if part=='sidecar' else status['data']['bridge']
            check(part+' installed code hash',manifest[part]['codeHash'],runtime['codeHash'])
        check('seven tools',sorted(manifest['tools']),sorted(x['name'] for x in facts['catalog']['tools']))
        check('negotiated capability',True,'document.context.v1' in status['data']['readCapabilities'])
        check('Glyphs host',dict(identifier='com.GeorgSeifert.Glyphs4',version='4.1',build='4107'),status['data']['bridge']['host'])
        protected=main.call(lambda:{str(f.filepath):proof(f) for f in Glyphs.fonts})
        baseline_hash=hashlib.sha256(BASE.read_bytes()).hexdigest()
        path_b=main.call(lambda:open_copy('B'))
        for size,count in (('small',2),('bounded',109)):
            for phase in ('first','warmup','rep1','rep2','rep3','rep4','rep5'):
                name=size+'-'+phase;path=main.call(lambda:open_copy(name))
                main.call(lambda:font_selection(name,count))
                doc,documents,discovery_ms=discover(path)
                check(name+' current marker',[path],[d['path'] for d in documents if d.get('isCurrent')])
                read_ms=inspect(name,doc,name,phase=phase)
                facts['timings'].append(dict(size=size,phase=phase,httpReadMs=read_ms,discoveryMs=discovery_ms,initialTotalMs=discovery_ms+read_ms,openDocuments=len(documents)))
                main.call(lambda:close_copy(name))
        path_a=main.call(lambda:open_copy('A'));doc,_,_=discover(path_a)
        for mi in range(3):
            main.call(lambda:font_selection('A',2,mi));inspect('A',doc,'font master '+str(mi))
        main.call(lambda:font_selection('A',0));inspect('A',doc,'font empty')
        main.call(lambda:font_selection('A',109));inspect('A',doc,'explicit limit',limit=3)
        for mi in range(3):
            main.call(lambda:edit_selection('A','mixed',mi));inspect('A',doc,'mixed master '+str(mi))
            master_id=main.call(lambda:fonts['A'].masters[mi].id)
            summary,_=read(doc,fields=('glyph','layer','selectedNodeCount','selectedAnchorCount','selectedComponentCount','selectedGuideCount','selectedOtherCount'),selector={'kind':'selection'})
            check('mixed native counts '+str(mi),dict(glyph='mixed',layer=master_id,selectedNodeCount=3,selectedAnchorCount=1,selectedComponentCount=1,selectedGuideCount=1,selectedOtherCount=0),summary['data'][0]['values'])
        for mode in ('nodes','256','empty'):
            main.call(lambda:edit_selection('A',mode));inspect('A',doc,'edit '+mode)
            before=main.call(lambda:proof(fonts['A']))
            body,_=read(doc,('glyph','layer','nodes'),{'kind':'selection','nodeLimit':256})
            nodes=body['data'][0]['values']['nodes'];expected_count={'nodes':3,'256':256,'empty':0}[mode]
            check(mode+' node count',(expected_count,expected_count,True),(nodes['total'],nodes['returned'],nodes['complete']))
            check(mode+' node read preservation',before,main.call(lambda:proof(fonts['A'])))
        def repeated():
            master_id=main.call(lambda:fonts['A'].masters[mi].id);t=f.currentTab;t.layers=[f.glyphs[n].layers[f.masters[1].id] for n in ('control','mixed','control')];t.selectedTextRange=NSMakeRange(0,3)
        main.call(repeated);inspect('A',doc,'repeated occurrences')
        def empty_tab():
            master_id=main.call(lambda:fonts['A'].masters[mi].id);f.currentTab.layers=[]
        main.call(empty_tab);inspect('A',doc,'empty Edit View')
        main.call(lambda:font_selection('A',2));main.call(lambda:font_selection('B',1,2))
        _,documents,_=discover(path_b)
        check('B becomes current',[path_b],[d['path'] for d in documents if d.get('isCurrent')])
        inspect('A',doc,'retained A while B current')
        def dirty():
            master_id=main.call(lambda:fonts['A'].masters[mi].id);f.glyphs['control'].layers[f.masters[0].id].width+=.25
        main.call(dirty);inspect('A',doc,'dirty context')
        check('dirty native flag',True,main.call(lambda:bool(fonts['A'].parent.isDocumentEdited())))
        for selector,fields,code in (({'kind':'context','glyphLimit':101},['selectedGlyphs'],'invalid_request'),
                ({'kind':'context','glyphLimit':True},['selectedGlyphs'],'invalid_request'),
                ({'kind':'context','glyphLimit':1},['view'],'invalid_request'),
                ({'kind':'context'},['nodes'],'unsupported_read')):
            body,_=read(doc,fields,selector);check('invalid bounded input '+str(selector)+str(fields),code,body['error']['code'])
        main.call(lambda:close_copy('A'))
        body,_=read(doc);check('closed document rejected','document_not_found',body['error']['code'])
        path_c=main.call(lambda:open_copy('C'));body,_=read(doc);check('different font never substituted','document_not_found',body['error']['code'])
        main.call(lambda:close_copy('C'));main.call(lambda:open_copy('A'))
        new_doc,_,_=discover(path_a);check('same-path reopen new ID',True,doc!=new_doc)
        body,_=read(doc);check('old ID still rejected after reopen','document_not_found',body['error']['code'])
        inspect('A',new_doc,'explicit recovered new ID')
        check('baseline immutable',baseline_hash,hashlib.sha256(BASE.read_bytes()).hexdigest())
        main.call(lambda:close_copy('A'));main.call(lambda:close_copy('B'))
        for path,expected in protected.items():
            actual=main.call(lambda:proof(next(f for f in Glyphs.fonts if str(f.filepath)==path)))
            check('protected document exact preservation '+path,expected,actual)
        preinstall=json.loads(Path('/private/tmp/glyphs-h3-20260914/protected-before-install.json').read_text())
        for row in preinstall:
            check('protected disk hash across install',row['sha256'],hashlib.sha256(Path(row['path']).read_bytes()).hexdigest())
            check('protected native contents across install',digest(row['data']),main.call(lambda:digest(ns['snapshot'](next(f for f in Glyphs.fonts if str(f.filepath)==row['path'])))))
        facts['passed']=True
    except Exception:
        facts['passed']=False;facts['error']=traceback.format_exc()
    finally:
        def cleanup():
            life.server.main_thread.call=original_call
            for name in list(fonts):close_copy(name)
            if Glyphs.fonts:Glyphs.fonts[0].show()
        try:main.call(cleanup)
        except Exception:facts['cleanupError']=traceback.format_exc()
        facts['loadAfter']=os.getloadavg();facts['finishedAt']=datetime.now(timezone.utc).isoformat();save()
        print('H3 NATIVE FINISHED',facts.get('passed'),facts.get('error',''))

Thread(target=run,name='H3 bounded qualification',daemon=True).start()
print('H3 qualification started; native setup and public HTTP reads run separately')
