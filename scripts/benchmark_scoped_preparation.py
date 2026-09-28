"""Fresh-process M2 native-route comparison; immutable fixtures built separately."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import resource
import sys
import time
from native_script_harness import Harness, GSFontMaster
from glyphs_mcp_protocol.preparation import stored_layers

parser=argparse.ArgumentParser()
parser.add_argument('--kind', choices=['color','width'], required=True)
parser.add_argument('--count', type=int, required=True)
parser.add_argument('--format', choices=['glyphs','glyphspackage'], required=True)
parser.add_argument('--fixtures', type=Path, required=True)
parser.add_argument('--prepare-fixture', action='store_true')
parser.add_argument('--trace', action='store_true')
parser.add_argument('--output', type=Path, required=True)
a=parser.parse_args([v for v in sys.argv[1:] if v!='--'])
assert not a.output.exists(), 'do not overwrite evidence'
size,contours=(501,4) if a.kind=='color' else (5000,4)
fixture=a.fixtures/f'{a.kind}-4.{a.format}'
if a.prepare_fixture:
    h=Harness(count=size,contours=contours,suffix=a.format,single_master=True,batch_fixture=True)
    h.doc.undoManager().beginUndoGrouping()
    if a.kind=='color':
        other=GSFontMaster();other.name='Bold';h.doc.font.masters.append(other)
    for g in h.doc.font.glyphs:
        g.undoManager().beginUndoGrouping()
        l=g.layers[h.mid];l.shapes=[s.copy() for s in l.background.shapes]
        if a.kind=='color':
            second=g.layers[other.id];second.shapes=[s.copy() for s in l.shapes];second.width=600.25
            g.userData['fixture']={'unchanged':'metadata'}
    h.doc.font.save(str(fixture),makeCopy=True)
    a.output.write_text(json.dumps(dict(passed=True,fixture=str(fixture),glyphs=size,contours=contours))+'\n')
    raise SystemExit(0)
h=Harness(count=size,suffix=a.format,fixture=fixture)


def exercise(h):
    trace=[]
    if a.trace:
        epoch=time.perf_counter();seen={};schedule=h.core.schedule;set_state=h.service.edit_workflows._set
        def event(source,state):trace.append(dict(source=source,state=state,seconds=time.perf_counter()-epoch))
        def schedule_trace(callback):
            def run():
                callback()
                for key,op in h.core._operations.items():
                    if seen.get(key)!=op['status']:
                        seen[key]=op['status'];event('native',op['status'])
            schedule(run)
        def workflow_trace(value,**fields):
            before=value['state'];result=set_state(value,**fields)
            if value['state']!=before:event('workflow',value['state'])
            return result
        h.core.schedule=schedule_trace;h.service.edit_workflows._set=workflow_trace
    identity=h.service.list_documents()[0]['id']
    # Select dispersed glyphs in reverse order to verify existing font-order patches.
    indices=sorted((i*size//a.count for i in range(a.count)),reverse=True)
    names=['probe'+str(i) for i in indices];selected=set(names)
    request=(dict(kind='width_delta',glyphs=names,delta=.25) if a.kind=='width' else
        dict(kind='native_action',options=dict(action='set_glyph_color',arguments=dict(color='red'),targets=[dict(glyph=n) for n in names])))
    def plist(owner):
        method=getattr(owner,'propertyListValueFormat_error_',None)
        if method:
            value,error=method(3,None);assert error is None
            return value.mutableCopy()
        return owner.propertyListValueFormat_(3).mutableCopy()
    def observe():
        result={}
        for g in h.doc.font.glyphs:
            metadata=plist(g)
            metadata.removeObjectForKey_('layers');metadata.removeObjectForKey_('color')
            layers={}
            for l in stored_layers(g):
                state=plist(l)
                state.removeObjectForKey_('width')
                inherited={}
                if a.kind=='width' and state.get('background') is not None:
                    background=state['background'].mutableCopy()
                    inherited['backgroundWidth']=float(background['width']) if 'width' in background else None
                    background.removeObjectForKey_('width');state['background']=background
                layers[str(l.layerId)]=dict(width=float(l.width),contents=str(state),**inherited)
            result[str(g.name)]=dict(color=g.color,layers=layers,metadata=str(metadata))
        return result
    def compare(actual,wanted):
        def diff(left,right,path=''):
            if left==right:return []
            if isinstance(left,dict) and isinstance(right,dict) and left.keys()==right.keys():
                return sum((diff(left[k],right[k],path+'/'+str(k)) for k in left),[])
            if isinstance(left,str) and isinstance(right,str):
                import difflib
                return [dict(path=path,diff=''.join(difflib.unified_diff(left.splitlines(True),right.splitlines(True))))]
            return [dict(path=path,expected=left,actual=right)]
        assert actual==wanted, diff(wanted,actual)[:3]
    before=h.main(observe);expected=deepcopy(before)
    for name in selected:
        if a.kind=='color':expected[name]['color']=0
        else:
            for layer in expected[name]['layers'].values():
                layer['width']+=.25
                if layer.get('backgroundWidth') is not None:layer['backgroundWidth']+=.25
    workers=[]
    def forbidden(*args,**kwargs):workers.append(True);raise AssertionError('native route launched worker')
    h.service.worker.prepare=forbidden
    main_calls=[];original=h.main
    def main(callback):
        def measured():
            started=time.perf_counter()
            try:return callback()
            finally:main_calls.append(time.perf_counter()-started)
        return original(measured)
    h.main=main
    started=time.perf_counter()
    value=h.service.edit_workflows.start(identity,mode='preview',auto_keep=False,idempotency_key='m2-bench',**request)
    value=h.wait(value,'ready');preparation=time.perf_counter()-started
    preparation_main=max(main_calls,default=0);main_calls.clear()
    assert h.main(observe)==before and not h.service.list_documents()[0]['dirty']
    job=h.service.jobs.get(value['jobId']);assert job['changeCount']==a.count
    assert not workers and not list(h.service.jobs.path(value['jobId']).glob('source*'))
    main_calls.clear();started=time.perf_counter()
    value=h.wait(h.choose(value,'apply'),'applied');application=time.perf_counter()-started
    application_main=max(main_calls,default=0)
    started=time.perf_counter();compare(h.main(observe),expected);verification=time.perf_counter()-started
    def undo_redo():
        managers=[h.doc.font.glyphs[n].undoManager() for n in names]
        for m in managers:assert m.canUndo();m.undo()
        assert observe()==before
        for m in managers:assert m.canRedo();m.redo()
        assert observe()==expected
    h.main(undo_redo)
    main_calls.clear();started=time.perf_counter()
    value=h.wait(h.choose(value,'discard'),'discarded');recovery=time.perf_counter()-started
    recovery_main=max(main_calls,default=0)
    assert h.main(observe)==before
    return dict(kind=a.kind,targets=a.count,format=a.format,fontGlyphs=size,contoursPerSurface=contours,
        preparationSeconds=preparation,applicationPollingSeconds=application,totalSeconds=preparation+application,
        verificationSeconds=verification,selectiveRecoverySeconds=recovery,saveSeconds=0,saveCalls=0,
        peakRSSBytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        longestPreparationCallSeconds=preparation_main,longestApplicationCallSeconds=application_main,
        longestRecoveryCallSeconds=recovery_main,longestScheduledChunkSeconds=h.max_chunk,
        preparationMetrics=job.get('preparationMetrics'),workerLaunches=len(workers),sourceCopyCount=0,
        unchangedControls=True,nativeUndoRedo=True,selectiveRecovery=True,**(dict(trace=trace) if a.trace else {}))
result=h.run(exercise)
result['methodologyVersion']=3
result['methodology']='Fresh native process; identical prebuilt fixtures; current native route before/after. Whole-font verification outside edit timings. Peak RSS includes runtime, fixture and verification. No prerequisite Save; editor Save and client latency separate. Scheduled/call maxima are instrumentation, not OS UI stall traces.'
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result),flush=True)
if not result.get('passed'):raise RuntimeError(result.get('error'))
