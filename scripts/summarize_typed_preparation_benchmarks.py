"""Summarize paired native/worker evidence without hiding missing runs."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
from statistics import median
p=argparse.ArgumentParser();p.add_argument('report',type=Path);args=p.parse_args();root=args.report
rows=defaultdict(list)
for path in sorted((root/'benchmarks').glob('*.json')):
 value=json.loads(path.read_text())
 if not value.get('passed'):continue
 d=value['data'];rows[(d['kind'],d['targets'],d['contours'],d['format'],d['route'])].append(d)
metrics=['preparationSeconds','applicationPollingSeconds','totalSeconds','verificationSeconds','selectiveRecoverySeconds','saveSeconds','peakRSSBytes','workerChildrenPeakRSSBytes','longestMainThreadChunkSeconds']
def stats(v):return dict(median=median(v),minimum=min(v),maximum=max(v))
summary=[]
for key,items in sorted(rows.items()):
 summary.append(dict(kind=key[0],targets=key[1],contours=key[2],format=key[3],route=key[4],runs=len(items),
  metrics={m:stats([r[m] for r in items]) for m in metrics},
  preparationLongestChunkSeconds=stats([r['preparationMetrics']['longestChunkSeconds'] for r in items]) if key[4]=='native' else None))
complete=len(summary)==64 and all(r['runs']==5 for r in summary)
comparisons=[]
for key,items in sorted(rows.items()):
 if key[4]!='native' or len(items)!=5:continue
 prior=rows.get((*key[:4],'worker'),[])
 if len(prior)!=5:continue
 comparisons.append(dict(kind=key[0],targets=key[1],contours=key[2],format=key[3],
  preparationSpeedup=median(r['preparationSeconds'] for r in prior)/median(r['preparationSeconds'] for r in items),
  prepareApplySpeedup=median(r['totalSeconds'] for r in prior)/median(r['totalSeconds'] for r in items)))
(root/'benchmark-summary.json').write_text(json.dumps(dict(complete=complete,successfulRuns=sum(map(len,rows.values())),expectedRuns=320,groups=summary,comparisons=comparisons),indent=2)+'\n')
lines=['# Typed preparation benchmark evidence','',f'Complete: **{complete}**. Successful fresh-process runs: **{sum(map(len,rows.values()))}/320**.','',
'Each cell is median [minimum–maximum] in seconds. “Prepare + apply” includes workflow polling, but excludes fixture construction, CLI startup, verification, recovery and the separate Keep/Undo qualification. Native editor saving and installed-client latency are separate gates.','',
'| Task | Targets | Contours | Format | Route | Runs | Preparation | Apply/poll | Prepare + apply | Verification | Selective recovery | Longest scheduled chunk |',
'|---|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|']
def cell(stats):return f"{stats['median']:.4f} [{stats['minimum']:.4f}–{stats['maximum']:.4f}]"
for r in summary:
 m=r['metrics'];lines.append('| '+' | '.join([r['kind'],str(r['targets']),str(r['contours']),r['format'],r['route'],str(r['runs'])]+[cell(m[k]) for k in metrics[:5]]+[cell(m['longestMainThreadChunkSeconds'])])+' |')
lines+=['','## Memory and methodology','',
'Raw JSON records contain isolated macOS parent-process peak RSS before recovery and terminated worker-child peak RSS separately. These peaks are not summed as if simultaneous. Native preparation launches no worker; the worker route launches one for the measured edit. Each process also performs a second edit to check Keep and native Undo/Redo; that qualification is outside the measured preparation/application interval.',
'', 'The longest scheduled chunk measures coordinator preparation/application/recovery callbacks. It does not include standalone verification loops or native Undo/Redo loops driven by the test harness. The existing application cleanup can exceed the nominal chunk budget; these measurements do not establish a canvas frame-rate guarantee.',
'', 'All baseline fonts are saved and clean: task Save calls and saving time are zero for this matrix. `.glyphs` and `.glyphspackage` fixture serialization is real GSFont writing, not the editor NSDocument Save operation. Host CPU load is not isolated; use the five-run ranges, not individual timings. The paired comparison uses the retained worker route in the same candidate.',
'', '| Task / targets / contours / format | Route | Parent peak MiB | Worker-child peak MiB |', '|---|---|---:|---:|']
for r in summary:
 def mib(m):return cell({k:v/(1024*1024) for k,v in r['metrics'][m].items()})
 lines.append(f"| {r['kind']} / {r['targets']} / {r['contours']} / {r['format']} | {r['route']} | {mib('peakRSSBytes')} | {mib('workerChildrenPeakRSSBytes')} |")
(root/'BENCHMARKS.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(dict(complete=complete,successfulRuns=sum(map(len,rows.values())),expectedRuns=320)))
