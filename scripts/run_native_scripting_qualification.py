"""Serial fresh-process benchmarks; never installs or restarts the editor."""
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'reports/native-scripting-qualification-20260926'
CLI='/Library/Frameworks/Python.framework/Versions/3.14/bin/glyphs'
APP='/Applications/Glyphs 4.app'


def main():
    import argparse
    global REPORT
    parser=argparse.ArgumentParser()
    parser.add_argument("--report",type=Path,default=REPORT)
    REPORT=parser.parse_args().report.resolve()
    benchmark=REPORT/'benchmarks';benchmark.mkdir(parents=True,exist_ok=True)
    logs=ROOT/'build/native-scripting-qualification';logs.mkdir(parents=True,exist_ok=True)
    cases=[]
    for count,contours in [(100,1),(1000,1),(4096,1),(100,12),(500,12)]:
        for mode in ('direct','native'):
            for repeat in range(1,6):
                name=f'{mode}-{count}-{contours}-{repeat}'
                output=benchmark/(name+'.json')
                cases.append((name,ROOT/'scripts/benchmark_saved_scripts_workflow.py',
                              [str(count),str(contours),mode,str(output)],output))
    for suffix in ('glyphs','glyphspackage'):
        for repeat in range(1,6):
            name=f'real-{suffix}-{repeat}';folder=benchmark/name
            cases.append((name,ROOT/'scripts/qualify_real_native_tasks.py',
                          [str(folder),suffix],folder/f'candidate-native-{suffix}.json'))
    results=[]
    for index,(name,script,args,output) in enumerate(cases,1):
        if output.exists():
            raise RuntimeError(f'Refusing to overwrite benchmark evidence: {output}')
        start=time.perf_counter()
        with (logs/(name+'.log')).open('w') as stream:
            proc=subprocess.run([CLI,'run','--app',APP,'--plugins','',str(script),'--',*args],
                                cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=180)
        data=json.loads(output.read_text()) if output.exists() else {}
        row=dict(name=name,exitCode=proc.returncode,passed=data.get('passed',False),
                 processWallSeconds=time.perf_counter()-start,path=str(output.relative_to(ROOT)))
        results.append(row)
        (REPORT/'benchmark-progress.json').write_text(json.dumps(dict(completed=index,total=len(cases),runs=results),indent=2)+'\n')
        print(f'{index}/{len(cases)} {name}: '+('PASS' if row['passed'] and not proc.returncode else 'FAIL'),flush=True)
        if not row['passed'] or proc.returncode:raise RuntimeError(name)


if __name__=='__main__':main()
