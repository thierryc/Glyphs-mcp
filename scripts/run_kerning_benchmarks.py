"""Five serial fresh-process runs: native script baseline versus typed entries."""
import json
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'reports/beta8-milestone8/matrix'
LOGS=ROOT/'build/beta8-milestone8/bench-logs'
REPORT.mkdir(parents=True,exist_ok=True);LOGS.mkdir(parents=True,exist_ok=True)
for route in ('script','typed'):
    for suffix in ('glyphs','glyphspackage'):
        for count in (1,10,100):
            for repeat in range(1,6):
                name=f'{route}-{suffix}-{count}-{repeat}'
                output=REPORT/(name+'.json')
                if output.exists() and json.loads(output.read_text()).get('passed'): continue
                command=['glyphs','run','--quiet','--app','/Applications/Glyphs 4.app','--plugins','',str(ROOT/'scripts/benchmark_kerning.py'),'--',
                         '--route',route,'--count',str(count),'--format',suffix,'--output',str(output)]
                if route=='script':command.append('--baseline')
                start=time.perf_counter()
                with (LOGS/(name+'.log')).open('w') as log:result=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=300)
                passed=result.returncode==0 and output.exists() and json.loads(output.read_text()).get('passed')
                print(name, 'PASS' if passed else 'FAIL',round(time.perf_counter()-start,3),flush=True)
                if not passed:raise SystemExit(name+' failed; inspect '+str(LOGS/(name+'.log')))
