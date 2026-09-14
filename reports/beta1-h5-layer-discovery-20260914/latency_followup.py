"""Bounded follow-up for the background-target callback outlier. No product edits."""
from pathlib import Path
p=Path('/Users/thierryc/Dev/github/thierryc/Glyphs-mcp-worktrees/v2/build/milestone7/desktop/reports/beta1-h5-layer-discovery-20260914/qualify_native.py')
prefix=p.read_text().split('def run():')[0]
prefix=prefix.replace("'native-facts.json'","'latency-followup.json'").replace('started=time.perf_counter();visits=[];counts=0','started=time.perf_counter();cpu=time.thread_time();visits=[];counts=0').replace('indices=visits,countReads=counts','cpuMs=(time.thread_time()-cpu)*1000,indices=visits,countReads=counts')
exec(compile(prefix,str(p),'exec'))
facts['purpose']='Repeat foreground switch / background-target read; per-field and layer-projection timing, plus callback CPU time. Original benchmark unchanged.'
facts['fieldTimings']=[];facts['projectionTimings']=[]
original_field=layer_inventory._field;original_read=layer_inventory.read
def timed_field(layer,field):
 start=time.perf_counter();cpu=time.thread_time()
 try:return original_field(layer,field)
 finally:facts['fieldTimings'].append(dict(field=field,wallMs=(time.perf_counter()-start)*1000,cpuMs=(time.thread_time()-cpu)*1000))
def timed_read(*args,**kwargs):
 start=time.perf_counter();cpu=time.thread_time();i=len(facts['fieldTimings'])
 try:return original_read(*args,**kwargs)
 finally:facts['projectionTimings'].append(dict(wallMs=(time.perf_counter()-start)*1000,cpuMs=(time.thread_time()-cpu)*1000,fields=facts['fieldTimings'][i:]))
layer_inventory._field=timed_field;layer_inventory.read=timed_read

def run_followup():
 try:
  status,_=call('get_status');facts['runtime']=status['data']
  for component in ('sidecar','bridge'):
   actual=status['data'] if component=='sidecar' else status['data']['bridge'];check(component+' fingerprint',manifest[component]['codeHash'],actual['codeHash'])
  originals=main.call(lambda:{str(f.filepath):proof(f) for f in Glyphs.fonts})
  main.call(lambda:open_copy('synthetic','latency-unrelated'));before_unrelated=main.call(lambda:proof(fonts['latency-unrelated']))
  for phase in ('first','warmup','rep1','rep2','rep3','rep4','rep5'):
   name='latency-'+phase;path=main.call(lambda:open_copy('synthetic',name));doc,_,docs=discover(path)
   before,expected=main.call(lambda:(proof(fonts[name]),oracle.rows(fonts[name].glyphs['a'])))
   for role in ('foreground','afterForegroundSwitch','backgroundIDsOnly'):
    if role=='foreground':main.call(lambda:fonts[name].show())
    elif role=='afterForegroundSwitch':main.call(lambda:fonts['latency-unrelated'].show())
    fields=['id'] if role=='backgroundIDsOnly' else list(oracle.FIELDS)
    start=len(facts['projectionTimings']);body,ms=page(doc,'a',phase=phase,fields=fields)
    check(phase+' '+role+' values',[{k:r[k] for k in fields} for r in expected],body['data'][0]['values']['items'])
    check(phase+' '+role+' complete',True,body['data'][0]['values']['complete'])
    facts['trials'].append(dict(phase=phase,role=role,openDocuments=docs,httpMs=ms,callback=facts['calls'][-1]['callbacks'][0],projection=facts['projectionTimings'][start]));save()
   check(phase+' preservation',before,main.call(lambda:proof(fonts[name])));main.call(lambda:close_copy(name))
  check('unrelated preservation',before_unrelated,main.call(lambda:proof(fonts['latency-unrelated'])))
  for path,before in originals.items():check('original preservation '+path,before,main.call(lambda:proof(next(f for f in Glyphs.fonts if str(f.filepath)==path))))
  facts['passed']=True
 except Exception:facts['passed']=False;facts['error']=traceback.format_exc()
 finally:
  def cleanup():
   layer_inventory._field=original_field;layer_inventory.read=original_read;layer_inventory.value=original_value;del layer_inventory.getattr;life.server.main_thread.call=original_call
   for name in list(fonts):close_copy(name)
  try:main.call(cleanup)
  except Exception:facts['cleanupError']=traceback.format_exc()
  facts['finishedAt']=datetime.now(timezone.utc).isoformat();facts['loadAfter']=os.getloadavg();save();print('H5 LATENCY FINISHED',facts.get('passed'),facts.get('error',''))
Thread(target=run_followup,name='H5 bounded latency follow-up',daemon=True).start();print('H5 latency follow-up started')
