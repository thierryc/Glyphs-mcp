"""Summarize all five-run M3 comparisons, retaining raw ranges and stage timings."""
import json
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
folder = ROOT/'reports/beta8-milestone3/matrix'
summary = []
for workload, count in [('width',1000),('width',4096),('script',1000),('script',10000),('script',20000)]:
    for suffix in ('glyphs','glyphspackage'):
        case = dict(workload=workload,targets=count,format=suffix)
        for route in ('baseline','candidate'):
            records = [json.loads((folder/f'{route}-{workload}-{count}-{suffix}-{i}.json').read_text()) for i in range(1,6)]
            assert all(r['passed'] for r in records)
            values = [{**r['data'], **{'cleanup.'+k:v for k,v in r['cleanup'].items()}} for r in records]
            metrics = {}
            for name in values[0]:
                if name.endswith(('Seconds','Bytes')):
                    numbers = [v[name] for v in values]
                    if all(isinstance(v,(float,int)) and not isinstance(v,bool) for v in numbers):
                        metrics[name] = dict(median=median(numbers),min=min(numbers),max=max(numbers))
            case[route] = metrics
        summary.append(case)
(folder/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
lines = ['# Native cleanup comparison','',
    'Five fresh native processes per case/route; 100 passing runs. These are native harness workflows,',
    'not installed-client latency or actual editor Save measurements. Raw files retain stage timings',
    'and native host identity; `summary.json` contains all metric medians/minima/maxima.','',
    'Seconds shown as median [minimum–maximum]. Cleanup scheduling includes application and',
    'selective recovery for typed edits; script restoration reloads the saved font instead.','',
    '| Workload | Targets | Format | Total before → after | Longest scheduled cleanup before → after |',
    '| --- | ---: | --- | --- | --- |']


def metric(case, route, key):
    v = case[route][key]
    return f"{v['median']:.3f} [{v['min']:.3f}–{v['max']:.3f}]"


for case in summary:
    row = [case['workload'],str(case['targets']),'.'+case['format']]
    for key in ('totalSeconds','cleanup.longestScheduledCleanupSeconds'):
        row.append(metric(case,'baseline',key)+' → '+metric(case,'candidate',key))
    lines.append('| '+' | '.join(row)+' |')
lines += ['', 'The cleanup maximum is not an overall UI-pause limit. Inspect the overall scheduled',
    'maximum, main-thread call maximum and stage timings in the JSON before making a responsiveness',
    'claim. Individual native calls, whole-font source checks and script invocations remain indivisible.',
    'Peak RSS includes runtime, fixture and verification, not only incremental edit memory.']
(folder/'README.md').write_text('\n'.join(lines)+'\n')
