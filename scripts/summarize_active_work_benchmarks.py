"""Summarize measured polling costs without conflating them with editor latency."""
import json
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
directory = ROOT/'reports/beta8-milestone4'
rows = []
for history in (0, 100, 1000, 10000):
    for active in (False, True):
        row = dict(history=history, active=active)
        for route in ('baseline', 'candidate'):
            runs = [json.loads((directory/f'matrix/{route}-{history}-{active}-{i}.json').read_text()) for i in range(1,6)]
            def values(key, scale=1):
                result = [r[key]*scale for r in runs]
                return dict(median=median(result), range=[min(result), max(result)])
            row[route] = dict(pollMs=values('activityMedianSeconds',1000),
                pollCpuMs=values('activityCpuSeconds',50),
                supervisorCpuMsPerTick=values('supervisorCpuSeconds',10),
                peakMiB=values('peakMemoryBytes',1/2**20),
                recordsCopiedPerPoll=runs[0]['activityCounts']['copiedRecords']/20,
                readsPerPoll=runs[0]['activityCounts']['reads']/20,
                writesPerPoll=runs[0]['activityCounts']['writes']/20)
        rows.append(row)
(directory/'benchmark-summary.json').write_text(json.dumps(rows,indent=2)+'\n')
lines = ['| History | Active jobs | Poll ms, baseline → candidate | CPU ms/poll | Supervisor CPU ms/tick | Peak MiB | Record copies/poll | Disk reads / writes per poll |',
         '| ---: | ---: | --- | --- | --- | --- | --- | --- |']
for row in rows:
    before, after = row['baseline'], row['candidate']
    def pair(key): return f"{before[key]['median']:.4f} → {after[key]['median']:.4f}"
    lines.append(f"| {row['history']:,} | {int(row['active'])} | {pair('pollMs')} | {pair('pollCpuMs')} | {pair('supervisorCpuMsPerTick')} | {pair('peakMiB')} | {before['recordsCopiedPerPoll']:g} → {after['recordsCopiedPerPoll']:g} | {before['readsPerPoll']:g}/{before['writesPerPoll']:g} → {after['readsPerPoll']:g}/{after['writesPerPoll']:g} |")
lines += ['', 'Each cell is the median of five fresh processes. Per-run medians, ranges, CPU and memory are retained in `benchmark-summary.json` and `matrix/`.']
(directory/'benchmark-table.md').write_text('\n'.join(lines)+'\n')
print('\n'.join(lines))
