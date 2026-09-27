"""Real-font tasks against the built native candidate; no installed-runtime writes."""
import importlib
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import time
import resource

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build/simple-native-scripting'
sys.path[:0] = [str(BUILD/'sidecar'), str(BUILD/'Glyphs MCP Bridge.glyphsPlugin/Contents/Resources'), str(ROOT/'scripts')]
loaded = {}
for name in ('glyphs_mcp_protocol.script_targets', 'glyphs_mcp_bridge.core', 'glyphs_mcp_sidecar.service', 'glyphs_mcp_sidecar.native_worker'):
    module = importlib.import_module(name)
    path = Path(module.__file__).resolve()
    assert path.is_relative_to(BUILD), (name, path)
    loaded[name] = str(path)
from native_script_harness import Harness
from GlyphsApp import GSFont
from Foundation import NSURL
from glyphs_mcp_protocol.source_identity import source_hash

fixture = ROOT/'build/real-task-qualification-20260926/Dactylotype Task Test.glyphspackage'
report_root = Path(sys.argv[-2]).resolve()
report_root.mkdir(parents=True, exist_ok=True)
suffix = sys.argv[-1] if sys.argv[-1] in ('glyphs', 'glyphspackage') else 'glyphspackage'
h = Harness(suffix=suffix)
value = GSFont.alloc().initWithURL_error_(NSURL.fileURLWithPath_(str(fixture)), None)
font = value[0] if isinstance(value, tuple) else value
assert font is not None
h.doc.setFont_(font)
h.mid = str(next(m for m in font.masters if str(m.name) == 'Regular').id)
font.save(str(h.source), makeCopy=True)
h.clean()

def plain(value):
    if hasattr(value, 'items'):
        return {str(k): plain(v) for k,v in value.items()}
    if isinstance(value, (str, bool, int, float)) or value is None:
        return value
    return str(value)

def kerning(font):
    # Glyphs 4 uses runtime glyph IDs; reloading necessarily changes those IDs.
    # Compare resolved glyph identities and group keys, not object identities.
    def key(value):
        if str(value).startswith('@'):return str(value)
        glyph=font.glyphForId_(value)
        assert glyph is not None, value
        return 'glyph:'+str(glyph.name)
    return {str(mid):{key(left):{key(right):float(value) for right,value in rights.items()}
                     for left,rights in pairs.items()} for mid,pairs in font.kerning.items()}

