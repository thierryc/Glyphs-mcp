"""Fresh-process checkpoint cost control. Run with glyphs-cli, plugins disabled.

The existing harness uses GSFont serialization, not editor NSDocument Save.
Actual editor results are qualified separately in editor-*.json.
"""
import argparse
import json
from pathlib import Path
import resource
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from native_script_harness import Harness, BridgeError
from glyphs_mcp_bridge import checkpoint_restore
from glyphs_mcp_sidecar import checkpoints
from glyphs_mcp_protocol.source_identity import source_hash

parser=argparse.ArgumentParser()
parser.add_argument('--format',required=True)
parser.add_argument('--checkpoints',choices=['on','off'],required=True)
parser.add_argument('--output',type=Path,required=True)
a=parser.parse_args([v for v in sys.argv[1:] if v!='--'])
assert not a.output.exists()
setup=time.perf_counter()
h=Harness(count=423,suffix=a.format,fixture=ROOT/'build/beta8-milestone6/native-fixtures'/('Checkpoint.'+a.format))
root=h.source.parent
h.service.jobs.root=root/'jobs'  # Match the resolved native source, including /private on macOS.
def git(*arguments):return subprocess.check_output(['/usr/bin/git','-C',str(root),*arguments],stderr=subprocess.DEVNULL)
git('init','--template=','-b','main');git('config','user.name','Checkpoint Test');git('config','user.email','test@example.invalid')
git('add',h.source.name);git('commit','-m','Identical disposable baseline')
baseline=git('rev-parse','HEAD').decode().strip()
if a.checkpoints=='on':(root/'.glyphs-mcp.json').write_text('{"schemaVersion":1,"gitCheckpoints":{"enabled":true}}')
setup_seconds=time.perf_counter()-setup
stages={'nativeSaveSeconds':0,'checkpointAfterSaveSeconds':0};main_calls=[]
original_save=h.adapter.save_document
def save(*args,**kwargs):
 start=time.perf_counter()
 try:return original_save(*args,**kwargs)
 finally:stages['nativeSaveSeconds']+=time.perf_counter()-start
h.adapter.save_document=save
original_after=checkpoints.after_save
def after(*args,**kwargs):
 start=time.perf_counter()
 try:return original_after(*args,**kwargs)
 finally:stages['checkpointAfterSaveSeconds']+=time.perf_counter()-start
checkpoints.after_save=after
original_main=h.main
def main(callback):
 def measured():
  start=time.perf_counter()
  try:return callback()
  finally:main_calls.append(time.perf_counter()-start)
 return original_main(measured)
h.main=main
h.service.bridge.restore_checkpoint=lambda request:h.service.bridge.call(lambda:checkpoint_restore.restore(h.core,request,BridgeError))

def exercise(h):
 identity=h.service.list_documents()[0]['id'];master='0578215A-7423-43EB-8AD4-4C95A1C78DFA'
 before=h.main(lambda:[float(h.doc.font.glyphs[n].layers[master].width) for n in ['H','A']])
 start=time.perf_counter()
 v=h.service.edit_workflows.start(identity,kind='width_delta',glyphs=['H'],delta=.125,mode='preview',auto_keep=False,idempotency_key='cost')
 v=h.wait(v,'ready');stages['preparationSeconds']=time.perf_counter()-start
 start=time.perf_counter();v=h.wait(h.choose(v,'apply'),'applied');stages['applicationAndBaselineSeconds']=time.perf_counter()-start
 assert stages['nativeSaveSeconds']==0
 start=time.perf_counter();v=h.wait(h.choose(v,'save_result'),'saved');stages['saveVerificationCheckpointPollingSeconds']=time.perf_counter()-start
 assert (v['receipt'].get('checkpoint',{}).get('status')=='created')==(a.checkpoints=='on')
 start=time.perf_counter();observed=h.main(lambda:[float(h.doc.font.glyphs[n].layers[master].width) for n in ['H','A']])
 assert observed==[before[0]+.125,before[1]] and source_hash(h.source)==v['receipt']['sourceHashAfter']
 stages['verificationSeconds']=time.perf_counter()-start
 start=time.perf_counter();restored=h.service.edit_workflows.start(identity,kind='checkpoint_restore',options={'revision':baseline},mode='apply',auto_keep=False,idempotency_key='restore')
 restored=h.wait(restored,'applied');stages['historicalRestorationSeconds']=time.perf_counter()-start
 assert restored['document']['id']!=identity
 assert h.main(lambda:[float(h.doc.font.glyphs[n].layers[master].width) for n in ['H','A']])==before
 h.choose(restored,'finish_edit')
 return dict(format=a.format,checkpoints=a.checkpoints,stages=stages,setupSeconds=setup_seconds,
   longestMeasuredMainThreadSeconds=max(main_calls+[h.max_chunk]),peakProcessRSSBytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
   methodology='One fresh native process; identical real-font fixtures. Native GSFont save adapter, same candidate with project checkpoints on/off; not a v1 or editor Save comparison.')
result=h.run(exercise)
a.output.write_text(json.dumps(result,indent=2)+'\n')
if not result.get('passed'):raise RuntimeError(result['error'])
