#!/usr/bin/env python3
"""Run the five-repeat native scripting benchmark sequentially to avoid contention."""
import json
from pathlib import Path
import statistics
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
output=Path(sys.argv[1] if len(sys.argv)>1 else ROOT/'build/native-script-benchmark')
output.mkdir(parents=True,exist_ok=True)
rows=[]
for count,contours in ((100,1),(1000,1),(4096,1),(100,12),(500,12)):
 for mode in ('direct','native'):
  for repeat in range(1,6):
   stem=f'{mode}-{count}-{contours}-{repeat}';path=(output/(stem+'.json')).resolve()
   with (output/(stem+'.log')).open('w') as log:
    subprocess.run(['glyphs','run','--quiet','--app','/Applications/Glyphs 4.app','--plugins','',str(ROOT/'scripts/benchmark_saved_scripts_workflow.py'),'--',str(count),str(contours),mode,str(path)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
   result=json.loads(path.read_text());assert result['passed'],result
   rows.append(result['data']);print(stem,round(result['data']['totalSeconds'],4),flush=True)
summary=[]
for count,contours in ((100,1),(1000,1),(4096,1),(100,12),(500,12)):
 for mode in ('direct','native'):
  group=[r for r in rows if (r['targets'],r['contours'],r['mode'])==(count,contours,mode)]
  stats={k:dict(median=statistics.median(r[k] for r in group),min=min(r[k] for r in group),max=max(r[k] for r in group)) for k in group[0] if k not in ('targets','contours','mode')}
  summary.append(dict(targets=count,contours=contours,mode=mode,runs=len(group),stats=stats))
(output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
