"""One exact-assignment route/format/count in a fresh native process."""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import sys
import time

p=argparse.ArgumentParser()
p.add_argument('--route',choices=['typed','script'],required=True)
p.add_argument('--count',type=int,choices=[1,10,100],required=True)
p.add_argument('--format',choices=['glyphs','glyphspackage'],required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--baseline',action='store_true')
args=p.parse_args([a for a in sys.argv[1:] if a!='--'])
ROOT=Path(__file__).resolve().parents[1]
if args.baseline:
    sys.path.insert(0,str(ROOT/'build/beta8-milestone8/baseline/scripts'))
from native_script_harness import Harness

SOURCE='for row in params["edits"]:\n    font.setKerningForPair(row["master"], row["left"]["name"], row["right"]["name"], row["value"], direction=0)\n'


def exercise(h):
    document=h.service.list_documents()[0]['id']
    rows=[dict(op='set',master=h.mid,direction='LTR',left=dict(kind='glyph',name=f'probe{i}'),
        right=dict(kind='glyph',name=f'probe{args.count}'),value=-72.5-i/8) for i in range(args.count)]
    request=dict(kind='kerning_edit',options=dict(edits=rows)) if args.route=='typed' else dict(kind='python_script',options=dict(
        source=SOURCE,params=dict(edits=rows),entrypoint='script',targets=[],summary=f'Set {args.count} exact kerning entries'))
    def begin(key):
        return h.service.edit_workflows.start(document,mode='preview',auto_keep=False,idempotency_key=key,**request)
    start=time.perf_counter()
    value=h.wait(begin('benchmark'),'ready','waiting_run')
    preparation=time.perf_counter()-start
    start=time.perf_counter()
    value=h.wait(h.choose(value,'apply' if args.route=='typed' else 'run_script'),'applied')
    execution=time.perf_counter()-start
    job=h.service.jobs.get(value['jobId'])
    if args.route=='typed':
        assert job['preparationRoute']=='native'
        assert not list(h.service.jobs.path(value['jobId']).glob('source*'))
    def verify(applied):
        font=h.doc.font
        for row in rows:
            actual=font.kerningForPair(h.mid,row['left']['name'],row['right']['name'])
            assert actual==(row['value'] if applied else None),(row,actual)
        assert font.glyphs['probe0'].layers[h.mid].width==500
    start=time.perf_counter();h.main(lambda:verify(True));verification=time.perf_counter()-start
    peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    longest=h.max_chunk;native=h.native_seconds
    start=time.perf_counter()
    value=h.choose(value,'discard' if args.route=='typed' else 'restore_saved_script')
    value=h.wait(value,'discarded');h.main(lambda:verify(False))
    recovery=time.perf_counter()-start
    # A separate, untimed preparation/application obtains a real result to save.
    if args.route=='typed':
        h.main(lambda:(h.doc.font.save(str(h.source),makeCopy=True),h.clean()))
    document=h.service.list_documents()[0]['id']
    value=h.wait(begin('save-probe'),'ready','waiting_run')
    value=h.wait(h.choose(value,'apply' if args.route=='typed' else 'run_script'),'applied')
    start=time.perf_counter();value=h.wait(h.choose(value,'save_result'),'saved');saving=time.perf_counter()-start
    return dict(route=args.route,count=args.count,format=args.format,baseline=args.baseline,
        preparationSeconds=preparation,executionPollingSeconds=execution,verificationSeconds=verification,
        recoverySeconds=recovery,saveSeconds=saving,totalEditSeconds=preparation+execution+verification,
        peakRSSBytes=peak,longestMainThreadChunkSeconds=longest,scheduledNativeSeconds=native,
        recoveryCoverage='selected stored pairs' if args.route=='typed' else 'whole saved font')


out=Harness(count=args.count+1,suffix=args.format,single_master=True).run(exercise)
out['methodology']='One route/count/format per fresh Glyphs CLI process. Workflow includes native preparation, dispatch, application, result polling, independent verification and recovery. Save is a second equivalent result. Native GSFont serialization is not editor NSDocument saving. Peak RSS includes Glyphs, fixture and route, sampled before recovery. CLI startup, HTTP/client latency and UI frame rate excluded.'
code_root=ROOT/'build/beta8-milestone8/baseline' if args.baseline else ROOT
out['sourceDigest']=hashlib.sha256(b''.join(p.read_bytes() for p in sorted((code_root/'src').rglob('*.py')) if '__pycache__' not in str(p))).hexdigest()
args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='error'}),flush=True)
if not out.get('passed'):raise RuntimeError(out.get('error'))
