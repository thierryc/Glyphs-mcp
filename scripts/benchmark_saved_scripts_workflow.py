"""One isolated native workflow or direct baseline measurement per fresh process."""
import hashlib
import json
from pathlib import Path
import resource
import sys
import time
from native_script_harness import Harness, ROOT
from glyphs_mcp_protocol import script_targets, scripts
from glyphs_mcp_protocol.script_runtime import ScriptRuntime
args=[a for a in sys.argv[1:] if a!='--']
count,contours=int(args[0]),int(args[1]);mode=args[2];output=Path(args[3])
assert (count,contours) in ((100,1),(1000,1),(4096,1),(100,12),(500,12)) and mode in ('native','direct')
source=(ROOT/'skills/glyphs-mcp-scripting/examples/vertical_flip.py').read_text()


def exercise(h):
    options=scripts.validate_options(dict(source=source,targets=dict(master=h.mid,glyphs='all',surface='background')))
    if mode=='direct':
        def direct():
            selected,_=script_targets.resolve(h.doc.font,options['targets'])
            runtime=ScriptRuntime(options,font=h.doc.font,targets=[l for _,l in selected]);runtime.initialize()
            managers=[g.undoManager() for g in h.doc.font.glyphs]
            for m in managers:m.disableUndoRegistration()
            before=[h.adapter._rounding_value(l) for _,l in selected]
            for _,layer in selected:layer.setTemporarilyDisableRounding_(True)
            try:
                start=time.perf_counter()
                for i,(target,layer) in enumerate(selected):runtime.run_target(layer,target,i,count)
                return time.perf_counter()-start
            finally:
                for (_,layer),original in zip(selected,before):layer.setTemporarilyDisableRounding_(original)
                for m in managers:m.enableUndoRegistration()
        elapsed=h.main(direct)
        row=dict(totalSeconds=elapsed,callbackSeconds=elapsed)
    else:
        # Dirty but unchanged fixture measures the same Save-and-run path as the
        # prior benchmark; clean-baseline zero-Save behavior is qualified separately.
        h.main(lambda:h.doc.updateChangeCount_(0))
        save_seconds=[];actual=h.service.save_document
        def measured_save(*a,**kw):
            start=time.perf_counter()
            try:return actual(*a,**kw)
            finally:save_seconds.append(time.perf_counter()-start)
        h.service.save_document=measured_save
        start=time.perf_counter();value=h.wait(h.start(options,'benchmark'),'waiting_run')
        preparation=time.perf_counter()-start
        run_start=time.perf_counter();value=h.wait(h.choose(value,'save_run_script'),'applied')
        run=time.perf_counter()-run_start;total=time.perf_counter()-start
        row=dict(totalSeconds=total,preparationSeconds=preparation,saveSeconds=sum(save_seconds),
                 dispatchToResultSeconds=run,scheduledNativeSeconds=h.native_seconds,
                 longestChunkSeconds=h.max_chunk,scheduledChunks=h.chunks)
        assert len(save_seconds)==1
    verification_start=time.perf_counter()
    assert h.main(lambda:h.doc.font.glyphs[0].layers[h.mid].background.paths[0].nodes[0].position.y)==700.25
    row['verificationSeconds']=time.perf_counter()-verification_start
    # Peak belongs to this mode alone, before saved-version restoration.
    row['peakRSSBytes']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if mode=='native':
        start=time.perf_counter();value=h.choose(value,'restore_saved_script');row['restoreSeconds']=time.perf_counter()-start
        assert value['state']=='discarded'
    return dict(targets=count,contours=contours,mode=mode,**row)

out=Harness(count=count,contours=contours).run(exercise)
out['sourceHashes']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
    for part in ('protocol','bridge','sidecar') for p in sorted((ROOT/'src'/part).rglob('*.py'))}
out['methodology']='One mode in one fresh glyphs-cli process. Native includes syntax/target preparation, authorized verified save through native GSFont fixture writer, main-thread batching, completion polling. Direct measures callbacks only with Undo disabled and precision flags enabled, excluding their setup/cleanup. RSS is macOS process high water including fixture and Glyphs runtime, sampled before restoration. CLI startup, HTTP/model latency and visual frame rate excluded. Native editor NSDocument Save is a separate integration gate.'
output.write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='sourceHashes'}),flush=True)
if not out.get('passed'):raise RuntimeError(out.get('error'))
