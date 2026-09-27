"""Summarize recorded fresh-process qualification runs without changing evidence."""
import json
from pathlib import Path
from statistics import median

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'reports/native-scripting-qualification-20260926'


def stats(values):
    return dict(n=len(values),median=median(values),minimum=min(values),maximum=max(values))


def main():
    import argparse
    global REPORT
    parser=argparse.ArgumentParser()
    parser.add_argument("--report",type=Path,default=REPORT)
    REPORT=parser.parse_args().report.resolve()
    folder=REPORT/'benchmarks'
    bulk=[];real=[]
    for count,contours in [(100,1),(1000,1),(4096,1),(100,12),(500,12)]:
        for mode in ('direct','native'):
            rows=[json.loads((folder/f'{mode}-{count}-{contours}-{n}.json').read_text()) for n in range(1,6)]
            assert all(r['passed'] for r in rows)
            keys=[k for k,v in rows[0]['data'].items() if isinstance(v,(int,float)) and k not in ('targets','contours')]
            bulk.append(dict(targets=count,contours=contours,mode=mode,
                             metrics={k:stats([r['data'][k] for r in rows]) for k in keys}))
    for suffix in ('glyphs','glyphspackage'):
        rows=[json.loads((folder/f'real-{suffix}-{n}'/f'candidate-native-{suffix}.json').read_text()) for n in range(1,6)]
        assert all(r['passed'] for r in rows)
        for index,name in enumerate(('path','spacing','kerning')):
            tasks=[r['data']['tasks'][index] for r in rows]
            assert all(t['name']==name for t in tasks)
            metrics={k:stats([t['timingsSeconds'][k] for t in tasks]) for k in tasks[0]['timingsSeconds']}
            metrics['processPeakRSSBytes']=stats([t['processPeakRSSBytes'] for t in tasks])
            real.append(dict(format=suffix,task=name,metrics=metrics,
                             saveCalls=[t['saveCalls'] for t in tasks]))
    out=dict(bulk=bulk,realTasks=real,
             methodology='Five fresh native processes per bulk fixture/mode and real-font file format. Bulk direct times callback loop only; workflow includes preparation, verified GSFont fixture save, execution/polling. Editor NSDocument saves and Codex tool latency are separate integration evidence. Bulk RSS is isolated by mode before restoration. Real-task RSS is a cumulative process high water across path, spacing, kerning; it is not isolated per task. Longest chunk is scheduled wrapper work, not complete event-loop latency or frame-rate measurement.')
    (REPORT/'benchmark-summary.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(out,indent=2))


if __name__=='__main__':main()
