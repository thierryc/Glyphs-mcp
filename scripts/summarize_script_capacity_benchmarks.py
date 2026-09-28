"""Summarize the complete five-run capacity matrix without mixing timing methods."""
import argparse
import collections
import json
from pathlib import Path
import statistics

parser = argparse.ArgumentParser()
parser.add_argument('report', type=Path)
args = parser.parse_args()
groups = collections.defaultdict(list)
for path in sorted(args.report.glob('*.json')):
    label = path.name.split('-')[0]
    if label not in {'baseline', 'candidate', 'direct', 'dirty'}:
        continue
    evidence = json.loads(path.read_text())
    assert evidence.get('passed'), path
    row = evidence['data']
    groups[(label, row['format'], row['targets'], row['contours'])].append(row)
assert len(groups) == 30, f'Expected 30 groups, found {len(groups)}'


def stats(values):
    return dict(median=statistics.median(values), minimum=min(values), maximum=max(values))


summary = []
for key, rows in sorted(groups.items()):
    assert len(rows) == 5, (key, len(rows))
    label, suffix, count, contours = key
    metrics = {name: stats([r[name] for r in rows]) for name in rows[0]
               if name.endswith(('Seconds', 'Bytes', 'Calls', 'Chunks'))
               and all(isinstance(r.get(name), (float, int)) for r in rows)}
    stages = {name: stats([r['stagesSeconds'][name] for r in rows])
              for name in rows[0].get('stagesSeconds', {})}
    summary.append(dict(route=label, format=suffix, targets=count, contours=contours,
                        runs=len(rows), metrics=metrics, stagesSeconds=stages))
(args.report/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')


def cell(row, metric, scale=1):
    value = row['metrics'].get(metric)
    if value is None:
        return '—'
    return (f"{value['median']/scale:.3f} "
            f"[{value['minimum']/scale:.3f}–{value['maximum']/scale:.3f}]")


lines = ['# Native capacity benchmark matrix', '',
    'Five fresh processes per row; values are median [minimum–maximum]. Seconds unless marked MiB.', '',
    'The native route includes local workflow preparation, execution, cleanup and polling. '
    'The direct route measures callbacks only, with setup and cleanup excluded. '
    'Neither includes CLI startup, fixture loading or installed-client latency. '
    'Each process loads the same prebuilt fixture. Peak RSS includes that load and the runtime. '
    'Dirty cases use the standalone native font writer; actual editor saves are qualified separately.', '',
    '| Route | Format | Targets / contours | Prepare | Dispatch to result | Total or direct callbacks | Verify | Restore | Peak MiB |',
    '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
for row in summary:
    fields = [row['route'], row['format'], f"{row['targets']} / {row['contours']}",
        cell(row, 'preparationSeconds'), cell(row, 'dispatchToResultSeconds'),
        cell(row, 'callbackSeconds' if row['route'] == 'direct' else 'totalSeconds'),
        cell(row, 'verificationSeconds'), cell(row, 'restoreSeconds'),
        cell(row, 'peakRSSBytes', 1024**2)]
    lines.append('| '+' | '.join(fields)+' |')
lines += ['', '## Scheduled and indivisible work', '',
    'These measurements report observed work, not a responsiveness or callback preemption guarantee. '
    'Preparation finalization, baseline hashing and reload can exceed the scheduled chunk budget.', '',
    '| Route | Format | Targets / contours | Longest preparation chunk | Longest scheduled chunk | Longest main call | Longest restore call | Save | Save calls | Request bytes |',
    '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
for row in summary:
    if row['route'] == 'direct':
        continue
    fields = [row['route'], row['format'], f"{row['targets']} / {row['contours']}"]
    fields += [cell(row, key) for key in ('longestPreparationChunkSeconds',
        'longestScheduledChunkSeconds', 'longestMainThreadCallSeconds',
        'longestRestoreCallSeconds', 'saveSeconds', 'saveCalls', 'requestBytes')]
    lines.append('| '+' | '.join(fields)+' |')
lines += ['', 'Per-stage native durations, pre-restoration peak RSS and all ranges are in '
          '[summary.json](summary.json). Raw runs retain source identities and host details.', '']
(args.report/'README.md').write_text('\n'.join(lines))
print(f'Summarized {sum(r["runs"] for r in summary)} runs in {len(summary)} groups.')