def exercise(h):
    checks = []
    tasks = []
    def check(name, condition):
        assert condition, name
        checks.append(name)
        print(name, flush=True)
    def scene():
        font = h.doc.font
        layers = {}
        for name in ('H','n','o','A','V','T'):
            for m in font.masters:
                layer = font.glyphs[name].layers[m.id]
                layers[name+'/'+str(m.id)] = dict(width=float(layer.width), outline=h.adapter._outline_hash(layer),
                    background=h.adapter._outline_hash(layer.background) if layer.hasBackground else None,
                    keys=[getattr(layer,k) for k in ('leftMetricsKey','rightMetricsKey','widthMetricsKey')])
        return dict(layers=layers, kerning=kerning(font), family=str(font.familyName),
                    features=[(str(f.name),str(f.code)) for f in font.features],
                    groups={str(g.name):[g.leftKerningGroup,g.rightKerningGroup] for g in font.glyphs})
    def geometry(names):
        out={}
        for name in names:
            layer=h.doc.font.glyphs[name].layers[h.mid]
            out[name]=dict(width=float(layer.width),
                paths=[[(float(n.position.x),float(n.position.y),str(n.type),bool(n.smooth)) for n in p.nodes] for p in layer.paths],
                components=[(str(c.componentName),tuple(float(x) for x in c.transform)) for c in layer.components],
                anchors=[(str(a.name),float(a.position.x),float(a.position.y)) for a in layer.anchors])
        return out
    saves=[];save_seconds=[]
    writer=h.adapter.save_document
    def counted(*args):
        saves.append(args[2]);started=time.perf_counter()
        try:return writer(*args)
        finally:save_seconds.append(time.perf_counter()-started)
    h.adapter.save_document=counted
    def run(name, options, verify, affected=(), dirty=False, later_edit=False):
        before=h.main(scene); geo=h.main(lambda:geometry(('H','n','o')))
        baseline=source_hash(h.source); saved_before=len(saves)
        h.max_chunk=0;h.native_seconds=0;h.chunks=0
        start=time.perf_counter()
        review=h.wait(h.start(options,name),'waiting_run')
        prepared=time.perf_counter()
        check(name+': preparation does not execute',h.main(scene)==before)
        dispatch=time.perf_counter()
        result=h.wait(h.choose(review,'save_run_script' if dirty else 'run_script'),'applied')
        completed=time.perf_counter()
        check(name+': save count',len(saves)-saved_before==(1 if dirty else 0))
        verify(geo)
        after=h.main(scene)
        for key, old in before['layers'].items():
            if key not in affected:check(name+': untouched '+key,after['layers'][key]==old)
            else:check(name+': background and metrics keys preserved '+key,
                       after['layers'][key]['background']==old['background'] and after['layers'][key]['keys']==old['keys'])
        if name!='kerning':check(name+': kerning untouched',before['kerning']==after['kerning'])
        check(name+': groups and features untouched',before['groups']==after['groups'] and before['features']==after['features'])
        metrics=dict(preparation=prepared-start,executionAndPolling=completed-dispatch,
                     save=sum(save_seconds[saved_before:]),verification=time.perf_counter()-completed,
                     longestScheduledChunk=h.max_chunk,scheduledNative=h.native_seconds,chunks=h.chunks)
        # Result reads and verification above are intentionally outside execution timing.
        if later_edit:
            def manual():
                manager=h.doc.undoManager();manager.beginUndoGrouping()
                try:h.doc.font.familyName='Later disposable edit'
                finally:manager.endUndoGrouping()
                h.doc.updateChangeCount_(0)
            h.main(manual)
        result=h.service.edit_workflows.get(result['id'])
        old_id=result['document']['id']
        restore_start=time.perf_counter();restored=h.choose(result,'restore_saved_script')
        metrics['restoration']=time.perf_counter()-restore_start
        restored_scene=h.main(scene)
        if restored['state']!='discarded' or restored_scene!=before:
            (ROOT/f'build/real-task-qualification-20260926/restore-diagnostic-{suffix}.json').write_text(json.dumps(dict(before=before,after=restored_scene,workflow=restored),indent=2)+'\n')
        check(name+': saved version restored',restored['state']=='discarded' and restored_scene==before)
        check(name+': restoration clean and fresh binding',not restored['document']['dirty'] and restored['document']['id']!=old_id)
        check(name+': restoration clears Undo',h.main(lambda:not h.doc.undoManager().canUndo() and all(not g.undoManager().canUndo() for g in h.doc.font.glyphs)))
        check(name+': restoration does not save',len(saves)-saved_before==(1 if dirty else 0))
        if not dirty:check(name+': baseline unchanged',source_hash(h.source)==baseline)
        tasks.append(dict(name=name,options=options,reviewState=review['state'],result=result,restored=restored,
                          timingsSeconds=metrics,processPeakRSSBytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,saveCalls=len(saves)-saved_before,laterEditReplaced=later_edit))
    def path_check(geo):
        expected=json.loads(json.dumps(geo)); expected['o']['paths'][0][0][0]+=7.25;expected['o']['paths'][0][0][1]-=3.5
        actual=json.loads(json.dumps(h.main(lambda:geometry(('H','n','o')))))
        check('path: exact fractional node, all other selected geometry unchanged',actual==expected)
    run('path',dict(summary='Move one Regular o node by +7.25, -3.5',
        source='def run(layer, params, context):\n    n=layer.paths[0].nodes[0]\n    n.position=(n.position.x+params["dx"],n.position.y+params["dy"])',
        params=dict(dx=7.25,dy=-3.5),targets=[dict(glyph='o',layer=h.mid)]),path_check,('o/'+h.mid,),later_edit=True)
    spacing='''def run(layer, params, context):
    dx=params['dx']
    for path in layer.paths:
        for node in path.nodes:
            node.position=(node.position.x+dx,node.position.y)
    for component in layer.components:
        t=list(component.transform)
        t[4]+=dx
        component.transform=tuple(t)
    for anchor in layer.anchors:
        anchor.position=(anchor.position.x+dx,anchor.position.y)
    layer.width+=params['advance']
'''
    def spacing_check(geo):
        expected=json.loads(json.dumps(geo))
        for item in expected.values():
            item['width']+=20.75
            for path in item['paths']:
                for node in path:node[0]+=12.5
            for component in item['components']:component[1][4]+=12.5
            for anchor in item['anchors']:anchor[1]+=12.5
        check('spacing: exact paths components anchors advances',json.loads(json.dumps(h.main(lambda:geometry(('H','n','o')))))==expected)
    # Deliberate unsaved metadata edit exercises the one-save prerequisite.
    def dirty_baseline():
        manager=h.doc.undoManager();manager.beginUndoGrouping()
        try:h.doc.font.userData['ownedQualification']='dirty baseline'
        finally:manager.endUndoGrouping()
        h.doc.updateChangeCount_(0)
    h.main(dirty_baseline)
    run('spacing',dict(summary='Add 12.5 left and 8.25 right spacing to H n o',source=spacing,
        params=dict(dx=12.5,advance=20.75),targets=[dict(glyph=n,layer=h.mid) for n in ('H','n','o')]),
        spacing_check,tuple(n+'/'+h.mid for n in ('H','n','o')),dirty=True)
    before_kerning=h.main(lambda:kerning(h.doc.font))
    def kern_check(geo):
        def inspect():
            font=h.doc.font
            assert font.kerningForPair(h.mid,'A','V')==-60.25
            assert font.kerningForPair(h.mid,'T','o')==-45.5
            expected=json.loads(json.dumps(before_kerning))
            for a,b,value in [('A','V',-60.25),('T','o',-45.5)]:
                expected.setdefault(h.mid,{}).setdefault('glyph:'+a,{})['glyph:'+b]=value
            return kerning(font)==expected
        check('kerning: two exact pairs and all other stored values unchanged',h.main(inspect))
    run('kerning',dict(summary='Set exact Regular A/V and T/o kerning',entrypoint='script',targets=[],
        source='for left,right,value in params["pairs"]:\n    font.setKerningForPair(params["master"],left,right,value)',
        params=dict(master=h.mid,pairs=[['A','V',-60.25],['T','o',-45.5]])),kern_check)
    return dict(checks=checks,tasks=tasks,glyphCount=h.main(lambda:len(h.doc.font.glyphs)),masterCount=9)

out=h.run(exercise)
out.update(loadedModules=loaded,fixture=str(fixture),suffix=suffix,
           limitation='Isolated native CLI with real candidate bridge/sidecar; fixture save adapter uses GSFont. Not installed editor, HTTP transport or chat-client scripting qualification.')
path=report_root/f'candidate-native-{suffix}.json'
path.write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(dict(passed=out.get('passed'),error=out.get('error'),path=str(path))),flush=True)
if not out.get('passed'):raise RuntimeError(out.get('error'))
