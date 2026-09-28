"""Summarize recorded M8 evidence without hiding timing boundaries."""
import json
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'reports/beta8-milestone8'


def summary(values): return dict(median=statistics.median(values),minimum=min(values),maximum=max(values))


rows=[]
for route in ('script','typed'):
    for suffix in ('glyphs','glyphspackage'):
        for count in (1,10,100):
            runs=[json.loads((REPORT/'matrix'/f'{route}-{suffix}-{count}-{i}.json').read_text()) for i in range(1,6)]
            assert all(r.get('passed') for r in runs)
            metrics={key:summary([r['data'][key] for r in runs]) for key in runs[0]['data'] if key.endswith('Seconds') or key=='peakRSSBytes'}
            rows.append(dict(route=route,format=suffix,count=count,runs=5,metrics=metrics))
proof=[]
for suffix in ('glyphs','glyphspackage'):
    for density in ('sparse','dense'):
        runs=[json.loads((REPORT/'proof-matrix'/f'{suffix}-{density}-{i}.json').read_text()) for i in range(1,6)]
        assert all(r.get('passed') for r in runs)
        for scope in range(3):
            values=[r['data']['evidence'][scope] for r in runs]
            proof.append(dict(format=suffix,density=density,languages=values[0]['languages'],runs=5,
                glyphs=runs[0]['data']['glyphs'],pairs=values[0]['pairs'],pages=len(values[0]['pages']),
                seconds=summary([v['seconds'] for v in values]),longestReadSeconds=summary([v['longestReadSeconds'] for v in values]),
                maxResponseBytes=max(v['maxResponseBytes'] for v in values),
                scannedCandidates=sum(p['scannedCandidates'] for p in values[0]['pages']),
                peakRSSBytes=summary([r['data']['peakRSSBytes'] for r in runs])))
out=dict(assignments=rows,proofs=proof)
(REPORT/'benchmark-summary.json').write_text(json.dumps(out,indent=2)+'\n')
lines=['# Native benchmark evidence','',
 'Five fresh Glyphs CLI processes per route/count/format. Script uses recorded pre-change sources; typed uses the frozen candidate. Counts 100 and the explicit batch boundary are the same case.',
 '', 'Total edit time includes preparation, dispatch/application, polling and independent verification. Saving is a second equivalent result. Typed recovery restores selected entries; script recovery reloads the whole font. These are different recovery guarantees.',
 '', 'Peak RSS includes the Glyphs runtime and fixture, sampled before recovery. Longest chunk measures scheduled preparation/application work, not UI frame rate or all synchronous save/load work. CLI startup, HTTP, Codex latency and actual editor NSDocument saving are excluded and qualified separately.',
 '', '| Route | Format | Pairs | Edit median ms [range] | Prepare ms | Apply/poll ms | Verify ms | Save ms | Recovery ms | Peak MiB | Longest scheduled chunk ms |',
 '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
for row in rows:
 m=row['metrics'];total=m['totalEditSeconds']
 median=lambda key:f"{m[key]['median']*1000:.2f}"
 lines.append(f"| {row['route']} | {row['format']} | {row['count']} | {total['median']*1000:.2f} [{total['minimum']*1000:.2f}–{total['maximum']*1000:.2f}] | {median('preparationSeconds')} | {median('executionPollingSeconds')} | {median('verificationSeconds')} | {median('saveSeconds')} | {median('recoverySeconds')} | {m['peakRSSBytes']['median']/1024**2:.1f} | {median('longestMainThreadChunkSeconds')} |")
lines+=['','All metric ranges, including each stage and RSS, are in `benchmark-summary.json`; individual records retain host and source identities.','',
 '| Format | Glyph coverage | Languages | Returned pairs | Pages | All-page median ms [range] | Longest read median ms | Largest response bytes |',
 '|---|---|---|---:|---:|---:|---:|---:|']
for r in proof:
 s=r['seconds'];langs=','.join(r['languages']) if len(r['languages'])<4 else 'all 24'
 lines.append(f"| {r['format']} | {r['density']} ({r['glyphs']}) | {langs} | {r['pairs']} | {r['pages']} | {s['median']*1000:.2f} [{s['minimum']*1000:.2f}–{s['maximum']*1000:.2f}] | {r['longestReadSeconds']['median']*1000:.2f} | {r['maxResponseBytes']} |")
lines+=['','Proof timings include a cold bounded primary-Unicode map for each language filter. Every page visits at most 256 glyphs or dataset candidates and returns at most 100 pairs. No font-wide kerning table is copied. A page is live evidence, not an atomic font snapshot.','']
(REPORT/'BENCHMARKS.md').write_text('\n'.join(lines))
print('Summarized 60 assignment runs and 20 proof processes (60 language-filter traversals).')
