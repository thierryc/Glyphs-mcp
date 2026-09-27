"""Serial isolated comparisons; never updates or restarts the running editor."""
import argparse
import json
from pathlib import Path
import subprocess
import time
ROOT=Path(__file__).resolve().parents[1]
CLI='/Library/Frameworks/Python.framework/Versions/3.14/bin/glyphs'
APP='/Applications/Glyphs 4.app'
p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);p.add_argument('--resume',action='store_true');args=p.parse_args()
report=args.report.resolve();out=report/'benchmarks';out.mkdir(parents=True,exist_ok=True)
logs=ROOT/'build/typed-preparation-benchmarks';logs.mkdir(parents=True,exist_ok=True)
cases=[('width',n,1) for n in (1,100,1000,4096)]+[('dimensions',n,1) for n in (1,10,100)]+[('color',n,1) for n in (1,10,100)]+[('outline',n,c) for c in (1,12) for n in (1,10,100)]
runs=[]
for kind,n,c in cases:
 for suffix in ('glyphs','glyphspackage'):
  for repeat in range(1,6):
   for route in ('worker','native'):
    name=f'{kind}-{n}-{c}-{suffix}-{repeat}-{route}';output=out/(name+'.json')
    if output.exists():
     if not args.resume:raise RuntimeError('Evidence already exists: '+str(output))
     d=json.loads(output.read_text())
     if not d.get('passed'):raise RuntimeError('Existing failed evidence: '+str(output))
     runs.append(dict(name=name,passed=True,retained=True));continue
    start=time.perf_counter()
    with (logs/(name+'.log')).open('w') as log:
     proc=subprocess.run([CLI,'run','--app',APP,'--plugins','',str(ROOT/'scripts/benchmark_typed_preparation.py'),'--',kind,str(n),str(c),suffix,route,str(output)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=180)
    d=json.loads(output.read_text()) if output.exists() else {}
    runs.append(dict(name=name,passed=d.get('passed',False) and proc.returncode==0,processWallSeconds=time.perf_counter()-start))
    (report/'benchmark-progress.json').write_text(json.dumps(dict(completed=len(runs),total=len(cases)*20,runs=runs),indent=2)+'\n')
    print(f'{len(runs)}/{len(cases)*20} {name}: '+('PASS' if runs[-1]['passed'] else 'FAIL'),flush=True)
    if not runs[-1]['passed']:raise RuntimeError(name)
