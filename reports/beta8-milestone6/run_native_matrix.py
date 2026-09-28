"""Five fresh native processes for each format and checkpoint-policy control."""
import json
from pathlib import Path
import subprocess
import time
ROOT=Path(__file__).resolve().parents[2]
reports=ROOT/'reports/beta8-milestone6/native-matrix'
logs=ROOT/'build/beta8-milestone6/native-logs';logs.mkdir(exist_ok=True)
progress=[]
for fmt in ('glyphs','glyphspackage'):
 for policy in ('off','on'):
  for repeat in range(1,6):
   name=f'{policy}-{fmt}-{repeat}';output=reports/(name+'.json')
   if output.exists():
    assert json.loads(output.read_text()).get('passed'),output
    continue
   started=time.perf_counter()
   with (logs/(name+'.txt')).open('w') as log:
    result=subprocess.run(['glyphs','run','--quiet','--app','/Applications/Glyphs 4.app','--plugins','',
      str(ROOT/'reports/beta8-milestone6/benchmark_native.py'),'--','--format',fmt,'--checkpoints',policy,'--output',str(output)],
      stdout=log,stderr=subprocess.STDOUT,timeout=120,cwd=ROOT)
   passed=result.returncode==0 and output.exists() and json.loads(output.read_text()).get('passed')
   progress.append(dict(case=name,passed=bool(passed),processSeconds=time.perf_counter()-started))
   (reports/'progress.json').write_text(json.dumps(progress,indent=2)+'\n')
   print(name,'PASS' if passed else 'FAIL',flush=True)
   assert passed,name
