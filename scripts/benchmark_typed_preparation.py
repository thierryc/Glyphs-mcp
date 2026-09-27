"""One existing-worker or native typed workflow per isolated native process."""
import json
from pathlib import Path
import resource
import sys
import time
from native_script_harness import Harness, ROOT, GSFontMaster
from glyphs_mcp_protocol.preparation.simple import CAPABILITY
from glyphs_mcp_protocol.preparation.outline import _path_state
from glyphs_mcp_protocol.outline import path_hash
from glyphs_mcp_protocol import dimensions

args = [a for a in sys.argv[1:] if a != '--']
kind, count, contours, suffix, route, output = args
count, contours, output = int(count), int(contours), Path(output)
assert route in {'worker', 'native'}
# Capture native preparation failures with their Python callsite during qualification.
from glyphs_mcp_bridge import typed_preparation
_original_fail=typed_preparation.fail
def traced_fail(core,operation,exc):
    import traceback
    traceback.print_exc()
    return _original_fail(core,operation,exc)
typed_preparation.fail=traced_fail
h = Harness(count=count if kind != 'dimensions' else 1, contours=contours, suffix=suffix, single_master=True)


def exercise(h):
    def setup():
        h.doc.undoManager().beginUndoGrouping()
        for g in h.doc.font.glyphs: g.undoManager().beginUndoGrouping()
        if kind == 'dimensions':
            keys = list(dimensions.CATALOG)
            for i in range((count-1)//len(keys)):
                master = GSFontMaster();master.name='Master'+str(i+2);h.doc.font.masters.append(master)
        h.doc.font.save(str(h.source), makeCopy=True)
        h.clean()
    h.main(setup)
    identity = h.service.list_documents()[0]['id']
    if route == 'worker':
        actual = h.service.bridge.status
        def legacy_status():
            value=actual();value['jobCapabilities']=[c for c in value['jobCapabilities'] if c != CAPABILITY];return value
        h.service.bridge.status=legacy_status
    workers=[];actual_worker=h.service.worker.prepare
    def measured_worker(*a,**kw):
        workers.append(True);return actual_worker(*a,**kw)
    h.service.worker.prepare=measured_worker
    def request():
        if kind == 'width': return dict(kind='width_delta', delta=.25)
        if kind == 'color': return dict(kind='native_action', options=dict(action='set_glyph_color',arguments=dict(color='red'),targets=[dict(glyph='probe'+str(i)) for i in range(count)]))
        if kind == 'dimensions':
            keys=list(dimensions.CATALOG);masters=list(h.doc.font.masters)
            return dict(kind='dimensions_edit',options=dict(changes=[dict(master=str(masters[i//len(keys)].id), key=keys[i%len(keys)],value=50.25+i) for i in range(count)]))
        return dict(kind='outline_edit', options=dict(compatibilityPolicy='preserve',targets=[dict(glyph='probe'+str(i), surface='background',referenceLayer=h.mid,layers=dict(scope='ids',ids=[h.mid]),guards=[dict(path=0,hash=path_hash(_path_state(h.doc.font.glyphs['probe'+str(i)].layers[h.mid].background.paths[0])))],operations=[dict(op='update_nodes',path=0,updates=[dict(index=0,delta=dict(dx=.25,dy=.5))])]) for i in range(count)]))
    req=h.main(request)
    before=h.main(lambda: observe(h))
    start=time.perf_counter()
    value=h.service.edit_workflows.start(identity,idempotency_key='typed-bench',mode='preview',auto_keep=False,**req)
    value=h.wait(value,'ready')
    preparation=time.perf_counter()-start
    assert h.main(lambda: observe(h))==before, 'preparation changed live data'
    assert not h.service.list_documents()[0]['dirty']
    start=time.perf_counter();value=h.wait(h.choose(value,'apply'),'applied');application=time.perf_counter()-start
    start=time.perf_counter();after=h.main(lambda:observe(h));verify(h,before,after);verification=time.perf_counter()-start
    job=h.service.jobs.get(value['jobId'])
    copies=list(h.service.jobs.path(value['jobId']).glob('source*'))
    assert job['changeCount']==count
    assert len(workers)==(1 if route=='worker' else 0)
    if route=='native': assert not copies
    peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    children_peak=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    start=time.perf_counter();value=h.wait(h.choose(value,'discard'),'discarded');recovery=time.perf_counter()-start
    assert h.main(lambda:observe(h))==before
    # Test Keep and native Undo/Redo on another authorized edit, without a save.
    h.main(h.clean)
    second=h.service.edit_workflows.start(identity,idempotency_key='keep-probe',mode='preview',auto_keep=False,**req)
    second=h.wait(second,'ready');second=h.wait(h.choose(second,'apply'),'applied')
    assert h.choose(second,'finish_edit')['state']=='executed'
    def undo_redo():
        if kind=='dimensions': managers=[h.doc.undoManager()]
        else: managers=[g.undoManager() for g in h.doc.font.glyphs]
        for m in managers: assert m.canUndo();m.undo()
        assert observe(h)==before
        for m in managers: assert m.canRedo();m.redo()
        verify(h,before,observe(h))
    h.main(undo_redo)
    return dict(kind=kind,targets=count,contours=contours,format=suffix,route=route,
        preparationSeconds=preparation,applicationPollingSeconds=application,totalSeconds=preparation+application,
        verificationSeconds=verification,selectiveRecoverySeconds=recovery,
        longestMainThreadChunkSeconds=h.max_chunk,peakRSSBytes=peak,workerChildrenPeakRSSBytes=children_peak,
        preparationMetrics=job.get('preparationMetrics'),workerLaunches=1 if route=='worker' else 0,
        sourceCopyCount=len(copies),nativeUndoAfterKeep=True,
        saveSeconds=0,saveCalls=0)


def observe(h):
    f=h.doc.font
    if kind=='dimensions':
        keys=list(dimensions.CATALOG);masters=list(f.masters)
        return [dimensions.read_state(f.userData[dimensions.STORAGE_KEY],str(masters[i//len(keys)].id),keys[i%len(keys)]) for i in range(count)]
    if kind=='color':return [None if g.color is None else int(g.color) for g in f.glyphs]
    if kind=='width':return [float(g.layers[h.mid].width) for g in f.glyphs]
    return [(float(g.layers[h.mid].background.paths[0].nodes[0].position.x),float(g.layers[h.mid].background.paths[0].nodes[0].position.y)) for g in f.glyphs]


def verify(h,before,after):
    if kind=='width':assert after==[v+.25 for v in before]
    elif kind=='color':assert after==[0]*count
    elif kind=='dimensions':assert after==[dict(present=True,value=50.25+i) for i in range(count)]
    else:assert after==[(x+.25,y+.5) for x,y in before]

result=h.run(exercise)
result['methodology']='Fresh glyphs-cli process, real native GSFont and GSDocument fixture. Preparation and guarded application through real workflow; clean baseline so no task Save. Fixture serialization and CLI startup excluded. Worker memory is separate and recorded by the runner when available. PeakRSS is this process before recovery. Selective recovery and native Undo/Redo after Keep verified. Actual editor NSDocument Save and installed-client latency require separate integration tests.'
output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result),flush=True)
if not result.get('passed'):raise RuntimeError(result.get('error'))
