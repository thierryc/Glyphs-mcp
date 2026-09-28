"""Five serial fresh-process runs per M2 native route, target count and format."""
import argparse,json,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--route',choices=['baseline','candidate'],required=True)
a=p.parse_args();base=ROOT/'build/beta8-milestone2';reports=ROOT/'reports/beta8-milestone2/matrix'
reports.mkdir(parents=True,exist_ok=True);(base/'fixtures').mkdir(parents=True,exist_ok=True);(base/'logs').mkdir(exist_ok=True)
root=base/'baseline' if a.route=='baseline' else ROOT
progress=[]
def invoke(kind,count,suffix,name,extra=()):
    output=reports/(name+'.json')
    if output.exists():
        assert json.loads(output.read_text()).get('passed'),str(output)
        return
    command=['glyphs','run','--quiet','--app','/Applications/Glyphs 4.app','--plugins','',str(root/'scripts/benchmark_scoped_preparation.py'),'--',
        '--kind',kind,'--count',str(count),'--format',suffix,'--fixtures',str(base/'fixtures'),'--output',str(output),*extra]
    started=time.perf_counter()
    with (base/'logs'/f'{name}.log').open('w') as log:run=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=600)
    passed=run.returncode==0 and output.exists() and json.loads(output.read_text()).get('passed')
    progress.append(dict(case=name,passed=bool(passed),processSeconds=time.perf_counter()-started))
    (reports/f'progress-{a.route}.json').write_text(json.dumps(progress,indent=2)+'\n')
    print(name+(' PASS' if passed else ' FAIL'),flush=True)
    if not passed:raise RuntimeError(name)
for kind,counts in [('color',[1,10,100]),('width',[1,100,1000,4096])]:
    for suffix in ['glyphs','glyphspackage']:
        if not (base/'fixtures'/f'{kind}-4.{suffix}').exists():invoke(kind,1,suffix,f'fixture-{kind}-{suffix}',['--prepare-fixture'])
        for count in counts:
            for repeat in range(1,6):invoke(kind,count,suffix,f'{a.route}-{kind}-{count}-{suffix}-{repeat}')
