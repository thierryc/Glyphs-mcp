"""Five fresh native processes per format and glyph-coverage density."""
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'reports/beta8-milestone8/proof-matrix'
LOGS=ROOT/'build/beta8-milestone8/proof-logs'
REPORT.mkdir(parents=True,exist_ok=True);LOGS.mkdir(parents=True,exist_ok=True)
for suffix in ('glyphs','glyphspackage'):
    for density in ('sparse','dense'):
        for repeat in range(1,6):
            name=f'{suffix}-{density}-{repeat}';output=REPORT/(name+'.json')
            if output.exists() and json.loads(output.read_text()).get('passed'):continue
            command=['glyphs','run','--quiet','--app','/Applications/Glyphs 4.app','--plugins','',str(ROOT/'scripts/qualify_kerning_proof_native.py'),'--',suffix,density,str(output)]
            with (LOGS/(name+'.log')).open('w') as log:result=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=300)
            passed=result.returncode==0 and output.exists() and json.loads(output.read_text()).get('passed')
            print(name,'PASS' if passed else 'FAIL',flush=True)
            if not passed:raise SystemExit(name+' failed')
