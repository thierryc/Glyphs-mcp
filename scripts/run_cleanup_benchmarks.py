"""Serial five-run cleanup comparison using unchanged M1/M2 disposable fixtures."""
import argparse
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--route', choices=['baseline','candidate'], required=True)
args = parser.parse_args()
base = ROOT/'build/beta8-milestone3'
root = base/'baseline' if args.route == 'baseline' else ROOT
reports = ROOT/'reports/beta8-milestone3/matrix'; reports.mkdir(parents=True, exist_ok=True)
logs = base/'logs'; logs.mkdir(parents=True, exist_ok=True)
progress = []
for kind, count in [('width',1000),('width',4096),('script',1000),('script',10000),('script',20000)]:
    fixtures = ROOT/('build/beta8-milestone2/fixtures' if kind == 'width' else 'build/beta8-milestone1/fixtures')
    for suffix in ('glyphs','glyphspackage'):
        for repeat in range(1,6):
            name = f'{args.route}-{kind}-{count}-{suffix}-{repeat}'
            output = reports/(name+'.json')
            if output.exists():
                assert json.loads(output.read_text()).get('passed'), str(output)
                continue
            command = ['glyphs','run','--quiet','--app','/Applications/Glyphs 4.app','--plugins','',
                str(root/'scripts/benchmark_cleanup.py'),'--','--workload',kind,'--count',str(count),
                '--format',suffix,'--fixtures',str(fixtures),'--output',str(output)]
            started = time.perf_counter()
            with (logs/(name+'.log')).open('w') as log:
                result = subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=900)
            passed = result.returncode == 0 and output.exists() and json.loads(output.read_text()).get('passed')
            progress.append(dict(case=name,passed=bool(passed),processSeconds=time.perf_counter()-started))
            (reports/f'progress-{args.route}.json').write_text(json.dumps(progress,indent=2)+'\n')
            print(name+(' PASS' if passed else ' FAIL'),flush=True)
            if not passed: raise RuntimeError(name)
